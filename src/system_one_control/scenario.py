from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from system_one_control.board import Board
from system_one_control.rules import Rules, make_rules

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scenarios"
DEFAULT_MAX_MOVES = 20


@dataclass(frozen=True)
class Scenario:
    """One starting board, the rules it is played under, and its known answer."""

    name: str
    description: str
    board: Board
    rules: Rules
    moves_to_goal: int
    best_first_moves: tuple[str, ...]
    max_moves: int = DEFAULT_MAX_MOVES

    @classmethod
    def load(cls, path: Path) -> Scenario:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            name=path.stem,
            description=data.get("description", ""),
            board=Board.parse(data["map"]),
            rules=make_rules(data.get("rules", "compass")),
            moves_to_goal=int(data["moves_to_goal"]),
            best_first_moves=tuple(data["best_first_moves"]),
            max_moves=int(data.get("max_moves", DEFAULT_MAX_MOVES)),
        )


def load_scenarios(folder: Path = SCENARIO_DIR) -> dict[str, Scenario]:
    """Every scenario in a folder, easiest first."""
    scenarios = sorted(
        (Scenario.load(path) for path in folder.glob("*.yaml")),
        key=lambda s: (s.moves_to_goal, s.name),
    )
    return {scenario.name: scenario for scenario in scenarios}
