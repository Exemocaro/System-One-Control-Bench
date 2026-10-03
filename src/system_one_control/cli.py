from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import typer

from system_one_control import leaderboard
from system_one_control.bench import (
    BENCHMARK_DIR,
    GameRecord,
    check_same_run,
    estimate_paid_calls,
    game_keys,
    load,
    run_benchmark,
    save,
    split_finished,
    summarize,
    usage,
    validate_file,
)
from system_one_control.exam import (
    EXAM_DIR,
    ITEMS_FILE,
    ExamItem,
    ExamRecord,
    check_same_exam,
    exam_keys,
    load_exam,
    run_exam,
    save_exam,
)
from system_one_control.examples import write_examples
from system_one_control.players import PLAYERS, register_toml_players
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import LEVELS, PUZZLE_DIR, Puzzle, load_puzzles, write_level
from system_one_control.world import RULES, Rules, make_rules

app = typer.Typer(no_args_is_help=True, add_completion=False)
T = TypeVar("T")


def _pick(catalog: dict[str, T], spec: str, kind: str) -> list[T]:
    if spec == "all":
        return list(catalog.values())
    names = [name.strip() for name in spec.split(",") if name.strip()]
    unknown = [name for name in names if name not in catalog]
    if unknown:
        raise typer.BadParameter(
            f"unknown {kind}: {', '.join(unknown)}. Known: {', '.join(catalog)}"
        )
    return [catalog[name] for name in names]


def _rules(name: str) -> Rules:
    try:
        return make_rules(name)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None


def _levels(spec: str) -> set[int] | None:
    """Levels such as "3", "1,4" or "2-5", or None for all of them."""
    if spec == "all":
        return None
    levels: set[int] = set()
    try:
        for part in spec.split(","):
            first, _, last = part.strip().partition("-")
            levels.update(range(int(first), int(last or first) + 1))
    except ValueError:
        raise typer.BadParameter(f"levels must look like 3, 1,4 or 2-5, not {spec!r}") from None
    return levels


def _resume_kept(
    out: Path,
    resume: bool,
    allow_paid: bool,
    keys: list[Any],
    load_records: Callable[[Path], list[Any]],
    check_records: Callable[[list[Any]], str | None],
    split_records: Callable[[list[Any]], tuple[list[Any], list[Any]]],
    count_calls: Callable[[set[Any]], int],
    kept_noun: str,
    verb: str,
    calls_noun: str,
) -> tuple[list[Any], set[Any]]:
    """Keep the finished records in out, refusing anything inconsistent or unpaid.

    Records are Any because games and answers share no base class by design: their
    formats must stay distinct, so the shared block cannot name either one.
    """
    kept: list[Any] = []
    if out.exists():
        if not resume:
            raise typer.BadParameter(
                f"{out} already exists; add --resume to finish it, or choose another --out"
            )
        loaded = load_records(out)
        if message := check_records(loaded):
            raise typer.BadParameter(f"{out} {message}")
        kept, _ = split_records(loaded)
    done = {record.key for record in kept}
    calls = count_calls(done)
    if calls and not allow_paid:
        raise typer.BadParameter(f"this can make up to {calls} paid {calls_noun}; add --allow-paid")
    if resume:
        typer.echo(f"Keeping {len(kept)} {kept_noun}, {verb} {len(keys) - len(kept)}")
    return kept, done


def _append_fresh(
    out: Path,
    kept: list[Any],
    keys: list[Any],
    run_fresh: Callable[[set[Any], Callable[[Any], None]], list[Any]],
    save_records: Callable[[list[Any], Path], Path],
    thing: str,
    run_kind: str,
) -> list[Any]:
    """Play the missing keys, appending to out, then return everything in key order."""
    save_records(kept, out)  # drops the errored ones, so they run again
    try:
        with out.open("a", encoding="utf-8", newline="") as file:

            def write(record: Any) -> None:
                file.write(record.to_json() + "\n")
                file.flush()

            fresh = run_fresh({record.key for record in kept}, write)
    except BaseException:
        typer.echo(
            f"\nStopped. Every finished {thing} is saved in {out}; to finish the {run_kind}, "
            f"repeat the command with --resume --out {out}",
            err=True,
        )
        raise
    order = {key: index for index, key in enumerate(keys)}
    records = sorted([*kept, *fresh], key=lambda record: order[record.key])
    save_records(records, out)
    return records


