from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from system_one_control.board import DOOR, GOAL, KEY, SYMBOL_NAMES, Board
from system_one_control.request import Option, Request
from system_one_control.rules import Rules

QUESTION = "What is the best next move?"  # the subgoal ingredient asks the rules' own instead

# Each ingredient hands the player one thing that code can work out for it.
INGREDIENTS = {
    "surroundings": "what is next to you in each direction, and where the key, door and goal are",
    "memory": "every move so far and what it did",
    "lookahead": "what each move would do, written into its option",
    "subgoal": "a question naming the next thing to reach: the key, then the door, then the goal",
}


@dataclass(frozen=True)
class Condition:
    """What a player is told: the map always, plus the ingredients switched on."""

    name: str
    surroundings: bool = False
    memory: bool = False
    lookahead: bool = False
    subgoal: bool = False

    @property
    def ingredients(self) -> list[str]:
        return [name for name in INGREDIENTS if getattr(self, name)]

    @property
    def description(self) -> str:
        added = [INGREDIENTS[name] for name in self.ingredients]
        return f"The map, plus {'; '.join(added)}." if added else "The map alone."

    def render(
        self,
        board: Board,
        rules: Rules,
        *,
        shuffle_seed: str | None = None,
        history: Sequence[str] = (),
    ) -> Request:
        """The request for this board. Options are shuffled by the seed, if one is given."""
        sections = [rules.description, describe_map(board), describe_player(board)]
        if self.surroundings:
            sections.append(rules.describe_surroundings(board))
        if self.memory:
            sections.append(describe_history(history))

        question = rules.subgoal_question(board) if self.subgoal else QUESTION

        moves = list(rules.moves(board))
        if shuffle_seed is not None:
            random.Random(shuffle_seed).shuffle(moves)
        options = []
        for number, move in enumerate(moves, start=1):
            text = move.description
            if self.lookahead:
                text += f": {rules.describe_outcome(board, rules.apply(board, move))}"
            options.append(Option(f"option_{number}", move.name, text))

        return Request("\n\n".join(sections), question, tuple(options))


def describe_map(board: Board) -> str:
    """The map with column numbers above it and row numbers beside it."""
    drawn = board.draw()
    legend = ", ".join(f"{s} = {name}" for s, name in SYMBOL_NAMES.items() if s in drawn)
    rows = drawn.splitlines()
    header = "   " + "".join(str(x % 10) for x in range(len(rows[0])))
    numbered = "\n".join([header, *(f"{y:>2} {row}" for y, row in enumerate(rows))])
    return (
        f"Map, with column numbers along the top and row numbers down the side ({legend}). "
        f"A position (x, y) is column x, row y:\n{numbered}"
    )


def describe_player(board: Board) -> str:
    carried = ", ".join(board.holding)
    holding = f"You are carrying: {carried}." if carried else "You are carrying nothing."
    objects = [
        f"{SYMBOL_NAMES[symbol]} {symbol} at {position}"
        for symbol in (GOAL, KEY, DOOR)
        for position in board.find(symbol)
    ]
    return f"You are A at {board.agent}. {holding}\nObjects: {'; '.join(objects)}."


def describe_history(history: Sequence[str]) -> str:
    if not history:
        return "No moves yet."
    lines = "\n".join(f"{number}. {line}" for number, line in enumerate(history, start=1))
    return f"Moves so far:\n{lines}"


# The ablation: each ingredient added to the map alone, then each taken away from everything.
CONDITIONS = {
    condition.name: condition
    for condition in (
        Condition("map"),
        Condition("map+surroundings", surroundings=True),
        Condition("map+memory", memory=True),
        Condition("map+lookahead", lookahead=True),
        Condition("map+subgoal", subgoal=True),
        Condition("everything", surroundings=True, memory=True, lookahead=True, subgoal=True),
        Condition("everything-surroundings", memory=True, lookahead=True, subgoal=True),
        Condition("everything-memory", surroundings=True, lookahead=True, subgoal=True),
        Condition("everything-lookahead", surroundings=True, memory=True, subgoal=True),
        Condition("everything-subgoal", surroundings=True, memory=True, lookahead=True),
    )
}
