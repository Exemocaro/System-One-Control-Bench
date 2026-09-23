from dataclasses import replace

import pytest

from system_one_control.board import Board
from system_one_control.generator import (
    LEVELS,
    LONGER_ROUTE,
    NEEDS_PLANNING,
    NEEDS_PLANNING_KEYLESS,
    PuzzleGenerator,
    detours,
    greedy_wins,
    has_a_longer_route,
    thicken,
    with_detours,
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


@pytest.mark.parametrize("level", LEVELS)
def test_a_generated_puzzle_is_exactly_its_level_away_from_the_goal(level):
    board = PuzzleGenerator(seed=level).puzzles(level, 1)[0].board
    assert solver.moves_to_goal(board) == level


@pytest.mark.parametrize("level", [level for level in LEVELS if level >= 3])
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


def test_the_repository_has_the_puzzles_levels_asks_for():
    counts = {}
    for scenario in SCENARIOS.values():
        counts[scenario.moves_to_goal] = counts.get(scenario.moves_to_goal, 0) + 1
    assert counts == LEVELS


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
    ("level", "count"), [(1, 0), (2, 0), (3, 1), (4, 1), (5, 2), (6, 2), (8, 5)]
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


def test_detours_count_the_moves_away_from_the_target_that_every_shortest_route_makes():
    assert detours(Board.parse("#####\n#A.G#\n#####")) == 0
    # Up out of the pocket (two away), along the top (two away), then down and back to the goal.
    assert detours(Board.parse(POCKET)) == 4
    # Walking back for the key is not a detour: the key is the target until it is picked up.
    assert detours(Board.parse("#########\n#GD..A.K#\n#########")) == 0
    assert detours(Board.parse("#####\n#A#G#\n#####")) is None


@pytest.mark.parametrize(("level", "least"), [(12, 2), (15, 3), (20, 5)])
def test_every_puzzle_at_the_top_levels_needs_planning_and_detours(level, least):
    boards = at_level(level)
    assert not any(greedy_wins(board) for board in boards)
    assert all((detours(board) or 0) >= least for board in boards)


@pytest.mark.parametrize(("level", "least"), [(15, 4), (20, 6)])
def test_half_of_the_two_top_levels_turns_away_even_more(level, least):
    assert sum(with_detours(least).accepts(board) for board in at_level(level)) >= 5


def test_a_thicker_outer_wall_changes_nothing_but_the_map():
    board = Board.parse(POCKET)
    thick = thicken(board, 3)
    assert len(thick.rows) == len(board.rows) + 4
    assert thick.rows[0] == thick.rows[1] == "#" * 11
    assert thick.rows[3] == "###.....###"
    assert solver.moves_to_goal(thick) == solver.moves_to_goal(board)
    assert detours(thick) == detours(board)
    assert thicken(board, 1) == board


def outer_wall(board):
    """How many rings of solid wall surround the map."""
    rings = 0
    while all(
        set(row[rings]) == {"#"} and set(row[-1 - rings]) == {"#"} for row in board.rows
    ) and (set(board.rows[rings]) == set(board.rows[-1 - rings]) == {"#"}):
        rings += 1
    return rings


@pytest.mark.parametrize("level", [12, 15, 20])
def test_half_of_the_top_three_levels_have_a_thicker_outer_wall(level):
    walls = sorted(outer_wall(board) for board in at_level(level))
    assert walls[:5] == [1] * 5
    assert all(wall >= 2 for wall in walls[5:])


@pytest.mark.parametrize("level", [15, 20])
def test_one_puzzle_at_each_of_the_two_top_levels_is_walled_in_five_thick(level):
    assert sum(outer_wall(board) == 5 for board in at_level(level)) == 1
