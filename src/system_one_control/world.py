"""The world of a puzzle: the map, what a move does to it, and the shortest way to the goal."""

from __future__ import annotations

import itertools
import math
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import ClassVar

WALL, FLOOR, AGENT, GOAL, KEY, DOOR = "#", ".", "A", "G", "K", "D"
SYMBOL_NAMES = {
    WALL: "wall",
    FLOOR: "floor",
    AGENT: "you",
    GOAL: "goal",
    KEY: "key",
    DOOR: "locked door",
}


@dataclass(frozen=True)
class Position:
    x: int
    y: int

    def moved(self, dx: int, dy: int) -> Position:
        return Position(self.x + dx, self.y + dy)

    def __str__(self) -> str:
        return f"({self.x}, {self.y})"


@dataclass(frozen=True)
class Board:
    """The map without the agent, where the agent stands, and what it carries."""

    rows: tuple[str, ...]
    agent: Position
    holding: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> Board:
        rows = [line.strip() for line in text.strip().splitlines()]
        if len({len(row) for row in rows}) != 1:
            raise ValueError("every row of a map must be the same width")
        unknown = set("".join(rows)) - SYMBOL_NAMES.keys()
        if unknown:
            raise ValueError(f"unknown map symbols: {sorted(unknown)}")
        agents = [
            Position(x, y)
            for y, row in enumerate(rows)
            for x, cell in enumerate(row)
            if cell == AGENT
        ]
        if len(agents) != 1:
            raise ValueError(f"a map needs exactly one {AGENT}, found {len(agents)}")
        agent = agents[0]
        rows[agent.y] = rows[agent.y].replace(AGENT, FLOOR)
        return cls(tuple(rows), agent)

    def at(self, position: Position) -> str:
        if 0 <= position.y < len(self.rows) and 0 <= position.x < len(self.rows[position.y]):
            return self.rows[position.y][position.x]
        return WALL

    def find(self, symbol: str) -> tuple[Position, ...]:
        return tuple(
            Position(x, y)
            for y, row in enumerate(self.rows)
            for x, cell in enumerate(row)
            if cell == symbol
        )

    def with_cell(self, position: Position, symbol: str) -> Board:
        rows = list(self.rows)
        row = rows[position.y]
        rows[position.y] = row[: position.x] + symbol + row[position.x + 1 :]
        return replace(self, rows=tuple(rows))

    def with_agent(self, position: Position) -> Board:
        return replace(self, agent=position)

    def pick_up(self, item: str) -> Board:
        return replace(self, holding=(*self.holding, item))

    def draw(self) -> str:
        return "\n".join(self.with_cell(self.agent, AGENT).rows)


@dataclass(frozen=True)
class Move:
    name: str
    description: str


class Rules(ABC):
    """How a board changes, and how to put that into words. Swap it to change the game."""

    name: ClassVar[str]
    description: ClassVar[str]

    @abstractmethod
    def moves(self, board: Board) -> tuple[Move, ...]: ...

    @abstractmethod
    def apply(self, board: Board, move: Move) -> Board: ...

    @abstractmethod
    def is_won(self, board: Board) -> bool: ...

    @abstractmethod
    def describe_outcome(self, before: Board, after: Board) -> str:
        """What a move did, such as "you move to (2, 1) and pick up the key"."""

    @abstractmethod
    def describe_surroundings(self, board: Board) -> str:
        """What is next to the player, and where the things that matter are."""

    @abstractmethod
    def describe_next_target(self, board: Board) -> str:
        """The next thing to reach on the way to winning, such as "the key K at (7, 2)"."""

    def subgoal_question(self, board: Board) -> str:
        """The question that names the next target, asked instead of the plain one."""
        return (
            f"Your next target is {self.describe_next_target(board)}. "
            "Which move is the first step of the shortest path to it?"
        )

    def passes(self, board: Board, move: Move) -> tuple[Board, ...]:
        """Every board the move passes through, ending with the one it ends on."""
        return (self.apply(board, move),)

    def find_move(self, board: Board, name: str | None) -> Move | None:
        return next((move for move in self.moves(board) if move.name == name), None)

    def step_rules(self) -> Rules:
        """The rules a level is counted in: these ones, unless a move here is several of theirs."""
        return self

    def moves_for(self, level: int) -> int:
        """The fewest moves here that win a puzzle this many of step_rules' moves away."""
        return level


