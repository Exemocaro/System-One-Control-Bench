"""Exam item generation: fixed positions per puzzle from the solver's shortest route."""

from __future__ import annotations

import random
from collections.abc import Sequence

from system_one_control.exam import ExamItem
from system_one_control.puzzles import Puzzle
from system_one_control.world import COMPASS, Board, Solver

SOLVER = Solver(COMPASS)


def shortest_route(board: Board, rng: random.Random) -> list[str]:
    """The solver's route from this board: a best move at a time, ties broken by `rng`."""
    route, here = [], board
    while not COMPASS.is_won(here):
        move = rng.choice(SOLVER.best_moves(here))
        route.append(move)
        here = take_step(here, move)
    return route


def take_step(board: Board, name: str) -> Board:
    """The board after this named compass move, which must be offered."""
    move = COMPASS.find_move(board, name)
    assert move is not None
    return COMPASS.apply(board, move)


def apply_prefix(board: Board, prefix: Sequence[str]) -> Board:
    """The board after these named moves."""
    for name in prefix:
        board = take_step(board, name)
    return board


def won_along(board: Board, prefix: Sequence[str]) -> bool:
    """Whether any board on the way, the last included, already wins."""
    for name in prefix:
        board = take_step(board, name)
        if COMPASS.is_won(board):
            return True
    return False


def base_len(level: int, rng: random.Random) -> int:
    """An on-route base length: 1 to level-1, or 0 where level 1 leaves no choice."""
    return 0 if level == 1 else rng.randrange(1, level)


def deviation(end: Board, kind: str, rng: random.Random) -> str | None:
    """One more move from a route prefix end: deviating for off-route, blocked otherwise."""
    if kind == "off-route":
        best = SOLVER.best_moves(end)
        ends = [
            move.name
            for move in COMPASS.moves(end)
            if move.name not in best and COMPASS.apply(end, move) != end
        ]
    else:
        ends = [move.name for move in COMPASS.moves(end) if COMPASS.apply(end, move) == end]
    return rng.choice(ends) if ends else None


def on_route_prefix(route: list[str], level: int, rng: random.Random) -> tuple[str, ...] | None:
    """The first k route moves, k drawn from 1 to level-1."""
    if level < 2:
        return None
    return tuple(route[: rng.randrange(1, level)])


def off_route_prefix(
    board: Board, route: list[str], level: int, rng: random.Random
) -> tuple[str, ...] | None:
    """An on-route prefix plus a move that is not best and changes the board."""
    base = route[: base_len(level, rng)]
    final = deviation(apply_prefix(board, base), "off-route", rng)
    return (*base, final) if final is not None else None


def after_blocked_prefix(
    board: Board, route: list[str], level: int, rng: random.Random
) -> tuple[str, ...] | None:
    """An on-route prefix plus a move into a wall."""
    base = route[: base_len(level, rng)]
    final = deviation(apply_prefix(board, base), "after-blocked", rng)
    return (*base, final) if final is not None else None


def pickup_after(board: Board, route: list[str]) -> int | None:
    """After how many route moves the key is picked up, if the puzzle has one."""
    if not (board.find("K") or board.find("D")):
        return None
    for number, name in enumerate(route, start=1):
        board = take_step(board, name)
        if "key" in board.holding:
            return number
    return None


def late_prefix(
    board: Board, route: list[str], level: int, rng: random.Random
) -> tuple[str, ...] | None:
    """The first k route moves with k at least half the level, past the key where there is one."""
    low = max(1, (level + 1) // 2)
    pickup = pickup_after(board, route)
    if pickup is not None:
        low = max(low, pickup)
    if low > level - 1:
        return None
    return tuple(route[: rng.randrange(low, level)])


def build_prefix(
    kind: str, board: Board, route: list[str], level: int, rng: random.Random
) -> tuple[str, ...] | None:
    """The prefix for this kind, or None where the kind cannot be built here."""
    if kind == "start":
        return ()
    if kind == "on-route":
        return on_route_prefix(route, level, rng)
    if kind == "off-route":
        return off_route_prefix(board, route, level, rng)
    if kind == "after-blocked":
        return after_blocked_prefix(board, route, level, rng)
    if kind == "late":
        return late_prefix(board, route, level, rng)
    raise ValueError(f"unknown exam kind {kind!r}")


def chain_prefix(
    board: Board, route: list[str], level: int, kind: str, rng: random.Random
) -> tuple[str, ...] | None:
    """A route prefix plus one more move: deviating for off-route, blocked otherwise."""
    base = route[: rng.randrange(0, level)]
    final = deviation(apply_prefix(board, base), kind, rng)
    return (*base, final) if final is not None else None


def end_labels(board: Board) -> tuple[bool, bool, tuple[str, ...], int]:
    """has_key, next_to_wall, best_moves and options count at this board."""
    return (
        "key" in board.holding,
        any(COMPASS.apply(board, move) == board for move in COMPASS.moves(board)),
        SOLVER.best_moves(board),
        len(COMPASS.moves(board)),
    )


def make_items(puzzle: Puzzle, rng: random.Random) -> tuple[list[ExamItem], int]:
    """Five items for this puzzle (four at level 1), and how many reuse a seen board."""
    board, route = puzzle.board, shortest_route(puzzle.board, rng)
    assert len(route) == puzzle.level
    seen_boards, seen_prefixes, items, loose = set(), set(), [], 0

    def take(kind: str, prefix: tuple[str, ...] | None, loose_ok: bool) -> bool:
        nonlocal loose
        if prefix is None or won_along(board, prefix) or prefix in seen_prefixes:
            return False
        end = apply_prefix(board, prefix)
        if end in seen_boards:
            if not loose_ok:
                return False
            loose += 1
        seen_boards.add(end)
        seen_prefixes.add(prefix)
        has_key, next_to_wall, best_moves, options = end_labels(end)
        items.append(
            ExamItem(
                puzzle.name,
                puzzle.level,
                kind,
                prefix,
                has_key,
                next_to_wall,
                best_moves,
                options,
            )
        )
        return True

    for kind in ("start", "on-route", "off-route", "after-blocked", "late"):
        take(kind, build_prefix(kind, board, route, puzzle.level, rng), False)
    pool = ["off-route", "after-blocked"]
    tries, target = 0, 5 if puzzle.level >= 2 else 4
    while len(items) < target and tries < 1000:
        kind = pool[tries % len(pool)]
        tries += 1
        prefix = build_prefix(kind, board, route, puzzle.level, rng) or chain_prefix(
            board, route, puzzle.level, kind, rng
        )
        take(kind, prefix, True)
    assert len(items) == target, puzzle.name
    return items, loose
