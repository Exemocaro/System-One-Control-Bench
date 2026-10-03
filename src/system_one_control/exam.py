"""Fixed-state evaluation: every model answers the same positions, once each."""

from __future__ import annotations

import json
import random
import threading
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from system_one_control.bench import (
    Game,
    MoveRecord,
    load_lines,
    record_of,
    run_pool,
    save_lines,
)
from system_one_control.players import Player
from system_one_control.players.baselines import ScriptedPlayer
from system_one_control.prompts import Condition
from system_one_control.puzzles import Puzzle
from system_one_control.world import COMPASS, Board, Solver, make_rules

EXAM_DIR = Path(__file__).resolve().parents[2] / "exam"
ITEMS_FILE = EXAM_DIR / "items.jsonl"

ExamKey = tuple[str, str, tuple[str, ...], str, str]  # puzzle, kind, prefix, condition, player


@dataclass(frozen=True)
class ExamItem:
    """One exam question: a puzzle plus a prefix of moves played from the start."""

    puzzle: str
    level: int
    kind: str  # start, on-route, off-route, after-blocked or late
    prefix: tuple[str, ...]
    has_key: bool  # carrying the key when answering
    next_to_wall: bool  # some compass move is blocked
    best_moves: tuple[str, ...]  # the solver's best moves when answering
    options: int  # how many options the move offers

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, line: str) -> ExamItem:
        data = json.loads(line)
        return cls(
            **{**data, "prefix": tuple(data["prefix"]), "best_moves": tuple(data["best_moves"])}
        )


@dataclass(frozen=True)
class ExamRecord:
    """One answer: the item, who was asked under which condition, and the move record."""

    item: ExamItem
    condition: str
    player: str
    answer: MoveRecord
    error: str | None  # why there is no answer, when the player failed

    @property
    def key(self) -> ExamKey:
        return (self.item.puzzle, self.item.kind, self.item.prefix, self.condition, self.player)

    def to_json(self) -> str:
        return json.dumps(
            {
                "item": json.loads(self.item.to_json()),
                "condition": self.condition,
                "player": self.player,
                "answer": asdict(self.answer),
                "error": self.error,
            }
        )

    @classmethod
    def from_json(cls, line: str) -> ExamRecord:
        data = json.loads(line)
        answer = {
            **data["answer"],
            "options": tuple(data["answer"]["options"]),
            "best_moves": tuple(data["answer"]["best_moves"]),
            "retried": tuple(data["answer"].get("retried", ())),
        }
        return cls(
            item=ExamItem.from_json(json.dumps(data["item"])),
            condition=data["condition"],
            player=data["player"],
            answer=MoveRecord(**answer),
            error=data["error"],
        )


def examine(
    puzzle: Puzzle, item: ExamItem, condition: Condition, name: str, player: Player
) -> ExamRecord:
    """Ask one player for the move after the item's prefix, played with the ordinary game."""
    game = Game(puzzle, ScriptedPlayer(item.prefix), condition)
    # Players answer once each, so RandomPlayer(seed=0) always takes shuffle position 4,
    # itself a uniform pick over the moves.
    try:
        for _ in item.prefix:
            game.play_move()
        if game.is_over:
            raise RuntimeError(f"the prefix already ends {item.puzzle} {item.kind}")
        # The scripted player plays the prefix, then the real one answers.
        game.player = player
        played = game.play_move()
    finally:
        player.close()
    return ExamRecord(item, condition.name, name, record_of(played), played.choice.error)


def exam_keys(
    items: list[ExamItem], conditions: list[Condition], players: Mapping[str, Callable[[], Player]]
) -> list[ExamKey]:
    """Every answer an exam asks for, in the order its records are kept."""
    return [
        (item.puzzle, item.kind, item.prefix, condition.name, name)
        for item in items
        for condition in conditions
        for name in players
    ]


