"""One game: a player working through a puzzle, and the runs that play and score every game."""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import typer

from system_one_control.players import PLAYERS, Choice, Player, Turn
from system_one_control.prompts import Condition, Request
from system_one_control.puzzles import Puzzle
from system_one_control.world import Board, Rules, Solver, make_rules

BENCHMARK_DIR = Path(__file__).resolve().parents[2] / "benchmarks"
CEILING = "solver"  # plays perfectly, so it is never the best result worth pointing out

GameKey = tuple[str, str, str]  # puzzle, condition, player


@dataclass(frozen=True)
class Played:
    """One move a game played: what was shown, what was answered, and where it led."""

    number: int
    before: Board
    request: Request
    choice: Choice
    best_moves: tuple[str, ...]
    after: Board
    seconds: float

    @property
    def optimal(self) -> bool:
        return self.choice.move in self.best_moves


class Game:
    """One player working through one puzzle, a move at a time."""

    def __init__(self, puzzle: Puzzle, player: Player, condition: Condition) -> None:
        self.puzzle = puzzle
        self.player = player
        self.condition = condition
        self.solver = Solver(puzzle.rules)
        self.board = puzzle.board
        # Worked out once: the distances from the start cover every board the game can reach.
        self._distances = self.solver.distances(self.board)
        # Counted in the moves a level is counted in, which may be shorter than these rules'.
        self._step_distances = Solver(puzzle.rules.step_rules()).distances(self.board)
        self.moves: list[Played] = []

    @property
    def rules(self) -> Rules:
        return self.puzzle.rules

    @property
    def won(self) -> bool:
        return self.rules.is_won(self.board)

    @property
    def closest(self) -> int | None:
        """The fewest moves to the goal from any board reached so far, the start included.

        Counted in the moves a level is counted in, so it compares across rules, and taking in
        every board a move passed through, not only the one it ended on.
        """
        boards = {self.puzzle.board}
        for each in self.moves:
            move = self.rules.find_move(each.before, each.choice.move)
            if move is not None:
                boards.update(self.rules.passes(each.before, move))
        distances = (self._step_distances.get(board) for board in boards)
        return min((d for d in distances if d is not None), default=None)

    def best_moves(self, board: Board) -> tuple[str, ...]:
        """Every move from a board of this game that starts a shortest path."""
        return self.solver.best_moves(board, self._distances)

    @property
    def is_over(self) -> bool:
        failed = bool(self.moves) and self.moves[-1].choice.move is None
        return self.won or failed or len(self.moves) >= self.puzzle.max_moves

    def next_request(self) -> Request:
        memory = [
            f"{each.choice.move}: {self.rules.describe_outcome(each.before, each.after)}"
            for each in self.moves
        ]
        seed = f"{self.puzzle.name}:{len(self.moves) + 1}"
        return self.condition.render(self.board, self.rules, shuffle_seed=seed, memory=memory)

    def play_move(self) -> Played:
        if self.is_over:
            raise RuntimeError("the game is over")
        request = self.next_request()
        started = time.perf_counter()
        try:
            choice = self.player.choose(Turn(self.board, self.rules, request))
        except Exception as error:  # a player that fails has failed this move, not the run
            choice = Choice(None, error=f"{type(error).__name__}: {error}")
        seconds = time.perf_counter() - started

        move = self.rules.find_move(self.board, choice.move)
        if move is None and choice.move is not None:
            choice = replace(choice, move=None, error=f"{choice.move!r} is not an allowed move")
        after = self.board if move is None else self.rules.apply(self.board, move)

        played = Played(
            number=len(self.moves) + 1,
            before=self.board,
            request=request,
            choice=choice,
            best_moves=self.best_moves(self.board),
            after=after,
            seconds=seconds,
        )
        self.moves.append(played)
        self.board = after
        return played

    def play(self, stop: threading.Event | None = None) -> list[Played]:
        """Play to the end, or until `stop` is set, which takes effect between moves."""
        while not self.is_over and not (stop and stop.is_set()):
            self.play_move()
        return self.moves


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
    """One game: a player on a puzzle under a condition, and every move it made."""

    puzzle: str
    condition: str
    player: str
    level: int
    won: bool
    closest: int | None  # the fewest moves to the goal from any board the player reached
    error: str | None
    moves: tuple[MoveRecord, ...]
    rules: str = "compass"  # added on 24 September, when other rules came in

    @property
    def key(self) -> GameKey:
        return (self.puzzle, self.condition, self.player)

    @property
    def fewest_moves(self) -> int:
        """The fewest moves that win under the game's rules; the level counts compass ones."""
        return make_rules(self.rules).moves_for(self.level)

    @property
    def progress(self) -> float:
        """How much of the way to the goal the game covered at its closest: 1 for a win."""
        if self.closest is None:
            return 0.0
        return 1 - self.closest / self.level

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
    puzzles: Sequence[Puzzle], conditions: Sequence[Condition], players: Iterable[str]
) -> list[GameKey]:
    """Every game a benchmark plays, in the order its records are kept."""
    names = list(players)
    return [(p.name, c.name, name) for p in puzzles for c in conditions for name in names]


