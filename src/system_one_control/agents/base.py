"""The interface every agent implements, and the request it is given.

``DecisionRequest`` holds exactly what a model may see: it has no cost, distance
or optimality field, so an adapter cannot leak a label even by accident. Only an
agent that declares ``privileged`` is handed the true world state; inferring that
from a method name would let an adapter opt itself in by accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from system_one_control.domain import CandidateSet, Snapshot
from system_one_control.observation import (
    DYNAMICS_LEGEND,
    LEGEND_VERSION,
    QUESTION_TEXT,
    QUESTION_VERSION,
    SERIALIZER_VERSION,
    CandidateDescriber,
    StateSerializer,
)


@dataclass(frozen=True, slots=True)
class CandidateView:
    """One option as the model sees it: an opaque id and a description."""

    display_id: str
    description: str


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    request_id: str
    state: str
    legend: str
    question: str
    candidates: tuple[CandidateView, ...]
    serializer_version: str = SERIALIZER_VERSION
    legend_version: str = LEGEND_VERSION
    question_version: str = QUESTION_VERSION
    description_mode: str = "action_only"

    @property
    def display_ids(self) -> tuple[str, ...]:
        return tuple(candidate.display_id for candidate in self.candidates)


@dataclass(frozen=True, slots=True)
class DecisionResult:
    agent: str
    selected_display_id: str | None
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    latency_ms: float = 0.0
    usage: dict[str, int] | None = None
    error: str | None = None
    raw: str | None = None
    attempt_count: int = 1
    extra: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class Agent(Protocol):
    """What every agent exposes, privileged or not."""

    name: str
    privileged: bool


@runtime_checkable
class DecisionAgent(Agent, Protocol):
    """An agent that sees only the sanitized request. Every model is one of these."""

    def choose(self, request: DecisionRequest) -> DecisionResult: ...


@runtime_checkable
class PrivilegedAgent(Agent, Protocol):
    """A baseline permitted to read the true world state. Never a model."""

    def choose_privileged(
        self, snapshot: Snapshot, candidate_set: CandidateSet
    ) -> DecisionResult: ...


def is_privileged(agent: object) -> bool:
    """True only for an agent that declares privilege and can act on it."""
    return bool(getattr(agent, "privileged", False)) and hasattr(agent, "choose_privileged")


class RequestBuilder:
    """Renders the request a model adapter receives.

    Holds the serializer and describer so an alternative representation — full
    JSON, or a rendered image — is a different builder rather than a flag.
    """

    def __init__(
        self,
        serializer: StateSerializer | None = None,
        describer: CandidateDescriber | None = None,
        *,
        legend: str = DYNAMICS_LEGEND,
        question: str = QUESTION_TEXT,
    ) -> None:
        self.serializer = serializer or StateSerializer()
        self.describer = describer or CandidateDescriber()
        self.legend = legend
        self.question = question

    def build(
        self,
        snapshot: Snapshot,
        candidate_set: CandidateSet,
        *,
        request_id: str,
        description_mode: str = "action_only",
    ) -> DecisionRequest:
        return DecisionRequest(
            request_id=request_id,
            state=self.serializer.render(snapshot),
            legend=self.legend,
            question=self.question,
            candidates=tuple(
                CandidateView(
                    display_id=candidate.display_id,
                    description=self.describer.describe(candidate, mode=description_mode),
                )
                for candidate in candidate_set.candidates
            ),
            serializer_version=self.serializer.version,
            description_mode=description_mode,
        )


DEFAULT_REQUEST_BUILDER = RequestBuilder()


def build_request(
    snapshot: Snapshot,
    candidate_set: CandidateSet,
    *,
    request_id: str,
    description_mode: str = "action_only",
) -> DecisionRequest:
    """Render a request with the default compact-text representation."""
    return DEFAULT_REQUEST_BUILDER.build(
        snapshot, candidate_set, request_id=request_id, description_mode=description_mode
    )
