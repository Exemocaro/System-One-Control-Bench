from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Option:
    id: str
    move: str
    text: str


@dataclass(frozen=True)
class Request:
    """Exactly what a player is shown: the state, the question and the options."""

    state: str
    question: str
    options: tuple[Option, ...]
