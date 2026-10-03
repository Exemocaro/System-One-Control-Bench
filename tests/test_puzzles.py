from dataclasses import replace

import pytest

from system_one_control.puzzles import (
    LEVELS,
    LONGER_ROUTE,
    NEEDS_PLANNING,
    NEEDS_PLANNING_KEYLESS,
    PUZZLE_DIR,
    WALL_IN_THE_WAY,
    Puzzle,
    PuzzleGenerator,
    around,
    detours,
    greedy_wins,
    has_a_longer_route,
    load_puzzles,
    thicken,
    wall_in_the_way,
    with_detours,
    write_level,
)
from system_one_control.world import (
    Board,
    CompassRules,
    Solver,
    ThreeMoveRules,
    TwoMoveRules,
    UpToThreeMoveRules,
    UpToTwoMoveRules,
)

PUZZLES = load_puzzles()
solver = Solver(CompassRules())

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


@pytest.mark.parametrize("name", PUZZLES)
def test_the_solver_agrees_with_what_each_puzzle_file_claims(name):
    puzzle = PUZZLES[name]
    solver = Solver(puzzle.rules)
    assert solver.fewest_moves(puzzle.board) == puzzle.level


def test_every_level_has_puzzles_and_there_are_no_others():
    assert {s.level for s in PUZZLES.values()} == set(LEVELS)


@pytest.mark.parametrize("path", sorted(PUZZLE_DIR.rglob("*.yaml")), ids=lambda p: p.stem)
def test_each_puzzle_sits_in_the_folder_for_its_level(path):
    assert path.parent.name == f"level-{Puzzle.load(path).level:02d}"


@pytest.mark.parametrize("name", [n for n, s in PUZZLES.items() if s.board.find("K")])
def test_where_there_is_a_key_the_goal_cannot_be_reached_without_it(name):
    puzzle = PUZZLES[name]
    keyless = replace(puzzle.board, rows=tuple(r.replace("K", ".") for r in puzzle.board.rows))
    assert Solver(puzzle.rules).fewest_moves(keyless) is None


def test_puzzles_are_named_after_their_file_and_sorted_by_difficulty():
    assert "maze" in PUZZLES and "gen-03-01" in PUZZLES
    distances = [s.level for s in PUZZLES.values()]
    assert distances == sorted(distances)


def test_a_puzzle_file_can_choose_its_rules(tmp_path):
    path = tmp_path / "tiny.yaml"
    path.write_text("rules: compass\nlevel: 1\nmap: |\n  ####\n  #AG#\n  ####\n")
    puzzle = Puzzle.load(path)
    assert puzzle.name == "tiny"
    assert puzzle.rules.name == "compass"


@pytest.mark.parametrize("name", PUZZLES)
def test_a_game_allows_twice_the_moves_the_solver_needs(name):
    assert PUZZLES[name].max_moves == 2 * PUZZLES[name].level


def test_two_puzzles_may_not_share_a_name(tmp_path):
    tiny = "level: 1\nmap: |\n  ####\n  #AG#\n  ####\n"
    for level in ("level-01", "level-02"):
        (tmp_path / level).mkdir()
        (tmp_path / level / "tiny.yaml").write_text(tiny)
    with pytest.raises(ValueError, match="tiny"):
        load_puzzles(tmp_path)


@pytest.mark.parametrize(
    "rules",
    [TwoMoveRules(), ThreeMoveRules(), UpToTwoMoveRules(), UpToThreeMoveRules()],
    ids=lambda r: r.name,
)
def test_under_sequence_rules_every_puzzle_is_won_in_its_fewest_moves(rules):
    for puzzle in PUZZLES.values():
        played = replace(puzzle, rules=rules)
        assert Solver(rules).fewest_moves(played.board) == played.fewest_moves, puzzle.name


def test_under_sequence_rules_a_game_allows_twice_the_fewest_sequences():
    puzzle = replace(PUZZLES["gen-05-01"], rules=TwoMoveRules())
    assert puzzle.level == 5
    assert puzzle.fewest_moves == 3
    assert puzzle.max_moves == 6


@pytest.mark.parametrize("level", LEVELS)
def test_a_generated_puzzle_is_exactly_its_level_away_from_the_goal(level):
    board = PuzzleGenerator(seed=level).drafts(level, 1)[0].board
    assert solver.fewest_moves(board) == level


@pytest.mark.parametrize("level", [level for level in LEVELS if level >= 3])
def test_from_level_three_every_puzzle_needs_the_key(level):
    board = PuzzleGenerator(seed=level).drafts(level, 1)[0].board
    keyless = replace(board, rows=tuple(r.replace("K", ".") for r in board.rows))
    assert board.find("K") and board.find("D")
    assert solver.fewest_moves(keyless) is None


def test_the_same_seed_gives_the_same_puzzles():
    assert PuzzleGenerator(seed=7).drafts(4, 3) == PuzzleGenerator(seed=7).drafts(4, 3)


def test_the_puzzles_for_a_level_are_all_different():
    puzzles = PuzzleGenerator(seed=0).drafts(2, 8)
    assert len({puzzle.board.draw() for puzzle in puzzles}) == 8


