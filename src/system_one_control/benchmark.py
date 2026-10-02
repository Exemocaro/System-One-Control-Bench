from __future__ import annotations

import json
import threading
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import typer

from system_one_control.game import Game, Step
from system_one_control.players import PLAYERS, Player
from system_one_control.prompts import Condition
from system_one_control.puzzles import Scenario
from system_one_control.world import make_rules

BENCHMARK_DIR = Path(__file__).resolve().parents[2] / "benchmarks"
CEILING = "solver"  # plays perfectly, so it is never the best result worth pointing out

GameKey = tuple[str, str, str]  # scenario, condition, player


@dataclass(frozen=True)
class MoveRecord:
    """One move: the options in the order shown, the answer, and how good it was."""

    options: tuple[str, ...]
    move: str | None
    probabilities: dict[str, float]
    best_moves: tuple[str, ...]
    optimal: bool
    input_tokens: int | None
    # Added on 23 September; games saved before then load with these empty.
    output_tokens: int | None = None
    confidence: float | None = None  # the model's own score, which is not a probability
    model: str | None = None  # the model version that answered
    seconds: float | None = None  # how long the answer took; for Jev, the answering call alone
    retried: tuple[str, ...] = ()  # why each earlier attempt at this move was turned away
    cost: float | None = None  # in US dollars, where the provider reports it; added 24 September


@dataclass(frozen=True)
class GameRecord:
    """One game: a player on a scenario under a condition, and every move it made."""

    scenario: str
    condition: str
    player: str
    moves_to_goal: int
    won: bool
    closest: int | None  # the fewest moves to the goal from any board the player reached
    error: str | None
    moves: tuple[MoveRecord, ...]
    rules: str = "compass"  # added on 24 September, when other rules came in

    @property
    def key(self) -> GameKey:
        return (self.scenario, self.condition, self.player)

    @property
    def fewest_moves(self) -> int:
        """The fewest moves that win under the game's rules; moves_to_goal counts compass ones."""
        return make_rules(self.rules).moves_for(self.moves_to_goal)

    @property
    def progress(self) -> float:
        """How much of the way to the goal the game covered at its closest: 1 for a win."""
        if self.closest is None:
            return 0.0
        return 1 - self.closest / self.moves_to_goal

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, line: str) -> GameRecord:
        data = json.loads(line)
        moves = tuple(
            MoveRecord(
                **{
                    **move,
                    "options": tuple(move["options"]),
                    "best_moves": tuple(move["best_moves"]),
                    "retried": tuple(move.get("retried", ())),
                }
            )
            for move in data.pop("moves")
        )
        return cls(**data, moves=moves)


def game_keys(
    scenarios: Sequence[Scenario], conditions: Sequence[Condition], players: Iterable[str]
) -> list[GameKey]:
    """Every game a benchmark plays, in the order its records are kept."""
    names = list(players)
    return [(s.name, c.name, name) for s in scenarios for c in conditions for name in names]


def play(
    scenario: Scenario,
    condition: Condition,
    name: str,
    player: Player,
    stop: threading.Event | None = None,
) -> GameRecord | None:
    """One game, or None if `stop` was set before it finished."""
    game = Game(scenario, player, condition)
    try:
        steps = game.play(stop)
    finally:
        player.close()
    if not game.is_over:
        return None
    errors = [step.choice.error for step in steps if step.choice.error]
    return GameRecord(
        scenario=scenario.name,
        condition=condition.name,
        player=name,
        moves_to_goal=scenario.moves_to_goal,
        won=game.won,
        closest=game.closest,
        error=errors[0] if errors else None,
        rules=scenario.rules.name,
        moves=tuple(
            MoveRecord(
                options=tuple(option.move for option in step.request.options),
                move=step.choice.move,
                probabilities=step.choice.probabilities,
                best_moves=step.best_moves,
                optimal=step.optimal,
                input_tokens=step.choice.input_tokens,
                output_tokens=step.choice.output_tokens,
                confidence=step.choice.confidence,
                model=step.choice.model,
                seconds=answer_time(step),
                retried=step.choice.retried,
                cost=step.choice.cost,
            )
            for step in steps
        ),
    )


def answer_time(step: Step) -> float:
    """The player's own time for its answer where it keeps one, else the whole move's."""
    return round(step.seconds if step.choice.seconds is None else step.choice.seconds, 3)


