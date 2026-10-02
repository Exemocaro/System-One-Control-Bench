from __future__ import annotations

import os
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, TypeVar

from dotenv import load_dotenv
from typesafe_sdk import (
    RetryPolicy,
    TypeSafeAPIConnectionError,
    TypeSafeAPITimeoutError,
    TypeSafeClient,
    TypeSafeInternalServerError,
    TypeSafeRateLimitError,
)

from system_one_control.request import Request
from system_one_control.world import Board, CompassRules, Move, Rules, Solver, next_target


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
    output_tokens: int | None = None
    confidence: float | None = None  # the model's own score, where it gives one
    model: str | None = None  # the model version that answered, where it says
    seconds: float | None = None  # the answering call alone, where the player times it
    retried: tuple[str, ...] = ()  # why each earlier attempt was turned away
    cost: float | None = None  # in US dollars, where the provider reports it


def answer_choice(
    request: Request,
    option_id: str | None,
    probabilities: dict[str, float],
    **details: Any,
) -> Choice:
    """A model's answer, given by option id, as a move: an answer outside the options is an
    error. `probabilities` are by option id too; `details` are the rest of the Choice."""
    moves = {option.id: option.move for option in request.options}
    choice = Choice(
        moves.get(option_id or ""),
        {moves[id]: p for id, p in probabilities.items() if id in moves},
        **details,
    )
    if option_id not in moves:
        return replace(choice, error=f"the answer {option_id!r} is not one of the options")
    return choice


T = TypeVar("T")


def with_retries(
    call: Callable[[], T], waits: Sequence[float], retryable: Callable[[Exception], bool]
) -> tuple[T, float, tuple[str, ...]]:
    """Make a call, trying again after each of `waits` while it fails in a way worth retrying.

    Returns what the call returned, how many seconds the answering call alone took, and why
    each earlier attempt failed. The last failure, or any not worth retrying, is raised.
    """
    retried: list[str] = []
    for wait in (*waits, None):
        started = time.perf_counter()
        try:
            result = call()
        except Exception as error:
            if wait is None or not retryable(error):
                raise
            retried.append(f"{type(error).__name__}: {error}")
            time.sleep(wait)
            continue
        return result, time.perf_counter() - started, tuple(retried)
    raise AssertionError("unreachable: the last attempt returns or raises")


class Player(ABC):
    """Chooses a move from what a turn shows it. Known by its name in the roster."""

    @abstractmethod
    def choose(self, turn: Turn) -> Choice: ...

    def close(self) -> None:  # noqa: B027  (optional: most players hold nothing)
        """Let go of anything held between moves, such as a connection."""


class RandomPlayer(Player):
    def __init__(self, seed: int = 0) -> None:
        self._rng = random.Random(seed)

    def choose(self, turn: Turn) -> Choice:
        return Choice(self._rng.choice(turn.request.options).move)


class ScriptedPlayer(Player):
    """Plays a fixed list of moves, then gives up. For examples and tests."""

    def __init__(self, moves: Sequence[str]) -> None:
        self._moves = iter(moves)

    def choose(self, turn: Turn) -> Choice:
        move = next(self._moves, None)
        return Choice(move, error=None if move else "out of scripted moves")


class SolverPlayer(Player):
    """Plays perfectly by searching the real board."""

    def __init__(self) -> None:
        # The distances from the first board of a game cover every later one.
        self._rules: Rules | None = None
        self._distances: dict[Board, int] = {}

    def choose(self, turn: Turn) -> Choice:
        solver = Solver(turn.rules)
        if turn.rules is not self._rules or turn.board not in self._distances:
            self._rules, self._distances = turn.rules, solver.distances(turn.board)
        best = solver.best_moves(turn.board, self._distances)
        if not best:
            return Choice(None, error="the goal cannot be reached")
        return Choice(best[0], {move: 1 / len(best) for move in best})


class GreedyPlayer(Player):
    """Steps straight toward the key, then the door, then the goal, and never plans.

    It shows what heading for the next target is worth on its own. It ignores walls, and it
    breaks ties by the rules' order of moves, so the option shuffle never changes its game.
    Compass rules only.
    """

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

    avoids_blocked_moves = True


JEV_MODEL = "jev-1.13.0"
JEV_QUESTION = "move"
API_KEY_NAMES = ("TYPESAFE_API_KEY", "JEV_API_KEY")
# Seconds to wait before each retry of a request the server turned away.
JEV_RETRY_WAITS = (1.0, 2.0)
# Seconds a call may take. A timeout is not retried and ends the game, so this is generous:
# the slowest compass call took 39 s, and a three-moves request is about 5 times as long.
JEV_TIMEOUT = 120.0


def turned_away(error: Exception) -> bool:
    """Whether the server refused the request (busy, rate-limited, failing) or never got it.

    A timeout is not one of these: the server may have answered, and billed, a slow request.
    """
    if isinstance(error, TypeSafeAPITimeoutError):
        return False
    refused = (TypeSafeRateLimitError, TypeSafeInternalServerError, TypeSafeAPIConnectionError)
    return isinstance(error, refused)


def setting(name: str) -> str | None:
    """A setting from the environment, or else from .env; None if empty."""
    load_dotenv()
    return os.environ.get(name) or None


def api_key(names: Sequence[str], service: str) -> str:
    """The first of these settings that is set: an API key for the service."""
    for name in names:
        if key := setting(name):
            return key
    raise RuntimeError(f"no {service} API key: set {' or '.join(names)} in .env")


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

    A call the server turned away is tried again after each of `retry_waits`, and the choice
    records why each earlier attempt failed. Its time is the answering call's alone. A call
    that still fails raises, and the game records it as a move with no answer.
    """

    def __init__(
        self,
        model: str = JEV_MODEL,
        client: Any = None,
        retry_waits: Sequence[float] = JEV_RETRY_WAITS,
    ) -> None:
        self._owns_client = client is None
        if client is None:
            no_retries = RetryPolicy(max_retries=0)  # retried here, so each attempt is seen
            client = TypeSafeClient(
                api_key=api_key(API_KEY_NAMES, "Jev"), timeout=JEV_TIMEOUT, retry=no_retries
            )
        self.model = model
        self._client = client
        self._retry_waits = tuple(retry_waits)

    def choose(self, turn: Turn) -> Choice:
        body = jev_body(turn.request, self.model)
        response, seconds, retried = with_retries(
            lambda: self._client.system_one(**body), self._retry_waits, turned_away
        )
        answer = response.choices[JEV_QUESTION]
        return answer_choice(
            turn.request,
            answer.choice,
            answer.probabilities,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            confidence=answer.confidence,
            model=response.model,
            seconds=seconds,
            retried=retried,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
