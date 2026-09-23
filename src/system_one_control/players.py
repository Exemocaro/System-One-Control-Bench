from __future__ import annotations

import os
import random
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from dotenv import load_dotenv
from typesafe_sdk import RetryPolicy, TypeSafeClient

from system_one_control.board import Board
from system_one_control.request import Request
from system_one_control.rules import CompassRules, Move, Rules, next_target
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
    input_tokens: int | None = None  # what a paid model billed for the question


class Player(ABC):
    name: ClassVar[str]

    @abstractmethod
    def choose(self, turn: Turn) -> Choice: ...

    def close(self) -> None:  # noqa: B027  (optional: most players hold nothing)
        """Let go of anything held between moves, such as a connection."""


class RandomPlayer(Player):
    name = "random"

    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def choose(self, turn: Turn) -> Choice:
        return Choice(self._rng.choice(turn.request.options).move)


class ScriptedPlayer(Player):
    """Plays a fixed list of moves, then gives up. For examples and tests."""

    name = "scripted"

    def __init__(self, moves: Sequence[str]) -> None:
        self._moves = iter(moves)

    def choose(self, turn: Turn) -> Choice:
        move = next(self._moves, None)
        return Choice(move, error=None if move else "out of scripted moves")


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
        _, target = next_target(board)

        def distance_after(move: Move) -> int:
            there = board.agent.moved(*CompassRules.STEPS[move.name])
            return abs(there.x - target.x) + abs(there.y - target.y)

        return min(moves, key=distance_after).name


class WallAwareGreedyPlayer(GreedyPlayer):
    """Greedy, but never picks a move that would leave it where it stands."""

    name = "greedy-walls"
    avoids_blocked_moves = True


JEV_MODEL = "jev-1.13.0"
JEV_QUESTION = "move"
API_KEY_NAMES = ("TYPESAFE_API_KEY", "JEV_API_KEY")


def api_key() -> str:
    load_dotenv()
    for name in API_KEY_NAMES:
        if os.environ.get(name):
            return os.environ[name]
    raise RuntimeError(f"no Jev API key: set {' or '.join(API_KEY_NAMES)} in .env")


def jev_body(request: Request, model: str = JEV_MODEL) -> dict[str, Any]:
    """The JSON body sent to Jev for a request, exactly as it goes over the wire."""
    return {
        "state": request.state,
        "model": model,
        "questions": {
            JEV_QUESTION: {
                "type": "choice",
                "instructions": request.question,
                "criteria": {option.id: option.text for option in request.options},
            }
        },
    }


class JevPlayer(Player):
    """Jev, through the TypeSafe SDK. Sees only the request, never the board.

    A failed call raises, and the game records it as a move with no answer.
    """

    name = "jev"

    def __init__(self, model: str = JEV_MODEL, client: Any = None) -> None:
        self._owns_client = client is None
        if client is None:
            no_retries = RetryPolicy(max_retries=0)  # one move is exactly one paid call
            client = TypeSafeClient(api_key=api_key(), timeout=60.0, retry=no_retries)
        self.model = model
        self._client = client

    def choose(self, turn: Turn) -> Choice:
        request = turn.request
        response = self._client.system_one(**jev_body(request, self.model))
        answer = response.choices[JEV_QUESTION]
        tokens = response.usage.input_tokens
        moves = {option.id: option.move for option in request.options}
        probabilities = {moves[id]: p for id, p in answer.probabilities.items() if id in moves}
        if answer.choice not in moves:
            problem = f"Jev answered {answer.choice!r}"
            return Choice(None, probabilities, error=problem, input_tokens=tokens)
        return Choice(moves[answer.choice], probabilities, input_tokens=tokens)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


@dataclass(frozen=True)
class PlayerEntry:
    build: Callable[[], Player]
    paid: bool = False


PLAYERS: dict[str, PlayerEntry] = {
    "random": PlayerEntry(RandomPlayer),
    "greedy": PlayerEntry(GreedyPlayer),
    "greedy-walls": PlayerEntry(WallAwareGreedyPlayer),
    "solver": PlayerEntry(SolverPlayer),
    "jev": PlayerEntry(JevPlayer, paid=True),
}


def make_player(name: str) -> Player:
    if name not in PLAYERS:
        raise ValueError(f"unknown player {name!r}; known: {', '.join(PLAYERS)}")
    return PLAYERS[name].build()
