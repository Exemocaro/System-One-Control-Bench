from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from system_one_control.board import DOOR, FLOOR, GOAL, KEY, WALL, Board


@dataclass(frozen=True)
class Move:
    name: str
    description: str


class Rules(ABC):
    """How a board changes. Swap this class to change the game; prompts adapt to it."""

    name: ClassVar[str]
    description: ClassVar[str]

    @abstractmethod
    def moves(self, board: Board) -> tuple[Move, ...]: ...

    @abstractmethod
    def apply(self, board: Board, move: Move) -> Board: ...

    @abstractmethod
    def is_won(self, board: Board) -> bool: ...

    def facts(self, board: Board) -> dict[str, str]:
        """Extra placeholders these rules offer to prompts, beyond the board's own."""
        return {}

    def find_move(self, board: Board, name: str | None) -> Move | None:
        return next((move for move in self.moves(board) if move.name == name), None)


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

    def facts(self, board: Board) -> dict[str, str]:
        around = " ".join(
            f"{name.capitalize()} of you is {self.NEIGHBOURS[board.at(board.agent.moved(*step))]}."
            for name, step in self.STEPS.items()
        )
        relative = " ".join(
            f"The {thing} is {self._offset(position.x - board.agent.x, position.y - board.agent.y)}"
            " of you."
            for symbol, thing in ((GOAL, "goal"), (KEY, "key"), (DOOR, "locked door"))
            for position in board.find(symbol)
        )
        return {"around": around, "relative": relative}

    @staticmethod
    def _offset(dx: int, dy: int) -> str:
        parts = []
        if dx:
            parts.append(f"{abs(dx)} {'east' if dx > 0 else 'west'}")
        if dy:
            parts.append(f"{abs(dy)} {'south' if dy > 0 else 'north'}")
        return " and ".join(parts) or "at the same place as you"

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
            board = board.with_cell(target, FLOOR).carrying("key")
        return board.with_agent(target)

    def is_won(self, board: Board) -> bool:
        return board.at(board.agent) == GOAL


RULES: dict[str, type[Rules]] = {CompassRules.name: CompassRules}


def make_rules(name: str) -> Rules:
    if name not in RULES:
        raise ValueError(f"unknown rules {name!r}; known: {', '.join(RULES)}")
    return RULES[name]()
