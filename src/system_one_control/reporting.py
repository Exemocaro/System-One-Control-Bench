"""Turning metrics and manifests into the text the CLI prints.

Kept apart from the commands so the tables can be rendered, tested and reused
without going through a command line.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

from system_one_control.analysis import (
    DecisionMetrics,
    EpisodeMetrics,
    brier_score,
    decision_metrics,
    expected_calibration_error,
    format_decision_table,
    selective_accuracy,
)
from system_one_control.dataset import StateBankManifest

Record = dict[str, Any]


def dataset_summary(manifest: StateBankManifest, path: str) -> list[str]:
    """One line per dataset, plus a warning when the split is not held out."""
    lines = [
        f"{manifest.env_id}: {manifest.state_count} states over "
        f"{manifest.layout_count} layouts -> {path}"
    ]
    if manifest.within_layout_split:
        lines.append(
            f"  note: {manifest.env_id} has {manifest.layout_count} layout(s), so splits are "
            "within-layout. Treat its results as a sanity check, not held-out evidence."
        )
    return lines


def dataset_manifest_json(manifest: StateBankManifest) -> str:
    return json.dumps(
        {
            "env_id": manifest.env_id,
            "state_count": manifest.state_count,
            "layout_count": manifest.layout_count,
            "states_per_split": manifest.states_per_split,
            "states_per_policy": manifest.states_per_policy,
            "checksum": manifest.checksum,
            "rng_seed": manifest.rng_seed,
            "max_steps": manifest.max_steps,
            "serializer_version": manifest.serializer_version,
            "within_layout_split": manifest.within_layout_split,
        },
        indent=2,
        sort_keys=True,
    )


def _group_by_agent_and_horizon(rows: Iterable[Record]) -> dict[tuple[str, int], list[Record]]:
    grouped: dict[tuple[str, int], list[Record]] = {}
    for row in rows:
        grouped.setdefault((row["agent"], row["horizon"]), []).append(row)
    return grouped


def decision_report(rows: Sequence[Record], *, bootstrap_samples: int) -> list[str]:
    """The headline table per horizon, then calibration for each agent."""
    grouped = _group_by_agent_and_horizon(rows)
    lines: list[str] = []

    for horizon in sorted({key[1] for key in grouped}):
        lines.append(f"horizon {horizon}")
        metrics: list[DecisionMetrics] = [
            decision_metrics(grouped[key], bootstrap_samples=bootstrap_samples)
            for key in sorted(grouped)
            if key[1] == horizon
        ]
        lines.append(format_decision_table(metrics))
        lines.append("")

    for (agent, horizon), group in sorted(grouped.items()):
        ece = expected_calibration_error(group)
        brier = brier_score(group)
        half = selective_accuracy(group, coverage=0.5)
        if ece is None or brier is None:
            continue
        line = f"{agent} h={horizon}: ECE {ece:.3f}  Brier {brier:.3f}"
        if half is not None:
            line += f"  accuracy at 50% coverage {half:.3f}"
        lines.append(line)
    return lines


def episode_summary(env_id: str, controller: str, metrics: EpisodeMetrics) -> str:
    """One online result line, flagging an interval no layout count can support."""
    line = (
        f"{env_id} {controller} {metrics.agent}: "
        f"success {metrics.success_rate} over {metrics.episodes} episodes"
    )
    if metrics.layouts < 2:
        line += f" (only {metrics.layouts} layout; interval not estimable)"
    return line
