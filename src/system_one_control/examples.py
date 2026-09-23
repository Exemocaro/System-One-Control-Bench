from __future__ import annotations

from pathlib import Path

from system_one_control.conditions import CONDITIONS, Condition
from system_one_control.game import Game
from system_one_control.players import ScriptedPlayer
from system_one_control.scenario import Scenario, load_scenarios

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples"
EXAMPLE_SCENARIO = "gen-10-01"
EXAMPLE_MOVES = ("east", "north")  # the second walks into a wall, so the memory shows it


def example(condition: Condition, scenario: Scenario) -> str:
    """Exactly what a player is shown under this condition, two moves into the scenario."""
    game = Game(scenario, ScriptedPlayer(EXAMPLE_MOVES), condition)
    for _ in EXAMPLE_MOVES:
        game.step()
    header = (
        f"# {condition.name}: {condition.description}\n"
        f"# {scenario.name}, after the moves {', '.join(EXAMPLE_MOVES)}\n\n"
    )
    return header + game.next_request().to_text()


def write_examples(folder: Path = EXAMPLE_DIR) -> list[Path]:
    """One file per condition, so anyone can read what each condition shows the player."""
    scenario = load_scenarios()[EXAMPLE_SCENARIO]
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for condition in CONDITIONS.values():
        path = folder / f"{condition.name}.txt"
        path.write_text(example(condition, scenario), encoding="utf-8")
        written.append(path)
    return written
