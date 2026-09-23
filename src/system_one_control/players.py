from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

from system_one_control.board import DOOR, GOAL, KEY, Board, Position
from system_one_control.prompt import Request
from system_one_control.rules import CompassRules, Move, Rules
from system_one_control.solver import Solver


@dataclass(frozen=True)
class Turn:
    """One decision. Model players must read only `request`; the board is for baselines."""

    board: Board
    rules: Rules
    request: Request


@dataclass(frozen=True)
class Choice:
    move: str | None
    probabilities: dict[str, float] = field(default_factory=dict)
    error: str | None = None


class Player(ABC):
    name: ClassVar[str]

    @abstractmethod
    def choose(self, turn: Turn) -> Choice: ...


class RandomPlayer(Player):
    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def choose(self, turn: Turn) -> Choice:
        return Choice(self._rng.choice(turn.request.options).move)


class SolverPlayer(Player):
    """Plays perfectly by searching the real board."""

    name = "solver"

    def choose(self, turn: Turn) -> Choice:
        best = Solver(turn.rules).best_moves(turn.board)
        if not best:
            return Choice(None, error="the goal cannot be reached")
        return Choice(best[0], {move: 1 / len(best) for move in best})


class GreedyPlayer(Player):
    """Steps straight toward the key, then the door, then the goal, and never plans.

    It shows what heading for the next target is worth on its own. It ignores walls, and it
    breaks ties by the rules' order of moves, so the option shuffle never changes its game.
    Compass rules only.
    """

    name = "greedy"
    avoids_blocked_moves = False

    def choose(self, turn: Turn) -> Choice:
        return Choice(self.pick(turn.board, turn.rules))

    def pick(self, board: Board, rules: Rules) -> str:
        moves = rules.moves(board)
        if self.avoids_blocked_moves:
            moves = tuple(m for m in moves if rules.apply(board, m) != board) or moves
        target = next_target(board)

        def distance_after(move: Move) -> int:
            there = board.agent.moved(*CompassRules.STEPS[move.name])
            return abs(there.x - target.x) + abs(there.y - target.y)

        return min(moves, key=distance_after).name


class WallAwareGreedyPlayer(GreedyPlayer):
    """Greedy, but never picks a move that would leave it where it stands."""

    name = "greedy-walls"
    avoids_blocked_moves = True


def next_target(board: Board) -> Position:
    """The key while it lies on the map, then the locked door, then the goal."""
    for symbol in (KEY, DOOR, GOAL):
        found = board.find(symbol)
        if found:
            return found[0]
    raise ValueError("the map has no goal")


def _jev() -> Player:
    from system_one_control.jev import JevPlayer

    return JevPlayer()


@dataclass(frozen=True)
class PlayerEntry:
    build: Callable[[], Player]
    paid: bool = False


PLAYERS: dict[str, PlayerEntry] = {
    "random": PlayerEntry(RandomPlayer),
    "greedy": PlayerEntry(GreedyPlayer),
    "greedy-walls": PlayerEntry(WallAwareGreedyPlayer),
    "solver": PlayerEntry(SolverPlayer),
    "jev": PlayerEntry(_jev, paid=True),
}


def make_player(name: str) -> Player:
    if name not in PLAYERS:
        raise ValueError(f"unknown player {name!r}; known: {', '.join(PLAYERS)}")
    return PLAYERS[name].build()
