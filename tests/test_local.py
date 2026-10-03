import pytest

from system_one_control.players.local import (
    GLiClassPlayer,
    LayaPlayer,
    LocalLLMPlayer,
    laya_budget,
    laya_inputs,
    number_probabilities,
)
from system_one_control.prompts import CONDITIONS
from system_one_control.world import Board, CompassRules
from tests.helpers import turn

TINY = "####\n#AG#\n####"
REQUEST = CONDITIONS["everything"].render(Board.parse(TINY), CompassRules())


def words(text: str) -> int:
    return len(text.split())


def tokenizer(text: str, add_special_tokens: bool = False) -> dict:
    """A token per word."""
    return {"input_ids": list(range(words(text)))}


def test_laya_is_asked_the_question_with_the_option_texts():
    state, questions, max_len, head = laya_inputs(REQUEST, tokenizer)
    assert state == REQUEST.state
    assert questions["move"]["criteria"] == [o.text for o in REQUEST.options]
    assert max_len > head


def test_laya_gets_room_for_the_whole_request():
    max_len, head = laya_budget(words, REQUEST)
    options = sum(words(" " + o.text) + 1 for o in REQUEST.options)
    assert head >= words(f"choice question: {REQUEST.question}") + options + 16
    assert max_len >= head + words(REQUEST.state)


def test_an_option_longer_than_laya_reads_is_refused_rather_cut():
    with pytest.raises(ValueError, match="longer"):
        laya_budget(lambda text: 1000 if "east" in text else 5, REQUEST)


class FakeLaya:
    tok = staticmethod(tokenizer)

    def system_one(self, state, questions, max_len, head_max_len):
        texts = questions["move"]["criteria"]
        probabilities = dict.fromkeys(texts, 0.1) | {texts[2]: 0.7}
        answer = {"choice": texts[2], "probabilities": probabilities, "confidence": 0.6}
        return {"answers": {"move": answer}, "usage": {"input_tokens": 321, "output_tokens": 0}}


def test_laya_answers_with_one_of_the_option_texts_and_it_maps_back_to_a_move():
    t = turn(TINY)
    choice = LayaPlayer(laya=FakeLaya()).choose(t)
    assert choice.move == t.request.options[2].move
    assert (choice.probabilities[choice.move], choice.input_tokens) == (0.7, 321)
    assert sum(choice.probabilities.values()) == pytest.approx(1.0)


def test_gliclass_plays_the_option_with_the_best_score():
    def pipeline(text, labels, threshold, prompt):
        return [
            [{"label": label, "score": 0.9 if i == 1 else 0.1} for i, label in enumerate(labels)]
        ]

    t = turn(TINY)
    choice = GLiClassPlayer(pipeline=pipeline).choose(t)
    assert choice.move == t.request.options[1].move
    assert choice.probabilities[choice.move] == pytest.approx(0.9 / 1.2)


def spread(*chances: float) -> list[float]:
    """The chance of each digit 0-9 coming next, the rest of the ten being zero."""
    return [*chances, *[0.0] * (10 - len(chances))]


@pytest.mark.parametrize(
    ("offered", "table", "expected", "asked"),
    [
        pytest.param(
            {"1", "2", "3"},
            {"": spread(0.0, 0.5, 0.2, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2)},  # 0.2 on 9: not offered
            {"1": 0.5 / 0.8, "2": 0.2 / 0.8, "3": 0.1 / 0.8},
            [""],
            id="single digits share the first digit",
        ),
        pytest.param(
            {"1", "2", "10", "11"},
            {"": spread(0.0, 0.8, 0.2), "1": spread(0.5, 0.0, 0.3)},  # 12 is not offered
            {"1": 0.8 * 0.2 / 0.7, "10": 0.8 * 0.5 / 0.7, "11": 0.0, "2": 0.2},
            ["", "1"],
            id="a number others extend shares the chance to end",
        ),
    ],
)
def test_number_probabilities(offered, table, expected, asked):
    seen = []

    def next_digits(written):
        seen.append(written)
        return table[written]

    assert number_probabilities(offered, next_digits) == pytest.approx(expected)
    assert sorted(seen) == asked  # a pass for each prefix that others extend, and no more


class FakeLocalLLM:
    def prompt(self, request):
        return [7] * 42

    def option_probabilities(self, request, prompt):
        return {"option_3": 0.7, "option_1": 0.1, "option_2": 0.1, "option_4": 0.1}


def test_a_local_chat_model_plays_the_option_it_gives_the_most_probability():
    t = turn(TINY)
    choice = LocalLLMPlayer("org/model", model=FakeLocalLLM()).choose(t)
    assert choice.move == t.request.options[2].move
    assert (choice.input_tokens, choice.model) == (42, "org/model")
