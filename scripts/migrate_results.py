"""Rename `scenario` to `puzzle` and `moves_to_goal` to `level` in every results file.

Reads each benchmarks/*.jsonl and writes it back with only those two keys renamed, in
place and in order. Every file is parsed and renamed before any file is written, so a
record that is not in the old shape fails the run without writing anything. Run once,
then commit the files separately.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmarks"
NAMES = {"scenario": "puzzle", "moves_to_goal": "level"}


def migrate_record(data: dict) -> dict:
    """The same record with the two renamed keys, everything else untouched."""
    if "scenario" not in data or "moves_to_goal" not in data:
        raise ValueError(f"not an old-shape record: {sorted(data)}")
    if "puzzle" in data or "level" in data:
        raise ValueError(f"already migrated: {sorted(data)}")
    return {NAMES.get(key, key): value for key, value in data.items()}


def read_migrated(path: Path) -> list[dict]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [migrate_record(json.loads(line)) for line in lines]


def write_records(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")


def main(folder: Path = BENCHMARK_DIR) -> None:
    paths = sorted(folder.glob("*.jsonl"))
    migrated = [(path, read_migrated(path)) for path in paths]
    for path, records in migrated:
        write_records(path, records)
    for path, records in migrated:
        print(f"{path.name}: {len(records)} games")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else BENCHMARK_DIR)
