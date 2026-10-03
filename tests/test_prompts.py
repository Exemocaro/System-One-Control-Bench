import pytest

from system_one_control.prompts import COMPONENTS, CONDITIONS, QUESTION, Condition
from system_one_control.puzzles import load_puzzles
from system_one_control.world import (
    Board,
    CompassRules,
    TwoMoveRules,
    UpToThreeMoveRules,
    UpToTwoMoveRules,
)

PUZZLES = load_puzzles()
LEVEL_TEN = PUZZLES["gen-10-01"].board
COMPASS = CompassRules()
TWO = TwoMoveRules()
ROOM = Board.parse("#####\n#A.G#\n#####")
MAP = CONDITIONS["map"]
FOUR_OPTIONS = ["option_1", "option_2", "option_3", "option_4"]


@pytest.mark.parametrize("condition", CONDITIONS)
@pytest.mark.parametrize("puzzle", PUZZLES)
def test_every_condition_renders_every_puzzle(condition, puzzle):
    request = CONDITIONS[condition].render(PUZZLES[puzzle].board, COMPASS, shuffle_seed="x")
    assert ("A" in request.state, bool(request.question), len(request.options)) == (True, True, 4)


@pytest.mark.parametrize(
    ("board", "fragment"),
    [
        (ROOM, COMPASS.description),
        (ROOM, "   01234\n 0 #####\n 1 #A.G#\n 2 #####"),
        (ROOM, "You are A at (1, 1). You are carrying nothing."),
        (ROOM.pick_up("key"), "You are carrying: key."),
    ],
    ids=["the rules", "the numbered map", "the position", "what you carry"],
)
def test_the_map_state_says(board, fragment):
    assert fragment in MAP.render(board, COMPASS).state


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("map", []),
        ("map+surroundings", ["surroundings"]),
        ("map+memory", ["memory"]),
        ("map+lookahead", ["lookahead"]),
        ("map+subgoal", ["subgoal"]),
        ("everything", ["surroundings", "memory", "lookahead", "subgoal"]),
        ("everything-surroundings", ["memory", "lookahead", "subgoal"]),
        ("everything-memory", ["surroundings", "lookahead", "subgoal"]),
        ("everything-lookahead", ["surroundings", "memory", "subgoal"]),
        ("everything-subgoal", ["surroundings", "memory", "lookahead"]),
    ],
)
def test_each_name_says_which_components_are_switched_on(name, expected):
    assert CONDITIONS[name].components == expected


def test_the_ablation_adds_each_component_to_the_map_and_takes_each_from_everything():
    assert list(CONDITIONS) == [
        "map",
        *(f"map+{name}" for name in COMPONENTS),
        "everything",
        *(f"everything-{name}" for name in COMPONENTS),
    ]


@pytest.mark.parametrize("name", COMPONENTS)
def test_adding_a_component_keeps_everything_the_map_already_said(name):
    plain = MAP.render(LEVEL_TEN, COMPASS)
    added = CONDITIONS[f"map+{name}"].render(LEVEL_TEN, COMPASS)
    assert added.state.startswith(plain.state) and added != plain


@pytest.mark.parametrize(
    ("condition", "fragment"),
    [
        ("map+surroundings", "North of you is a wall."),
        ("map+surroundings", "The key is 1 east and 1 south of you."),
    ],
    ids=["what is next to you", "where the key is"],
)
def test_a_component_adds_its_text_to_the_state(condition, fragment):
    assert fragment in CONDITIONS[condition].render(LEVEL_TEN, COMPASS).state


@pytest.mark.parametrize(
    ("memory", "ending"),
    [
        ([], "No moves yet."),
        (["east: you move to (2, 1)"], "Moves so far:\n1. east: you move to (2, 1)"),
    ],
    ids=["no moves", "one move"],
)
def test_memory_lists_the_moves_so_far(memory, ending):
    assert CONDITIONS["map+memory"].render(ROOM, COMPASS, memory=memory).state.endswith(ending)


@pytest.mark.parametrize(
    ("move", "expected"),
    [
        ("east", "move east (right): you move to (2, 1)"),
        ("north", "move north (up): blocked, you stay at (1, 1)"),
    ],
    ids=["a move that goes", "a move into a wall"],
)
def test_lookahead_writes_what_each_move_would_do_into_its_option(move, expected):
    options = CONDITIONS["map+lookahead"].render(ROOM, COMPASS).options
    assert {o.move: o.text for o in options}[move] == expected


@pytest.mark.parametrize(
    ("rules", "board", "expected"),
    [
        (COMPASS, ROOM, "first step"),
        (COMPASS, LEVEL_TEN, "Your next target is the key K at (7, 2)."),
        (
            TWO,
            ROOM,
            "Your next target is the goal G at (3, 1). Which move starts the shortest path to it?",
        ),
        (
            TWO,
            LEVEL_TEN,
            "Your next target is the key K at (7, 2). "
            "Which move starts the shortest path to the goal through it?",
        ),
        (
            UpToThreeMoveRules(),
            ROOM,
            "Your next target is the goal G at (3, 1). "
            "Which move starts the way to it that takes the fewest turns?",
        ),
        (
            UpToTwoMoveRules(),
            LEVEL_TEN,
            "Your next target is the key K at (7, 2). "
            "Which move starts the way to the goal through it that takes the fewest turns?",
        ),
    ],
    ids=[
        "compass asks for the first step",
        "compass names the key",
        "sequences, the goal",
        "sequences, the key then the goal",
        "up-to, the goal",
        "up-to, the key then the goal",
    ],
)
def test_the_subgoal_names_the_next_target_and_asks_for_the_move_that_starts_the_path(
    rules, board, expected
):
    assert expected in CONDITIONS["map+subgoal"].render(board, rules).question


@pytest.mark.parametrize(
    "rules", [COMPASS, TWO, UpToThreeMoveRules()], ids=["compass", "two-moves", "up-to-three"]
)
def test_without_the_subgoal_every_rules_ask_the_plain_question(rules):
    assert MAP.render(LEVEL_TEN, rules).question == QUESTION


def test_without_a_seed_the_options_follow_the_rules_order():
    options = MAP.render(ROOM, COMPASS).options
    assert [o.move for o in options] == ["north", "south", "east", "west"]
    assert [o.id for o in options] == FOUR_OPTIONS


def test_every_condition_shows_the_options_in_the_same_order_for_the_same_seed():
    orders = {
        tuple(o.move for o in c.render(LEVEL_TEN, COMPASS, shuffle_seed="gen-10-01:1").options)
        for c in CONDITIONS.values()
    }
    assert len(orders) == 1


def test_the_same_seed_always_gives_the_same_order():
    first = MAP.render(ROOM, COMPASS, shuffle_seed="m:3")
    assert MAP.render(ROOM, COMPASS, shuffle_seed="m:3") == first


def test_different_seeds_give_different_orders_but_ids_stay_in_position():
    renders = [MAP.render(ROOM, COMPASS, shuffle_seed=f"s:{n}") for n in range(20)]
    assert len({tuple(o.move for o in r.options) for r in renders}) > 5
    assert all([o.id for o in r.options] == FOUR_OPTIONS for r in renders)


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (MAP, "The map alone."),
        (Condition("m", memory=True), f"The map, plus {COMPONENTS['memory']}."),
    ],
    ids=["the map alone", "a component added"],
)
def test_a_condition_describes_itself_from_its_components(condition, expected):
    assert condition.description == expected
