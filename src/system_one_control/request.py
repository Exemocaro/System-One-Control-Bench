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

    def to_text(self) -> str:
        """The request as one readable page, the way the examples folder shows it."""
        options = "\n".join(f"{option.id}: {option.text}" for option in self.options)
        return f"{self.state}\n\nQuestion: {self.question}\n\nOptions:\n{options}\n"