def run_benchmark(
    scenarios: Sequence[Scenario],
    conditions: Sequence[Condition],
    players: Mapping[str, Callable[[], Player]],
    *,
    workers: int = 1,
    done: Collection[GameKey] = (),
    on_record: Callable[[GameRecord], None] | None = None,
) -> list[GameRecord]:
    """Every player on every scenario under every condition, `workers` games at a time.

    Each game gets a fresh player, so games never share state and can run side by side.
    Games in `done` are skipped. `on_record` gets each game as it finishes, so a caller can
    save it straight away. A player's failed move ends only its own game, as an error. Any
    other failure starts no more games, stops those under way after their current move
    without recording them, hands over any that finished meanwhile, and is then raised.
    Ctrl+C does the same, without waiting for the games under way.

    Returns the games played, in the order of scenarios, then conditions, then players.
    """
    by_name = {s.name: s for s in scenarios}
    by_condition = {c.name: c for c in conditions}
    keys = [key for key in game_keys(scenarios, conditions, players) if key not in done]
    stop = threading.Event()

    def play_one(key: GameKey) -> GameRecord | None:
        if stop.is_set():
            return None
        scenario, condition, name = key
        try:
            player = players[name]()
            return play(by_name[scenario], by_condition[condition], name, player, stop)
        except BaseException:
            stop.set()
            raise

    pool = ThreadPoolExecutor(max_workers=workers)
    futures = [pool.submit(play_one, key) for key in keys]
    records: dict[GameKey, GameRecord] = {}
    failure: BaseException | None = None
    try:
        for future in as_completed(futures):
            try:
                record = future.result()
            except CancelledError:
                continue
            except Exception as error:
                failure = failure or error
                pool.shutdown(wait=False, cancel_futures=True)
                continue
            if record is not None:
                records[record.key] = record
                if on_record:
                    on_record(record)
        if failure:
            raise failure
    finally:
        stop.set()
        pool.shutdown(wait=False, cancel_futures=True)
    return [records[key] for key in keys]


def estimate_paid_calls(
    scenarios: Sequence[Scenario],
    conditions: Sequence[Condition],
    player_names: Iterable[str],
    *,
    done: Collection[GameKey] = (),
) -> int:
    """The most calls paid players could make on the games not yet done: one per move."""
    moves = {s.name: s.max_moves for s in scenarios}
    return sum(
        moves[scenario]
        for scenario, condition, name in game_keys(scenarios, conditions, player_names)
        if PLAYERS[name].paid and (scenario, condition, name) not in done
    )


def save(records: Iterable[GameRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        for record in records:
            file.write(record.to_json() + "\n")
    return path


def load(path: Path) -> list[GameRecord]:
    """The games saved in a file. A cut-off last line, from a run that was killed, is skipped."""
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    records = []
    for number, line in enumerate(lines, start=1):
        try:
            records.append(GameRecord.from_json(line))
        except json.JSONDecodeError:
            if number < len(lines):
                raise
    return records


def summarize(records: Sequence[GameRecord], *, bold_best: bool = False) -> str:
    """Per player and condition: the games won at each level, then scores over all games.

    Won counts the games that reached the goal; progress is how much of the way to the goal a
    game covered at its closest, averaged; SPL (success weighted by path length) scores a won
    game as the fewest moves over the moves used, and a lost one as 0. Levels and progress count
    compass moves under any rules; SPL counts the moves of the game's own rules. Errors counts
    the games a player could not finish, such as a failed API call.

    Rows run from the simple players to the solver, then any other player. With `bold_best`,
    the best score in each column, the solver aside, is in bold.
    """
    levels = sorted({r.moves_to_goal for r in records})
    groups: dict[tuple[str, str], list[GameRecord]] = defaultdict(list)
    for record in records:
        groups[(record.player, record.condition)].append(record)
    order = list(PLAYERS)
    ranked = sorted(groups, key=lambda key: order.index(key[0]) if key[0] in order else len(order))

    header = ["player", "condition", *(f"{d} away" for d in levels), "won", "progress", "SPL"]
    header.append("errors")
    rows: list[tuple[str, str, list[tuple[str, float]], str]] = []  # (text, value) per score
    for player, condition in ranked:
        group = groups[(player, condition)]
        scores: list[tuple[str, float]] = []
        for level in levels:
            at_level = [r for r in group if r.moves_to_goal == level]
            won = sum(r.won for r in at_level)
            scores.append((f"{won}/{len(at_level)}", won))
        won = sum(r.won for r in group)
        progress = sum(r.progress for r in group) / len(group)
        spl = sum(r.fewest_moves / len(r.moves) if r.won else 0.0 for r in group) / len(group)
        scores += [(f"{won}/{len(group)}", won), (f"{progress:.2f}", progress), (f"{spl:.2f}", spl)]
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


def usage(records: Sequence[GameRecord]) -> str:
    """For each paid player: the calls made (one per move), the tokens, and the typical wait."""
    lines = []
    for player in dict.fromkeys(r.player for r in records):
        if player not in PLAYERS or not PLAYERS[player].paid:
            continue
        moves = [move for r in records if r.player == player for move in r.moves]
        tokens = sum(move.input_tokens or 0 for move in moves)
        output = sum(move.output_tokens or 0 for move in moves)
        calls = "1 call" if len(moves) == 1 else f"{len(moves)} calls"
        line = f"{player}: {calls}, {tokens:,} input tokens, {output:,} output tokens"
        seconds = sorted(move.seconds for move in moves if move.seconds is not None)
        if seconds:
            line += f", {seconds[len(seconds) // 2]:.2f} s per call (median)"
        costs = [move.cost for move in moves if move.cost is not None]
        if costs:
            line += f", ${sum(costs):.4f}"
        retries = sum(len(move.retried) for move in moves)
        if retries:
            line += f", {retries} turned away and retried"
        lines.append(line)
    return "\n".join(lines)
