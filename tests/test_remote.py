import json
from types import SimpleNamespace

import httpx
import pytest
from typesafe_sdk import (
    TypeSafeAPITimeoutError,
    TypeSafeBadRequestError,
    TypeSafeInternalServerError,
)

from system_one_control.players.remote import (
    ANSWER_TOKENS,
    JEV_MODEL,
    JEV_RETRY_WAITS,
    LLM_SYSTEM,
    OPENROUTER_URL,
    REASONING_BUDGET,
    JevPlayer,
    LLMPlayer,
    chat_payload,
    jev_body,
    llm_messages,
    parse_answer,
    with_retries,
)
from system_one_control.prompts import CONDITIONS
from system_one_control.world import Board, CompassRules
from tests.helpers import option_for, turn

TINY = "####\n#AG#\n####"
BUSY = TypeSafeInternalServerError(529, {"error": "high traffic"}, httpx.Headers())
BAD = TypeSafeBadRequestError(400, {"error": "bad"}, httpx.Headers())
REQUEST = CONDITIONS["everything"].render(Board.parse(TINY), CompassRules())


def flaky(*failures):
    """A call that raises each of `failures` in turn, then returns "ok"."""
    queue = list(failures)

    def call():
        if queue:
            raise queue.pop(0)
        return "ok"

    return call


@pytest.mark.parametrize(
    ("failures", "slept", "retried"),
    [
        ((), [], ()),
        ((RuntimeError("a"),), [0.5], ("RuntimeError: a",)),
        (
            (RuntimeError("a"), RuntimeError("b")),
            [0.5, 1.0],
            ("RuntimeError: a", "RuntimeError: b"),
        ),
    ],
    ids=["no failure", "one failure", "two failures"],
)
def test_a_failing_call_is_tried_again_after_each_wait(failures, slept, retried):
    waited = []
    result, _, why = with_retries(flaky(*failures), (0.5, 1.0), lambda e: True, waited.append)
    assert (result, waited, why) == ("ok", slept, retried)


@pytest.mark.parametrize(
    ("failures", "retryable", "slept"),
    [
        ((ValueError(),) * 3, True, [0.5, 1.0]),
        ((ValueError(),), False, []),
    ],
    ids=["the last failure is raised", "a failure not worth retrying is raised at once"],
)
def test_a_call_that_keeps_failing_raises(failures, retryable, slept):
    waited = []
    with pytest.raises(ValueError):
        with_retries(flaky(*failures), (0.5, 1.0), lambda e: retryable, waited.append)
    assert waited == slept


def test_jev_is_sent_exactly_the_request():
    assert jev_body(REQUEST) == {
        "state": REQUEST.state,
        "model": JEV_MODEL,
        "questions": {
            "move": {
                "type": "choice",
                "instructions": REQUEST.question,
                "criteria": {o.id: o.text for o in REQUEST.options},
            }
        },
    }


class FakeJevClient:
    def __init__(self, choice="option_3", failures=()):
        self.choice, self.failures, self.calls, self.sent = choice, list(failures), 0, {}

    def system_one(self, *, state, questions, model):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        self.sent = {"state": state, "model": model, "questions": questions}
        probabilities = {"option_1": 0.1, "option_2": 0.1, "option_3": 0.7, "option_4": 0.1}
        answer = SimpleNamespace(choice=self.choice, probabilities=probabilities, confidence=0.6)
        usage = SimpleNamespace(input_tokens=120, output_tokens=3)
        return SimpleNamespace(choices={"move": answer}, usage=usage, model="jev-1.13.0")


def jev(*failures, choice="option_3"):
    client = FakeJevClient(choice, failures)
    return JevPlayer(client=client, retry_waits=(0, 0)), client