def record_of(played: Played) -> MoveRecord:
    """One played move as a saved move record."""
    return MoveRecord(
        options=tuple(option.move for option in played.request.options),
        move=played.choice.move,
        probabilities=played.choice.probabilities,
        best_moves=played.best_moves,
        optimal=played.optimal,
        input_tokens=played.choice.input_tokens,
        output_tokens=played.choice.output_tokens,
        confidence=played.choice.confidence,
        model=played.choice.model,
        seconds=answer_time(played),
        retried=played.choice.retried,
        cost=played.choice.cost,
    )


def play_game(
    puzzle: Puzzle,
    condition: Condition,
    name: str,
    player: Player,
    stop: threading.Event | None = None,
) -> GameRecord | None:
    """One game, or None if `stop` was set before it finished."""
    game = Game(puzzle, player, condition)
    try:
        moves_played = game.play(stop)
    finally:
        player.close()
    if not game.is_over:
        return None
    errors = [each.choice.error for each in moves_played if each.choice.error]
    return GameRecord(
        puzzle=puzzle.name,
        condition=condition.name,
        player=name,
        level=puzzle.level,
        won=game.won,
        closest=game.closest,
        error=errors[0] if errors else None,
        rules=puzzle.rules.name,
        moves=tuple(record_of(each) for each in moves_played),
    )


def answer_time(played: Played) -> float:
    """The player's own time for its answer where it keeps one, else the whole move's."""
    return round(played.seconds if played.choice.seconds is None else played.choice.seconds, 3)


