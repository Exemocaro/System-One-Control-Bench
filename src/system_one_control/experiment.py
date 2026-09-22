from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from system_one_control.game import Game
from system_one_control.players import PLAYERS, Player
from system_one_control.prompt import Prompt
from system_one_control.scenario import Scenario

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"


@dataclass(frozen=True)
class Result:
    scenario: str
    prompt: str
    player: str
    moves_to_goal: int
    first_move: str | None
    first_move_correct: bool
    won: bool
    moves_used: int
    error: str | None


def run_experiment(
    scenarios: Sequence[Scenario],
    prompts: Sequence[Prompt],
    players: Sequence[Player],
    *,
    first_move_only: bool = False,
) -> Iterator[Result]:
    """Every player on every scenario under every prompt."""
    for scenario in scenarios:
        for prompt in prompts:
            for player in players:
                game = Game(scenario, player, prompt)
                steps = [game.step()] if first_move_only else game.play()
                errors = [step.choice.error for step in steps if step.choice.error]
                yield Result(
                    scenario=scenario.name,
                    prompt=prompt.name,
                    player=player.name,
                    moves_to_goal=scenario.moves_to_goal,
                    first_move=steps[0].choice.move,
                    first_move_correct=steps[0].correct,
                    won=game.won,
                    moves_used=len(steps),
                    error=errors[0] if errors else None,
                )


def estimate_paid_calls(
    scenarios: Sequence[Scenario],
    prompts: Sequence[Prompt],
    player_names: Iterable[str],
    *,
    first_move_only: bool,
) -> int:
    """The most calls paid players could make: one per move."""
    paid = sum(1 for name in player_names if PLAYERS[name].paid)
    moves = sum(1 if first_move_only else s.max_moves for s in scenarios)
    return paid * moves * len(prompts)


def save(results: Iterable[Result], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for result in results:
            file.write(json.dumps(asdict(result)) + "\n")
    return path


def summarize(results: Sequence[Result]) -> str:
    """First moves right, by distance to the goal, and games won, per player and prompt."""
    distances = sorted({r.moves_to_goal for r in results})
    groups: dict[tuple[str, str], list[Result]] = defaultdict(list)
    for result in results:
        groups[(result.player, result.prompt)].append(result)

    header = ["player", "prompt", *(f"{d} away" for d in distances), "won"]
    rows = [header]
    for (player, prompt), group in sorted(groups.items()):
        cells = [player, prompt]
        for distance in distances:
            subset = [r for r in group if r.moves_to_goal == distance]
            cells.append(f"{sum(r.first_move_correct for r in subset)}/{len(subset)}")
        cells.append(f"{sum(r.won for r in group)}/{len(group)}")
        rows.append(cells)

    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        for row in rows
    ]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(lines)
