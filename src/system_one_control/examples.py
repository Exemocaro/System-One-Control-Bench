from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from system_one_control.conditions import CONDITIONS, Condition
from system_one_control.game import Game
from system_one_control.players import ScriptedPlayer, jev_body
from system_one_control.rules import CompassRules, Rules
from system_one_control.scenario import Scenario, load_scenarios

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_SCENARIO = "gen-10-01"
# Two moves under each rules; the second walks into a wall, so the memory shows it.
EXAMPLE_MOVES = {
    "compass": ("east", "north"),
    "two-moves": ("east,south", "north,north"),
    "three-moves": ("east,south,west", "north,north,north"),
}


def example(condition: Condition, scenario: Scenario) -> str:
    """The JSON body sent to Jev under this condition, two moves into the scenario."""
    moves = EXAMPLE_MOVES[scenario.rules.name]
    game = Game(scenario, ScriptedPlayer(moves), condition)
    for _ in moves:
        game.step()
    return json.dumps(jev_body(game.next_request()), indent=2, ensure_ascii=False) + "\n"


def write_examples(folder: Path = EXAMPLE_DIR, rules: Rules | None = None) -> list[Path]:
    """One file per condition, so anyone can read what each condition sends Jev.

    Rules other than compass get a subfolder of their own.
    """
    scenario = load_scenarios()[EXAMPLE_SCENARIO]
    if rules is not None and not isinstance(rules, CompassRules):
        scenario = replace(scenario, rules=rules)
        folder = folder / rules.name
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for condition in CONDITIONS.values():
        path = folder / f"{condition.name}.json"
        path.write_text(example(condition, scenario), encoding="utf-8", newline="\n")
        written.append(path)
    return written
