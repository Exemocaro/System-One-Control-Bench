"""Ask a player again at the positions of its recorded games and compare the answers.

Every request is rebuilt from the recorded moves with today's code, so this also checks that
the requests have not changed. Report: how many positions got the same move, and how many got
probabilities within 0.001 of the recorded ones.

Usage: replay_check.py <player> <results.jsonl> <conditions, or all> <games> <moves per game>
Example: uv run --extra local python scripts/replay_check.py qwen3.5-4b \
    benchmarks/2026-10-04_18-06_qwen3.5-4b_all_two-moves.jsonl all 40 5
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from system_one_control.bench import Game
from system_one_control.players import PLAYERS
from system_one_control.players.base import Turn
from system_one_control.players.baselines import ScriptedPlayer
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import load_puzzles
from system_one_control.world import make_rules


def main(name: str, path: str, conditions: str, games: int, moves: int) -> None:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    records = [
        r
        for r in records
        if r["player"] == name and (conditions == "all" or r["condition"] in conditions.split(","))
    ]
    records = records[:: max(1, len(records) // games)][:games]
    puzzles = load_puzzles()
    player = PLAYERS[name].build()
    asked = same_move = same_probabilities = 0
    worst = 0.0
    differences = []
    for record in records:
        puzzle = replace(puzzles[record["puzzle"]], rules=make_rules(record["rules"]))
        recorded = [m["move"] for m in record["moves"]]
        game = Game(puzzle, ScriptedPlayer(recorded), CONDITIONS[record["condition"]])
        for number, move in enumerate(record["moves"][:moves], start=1):
            if move["move"] is None or game.is_over:
                break
            request = game.next_request()
            assert [o.move for o in request.options] == move["options"], "option order differs"
            choice = player.choose(Turn(game.board, game.rules, request))
            asked += 1
            same_move += choice.move == move["move"]
            if choice.probabilities and move["probabilities"]:
                gap = max(
                    abs(choice.probabilities.get(option, 0) - p)
                    for option, p in move["probabilities"].items()
                )
                worst = max(worst, gap)
                same_probabilities += gap < 1e-3
                if gap >= 1e-3:
                    differences.append((record["puzzle"], record["condition"], number, gap))
            elif choice.move != move["move"]:
                differences.append((record["puzzle"], record["condition"], number, None))
            game.play_move()
    player.close()
    print(
        f"{name}: {len(records)} games, {asked} positions, same move {same_move}/{asked}, "
        f"probabilities within 0.001 {same_probabilities}/{asked}, largest gap {worst:.4f}"
    )
    for difference in differences[:15]:
        print("  ", difference)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
