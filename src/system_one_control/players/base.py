"""One decision, one answer, every player by name, and the environment settings."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from dotenv import load_dotenv

from system_one_control.prompts import Request
from system_one_control.world import Board, Rules


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


class Player(ABC):
    """Chooses a move from what a turn shows it. Known by its name in PLAYERS."""

    @abstractmethod
    def choose(self, turn: Turn) -> Choice: ...

    def close(self) -> None:  # noqa: B027  (optional: most players hold nothing)
        """Let go of anything held between moves, such as a connection."""


@dataclass(frozen=True)
class PlayerEntry:
    build: Callable[[], Player]
    paid: bool = False
    compass_only: bool = False  # it reads compass moves itself, so it cannot play other rules


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
