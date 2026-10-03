import random
from collections import Counter

import pytest

from system_one_control.exam import ITEMS_FILE, ExamItem, examine, load_exam, save_exam
from system_one_control.exam_items import build_prefix, shortest_route, take_step
from system_one_control.players.baselines import SolverPlayer
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import load_puzzles
from system_one_control.world import COMPASS, Board, Solver
from tests.helpers import MAP

PUZZLES = load_puzzles()
ITEMS = [ExamItem.from_json(line) for line in ITEMS_FILE.read_text(encoding="utf-8").splitlines()]
SOLVER = Solver(COMPASS)
CORRIDOR = Board.parse("#####\n#A.G#\n#####")
ROUTE = shortest_route(CORRIDOR, random.Random(0))


def walk(item):
    """The boards an item visits, the start included."""
    boards = [PUZZLES[item.puzzle].board]
    for name in item.prefix:
        boards.append(take_step(boards[-1], name))
    return boards


def all_on_route(names, boards):
    """Whether every named move is a best move from its board."""
    return all(name in SOLVER.best_moves(board) for name, board in zip(names, boards, strict=True))


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("start", ()),
        ("on-route", ("east",)),
        ("off-route", ("east", "west")),
        ("after-blocked", ("east", "north")),
        ("late", ("east",)),
    ],
    ids=[
        "empty at the start",
        "one step along",
        "a step back",
        "a step into a wall",
        "late is one step here",
    ],
)
def test_each_kind_builds_its_prefix(kind, expected):
    assert build_prefix(kind, CORRIDOR, ROUTE, 2, random.Random(1)) == expected


def test_every_puzzle_has_five_items_or_four_at_level_one():
    counts = Counter((item.puzzle, item.level) for item in ITEMS)
    assert all(n == (4 if level == 1 else 5) for (_, level), n in counts.items())
    assert len(ITEMS) == 495


ROUTE_ITEMS = [item for item in ITEMS if item.kind in ("start", "on-route", "late")]
OFF_ITEMS = [item for item in ITEMS if item.kind == "off-route"]
BLOCKED_ITEMS = [item for item in ITEMS if item.kind == "after-blocked"]


@pytest.mark.parametrize("item", ROUTE_ITEMS, ids=[f"{i.puzzle} {i.kind}" for i in ROUTE_ITEMS])
def test_route_prefix_items_stay_on_a_shortest_route(item):
    assert all_on_route(item.prefix, walk(item)[:-1])


@pytest.mark.parametrize("item", OFF_ITEMS, ids=[f"{i.puzzle} {i.kind}" for i in OFF_ITEMS])
def test_off_route_items_end_one_move_off_the_route(item):
    boards = walk(item)
    assert all_on_route(item.prefix[:-1], boards[:-2])
    assert item.prefix[-1] not in SOLVER.best_moves(boards[-2])
    assert boards[-1] != boards[-2]


@pytest.mark.parametrize("item", BLOCKED_ITEMS, ids=[f"{i.puzzle} {i.kind}" for i in BLOCKED_ITEMS])
def test_after_blocked_items_end_with_a_move_into_a_wall(item):
    boards = walk(item)
    assert all_on_route(item.prefix[:-1], boards[:-2])
    assert boards[-1] == boards[-2]


def test_one_exam_answer_records_the_item_and_the_move():
    item = ITEMS[0]
    record = examine(PUZZLES[item.puzzle], item, MAP, "solver", SolverPlayer())
    assert (record.item, record.condition, record.player) == (item, "map", "solver")
    assert record.answer.optimal and record.error is None
    assert record.answer.best_moves == item.best_moves


def test_exam_answers_save_and_load_unchanged(tmp_path):
    item = ITEMS[0]
    record = examine(PUZZLES[item.puzzle], item, CONDITIONS["everything"], "solver", SolverPlayer())
    assert load_exam(save_exam([record], tmp_path / "exam.jsonl")) == [record]
