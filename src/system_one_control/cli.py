from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import TypeVar

import typer

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
    split_unanswered,
)
from system_one_control.examples import write_examples
from system_one_control.players import PLAYERS
from system_one_control.prompts import CONDITIONS
from system_one_control.puzzles import LEVELS, PUZZLE_DIR, load_puzzles, write_level
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


@app.command()
def benchmark(
    players: str = typer.Option(
        "random,greedy,greedy-walls,solver", help="Comma-separated player names."
    ),
    levels: str = typer.Option("all", help="Levels to play, such as 3, 1,4 or 2-5, or all."),
    puzzles: str = typer.Option("all", help="Comma-separated puzzle names, or all."),
    conditions: str = typer.Option("map", help="Comma-separated condition names, or all."),
    rules: str | None = typer.Option(
        None,
        help=f"Play every puzzle under these rules: {', '.join(RULES)}. "
        "Default: each puzzle's own, which is compass.",
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
    chosen_puzzles = _pick(load_puzzles(), puzzles, "puzzle")
    chosen_levels = _levels(levels)
    if chosen_levels is not None:
        chosen_puzzles = [p for p in chosen_puzzles if p.level in chosen_levels]
    if not chosen_puzzles:
        raise typer.BadParameter("no puzzle matches the chosen --levels and --puzzles")
    if rules is not None:
        chosen_rules = _rules(rules)
        chosen_puzzles = [replace(p, rules=chosen_rules) for p in chosen_puzzles]
    chosen_conditions = _pick(CONDITIONS, conditions, "condition")
    names = _pick({name: name for name in PLAYERS}, players, "player")
    compass_only = [n for n in names if PLAYERS[n].compass_only]
    if compass_only and any(p.rules.name != "compass" for p in chosen_puzzles):
        raise typer.BadParameter(f"{', '.join(compass_only)} can only play compass rules")
    keys = game_keys(chosen_puzzles, chosen_conditions, names)
    rules_of = {p.name: p.rules.name for p in chosen_puzzles}

    if out is None:
        name = _run_name(names, conditions, levels, puzzles, rules=rules)
        out = BENCHMARK_DIR / f"{name}.jsonl"
    kept: list[GameRecord] = []
    if out.exists():
        if not resume:
            raise typer.BadParameter(
                f"{out} already exists; add --resume to finish it, or choose another --out"
            )
        # Every game in the file is checked, those that ended in an error too, though only the
        # finished ones are kept.
        loaded = load(out)
        message = check_same_run(loaded, keys, rules_of)
        if message:
            raise typer.BadParameter(f"{out} {message}")
        kept, _ = split_finished(loaded)
    done = {record.key for record in kept}
    calls = estimate_paid_calls(chosen_puzzles, chosen_conditions, names, done=done)
    if calls and not allow_paid:
        raise typer.BadParameter(f"this can make up to {calls} paid calls; add --allow-paid")
    if resume:
        typer.echo(f"Keeping {len(kept)} finished games, playing {len(keys) - len(kept)}")

    save(kept, out)  # drops the games that ended in an error, so they are played again
    try:
        with out.open("a", encoding="utf-8", newline="") as file:

            def write(record: GameRecord) -> None:
                file.write(record.to_json() + "\n")
                file.flush()

            played = run_benchmark(
                chosen_puzzles,
                chosen_conditions,
                {name: PLAYERS[name].build for name in names},
                workers=workers,
                done=done,
                on_record=write,
            )
    except BaseException:
        typer.echo(
            f"\nStopped. Every finished game is saved in {out}; to finish the run, repeat the "
            f"command with --resume --out {out}",
            err=True,
        )
        raise

    order = {key: index for index, key in enumerate(keys)}
    records = sorted([*kept, *played], key=lambda record: order[record.key])
    save(records, out)
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
    kept: list[ExamRecord] = []
    if out.exists():
        if not resume:
            raise typer.BadParameter(
                f"{out} already exists; add --resume to finish it, or choose another --out"
            )
        loaded = load_exam(out)
        message = check_same_exam(loaded, keys)
        if message:
            raise typer.BadParameter(f"{out} {message}")
        kept, _ = split_unanswered(loaded)
    done = {record.key for record in kept}
    calls = sum(1 for key in keys if key not in done and PLAYERS[key[4]].paid)
    if calls and not allow_paid:
        raise typer.BadParameter(f"this can ask up to {calls} paid questions; add --allow-paid")
    if resume:
        typer.echo(f"Keeping {len(kept)} answered items, asking {len(keys) - len(kept)}")

    save_exam(kept, out)  # drops the errored answers, so they are asked again
    try:
        with out.open("a", encoding="utf-8", newline="") as file:

            def write(record: ExamRecord) -> None:
                file.write(record.to_json() + "\n")
                file.flush()

            fresh = run_exam(
                puzzles,
                chosen_items,
                chosen_conditions,
                {name: PLAYERS[name].build for name in names},
                workers=workers,
                done=done,
                on_record=write,
            )
    except BaseException:
        typer.echo(
            f"\nStopped. Every finished answer is saved in {out}; to finish the exam, repeat the "
            f"command with --resume --out {out}",
            err=True,
        )
        raise

    order = {key: index for index, key in enumerate(keys)}
    records = sorted([*kept, *fresh], key=lambda record: order[record.key])
    save_exam(records, out)

    errors = sum(record.error is not None for record in records)
    if errors:
        typer.echo(f"\n{errors} answers ended in an error; --resume --out {out} asks them again")
    typer.echo(f"\nSaved {len(records)} answers to {out}")


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
