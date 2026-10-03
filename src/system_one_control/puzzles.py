"""Puzzles: one board and its level each, and the generator that fills the levels."""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from system_one_control.world import (
    COMPASS,
    DOOR,
    FLOOR,
    GOAL,
    KEY,
    WALL,
    Board,
    Position,
    Rules,
    Solver,
    make_rules,
    next_target,
)

PUZZLE_DIR = Path(__file__).resolve().parents[2] / "puzzles"
MOVE_ALLOWANCE = 2  # a game ends once it has used this many times the fewest moves


@dataclass(frozen=True)
class Puzzle:
    """One starting board, the rules it is played under, and how far the goal is."""

    # The level counts the moves of the rules' step_rules: compass moves, even when a move
    # under these rules is several of them.
    name: str
    description: str
    board: Board
    rules: Rules
    level: int

    @property
    def fewest_moves(self) -> int:
        """The fewest moves that win under the puzzle's own rules."""
        return self.rules.moves_for(self.level)

    @property
    def max_moves(self) -> int:
        return MOVE_ALLOWANCE * self.fewest_moves

    @classmethod
    def load(cls, path: Path) -> Puzzle:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            name=path.stem,
            description=data.get("description", ""),
            board=Board.parse(data["map"]),
            rules=make_rules(data.get("rules", "compass")),
            level=int(data["level"]),
        )


def check_names(paths: list[Path]) -> None:
    """Every puzzle file must have a name of its own, since puzzles are known by file name."""
    names = [path.stem for path in paths]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ValueError(f"puzzle names used more than once: {', '.join(repeated)}")


def load_puzzles(folder: Path = PUZZLE_DIR) -> dict[str, Puzzle]:
    """Every puzzle under a folder (one subfolder per level), easiest first.

    Puzzles are known by their file name, so two files may not share one.
    """
    paths = sorted(folder.rglob("*.yaml"))
    check_names(paths)
    puzzles = sorted((Puzzle.load(path) for path in paths), key=lambda p: (p.level, p.name))
    return {puzzle.name: puzzle for puzzle in puzzles}


SOLVER = Solver(COMPASS)
KEY_FROM_LEVEL = 3  # key, door and goal need at least three moves
MAX_ATTEMPTS = 20000


def greedy_wins(board: Board) -> bool:
    """Whether walking straight at each target, around nothing, reaches the goal in time."""
    # Imported here: the players are built on the prompts, which are built on this module.
    from system_one_control.players.baselines import WallAwareGreedyPlayer

    player = WallAwareGreedyPlayer()
    moves = SOLVER.fewest_moves(board)
    if moves is None:
        return False
    for _ in range(MOVE_ALLOWANCE * moves):
        if COMPASS.is_won(board):
            return True
        move = COMPASS.find_move(board, player.pick(board, COMPASS))
        assert move is not None
        board = COMPASS.apply(board, move)
    return COMPASS.is_won(board)


def has_a_longer_route(board: Board) -> bool:
    """Whether walling off the floor of one shortest route leaves another, longer one."""
    moves = SOLVER.fewest_moves(board)
    if moves is None:
        return False
    walled, current = board, board
    for _ in range(moves):
        move = COMPASS.find_move(current, SOLVER.best_moves(current)[0])
        assert move is not None
        current = COMPASS.apply(current, move)
        if board.at(current.agent) == FLOOR:
            walled = walled.with_cell(current.agent, WALL)
    detour = SOLVER.fewest_moves(walled)
    return detour is not None and detour > moves


def detours(board: Board) -> int | None:
    """The fewest moves away from the next target that any shortest route has to make.

    The next target is the key, then the door, then the goal, as the greedy players see it.
    A move away is one that ends further from it, as the crow walks, than it started. None
    if the goal cannot be reached.
    """
    layer = {board: 0}  # every board first reached at this depth, and its fewest detours
    seen = {board}
    while layer:
        won = [count for current, count in layer.items() if COMPASS.is_won(current)]
        if won:
            return min(won)
        following: dict[Board, int] = {}
        for current, count in layer.items():
            _, target = next_target(current)
            before = _walk(current.agent, target)
            for move in COMPASS.moves(current):
                after = COMPASS.apply(current, move)
                if after in seen:  # reached sooner, or a blocked move
                    continue
                away = count + (_walk(after.agent, target) > before)
                following[after] = min(away, following.get(after, away))
        seen |= following.keys()
        layer = following
    return None


