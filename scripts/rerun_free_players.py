"""Rerun the free players with the new code and compare against the saved files.

Covers random, greedy, greedy-walls and solver under compass/map, and random+solver under
each other rules. Results must equal the saved games except the per-move seconds (timing).
Prints one line per file; exits 1 on any other difference.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from system_one_control.bench import GameRecord, run_benchmark
from system_one_control.players import PLAYERS
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import load_puzzles
from system_one_control.world import make_rules

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmarks"
RUNS = [
    (
        "2026-09-23_21-49_random+greedy+greedy-walls+solver_map.jsonl",
        ["random", "greedy", "greedy-walls", "solver"],
        "compass",
    ),
    ("2026-09-24_00-09_random+solver_map_two-moves.jsonl", ["random", "solver"], "two-moves"),
    ("2026-09-24_00-22_random+solver_map_three-moves.jsonl", ["random", "solver"], "three-moves"),
    (
        "2026-09-26_12-43_random+solver_map_up-to-two-moves.jsonl",
        ["random", "solver"],
        "up-to-two-moves",
    ),
    (
        "2026-09-26_12-44_random+solver_map_up-to-three-moves.jsonl",
        ["random", "solver"],
        "up-to-three-moves",
    ),
]


def untimed(record: GameRecord) -> GameRecord:
    """A game without its timing: per-move seconds are never equal between runs."""
    return replace(record, moves=tuple(replace(m, seconds=None) for m in record.moves))


def field_diffs(a: GameRecord, b: GameRecord) -> list[str]:
    """Top-level fields that differ, with per-move differences folded into 'moves'."""
    fields = a.__dataclass_fields__.values()
    return [f.name for f in fields if getattr(a, f.name) != getattr(b, f.name)]


def main() -> None:
    puzzles = load_puzzles()
    failures = 0
    for filename, names, rules_name in RUNS:
        path = BENCHMARK_DIR / filename
        old = [
            untimed(GameRecord.from_json(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        played = [replace(p, rules=make_rules(rules_name)) for p in puzzles.values()]
        new = run_benchmark(
            played, [CONDITIONS["map"]], {name: PLAYERS[name].build for name in names}, workers=8
        )
        assert [r.key for r in new] == [r.key for r in old]
        fresh = [untimed(record) for record in new]
        diffs = 0
        for saved, rerun in zip(old, fresh, strict=True):
            if saved != rerun:
                diffs += 1
                print(f"{filename} {saved.key}: differs in {field_diffs(saved, rerun)}")
        print(f"{filename}: {len(old)} games, differences besides timing: {diffs}")
        failures += diffs
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
