from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import typer

from system_one_control.experiment import (
    RESULTS_DIR,
    estimate_paid_calls,
    run_experiment,
    save,
    summarize,
)
from system_one_control.generator import write_level
from system_one_control.players import PLAYERS, make_player
from system_one_control.prompt import load_prompts
from system_one_control.scenario import SCENARIO_DIR, load_scenarios

app = typer.Typer(no_args_is_help=True, add_completion=False)
T = TypeVar("T")
DEFAULT_OUT = RESULTS_DIR / "latest.jsonl"


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
def experiment(
    players: str = typer.Option("solver,random", help="Comma-separated player names."),
    scenarios: str = typer.Option("all", help="Comma-separated scenario names, or all."),
    prompts: str = typer.Option("full", help="Comma-separated prompt names, or all."),
    first_move_only: bool = typer.Option(False, help="Ask only for the first move."),
    allow_paid: bool = typer.Option(False, help="Allow players that cost money per move."),
    out: Path = typer.Option(DEFAULT_OUT, help="Where to save results."),
) -> None:
    """Play every chosen player on every chosen scenario under every chosen prompt."""
    chosen_scenarios = _pick(load_scenarios(), scenarios, "scenario")
    chosen_prompts = _pick(load_prompts(), prompts, "prompt")
    names = _pick({name: name for name in PLAYERS}, players, "player")

    calls = estimate_paid_calls(
        chosen_scenarios, chosen_prompts, names, first_move_only=first_move_only
    )
    if calls and not allow_paid:
        raise typer.BadParameter(f"this can make up to {calls} paid calls; add --allow-paid")

    results = list(
        run_experiment(
            chosen_scenarios,
            chosen_prompts,
            [make_player(name) for name in names],
            first_move_only=first_move_only,
        )
    )
    save(results, out)
    typer.echo(summarize(results))
    typer.echo(f"\nSaved to {out}")


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
def web(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Open the board viewer at http://127.0.0.1:8000."""
    import uvicorn

    from system_one_control.web.app import create_app

    uvicorn.run(create_app(), host=host, port=port)