def test_both_open_rooms_and_mazes_are_generated():
    puzzles = PuzzleGenerator(seed=1).drafts(6, 10)
    assert {puzzle.style for puzzle in puzzles} == {"room", "maze"}


def test_a_level_is_topped_up_to_the_target_and_hand_made_puzzles_are_kept(tmp_path):
    folder = tmp_path / "level-02"
    folder.mkdir()
    (folder / "straight.yaml").write_text(
        "level: 2\nmap: |\n  ######\n  #A.G.#\n  ######\n"
    )
    write_level(tmp_path, level=2, target=4, seed=0)
    write_level(tmp_path, level=2, target=4, seed=0)

    names = sorted(path.stem for path in folder.glob("*.yaml"))
    assert names == ["gen-02-01", "gen-02-02", "gen-02-03", "straight"]
    generated = Puzzle.load(folder / "gen-02-01.yaml")
    assert generated.level == 2
    assert solver.fewest_moves(generated.board) == 2


def test_a_failed_generation_keeps_the_puzzles_already_there(tmp_path, monkeypatch):
    write_level(tmp_path, level=2, target=3, seed=0)
    before = {path.name: path.read_text() for path in (tmp_path / "level-02").glob("*.yaml")}

    def fail(*args, **kwargs):
        raise RuntimeError("could not generate")

    monkeypatch.setattr(PuzzleGenerator, "drafts", fail)
    with pytest.raises(RuntimeError):
        write_level(tmp_path, level=2, target=3, seed=1)
    after = {path.name: path.read_text() for path in (tmp_path / "level-02").glob("*.yaml")}
    assert after == before


def test_the_repository_has_the_puzzles_levels_asks_for():
    counts = {}
    for puzzle in PUZZLES.values():
        counts[puzzle.level] = counts.get(puzzle.level, 0) + 1
    assert counts == LEVELS


def test_greedy_wins_where_walking_straight_at_the_goal_works():
    assert greedy_wins(Board.parse("#####\n#A.G#\n#####"))
    assert not greedy_wins(Board.parse(POCKET))


def test_a_longer_route_must_exist_and_be_longer():
    assert has_a_longer_route(Board.parse(LOOP))
    assert not has_a_longer_route(Board.parse("######\n#A..G#\n######"))
    assert not has_a_longer_route(Board.parse(POCKET))  # its two routes are the same length


def test_a_puzzle_of_a_harder_kind_is_generated_to_order():
    board = PuzzleGenerator(seed=0).drafts(10, 1, kind=LONGER_ROUTE)[0].board
    assert solver.fewest_moves(board) == 10
    assert not greedy_wins(board) and has_a_longer_route(board)


def test_a_level_gets_its_harder_puzzles_and_a_hand_made_one_counts_toward_them(tmp_path):
    folder = tmp_path / "level-10"
    folder.mkdir()
    (folder / "pocket.yaml").write_text(
        "level: 10\nmap: |\n" + "".join(f"  {row}\n" for row in POCKET.split())
    )
    written = write_level(tmp_path, level=10, target=10, seed=0)
    boards = [Puzzle.load(path).board for path in written]
    assert len(written) == 9
    assert sum(has_a_longer_route(board) for board in boards) >= 5
    assert not any(greedy_wins(board) for board in boards)


def at_level(level):
    return [s.board for s in PUZZLES.values() if s.level == level]


@pytest.mark.parametrize(
    ("level", "least"), [(1, 0), (2, 0), (3, 1), (4, 1), (5, 2), (6, 2), (8, 5)]
)
def test_the_puzzles_that_need_planning_grow_with_the_level(level, least):
    # At least as many as LEVEL_KINDS asks for: the puzzles that go round a wall may add more.
    assert sum(NEEDS_PLANNING.accepts(board) for board in at_level(level)) >= least


def test_levels_one_to_eight_are_all_generated():
    names = [s.name for s in PUZZLES.values() if s.level <= 8]
    assert all(name.startswith("gen-") for name in names)


@pytest.mark.parametrize(("level", "kind"), [(2, WALL_IN_THE_WAY), (3, WALL_IN_THE_WAY)])
def test_levels_two_and_three_have_three_keyless_puzzles_with_a_wall_in_the_way(level, kind):
    assert sum(kind.accepts(board) for board in at_level(level)) >= 3


@pytest.mark.parametrize(("level", "least"), [(4, 1), (5, 1), (6, 2), (8, 2)])
def test_levels_four_to_eight_have_three_keyless_puzzles_that_go_round_a_wall(level, least):
    assert sum(around(least).accepts(board) for board in at_level(level)) >= 3


def test_a_wall_in_the_way_blocks_a_first_step_toward_the_target():
    # The goal is up and to the left, and north is a wall: the puzzle Jev lost at level 2.
    assert wall_in_the_way(Board.parse("######\n#G#.##\n#.A..#\n######"))
    assert not wall_in_the_way(Board.parse("#####\n#A.G#\n#####"))


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
    assert solver.fewest_moves(thick) == solver.fewest_moves(board)
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
