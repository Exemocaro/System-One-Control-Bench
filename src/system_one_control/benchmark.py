from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import typer

from system_one_control.conditions import Condition
from system_one_control.game import Game, Step
from system_one_control.players import PLAYERS, Player
from system_one_control.scenario import Scenario

BENCHMARK_DIR = Path(__file__).resolve().parents[2] / "benchmarks"
CEILING = "solver"  # plays perfectly, so it is never the best result worth pointing out


@dataclass(frozen=True)
class MoveRecord:
    """One move: the options in the order shown, the answer, and how good it was."""

    options: tuple[str, ...]
    move: str | None
    probabilities: dict[str, float]
    best_moves: tuple[str, ...]
    optimal: bool
    input_tokens: int | None

    @classmethod
    def of(cls, step: Step) -> MoveRecord:
        return cls(
            options=tuple(option.move for option in step.request.options),
            move=step.choice.move,
            probabilities=step.choice.probabilities,
            best_moves=step.best_moves,
            optimal=step.optimal,
            input_tokens=step.choice.input_tokens,
        )


@dataclass(frozen=True)
class GameRecord:
    """One game: a player on a scenario under a condition, and every move it made."""

    scenario: str
    condition: str
    player: str
    moves_to_goal: int
    won: bool
    error: str | None
    moves: tuple[MoveRecord, ...]


def play(
    scenario: Scenario, condition: Condition, player: Player, first_move_only: bool
) -> GameRecord:
    game = Game(scenario, player, condition)
    steps = [game.step()] if first_move_only else game.play()
    errors = [step.choice.error for step in steps if step.choice.error]
    return GameRecord(
        scenario=scenario.name,
        condition=condition.name,
        player=player.name,
        moves_to_goal=scenario.moves_to_goal,
        won=game.won,
        error=errors[0] if errors else None,
        moves=tuple(MoveRecord.of(step) for step in steps),
    )


def run_benchmark(
    scenarios: Sequence[Scenario],
    conditions: Sequence[Condition],
    players: Sequence[Callable[[], Player]],
    *,
    first_move_only: bool = False,
    workers: int = 1,
) -> list[GameRecord]:
    """Every player on every scenario under every condition, `workers` games at a time.

    Each game gets a fresh player, so games never share state and can run side by side.
    """
    games = [(s, c, build) for s in scenarios for c in conditions for build in players]

    def play_one(game: tuple[Scenario, Condition, Callable[[], Player]]) -> GameRecord:
        scenario, condition, build = game
        return play(scenario, condition, build(), first_move_only)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(play_one, games))


def estimate_paid_calls(
    scenarios: Sequence[Scenario],
    conditions: Sequence[Condition],
    player_names: Iterable[str],
    *,
    first_move_only: bool,
) -> int:
    """The most calls paid players could make: one per move."""
    paid = sum(1 for name in player_names if PLAYERS[name].paid)
    moves = sum(1 if first_move_only else s.max_moves for s in scenarios)
    return paid * moves * len(conditions)


def save(records: Iterable[GameRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(asdict(record)) + "\n")
    return path


def summarize(
    records: Sequence[GameRecord], *, first_move_only: bool = False, bold_best: bool = False
) -> str:
    """Per player and condition: how it did at each distance to the goal, then overall.

    For whole games, each distance counts the games won; optimal is the share of all moves that
    started a shortest path; SPL (success weighted by path length) scores a won game as the
    fewest moves over the moves used, and a lost one as 0. With `first_move_only`, each distance
    counts the optimal first moves instead, and won and SPL, which mean nothing after one move,
    are left out. Errors counts the games a player could not finish, such as a failed API call.

    Rows run from the simple players to the solver, then any other player. With `bold_best`,
    the best score in each column, the solver aside, is in bold.
    """
    distances = sorted({r.moves_to_goal for r in records})
    groups: dict[tuple[str, str], list[GameRecord]] = defaultdict(list)
    for record in records:
        groups[(record.player, record.condition)].append(record)
    order = list(PLAYERS)
    ranked = sorted(groups, key=lambda key: order.index(key[0]) if key[0] in order else len(order))

    totals = ["optimal"] if first_move_only else ["won", "optimal", "SPL"]
    header = ["player", "condition", *(f"{d} away" for d in distances), *totals, "errors"]
    rows: list[tuple[str, str, list[tuple[str, float]], str]] = []  # (text, value) per score
    for player, condition in ranked:
        group = groups[(player, condition)]
        scores = [_level_score(group, distance, first_move_only) for distance in distances]
        moves = [move for r in group for move in r.moves]
        optimal = sum(m.optimal for m in moves) / len(moves)
        if not first_move_only:
            won = sum(r.won for r in group)
            scores.append((f"{won}/{len(group)}", won))
        scores.append((f"{optimal:.0%}", optimal))
        if not first_move_only:
            spl = sum(r.moves_to_goal / len(r.moves) if r.won else 0.0 for r in group) / len(group)
            scores.append((f"{spl:.2f}", spl))
        errors = str(sum(r.error is not None for r in group))
        rows.append((player, condition, scores, errors))

    contenders = [scores for player, _, scores, _ in rows if player != CEILING]
    best = [
        max((scores[i][1] for scores in contenders), default=0.0) for i in range(len(header) - 3)
    ]
    texts = [header, *([p, c, *(text for text, _ in s), e] for p, c, s, e in rows)]
    widths = [max(len(row[i]) for row in texts) for i in range(len(header))]

    def line(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths, strict=True))

    lines = [line(header), line(["-" * width for width in widths])]
    for player, condition, scores, errors in rows:
        shown = [player.ljust(widths[0]), condition.ljust(widths[1])]
        for (text, value), top, width in zip(scores, best, widths[2:-1], strict=True):
            cell = text.ljust(width)
            if bold_best and player != CEILING and value == top and value > 0:
                cell = typer.style(cell, bold=True)
            shown.append(cell)
        shown.append(errors.ljust(widths[-1]))
        lines.append("  ".join(shown))
    return "\n".join(lines)


def _level_score(
    group: Sequence[GameRecord], distance: int, first_move_only: bool
) -> tuple[str, float]:
    """Games won at this distance, or optimal first moves when only first moves were asked."""
    at_distance = [r for r in group if r.moves_to_goal == distance]
    if first_move_only:
        count = sum(r.moves[0].optimal for r in at_distance)
    else:
        count = sum(r.won for r in at_distance)
    return f"{count}/{len(at_distance)}", count


def usage(records: Sequence[GameRecord]) -> str:
    """For each paid player: the calls made, one per move, and the input tokens billed."""
    lines = []
    for player in dict.fromkeys(r.player for r in records):
        if player not in PLAYERS or not PLAYERS[player].paid:
            continue
        moves = [move for r in records if r.player == player for move in r.moves]
        tokens = sum(move.input_tokens or 0 for move in moves)
        calls = "1 call" if len(moves) == 1 else f"{len(moves)} calls"
        lines.append(f"{player}: {calls}, {tokens:,} input tokens")
    return "\n".join(lines)
