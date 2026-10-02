import json
from dataclasses import replace

import pytest

from system_one_control.conditions import CONDITIONS
from system_one_control.examples import (
    EXAMPLE_DIR,
    EXAMPLE_SCENARIO,
    example,
    example_moves,
    write_examples,
)
from system_one_control.scenario import load_scenarios
from system_one_control.world import RULES, CompassRules, ThreeMoveRules, TwoMoveRules

SCENARIO = load_scenarios()[EXAMPLE_SCENARIO]


@pytest.mark.parametrize(
    "rules",
    [None, *(rules() for name, rules in RULES.items() if name != "compass")],
    ids=lambda r: r.name if r else "compass",
)
@pytest.mark.parametrize("name", CONDITIONS)
def test_the_saved_example_is_what_the_condition_sends_today(name, rules):
    """If this fails, the wording changed: check the change, then run `socb examples` (with
    `--rules` for the rules that failed)."""
    folder, scenario = EXAMPLE_DIR, SCENARIO
    if rules is not None:
        folder, scenario = EXAMPLE_DIR / rules.name, replace(SCENARIO, rules=rules)
    saved = (folder / f"{name}.json").read_text(encoding="utf-8")
    assert saved == example(CONDITIONS[name], scenario)


def test_an_example_is_the_jev_request_after_a_move_and_a_blocked_move():
    body = json.loads(example(CONDITIONS["everything"], SCENARIO))
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

    scenario = replace(SCENARIO, rules=SouthFirst())
    first, second = example_moves(scenario)
    rules, board = scenario.rules, scenario.board
    moved = rules.apply(board, rules.find_move(board, first))
    assert moved != board
    assert rules.apply(moved, rules.find_move(moved, second)) == moved
