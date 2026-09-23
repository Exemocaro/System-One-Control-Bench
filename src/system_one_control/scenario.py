from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from system_one_control.board import Board
from system_one_control.rules import Rules, make_rules

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "scenarios"
MOVE_ALLOWANCE = 3  # a game ends once it has used this many times the fewest moves


@dataclass(frozen=True)
class Scenario:
    """One starting board, the rules it is played under, and how far the goal is."""

    name: str
    description: str
    board: Board
    rules: Rules
    moves_to_goal: int

    @property
    def max_moves(self) -> int:
        return MOVE_ALLOWANCE * self.moves_to_goal

    @classmethod
    def load(cls, path: Path) -> Scenario:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            name=path.stem,
            description=data.get("description", ""),
            board=Board.parse(data["map"]),
            rules=make_rules(data.get("rules", "compass")),
            moves_to_goal=int(data["moves_to_goal"]),
        )


def load_scenarios(folder: Path = SCENARIO_DIR) -> dict[str, Scenario]:
    """Every scenario under a folder (one subfolder per level), easiest first.

    Scenarios are known by their file name, so two files may not share one.
    """
    paths = sorted(folder.rglob("*.yaml"))
    names = [path.stem for path in paths]
    repeated = sorted({name for name in names if names.count(name) > 1})
    if repeated:
        raise ValueError(f"scenario names used more than once: {', '.join(repeated)}")
    scenarios = sorted(
        (Scenario.load(path) for path in paths), key=lambda s: (s.moves_to_goal, s.name)
    )
    return {scenario.name: scenario for scenario in scenarios}
