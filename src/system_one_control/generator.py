from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from system_one_control.board import DOOR, FLOOR, GOAL, KEY, WALL, Board, Position
from system_one_control.players import WallAwareGreedyPlayer
from system_one_control.rules import CompassRules
from system_one_control.scenario import MOVE_ALLOWANCE, Scenario
from system_one_control.solver import Solver

KEY_FROM_LEVEL = 3  # key, door and goal need at least three moves
MAX_ATTEMPTS = 20000
STEPS = ((0, -1), (0, 1), (1, 0), (-1, 0))
RULES = CompassRules()
SOLVER = Solver(RULES)


def greedy_wins(board: Board) -> bool:
    """Whether walking straight at each target, around nothing, reaches the goal in time."""
    player = WallAwareGreedyPlayer()
    distance = SOLVER.distance(board)
    if distance is None:
        return False
    for _ in range(MOVE_ALLOWANCE * distance):
        if RULES.is_won(board):
            return True
        move = RULES.find_move(board, player.pick(board, RULES))
        assert move is not None
        board = RULES.apply(board, move)
    return RULES.is_won(board)


def has_a_longer_route(board: Board) -> bool:
    """Whether walling off the floor of one shortest route leaves another, longer one."""
    distance = SOLVER.distance(board)
    if distance is None:
        return False
    walled, current = board, board
    for _ in range(distance):
        move = RULES.find_move(current, SOLVER.best_moves(current)[0])
        assert move is not None
        current = RULES.apply(current, move)
        if board.at(current.agent) == FLOOR:
            walled = walled.with_cell(current.agent, WALL)
    detour = SOLVER.distance(walled)
    return detour is not None and detour > distance


@dataclass(frozen=True)
class Kind:
    """What a puzzle must be, beyond sitting at its level."""

    description: str
    needs_planning: bool = False  # the greedy player with walls cannot win it
    greedy_can_win: bool = False  # the greedy player with walls wins it
    longer_route: bool = False  # a second, longer route to the goal exists
    keyless: bool = False  # no key or door, even at a level that usually has them

    def accepts(self, board: Board) -> bool:
        if self.needs_planning and greedy_wins(board):
            return False
        if self.greedy_can_win and not greedy_wins(board):
            return False
        return not self.longer_route or has_a_longer_route(board)


ANY = Kind("")
NEEDS_PLANNING = Kind("that walking straight at the target cannot solve", needs_planning=True)
# Up to level 4, a key leaves no room for a wrong turn: every target is at most two steps away.
NEEDS_PLANNING_KEYLESS = Kind(
    "without a key, that walking straight at the goal cannot solve",
    needs_planning=True,
    keyless=True,
)
GREEDY_CAN_WIN = Kind("that walking straight at the target solves", greedy_can_win=True)
LONGER_ROUTE = Kind(
    "that walking straight at the target cannot solve, with a second, longer route",
    needs_planning=True,
    longer_route=True,
)
# How many of a level's puzzles must be of each kind, strictest first; the rest are ANY.
LEVEL_KINDS: dict[int, dict[Kind, int]] = {
    4: {NEEDS_PLANNING_KEYLESS: 1, GREEDY_CAN_WIN: 9},
    5: {NEEDS_PLANNING: 2, GREEDY_CAN_WIN: 8},
    6: {NEEDS_PLANNING: 2, GREEDY_CAN_WIN: 8},
    7: {NEEDS_PLANNING: 3, GREEDY_CAN_WIN: 7},
    8: {NEEDS_PLANNING: 5, GREEDY_CAN_WIN: 5},
    9: {NEEDS_PLANNING: 5, GREEDY_CAN_WIN: 5},
    10: {LONGER_ROUTE: 5, NEEDS_PLANNING: 5},
}


@dataclass(frozen=True)
class Puzzle:
    style: str
    board: Board
    kind: Kind = ANY