@app.command()
def benchmark(
    players: str = typer.Option(
        "random,greedy,greedy-walls,solver", help="Comma-separated player names."
    ),
    levels: str = typer.Option("all", help="Levels to play, such as 3, 1,4 or 2-5, or all."),
    puzzles: str = typer.Option("all", help="Comma-separated puzzle names, or all."),
    conditions: str | None = typer.Option(
        None, help="Comma-separated condition names, or all. Default: map."
    ),
    rules: str | None = typer.Option(
        None,
        help=f"Play every puzzle under these rules: {', '.join(RULES)}. "
        "Default: each puzzle's own, which is compass.",
    ),
    track: str | None = typer.Option(
        None, help="Shorthand for --rules compass --conditions map,everything: core."
    ),
    players_file: Path | None = typer.Option(
        None, help="A players.toml with extra players. Default: players.toml, if present."
    ),
    allow_paid: bool = typer.Option(False, help="Allow players that cost money per move."),
    workers: int = typer.Option(3, help="How many games to play at once."),
    out: Path | None = typer.Option(
        None,
        help="Where to save every move. Default: benchmarks/<date>_<time>_<what was run>.jsonl",
    ),
    resume: bool = typer.Option(
        False, help="Finish an earlier run in --out: replay its missing games and its errors."
    ),
) -> None:
    """Play every chosen player on every chosen puzzle under every chosen condition."""
    if players_file is None and Path("players.toml").exists():
        players_file = Path("players.toml")
    if players_file is not None:
        try:
            register_toml_players(players_file)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from None
    if track is not None:
        if track != "core":
            raise typer.BadParameter(f"unknown track {track!r}; known: core")
        if conditions is not None or rules is not None:
            raise typer.BadParameter("--track cannot be combined with --conditions or --rules")
        conditions, rules = "map,everything", "compass"
    chosen_puzzles = _pick(load_puzzles(), puzzles, "puzzle")
    chosen_levels = _levels(levels)
    if chosen_levels is not None:
        chosen_puzzles = [p for p in chosen_puzzles if p.level in chosen_levels]
    if not chosen_puzzles:
        raise typer.BadParameter("no puzzle matches the chosen --levels and --puzzles")
    names = _pick({name: name for name in PLAYERS}, players, "player")
    _benchmark_once(
        chosen_puzzles,
        conditions or "map",
        rules,
        names,
        workers,
        out,
        resume,
        levels,
        puzzles,
        allow_paid,
    )


def _benchmark_once(
    puzzles_all: list[Puzzle],
    conditions_spec: str,
    rules_spec: str | None,
    names: list[str],
    workers: int,
    out: Path | None,
    resume: bool,
    levels: str,
    puzzles_spec: str,
    allow_paid: bool,
) -> None:
    """One benchmark run: every player on every puzzle under every condition, once."""
    if rules_spec is not None:
        chosen_rules = _rules(rules_spec)
        chosen_puzzles = [replace(p, rules=chosen_rules) for p in puzzles_all]
    else:
        chosen_puzzles = list(puzzles_all)
    chosen_conditions = _pick(CONDITIONS, conditions_spec, "condition")
    compass_only = [n for n in names if PLAYERS[n].compass_only]
    if compass_only and any(p.rules.name != "compass" for p in chosen_puzzles):
        raise typer.BadParameter(f"{', '.join(compass_only)} can only play compass rules")
    keys = game_keys(chosen_puzzles, chosen_conditions, names)
    rules_of = {p.name: p.rules.name for p in chosen_puzzles}

    if out is None:
        name = _run_name(names, conditions_spec, levels, puzzles_spec, rules=rules_spec)
        out = BENCHMARK_DIR / f"{name}.jsonl"

    def check(loaded: list[GameRecord]) -> str | None:
        return check_same_run(loaded, keys, rules_of)

    def count(skipped: set[Any]) -> int:
        return estimate_paid_calls(chosen_puzzles, chosen_conditions, names, done=skipped)

    kept, done = _resume_kept(
        out,
        resume,
        allow_paid,
        keys,
        load,
        check,
        split_finished,
        count,
        "finished games",
        "playing",
        "calls",
    )

    def run_fresh(done: set[Any], write: Callable[[GameRecord], None]) -> list[GameRecord]:
        return run_benchmark(
            chosen_puzzles,
            chosen_conditions,
            {name: PLAYERS[name].build for name in names},
            workers=workers,
            done=done,
            on_record=write,
        )

    records = _append_fresh(out, kept, keys, run_fresh, save, "game", "run")
    played = [record for record in records if record.key not in done]
    table = summarize(records)
    out.with_suffix(".txt").write_text(table + "\n", encoding="utf-8", newline="")

    typer.echo(summarize(records, bold_best=True))
    if usage(played):
        typer.echo(f"\nPaid calls in this run:\n{usage(played)}")
    errors = sum(record.error is not None for record in records)
    if errors:
        typer.echo(f"\n{errors} games ended in an error; --resume --out {out} plays them again")
    typer.echo(f"\nSaved to {out} and {out.with_suffix('.txt').name}")


