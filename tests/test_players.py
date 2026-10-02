import json
from types import SimpleNamespace

import httpx
import pytest
from typesafe_sdk import (
    TypeSafeAPITimeoutError,
    TypeSafeBadRequestError,
    TypeSafeInternalServerError,
)

from system_one_control.players import PLAYERS, Turn, make_player
from system_one_control.players.baselines import (
    GreedyPlayer,
    RandomPlayer,
    SolverPlayer,
    WallAwareGreedyPlayer,
)
from system_one_control.players.local import (
    LAYA_OPTION_TOKENS,
    GLiClassPlayer,
    LayaPlayer,
    LocalLLMPlayer,
    laya_budget,
    number_probabilities,
)
from system_one_control.players.remote import (
    ANSWER_TOKENS,
    JEV_RETRY_WAITS,
    LLM_MODELS,
    LLM_SYSTEM,
    OPENROUTER_URL,
    REASONING_TOKENS,
    JevPlayer,
    LLMPlayer,
    jev_body,
    llm_messages,
    parse_answer,
)
from system_one_control.prompts import CONDITIONS
from system_one_control.world import Board, CompassRules
from tests.helpers import MAP

rules = CompassRules()


def turn(text: str) -> Turn:
    board = Board.parse(text)
    return Turn(board, rules, MAP.render(board, rules))


def option_for(t: Turn, move: str) -> str:
    return next(option.id for option in t.request.options if option.move == move)


def test_random_picks_an_offered_move_and_is_reproducible():
    t = turn("#####\n#A.G#\n#####")
    assert RandomPlayer(seed=1).choose(t).move in rules.STEPS
    assert RandomPlayer(seed=1).choose(t).move == RandomPlayer(seed=1).choose(t).move


def test_the_solver_picks_a_best_move():
    assert SolverPlayer().choose(turn("#####\n#A#.#\n#.G.#\n#####")).move == "south"


@pytest.mark.parametrize(
    ("player", "board", "expected"),
    [
        (GreedyPlayer(), "#######\n#K.A.G#\n#######", "west"),
        (GreedyPlayer(), "#######\n#..A.G#\n#######", "east"),
        (GreedyPlayer(), "#####\n#A#G#\n#...#\n#####", "east"),
        (WallAwareGreedyPlayer(), "#####\n#A#G#\n#...#\n#####", "south"),
    ],
    ids=[
        "greedy heads for the key before the goal",
        "greedy heads straight for the goal",
        "greedy walks into the wall between it and the goal",
        "greedy with walls steps around instead",
    ],
)
def test_greedy_steps_toward_the_next_target(player, board, expected):
    assert player.choose(turn(board)).move == expected


def test_greedy_breaks_ties_the_same_way_whatever_the_option_order():
    board = Board.parse("####\n#A.#\n#.G#\n####")
    requests = [MAP.render(board, rules, shuffle_seed=seed) for seed in "abcd"]
    moves = {GreedyPlayer().choose(Turn(board, rules, request)).move for request in requests}
    assert moves == {"south"}  # south and east both close in; south comes first in the rules


def test_players_are_built_by_name_and_only_jev_and_the_chat_models_cost_money():
    assert isinstance(make_player("random"), RandomPlayer)
    paid = {name for name, entry in PLAYERS.items() if entry.paid}
    assert paid == {"jev", *LLM_MODELS, *(f"{name}-think" for name in LLM_MODELS)}
    assert not PLAYERS["laya"].paid and not PLAYERS["gliclass"].paid
    with pytest.raises(ValueError, match="unknown player"):
        make_player("chess-engine")


class FakeJevClient:
    def __init__(
        self,
        choice: str = "option_3",
        fail: Exception | None = None,
        failures: list[Exception] | None = None,
    ) -> None:
        self.choice, self.fail, self.sent = choice, fail, {}
        self.failures, self.calls = failures or [], 0

    def system_one(self, *, state, questions, model):
        self.calls += 1
        if self.fail:
            raise self.fail
        if self.failures:
            raise self.failures.pop(0)
        self.sent = {"state": state, "model": model, "questions": questions}
        probabilities = {"option_1": 0.1, "option_2": 0.1, "option_3": 0.7, "option_4": 0.1}
        answer = SimpleNamespace(choice=self.choice, probabilities=probabilities, confidence=0.6)
        usage = SimpleNamespace(input_tokens=120, output_tokens=3)
        return SimpleNamespace(choices={"move": answer}, usage=usage, model="jev-1.13.0")