class PuzzleGenerator:
    """Random rooms and mazes whose goal is exactly `level` moves away."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def puzzle(self, level: int, kind: Kind = ANY) -> Puzzle:
        return self.puzzles(level, 1, kind=kind)[0]

    def puzzles(
        self, level: int, count: int, avoid: set[str] | None = None, kind: Kind = ANY
    ) -> list[Puzzle]:
        seen = set(avoid or ())
        found: list[Puzzle] = []
        if count == 0:
            return found
        for _ in range(MAX_ATTEMPTS):
            puzzle = self._attempt(level, with_key=level >= KEY_FROM_LEVEL and not kind.keyless)
            if puzzle and puzzle.board.draw() not in seen and kind.accepts(puzzle.board):
                seen.add(puzzle.board.draw())
                found.append(Puzzle(puzzle.style, puzzle.board, kind))
                if len(found) == count:
                    return found
        raise RuntimeError(f"could not generate {count} puzzles at level {level}")

    def _attempt(self, level: int, with_key: bool) -> Puzzle | None:
        style = "maze" if self._rng.random() < 0.4 else "room"
        grid = self._maze() if style == "maze" else self._room()
        floor = _cells(grid, FLOOR)
        if len(floor) < 3:
            return None

        goal = self._rng.choice(floor)
        _set(grid, goal, GOAL)
        if with_key:
            openings = [p for p in _neighbours(goal) if _get(grid, p) == FLOOR]
            if not openings:
                return None
            door = self._rng.choice(openings)
            for position in _neighbours(goal):
                if position != door:
                    _set(grid, position, WALL)
            _set(grid, door, DOOR)
            floor = _cells(grid, FLOOR)
            if len(floor) < 2:
                return None
            _set(grid, self._rng.choice(floor), KEY)

        rows = tuple("".join(row) for row in grid)
        starts = [
            board
            for position in _cells(grid, FLOOR)
            if SOLVER.distance(board := Board(rows, position)) == level
        ]
        return Puzzle(style, self._rng.choice(starts)) if starts else None

    def _room(self) -> list[list[str]]:
        width, height = self._rng.randint(5, 13), self._rng.randint(4, 9)
        density = self._rng.uniform(0.0, 0.3)
        return [
            [
                WALL
                if x in (0, width - 1) or y in (0, height - 1) or self._rng.random() < density
                else FLOOR
                for x in range(width)
            ]
            for y in range(height)
        ]

    def _maze(self) -> list[list[str]]:
        width, height = self._rng.choice((7, 9, 11, 15, 21)), self._rng.choice((5, 7, 9, 13))
        grid = [[WALL] * width for _ in range(height)]
        stack = [Position(1, 1)]
        _set(grid, stack[0], FLOOR)
        while stack:
            here = stack[-1]
            ahead = [
                (dx, dy)
                for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))
                if 0 < here.x + dx < width - 1
                and 0 < here.y + dy < height - 1
                and _get(grid, here.moved(dx, dy)) == WALL
            ]
            if not ahead:
                stack.pop()
                continue
            dx, dy = self._rng.choice(ahead)
            _set(grid, here.moved(dx // 2, dy // 2), FLOOR)
            _set(grid, here.moved(dx, dy), FLOOR)
            stack.append(here.moved(dx, dy))
        return grid


def _cells(grid: list[list[str]], symbol: str) -> list[Position]:
    return [
        Position(x, y) for y, row in enumerate(grid) for x, cell in enumerate(row) if cell == symbol
    ]


def _neighbours(position: Position) -> list[Position]:
    return [position.moved(dx, dy) for dx, dy in STEPS]


def _get(grid: list[list[str]], position: Position) -> str:
    return grid[position.y][position.x]


def _set(grid: list[list[str]], position: Position, symbol: str) -> None:
    grid[position.y][position.x] = symbol


def write_level(root: Path, *, level: int, target: int, seed: int) -> list[Path]:
    """Replace a level's generated puzzles so it holds `target` puzzles, hand-made ones kept.

    Hand-made puzzles count toward the kinds the level asks for, when they qualify.
    A level asked for fewer puzzles than its kinds add up to fills them strictest first.
    """
    folder = root / f"level-{level:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("gen-*.yaml"):
        old.unlink()
    hand_made = [Scenario.load(path).board for path in folder.glob("*.yaml")]

    kinds = dict(LEVEL_KINDS.get(level, {}))
    for board in hand_made:
        kind = next((k for k, n in kinds.items() if n and k.accepts(board)), None)
        if kind:
            kinds[kind] -= 1

    room = max(target - len(hand_made), 0)
    wanted: dict[Kind, int] = {}
    for kind, count in kinds.items():  # strictest first, as far as there is room
        wanted[kind] = min(count, room)
        room -= wanted[kind]
    wanted[ANY] = room

    generator = PuzzleGenerator(seed=seed * 1000 + level)
    seen = {board.draw() for board in hand_made}
    puzzles: list[Puzzle] = []
    for kind, count in wanted.items():
        puzzles += generator.puzzles(level, count, seen, kind)
        seen |= {puzzle.board.draw() for puzzle in puzzles}

    written = []
    for number, puzzle in enumerate(puzzles, start=1):
        board = puzzle.board
        size = f"{len(board.rows[0])}x{len(board.rows)}"
        label = f" {puzzle.kind.description}" if puzzle.kind.description else ""
        lines = [
            f"description: A generated {size} {puzzle.style}{label}.",
            f"moves_to_goal: {level}",
            "map: |",
            *(f"  {row}" for row in board.draw().splitlines()),
        ]
        path = folder / f"gen-{level:02d}-{number:02d}.yaml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(path)
    return written