@app.command()
def exam(
    players: str = typer.Option(
        "random,greedy,greedy-walls,solver", help="Comma-separated player names."
    ),
    conditions: str = typer.Option("map", help="Comma-separated condition names, or all."),
    items: Path = typer.Option(ITEMS_FILE, help="The exam items file."),
    allow_paid: bool = typer.Option(False, help="Allow players that cost money per move."),
    workers: int = typer.Option(3, help="How many answers to ask for at once."),
    out: Path | None = typer.Option(
        None,
        help="Where to save every answer. Default: exam/<date>_<time>_<what was run>.jsonl",
    ),
    resume: bool = typer.Option(
        False, help="Finish an earlier exam in --out: ask its missing items and its errors again."
    ),
) -> None:
    """Ask every chosen player every exam item under every chosen condition, once each."""
    lines = [line for line in items.read_text(encoding="utf-8").splitlines() if line.strip()]
    chosen_items = [ExamItem.from_json(line) for line in lines]
    chosen_conditions = _pick(CONDITIONS, conditions, "condition")
    names = _pick({name: name for name in PLAYERS}, players, "player")
    puzzles = load_puzzles()
    keys = exam_keys(chosen_items, chosen_conditions, {name: PLAYERS[name].build for name in names})

    if out is None:
        name = _run_name(names, conditions, "all", "all", rules="compass")
        out = EXAM_DIR / f"{name}.jsonl"

    def check(loaded: list[ExamRecord]) -> str | None:
        return check_same_exam(loaded, keys)

    def count(skipped: set[Any]) -> int:
        return sum(1 for key in keys if key not in skipped and PLAYERS[key[4]].paid)

    kept, _ = _resume_kept(
        out,
        resume,
        allow_paid,
        keys,
        load_exam,
        check,
        split_finished,
        count,
        "answered items",
        "asking",
        "questions",
    )

    def run_fresh(done: set[Any], write: Callable[[ExamRecord], None]) -> list[ExamRecord]:
        return run_exam(
            puzzles,
            chosen_items,
            chosen_conditions,
            {name: PLAYERS[name].build for name in names},
            workers=workers,
            done=done,
            on_record=write,
        )

    records = _append_fresh(out, kept, keys, run_fresh, save_exam, "answer", "exam")

    errors = sum(record.error is not None for record in records)
    if errors:
        typer.echo(f"\n{errors} answers ended in an error; --resume --out {out} asks them again")
    typer.echo(f"\nSaved {len(records)} answers to {out}")


@app.command()
def validate(file: Path) -> None:
    """Replay every game in a results file and report what does not check out."""
    failures = validate_file(file)
    for failure in failures:
        typer.echo(failure)
    if failures:
        raise typer.Exit(1)
    typer.echo(f"{file} is valid")


@app.command()
def submit(
    files: list[Path] = typer.Argument(..., help="Core-track results files, one player in total."),
    name: str = typer.Option(..., help="The entry name shown on the leaderboard."),
    org: str = typer.Option("", help="The entrant's organisation."),
    url: str = typer.Option("", help="A link shown beside the entry name."),
    notes: str = typer.Option("", help="Anything to say about the run."),
    player: str | None = typer.Option(None, help="Whose games to take; needed with several."),
    kind: str | None = typer.Option(None, help="baseline, chat or decision."),
) -> None:
    """Validate core-track results and write the player's leaderboard entry."""
    try:
        path = leaderboard.submit(
            files, name=name, org=org, url=url, notes=notes, player=player, kind=kind
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from None
    typer.echo(f"wrote {path}")


@app.command("leaderboard")
def rebuild_leaderboard() -> None:
    """Rebuild the leaderboard table and page from the entries."""
    readme, page = leaderboard.rebuild()
    typer.echo(f"wrote {readme} and {page}")


def _run_name(
    players: list[str],
    conditions: str,
    levels: str,
    puzzles: str,
    when: datetime | None = None,
    rules: str | None = None,
) -> str:
    """The date, the time to the minute, and what was run, such as
    2026-09-23_18-45_jev_all_levels-1-3 or 2026-09-24_10-00_jev_all_two-moves."""
    when = when or datetime.now()
    parts = [when.strftime("%Y-%m-%d_%H-%M"), "+".join(players), _plus(conditions)]
    if rules is not None and rules != "compass":
        parts.append(rules)
    if levels != "all":
        parts.append(f"levels-{_plus(levels)}")
    if puzzles != "all":
        parts.append(_plus(puzzles))
    return "_".join(parts)


def _plus(spec: str) -> str:
    return "+".join(part.strip() for part in spec.split(",") if part.strip())


@app.command()
def generate(
    per_level: int | None = typer.Option(
        None, help="Puzzles per level, hand-made ones included. Default: as LEVELS says."
    ),
    seed: int = typer.Option(0, help="Change it for a fresh set of puzzles."),
    folder: Path = typer.Option(PUZZLE_DIR, help="The puzzles folder."),
) -> None:
    """Top up every level in LEVELS with generated puzzles checked by the solver."""
    for level, count in LEVELS.items():
        written = write_level(folder, level=level, target=per_level or count, seed=seed)
        typer.echo(f"level {level:2}: {len(written)} generated")


@app.command()
def examples(
    rules: str = typer.Option(
        "compass", help=f"Show the requests under these rules: {', '.join(RULES)}."
    ),
) -> None:
    """Write what each condition shows the player to the examples folder."""
    for path in write_examples(rules=_rules(rules)):
        typer.echo(f"wrote {path}")


@app.command()
def web(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Open the board viewer at http://127.0.0.1:8000."""
    import uvicorn

    from system_one_control.web.app import create_app

    uvicorn.run(create_app(), host=host, port=port)
