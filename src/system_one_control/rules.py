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
            board = board.with_cell(target, FLOOR).carrying("key")
        return board.with_agent(target)

    def is_won(self, board: Board) -> bool:
        return board.at(board.agent) == GOAL


RULES: dict[str, type[Rules]] = {CompassRules.name: CompassRules}


def make_rules(name: str) -> Rules:
    if name not in RULES:
        raise ValueError(f"unknown rules {name!r}; known: {', '.join(RULES)}")
    return RULES[name]()