class CompassRules(Rules):
    name = "compass"
    description = (
        "You move one cell per turn: north (up), south (down), east (right) or west (left). "
        "Walls (#) block you, and walking into one wastes the move. Stepping onto the key (K) "
        "picks it up. A locked door (D) opens when you walk into it carrying the key, and you "
        "step through; without the key it blocks you like a wall. Reaching the goal (G) wins."
    )
    STEPS: ClassVar[dict[str, tuple[int, int]]] = {
        "north": (0, -1),
        "south": (0, 1),
        "east": (1, 0),
        "west": (-1, 0),
    }
    MOVES: ClassVar[tuple[Move, ...]] = (
        Move("north", "move north (up)"),
        Move("south", "move south (down)"),
        Move("east", "move east (right)"),
        Move("west", "move west (left)"),
    )
    NEIGHBOURS: ClassVar[dict[str, str]] = {
        WALL: "a wall",
        FLOOR: "open floor",
        GOAL: "the goal",
        KEY: "the key",
        DOOR: "the locked door",
    }

    def moves(self, board: Board) -> tuple[Move, ...]:
        return self.MOVES

    def apply(self, board: Board, move: Move) -> Board:
        target = board.agent.moved(*self.STEPS[move.name])
        cell = board.at(target)
        if cell == WALL:
            return board
        if cell == DOOR:
            if "key" not in board.holding:
                return board
            board = board.with_cell(target, FLOOR)
        if cell == KEY:
            board = board.with_cell(target, FLOOR).pick_up("key")
        return board.with_agent(target)

    def is_won(self, board: Board) -> bool:
        return board.at(board.agent) == GOAL

    def describe_outcome(self, before: Board, after: Board) -> str:
        if after == before:
            return f"blocked, you stay at {before.agent}"
        return " and ".join([f"you move to {after.agent}", *self.events(before, after)])

    def events(self, before: Board, after: Board) -> list[str]:
        """What happened on the way, besides moving: the key, the door, the goal."""
        events = []
        if len(after.holding) > len(before.holding):
            events.append(f"pick up the {after.holding[-1]}")
        if len(after.find(DOOR)) < len(before.find(DOOR)):
            events.append("unlock the door")
        if self.is_won(after):
            events.append("reach the goal")
        return events

    def describe_surroundings(self, board: Board) -> str:
        """One line on the four cells next to you, one on where the goal, key and door are."""
        around = " ".join(
            f"{name.capitalize()} of you is {self.NEIGHBOURS[board.at(board.agent.moved(*step))]}."
            for name, step in self.STEPS.items()
        )
        relative = " ".join(
            f"The {SYMBOL_NAMES[symbol]} is "
            f"{self._offset(position.x - board.agent.x, position.y - board.agent.y)} of you."
            for symbol in (GOAL, KEY, DOOR)
            for position in board.find(symbol)
        )
        return f"{around}\n{relative}"

    def describe_next_target(self, board: Board) -> str:
        symbol, position = next_target(board)
        return f"the {SYMBOL_NAMES[symbol]} {symbol} at {position}"

    @staticmethod
    def _offset(dx: int, dy: int) -> str:
        parts = []
        if dx:
            parts.append(f"{abs(dx)} {'east' if dx > 0 else 'west'}")
        if dy:
            parts.append(f"{abs(dy)} {'south' if dy > 0 else 'north'}")
        return " and ".join(parts) or "at the same place as you"


def sequence_description(count: str) -> str:
    return (
        f"Each turn you choose a path of {count} steps, taken one after another. Each step goes "
        "one cell: north (up), south (down), east (right) or west (left). Walls (#) block you, "
        "and walking into one wastes that step. Stepping onto the key (K) picks it up. A locked "
        "door (D) opens when you walk into it carrying the key, and you step through; without "
        "the key it blocks you like a wall. Reaching the goal (G) wins at once, and any steps "
        "left are not taken."
    )


