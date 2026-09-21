"""Metrics computed from saved raw records, without loading any model.

Two conventions matter. States inside a layout are correlated, so intervals
resample layouts rather than decisions. And a menu on which every option fails
is reported separately, never folded into accuracy as a tie everyone gets right.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

Record = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Interval:
    point: float
    low: float
    high: float

    def __str__(self) -> str:
        return f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}]"


@dataclass(frozen=True, slots=True)
class DecisionMetrics:
    """Decision-level results for one agent under one condition."""

    agent: str
    n: int
    scored: int
    accuracy: Interval | None
    candidate_recall: float
    mean_regret: float | None
    mean_global_regret: float | None
    failure_rate: float
    error_rate: float
    all_fail_rate: float
    subsampled_rate: float
    mean_latency_ms: float
    layouts: int
    extra: dict[str, float] = field(default_factory=dict)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _rate(rows: Sequence[Record], key: str) -> float:
    """Fraction of rows whose flag is set; an empty set of rows is 0.0."""
    return sum(1 for row in rows if row.get(key)) / len(rows) if rows else 0.0


def cluster_bootstrap(
    clusters: dict[str, list[float]],
    statistic: Callable[[Sequence[float]], float | None],
    *,
    samples: int = 2000,
    seed: int = 0,
    confidence: float = 0.95,
) -> Interval | None:
    """Percentile interval obtained by resampling whole clusters.

    One cluster per layout is the point: decisions from the same map move
    together, so resampling decisions would understate the uncertainty.
    """
    keys = sorted(clusters)
    pooled = [value for key in keys for value in clusters[key]]
    point = statistic(pooled)
    if point is None or not keys:
        return None

    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(samples):
        drawn: list[float] = []
        for _ in range(len(keys)):
            drawn.extend(clusters[keys[rng.randrange(len(keys))]])
        value = statistic(drawn)
        if value is not None:
            draws.append(value)

    if not draws:
        return Interval(point, point, point)

    draws.sort()
    tail = (1.0 - confidence) / 2.0
    low = draws[min(len(draws) - 1, int(tail * len(draws)))]
    high = draws[min(len(draws) - 1, int((1.0 - tail) * len(draws)))]
    return Interval(point=point, low=low, high=high)


def decision_metrics(
    records: Iterable[Record],
    *,
    bootstrap_samples: int = 2000,
    seed: int = 0,
) -> DecisionMetrics:
    """Summarise one agent's decisions, with layout-clustered accuracy."""
    rows = list(records)
    if not rows:
        raise ValueError("no records to summarize")

    agents = {row["agent"] for row in rows}
    agent = agents.pop() if len(agents) == 1 else "mixed"

    errors = [row for row in rows if row.get("error")]
    all_fail = [row for row in rows if row.get("all_candidates_fail")]
    scored = [
        row
        for row in rows
        if not row.get("error")
        and not row.get("all_candidates_fail")
        and row.get("correct") is not None
    ]

    clusters: dict[str, list[float]] = {}
    for row in scored:
        key = row.get("layout_id") or row.get("state_id") or "all"
        clusters.setdefault(key, []).append(1.0 if row["correct"] else 0.0)

    accuracy = cluster_bootstrap(
        clusters, lambda values: _mean(values), samples=bootstrap_samples, seed=seed
    )

    regrets = [row["regret"] for row in scored if row.get("regret") is not None]
    global_regrets = [
        row["global_regret"] for row in scored if row.get("global_regret") is not None
    ]
    failures = [row for row in scored if row.get("selected_cost") is None]

    return DecisionMetrics(
        agent=agent,
        n=len(rows),
        scored=len(scored),
        accuracy=accuracy,
        candidate_recall=_rate(rows, "global_optimal_present"),
        mean_regret=_mean(regrets),
        mean_global_regret=_mean(global_regrets),
        failure_rate=len(failures) / len(scored) if scored else 0.0,
        error_rate=len(errors) / len(rows),
        all_fail_rate=len(all_fail) / len(rows),
        subsampled_rate=_rate(rows, "candidate_subsampled"),
        mean_latency_ms=_mean([float(row.get("latency_ms") or 0.0) for row in rows]) or 0.0,
        layouts=len(clusters),
    )


def _confidence_of(row: Record) -> float | None:
    if row.get("reported_confidence") is not None:
        return float(row["reported_confidence"])
    probabilities = row.get("probabilities")
    selected = row.get("selected_candidate_id")
    if probabilities and selected in probabilities:
        return float(probabilities[selected])
    return None