def run_benchmark(
    puzzles: Sequence[Puzzle],
    conditions: Sequence[Condition],
    players: Mapping[str, Callable[[], Player]],
    *,
    workers: int = 1,
    done: Collection[GameKey] = (),
    on_record: Callable[[GameRecord], None] | None = None,
) -> list[GameRecord]:
    """Every player on every puzzle under every condition, `workers` games at a time.

    Each game gets a fresh player, so games never share state and can run side by side.
    Games in `done` are skipped. `on_record` gets each game as it finishes, so a caller can
    save it straight away. A player's failed move ends only its own game, as an error. Any
    other failure starts no more games, stops those under way after their current move
    without recording them, hands over any that finished meanwhile, and is then raised.
    Ctrl+C does the same, without waiting for the games under way.

    Returns the games played, in the order of puzzles, then conditions, then players.
    """
    by_name = {p.name: p for p in puzzles}
    by_condition = {c.name: c for c in conditions}
    keys = [key for key in game_keys(puzzles, conditions, players) if key not in done]
    stop = threading.Event()

    def play_one(key: GameKey) -> GameRecord | None:
        if stop.is_set():
            return None
        puzzle, condition, name = key
        try:
            player = players[name]()
            return play_game(by_name[puzzle], by_condition[condition], name, player, stop)
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
    puzzles: Sequence[Puzzle],
    conditions: Sequence[Condition],
    player_names: Iterable[str],
    *,
    done: Collection[GameKey] = (),
) -> int:
    """The most calls paid players could make on the games not yet done: one per move."""
    moves = {p.name: p.max_moves for p in puzzles}
    return sum(
        moves[puzzle]
        for puzzle, condition, name in game_keys(puzzles, conditions, player_names)
        if PLAYERS[name].paid and (puzzle, condition, name) not in done
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


def split_finished(records: Sequence[GameRecord]) -> tuple[list[GameRecord], list[GameRecord]]:
    """The records split two ways: the finished games to keep, the errored ones to play again."""
    kept = [record for record in records if record.error is None]
    return kept, [record for record in records if record.error is not None]


def check_same_run(
    loaded: Sequence[GameRecord], keys: Collection[GameKey], rules_of: Mapping[str, str]
) -> str | None:
    """Why a results file cannot be resumed by this run, or None if it can."""
    wanted = set(keys)
    strays = [record.key for record in loaded if record.key not in wanted]
    if strays:
        return (
            f"holds games this run would not play, such as {strays[0]}; "
            "resume with the same --players, --levels, --puzzles and --conditions"
        )
    other = next((r for r in loaded if r.rules != rules_of[r.puzzle]), None)
    if other:
        return f"holds games played under {other.rules} rules; resume with the same --rules"
    return None


@dataclass(frozen=True)
class Scores:
    """One group's numbers: the games won at each level, then the scores over all games."""

    by_level: dict[int, tuple[int, int]]  # level: (won, played)
    won: int
    played: int
    progress: float
    spl: float
    errors: int


def scores(records: Sequence[GameRecord]) -> dict[tuple[str, str], Scores]:
    """The numbers behind `summarize`, per (player, condition)."""
    groups: dict[tuple[str, str], list[GameRecord]] = defaultdict(list)
    for record in records:
        groups[(record.player, record.condition)].append(record)
    return {key: _score(group) for key, group in groups.items()}


def _score(group: Sequence[GameRecord]) -> Scores:
    at_level: dict[int, list[GameRecord]] = defaultdict(list)
    for record in group:
        at_level[record.level].append(record)
    return Scores(
        by_level={
            level: (sum(r.won for r in records), len(records))
            for level, records in at_level.items()
        },
        won=sum(r.won for r in group),
        played=len(group),
        progress=sum(r.progress for r in group) / len(group),
        spl=sum(r.fewest_moves / len(r.moves) if r.won else 0.0 for r in group) / len(group),
        errors=sum(r.error is not None for r in group),
    )


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
    levels = sorted({r.level for r in records})
    all_scores = scores(records)
    order = list(PLAYERS)
    ranked = sorted(
        all_scores, key=lambda key: order.index(key[0]) if key[0] in order else len(order)
    )

    header = ["player", "condition", *(f"{d} away" for d in levels), "won", "progress", "SPL"]
    header.append("errors")
    rows: list[tuple[str, str, list[tuple[str, float]], str]] = []  # (text, value) per score
    for player, condition in ranked:
        group = all_scores[(player, condition)]
        cells: list[tuple[str, float]] = []
        for level in levels:
            won, played = group.by_level.get(level, (0, 0))
            cells.append((f"{won}/{played}", won))
        cells += [
            (f"{group.won}/{group.played}", group.won),
            (f"{group.progress:.2f}", group.progress),
            (f"{group.spl:.2f}", group.spl),
        ]
        rows.append((player, condition, cells, str(group.errors)))

    contenders = [cells for player, _, cells, _ in rows if player != CEILING]
    best = [max((cells[i][1] for cells in contenders), default=0.0) for i in range(len(header) - 3)]
    texts = [header, *([p, c, *(text for text, _ in s), e] for p, c, s, e in rows)]
    widths = [max(len(row[i]) for row in texts) for i in range(len(header))]

    def line(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths, strict=True))

    lines = [line(header), line(["-" * width for width in widths])]
    for player, condition, cells, errors in rows:
        shown = [player.ljust(widths[0]), condition.ljust(widths[1])]
        for (text, value), top, width in zip(cells, best, widths[2:-1], strict=True):
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
