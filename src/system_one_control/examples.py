"""The exact request each condition sends: one file per condition, written by `socb examples`."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from system_one_control.bench import Game
from system_one_control.players.baselines import ScriptedPlayer
from system_one_control.players.remote import jev_body
from system_one_control.prompts import CONDITIONS, Condition
from system_one_control.puzzles import Puzzle, load_puzzles
from system_one_control.world import CompassRules, Rules

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_PUZZLE = "gen-10-01"
# Two moves under each rules; the second walks into a wall, so the memory shows it. Rules not
# listed get the first move that goes anywhere, then the first that is blocked (see example_moves).
EXAMPLE_MOVES = {
    "compass": ("east", "north"),
    "two-moves": ("east,south", "north,north"),
    "three-moves": ("east,south,west", "north,north,north"),
    "up-to-two-moves": ("east", "north,north"),
    "up-to-three-moves": ("east,south", "north,north,north"),
}


def example_moves(puzzle: Puzzle) -> tuple[str, ...]:
    """The two moves an example is taken after: a move, then one that is blocked, if any is."""
    if puzzle.rules.name in EXAMPLE_MOVES:
        return EXAMPLE_MOVES[puzzle.rules.name]
    rules, board = puzzle.rules, puzzle.board
    first = next(move for move in rules.moves(board) if rules.apply(board, move) != board)
    after = rules.apply(board, first)
    blocked = [move for move in rules.moves(after) if rules.apply(after, move) == after]
    return first.name, (blocked or [first])[0].name


def example(condition: Condition, puzzle: Puzzle) -> str:
    """The JSON body sent to Jev under this condition, two moves into the puzzle."""
    moves = example_moves(puzzle)
    game = Game(puzzle, ScriptedPlayer(moves), condition)
    for _ in moves:
        game.play_move()
    return json.dumps(jev_body(game.next_request()), indent=2, ensure_ascii=False) + "\n"


def write_examples(folder: Path = EXAMPLE_DIR, rules: Rules | None = None) -> list[Path]:
    """One file per condition, so anyone can read what each condition sends Jev.

    Rules other than compass get a subfolder of their own.
    """
    puzzle = load_puzzles()[EXAMPLE_PUZZLE]
    if rules is not None and not isinstance(rules, CompassRules):
        puzzle = replace(puzzle, rules=rules)
        folder = folder / rules.name
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for condition in CONDITIONS.values():
        path = folder / f"{condition.name}.json"
        path.write_text(example(condition, puzzle), encoding="utf-8", newline="\n")
        written.append(path)
    return written