def test_jevs_answer_maps_back_to_a_move_with_its_probabilities_and_cost():
    t = turn(TINY)
    player, client = jev()
    choice = player.choose(t)
    assert client.sent == jev_body(t.request)
    assert (choice.move, choice.probabilities["east"], choice.input_tokens) == ("east", 0.7, 120)
    assert (choice.output_tokens, choice.confidence, choice.model) == (3, 0.6, "jev-1.13.0")


def test_an_answer_outside_the_options_is_an_error():
    choice = jev(choice="option_9")[0].choose(turn(TINY))
    assert choice.move is None and "option_9" in choice.error


@pytest.mark.parametrize(
    ("failures", "calls"), [((BUSY,), 2), ((BUSY, BUSY), 3)], ids=["once", "twice"]
)
def test_a_busy_server_is_tried_again_and_the_move_records_why(failures, calls):
    player, client = jev(*failures)
    choice = player.choose(turn(TINY))
    assert (choice.move, client.calls, len(choice.retried)) == ("east", calls, len(failures))
    assert choice.retried[0] == "TypeSafeInternalServerError: 529 high traffic"


@pytest.mark.parametrize(
    ("failures", "error", "calls"),
    [
        ((BUSY, BUSY, BUSY), TypeSafeInternalServerError, 3),
        ((TypeSafeAPITimeoutError(60.0),), TypeSafeAPITimeoutError, 1),
        ((BAD,), TypeSafeBadRequestError, 1),
        ((RuntimeError("rate limited"),), RuntimeError, 1),
    ],
    ids=[
        "after two retries the failure is raised",
        "a timeout may already have been billed",
        "a bad request will not heal",
        "any other failure is raised for the game to record",
    ],
)
def test_a_failed_jev_call_is_raised_for_the_game_to_record(failures, error, calls):
    player, client = jev(*failures)
    with pytest.raises(error):
        player.choose(turn(TINY))
    assert client.calls == calls


def test_the_time_recorded_is_the_answering_call_alone():
    player, _ = jev(BUSY)
    player._retry_waits = (0.3, 0.3)
    assert player.choose(turn(TINY)).seconds < 0.3
    assert JEV_RETRY_WAITS == (1.0, 2.0)


def test_jev_closes_only_a_client_it_opened_itself():
    jev()[0].close()  # the fake has no close(), so closing it would raise


# Chat models on OpenRouter


@pytest.mark.parametrize(
    ("reasoning", "key", "expected"),
    [
        (False, "messages", llm_messages(REQUEST)),
        (False, "reasoning", {"enabled": False, "exclude": True}),
        (False, "max_tokens", ANSWER_TOKENS),
        (False, "provider", {"require_parameters": True}),
        (False, "usage", {"include": True}),
        (True, "reasoning", {"enabled": True, "exclude": True, "max_tokens": REASONING_BUDGET}),
        (True, "max_tokens", REASONING_BUDGET + ANSWER_TOKENS),
    ],
    ids=[
        "the chat",
        "answering at once",
        "a short answer",
        "providers that enforce the format",
        "the cost comes back",
        "thinking first, within a budget",
        "room to think and answer",
    ],
)
def test_the_chat_payload(reasoning, key, expected):
    assert chat_payload(REQUEST, reasoning)[key] == expected


def test_the_answer_must_be_json_naming_one_of_the_options():
    schema = chat_payload(REQUEST, False)["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["option"]["enum"] == [o.id for o in REQUEST.options]
    assert schema["required"] == ["option"]


def test_the_chat_carries_the_system_text_the_state_the_question_and_every_option_by_id():
    system, user = llm_messages(REQUEST)
    assert system["content"] == LLM_SYSTEM
    assert REQUEST.state in user["content"] and REQUEST.question in user["content"]
    assert all(f"{o.id}: {o.text}" in user["content"] for o in REQUEST.options)


def test_a_model_can_be_pinned_to_one_host():
    player = LLMPlayer("m", reasoning=False, host="deepinfra", client=object())
    assert player.body(REQUEST)["provider"] == {
        "require_parameters": True,
        "order": ["deepinfra"],
        "allow_fallbacks": False,
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("option_1, no: option_3", "option_3"),
        ("  option_2\n", "option_2"),
        ("option_9", None),
        ("east", None),
        ('{"option": "option_2"}', "option_2"),
        ('{"option": "option_9"} option_1', "option_1"),
    ],
    ids=[
        "the last option id wins",
        "surrounding whitespace is fine",
        "an id outside the options is no answer",
        "a move name is no answer",
        "the asked-for json is read first",
        "json naming nothing offered falls back to the text",
    ],
)
def test_reading_the_option_out_of_a_chat_answer(text, expected):
    assert parse_answer(text, turn(TINY).request) == expected


