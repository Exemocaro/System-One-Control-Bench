import json
import random
from collections import Counter
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from system_one_control.bench import split_finished
from system_one_control.cli import app
from system_one_control.exam import (
    ITEMS_FILE,
    ExamItem,
    check_same_exam,
    exam_keys,
    examine,
    load_exam,
    run_exam,
    save_exam,
)
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
runner = CliRunner(env={"FORCE_COLOR": None, "NO_COLOR": "1", "COLUMNS": "200"})


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


@pytest.mark.parametrize("item", ITEMS, ids=[f"{i.puzzle} {i.kind}" for i in ITEMS])
def test_labels_match_the_solver_at_the_end(item):
    end = walk(item)[-1]
    assert (item.has_key, item.next_to_wall, item.best_moves, item.options) == (
        "key" in end.holding,
        any(COMPASS.apply(end, move) == end for move in COMPASS.moves(end)),
        SOLVER.best_moves(end),
        len(COMPASS.moves(end)),
    )


def answered(items, players=None, **more):
    if players is None:
        players = {"solver": SolverPlayer}
    return run_exam(PUZZLES, items, [MAP], players, **more)


def test_answers_already_done_are_skipped_and_handed_over():
    handed = []
    done = {(ITEMS[0].puzzle, ITEMS[0].kind, ITEMS[0].prefix, "map", "solver")}
    records = answered(ITEMS[:3], done=done, on_record=handed.append)
    assert [r.item.prefix for r in records] == [item.prefix for item in ITEMS[1:3]]
    assert handed == records


def test_a_failure_to_build_stops_the_run_after_what_was_handed_over():
    handed, built = [], 0

    def build():
        nonlocal built
        built += 1
        if built == 2:
            raise RuntimeError("could not start a player")
        return SolverPlayer()

    with pytest.raises(RuntimeError, match="could not start"):
        answered(ITEMS[:2], players={"solver": build}, on_record=handed.append)
    assert (len(handed), built) == (1, 2)


OK = examine(PUZZLES[ITEMS[0].puzzle], ITEMS[0], MAP, "solver", SolverPlayer())
BAD = replace(OK, error="the server is down")


@pytest.mark.parametrize(
    ("records", "kept", "dropped"),
    [([OK], [OK], []), ([OK, BAD], [OK], [BAD])],
    ids=["nothing errored", "one error to ask again"],
)
def test_split_keeps_the_answered_for_resume(records, kept, dropped):
    assert split_finished(records) == (kept, dropped)


def test_exam_keys_lists_every_item_condition_and_player():
    keys = exam_keys(ITEMS[:2], [MAP], {"a": SolverPlayer, "b": SolverPlayer})
    assert keys == [
        (item.puzzle, item.kind, item.prefix, "map", name)
        for item in ITEMS[:2]
        for name in ("a", "b")
    ]


def test_check_same_exam_refuses_answers_from_another_run():
    records = answered(ITEMS[:2])
    keys = [record.key for record in records]
    assert check_same_exam(records, keys) is None
    assert "would not ask" in check_same_exam([*records, replace(records[0], item=ITEMS[2])], keys)


def test_exam_needs_permission_for_paid_players(tmp_path):
    out = tmp_path / "exam.jsonl"
    result = runner.invoke(app, ["exam", "--players", "jev", "--out", str(out)])
    assert result.exit_code != 0
    assert "--allow-paid" in result.output
    assert not out.exists()


def test_exam_resume_replays_the_errors_and_keeps_the_rest(tmp_path):
    items = tmp_path / "items.jsonl"
    items.write_text("\n".join(item.to_json() for item in ITEMS[:2]) + "\n", encoding="utf-8")
    out = tmp_path / "exam.jsonl"
    command = ["exam", "--players", "solver", "--items", str(items), "--out", str(out)]
    assert runner.invoke(app, command).exit_code == 0
    kept, broken = out.read_text(encoding="utf-8").splitlines()
    broken = json.dumps(json.loads(broken) | {"error": "ConnectionError: the API is down"})
    out.write_text(f"{kept}\n{broken}\n", encoding="utf-8")

    result = runner.invoke(app, [*command, "--resume"])
    assert result.exit_code == 0, result.output
    assert "Keeping 1 answered items, asking 1" in result.output
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and kept in lines
    assert all(json.loads(line)["error"] is None for line in lines)
