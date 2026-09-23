from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TypeVar

import typer

from system_one_control.benchmark import (
    BENCHMARK_DIR,
    estimate_paid_calls,
    run_benchmark,
    save,
    summarize,
    usage,
)
from system_one_control.conditions import CONDITIONS
from system_one_control.examples import write_examples
from system_one_control.generator import write_level
from system_one_control.players import PLAYERS
from system_one_control.scenario import SCENARIO_DIR, load_scenarios

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


@app.command()
def benchmark(
    players: str = typer.Option(
        "random,greedy,greedy-walls,solver", help="Comma-separated player names."
    ),
    scenarios: str = typer.Option("all", help="Comma-separated scenario names, or all."),
    conditions: str = typer.Option("map", help="Comma-separated condition names, or all."),
    first_move_only: bool = typer.Option(False, help="Ask only for the first move."),
    allow_paid: bool = typer.Option(False, help="Allow players that cost money per move."),
    workers: int = typer.Option(8, help="How many games to play at once."),
    out: Path | None = typer.Option(
        None,
        help="Where to save every move. Default: benchmarks/<date>_<what was run>.jsonl",
    ),
) -> None:
    """Play every chosen player on every chosen scenario under every chosen condition."""
    chosen_scenarios = _pick(load_scenarios(), scenarios, "scenario")
    chosen_conditions = _pick(CONDITIONS, conditions, "condition")
    names = _pick({name: name for name in PLAYERS}, players, "player")

    if out is None:
        out = BENCHMARK_DIR / f"{_run_name(names, conditions, scenarios, first_move_only)}.jsonl"
    if out.exists():
        raise typer.BadParameter(f"{out} already exists; delete it or choose another --out")
    calls = estimate_paid_calls(
        chosen_scenarios, chosen_conditions, names, first_move_only=first_move_only
    )
    if calls and not allow_paid:
        raise typer.BadParameter(f"this can make up to {calls} paid calls; add --allow-paid")

    records = run_benchmark(
        chosen_scenarios,
        chosen_conditions,
        [PLAYERS[name].build for name in names],
        first_move_only=first_move_only,
        workers=workers,
    )
    save(records, out)
    table = summarize(records, first_move_only=first_move_only)
    out.with_suffix(".txt").write_text(table + "\n", encoding="utf-8")

    typer.echo(summarize(records, first_move_only=first_move_only, bold_best=True))
    if usage(records):
        typer.echo(f"\n{usage(records)}")
    typer.echo(f"\nSaved to {out} and {out.with_suffix('.txt').name}")


def _run_name(players: list[str], conditions: str, scenarios: str, first_move_only: bool) -> str:
    """Today's date and what was run, so that no two different runs share a file."""
    parts = [str(date.today()), "+".join(players), conditions.replace(",", "+")]
    if scenarios != "all":
        parts.append(scenarios.replace(",", "+"))
    if first_move_only:
        parts.append("first-move")
    return "_".join(parts)


@app.command()
def generate(
    per_level: int = typer.Option(10, help="Puzzles per level, hand-made ones included."),
    seed: int = typer.Option(0, help="Change it for a fresh set of puzzles."),
    folder: Path = typer.Option(SCENARIO_DIR, help="The scenarios folder."),
) -> None:
    """Top up every level from 1 to 10 with generated puzzles checked by the solver."""
    for level in range(1, 11):
        written = write_level(folder, level=level, target=per_level, seed=seed)
        typer.echo(f"level {level:2}: {len(written)} generated")


@app.command()
def examples() -> None:
    """Write what each condition shows the player to the examples folder."""
    for path in write_examples():
        typer.echo(f"wrote {path}")


@app.command()
def web(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Open the board viewer at http://127.0.0.1:8000."""
    import uvicorn

    from system_one_control.web.app import create_app

    uvicorn.run(create_app(), host=host, port=port)
