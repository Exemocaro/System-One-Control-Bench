"""Every player: one decision, one answer, and every player by name."""

from __future__ import annotations

import tomllib
from functools import partial
from pathlib import Path
from typing import Any

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
from system_one_control.players.remote import (
    LLM_MODELS,
    DecisionPlayer,
    JevPlayer,
    LLMPlayer,
)

__all__ = [
    "LLM_MODELS",
    "LOCAL_LLM_MODELS",
    "PLAYERS",
    "Choice",
    "DecisionPlayer",
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
    "players_from_toml",
    "register_toml_players",
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


def players_from_toml(path: Path) -> dict[str, PlayerEntry]:
    """Extra players from a players.toml file: chat models and decision endpoints."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    builders = {"chat": chat_player, "decision": decision_player}
    entries = {}
    for name, spec in (data.get("players") or {}).items():
        if name in PLAYERS or name in entries:
            raise ValueError(f"player {name!r} clashes with a player that already exists")
        if spec.get("kind") not in builders:
            raise ValueError(
                f"player {name!r}: kind must be chat or decision, not {spec.get('kind')!r}"
            )
        entries[name] = builders[spec["kind"]](spec, spec.get("paid", True))
    return entries


def chat_player(spec: dict[str, Any], paid: bool) -> PlayerEntry:
    """A chat model on any OpenAI-compatible endpoint, asked as the OpenRouter ones are."""
    for field in ("base_url", "model"):
        if field not in spec:
            raise ValueError(f"chat player needs {field!r}")
    key = setting(spec["api_key_env"]) if spec.get("api_key_env") else None
    return PlayerEntry(
        partial(
            LLMPlayer,
            spec["model"],
            reasoning=spec.get("reasoning", False),
            base_url=spec["base_url"].rstrip("/") + "/chat/completions",
            api_key=key,
        ),
        paid=paid,
    )


def decision_player(spec: dict[str, Any], paid: bool) -> PlayerEntry:
    """A bounded decision model behind an HTTP API: state, question and options in, odds out."""
    if "url" not in spec:
        raise ValueError("decision player needs 'url'")
    key = setting(spec["api_key_env"]) if spec.get("api_key_env") else None
    return PlayerEntry(
        partial(DecisionPlayer, spec["url"], api_key=key),
        paid=paid,
    )


def register_toml_players(path: Path) -> list[str]:
    """Add a players.toml file's players to the registry."""
    entries = players_from_toml(path)
    PLAYERS.update(entries)
    return list(entries)
