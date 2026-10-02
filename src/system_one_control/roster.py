"""Every player the benchmark knows, by name."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

from system_one_control.llm_players import LLM_MODELS, LLMPlayer
from system_one_control.local_players import (
    LOCAL_LLM_MODELS,
    GLiClassPlayer,
    LayaPlayer,
    LocalLLMPlayer,
)
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


def _llm(model: str, host: str, *, reasoning: bool) -> PlayerEntry:
    return PlayerEntry(lambda: LLMPlayer(model, host=host, reasoning=reasoning), paid=True)


PLAYERS: dict[str, PlayerEntry] = {
    "random": PlayerEntry(RandomPlayer),
    "greedy": PlayerEntry(GreedyPlayer, compass_only=True),
    "greedy-walls": PlayerEntry(WallAwareGreedyPlayer, compass_only=True),
    "solver": PlayerEntry(SolverPlayer),
    "jev": PlayerEntry(JevPlayer, paid=True),
    # On this machine: loaded only when a game first asks, so only then is the local extra needed.
    "laya": PlayerEntry(LayaPlayer),
    "gliclass": PlayerEntry(GLiClassPlayer),
    **{name: PlayerEntry(partial(LocalLLMPlayer, repo)) for name, repo in LOCAL_LLM_MODELS.items()},
    # Each chat model twice: answering at once, as Jev does, and thinking first.
    **{name: _llm(*model, reasoning=False) for name, model in LLM_MODELS.items()},
    **{f"{name}-think": _llm(*model, reasoning=True) for name, model in LLM_MODELS.items()},
}


def make_player(name: str) -> Player:
    if name not in PLAYERS:
        raise ValueError(f"unknown player {name!r}; known: {', '.join(PLAYERS)}")
    return PLAYERS[name].build()
