import pytest

from system_one_control.board import Board
from system_one_control.conditions import CONDITIONS, INGREDIENTS, Condition
from system_one_control.rules import CompassRules
from system_one_control.scenario import load_scenarios

SCENARIOS = load_scenarios()
LEVEL_TEN = SCENARIOS["gen-10-01"].board
rules = CompassRules()
ROOM = Board.parse("#####\n#A.G#\n#####")
MAP = CONDITIONS["map"]


@pytest.mark.parametrize("condition", CONDITIONS)
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_condition_renders_every_scenario(condition, scenario):
    request = CONDITIONS[condition].render(SCENARIOS[scenario].board, rules, shuffle_seed="x")
    assert "A" in request.state
    assert request.question
    assert len(request.options) == 4


def test_the_map_shows_the_rules_the_numbered_map_and_asks_the_neutral_question():
    request = MAP.render(ROOM, rules)
    assert rules.description in request.state
    assert "   01234\n 0 #####\n 1 #A.G#\n 2 #####" in request.state
    assert "You are A at (1, 1). You are carrying nothing." in request.state
    assert request.question == "What is the best next move?"


def test_the_state_says_what_you_carry():
    assert "You are carrying: key." in MAP.render(ROOM.pick_up("key"), rules).state


@pytest.mark.parametrize("name", CONDITIONS)
def test_each_name_says_which_ingredients_are_switched_on(name):
    if name == "map":
        expected = []
    elif name.startswith("map+"):
        expected = [name.removeprefix("map+")]
    else:
        taken = name.removeprefix("everything").removeprefix("-")
        expected = [ingredient for ingredient in INGREDIENTS if ingredient != taken]
    assert CONDITIONS[name].ingredients == expected


def test_the_ablation_adds_each_ingredient_to_the_map_and_takes_each_from_everything():
    assert list(CONDITIONS) == [
        "map",
        *(f"map+{name}" for name in INGREDIENTS),
        "everything",
        *(f"everything-{name}" for name in INGREDIENTS),
    ]


@pytest.mark.parametrize("name", INGREDIENTS)
def test_adding_an_ingredient_keeps_everything_the_map_already_said(name):
    plain = MAP.render(LEVEL_TEN, rules)
    added = CONDITIONS[f"map+{name}"].render(LEVEL_TEN, rules)
    assert added.state.startswith(plain.state)
    assert added != plain


def test_every_condition_shows_the_options_in_the_same_order_for_the_same_seed():
    orders = {
        tuple(o.move for o in c.render(LEVEL_TEN, rules, shuffle_seed="gen-10-01:1").options)
        for c in CONDITIONS.values()
    }
    assert len(orders) == 1


def test_surroundings_say_what_is_next_to_you():
    state = CONDITIONS["map+surroundings"].render(LEVEL_TEN, rules).state
    assert "North of you is a wall." in state
    assert "The key is 1 east and 1 south of you." in state


def test_memory_lists_the_moves_so_far():
    memory = CONDITIONS["map+memory"]
    assert memory.render(ROOM, rules).state.endswith("No moves yet.")
    state = memory.render(ROOM, rules, history=["east: you move to (2, 1)"]).state
    assert state.endswith("Moves so far:\n1. east: you move to (2, 1)")


def test_lookahead_writes_what_each_move_would_do_into_its_option():
    texts = {o.move: o.text for o in CONDITIONS["map+lookahead"].render(ROOM, rules).options}
    assert texts["east"] == "move east (right): you move to (2, 1)"
    assert texts["north"] == "move north (up): blocked, you stay at (1, 1)"


def test_the_subgoal_names_the_next_thing_to_reach():
    question = CONDITIONS["map+subgoal"].render(LEVEL_TEN, rules).question
    assert question.startswith("Your next target is the key K at (7, 2).")


def test_without_a_seed_the_options_follow_the_rules_order():
    request = MAP.render(ROOM, rules)
    assert [o.move for o in request.options] == ["north", "south", "east", "west"]
    assert [o.id for o in request.options] == ["option_1", "option_2", "option_3", "option_4"]


def test_the_same_seed_always_gives_the_same_order():
    first = MAP.render(ROOM, rules, shuffle_seed="m:3")
    assert MAP.render(ROOM, rules, shuffle_seed="m:3") == first


def test_different_seeds_give_different_orders_but_ids_stay_in_position():
    orders = {
        tuple(o.move for o in MAP.render(ROOM, rules, shuffle_seed=f"s:{n}").options)
        for n in range(20)
    }
    assert len(orders) > 5
    shuffled = MAP.render(ROOM, rules, shuffle_seed="s:1")
    assert [o.id for o in shuffled.options] == ["option_1", "option_2", "option_3", "option_4"]


def test_a_condition_describes_itself_from_its_ingredients():
    assert MAP.description == "The map alone."
    assert Condition("m", memory=True).description == f"The map, plus {INGREDIENTS['memory']}."
