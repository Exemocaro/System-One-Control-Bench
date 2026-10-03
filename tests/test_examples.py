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
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import load_puzzles
from system_one_control.world import RULES, CompassRules, ThreeMoveRules, TwoMoveRules

PUZZLE = load_puzzles()[EXAMPLE_PUZZLE]


@pytest.mark.parametrize(
    "rules",
    [None, *(kind() for name, kind in RULES.items() if name != "compass")],
    ids=lambda r: r.name if r else "compass",
)
@pytest.mark.parametrize("name", CONDITIONS)
def test_the_saved_example_is_what_the_condition_sends_today(name, rules):
    """If this fails, the wording changed: check the change, then run `socb examples` (with
    `--rules` for the rules that failed)."""
    folder, puzzle = EXAMPLE_DIR, PUZZLE
    if rules is not None:
        folder, puzzle = EXAMPLE_DIR / rules.name, replace(PUZZLE, rules=rules)
    assert (folder / f"{name}.json").read_text(encoding="utf-8") == example(
        CONDITIONS[name], puzzle
    )


def test_an_example_is_the_jev_request_after_a_move_and_a_blocked_move():
    body = json.loads(example(CONDITIONS["everything"], PUZZLE))
    question = body["questions"]["move"]
    assert set(body) == {"state", "model", "questions"}
    assert "1. east: you move to (7, 1)\n2. north: blocked, you stay at (7, 1)" in body["state"]
    assert (question["type"], sorted(question["criteria"])) == (
        "choice",
        ["option_1", "option_2", "option_3", "option_4"],
    )


@pytest.mark.parametrize(
    ("rules", "folder", "options", "fragment"),
    [
        (None, "", 4, "No moves yet"),
        (TwoMoveRules(), "two-moves", 16, "you end"),
        (ThreeMoveRules(), "three-moves", 64, "you end"),
    ],
    ids=["compass, in the folder itself", "two-moves, in its own folder", "three-moves, likewise"],
)
def test_one_example_is_written_per_condition(tmp_path, rules, folder, options, fragment):
    written = write_examples(tmp_path, rules=rules)
    body = json.loads((tmp_path / folder / "map+memory.json").read_text(encoding="utf-8"))
    assert sorted(path.stem for path in written) == sorted(CONDITIONS)
    assert {path.parent for path in written} == {tmp_path / folder}
    assert len(body["questions"]["move"]["criteria"]) == options
    assert fragment in body["state"] or rules is None


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
