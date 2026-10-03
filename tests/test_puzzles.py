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
    count_kind,
    detours,
    greedy_wins,
    has_a_longer_route,
    load_puzzles,
    outer_wall,
    thick_wall_count,
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
STRAIGHT = "#####\n#A.G#\n#####"
# The goal sits just below A, but A must climb out of its pocket and walk round either side.
POCKET = "#######\n#.....#\n#.#.#.#\n#.#A#.#\n#.###.#\n#..G..#\n#######"
# Two ways round a block: along the top in 4 moves, or down and round the bottom in 8.
LOOP = "#######\n#A...G#\n#.###.#\n#.....#\n#######"
TINY = "level: 1\nmap: |\n  ####\n  #AG#\n  ####\n"


def at_level(level):
    return [p.board for p in PUZZLES.values() if p.level == level]


def without_key(board):
    return replace(board, rows=tuple(r.replace("K", ".") for r in board.rows))


@pytest.mark.parametrize("name", PUZZLES)
def test_the_solver_agrees_with_what_each_puzzle_file_claims(name):
    puzzle = PUZZLES[name]
    assert Solver(puzzle.rules).fewest_moves(puzzle.board) == puzzle.level


@pytest.mark.parametrize("name", PUZZLES)
def test_a_game_allows_twice_the_moves_the_solver_needs(name):
    assert PUZZLES[name].max_moves == 2 * PUZZLES[name].level


@pytest.mark.parametrize("path", sorted(PUZZLE_DIR.rglob("*.yaml")), ids=lambda p: p.stem)
def test_each_puzzle_sits_in_the_folder_for_its_level(path):
    assert path.parent.name == f"level-{Puzzle.load(path).level:02d}"


@pytest.mark.parametrize("name", [n for n, p in PUZZLES.items() if p.board.find("K")])
def test_where_there_is_a_key_the_goal_cannot_be_reached_without_it(name):
    assert Solver(PUZZLES[name].rules).fewest_moves(without_key(PUZZLES[name].board)) is None


def test_every_level_has_the_number_of_puzzles_levels_asks_for():
    levels = [p.level for p in PUZZLES.values()]
    assert {level: levels.count(level) for level in set(levels)} == LEVELS


def test_puzzles_are_named_after_their_file_and_sorted_by_difficulty():
    levels = [p.level for p in PUZZLES.values()]
    assert ("maze" in PUZZLES, "gen-03-01" in PUZZLES, levels == sorted(levels)) == (True,) * 3


def test_a_puzzle_file_can_choose_its_rules(tmp_path):
    (tmp_path / "tiny.yaml").write_text("rules: two-moves\n" + TINY)
    puzzle = Puzzle.load(tmp_path / "tiny.yaml")
    assert (puzzle.name, puzzle.rules.name) == ("tiny", "two-moves")


def test_two_puzzles_may_not_share_a_name(tmp_path):
    for level in ("level-01", "level-02"):
        (tmp_path / level).mkdir()
        (tmp_path / level / "tiny.yaml").write_text(TINY)
    with pytest.raises(ValueError, match="tiny"):
        load_puzzles(tmp_path)


@pytest.mark.parametrize(
    "rules",
    [TwoMoveRules(), ThreeMoveRules(), UpToTwoMoveRules(), UpToThreeMoveRules()],
    ids=lambda r: r.name,
)
def test_under_sequence_rules_every_puzzle_is_won_in_its_fewest_moves(rules):
    played = [replace(p, rules=rules) for p in PUZZLES.values()]
    assert all(Solver(rules).fewest_moves(p.board) == p.fewest_moves for p in played)


def test_under_sequence_rules_a_game_allows_twice_the_fewest_sequences():
    puzzle = replace(PUZZLES["gen-05-01"], rules=TwoMoveRules())
    assert (puzzle.level, puzzle.fewest_moves, puzzle.max_moves) == (5, 3, 6)