def answering(*replies) -> tuple[httpx.Client, list[dict]]:
    """A client whose server gives each reply in turn: a text, an HTTP status, or a dict."""
    sent: list[dict] = []
    replies = list(replies)

    def handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == OPENROUTER_URL
        sent.append(json.loads(request.content))
        reply = replies.pop(0)
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": {"code": reply, "message": "busy"}})
        if isinstance(reply, dict):
            return httpx.Response(200, json=reply)
        usage = {"prompt_tokens": 700, "completion_tokens": 4, "cost": 0.00002}
        message = {"role": "assistant", "content": reply}
        body = {"model": "qwen/qwen3.7-flash", "provider": "Alibaba", "usage": usage}
        return httpx.Response(200, json={**body, "choices": [{"message": message}]})

    return httpx.Client(transport=httpx.MockTransport(handle)), sent


def llm(client: httpx.Client) -> LLMPlayer:
    return LLMPlayer("qwen/qwen3.7-flash", reasoning=False, client=client, retry_waits=(0, 0))


def test_a_chat_models_answer_maps_back_to_a_move_with_its_cost():
    t = turn(TINY)
    client, sent = answering(option_for(t, "east"))
    choice = llm(client).choose(t)
    assert (choice.move, choice.error, choice.probabilities) == ("east", None, {})
    assert (choice.input_tokens, choice.output_tokens, choice.cost) == (700, 4, 0.00002)
    assert choice.model == "qwen/qwen3.7-flash via Alibaba"
    assert sent[0]["messages"] == llm_messages(t.request)


def test_an_answer_in_json_maps_back_to_a_move():
    t = turn(TINY)
    client, _ = answering(json.dumps({"option": option_for(t, "east")}))
    assert llm(client).choose(t).move == "east"


@pytest.mark.parametrize(
    ("reply", "fragment"),
    [
        (
            {
                "model": "m",
                "choices": [
                    {"message": {"content": '{"option": "option_1'}, "finish_reason": "length"}
                ],
            },
            "ran out of tokens",
        ),
        ("I would go east", "I would go east"),
    ],
    ids=["cut off by the token cap, even if it names an option", "no option id, quoted"],
)
def test_an_answer_that_names_no_option_is_an_error(reply, fragment):
    client, _ = answering(reply)
    choice = llm(client).choose(turn(TINY))
    assert choice.move is None and fragment in choice.error


@pytest.mark.parametrize(
    ("before", "calls"),
    [
        ([429, 503], 3),
        ([{"error": {"code": 502, "message": "upstream"}}], 2),
    ],
    ids=["a busy provider", "an error reported inside a success"],
)
def test_a_provider_that_turns_a_call_away_is_tried_again(before, calls):
    t = turn(TINY)
    client, sent = answering(*before, option_for(t, "east"))
    choice = llm(client).choose(t)
    assert (choice.move, len(sent), len(choice.retried)) == ("east", calls, len(before))


def test_a_bad_request_is_raised_at_once_for_the_game_to_record():
    client, sent = answering(400)
    with pytest.raises(httpx.HTTPStatusError):
        llm(client).choose(turn(TINY))
    assert len(sent) == 1
