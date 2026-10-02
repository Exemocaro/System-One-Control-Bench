"""Every player: one decision, one answer, and every player by name."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import partial
from typing import Any

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
    """Chooses a move from what a turn shows it. Known by its name in the roster."""

    @abstractmethod
    def choose(self, turn: Turn) -> Choice: ...

    def close(self) -> None:  # noqa: B027  (optional: most players hold nothing)
        """Let go of anything held between moves, such as a connection."""


@dataclass(frozen=True)
class PlayerEntry:
    build: Callable[[], Player]
    paid: bool = False
    compass_only: bool = False  # it reads compass moves itself, so it cannot play other rules


# Imported last: each player below is built on the names above.
from system_one_control.players.baselines import (  # noqa: E402
    GreedyPlayer,
    RandomPlayer,
    SolverPlayer,
    WallAwareGreedyPlayer,
)
from system_one_control.players.local import (  # noqa: E402
    LOCAL_LLM_MODELS,
    GLiClassPlayer,
    LayaPlayer,
    LocalLLMPlayer,
)
from system_one_control.players.remote import LLM_MODELS, JevPlayer, LLMPlayer  # noqa: E402

PLAYERS: dict[str, PlayerEntry] = {
    "random": PlayerEntry(RandomPlayer),
    "greedy": PlayerEntry(GreedyPlayer, compass_only=True),
    "greedy-walls": PlayerEntry(WallAwareGreedyPlayer, compass_only=True),
    "solver": PlayerEntry(SolverPlayer),
    "jev": PlayerEntry(JevPlayer, paid=True),
    # On this machine: loaded only when a game first asks, so only then is the local extra needed.
    "laya": PlayerEntry(LayaPlayer),
    "gliclass": PlayerEntry(GLiClassPlayer),
}
for name, repo in LOCAL_LLM_MODELS.items():
    PLAYERS[name] = PlayerEntry(partial(LocalLLMPlayer, repo))
# Each chat model twice: answering at once, as Jev does, and thinking first.
for name, (model, host) in LLM_MODELS.items():
    PLAYERS[name] = PlayerEntry(partial(LLMPlayer, model, host=host, reasoning=False), paid=True)
for name, (model, host) in LLM_MODELS.items():
    PLAYERS[f"{name}-think"] = PlayerEntry(
        partial(LLMPlayer, model, host=host, reasoning=True), paid=True
    )


def make_player(name: str) -> Player:
    if name not in PLAYERS:
        raise ValueError(f"unknown player {name!r}; known: {', '.join(PLAYERS)}")
    return PLAYERS[name].build()
