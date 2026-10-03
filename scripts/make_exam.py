"""Make the exam: fixed positions per puzzle (5 each, 4 at level 1) every model answers once.

Seeded; run once, the output is committed. Usage: make_exam.py.
"""

from __future__ import annotations

import random
from collections import Counter

from system_one_control.exam import EXAM_DIR
from system_one_control.exam_items import make_items
from system_one_control.puzzles import load_puzzles

SEED = 0


def main() -> None:
    rng = random.Random(SEED)
    puzzles = load_puzzles()
    all_items, kinds, loose = [], Counter(), 0
    for puzzle in puzzles.values():
        items, fell_back = make_items(puzzle, rng)
        all_items += items
        kinds.update(item.kind for item in items)
        loose += fell_back
    EXAM_DIR.mkdir(parents=True, exist_ok=True)
    path = EXAM_DIR / "items.jsonl"
    with path.open("w", encoding="utf-8", newline="") as file:
        for item in all_items:
            file.write(item.to_json() + "\n")
    print(f"{len(all_items)} items in {path}: {dict(kinds)}, {loose} on seen boards")


if __name__ == "__main__":
    main()
