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
    JEV_MODEL,
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
REQUEST = CONDITIONS["everything"].render(Board.parse(TINY), CompassRules())
THINKING = {"enabled": True, "exclude": True, "max_tokens": REASONING_BUDGET}
CUT_OFF = {"message": {"content": '{"option": "option_1'}, "finish_reason": "length"}
UPSTREAM = {"error": {"code": 502, "message": "upstream"}}


def flaky(*failures):
    """A call that raises each of `failures` in turn, then returns "ok"."""
    queue = list(failures)

    def call():
        if queue:
            raise queue.pop(0)
        return "ok"

    return call


def test_a_failing_call_is_tried_again_after_each_wait():
    waited = []
    call = flaky(KeyError("a"), KeyError("b"))
    result, _, why = with_retries(call, (0.5, 1.0), lambda e: True, waited.append)
    assert (result, waited, why) == ("ok", [0.5, 1.0], ("KeyError: 'a'", "KeyError: 'b'"))


@pytest.mark.parametrize(
    ("failures", "retryable", "slept"),
    [
        pytest.param(3, True, [0.5, 1.0], id="the last failure is raised"),
        pytest.param(1, False, [], id="a failure not worth retrying"),
    ],
)
def test_a_call_that_keeps_failing_raises(failures, retryable, slept):
    waited = []
    with pytest.raises(ValueError):
        with_retries(
            flaky(*[ValueError()] * failures), (0.5, 1.0), lambda e: retryable, waited.append
        )
    assert waited == slept


def test_jev_is_sent_exactly_the_request():
    criteria = {o.id: o.text for o in REQUEST.options}
    question = {"type": "choice", "instructions": REQUEST.question, "criteria": criteria}
    assert jev_body(REQUEST) == {
        "state": REQUEST.state,
        "model": JEV_MODEL,
        "questions": {"move": question},
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


def test_a_busy_server_is_tried_again_and_the_move_records_why():
    player, client = jev(BUSY, BUSY)
    choice = player.choose(turn(TINY))
    assert (choice.move, client.calls, len(choice.retried)) == ("east", 3, 2)
    assert choice.retried[0] == "TypeSafeInternalServerError: 529 high traffic"


@pytest.mark.parametrize(
    ("failures", "calls"),
    [
        pytest.param((BUSY,) * 3, 3, id="after two retries"),
        pytest.param((TypeSafeAPITimeoutError(60.0),), 1, id="a timeout is not retried"),
        pytest.param((TypeSafeBadRequestError(400, {}, httpx.Headers()),), 1, id="a bad request"),
    ],
)
def test_a_failed_jev_call_is_raised_for_the_game_to_record(failures, calls):
    player, client = jev(*failures)
    with pytest.raises(type(failures[0])):
        player.choose(turn(TINY))
    assert client.calls == calls


@pytest.mark.parametrize(
    ("reasoning", "expected"),
    [
        pytest.param(False, {"enabled": False, "exclude": True}, id="answering at once"),
        pytest.param(True, THINKING, id="thinking within a budget"),
    ],
)
def test_the_chat_payload_asks_for_reasoning_or_not(reasoning, expected):
    assert chat_payload(REQUEST, reasoning)["reasoning"] == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("option_1, no: option_3", "option_3", id="the last option id wins"),
        pytest.param("option_9", None, id="an id outside the options"),
        pytest.param("east", None, id="a move name"),
        pytest.param('{"option": "option_2"}', "option_2", id="the asked-for json"),
        pytest.param('{"option": "option_9"} option_1', "option_1", id="json naming nothing"),
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


@pytest.mark.parametrize(
    ("reply", "fragment"),
    [
        pytest.param({"choices": [CUT_OFF]}, "ran out of tokens", id="cut off, naming an option"),
        pytest.param("I would go east", "I would go east", id="no option id, quoted"),
    ],
)
def test_an_answer_that_names_no_option_is_an_error(reply, fragment):
    choice = llm(answering(reply)[0]).choose(turn(TINY))
    assert choice.move is None and fragment in choice.error


@pytest.mark.parametrize(
    "before",
    [pytest.param([429, 503], id="a busy provider"), pytest.param([UPSTREAM], id="error in a 200")],
)
def test_a_provider_that_turns_a_call_away_is_tried_again(before):
    t = turn(TINY)
    client, sent = answering(*before, option_for(t, "east"))
    choice = llm(client).choose(t)
    assert (choice.move, len(sent), len(choice.retried)) == ("east", len(before) + 1, len(before))


def test_a_bad_request_is_raised_at_once_for_the_game_to_record():
    client, sent = answering(400)
    with pytest.raises(httpx.HTTPStatusError):
        llm(client).choose(turn(TINY))
    assert len(sent) == 1