# Each row: a level, a kind of puzzle, and how many of that level's puzzles are at least of it.
@pytest.mark.parametrize(
    ("level", "kind", "least"),
    [
        (1, NEEDS_PLANNING, 0),
        (3, NEEDS_PLANNING, 1),
        (4, NEEDS_PLANNING, 1),
        (5, NEEDS_PLANNING, 2),
        (6, NEEDS_PLANNING, 2),
        (8, NEEDS_PLANNING, 5),
        (2, WALL_IN_THE_WAY, 3),
        (3, WALL_IN_THE_WAY, 3),
        (4, around(1), 3),
        (5, around(1), 3),
        (6, around(2), 3),
        (8, around(2), 3),
        (10, LONGER_ROUTE, 5),
        (15, with_detours(4), 5),
        (20, with_detours(6), 5),
    ],
    ids=[
        "level 1 needs no planning",
        "level 3 needs planning once",
        "level 4 needs planning once",
        "level 5 needs planning twice",
        "level 6 needs planning twice",
        "level 8 needs planning half the time",
        "level 2 has a wall in the way",
        "level 3 has a wall in the way",
        "level 4 goes round a wall",
        "level 5 goes round a wall",
        "level 6 goes round two walls",
        "level 8 goes round two walls",
        "level 10 has a longer second route",
        "level 15 turns away four times",
        "level 20 turns away six times",
    ],
)
def test_the_levels_have_the_kinds_of_puzzle_they_are_meant_to(level, kind, least):
    assert count_kind(at_level(level), kind) >= least


@pytest.mark.parametrize("level", [10, 12, 15, 20])
def test_no_puzzle_at_the_top_levels_can_be_won_by_walking_straight_at_the_target(level):
    assert not any(greedy_wins(board) for board in at_level(level))


@pytest.mark.parametrize(("level", "least"), [(12, 2), (15, 3), (20, 5)])
def test_every_puzzle_at_the_top_levels_needs_detours(level, least):
    assert all((detours(board) or 0) >= least for board in at_level(level))


@pytest.mark.parametrize("level", [12, 15, 20])
def test_half_of_the_top_three_levels_have_a_thicker_outer_wall(level):
    assert thick_wall_count(at_level(level)) == 5


@pytest.mark.parametrize("level", [15, 20])
def test_one_puzzle_at_each_of_the_two_top_levels_is_walled_in_five_thick(level):
    assert sum(outer_wall(board) == 5 for board in at_level(level)) == 1


@pytest.mark.parametrize(
    ("text", "expected"), [(STRAIGHT, True), (POCKET, False)], ids=["a straight line", "a pocket"]
)
def test_greedy_wins_where_walking_straight_at_the_goal_works(text, expected):
    assert greedy_wins(Board.parse(text)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [(LOOP, True), ("######\n#A..G#\n######", False), (POCKET, False)],
    ids=["a loop", "one route", "two routes of the same length"],
)
def test_a_longer_route_must_exist_and_be_longer(text, expected):
    assert has_a_longer_route(Board.parse(text)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # The goal is up and to the left, and north is a wall: the puzzle Jev lost at level 2.
        ("######\n#G#.##\n#.A..#\n######", True),
        (STRAIGHT, False),
    ],
    ids=["north is a wall", "a straight line"],
)
def test_a_wall_in_the_way_blocks_a_first_step_toward_the_target(text, expected):
    assert wall_in_the_way(Board.parse(text)) == expected


@pytest.mark.parametrize(
    ("kind", "text", "expected"),
    [
        (NEEDS_PLANNING, POCKET.replace("#.....#", "#..K..#", 1), True),
        (NEEDS_PLANNING_KEYLESS, POCKET.replace("#.....#", "#..K..#", 1), False),
        (NEEDS_PLANNING_KEYLESS, POCKET, True),
    ],
    ids=["a key is fine", "a keyless kind turns it down", "a keyless puzzle is fine"],
)
def test_a_kind_accepts_or_turns_down_a_puzzle(kind, text, expected):
    assert kind.accepts(Board.parse(text)) == expected


