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
from system_one_control.world import RULES, CompassRules, TwoMoveRules

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
    saved = (folder / f"{name}.json").read_text(encoding="utf-8")
    assert saved == example(CONDITIONS[name], puzzle)


@pytest.mark.parametrize(
    ("rules", "folder", "options"),
    [
        pytest.param(None, "", 4, id="compass"),
        pytest.param(TwoMoveRules(), "two-moves", 16, id="two-moves"),
    ],
)
def test_one_example_is_written_per_condition_in_a_folder_for_its_rules(
    tmp_path, rules, folder, options
):
    written = write_examples(tmp_path, rules=rules)
    body = json.loads((tmp_path / folder / "map+memory.json").read_text(encoding="utf-8"))
    assert sorted(path.stem for path in written) == sorted(CONDITIONS)
    assert {path.parent for path in written} == {tmp_path / folder}
    assert len(body["questions"]["move"]["criteria"]) == options


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
