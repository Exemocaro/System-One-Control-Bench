from dataclasses import replace

import pytest

from system_one_control.board import Board
from system_one_control.generator import (
    LONGER_ROUTE,
    NEEDS_PLANNING,
    NEEDS_PLANNING_KEYLESS,
    PuzzleGenerator,
    greedy_wins,
    has_a_longer_route,
    write_level,
)
from system_one_control.rules import CompassRules
from system_one_control.scenario import Scenario, load_scenarios
from system_one_control.solver import Solver

solver = Solver(CompassRules())
SCENARIOS = load_scenarios()

# The goal sits just below A, but A must climb out of its pocket and walk round either side.
POCKET = """
#######
#.....#
#.#.#.#
#.#A#.#
#.###.#
#..G..#
#######
"""
# Two ways round a block: along the top in 4 moves, or down and round the bottom in 8.
LOOP = """
#######
#A...G#
#.###.#
#.....#
#######
"""


@pytest.mark.parametrize("level", range(1, 11))
def test_a_generated_puzzle_is_exactly_its_level_away_from_the_goal(level):
    board = PuzzleGenerator(seed=level).puzzles(level, 1)[0].board
    assert solver.moves_to_goal(board) == level


@pytest.mark.parametrize("level", range(3, 11))
def test_from_level_three_every_puzzle_needs_the_key(level):
    board = PuzzleGenerator(seed=level).puzzles(level, 1)[0].board
    keyless = replace(board, rows=tuple(r.replace("K", ".") for r in board.rows))
    assert board.find("K") and board.find("D")
    assert solver.moves_to_goal(keyless) is None


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
    assert solver.moves_to_goal(generated.board) == 2


def test_a_failed_generation_keeps_the_puzzles_already_there(tmp_path, monkeypatch):
    write_level(tmp_path, level=2, target=3, seed=0)
    before = {path.name: path.read_text() for path in (tmp_path / "level-02").glob("*.yaml")}

    def fail(*args, **kwargs):
        raise RuntimeError("could not generate")

    monkeypatch.setattr(PuzzleGenerator, "puzzles", fail)
    with pytest.raises(RuntimeError):
        write_level(tmp_path, level=2, target=3, seed=1)
    after = {path.name: path.read_text() for path in (tmp_path / "level-02").glob("*.yaml")}
    assert after == before


def test_the_repository_has_ten_puzzles_at_every_level():
    counts = {}
    for scenario in SCENARIOS.values():
        counts[scenario.moves_to_goal] = counts.get(scenario.moves_to_goal, 0) + 1
    assert counts == dict.fromkeys(range(1, 11), 10)


def test_greedy_wins_where_walking_straight_at_the_goal_works():
    assert greedy_wins(Board.parse("#####\n#A.G#\n#####"))
    assert not greedy_wins(Board.parse(POCKET))


def test_a_longer_route_must_exist_and_be_longer():
    assert has_a_longer_route(Board.parse(LOOP))
    assert not has_a_longer_route(Board.parse("######\n#A..G#\n######"))
    assert not has_a_longer_route(Board.parse(POCKET))  # its two routes are the same length


def test_a_puzzle_of_a_harder_kind_is_generated_to_order():
    board = PuzzleGenerator(seed=0).puzzles(10, 1, kind=LONGER_ROUTE)[0].board
    assert solver.moves_to_goal(board) == 10
    assert not greedy_wins(board) and has_a_longer_route(board)


def test_a_level_gets_its_harder_puzzles_and_a_hand_made_one_counts_toward_them(tmp_path):
    folder = tmp_path / "level-10"
    folder.mkdir()
    (folder / "pocket.yaml").write_text(
        "moves_to_goal: 10\nmap: |\n" + "".join(f"  {row}\n" for row in POCKET.split())
    )
    written = write_level(tmp_path, level=10, target=10, seed=0)
    boards = [Scenario.load(path).board for path in written]
    assert len(written) == 9
    assert sum(has_a_longer_route(board) for board in boards) >= 5
    assert not any(greedy_wins(board) for board in boards)


def at_level(level):
    return [s.board for s in SCENARIOS.values() if s.moves_to_goal == level]


@pytest.mark.parametrize(
    ("level", "count"), [(1, 0), (2, 0), (3, 1), (4, 1), (5, 2), (6, 2), (7, 3), (8, 5), (9, 5)]
)
def test_the_puzzles_that_need_planning_grow_steadily_with_the_level(level, count):
    assert sum(NEEDS_PLANNING.accepts(board) for board in at_level(level)) == count


def test_no_puzzle_at_level_ten_can_be_won_by_walking_straight_at_the_target():
    assert not any(greedy_wins(board) for board in at_level(10))


def test_at_least_half_of_level_ten_has_a_second_longer_route():
    assert sum(LONGER_ROUTE.accepts(board) for board in at_level(10)) >= 5


def test_a_keyless_kind_turns_down_a_puzzle_with_a_key():
    with_key = Board.parse(POCKET.replace("#.....#", "#..K..#", 1))
    assert NEEDS_PLANNING.accepts(with_key)
    assert not NEEDS_PLANNING_KEYLESS.accepts(with_key)
    assert NEEDS_PLANNING_KEYLESS.accepts(Board.parse(POCKET))