class SequenceRules(Rules):
    """Each move is `length` compass moves, chosen together; with `shortest`, also fewer."""

    length: ClassVar[int]  # the most compass moves in a move
    shortest: ClassVar[int | None] = None  # the fewest, where a move may be shorter than length

    def __init__(self) -> None:
        self.step = CompassRules()
        self._steps: dict[str, tuple[Move, ...]] = {}
        moves = []
        counts = range(self.shortest or self.length, self.length + 1)
        for steps in itertools.chain.from_iterable(
            itertools.product(CompassRules.MOVES, repeat=count) for count in counts
        ):
            name = ",".join(step.name for step in steps)
            self._steps[name] = steps
            ways = ", then ".join(step.description.removeprefix("move ") for step in steps)
            moves.append(Move(name, f"move {ways}"))
        self._moves = tuple(moves)

    def moves(self, board: Board) -> tuple[Move, ...]:
        return self._moves

    def apply(self, board: Board, move: Move) -> Board:
        return self.passes(board, move)[-1]

    def passes(self, board: Board, move: Move) -> tuple[Board, ...]:
        # Every sequence is offered, blocked or not, as the compass rules offer every direction,
        # and a move that reaches the goal stops there.
        boards = []
        for step in self._steps[move.name]:
            board = self.step.apply(board, step)
            boards.append(board)
            if self.is_won(board):
                break
        return tuple(boards)

    def is_won(self, board: Board) -> bool:
        return self.step.is_won(board)

    def describe_outcome(self, before: Board, after: Board) -> str:
        if after.agent == before.agent:
            where = f"you end where you started, at {before.agent}"
        else:
            where = f"you end at {after.agent}"
        return " and ".join([where, *self.step.events(before, after)])

    def describe_surroundings(self, board: Board) -> str:
        return self.step.describe_surroundings(board)

    def describe_next_target(self, board: Board) -> str:
        return self.step.describe_next_target(board)

    def subgoal_question(self, board: Board) -> str:
        # Not "the first step", since a move is several; and the way to the goal, not to the
        # target alone, since a move that reaches the key with steps to spare should spend them
        # heading on, and the solver scores it that way. Where a move may be shorter than
        # `length`, "the shortest path" would be wrong too: a single step does start it, yet
        # wastes a turn. So those rules ask for the way that takes the fewest turns.
        target = self.describe_next_target(board)
        onward = "it" if next_target(board)[0] == GOAL else "the goal through it"
        if self.shortest is None:
            return f"Your next target is {target}. Which move starts the shortest path to {onward}?"
        return (
            f"Your next target is {target}. "
            f"Which move starts the way to {onward} that takes the fewest turns?"
        )

    def step_rules(self) -> Rules:
        return self.step

    def moves_for(self, level: int) -> int:
        # A path of `level` compass moves splits into this many sequences, the last cut short at
        # the goal, and no sequence brings the goal more than `length` compass moves nearer.
        return math.ceil(level / self.length)


class TwoMoveRules(SequenceRules):
    name = "two-moves"
    description = sequence_description("two")
    length = 2


class ThreeMoveRules(SequenceRules):
    name = "three-moves"
    description = sequence_description("three")
    length = 3


class UpToTwoMoveRules(SequenceRules):
    name = "up-to-two-moves"
    description = sequence_description("one or two")
    length = 2
    shortest = 1


class UpToThreeMoveRules(SequenceRules):
    name = "up-to-three-moves"
    description = sequence_description("one, two or three")
    length = 3
    shortest = 1


def next_target(board: Board) -> tuple[str, Position]:
    """The key while it lies on the map, then the locked door, then the goal."""
    for symbol in (KEY, DOOR, GOAL):
        found = board.find(symbol)
        if found:
            return symbol, found[0]
    raise ValueError("the map has no goal")


RULES: dict[str, type[Rules]] = {
    rules.name: rules
    for rules in (
        CompassRules,
        TwoMoveRules,
        ThreeMoveRules,
        UpToTwoMoveRules,
        UpToThreeMoveRules,
    )
}


def make_rules(name: str) -> Rules:
    if name not in RULES:
        raise ValueError(f"unknown rules {name!r}; known: {', '.join(RULES)}")
    return RULES[name]()


class Solver:
    """Exact shortest paths by breadth-first search over boards."""

    def __init__(self, rules: Rules) -> None:
        self.rules = rules

    def moves_to_goal(self, board: Board) -> int | None:
        """Fewest moves to win from this board, or None if the goal cannot be reached."""
        frontier = deque([(board, 0)])
        seen = {board}
        while frontier:
            current, moves = frontier.popleft()
            if self.rules.is_won(current):
                return moves
            for move in self.rules.moves(current):
                after = self.rules.apply(current, move)
                if after not in seen:
                    seen.add(after)
                    frontier.append((after, moves + 1))
        return None

    def distances(self, board: Board) -> dict[Board, int]:
        """The fewest moves to win from every board reachable from this one that can win.

        One search forward to map every move, then one back from the winning boards: much
        cheaper than a search per board when there are many moves, as under sequence rules.
        """
        came_from: dict[Board, list[Board]] = {board: []}
        frontier = deque([board])
        while frontier:
            current = frontier.popleft()
            if self.rules.is_won(current):
                continue  # the game ends here
            for move in self.rules.moves(current):
                after = self.rules.apply(current, move)
                if after not in came_from:
                    came_from[after] = []
                    frontier.append(after)
                came_from[after].append(current)
        found = {b: 0 for b in came_from if self.rules.is_won(b)}
        back = deque(found)
        while back:
            current = back.popleft()
            for before in came_from[current]:
                if before not in found:
                    found[before] = found[current] + 1
                    back.append(before)
        return found

    def best_moves(
        self, board: Board, distances: Mapping[Board, int] | None = None
    ) -> tuple[str, ...]:
        """Every move that starts a shortest path, ties included.

        `distances` may come from any earlier board this one was reached from, since the
        distances from a board cover every board reachable from it; by default they are worked
        out from this board.
        """
        if distances is None:
            distances = self.distances(board)
        distance = distances.get(board)
        if not distance:
            return ()
        return tuple(
            move.name
            for move in self.rules.moves(board)
            if distances.get(self.rules.apply(board, move)) == distance - 1
        )
