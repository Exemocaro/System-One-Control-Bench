from dataclasses import replace

import pytest

from system_one_control.generator import PuzzleGenerator, write_level
from system_one_control.rules import CompassRules
from system_one_control.scenario import Scenario, load_scenarios
from system_one_control.solver import Solver

solver = Solver(CompassRules())


@pytest.mark.parametrize("level", range(1, 11))
def test_a_generated_puzzle_is_exactly_its_level_away_from_the_goal(level):
    board = PuzzleGenerator(seed=level).puzzle(level).board
    assert solver.distance(board) == level


@pytest.mark.parametrize("level", range(3, 11))
def test_from_level_three_every_puzzle_needs_the_key(level):
    board = PuzzleGenerator(seed=level).puzzle(level).board
    keyless = replace(board, rows=tuple(r.replace("K", ".") for r in board.rows))
    assert board.find("K") and board.find("D")
    assert solver.distance(keyless) is None


def test_the_same_seed_gives_the_same_puzzles():
    assert PuzzleGenerator(seed=7).puzzles(4, 3) == PuzzleGenerator(seed=7).puzzles(4, 3)


def test_the_puzzles_for_a_level_are_all_different():
    puzzles = PuzzleGenerator(seed=0).puzzles(2, 8)
    assert len({puzzle.board.draw() for puzzle in puzzles}) == 8


def test_both_open_rooms_and_mazes_are_generated():
    puzzles = PuzzleGenerator(seed=1).puzzles(6, 10)
    assert {puzzle.style for puzzle in puzzles} == {"room", "maze"}


def test_a_level_is_topped_up_to_the_target_and_hand_made_puzzles_are_kept(tmp_path):
    folder = tmp_path / "level-02"
    folder.mkdir()
    (folder / "straight.yaml").write_text(
        "moves_to_goal: 2\nmap: |\n  ######\n  #A.G.#\n  ######\n"
    )
    write_level(tmp_path, level=2, target=4, seed=0)
    write_level(tmp_path, level=2, target=4, seed=0)

    names = sorted(path.stem for path in folder.glob("*.yaml"))
    assert names == ["gen-02-01", "gen-02-02", "gen-02-03", "straight"]
    generated = Scenario.load(folder / "gen-02-01.yaml")
    assert generated.moves_to_goal == 2
    assert solver.distance(generated.board) == 2


def test_the_repository_has_ten_puzzles_at_every_level():
    counts = {}
    for scenario in load_scenarios().values():
        counts[scenario.moves_to_goal] = counts.get(scenario.moves_to_goal, 0) + 1
    assert counts == {level: 10 for level in range(1, 11)}