def wall_in_the_way(board: Board) -> bool:
    """Whether a wall blocks one of the first steps that would bring you nearer your target."""
    _, target = next_target(board)
    nearer = [
        move
        for move in COMPASS.moves(board)
        if _walk(board.agent.moved(*COMPASS.STEPS[move.name]), target) < _walk(board.agent, target)
    ]
    return any(COMPASS.apply(board, move) == board for move in nearer)


def _walk(a: Position, b: Position) -> int:
    return abs(a.x - b.x) + abs(a.y - b.y)


@dataclass(frozen=True)
class PuzzleKind:
    """What a puzzle must be, beyond sitting at its level."""

    description: str
    needs_planning: bool = False  # the greedy player with walls cannot win it
    greedy_can_win: bool = False  # the greedy player with walls wins it
    longer_route: bool = False  # a second, longer route to the goal exists
    keyless: bool = False  # no key or door, even at a level that usually has them
    min_detours: int = 0  # moves away from the next target that every shortest route makes
    wall_in_the_way: bool = False  # a wall blocks a first step toward the target

    def accepts(self, board: Board) -> bool:
        if self.keyless and (board.find(KEY) or board.find(DOOR)):
            return False
        if self.min_detours and (detours(board) or 0) < self.min_detours:
            return False
        if self.wall_in_the_way and not wall_in_the_way(board):
            return False
        if self.needs_planning and greedy_wins(board):
            return False
        if self.greedy_can_win and not greedy_wins(board):
            return False
        return not self.longer_route or has_a_longer_route(board)


ANY = PuzzleKind("")
NEEDS_PLANNING = PuzzleKind("that walking straight at the target cannot solve", needs_planning=True)
# Up to level 4, a key leaves no room for a wrong turn: every target is at most two steps away.
NEEDS_PLANNING_KEYLESS = PuzzleKind(
    "without a key, that walking straight at the goal cannot solve",
    needs_planning=True,
    keyless=True,
)
GREEDY_CAN_WIN = PuzzleKind("that walking straight at the target solves", greedy_can_win=True)
LONGER_ROUTE = PuzzleKind(
    "that walking straight at the target cannot solve, with a second, longer route",
    needs_planning=True,
    longer_route=True,
)
# The way to the goal is blocked, as in a puzzle Jev lost at level 2: the goal is up and to
# the left, north is a wall, and it walked north again and again. Any level from 2 can have it.
WALL_IN_THE_WAY = PuzzleKind(
    "without a key, with a wall in the way of walking straight at the goal",
    keyless=True,
    wall_in_the_way=True,
)
TIMES = {1: "once", 2: "twice", 3: "three times", 4: "four times", 5: "five times", 6: "six times"}


def with_detours(least: int) -> PuzzleKind:
    """Puzzles the greedy player cannot win, whose every shortest route turns away `least` times."""
    return PuzzleKind(
        "that walking straight at the target cannot solve, whose every shortest route turns away "
        f"from its target at least {TIMES[least]}",
        needs_planning=True,
        min_detours=least,
    )


def around(least: int) -> PuzzleKind:
    """Puzzles without a key that have to turn away from the goal `least` times to get round.

    Turning away and back costs two moves, so this needs the goal at least two moves nearer
    than the level, as the crow walks: from level 4 up.
    """
    return PuzzleKind(
        f"without a key, whose every shortest route turns away from the goal at least "
        f"{TIMES[least]} to get round a wall",
        keyless=True,
        min_detours=least,
    )


