from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

from system_one_control.board import Board
from system_one_control.prompt import Request
from system_one_control.rules import Rules
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


def _jev() -> Player:
    from system_one_control.jev import JevPlayer

    return JevPlayer()


@dataclass(frozen=True)
class PlayerEntry:
    build: Callable[[], Player]
    paid: bool = False


PLAYERS: dict[str, PlayerEntry] = {
    "random": PlayerEntry(RandomPlayer),
    "solver": PlayerEntry(SolverPlayer),
    "jev": PlayerEntry(_jev, paid=True),
}


def make_player(name: str) -> Player:
    if name not in PLAYERS:
        raise ValueError(f"unknown player {name!r}; known: {', '.join(PLAYERS)}")
    return PLAYERS[name].build()
