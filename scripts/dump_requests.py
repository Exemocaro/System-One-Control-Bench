"""Dump the full request (state, question, options) of every puzzle x condition x rules.

For each combination: the move-1 request, and the request after the first 3 recorded moves
of a saved game for that puzzle under those rules (or a NO-SAVED-GAME marker where no
saved game has 3 valid moves). Runs under the old code and the new code; diff the two
output files, which must be identical. Usage: dump_requests.py <out path>.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import system_one_control

try:  # new layout
    from system_one_control.bench import Game
    from system_one_control.players.baselines import ScriptedPlayer
    from system_one_control.prompts import CONDITIONS
    from system_one_control.puzzles import load_puzzles
    from system_one_control.world import RULES, make_rules

    ITEMS = load_puzzles()
except ImportError:  # old layout on main
    from system_one_control.conditions import CONDITIONS
    from system_one_control.game import Game
    from system_one_control.rules import RULES, make_rules
    from system_one_control.scenario import load_scenarios as load_puzzles

    from system_one_control.players import ScriptedPlayer

    ITEMS = load_puzzles()

REPO = Path(system_one_control.__file__).resolve().parents[2]


def advance(game: Game, moves: int) -> None:
    for _ in range(moves):
        if hasattr(game, "play_move"):
            game.play_move()
        else:
            game.step()


def saved_opener(name: str, rules: str) -> list | None:
    """The first 3 recorded moves of a saved game of this puzzle under these rules."""
    for path in sorted((REPO / "benchmarks").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if (record.get("puzzle") or record.get("scenario")) != name:
                continue
            if record.get("rules", "compass") != rules:
                continue
            moves = [move["move"] for move in record["moves"]]
            if len(moves) >= 3 and all(move is not None for move in moves[:3]):
                return moves[:3]
    return None


def write_request(file, rules: str, name: str, condition: str, tag: str, request) -> None:
    file.write(f"### {rules} {name} {condition} {tag}\n")
    file.write(request.state + "\n--- question ---\n" + request.question + "\n--- options ---\n")
    for option in request.options:
        file.write(f"{option.id}: {option.move}: {option.text}\n")


def main(out: Path) -> None:
    combinations = 0
    with out.open("w", encoding="utf-8", newline="") as file:
        for rules_name in sorted(RULES):
            rules = make_rules(rules_name)
            for name in sorted(ITEMS):
                item = replace(ITEMS[name], rules=rules)
                game = Game(item, ScriptedPlayer([]), CONDITIONS["map"])
                for condition_name in sorted(CONDITIONS):
                    game.condition = CONDITIONS[condition_name]
                    write_request(
                        file, rules_name, name, condition_name, "move-1", game.next_request()
                    )
                    combinations += 1
                opener = saved_opener(name, rules_name)
                if opener is None:
                    file.write(f"### {rules_name} {name} all after-3: NO-SAVED-GAME\n")
                    continue
                game = Game(item, ScriptedPlayer(opener), CONDITIONS["map"])
                advance(game, 3)
                for condition_name in sorted(CONDITIONS):
                    game.condition = CONDITIONS[condition_name]
                    write_request(
                        file, rules_name, name, condition_name, "after-3", game.next_request()
                    )
                    combinations += 1
    print(f"{combinations} requests in {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