# The levels there are, and how many puzzles each holds, hand-made ones included. Spaced out
# at the top, where every game costs the most calls; thin at the bottom, which is a sanity check.
LEVELS = {1: 5, 2: 5, 3: 10, 4: 10, 5: 10, 6: 10, 8: 10, 10: 10, 12: 10, 15: 10, 20: 10}
# How many of a level's puzzles must be of each kind, strictest first; the rest are ANY.
LEVEL_KINDS: dict[int, dict[PuzzleKind, int]] = {
    2: {WALL_IN_THE_WAY: 3},
    3: {NEEDS_PLANNING_KEYLESS: 1, WALL_IN_THE_WAY: 3},
    4: {NEEDS_PLANNING_KEYLESS: 1, around(1): 3, GREEDY_CAN_WIN: 6},
    5: {NEEDS_PLANNING: 2, around(1): 3, GREEDY_CAN_WIN: 5},
    6: {NEEDS_PLANNING: 2, around(2): 3, GREEDY_CAN_WIN: 5},
    8: {NEEDS_PLANNING: 5, around(2): 3, GREEDY_CAN_WIN: 2},
    10: {LONGER_ROUTE: 5, NEEDS_PLANNING: 5},
    12: {with_detours(2): 10},
    15: {with_detours(4): 5, with_detours(3): 5},
    20: {with_detours(6): 5, with_detours(5): 5},
}
# How thick the outer wall is on every other puzzle of a level, where it is not the usual one
# wall. The extra rings change nothing about the puzzle, only how much map there is to read.
LEVEL_WALLS: dict[int, tuple[int, ...]] = {
    12: (2, 2, 3, 3, 3),
    15: (2, 2, 3, 3, 5),
    20: (2, 2, 3, 3, 5),
}


def thicken(board: Board, walls: int) -> Board:
    """The same board inside more rings of wall, so its outer wall is `walls` thick."""
    extra = walls - 1
    ring = (WALL * (len(board.rows[0]) + 2 * extra),) * extra
    rows = (*ring, *(WALL * extra + row + WALL * extra for row in board.rows), *ring)
    return Board(rows, board.agent.moved(extra, extra), board.holding)


def count_kind(boards: Iterable[Board], kind: PuzzleKind) -> int:
    """How many of these boards a kind accepts."""
    return sum(kind.accepts(board) for board in boards)


def outer_wall(board: Board) -> int:
    """How many rings of solid wall surround the map."""
    rings = 0
    while (
        all(set(row[rings]) == {WALL} and set(row[-1 - rings]) == {WALL} for row in board.rows)
        and set(board.rows[rings]) == {WALL}
        and set(board.rows[-1 - rings]) == {WALL}
    ):
        rings += 1
    return rings


def thick_wall_count(boards: Iterable[Board]) -> int:
    """How many of these boards are walled in more thickly than the usual one ring."""
    return sum(outer_wall(board) > 1 for board in boards)


@dataclass(frozen=True)
class Draft:
    """A generated puzzle, not yet written to its file."""

    style: str
    board: Board
    kind: PuzzleKind = ANY
    walls: int = 1  # how thick the outer wall is


