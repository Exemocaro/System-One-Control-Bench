import json

import httpx
import pytest

from system_one_control.board import Board
from system_one_control.conditions import CONDITIONS
from system_one_control.llm_players import (
    ANSWER_TOKENS,
    LLM_SYSTEM,
    OPENROUTER_URL,
    REASONING_TOKENS,
    LLMPlayer,
    llm_messages,
    parse_answer,
)
from system_one_control.local_players import (
    LAYA_OPTION_TOKENS,
    GLiClassPlayer,
    LayaPlayer,
    LocalLLMPlayer,
    laya_budget,
    number_probabilities,
)
from system_one_control.players import Turn
from system_one_control.rules import CompassRules
from tests.helpers import MAP

rules = CompassRules()
BOARD = Board.parse("####\n#AG#\n####")


def turn(board: Board = BOARD, condition=MAP, rules=rules) -> Turn:
    return Turn(board, rules, condition.render(board, rules))


def option_for(t: Turn, move: str) -> str:
    return next(option.id for option in t.request.options if option.move == move)


# --- Chat models on OpenRouter ---------------------------------------------------------------


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
    t = turn()
    client, sent = answering(option_for(t, "east"))
    choice = llm(client).choose(t)
    assert choice.move == "east" and choice.error is None
    assert (choice.input_tokens, choice.output_tokens, choice.cost) == (700, 4, 0.00002)
    assert choice.model == "qwen/qwen3.7-flash via Alibaba"
    assert choice.probabilities == {}
    assert sent[0]["messages"] == llm_messages(t.request)
    assert sent[0]["messages"][0]["content"] == LLM_SYSTEM


def test_the_chat_carries_the_state_the_question_and_every_option_by_id():
    t = turn(condition=CONDITIONS["everything"])
    user = llm_messages(t.request)[1]["content"]
    assert t.request.state in user and t.request.question in user
    for option in t.request.options:
        assert f"{option.id}: {option.text}" in user


def test_without_reasoning_the_model_must_answer_at_once_and_with_it_may_think():
    t = turn()
    quick, reasoned = llm(answering()[0]).body(t.request), llm(answering()[0], True).body(t.request)
    assert quick["reasoning"] == {"enabled": False, "exclude": True}
    assert quick["max_tokens"] == ANSWER_TOKENS
    assert reasoned["reasoning"] == {"enabled": True, "exclude": True}
    assert reasoned["max_tokens"] == REASONING_TOKENS  # room to think, but not without end


def test_the_answer_must_be_json_naming_one_of_the_options():
    t = turn()
    body = llm(answering()[0]).body(t.request)
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["option"]["enum"] == [option.id for option in t.request.options]
    assert schema["required"] == ["option"]
    assert body["provider"] == {"require_parameters": True}


def test_a_model_can_be_pinned_to_one_host():
    t = turn()
    player = LLMPlayer("m", reasoning=False, host="deepinfra", client=answering()[0])
    assert player.body(t.request)["provider"] == {
        "require_parameters": True,
        "order": ["deepinfra"],
        "allow_fallbacks": False,
    }


def test_an_answer_in_json_maps_back_to_a_move():
    t = turn()
    client, _ = answering(json.dumps({"option": option_for(t, "east")}))
    assert llm(client).choose(t).move == "east"


def test_the_last_option_id_in_the_answer_is_the_one_taken():
    t = turn()
    assert parse_answer("option_1, no: option_3", t.request) == "option_3"
    assert parse_answer("  option_2\n", t.request) == "option_2"
    assert parse_answer("option_9", t.request) is None
    assert parse_answer("east", t.request) is None


def test_the_json_answer_is_read_before_any_id_in_the_text():
    t = turn()
    assert parse_answer('{"option": "option_2"}', t.request) == "option_2"
    assert parse_answer('{"option": "option_9"} option_1', t.request) == "option_1"


def test_an_answer_cut_off_by_the_token_cap_is_an_error_even_if_it_names_an_option():
    # Cut off while writing option_12, it would read as option_1.
    t = turn()
    cut = {"message": {"content": '{"option": "option_1'}, "finish_reason": "length"}
    client, _ = answering({"model": "m", "choices": [cut]})
    choice = llm(client).choose(t)
    assert choice.move is None
    assert "ran out of tokens" in choice.error


def test_an_answer_without_an_option_id_is_an_error_that_quotes_it():
    client, _ = answering("I would go east")
    choice = llm(client).choose(turn())
    assert choice.move is None
    assert "I would go east" in choice.error


def test_a_busy_provider_is_tried_again_and_the_move_records_why():
    t = turn()
    client, sent = answering(429, 503, option_for(t, "east"))
    choice = llm(client).choose(t)
    assert choice.move == "east" and len(sent) == 3
    assert len(choice.retried) == 2


def test_an_error_reported_inside_a_success_is_tried_again_too():
    t = turn()
    client, sent = answering({"error": {"code": 502, "message": "upstream"}}, option_for(t, "east"))
    assert llm(client).choose(t).move == "east" and len(sent) == 2


def test_a_bad_request_is_raised_at_once_for_the_game_to_record():
    client, sent = answering(400)
    with pytest.raises(httpx.HTTPStatusError):
        llm(client).choose(turn())
    assert len(sent) == 1


# --- Laya ------------------------------------------------------------------------------------


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
    t = turn()
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
    t = turn(condition=CONDITIONS["everything"])
    max_len, head = laya_budget(words, t.request)
    options = sum(words(" " + option.text) + 1 for option in t.request.options)
    assert head >= words(f"choice question: {t.request.question}") + options + 16
    assert max_len >= head + words(t.request.state)


def test_an_option_longer_than_laya_reads_is_refused_rather_than_cut():
    t = turn()
    with pytest.raises(ValueError, match="longer"):
        laya_budget(lambda text: LAYA_OPTION_TOKENS + 1 if "east" in text else 5, t.request)


# --- GLiClass --------------------------------------------------------------------------------


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
    t = turn()
    gliclass = FakeGLiClass(best=1)
    choice = GLiClassPlayer(pipeline=gliclass).choose(t)
    assert gliclass.sent["text"] == t.request.state
    assert gliclass.sent["prompt"] == t.request.question
    assert gliclass.sent["labels"] == [option.text for option in t.request.options]
    assert gliclass.sent["threshold"] == 0.0  # every option's score comes back
    assert choice.move == t.request.options[1].move
    assert choice.probabilities[choice.move] == pytest.approx(0.9 / 1.2)
    assert sum(choice.probabilities.values()) == pytest.approx(1.0)


# --- Chat models on this machine -------------------------------------------------------------


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
    t = turn()
    favourite = option_for(t, "east")
    choice = LocalLLMPlayer("org/model", model=FakeLocalLLM(favourite)).choose(t)
    assert choice.move == "east" and choice.error is None
    assert choice.probabilities["east"] == 0.7
    assert (choice.input_tokens, choice.model) == (42, "org/model")
