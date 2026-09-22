import pytest

from system_one_control.board import Board
from system_one_control.prompt import Prompt, describe_outcome, load_prompts
from system_one_control.rules import CompassRules
from system_one_control.scenario import load_scenarios

PROMPTS = load_prompts()
SCENARIOS = load_scenarios()
rules = CompassRules()
ROOM = Board.parse("#####\n#A.G#\n#####")


def render(state: str, board: Board = ROOM, **kwargs):
    return Prompt(name="t", description="", state=state, question="?").render(
        board, rules, **kwargs
    )


@pytest.mark.parametrize("prompt", PROMPTS)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_prompt_renders_every_scenario(prompt, scenario):
    request = PROMPTS[prompt].render(SCENARIOS[scenario].board, rules, shuffle_seed="x")
    assert "A" in request.state
    assert "{" not in request.state
    assert request.question


def test_without_a_seed_the_options_follow_the_rules_order():
    request = PROMPTS["full"].render(ROOM, rules)
    assert [o.move for o in request.options] == ["north", "south", "east", "west"]
    assert [o.id for o in request.options] == ["option_1", "option_2", "option_3", "option_4"]


def test_the_same_seed_always_gives_the_same_order():
    first = PROMPTS["full"].render(ROOM, rules, shuffle_seed="maze:3")
    again = PROMPTS["full"].render(ROOM, rules, shuffle_seed="maze:3")
    assert first.options == again.options


def test_different_seeds_give_different_orders_but_ids_stay_in_position():
    orders = {
        tuple(o.move for o in PROMPTS["full"].render(ROOM, rules, shuffle_seed=f"s:{n}").options)
        for n in range(20)
    }
    assert len(orders) > 5
    shuffled = PROMPTS["full"].render(ROOM, rules, shuffle_seed="s:1")
    assert [o.id for o in shuffled.options] == ["option_1", "option_2", "option_3", "option_4"]
    assert sorted(o.move for o in shuffled.options) == ["east", "north", "south", "west"]


def test_a_prompt_can_rename_the_options():
    prompt = Prompt(
        name="t", description="", state="{map}", question="?", option_text={"east": "right"}
    )
    request = prompt.render(ROOM, rules)
    assert [o.text for o in request.options][2] == "right"


def test_a_prompt_can_describe_what_each_option_would_do():
    prompt = Prompt(name="t", description="", state="{map}", question="?", show_outcomes=True)
    texts = {o.move: o.text for o in prompt.render(ROOM, rules).options}
    assert texts["east"] == "move east (right): you move to (2, 1)"
    assert texts["north"] == "move north (up): blocked, you stay at (1, 1)"


def test_the_state_says_what_you_carry():
    assert render("{holding}").state == "You are carrying nothing."
    assert render("{holding}", ROOM.carrying("key")).state == "You are carrying: key."


def test_the_map_can_be_drawn_with_row_and_column_numbers():
    assert render("{map_grid}").state == "   01234\n 0 #####\n 1 #A.G#\n 2 #####"


def test_history_is_empty_until_moves_are_played():
    assert render("{history}").state == "No moves yet."
    lines = ("east: you move to (2, 1)", "east: blocked, you stay at (2, 1)")
    state = render("{history}", history=lines).state
    assert (
        state == "Moves so far:\n1. east: you move to (2, 1)\n2. east: blocked, you stay at (2, 1)"
    )


def test_the_full_prompt_shows_the_map_and_the_rules():
    state = PROMPTS["full"].render(ROOM, rules).state
    assert "#A.G#" in state
    assert rules.description in state


def test_an_unknown_placeholder_names_what_is_available():
    with pytest.raises(ValueError, match="facing"):
        render("{facing}")


@pytest.mark.parametrize(
    ("before", "move", "expected"),
    [
        ("#####\n#A.G#\n#####", "east", "you move to (2, 1)"),
        ("#####\n#A.G#\n#####", "west", "blocked, you stay at (1, 1)"),
        ("####\n#AK#\n####", "east", "you move to (2, 1) and pick up the key"),
        ("####\n#AG#\n####", "east", "you move to (2, 1) and reach the goal"),
    ],
)
def test_outcomes_are_described_in_plain_words(before, move, expected):
    board = Board.parse(before)
    after = rules.apply(board, rules.find_move(board, move))
    assert describe_outcome(board, after, rules) == expected


def test_unlocking_the_door_is_described():
    board = Board.parse("####\n#AD#\n####").carrying("key")
    after = rules.apply(board, rules.find_move(board, "east"))
    assert describe_outcome(board, after, rules) == "you move to (2, 1) and unlock the door"
