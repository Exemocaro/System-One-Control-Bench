"""Replay every game in every benchmarks/*.jsonl with a ScriptedPlayer and check it.

For each recorded move: the options in the recorded order, the best moves and whether the
move was optimal must match. At the end: won and closest must match. Prints the games
checked and every mismatch; exits 1 on any mismatch. Optional argv: only files whose
name contains the given text.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from system_one_control.bench import Game
from system_one_control.players.baselines import ScriptedPlayer
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import load_puzzles
from system_one_control.world import make_rules

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmarks"


def main(folder: Path = BENCHMARK_DIR, only: str = "") -> None:
    puzzles = load_puzzles()
    solved: dict = {}  # (puzzle, rules): solved distances, worked out once per pair
    checked = mismatches = 0

    def fresh(name: str, rules_name: str, condition: str, moves: list) -> Game:
        puzzle = replace(puzzles[name], rules=make_rules(rules_name))
        game = Game(puzzle, ScriptedPlayer(moves), CONDITIONS[condition])
        key = (name, rules_name)
        if key in solved:
            game._distances, game._step_distances = solved[key]
        else:
            solved[key] = (game._distances, game._step_distances)
        return game

    for path in sorted(folder.glob("*.jsonl")):
        if only and only not in path.name:
            continue
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for line in lines:
            checked += 1
            record = json.loads(line)
            game = fresh(
                record["puzzle"],
                record.get("rules", "compass"),
                record["condition"],
                [m["move"] for m in record["moves"]],
            )
            where = f"{path.name} {record['puzzle']} {record['condition']} {record['player']}"
            for number, move in enumerate(record["moves"], start=1):
                if game.is_over:
                    print(f"{where}: game over before move {number}")
                    mismatches += 1
                    break
                played = game.play_move()
                if [o.move for o in played.request.options] != move["options"]:
                    print(f"{where} move {number}: options differ")
                    mismatches += 1
                best, optimal = list(played.best_moves), played.optimal
                if best != move["best_moves"] or optimal != move["optimal"]:
                    print(f"{where} move {number}: best moves or optimal differ")
                    mismatches += 1
            else:
                if game.won != record["won"] or game.closest != record["closest"]:
                    print(
                        f"{where}: end differs (won {game.won}/{record['won']}, "
                        f"closest {game.closest}/{record['closest']})"
                    )
                    mismatches += 1
    print(f"games checked: {checked}, mismatches: {mismatches}")
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main(only=sys.argv[1] if len(sys.argv) > 1 else "")
