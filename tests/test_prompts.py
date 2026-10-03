import json
from dataclasses import replace

import pytest

from system_one_control.examples import (
    EXAMPLE_DIR,
    EXAMPLE_PUZZLE,
    example,
    example_moves,
    write_examples,
)
from system_one_control.prompts import COMPONENTS, CONDITIONS, Condition
from system_one_control.puzzles import load_puzzles
from system_one_control.world import (
    RULES,
    Board,
    CompassRules,
    ThreeMoveRules,
    TwoMoveRules,
    UpToThreeMoveRules,
    UpToTwoMoveRules,
)

PUZZLES = load_puzzles()
PUZZLE = PUZZLES[EXAMPLE_PUZZLE]
LEVEL_TEN = PUZZLES["gen-10-01"].board
rules = CompassRules()
ROOM = Board.parse("#####\n#A.G#\n#####")
MAP = CONDITIONS["map"]


@pytest.mark.parametrize("condition", CONDITIONS)
@pytest.mark.parametrize("puzzle", PUZZLES)
def test_every_condition_renders_every_puzzle(condition, puzzle):
    request = CONDITIONS[condition].render(PUZZLES[puzzle].board, rules, shuffle_seed="x")
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
def test_each_name_says_which_components_are_switched_on(name):
    if name == "map":
        expected = []
    elif name.startswith("map+"):
        expected = [name.removeprefix("map+")]
    else:
        taken = name.removeprefix("everything").removeprefix("-")
        expected = [component for component in COMPONENTS if component != taken]
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
    state = memory.render(ROOM, rules, memory=["east: you move to (2, 1)"]).state
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


def test_a_condition_describes_itself_from_its_components():
    assert MAP.description == "The map alone."
    assert Condition("m", memory=True).description == f"The map, plus {COMPONENTS['memory']}."


def test_under_sequence_rules_the_subgoal_asks_for_the_move_that_starts_the_path():
    subgoal = CONDITIONS["map+subgoal"]
    assert "first step" in subgoal.render(ROOM, rules).question
    assert subgoal.render(ROOM, TwoMoveRules()).question == (
        "Your next target is the goal G at (3, 1). Which move starts the shortest path to it?"
    )


def test_under_sequence_rules_a_subgoal_before_the_goal_asks_for_the_path_to_the_goal():
    # A move that reaches the key with steps to spare should spend them on the way onward.
    question = CONDITIONS["map+subgoal"].render(LEVEL_TEN, TwoMoveRules()).question
    assert question == (
        "Your next target is the key K at (7, 2). "
        "Which move starts the shortest path to the goal through it?"
    )


def test_where_a_move_may_be_shorter_the_subgoal_asks_for_the_way_with_fewest_turns():
    # "Starts the shortest path" would be true of a single step, which wastes a turn.
    subgoal = CONDITIONS["map+subgoal"]
    assert subgoal.render(ROOM, UpToThreeMoveRules()).question == (
        "Your next target is the goal G at (3, 1). "
        "Which move starts the way to it that takes the fewest turns?"
    )
    assert subgoal.render(LEVEL_TEN, UpToTwoMoveRules()).question == (
        "Your next target is the key K at (7, 2). "
        "Which move starts the way to the goal through it that takes the fewest turns?"
    )


def test_without_the_subgoal_every_rules_ask_the_plain_question():
    for rules_type in (CompassRules, TwoMoveRules, UpToThreeMoveRules):
        assert MAP.render(LEVEL_TEN, rules_type()).question == "What is the best next move?"


@pytest.mark.parametrize(
    "rules",
    [None, *(rules() for name, rules in RULES.items() if name != "compass")],
    ids=lambda r: r.name if r else "compass",
)
@pytest.mark.parametrize("name", CONDITIONS)
def test_the_saved_example_is_what_the_condition_sends_today(name, rules):
    """If this fails, the wording changed: check the change, then run `socb examples` (with
    `--rules` for the rules that failed)."""
    folder, puzzle = EXAMPLE_DIR, PUZZLE
    if rules is not None:
        folder, puzzle = EXAMPLE_DIR / rules.name, replace(PUZZLE, rules=rules)
    saved = (folder / f"{name}.json").read_text(encoding="utf-8")
    assert saved == example(CONDITIONS[name], puzzle)


def test_an_example_is_the_jev_request_after_a_move_and_a_blocked_move():
    body = json.loads(example(CONDITIONS["everything"], PUZZLE))
    assert set(body) == {"state", "model", "questions"}
    assert "1. east: you move to (7, 1)\n2. north: blocked, you stay at (7, 1)" in body["state"]
    question = body["questions"]["move"]
    assert question["type"] == "choice"
    assert sorted(question["criteria"]) == ["option_1", "option_2", "option_3", "option_4"]


def test_examples_are_written_one_file_per_condition(tmp_path):
    written = write_examples(tmp_path)
    assert sorted(path.stem for path in written) == sorted(CONDITIONS)


@pytest.mark.parametrize(("rules", "options"), [(TwoMoveRules(), 16), (ThreeMoveRules(), 64)])
def test_examples_under_sequence_rules_go_in_their_own_folder(tmp_path, rules, options):
    written = write_examples(tmp_path, rules=rules)
    assert {path.parent.name for path in written} == {rules.name}
    body = json.loads((tmp_path / rules.name / "map+memory.json").read_text(encoding="utf-8"))
    assert len(body["questions"]["move"]["criteria"]) == options
    assert "you end" in body["state"]


def test_rules_without_example_moves_get_a_move_then_a_blocked_one():
    class SouthFirst(CompassRules):
        name = "south-first"
        MOVES = (CompassRules.MOVES[1], *CompassRules.MOVES[:1], *CompassRules.MOVES[2:])

    puzzle = replace(PUZZLE, rules=SouthFirst())
    first, second = example_moves(puzzle)
    rules, board = puzzle.rules, puzzle.board
    moved = rules.apply(board, rules.find_move(board, first))
    assert moved != board
    assert rules.apply(moved, rules.find_move(moved, second)) == moved
