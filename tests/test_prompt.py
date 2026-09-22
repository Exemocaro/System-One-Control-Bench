import pytest

from system_one_control.board import Board
from system_one_control.prompt import Prompt, load_prompts
from system_one_control.rules import CompassRules
from system_one_control.scenario import load_scenarios

PROMPTS = load_prompts()
SCENARIOS = load_scenarios()
rules = CompassRules()


@pytest.mark.parametrize("prompt", PROMPTS)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_prompt_renders_every_scenario(prompt, scenario):
    request = PROMPTS[prompt].render(SCENARIOS[scenario].board, rules)
    assert "A" in request.state
    assert "{" not in request.state
    assert request.question


def test_there_is_one_option_per_allowed_move():
    request = PROMPTS["full"].render(Board.parse("####\n#AG#\n####"), rules)
    assert [o.move for o in request.options] == ["north", "south", "east", "west"]
    assert len({o.id for o in request.options}) == 4


def test_a_prompt_can_rename_the_options():
    request = PROMPTS["up-down"].render(Board.parse("####\n#AG#\n####"), rules)
    assert [o.text for o in request.options] == ["up", "down", "right", "left"]


def test_the_state_says_what_you_carry():
    prompt = Prompt(name="t", description="", state="{holding}", question="?")
    board = Board.parse("####\n#AG#\n####")
    assert prompt.render(board, rules).state == "You are carrying nothing."
    carrying = prompt.render(board.carrying("key"), rules).state
    assert carrying == "You are carrying: key."


def test_the_full_prompt_shows_the_map_and_the_rules():
    state = PROMPTS["full"].render(Board.parse("####\n#AG#\n####"), rules).state
    assert "#AG#" in state
    assert rules.description in state


def test_an_unknown_placeholder_names_what_is_available():
    prompt = Prompt(name="bad", description="", state="{facing}", question="?")
    with pytest.raises(ValueError, match="facing"):
        prompt.render(Board.parse("####\n#AG#\n####"), rules)
