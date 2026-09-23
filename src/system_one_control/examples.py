from __future__ import annotations

import json
from pathlib import Path

from system_one_control.conditions import CONDITIONS, Condition
from system_one_control.game import Game
from system_one_control.players import ScriptedPlayer, jev_body
from system_one_control.scenario import Scenario, load_scenarios

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_SCENARIO = "gen-10-01"
EXAMPLE_MOVES = ("east", "north")  # the second walks into a wall, so the memory shows it


def example(condition: Condition, scenario: Scenario) -> str:
    """The JSON body sent to Jev under this condition, two moves into the scenario."""
    game = Game(scenario, ScriptedPlayer(EXAMPLE_MOVES), condition)
    for _ in EXAMPLE_MOVES:
        game.step()
    return json.dumps(jev_body(game.next_request()), indent=2, ensure_ascii=False) + "\n"


def write_examples(folder: Path = EXAMPLE_DIR) -> list[Path]:
    """One file per condition, so anyone can read what each condition sends Jev."""
    scenario = load_scenarios()[EXAMPLE_SCENARIO]
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for condition in CONDITIONS.values():
        path = folder / f"{condition.name}.json"
        path.write_text(example(condition, scenario), encoding="utf-8", newline="\n")
        written.append(path)
    return written
