from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from system_one_control.game import Game, Step
from system_one_control.players import PLAYERS, Player
from system_one_control.prompt import Prompt
from system_one_control.scenario import Scenario

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"


@dataclass(frozen=True)
class MoveResult:
    """One move: the options in the order shown, the answer, and how good it was."""

    options: tuple[str, ...]
    move: str | None
    probabilities: dict[str, float]
    best_moves: tuple[str, ...]
    correct: bool

    @classmethod
    def of(cls, step: Step) -> MoveResult:
        return cls(
            options=tuple(option.move for option in step.request.options),
            move=step.choice.move,
            probabilities=step.choice.probabilities,
            best_moves=step.best_moves,
            correct=step.correct,
        )


@dataclass(frozen=True)
class Result:
    """One game: a player on a scenario under a prompt, and every move it made."""

    scenario: str
    prompt: str
    player: str
    moves_to_goal: int
    won: bool
    error: str | None
    moves: tuple[MoveResult, ...]


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
                    won=game.won,
                    error=errors[0] if errors else None,
                    moves=tuple(MoveResult.of(step) for step in steps),
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
    """Per player and prompt: games won at each distance to the goal, then overall.

    Optimal is the share of all moves that started a shortest path. SPL (success weighted by
    path length) scores a won game as the fewest moves over the moves used, and a lost one as 0.
    """
    distances = sorted({r.moves_to_goal for r in results})
    groups: dict[tuple[str, str], list[Result]] = defaultdict(list)
    for result in results:
        groups[(result.player, result.prompt)].append(result)

    header = ["player", "prompt", *(f"{d} away" for d in distances), "won", "optimal", "SPL"]
    rows = [header]
    for (player, prompt), group in sorted(groups.items()):
        cells = [player, prompt]
        for distance in distances:
            subset = [r for r in group if r.moves_to_goal == distance]
            cells.append(f"{sum(r.won for r in subset)}/{len(subset)}")
        moves = [move for r in group for move in r.moves]
        spl = [r.moves_to_goal / len(r.moves) if r.won else 0.0 for r in group]
        cells.append(f"{sum(r.won for r in group)}/{len(group)}")
        cells.append(f"{sum(m.correct for m in moves) / len(moves):.0%}")
        cells.append(f"{sum(spl) / len(spl):.2f}")
        rows.append(cells)

    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        for row in rows
    ]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(lines)
