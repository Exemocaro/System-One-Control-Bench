"""The dynamics diagnostic: does the model understand the rules at all?

If a model cannot say which way it faces after a turn, a low control score says
nothing about decision-making. Every answer here comes from the pure transition
function, and items carry the benchmark's own legend and serializer, so a result
on one explains a result on the other.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from system_one_control.agents.base import (
    Agent,
    CandidateView,
    DecisionAgent,
    DecisionRequest,
    DecisionResult,
    is_privileged,
)
from system_one_control.domain import Snapshot
from system_one_control.observation import (
    ACTION_NAMES,
    DIRECTION_NAMES,
    DYNAMICS_LEGEND,
    LEGEND_VERSION,
    QUESTION_VERSION,
    SERIALIZER_VERSION,
    evaluation_state_id,
    serialize_state,
)
from system_one_control.transition import (
    DIR_TO_VEC,
    FORWARD,
    KEY,
    LEFT,
    PICKUP,
    RIGHT,
    step,
)

CATEGORIES = ("orientation", "movement", "affordance")
DIAGNOSTIC_VERSION = "dynamics_v1"


@dataclass(frozen=True, slots=True)
class DiagnosticItem:
    """One single-step question, with the answer ordinary code computed."""

    item_id: str
    category: str
    request: DecisionRequest
    correct_display_id: str
    answer_text: str
    action: int
    state_id: str
    env_id: str
    # Joined onto a record after the answer, like an oracle label. Never sent.
    facts: dict[str, str] = field(default_factory=dict)


def _build_item(
    *,
    item_id: str,
    category: str,
    snapshot: Snapshot,
    question: str,
    options: Sequence[str],
    answer_text: str,
    action: int,
    rng: random.Random,
    facts: dict[str, str],
) -> DiagnosticItem:
    """Shuffle the options so no answer sits in a fixed position."""
    shuffled = list(dict.fromkeys(options))
    rng.shuffle(shuffled)
    views = tuple(
        CandidateView(display_id=f"option_{index:03d}", description=text)
        for index, text in enumerate(shuffled)
    )

    return DiagnosticItem(
        item_id=item_id,
        category=category,
        request=DecisionRequest(
            request_id=item_id,
            state=serialize_state(snapshot),
            legend=DYNAMICS_LEGEND,
            question=question,
            candidates=views,
            serializer_version=SERIALIZER_VERSION,
            legend_version=LEGEND_VERSION,
            question_version=QUESTION_VERSION,
            description_mode="diagnostic",
        ),
        correct_display_id=views[shuffled.index(answer_text)].display_id,
        answer_text=answer_text,
        action=action,
        state_id=evaluation_state_id(snapshot),
        env_id=snapshot.env_id,
        facts=facts,
    )


def orientation_item(snapshot: Snapshot, rng: random.Random, prefix: str) -> DiagnosticItem:
    """After one turn, which way does the agent face?"""
    action = rng.choice((LEFT, RIGHT))
    after = step(snapshot, action).snapshot
    return _build_item(
        item_id=f"{prefix}:orientation",
        category="orientation",
        snapshot=snapshot,
        question=f"If the agent does nothing but {ACTION_NAMES[action]}, which way will it face?",
        options=DIRECTION_NAMES,
        answer_text=DIRECTION_NAMES[after.agent_dir],
        action=action,
        rng=rng,
        facts={"turn": "left" if action == LEFT else "right"},
    )


def movement_item(snapshot: Snapshot, rng: random.Random, prefix: str) -> DiagnosticItem:
    """After one forward, where is the agent? Sometimes nowhere new."""
    after = step(snapshot, FORWARD).snapshot
    return _build_item(
        item_id=f"{prefix}:movement",
        category="movement",
        snapshot=snapshot,
        question="If the agent moves forward once, which cell will it be standing on?",
        options=(
            _coordinate(snapshot.agent_pos),
            _coordinate(_cell_ahead(snapshot)),
            *_neighbor_coordinates(snapshot),
        ),
        answer_text=_coordinate(after.agent_pos),
        action=FORWARD,
        rng=rng,
        facts={"blocked": _flag(after.agent_pos == snapshot.agent_pos)},
    )


def affordance_item(snapshot: Snapshot, rng: random.Random, prefix: str) -> DiagnosticItem:
    """Can the agent pick something up right now?"""
    after = step(snapshot, PICKUP).snapshot
    picked_up = after.carrying is not None and after.carrying != snapshot.carrying
    return _build_item(
        item_id=f"{prefix}:affordance",
        category="affordance",
        snapshot=snapshot,
        question=(
            "If the agent tries to pick up right now, will it end up holding "
            "something it was not holding before?"
        ),
        options=("yes", "no"),
        answer_text="yes" if picked_up else "no",
        action=PICKUP,
        rng=rng,
        facts={"reachable": _flag(picked_up)},
    )


ItemBuilder = Callable[[Snapshot, random.Random, str], DiagnosticItem]
BUILDERS: tuple[ItemBuilder, ...] = (orientation_item, movement_item, affordance_item)


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _coordinate(position: tuple[int, int]) -> str:
    return f"({position[0]}, {position[1]})"


def _cell_ahead(snapshot: Snapshot) -> tuple[int, int]:
    dx, dy = DIR_TO_VEC[snapshot.agent_dir]
    return (snapshot.agent_pos[0] + dx, snapshot.agent_pos[1] + dy)


def _in_bounds(snapshot: Snapshot, cell: tuple[int, int]) -> bool:
    return 0 <= cell[0] < snapshot.width and 0 <= cell[1] < snapshot.height


def _neighbor_coordinates(snapshot: Snapshot) -> tuple[str, ...]:
    """Plausible wrong cells, so the menu is not two options wearing a disguise."""
    x, y = snapshot.agent_pos
    around = ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
    return tuple(_coordinate(cell) for cell in around if _in_bounds(snapshot, cell))


def build_diagnostic(
    snapshots: Iterable[Snapshot], *, rng_seed: int = 0, prefix: str = "dx"
) -> tuple[DiagnosticItem, ...]:
    """One item per category per snapshot, deterministic for a given seed."""
    items: list[DiagnosticItem] = []
    for index, snapshot in enumerate(snapshots):
        for builder in BUILDERS:
            rng = random.Random(f"{rng_seed}:{index}:{builder.__name__}")
            items.append(builder(snapshot, rng, f"{prefix}:{index}"))
    return tuple(items)


def find_key_states(snapshots: Iterable[Snapshot]) -> tuple[Snapshot, ...]:
    """States with a key directly ahead, so the affordance item is not all 'no'."""
    found = []
    for snapshot in snapshots:
        cell = _cell_ahead(snapshot)
        if _in_bounds(snapshot, cell) and snapshot.cells[cell[1]][cell[0]][0] == KEY:
            found.append(snapshot)
    return tuple(found)


def balance_states(
    snapshots: Sequence[Snapshot], *, total: int, reserved_share: float = 0.25
) -> list[Snapshot]:
    """Pick `total` states, keeping a share with something in reach to pick up.

    Left to chance most states have nothing ahead, and an agent that always
    answers "no" scores well on the affordance question without understanding
    it. The reserved share is a ceiling, not a quota: it takes only as many as
    the pool actually holds.
    """
    if total <= 0:
        return []

    # Positions, not values: two identical states must not collapse into one.
    reachable = [i for i, s in enumerate(snapshots) if find_key_states([s])]
    quota = min(len(reachable), max(1, int(total * reserved_share)))

    picked = list(reachable[:quota])
    taken = set(picked)
    for index in range(len(snapshots)):
        if len(picked) >= total:
            break
        if index not in taken:
            picked.append(index)
            taken.add(index)
    return [snapshots[index] for index in sorted(picked)[:total]]


DiagnosticResults = Sequence[tuple[DiagnosticItem, DecisionResult]]


def run_diagnostic(
    agent: Agent, items: Sequence[DiagnosticItem]
) -> list[tuple[DiagnosticItem, DecisionResult]]:
    """Ask one agent every item. A privileged agent cannot meaningfully answer."""
    if is_privileged(agent):
        raise ValueError(
            f"{getattr(agent, 'name', agent)!r} reads the true state, so a diagnostic "
            "score for it would be meaningless"
        )
    answerer = cast(DecisionAgent, agent)
    return [(item, answerer.choose(item.request)) for item in items]


def accuracy_by_fact(results: DiagnosticResults, fact: str) -> dict[str, float]:
    """Accuracy split by one recorded fact, such as blocked versus free moves."""
    buckets: dict[str, list[bool]] = {}
    for item, result in results:
        if fact in item.facts:
            correct = result.selected_display_id == item.correct_display_id
            buckets.setdefault(item.facts[fact], []).append(correct)
    return {key: sum(values) / len(values) for key, values in sorted(buckets.items())}


def counts_by_fact(results: DiagnosticResults, fact: str) -> dict[str, int]:
    """How many items sat behind each rate in `accuracy_by_fact`."""
    counts: dict[str, int] = {}
    for item, _ in results:
        if fact in item.facts:
            counts[item.facts[fact]] = counts.get(item.facts[fact], 0) + 1
    return dict(sorted(counts.items()))


@dataclass(frozen=True, slots=True)
class DiagnosticMetrics:
    """Diagnostic results for one agent."""

    agent: str
    items: int
    answered: int
    overall: float
    by_category: dict[str, float]
    by_fact: dict[str, dict[str, float]]
    counts_by_fact: dict[str, dict[str, int]]
    mean_latency_ms: float
    error_rate: float


def diagnostic_metrics(results: DiagnosticResults) -> DiagnosticMetrics:
    """Accuracy overall, per category and per fact. Unanswered counts as wrong."""
    if not results:
        raise ValueError("no diagnostic results to summarize")

    scored = [
        (item.category, result.selected_display_id == item.correct_display_id)
        for item, result in results
    ]
    by_category = {}
    for category in CATEGORIES:
        hits = [correct for name, correct in scored if name == category]
        if hits:
            by_category[category] = sum(hits) / len(hits)

    facts = sorted({key for item, _ in results for key in item.facts})
    return DiagnosticMetrics(
        agent=results[0][1].agent,
        items=len(results),
        answered=sum(1 for _, result in results if result.selected_display_id is not None),
        overall=sum(correct for _, correct in scored) / len(scored),
        by_category=by_category,
        by_fact={fact: accuracy_by_fact(results, fact) for fact in facts},
        counts_by_fact={fact: counts_by_fact(results, fact) for fact in facts},
        mean_latency_ms=sum(result.latency_ms for _, result in results) / len(results),
        error_rate=sum(1 for _, result in results if result.error) / len(results),
    )


def diagnostic_record(
    *, run_id: str, item: DiagnosticItem, result: DecisionResult
) -> dict[str, Any]:
    """One raw record, in the same spirit as a decision record."""
    return {
        "run_id": run_id,
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "item_id": item.item_id,
        "category": item.category,
        "environment": item.env_id,
        "state_id": item.state_id,
        "agent": result.agent,
        "question": item.request.question,
        "options": {c.display_id: c.description for c in item.request.candidates},
        "facts": dict(item.facts),
        "correct_option_id": item.correct_display_id,
        "correct_answer": item.answer_text,
        "selected_option_id": result.selected_display_id,
        "correct": result.selected_display_id == item.correct_display_id,
        "probabilities": result.probabilities,
        "reported_confidence": result.confidence,
        "latency_ms": result.latency_ms,
        "usage": result.usage,
        "attempt_count": result.attempt_count,
        "error": result.error,
        "serializer_version": item.request.serializer_version,
        "legend_version": item.request.legend_version,
    }


def format_diagnostic_report(metrics: DiagnosticMetrics) -> str:
    """Render diagnostic metrics as plain text, with the n behind every rate."""
    lines = [
        f"agent             {metrics.agent}",
        f"items             {metrics.items} ({metrics.answered} answered)",
        f"overall accuracy  {metrics.overall:.3f}",
    ]
    for category, score in metrics.by_category.items():
        lines.append(f"  {category:<15} {score:.3f}")
    for fact, split in metrics.by_fact.items():
        counts = metrics.counts_by_fact.get(fact, {})
        rendered = "  ".join(
            f"{key}={value:.3f} (n={counts.get(key, 0)})" for key, value in split.items()
        )
        lines.append(f"by {fact:<14} {rendered}")
    lines.append(f"mean latency      {metrics.mean_latency_ms:.0f} ms")
    if metrics.error_rate:
        lines.append(f"error rate        {metrics.error_rate:.3f}")
    return "\n".join(lines)
