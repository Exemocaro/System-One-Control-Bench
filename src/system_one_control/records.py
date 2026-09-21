"""Append-only raw results, and the manifest that says how they were produced.

One JSON object per decision, flushed as it happens and never rewritten, so a
killed run stays readable up to its last complete line.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from system_one_control.agents.base import DecisionResult
from system_one_control.domain import CandidateLabels, CandidateSet, Snapshot
from system_one_control.observation import (
    LEGEND_VERSION,
    QUESTION_VERSION,
    SERIALIZER_VERSION,
    evaluation_state_id,
)

CANDIDATE_GENERATOR_VERSION = "effective_exact_v1"


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True, timeout=10
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


@dataclass(frozen=True, slots=True)
class RunManifest:
    """Everything needed to say what produced a set of records."""

    run_id: str
    created_utc: str
    git_commit: str
    git_dirty: bool
    python_version: str
    platform: str
    serializer_version: str
    legend_version: str
    question_version: str
    candidate_generator_version: str
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def config_hash(self) -> str:
        payload = json.dumps(self.config, sort_keys=True, default=str).encode()
        return "sha256:" + hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "config_hash": self.config_hash}


def build_manifest(run_id: str, config: dict[str, Any] | None = None) -> RunManifest:
    """Capture the provenance of a run at the moment it starts."""
    return RunManifest(
        run_id=run_id,
        created_utc=datetime.now(UTC).isoformat(),
        git_commit=_git("rev-parse", "HEAD"),
        git_dirty=bool(_git("status", "--porcelain")),
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        serializer_version=SERIALIZER_VERSION,
        legend_version=LEGEND_VERSION,
        question_version=QUESTION_VERSION,
        candidate_generator_version=CANDIDATE_GENERATOR_VERSION,
        config=config or {},
    )


def decision_record(
    *,
    run_id: str,
    request_id: str,
    snapshot: Snapshot,
    candidate_set: CandidateSet,
    result: DecisionResult,
    labels: CandidateLabels,
    controller: str,
    split: str | None = None,
    layout_id: str | None = None,
    episode_id: str | None = None,
    step_index: int = 0,
) -> dict[str, Any]:
    """Build one raw record.

    Oracle annotations are joined on here, after the model has answered, so
    nothing in this function can influence the decision it describes.
    """
    selected = result.selected_display_id
    cost = labels.costs.get(selected) if selected is not None else None
    regret = (
        None
        if cost is None or labels.best_offered_cost is None
        else cost - labels.best_offered_cost
    )
    global_regret = None if cost is None or labels.distance is None else cost - labels.distance

    return {
        "run_id": run_id,
        "request_id": request_id,
        "episode_id": episode_id,
        "step": step_index,
        "state_id": evaluation_state_id(snapshot),
        "environment": snapshot.env_id,
        "layout_id": layout_id,
        "split": split,
        "agent": result.agent,
        "controller": controller,
        "horizon": candidate_set.horizon,
        "remaining_steps": snapshot.max_steps - snapshot.step_count,
        "serializer_version": SERIALIZER_VERSION,
        "question_version": QUESTION_VERSION,
        "candidate_generator_version": CANDIDATE_GENERATOR_VERSION,
        "candidate_ids": [c.display_id for c in candidate_set.candidates],
        "candidate_semantics": {c.display_id: list(c.actions) for c in candidate_set.candidates},
        "candidate_pool_size": candidate_set.pool_size,
        "candidate_subsampled": candidate_set.subsampled,
        "optimal_candidate_ids": sorted(labels.optimal_offered_ids),
        "global_optimal_present": labels.global_optimal_present,
        "all_candidates_fail": labels.all_candidates_fail,
        "oracle_distance": labels.distance,
        "best_offered_cost": labels.best_offered_cost,
        "candidate_gap": labels.candidate_gap,
        "selected_candidate_id": selected,
        "selected_cost": cost,
        "regret": regret,
        "global_regret": global_regret,
        "correct": None if selected is None else selected in labels.optimal_offered_ids,
        "probabilities": result.probabilities,
        "reported_confidence": result.confidence,
        "latency_ms": result.latency_ms,
        "usage": result.usage,
        "attempt_count": result.attempt_count,
        "error": result.error,
    }


class JsonlWriter:
    """Append-only JSONL sink. One writer per file, one line per record."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        self._handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> JsonlWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_jsonl(path: Path | str) -> Iterator[dict[str, Any]]:
    """Read records back, skipping a trailing partial line if a run was killed."""
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                return


def write_manifest(path: Path | str, manifest: RunManifest) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
