from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from system_one_control.board import DOOR, FLOOR, GOAL, KEY, WALL, Board, Position
from system_one_control.rules import CompassRules
from system_one_control.solver import Solver

KEY_FROM_LEVEL = 3  # key, door and goal need at least three moves
MAX_ATTEMPTS = 5000
STEPS = ((0, -1), (0, 1), (1, 0), (-1, 0))


@dataclass(frozen=True)
class Puzzle:
    style: str
    board: Board


class PuzzleGenerator:
    """Random rooms and mazes whose goal is exactly `level` moves away."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)
        self.solver = Solver(CompassRules())

    def puzzle(self, level: int) -> Puzzle:
        return self.puzzles(level, 1)[0]

    def puzzles(self, level: int, count: int, avoid: set[str] | None = None) -> list[Puzzle]:
        seen = set(avoid or ())
        found: list[Puzzle] = []
        for _ in range(MAX_ATTEMPTS):
            puzzle = self._attempt(level)
            if puzzle and puzzle.board.draw() not in seen:
                seen.add(puzzle.board.draw())
                found.append(puzzle)
                if len(found) == count:
                    return found
        raise RuntimeError(f"could not generate {count} puzzles at level {level}")

    def _attempt(self, level: int) -> Puzzle | None:
        style = "maze" if self._rng.random() < 0.4 else "room"
        grid = self._maze() if style == "maze" else self._room()
        floor = _cells(grid, FLOOR)
        if len(floor) < 3:
            return None

        goal = self._rng.choice(floor)
        _set(grid, goal, GOAL)
        if level >= KEY_FROM_LEVEL:
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
            if self.solver.distance(board := Board(rows, position)) == level
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
    """Replace a level's generated puzzles so it holds `target` puzzles, hand-made ones kept."""
    from system_one_control.scenario import Scenario

    folder = root / f"level-{level:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("gen-*.yaml"):
        old.unlink()
    hand_made = [Scenario.load(path).board.draw() for path in folder.glob("*.yaml")]

    generator = PuzzleGenerator(seed=seed * 1000 + level)
    written = []
    needed = max(target - len(hand_made), 0)
    for number, puzzle in enumerate(generator.puzzles(level, needed, set(hand_made)), start=1):
        board = puzzle.board
        size = f"{len(board.rows[0])}x{len(board.rows)}"
        lines = [
            f"description: A generated {size} {puzzle.style}.",
            f"moves_to_goal: {level}",
            "map: |",
            *(f"  {row}" for row in board.draw().splitlines()),
        ]
        path = folder / f"gen-{level:02d}-{number:02d}.yaml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(path)
    return written
