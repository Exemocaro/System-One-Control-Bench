"""What a player is shown: the state and question of a turn, its options, and the conditions."""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from system_one_control.puzzles import Scenario, load_scenarios
from system_one_control.world import (
    DOOR,
    GOAL,
    KEY,
    SYMBOL_NAMES,
    Board,
    CompassRules,
    Rules,
)

QUESTION = "What is the best next move?"  # the subgoal ingredient asks the rules' own instead

# Each ingredient hands the player one thing that code can work out for it.
INGREDIENTS = {
    "surroundings": "what is next to you in each direction, and where the key, door and goal are",
    "memory": "every move so far and what it did",
    "lookahead": "what each move would do, written into its option",
    "subgoal": "a question naming the next thing to reach: the key, then the door, then the goal",
}


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

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_SCENARIO = "gen-10-01"
# Two moves under each rules; the second walks into a wall, so the memory shows it. Rules not
# listed get the first move that goes anywhere, then the first that is blocked (see example_moves).
EXAMPLE_MOVES = {
    "compass": ("east", "north"),
    "two-moves": ("east,south", "north,north"),
    "three-moves": ("east,south,west", "north,north,north"),
    "up-to-two-moves": ("east", "north,north"),
    "up-to-three-moves": ("east,south", "north,north,north"),
}


def example_moves(scenario: Scenario) -> tuple[str, ...]:
    """The two moves an example is taken after: a move, then one that is blocked, if any is."""
    if scenario.rules.name in EXAMPLE_MOVES:
        return EXAMPLE_MOVES[scenario.rules.name]
    rules, board = scenario.rules, scenario.board
    first = next(move for move in rules.moves(board) if rules.apply(board, move) != board)
    after = rules.apply(board, first)
    blocked = [move for move in rules.moves(after) if rules.apply(after, move) == after]
    return first.name, (blocked or [first])[0].name


def example(condition: Condition, scenario: Scenario) -> str:
    """The JSON body sent to Jev under this condition, two moves into the scenario."""
    # Imported here: the game and the players are built on this module's Request.
    from system_one_control.game import Game
    from system_one_control.players import ScriptedPlayer, jev_body

    moves = example_moves(scenario)
    game = Game(scenario, ScriptedPlayer(moves), condition)
    for _ in moves:
        game.step()
    return json.dumps(jev_body(game.next_request()), indent=2, ensure_ascii=False) + "\n"


def write_examples(folder: Path = EXAMPLE_DIR, rules: Rules | None = None) -> list[Path]:
    """One file per condition, so anyone can read what each condition sends Jev.

    Rules other than compass get a subfolder of their own.
    """
    scenario = load_scenarios()[EXAMPLE_SCENARIO]
    if rules is not None and not isinstance(rules, CompassRules):
        scenario = replace(scenario, rules=rules)
        folder = folder / rules.name
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for condition in CONDITIONS.values():
        path = folder / f"{condition.name}.json"
        path.write_text(example(condition, scenario), encoding="utf-8", newline="\n")
        written.append(path)
    return written
