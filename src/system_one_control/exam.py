"""Fixed-state evaluation: every model answers the same positions, once each."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from system_one_control.bench import Game, MoveRecord, load_lines, record_of, run_pool, save_lines
from system_one_control.players import Player
from system_one_control.players.baselines import ScriptedPlayer
from system_one_control.prompts import Condition
from system_one_control.puzzles import Puzzle
from system_one_control.world import make_rules

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