def run_exam(
    puzzles: Mapping[str, Puzzle],
    items: list[ExamItem],
    conditions: list[Condition],
    players: Mapping[str, Callable[[], Player]],
    *,
    workers: int = 1,
    done: Collection[ExamKey] = (),
    on_record: Callable[[ExamRecord], None] | None = None,
) -> list[ExamRecord]:
    """Every player on every item under every condition, `workers` answers at a time.

    Each answer gets a fresh player. Answers in `done` are skipped. `on_record` gets each
    answer as it finishes. Any other failure stops the run the way `run_benchmark` does.
    Returns the answers played, in the order of items, then conditions, then players.
    """
    compass = {
        name: replace(puzzle, rules=make_rules("compass")) for name, puzzle in puzzles.items()
    }
    by_item = {(item.puzzle, item.kind, item.prefix): item for item in items}
    keys = [key for key in exam_keys(items, conditions, players) if key not in done]
    by_condition = {c.name: c for c in conditions}

    def answer_one(key: ExamKey, stop: threading.Event) -> ExamRecord | None:
        if stop.is_set():
            return None
        puzzle, kind, prefix, condition, name = key
        try:
            item = by_item[(puzzle, kind, prefix)]
            player = players[name]()
            return examine(compass[puzzle], item, by_condition[condition], name, player)
        except BaseException:
            stop.set()
            raise

    finished = run_pool(keys, answer_one, workers=workers, on_record=on_record)
    return [finished[key] for key in keys]


def save_exam(records: Iterable[ExamRecord], path: Path) -> Path:
    return save_lines(path, (record.to_json() for record in records))


def load_exam(path: Path) -> list[ExamRecord]:
    """The answers saved in a file. A cut-off last line, from a run that was killed, is skipped."""
    return load_lines(path, ExamRecord.from_json)


def check_same_exam(loaded: list[ExamRecord], keys: Collection[ExamKey]) -> str | None:
    """Why an answers file cannot be resumed by this run, or None if it can."""
    wanted = set(keys)
    strays = [record.key for record in loaded if record.key not in wanted]
    if strays:
        return (
            f"holds answers this run would not ask, such as {strays[0]}; "
            "resume with the same --players, --conditions and --items"
        )
    return None


SOLVER = Solver(COMPASS)


def shortest_route(board: Board, rng: random.Random) -> list[str]:
    """The solver's route from this board: a best move at a time, ties broken by `rng`."""
    route, here = [], board
    while not COMPASS.is_won(here):
        move = rng.choice(SOLVER.best_moves(here))
        route.append(move)
        here = take_step(here, move)
    return route


def take_step(board: Board, name: str) -> Board:
    """The board after this named compass move, which must be offered."""
    move = COMPASS.find_move(board, name)
    assert move is not None
    return COMPASS.apply(board, move)


def apply_prefix(board: Board, prefix: Sequence[str]) -> Board:
    """The board after these named moves."""
    for name in prefix:
        board = take_step(board, name)
    return board


def won_along(board: Board, prefix: Sequence[str]) -> bool:
    """Whether any board on the way, the last included, already wins."""
    for name in prefix:
        board = take_step(board, name)
        if COMPASS.is_won(board):
            return True
    return False


def base_len(level: int, rng: random.Random) -> int:
    """An on-route base length: 1 to level-1, or 0 where level 1 leaves no choice."""
    return 0 if level == 1 else rng.randrange(1, level)


def on_route_prefix(route: list[str], level: int, rng: random.Random) -> tuple[str, ...] | None:
    """The first k route moves, k drawn from 1 to level-1."""
    if level < 2:
        return None
    return tuple(route[: rng.randrange(1, level)])


def off_route_prefix(
    board: Board, route: list[str], level: int, rng: random.Random
) -> tuple[str, ...] | None:
    """An on-route prefix plus a move that is not best and changes the board."""
    base = route[: base_len(level, rng)]
    end = apply_prefix(board, base)
    best = SOLVER.best_moves(end)
    devs = [
        move.name
        for move in COMPASS.moves(end)
        if move.name not in best and COMPASS.apply(end, move) != end
    ]
    return (*base, rng.choice(devs)) if devs else None


def after_blocked_prefix(
    board: Board, route: list[str], level: int, rng: random.Random
) -> tuple[str, ...] | None:
    """An on-route prefix plus a move into a wall."""
    base = route[: base_len(level, rng)]
    end = apply_prefix(board, base)
    blocked = [move.name for move in COMPASS.moves(end) if COMPASS.apply(end, move) == end]
    return (*base, rng.choice(blocked)) if blocked else None


