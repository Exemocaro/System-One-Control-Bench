import pytest

from system_one_control.prompts import COMPONENTS, CONDITIONS, QUESTION
from system_one_control.puzzles import load_puzzles
from system_one_control.world import Board, CompassRules, TwoMoveRules, UpToThreeMoveRules

PUZZLES = load_puzzles()
LEVEL_TEN = PUZZLES["gen-10-01"].board
COMPASS = CompassRules()
TWO = TwoMoveRules()
ROOM = Board.parse("#####\n#A.G#\n#####")
MAP = CONDITIONS["map"]
KEY = "Your next target is the key K at (7, 2)."
GOAL = "Your next target is the goal G at (3, 1)."


@pytest.mark.parametrize("condition", CONDITIONS)
@pytest.mark.parametrize("puzzle", PUZZLES)
def test_every_condition_renders_every_puzzle(condition, puzzle):
    request = CONDITIONS[condition].render(PUZZLES[puzzle].board, COMPASS, shuffle_seed="x")
    assert ("A" in request.state, bool(request.question), len(request.options)) == (True, True, 4)


@pytest.mark.parametrize(
    ("board", "fragment"),
    [
        pytest.param(ROOM, COMPASS.description, id="the rules"),
        pytest.param(ROOM, "   01234\n 0 #####\n 1 #A.G#\n 2 #####", id="the numbered map"),
        pytest.param(ROOM, "You are A at (1, 1). You are carrying nothing.", id="the position"),
        pytest.param(ROOM.pick_up("key"), "You are carrying: key.", id="what you carry"),
    ],
)
def test_the_map_state_says(board, fragment):
    assert fragment in MAP.render(board, COMPASS).state


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("map", [], id="the map alone"),
        pytest.param("map+memory", ["memory"], id="one component added"),
        pytest.param("everything-lookahead", ["surroundings", "memory", "subgoal"], id="one taken"),
    ],
)
def test_each_name_says_which_components_are_switched_on(name, expected):
    assert CONDITIONS[name].components == expected


@pytest.mark.parametrize("name", COMPONENTS)
def test_adding_a_component_keeps_everything_the_map_already_said(name):
    plain = MAP.render(LEVEL_TEN, COMPASS)
    added = CONDITIONS[f"map+{name}"].render(LEVEL_TEN, COMPASS)
    assert added.state.startswith(plain.state) and added != plain


@pytest.mark.parametrize(
    "fragment",
    ["North of you is a wall.", "The key is 1 east and 1 south of you."],
    ids=["what is next to you", "where the key is"],
)
def test_surroundings_add_what_is_around_you(fragment):
    assert fragment in CONDITIONS["map+surroundings"].render(LEVEL_TEN, COMPASS).state


@pytest.mark.parametrize(
    ("memory", "ending"),
    [
        pytest.param([], "No moves yet.", id="no moves"),
        pytest.param(
            ["east: you move to (2, 1)"],
            "Moves so far:\n1. east: you move to (2, 1)",
            id="one move",
        ),
    ],
)
def test_memory_lists_the_moves_so_far(memory, ending):
    assert CONDITIONS["map+memory"].render(ROOM, COMPASS, memory=memory).state.endswith(ending)


def test_lookahead_writes_what_each_move_would_do_into_its_option():
    options = CONDITIONS["map+lookahead"].render(ROOM, COMPASS).options
    texts = {o.move: o.text for o in options}
    assert texts["east"] == "move east (right): you move to (2, 1)"
    assert texts["north"] == "move north (up): blocked, you stay at (1, 1)"


@pytest.mark.parametrize(
    ("rules", "board", "expected"),
    [
        pytest.param(COMPASS, LEVEL_TEN, KEY, id="compass names the key"),
        pytest.param(
            TWO, ROOM, GOAL + " Which move starts the shortest path to it?", id="sequences"
        ),
        pytest.param(
            TWO,
            LEVEL_TEN,
            KEY + " Which move starts the shortest path to the goal through it?",
            id="sequences, the key then the goal",
        ),
        pytest.param(
            UpToThreeMoveRules(),
            ROOM,
            GOAL + " Which move starts the way to it that takes the fewest turns?",
            id="up-to asks for the fewest turns",
        ),
    ],
)
def test_the_subgoal_names_the_next_target_and_asks_for_the_move_that_starts_the_path(
    rules, board, expected
):
    assert expected in CONDITIONS["map+subgoal"].render(board, rules).question


@pytest.mark.parametrize("rules", [COMPASS, TWO], ids=["compass", "two-moves"])
def test_without_the_subgoal_every_rules_ask_the_plain_question(rules):
    assert MAP.render(LEVEL_TEN, rules).question == QUESTION


def test_without_a_seed_the_options_follow_the_rules_order():
    options = MAP.render(ROOM, COMPASS).options
    assert [o.move for o in options] == ["north", "south", "east", "west"]
    assert [o.id for o in options] == ["option_1", "option_2", "option_3", "option_4"]


def test_the_same_seed_gives_the_same_order_in_every_condition():
    orders = {
        tuple(o.move for o in c.render(LEVEL_TEN, COMPASS, shuffle_seed="gen-10-01:1").options)
        for c in CONDITIONS.values()
    }
    assert len(orders) == 1


def test_different_seeds_give_different_orders():
    renders = [MAP.render(ROOM, COMPASS, shuffle_seed=f"s:{n}") for n in range(20)]
    assert len({tuple(o.move for o in r.options) for r in renders}) > 5