def jev(client: FakeJevClient) -> JevPlayer:
    return JevPlayer(client=client)


def test_jev_is_sent_exactly_the_request_and_its_answer_maps_back_to_a_move():
    client = FakeJevClient()
    t = turn("#####\n#A.G#\n#####")
    choice = jev(client).choose(t)

    assert client.sent == jev_body(t.request)
    assert client.sent["state"] == t.request.state
    question = client.sent["questions"]["move"]
    assert question["type"] == "choice"
    assert question["instructions"] == t.request.question
    assert question["criteria"] == {o.id: o.text for o in t.request.options}
    assert choice.move == "east"
    assert choice.probabilities["east"] == 0.7
    assert choice.input_tokens == 120
    assert (choice.output_tokens, choice.confidence, choice.model) == (3, 0.6, "jev-1.13.0")


def test_a_failed_jev_call_is_raised_for_the_game_to_record():
    with pytest.raises(RuntimeError, match="rate limited"):
        jev(FakeJevClient(fail=RuntimeError("rate limited"))).choose(turn("####\n#AG#\n####"))


def test_jev_closes_only_a_client_it_opened_itself():
    jev(FakeJevClient()).close()  # the fake has no close(), so closing it would raise


def test_an_answer_outside_the_options_is_an_error():
    choice = jev(FakeJevClient(choice="option_9")).choose(turn("####\n#AG#\n####"))
    assert choice.move is None
    assert "option_9" in choice.error


TINY = """
####
#AG#
####
"""
BUSY = TypeSafeInternalServerError(529, {"error": "high traffic"}, httpx.Headers())


def retrying_jev(*failures: Exception) -> tuple[JevPlayer, FakeJevClient]:
    """Jev on a client that raises each of `failures` in turn, then answers; no real waits."""
    client = FakeJevClient(failures=list(failures))
    return JevPlayer(client=client, retry_waits=(0, 0)), client


def test_a_busy_server_is_tried_again_and_the_move_records_why():
    player, client = retrying_jev(BUSY, BUSY)
    choice = player.choose(turn(TINY))
    assert choice.move == "east" and client.calls == 3
    assert choice.retried == ("TypeSafeInternalServerError: 529 high traffic",) * 2


def test_after_two_retries_the_failure_is_raised():
    player, client = retrying_jev(BUSY, BUSY, BUSY)
    with pytest.raises(TypeSafeInternalServerError):
        player.choose(turn(TINY))
    assert client.calls == 3


@pytest.mark.parametrize(
    "failure",
    [
        TypeSafeAPITimeoutError(60.0),
        TypeSafeBadRequestError(400, {"error": "bad"}, httpx.Headers()),
    ],
    ids=["a timeout may already have been answered and billed", "a bad request will not heal"],
)
def test_a_timeout_or_a_bad_request_is_not_tried_again(failure):
    player, client = retrying_jev(failure)
    with pytest.raises(type(failure)):
        player.choose(turn(TINY))
    assert client.calls == 1


def test_the_time_recorded_is_the_answering_call_alone():
    player, _ = retrying_jev(BUSY)
    player._retry_waits = (0.3, 0.3)
    choice = player.choose(turn(TINY))
    assert choice.seconds is not None and choice.seconds < 0.3
    assert JEV_RETRY_WAITS == (1.0, 2.0)


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


def llm(client: httpx.Client, reasoning: bool = False) -> LLMPlayer:
    return LLMPlayer("qwen/qwen3.7-flash", reasoning=reasoning, client=client, retry_waits=(0, 0))


def test_a_chat_model_is_sent_the_request_and_its_answer_maps_back_to_a_move():
    t = turn("####\n#AG#\n####")
    client, sent = answering(option_for(t, "east"))
    choice = llm(client).choose(t)
    assert choice.move == "east" and choice.error is None
    assert (choice.input_tokens, choice.output_tokens, choice.cost) == (700, 4, 0.00002)
    assert choice.model == "qwen/qwen3.7-flash via Alibaba"
    assert choice.probabilities == {}
    assert sent[0]["messages"] == llm_messages(t.request)
    assert sent[0]["messages"][0]["content"] == LLM_SYSTEM


def test_the_chat_carries_the_state_the_question_and_every_option_by_id():
    board = Board.parse("####\n#AG#\n####")
    request = CONDITIONS["everything"].render(board, rules)
    user = llm_messages(request)[1]["content"]
    assert request.state in user and request.question in user
    for option in request.options:
        assert f"{option.id}: {option.text}" in user


