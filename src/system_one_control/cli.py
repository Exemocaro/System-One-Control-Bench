"""Command line entry points.

Analysis never loads a model or reads a credential, so a published run can be
re-analyzed from its saved records by anyone who clones the repository.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from system_one_control.agents.base import build_request
from system_one_control.analysis import episode_metrics
from system_one_control.candidates import build_candidate_set
from system_one_control.config import ExperimentConfig, load_config
from system_one_control.dataset import (
    StateBank,
    StateRecord,
    build_state_bank,
    census_layouts,
)
from system_one_control.diagnostics import (
    balance_states,
    build_diagnostic,
    diagnostic_metrics,
    diagnostic_record,
    format_diagnostic_report,
    run_diagnostic,
)
from system_one_control.domain import Snapshot
from system_one_control.observation import DYNAMICS_LEGEND
from system_one_control.records import JsonlWriter, build_manifest, read_jsonl, write_manifest
from system_one_control.reporting import (
    dataset_manifest_json,
    dataset_summary,
    decision_report,
    episode_summary,
)
from system_one_control.runner import (
    CONTROLLERS,
    CallBudget,
    SweepSettings,
    build_agent,
    estimate_calls,
    evaluate_offline,
    evaluate_online,
    select_states,
)

app = typer.Typer(add_completion=False, help="System-One Control Bench")

CONFIG = typer.Option(Path("configs/v0.yaml"), "--config", help="Experiment configuration.")
RUNS = typer.Option(Path("runs"), "--runs", help="Directory for run outputs.")
RUN_DIR = typer.Option(..., "--run", help="Run directory to analyze.")
BOOTSTRAP = typer.Option(None, help="Bootstrap resamples; defaults to the run's config.")
DRY_RUN = typer.Option(False, "--dry-run", help="Build and print the items; call nothing.")
AGENTS = typer.Option("", help="Comma-separated agents; defaults to the config.")
AGENT = typer.Option(..., "--agent", help="Which agent to diagnose.")
STATES = typer.Option(8, help="How many states to build questions from.")

OPTIONAL_ADAPTERS = ("typesafe_sdk", "laya", "torch")
DEFAULT_BOOTSTRAP_SAMPLES = 2000


class Workspace:
    """One loaded config plus the state banks built from it.

    Every command needs the bank, and building it costs a full BFS pass over
    every collected state, so it is built once per environment and kept.
    """

    def __init__(self, config: ExperimentConfig, runs: Path | None = None) -> None:
        self.config = config
        self.runs = runs
        self._banks: dict[str, StateBank] = {}

    @classmethod
    def load(cls, config: Path, runs: Path | None = None) -> Workspace:
        if not config.exists():
            raise typer.BadParameter(f"no such config: {config}")
        return cls(load_config(config), runs)

    @property
    def target(self) -> Path:
        """The run directory for this experiment, created on demand."""
        if self.runs is None:
            raise typer.BadParameter("this command needs --runs")
        path = self.runs / self.config.experiment_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def bank(self, env_id: str) -> StateBank:
        if env_id not in self._banks:
            dataset = self.config.dataset
            self._banks[env_id] = build_state_bank(
                env_id,
                seeds=range(dataset.seeds),
                states_per_episode=dataset.states_per_episode,
                rng_seed=self.config.seed,
                max_steps=dataset.max_steps,
                max_options=self.config.candidates.max_options,
            )
        return self._banks[env_id]

    def states(self, env_id: str, limit: int | None) -> tuple[StateRecord, ...]:
        return select_states(self.bank(env_id), split=self.config.dataset.split, limit=limit)

    def sweep_settings(self) -> SweepSettings:
        return SweepSettings(
            run_id=self.config.experiment_id,
            max_options=self.config.candidates.max_options,
            rng_seed=self.config.seed,
            description_mode=self.config.offline.description_mode,
            randomize_display_ids=self.config.candidates.randomize_display_ids,
        )

    def agents(self, override: str) -> tuple[str, ...]:
        chosen = tuple(name.strip() for name in override.split(",") if name.strip())
        return chosen or self.config.agents


def _echo_lines(lines: list[str]) -> None:
    for line in lines:
        typer.echo(line)


def _diagnostic_states(workspace: Workspace, total: int) -> list[Snapshot]:
    """Share the item budget across environments, keeping pickups in reach.

    Taking the first `total` of a concatenated list would silently diagnose only
    the first environment.
    """
    environments = workspace.config.environments
    per_env = max(1, total // len(environments))

    chosen: list[Snapshot] = []
    for env_id in environments:
        snapshots = [state.snapshot for state in workspace.states(env_id, limit=None)]
        chosen.extend(balance_states(snapshots, total=per_env))
    return chosen[:total]


@app.command()
def doctor(config: Path = CONFIG) -> None:
    """Check the environment, the config and the optional dependencies."""
    typer.echo(f"python            {sys.version.split()[0]}")
    try:
        import gymnasium
        import minigrid

        typer.echo(f"minigrid          {minigrid.__version__}")
        typer.echo(f"gymnasium         {gymnasium.__version__}")
    except ImportError as error:  # pragma: no cover - environment specific
        typer.echo(f"minigrid          MISSING ({error})")

    for optional in OPTIONAL_ADAPTERS:
        try:
            __import__(optional)
            typer.echo(f"{optional:<18}available")
        except ImportError:
            typer.echo(f"{optional:<18}not installed (adapter unavailable)")

    if not config.exists():
        typer.echo(f"config            {config} NOT FOUND")
        return
    loaded = load_config(config)
    typer.echo(f"config            {config} ({loaded.experiment_id})")
    typer.echo(f"environments      {', '.join(loaded.environments)}")
    typer.echo(f"agents            {', '.join(loaded.agents)}")


@app.command()
def census(
    environment: str = typer.Argument(..., help="MiniGrid environment id."),
    seeds: int = typer.Option(200, help="How many seeds to inspect."),
) -> None:
    """Count the genuinely distinct layouts a range of seeds produces.

    Several MiniGrid environments generate far fewer layouts than seeds, which
    caps the effective sample size of any layout-clustered interval.
    """
    result = census_layouts(environment, range(seeds))
    typer.echo(f"environment       {environment}")
    typer.echo(f"seeds inspected   {seeds}")
    typer.echo(f"distinct layouts  {result.layout_count}")
    typer.echo(f"distinct starts   {result.start_state_count}")
    largest = max((len(v) for v in result.layouts.values()), default=0)
    typer.echo(f"largest layout    {largest} seeds")


@app.command("build-dataset")
def build_dataset(config: Path = CONFIG, runs: Path = RUNS) -> None:
    """Generate, split and freeze the offline state bank."""
    workspace = Workspace.load(config, runs)
    for env_id in workspace.config.environments:
        manifest = workspace.bank(env_id).manifest
        path = workspace.target / f"dataset_{env_id.replace('/', '_')}.json"
        path.write_text(dataset_manifest_json(manifest), encoding="utf-8")
        _echo_lines(dataset_summary(manifest, str(path)))


@app.command("audit-inputs")
def audit_inputs(config: Path = CONFIG) -> None:
    """Report the size of what a model would actually receive.

    Character counts are a proxy. A real audit decodes the tokenizer's own
    output and checks that no option lost its action text; that belongs in each
    model adapter, because the budget belongs to the model.
    """
    workspace = Workspace.load(config)
    loaded = workspace.config
    for env_id in loaded.environments:
        states = workspace.states(env_id, limit=25)
        for horizon in loaded.offline.horizons:
            widest = 0
            for index, state in enumerate(states):
                candidate_set = build_candidate_set(
                    state.snapshot,
                    horizon=horizon,
                    max_options=loaded.candidates.max_options,
                    rng_seed=loaded.seed + index,
                    randomize_display_ids=loaded.candidates.randomize_display_ids,
                )
                if not candidate_set.candidates:
                    continue
                request = build_request(
                    state.snapshot,
                    candidate_set,
                    request_id="audit",
                    description_mode=loaded.offline.description_mode,
                )
                widest = max(
                    widest,
                    len(request.state)
                    + len(request.legend)
                    + len(request.question)
                    + sum(len(c.description) for c in request.candidates),
                )
            typer.echo(
                f"{env_id} h={horizon} mode={loaded.offline.description_mode}: "
                f"largest request {widest} characters "
                f"(legend {len(DYNAMICS_LEGEND)} of them)"
            )


@app.command()
def estimate(config: Path = CONFIG) -> None:
    """Print how many decisions a sweep would ask for, before running it."""
    workspace = Workspace.load(config)
    loaded = workspace.config
    total = 0
    for env_id in loaded.environments:
        states = workspace.states(env_id, limit=loaded.dataset.states_per_environment)
        calls = estimate_calls(states, loaded.agents, loaded.offline.horizons)
        typer.echo(f"{env_id}: {len(states)} states -> {calls} decisions")
        total += calls
    typer.echo(f"total offline decisions: {total}")
    if loaded.max_calls is not None and total > loaded.max_calls:
        typer.echo(f"WARNING: exceeds configured max_calls ({loaded.max_calls})")


@app.command("evaluate-offline")
def evaluate_offline_command(
    config: Path = CONFIG, runs: Path = RUNS, agents: str = AGENTS
) -> None:
    """Run every agent over the same frozen states and save raw records."""
    workspace = Workspace.load(config, runs)
    loaded = workspace.config
    chosen = workspace.agents(agents)
    settings = workspace.sweep_settings()

    write_manifest(
        workspace.target / "manifest.json",
        build_manifest(loaded.experiment_id, loaded.to_dict()),
    )
    budget = CallBudget(max_calls=loaded.max_calls)

    with JsonlWriter(workspace.target / "decisions.jsonl") as writer:
        for env_id in loaded.environments:
            states = workspace.states(env_id, limit=loaded.dataset.states_per_environment)
            if not states:
                typer.echo(f"{env_id}: no states in split {loaded.dataset.split!r}, skipping")
                continue
            for horizon in loaded.offline.horizons:
                for name in chosen:
                    records = evaluate_offline(
                        states,
                        build_agent(name, seed=loaded.seed),
                        run_id=settings.run_id,
                        horizon=horizon,
                        max_options=settings.max_options,
                        rng_seed=settings.rng_seed,
                        description_mode=settings.description_mode,
                        randomize_display_ids=settings.randomize_display_ids,
                        budget=budget,
                    )
                    for record in records:
                        writer.write(record)
                    typer.echo(f"{env_id} h={horizon} {name}: {len(records)} decisions")
    typer.echo(f"calls used: {budget.used}")


@app.command("evaluate-online")
def evaluate_online_command(config: Path = CONFIG, runs: Path = RUNS, agents: str = AGENTS) -> None:
    """Run whole episodes for each agent and controller."""
    workspace = Workspace.load(config, runs)
    loaded = workspace.config
    chosen = workspace.agents(agents)
    settings = workspace.sweep_settings()
    budget = CallBudget(max_calls=loaded.max_calls)
    samples = loaded.statistics.bootstrap_samples

    with JsonlWriter(workspace.target / "episodes.jsonl") as writer:
        for env_id in loaded.environments:
            starts = workspace.states(env_id, limit=loaded.online.starts_per_environment)
            if not starts:
                typer.echo(f"{env_id}: no states in split {loaded.dataset.split!r}, skipping")
                continue
            for controller_name in loaded.online.controllers:
                for name in chosen:
                    episodes, records = evaluate_online(
                        starts,
                        build_agent(name, seed=loaded.seed),
                        CONTROLLERS[controller_name],
                        run_id=settings.run_id,
                        max_options=settings.max_options,
                        rng_seed=settings.rng_seed,
                        description_mode=settings.description_mode,
                        budget=budget,
                    )
                    for record in records:
                        writer.write(record)
                    metrics = episode_metrics(
                        episodes,
                        layout_of=lambda e: e.layout_id or "",
                        bootstrap_samples=samples,
                    )
                    typer.echo(episode_summary(env_id, controller_name, metrics))
    typer.echo(f"calls used: {budget.used}")


@app.command()
def diagnose(
    agent: str = AGENT,
    config: Path = CONFIG,
    runs: Path = RUNS,
    states: int = STATES,
    dry_run: bool = DRY_RUN,
) -> None:
    """Ask single-step questions about the dynamics, before trusting any score.

    A model that cannot say which way it faces after a turn has not been shown
    to be a poor controller; it has been shown not to have understood the rules.
    """
    workspace = Workspace.load(config, runs)
    loaded = workspace.config

    chosen = _diagnostic_states(workspace, states)
    if not chosen:
        raise typer.BadParameter(f"no states in split {loaded.dataset.split!r}")

    items = build_diagnostic(chosen, rng_seed=loaded.seed)
    typer.echo(f"{len(items)} items over {len(chosen)} states")

    if dry_run:
        for item in items:
            typer.echo("")
            typer.echo(f"[{item.category}] {item.request.question}")
            for view in item.request.candidates:
                marker = "*" if view.display_id == item.correct_display_id else " "
                typer.echo(f"  {marker} {view.display_id}  {view.description}")
        return

    results = run_diagnostic(build_agent(agent, seed=loaded.seed), items)
    with JsonlWriter(workspace.target / "diagnostics.jsonl") as writer:
        for item, result in results:
            writer.write(diagnostic_record(run_id=loaded.experiment_id, item=item, result=result))

    typer.echo("")
    typer.echo(format_diagnostic_report(diagnostic_metrics(results)))


@app.command()
def report(run: Path = RUN_DIR, bootstrap_samples: int | None = BOOTSTRAP) -> None:
    """Rebuild every table from saved records, without loading any model."""
    decisions = run / "decisions.jsonl"
    if not decisions.exists():
        raise typer.BadParameter(f"no decisions.jsonl in {run}")

    rows = list(read_jsonl(decisions))
    samples = bootstrap_samples or _bootstrap_from_manifest(run)
    typer.echo(f"{len(rows)} records from {decisions}")
    typer.echo(f"{samples} bootstrap resamples\n")
    _echo_lines(decision_report(rows, bootstrap_samples=samples))


def _bootstrap_from_manifest(run: Path) -> int:
    """The resample count the run was configured with, or the library default."""
    manifest = run / "manifest.json"
    if not manifest.exists():
        return DEFAULT_BOOTSTRAP_SAMPLES
    saved = json.loads(manifest.read_text(encoding="utf-8"))
    statistics = saved.get("config", {}).get("statistics", {})
    return int(statistics.get("bootstrap_samples", DEFAULT_BOOTSTRAP_SAMPLES))


if __name__ == "__main__":  # pragma: no cover
    app()
