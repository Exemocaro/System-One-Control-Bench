"""Every player the benchmark knows, by name."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from system_one_control.llm_players import LLM_MODELS, LLMPlayer
from system_one_control.players import (
    GreedyPlayer,
    JevPlayer,
    Player,
    RandomPlayer,
    SolverPlayer,
    WallAwareGreedyPlayer,
)


@dataclass(frozen=True)
class PlayerEntry:
    build: Callable[[], Player]
    paid: bool = False
    compass_only: bool = False  # it reads compass moves itself, so it cannot play other rules


def _laya() -> Player:
    from system_one_control.local_players import LayaPlayer  # needs the local extra

    return LayaPlayer()


def _gliclass() -> Player:
    from system_one_control.local_players import GLiClassPlayer  # needs the local extra

    return GLiClassPlayer()


def _llm(model: str, *, reasoning: bool) -> PlayerEntry:
    return PlayerEntry(lambda: LLMPlayer(model, reasoning=reasoning), paid=True)


PLAYERS: dict[str, PlayerEntry] = {
    "random": PlayerEntry(RandomPlayer),
    "greedy": PlayerEntry(GreedyPlayer, compass_only=True),
    "greedy-walls": PlayerEntry(WallAwareGreedyPlayer, compass_only=True),
    "solver": PlayerEntry(SolverPlayer),
    "jev": PlayerEntry(JevPlayer, paid=True),
    "laya": PlayerEntry(_laya),
    "gliclass": PlayerEntry(_gliclass),
    # Each chat model twice: answering at once, as Jev does, and thinking first.
    **{name: _llm(model, reasoning=False) for name, model in LLM_MODELS.items()},
    **{f"{name}-think": _llm(model, reasoning=True) for name, model in LLM_MODELS.items()},
}


def make_player(name: str) -> Player:
    if name not in PLAYERS:
        raise ValueError(f"unknown player {name!r}; known: {', '.join(PLAYERS)}")
    return PLAYERS[name].build()