def test_without_reasoning_the_model_must_answer_at_once_and_with_it_may_think():
    t = turn("####\n#AG#\n####")
    quick, reasoned = llm(answering()[0]).body(t.request), llm(answering()[0], True).body(t.request)
    assert quick["reasoning"] == {"enabled": False, "exclude": True}
    assert quick["max_tokens"] == ANSWER_TOKENS
    assert reasoned["reasoning"] == {"enabled": True, "exclude": True}
    assert reasoned["max_tokens"] == REASONING_TOKENS  # room to think, but not without end


def test_the_answer_must_be_json_naming_one_of_the_options():
    t = turn("####\n#AG#\n####")
    body = llm(answering()[0]).body(t.request)
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["option"]["enum"] == [option.id for option in t.request.options]
    assert schema["required"] == ["option"]
    assert body["provider"] == {"require_parameters": True}


def test_a_model_can_be_pinned_to_one_host():
    t = turn("####\n#AG#\n####")
    player = LLMPlayer("m", reasoning=False, host="deepinfra", client=answering()[0])
    assert player.body(t.request)["provider"] == {
        "require_parameters": True,
        "order": ["deepinfra"],
        "allow_fallbacks": False,
    }


def test_an_answer_in_json_maps_back_to_a_move():
    t = turn("####\n#AG#\n####")
    client, _ = answering(json.dumps({"option": option_for(t, "east")}))
    assert llm(client).choose(t).move == "east"


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
    t = turn("####\n#AG#\n####")
    assert parse_answer(text, t.request) == expected


def test_an_answer_cut_off_by_the_token_cap_is_an_error_even_if_it_names_an_option():
    # Cut off while writing option_12, it would read as option_1.
    t = turn("####\n#AG#\n####")
    cut = {"message": {"content": '{"option": "option_1'}, "finish_reason": "length"}
    client, _ = answering({"model": "m", "choices": [cut]})
    choice = llm(client).choose(t)
    assert choice.move is None
    assert "ran out of tokens" in choice.error


def test_an_answer_without_an_option_id_is_an_error_that_quotes_it():
    client, _ = answering("I would go east")
    choice = llm(client).choose(turn("####\n#AG#\n####"))
    assert choice.move is None
    assert "I would go east" in choice.error


def test_a_busy_provider_is_tried_again_and_the_move_records_why():
    t = turn("####\n#AG#\n####")
    client, sent = answering(429, 503, option_for(t, "east"))
    choice = llm(client).choose(t)
    assert choice.move == "east" and len(sent) == 3
    assert len(choice.retried) == 2


def test_an_error_reported_inside_a_success_is_tried_again_too():
    t = turn("####\n#AG#\n####")
    client, sent = answering({"error": {"code": 502, "message": "upstream"}}, option_for(t, "east"))
    assert llm(client).choose(t).move == "east" and len(sent) == 2


def test_a_bad_request_is_raised_at_once_for_the_game_to_record():
    client, sent = answering(400)
    with pytest.raises(httpx.HTTPStatusError):
        llm(client).choose(turn("####\n#AG#\n####"))
    assert len(sent) == 1


def words(text: str) -> int:
    return len(text.split())


class FakeTokenizer:
    """Counts a token per word."""

    def __call__(self, text: str, add_special_tokens: bool = False) -> dict:
        return {"input_ids": list(range(words(text)))}


class FakeLaya:
    def __init__(self, pick: int = 2) -> None:
        self.tok, self.pick, self.sent = FakeTokenizer(), pick, {}

    def system_one(self, state, questions, max_len, head_max_len):
        self.sent = {"state": state, "questions": questions, "budget": (max_len, head_max_len)}
        texts = questions["move"]["criteria"]
        probabilities = dict.fromkeys(texts, 0.1) | {texts[self.pick]: 0.7}
        answer = {"choice": texts[self.pick], "probabilities": probabilities, "confidence": 0.6}
        return {"answers": {"move": answer}, "usage": {"input_tokens": 321, "output_tokens": 0}}


def test_laya_is_asked_the_question_with_the_option_texts_and_answers_with_one():
    t = turn("####\n#AG#\n####")
    laya = FakeLaya(pick=2)
    choice = LayaPlayer(agent=laya).choose(t)
    question = laya.sent["questions"]["move"]
    assert laya.sent["state"] == t.request.state
    assert question["instructions"] == t.request.question
    assert question["criteria"] == [option.text for option in t.request.options]
    assert choice.move == t.request.options[2].move
    assert choice.probabilities[choice.move] == 0.7
    assert sum(choice.probabilities.values()) == pytest.approx(1.0)
    assert (choice.input_tokens, choice.confidence) == (321, 0.6)