# Walking back for the key is not a detour: the key is the target until it is picked up.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (STRAIGHT, 0),
        (POCKET, 4),
        ("#########\n#GD..A.K#\n#########", 0),
        ("#####\n#A#G#\n#####", None),
    ],
    ids=["a straight line", "out of a pocket", "back for the key", "unreachable"],
)
def test_detours_count_the_moves_away_from_the_target_every_shortest_route_makes(text, expected):
    assert detours(Board.parse(text)) == expected


def test_a_thicker_outer_wall_changes_nothing_but_the_map():
    board = Board.parse(POCKET)
    thick = thicken(board, 3)
    assert (len(thick.rows), thick.rows[0], thick.rows[3]) == (11, "#" * 11, "###.....###")
    assert solver.fewest_moves(thick) == solver.fewest_moves(board)
    assert detours(thick) == detours(board)
    assert thicken(board, 1) == board


@pytest.mark.parametrize("level", LEVELS)
def test_a_generated_puzzle_is_exactly_its_level_away_from_the_goal(level):
    assert solver.fewest_moves(PuzzleGenerator(seed=level).drafts(level, 1)[0].board) == level


@pytest.mark.parametrize("level", [level for level in LEVELS if level >= 3])
def test_from_level_three_every_generated_puzzle_needs_the_key(level):
    board = PuzzleGenerator(seed=level).drafts(level, 1)[0].board
    assert (bool(board.find("K")), bool(board.find("D"))) == (True, True)
    assert solver.fewest_moves(without_key(board)) is None


def test_the_same_seed_gives_the_same_puzzles():
    assert PuzzleGenerator(seed=7).drafts(4, 3) == PuzzleGenerator(seed=7).drafts(4, 3)


def test_the_puzzles_for_a_level_are_all_different():
    drafts = PuzzleGenerator(seed=0).drafts(2, 8)
    assert len({draft.board.draw() for draft in drafts}) == 8


def test_both_open_rooms_and_mazes_are_generated():
    drafts = PuzzleGenerator(seed=1).drafts(6, 10)
    assert {draft.style for draft in drafts} == {"room", "maze"}


def test_a_puzzle_of_a_harder_kind_is_generated_to_order():
    board = PuzzleGenerator(seed=0).drafts(10, 1, kind=LONGER_ROUTE)[0].board
    assert solver.fewest_moves(board) == 10
    assert (greedy_wins(board), has_a_longer_route(board)) == (False, True)


def test_a_level_is_topped_up_to_the_target_and_hand_made_puzzles_are_kept(tmp_path):
    folder = tmp_path / "level-02"
    folder.mkdir()
    (folder / "straight.yaml").write_text("level: 2\nmap: |\n  ######\n  #A.G.#\n  ######\n")
    write_level(tmp_path, level=2, target=4, seed=0)
    write_level(tmp_path, level=2, target=4, seed=0)
    names = sorted(path.stem for path in folder.glob("*.yaml"))
    assert names == ["gen-02-01", "gen-02-02", "gen-02-03", "straight"]


def test_a_level_gets_its_harder_puzzles_and_a_hand_made_one_counts_toward_them(tmp_path):
    folder = tmp_path / "level-10"
    folder.mkdir()
    rows = "".join(f"  {row}\n" for row in POCKET.split())
    (folder / "pocket.yaml").write_text("level: 10\nmap: |\n" + rows)
    written = write_level(tmp_path, level=10, target=10, seed=0)
    boards = [Puzzle.load(path).board for path in written]
    assert len(written) == 9
    assert count_kind(boards, LONGER_ROUTE) >= 5
    assert not any(greedy_wins(board) for board in boards)


def test_a_failed_generation_keeps_the_puzzles_already_there(tmp_path, monkeypatch):
    write_level(tmp_path, level=2, target=3, seed=0)
    before = {path.name: path.read_text() for path in (tmp_path / "level-02").glob("*.yaml")}
    monkeypatch.setattr(PuzzleGenerator, "drafts", lambda *a, **k: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        write_level(tmp_path, level=2, target=3, seed=1)
    after = {path.name: path.read_text() for path in (tmp_path / "level-02").glob("*.yaml")}
    assert after == before