def pickup_after(board: Board, route: list[str]) -> int | None:
    """After how many route moves the key is picked up, if the puzzle has one."""
    if not (board.find("K") or board.find("D")):
        return None
    for number, name in enumerate(route, start=1):
        board = take_step(board, name)
        if "key" in board.holding:
            return number
    return None


def late_prefix(
    board: Board, route: list[str], level: int, rng: random.Random
) -> tuple[str, ...] | None:
    """The first k route moves with k at least half the level, past the key where there is one."""
    low = max(1, (level + 1) // 2)
    pickup = pickup_after(board, route)
    if pickup is not None:
        low = max(low, pickup)
    if low > level - 1:
        return None
    return tuple(route[: rng.randrange(low, level)])


def build_prefix(
    kind: str, board: Board, route: list[str], level: int, rng: random.Random
) -> tuple[str, ...] | None:
    """The prefix for this kind, or None where the kind cannot be built here."""
    if kind == "start":
        return ()
    if kind == "on-route":
        return on_route_prefix(route, level, rng)
    if kind == "off-route":
        return off_route_prefix(board, route, level, rng)
    if kind == "after-blocked":
        return after_blocked_prefix(board, route, level, rng)
    return late_prefix(board, route, level, rng)


def chain_prefix(
    board: Board, route: list[str], level: int, kind: str, rng: random.Random
) -> tuple[str, ...] | None:
    """A route prefix plus one more move: deviating for off-route, blocked otherwise."""
    base = route[: rng.randrange(0, level)]
    end = apply_prefix(board, base)
    if kind == "off-route":
        best = SOLVER.best_moves(end)
        ends = [
            move.name
            for move in COMPASS.moves(end)
            if move.name not in best and COMPASS.apply(end, move) != end
        ]
    else:
        ends = [move.name for move in COMPASS.moves(end) if COMPASS.apply(end, move) == end]
    return (*base, rng.choice(ends)) if ends else None


def end_labels(board: Board) -> tuple[bool, bool, tuple[str, ...], int]:
    """has_key, next_to_wall, best_moves and options count at this board."""
    return (
        "key" in board.holding,
        any(COMPASS.apply(board, move) == board for move in COMPASS.moves(board)),
        SOLVER.best_moves(board),
        len(COMPASS.moves(board)),
    )


def make_items(puzzle: Puzzle, rng: random.Random) -> tuple[list[ExamItem], int]:
    """Five items for this puzzle (four at level 1), and how many reuse a seen board."""
    board, route = puzzle.board, shortest_route(puzzle.board, rng)
    assert len(route) == puzzle.level
    seen_boards, seen_prefixes, items, loose = set(), set(), [], 0

    def take(kind: str, prefix: tuple[str, ...] | None, loose_ok: bool) -> bool:
        nonlocal loose
        if prefix is None or won_along(board, prefix) or prefix in seen_prefixes:
            return False
        end = apply_prefix(board, prefix)
        if end in seen_boards:
            if not loose_ok:
                return False
            loose += 1
        seen_boards.add(end)
        seen_prefixes.add(prefix)
        has_key, next_to_wall, best_moves, options = end_labels(end)
        items.append(
            ExamItem(
                puzzle.name,
                puzzle.level,
                kind,
                prefix,
                has_key,
                next_to_wall,
                best_moves,
                options,
            )
        )
        return True

    for kind in ("start", "on-route", "off-route", "after-blocked", "late"):
        take(kind, build_prefix(kind, board, route, puzzle.level, rng), False)
    pool = ["off-route", "after-blocked"]
    tries, target = 0, 5 if puzzle.level >= 2 else 4
    while len(items) < target and tries < 1000:
        kind = pool[tries % len(pool)]
        tries += 1
        prefix = build_prefix(kind, board, route, puzzle.level, rng) or chain_prefix(
            board, route, puzzle.level, kind, rng
        )
        take(kind, prefix, True)
    assert len(items) == target, puzzle.name
    return items, loose
