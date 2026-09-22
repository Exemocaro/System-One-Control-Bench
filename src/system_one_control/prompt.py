from __future__ import annotations

import random
from collections.abc import Sequence
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
    """A wording: templates filled from the board and rules, plus how options are written."""

    name: str
    description: str
    state: str
    question: str
    option_text: dict[str, str] = field(default_factory=dict)
    show_outcomes: bool = False

    @classmethod
    def load(cls, path: Path) -> Prompt:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            name=path.stem,
            description=data.get("description", ""),
            state=data["state"],
            question=data["question"],
            option_text=dict(data.get("options", {})),
            show_outcomes=bool(data.get("show_outcomes", False)),
        )

    def render(
        self,
        board: Board,
        rules: Rules,
        *,
        shuffle_seed: str | None = None,
        history: Sequence[str] = (),
    ) -> Request:
        facts = board_facts(board, rules, history)
        try:
            state = self.state.format(**facts).strip("\n")
            question = self.question.format(**facts).strip()
        except KeyError as error:
            raise ValueError(
                f"prompt {self.name!r} uses {{{error.args[0]}}}, which is not available; "
                f"available: {', '.join(sorted(facts))}"
            ) from error

        moves = list(rules.moves(board))
        if shuffle_seed is not None:
            random.Random(shuffle_seed).shuffle(moves)
        options = []
        for number, move in enumerate(moves, start=1):
            text = self.option_text.get(move.name, move.description)
            if self.show_outcomes:
                text += f": {describe_outcome(board, rules.apply(board, move), rules)}"
            options.append(Option(f"option_{number}", move.name, text))
        return Request(state, question, tuple(options))


def describe_outcome(before: Board, after: Board, rules: Rules) -> str:
    if after == before:
        return f"blocked, you stay at {before.agent}"
    events = []
    if len(after.holding) > len(before.holding):
        events.append(f"pick up the {after.holding[-1]}")
    if len(after.find(DOOR)) < len(before.find(DOOR)):
        events.append("unlock the door")
    if rules.is_won(after):
        events.append("reach the goal")
    return " and ".join([f"you move to {after.agent}", *events])


def board_facts(board: Board, rules: Rules, history: Sequence[str] = ()) -> dict[str, str]:
    """Every placeholder a prompt template can use."""
    drawn = board.draw()
    objects = [
        f"{SYMBOL_NAMES[symbol]} {symbol} at {position}"
        for symbol in (GOAL, KEY, DOOR)
        for position in board.find(symbol)
    ]
    carried = ", ".join(board.holding)
    moves_so_far = "\n".join(f"{n}. {line}" for n, line in enumerate(history, start=1))
    return {
        "rules": rules.description,
        "map": drawn,
        "map_grid": _numbered(drawn),
        "legend": ", ".join(f"{s} = {name}" for s, name in SYMBOL_NAMES.items() if s in drawn),
        "position": str(board.agent),
        "holding": f"You are carrying: {carried}." if carried else "You are carrying nothing.",
        "objects": "; ".join(objects) or "none",
        "moves": ", ".join(move.name for move in rules.moves(board)),
        "history": f"Moves so far:\n{moves_so_far}" if history else "No moves yet.",
        **rules.facts(board),
    }


def _numbered(drawn: str) -> str:
    """The map with column numbers above it and row numbers beside it."""
    rows = drawn.splitlines()
    header = "   " + "".join(str(x % 10) for x in range(len(rows[0])))
    return "\n".join([header, *(f"{y:>2} {row}" for y, row in enumerate(rows))])


def load_prompts(folder: Path = PROMPT_DIR) -> dict[str, Prompt]:
    return {path.stem: Prompt.load(path) for path in sorted(folder.glob("*.yaml"))}
