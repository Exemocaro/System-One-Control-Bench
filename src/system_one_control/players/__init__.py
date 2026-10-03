"""Every player: one decision, one answer, and every player by name."""

from __future__ import annotations

from functools import partial

from system_one_control.players.base import (
    Choice,
    Player,
    PlayerEntry,
    Turn,
    answer_choice,
    api_key,
    setting,
)
from system_one_control.players.baselines import (
    GreedyPlayer,
    RandomPlayer,
    SolverPlayer,
    WallAwareGreedyPlayer,
)
from system_one_control.players.local import (
    LOCAL_LLM_MODELS,
    GLiClassPlayer,
    LayaPlayer,
    LocalLLMPlayer,
)
from system_one_control.players.remote import LLM_MODELS, JevPlayer, LLMPlayer

__all__ = [
    "LLM_MODELS",
    "LOCAL_LLM_MODELS",
    "PLAYERS",
    "Choice",
    "GLiClassPlayer",
    "GreedyPlayer",
    "JevPlayer",
    "LLMPlayer",
    "LayaPlayer",
    "LocalLLMPlayer",
    "Player",
    "PlayerEntry",
    "RandomPlayer",
    "SolverPlayer",
    "Turn",
    "WallAwareGreedyPlayer",
    "answer_choice",
    "api_key",
    "make_player",
    "setting",
]

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