def expected_calibration_error(records: Iterable[Record], *, bins: int = 10) -> float | None:
    """Binned gap between stated confidence and observed correctness.

    Read alongside the tied-optimum breakdown: being unsure which label to give
    is not the same as being unsure whether the action is any good.
    """
    pairs = [
        (confidence, 1.0 if row["correct"] else 0.0)
        for row in records
        if row.get("correct") is not None and (confidence := _confidence_of(row)) is not None
    ]
    if not pairs:
        return None

    total = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        bucket = [
            pair
            for pair in pairs
            if low <= pair[0] < high or (index == bins - 1 and pair[0] == 1.0)
        ]
        if not bucket:
            continue
        mean_confidence = sum(pair[0] for pair in bucket) / len(bucket)
        mean_correct = sum(pair[1] for pair in bucket) / len(bucket)
        total += (len(bucket) / len(pairs)) * abs(mean_confidence - mean_correct)
    return total


def risk_coverage(records: Iterable[Record]) -> list[tuple[float, float]]:
    """Accuracy retained as the least confident answers are abstained on."""
    pairs = [
        (confidence, 1.0 if row["correct"] else 0.0)
        for row in records
        if row.get("correct") is not None and (confidence := _confidence_of(row)) is not None
    ]
    if not pairs:
        return []

    pairs.sort(key=lambda pair: pair[0], reverse=True)
    curve = []
    correct = 0.0
    for index, (_, is_correct) in enumerate(pairs, start=1):
        correct += is_correct
        curve.append((index / len(pairs), correct / index))
    return curve


def selective_accuracy(records: Iterable[Record], *, coverage: float = 0.5) -> float | None:
    """Accuracy over the most confident `coverage` share of the answers.

    The headline number for abstention: a model worth trusting selectively
    scores higher here than it does answering everything.
    """
    if not 0.0 < coverage <= 1.0:
        raise ValueError(f"coverage must be in (0, 1], got {coverage}")
    curve = risk_coverage(records)
    if not curve:
        return None
    kept = [accuracy for covered, accuracy in curve if covered <= coverage]
    return kept[-1] if kept else curve[0][1]


@dataclass(frozen=True, slots=True)
class EpisodeMetrics:
    agent: str
    controller: str
    episodes: int
    success_rate: Interval | None
    mean_steps_on_success: float | None
    truncation_rate: float
    invalid_rate: float
    layouts: int = 0


def episode_metrics(
    episodes: Iterable[Any],
    *,
    layout_of: Callable[[Any], str] | None = None,
    bootstrap_samples: int = 2000,
    seed: int = 0,
) -> EpisodeMetrics:
    """Summarise online episodes, clustering by layout where one is known."""
    rows = list(episodes)
    if not rows:
        raise ValueError("no episodes to summarize")

    clusters: dict[str, list[float]] = {}
    for index, episode in enumerate(rows):
        key = layout_of(episode) if layout_of else str(index)
        clusters.setdefault(key, []).append(1.0 if episode.success else 0.0)

    successes = [episode for episode in rows if episode.success]
    return EpisodeMetrics(
        agent=rows[0].agent,
        controller=rows[0].controller,
        episodes=len(rows),
        success_rate=cluster_bootstrap(
            clusters, lambda values: _mean(values), samples=bootstrap_samples, seed=seed
        ),
        mean_steps_on_success=_mean([episode.steps_used for episode in successes]),
        truncation_rate=sum(1 for e in rows if e.truncated) / len(rows),
        invalid_rate=sum(1 for e in rows if e.invalid_selection) / len(rows),
        layouts=len(clusters),
    )


def format_decision_table(metrics: Sequence[DecisionMetrics]) -> str:
    """Render the headline comparison as a plain text table."""
    header = (
        f"{'agent':<20}{'n':>7}{'accuracy':>26}{'regret':>9}"
        f"{'recall':>9}{'fail':>8}{'err':>7}{'ms':>9}"
    )
    lines = [header, "-" * len(header)]
    for row in metrics:
        accuracy = str(row.accuracy) if row.accuracy else "n/a"
        regret = "n/a" if row.mean_regret is None else f"{row.mean_regret:.2f}"
        lines.append(
            f"{row.agent:<20}{row.n:>7}{accuracy:>26}{regret:>9}"
            f"{row.candidate_recall:>9.2f}{row.failure_rate:>8.2f}"
            f"{row.error_rate:>7.2f}{row.mean_latency_ms:>9.1f}"
        )
    return "\n".join(lines)


def brier_score(records: Iterable[Record]) -> float | None:
    """Mean squared error of the probability assigned to the chosen option."""
    pairs = [
        (confidence, 1.0 if row["correct"] else 0.0)
        for row in records
        if row.get("correct") is not None and (confidence := _confidence_of(row)) is not None
    ]
    if not pairs:
        return None
    return sum((confidence - correct) ** 2 for confidence, correct in pairs) / len(pairs)