class PuzzleGenerator:
    """Random rooms and mazes whose goal is exactly `level` moves away."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def drafts(
        self, level: int, count: int, avoid: set[str] | None = None, kind: PuzzleKind = ANY
    ) -> list[Draft]:
        seen = set(avoid or ())
        found: list[Draft] = []
        if count == 0:
            return found
        for _ in range(MAX_ATTEMPTS):
            draft = self._attempt(level, with_key=level >= KEY_FROM_LEVEL and not kind.keyless)
            if draft and draft.board.draw() not in seen and kind.accepts(draft.board):
                seen.add(draft.board.draw())
                found.append(Draft(draft.style, draft.board, kind))
                if len(found) == count:
                    return found
        raise RuntimeError(f"could not generate {count} puzzles at level {level}")

    def _attempt(self, level: int, with_key: bool) -> Draft | None:
        style = "maze" if self._rng.random() < 0.4 else "room"
        rows = self._maze() if style == "maze" else self._room()
        floor = _cells(rows, FLOOR)
        if len(floor) < 3:
            return None

        goal = self._rng.choice(floor)
        _set(rows, goal, GOAL)
        if with_key:
            openings = [p for p in _neighbours(goal) if _get(rows, p) == FLOOR]
            if not openings:
                return None
            door = self._rng.choice(openings)
            for position in _neighbours(goal):
                if position != door:
                    _set(rows, position, WALL)
            _set(rows, door, DOOR)
            floor = _cells(rows, FLOOR)
            if len(floor) < 2:
                return None
            _set(rows, self._rng.choice(floor), KEY)

        drawn = tuple("".join(row) for row in rows)
        starts = [
            board
            for position in _cells(rows, FLOOR)
            if SOLVER.fewest_moves(board := Board(drawn, position)) == level
        ]
        return Draft(style, self._rng.choice(starts)) if starts else None

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
        rows = [[WALL] * width for _ in range(height)]
        stack = [Position(1, 1)]
        _set(rows, stack[0], FLOOR)
        while stack:
            here = stack[-1]
            ahead = [
                (dx, dy)
                for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))
                if 0 < here.x + dx < width - 1
                and 0 < here.y + dy < height - 1
                and _get(rows, here.moved(dx, dy)) == WALL
            ]
            if not ahead:
                stack.pop()
                continue
            dx, dy = self._rng.choice(ahead)
            _set(rows, here.moved(dx // 2, dy // 2), FLOOR)
            _set(rows, here.moved(dx, dy), FLOOR)
            stack.append(here.moved(dx, dy))
        return rows


def _cells(rows: list[list[str]], symbol: str) -> list[Position]:
    return [
        Position(x, y) for y, row in enumerate(rows) for x, cell in enumerate(row) if cell == symbol
    ]


def _neighbours(position: Position) -> list[Position]:
    return [position.moved(dx, dy) for dx, dy in COMPASS.STEPS.values()]


def _get(rows: list[list[str]], position: Position) -> str:
    return rows[position.y][position.x]


def _set(rows: list[list[str]], position: Position, symbol: str) -> None:
    rows[position.y][position.x] = symbol


def write_level(root: Path, *, level: int, target: int, seed: int) -> list[Path]:
    """Replace a level's generated puzzles so it holds `target` puzzles, hand-made ones kept.

    Hand-made puzzles count toward the kinds the level asks for, when they qualify.
    A level asked for fewer puzzles than its kinds add up to fills them strictest first.
    The old generated puzzles are only deleted once the new ones are ready.
    """
    folder = root / f"level-{level:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    hand_made = [
        Puzzle.load(path).board
        for path in folder.glob("*.yaml")
        if not path.name.startswith("gen-")
    ]

    kinds = dict(LEVEL_KINDS.get(level, {}))
    for board in hand_made:
        kind = next((k for k, n in kinds.items() if n and k.accepts(board)), None)
        if kind:
            kinds[kind] -= 1

    room = max(target - len(hand_made), 0)
    wanted: dict[PuzzleKind, int] = {}
    for kind, count in kinds.items():  # strictest first, as far as there is room
        wanted[kind] = min(count, room)
        room -= wanted[kind]
    wanted[ANY] = room

    generator = PuzzleGenerator(seed=seed * 1000 + level)
    seen = {board.draw() for board in hand_made}
    drafts: list[Draft] = []
    for kind, count in wanted.items():
        drafts += generator.drafts(level, count, seen, kind)
        seen |= {draft.board.draw() for draft in drafts}
    for index, walls in zip(range(1, len(drafts), 2), LEVEL_WALLS.get(level, ()), strict=False):
        drafts[index] = replace(
            drafts[index], board=thicken(drafts[index].board, walls), walls=walls
        )

    for old in folder.glob("gen-*.yaml"):
        old.unlink()
    written = []
    for number, draft in enumerate(drafts, start=1):
        board = draft.board
        size = f"{len(board.rows[0])}x{len(board.rows)}"
        label = f" {draft.kind.description}" if draft.kind.description else ""
        if draft.walls > 1:
            label += f", inside an outer wall {draft.walls} thick"
        lines = [
            f"description: A generated {size} {draft.style}{label}.",
            f"level: {level}",
            "map: |",
            *(f"  {row}" for row in board.draw().splitlines()),
        ]
        path = folder / f"gen-{level:02d}-{number:02d}.yaml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        written.append(path)
    return written