def test_laya_gets_room_for_the_whole_request():
    board = Board.parse("####\n#AG#\n####")
    request = CONDITIONS["everything"].render(board, rules)
    max_len, head = laya_budget(words, request)
    options = sum(words(" " + option.text) + 1 for option in request.options)
    assert head >= words(f"choice question: {request.question}") + options + 16
    assert max_len >= head + words(request.state)


def test_an_option_longer_than_laya_reads_is_refused_rather_than_cut():
    t = turn("####\n#AG#\n####")
    with pytest.raises(ValueError, match="longer"):
        laya_budget(lambda text: LAYA_OPTION_TOKENS + 1 if "east" in text else 5, t.request)


class FakeGLiClass:
    def __init__(self, best: int = 1) -> None:
        self.best, self.sent = best, {}

    def __call__(self, text, labels, threshold, prompt):
        self.sent = {"text": text, "labels": labels, "threshold": threshold, "prompt": prompt}
        return [
            [
                {"label": label, "score": 0.9 if i == self.best else 0.1}
                for i, label in enumerate(labels)
            ]
        ]


def test_gliclass_classifies_the_state_by_the_option_texts_under_the_question():
    t = turn("####\n#AG#\n####")
    gliclass = FakeGLiClass(best=1)
    choice = GLiClassPlayer(pipeline=gliclass).choose(t)
    assert gliclass.sent["text"] == t.request.state
    assert gliclass.sent["prompt"] == t.request.question
    assert gliclass.sent["labels"] == [option.text for option in t.request.options]
    assert gliclass.sent["threshold"] == 0.0  # every option's score comes back
    assert choice.move == t.request.options[1].move
    assert choice.probabilities[choice.move] == pytest.approx(0.9 / 1.2)
    assert sum(choice.probabilities.values()) == pytest.approx(1.0)


def digits_after(table: dict[str, list[float]], asked: list[str]):
    """next_digits for number_probabilities, from a table by what has been written."""

    def next_digits(written: str) -> list[float]:
        asked.append(written)
        return table[written]

    return next_digits


def test_single_digit_numbers_share_the_first_digit_among_themselves():
    asked: list[str] = []
    first = [0.0, 0.5, 0.2, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.1]  # 0.1 on 9, which is not offered
    found = number_probabilities({"1", "2", "3", "4"}, digits_after({"": first}, asked))
    assert found == pytest.approx({"1": 0.5 / 0.9, "2": 0.2 / 0.9, "3": 0.1 / 0.9, "4": 0.1 / 0.9})
    assert asked == [""]  # one pass: no number is longer than a digit


def test_a_number_that_others_extend_shares_with_them_the_chance_of_ending_there():
    asked: list[str] = []
    table = {
        "": [0.0, 0.8, 0.2] + [0.0] * 7,
        "1": [0.5, 0.0, 0.3] + [0.0] * 7,  # 0.5 on 10, 0.3 on 12 (not offered), 0.2 to end
    }
    found = number_probabilities({"1", "2", "10", "11"}, digits_after(table, asked))
    assert found == pytest.approx(
        {"1": 0.8 * 0.2 / 0.7, "10": 0.8 * 0.5 / 0.7, "11": 0.0, "2": 0.2}
    )
    assert sum(found.values()) == pytest.approx(1.0)
    assert sorted(asked) == ["", "1"]  # 10 and 11 end where nothing longer is offered


class FakeLocalLLM:
    def __init__(self, favourite: str) -> None:
        self.favourite = favourite

    def prompt(self, request):
        return [7] * 42

    def option_probabilities(self, request, prompt):
        others = [o.id for o in request.options if o.id != self.favourite]
        return {self.favourite: 0.7} | dict.fromkeys(others, 0.3 / len(others))


def test_a_local_chat_model_plays_the_option_it_gives_the_most_probability():
    t = turn("####\n#AG#\n####")
    favourite = option_for(t, "east")
    choice = LocalLLMPlayer("org/model", model=FakeLocalLLM(favourite)).choose(t)
    assert choice.move == "east" and choice.error is None
    assert choice.probabilities["east"] == 0.7
    assert (choice.input_tokens, choice.model) == (42, "org/model")
