from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from system_one_control.board import DOOR, GOAL, KEY, SYMBOL_NAMES, Board
from system_one_control.rules import Rules

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


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


@dataclass(frozen=True)
class Prompt:
    """A wording: templates filled from the board and rules, plus optional option names."""

    name: str
    description: str
    state: str
    question: str
    option_text: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Prompt:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            name=path.stem,
            description=data.get("description", ""),
            state=data["state"],
            question=data["question"],
            option_text=dict(data.get("options", {})),
        )

    def render(self, board: Board, rules: Rules) -> Request:
        facts = board_facts(board, rules)
        try:
            state = self.state.format(**facts).strip()
            question = self.question.format(**facts).strip()
        except KeyError as error:
            raise ValueError(
                f"prompt {self.name!r} uses {{{error.args[0]}}}, which is not available; "
                f"available: {', '.join(sorted(facts))}"
            ) from error
        options = tuple(
            Option(f"option_{number}", move.name, self.option_text.get(move.name, move.description))
            for number, move in enumerate(rules.moves(board), start=1)
        )
        return Request(state, question, options)


def board_facts(board: Board, rules: Rules) -> dict[str, str]:
    """Every placeholder a prompt template can use."""
    drawn = board.draw()
    objects = [
        f"{SYMBOL_NAMES[symbol]} {symbol} at {position}"
        for symbol in (GOAL, KEY, DOOR)
        for position in board.find(symbol)
    ]
    carried = ", ".join(board.holding)
    return {
        "rules": rules.description,
        "map": drawn,
        "legend": ", ".join(f"{s} = {name}" for s, name in SYMBOL_NAMES.items() if s in drawn),
        "position": str(board.agent),
        "holding": f"You are carrying: {carried}." if carried else "You are carrying nothing.",
        "objects": "; ".join(objects) or "none",
        "moves": ", ".join(move.name for move in rules.moves(board)),
        **rules.facts(board),
    }


def load_prompts(folder: Path = PROMPT_DIR) -> dict[str, Prompt]:
    return {path.stem: Prompt.load(path) for path in sorted(folder.glob("*.yaml"))}
