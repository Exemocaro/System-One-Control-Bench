"""Shared machinery for every model adapter.

A subclass implements `call_model` and inherits timing, retries, validation and
error capture, so adding a provider is the provider call and nothing else. Two
rules hold throughout: a model is never privileged, and a failed decision is
recorded rather than raised, so one bad call cannot discard a run's records.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from system_one_control.agents.base import DecisionRequest, DecisionResult

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_TIMEOUT_SECONDS = 60.0


class ModelCallError(RuntimeError):
    """A provider call failed in a way that is worth retrying."""


class ModelRefusedError(RuntimeError):
    """A provider call failed in a way that retrying cannot fix."""


@dataclass(frozen=True, slots=True)
class ModelAnswer:
    """What an adapter got back, before it is checked against the menu."""

    selected_display_id: str | None
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    usage: dict[str, int] | None = None
    raw: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


class ModelAgent(ABC):
    """A decision agent backed by a model behind a network call."""

    privileged = False

    def __init__(
        self,
        *,
        name: str,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {max_attempts}")
        self.name = name
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    def call_model(self, request: DecisionRequest) -> ModelAnswer:
        """Ask the provider. Raise ModelCallError for anything worth retrying."""

    def choose(self, request: DecisionRequest) -> DecisionResult:
        started = time.perf_counter()
        if not request.candidates:
            return self._failure("no candidates were offered", 0, started)

        last_error = "no attempt was made"
        for attempt in range(1, self.max_attempts + 1):
            try:
                answer = self.call_model(request)
            except ModelRefusedError as error:
                return self._failure(f"refused: {error}", attempt, started)
            except Exception as error:  # a provider failure is data, not a crash
                last_error = f"{type(error).__name__}: {error}"
                continue

            validated = self._validate(answer, request)
            if validated is not None:
                return self._failure(validated, attempt, started)
            return self._success(answer, request, attempt, started)

        return self._failure(last_error, self.max_attempts, started)

    def _validate(self, answer: ModelAnswer, request: DecisionRequest) -> str | None:
        """The reason this answer is unusable, or None if it is fine."""
        if answer.selected_display_id is None:
            return "the model selected nothing"
        if answer.selected_display_id not in request.display_ids:
            return f"the model chose {answer.selected_display_id!r}, which was not offered"
        return None

    def _success(
        self, answer: ModelAnswer, request: DecisionRequest, attempt: int, started: float
    ) -> DecisionResult:
        offered = set(request.display_ids)
        probabilities = (
            {k: v for k, v in answer.probabilities.items() if k in offered}
            if answer.probabilities
            else None
        )
        return DecisionResult(
            agent=self.name,
            selected_display_id=answer.selected_display_id,
            probabilities=probabilities,
            confidence=answer.confidence,
            latency_ms=self._elapsed_ms(started),
            usage=answer.usage,
            raw=answer.raw,
            attempt_count=attempt,
            extra=dict(answer.extra),
        )

    def _failure(self, reason: str, attempt: int, started: float) -> DecisionResult:
        return DecisionResult(
            agent=self.name,
            selected_display_id=None,
            latency_ms=self._elapsed_ms(started),
            error=reason,
            attempt_count=attempt,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        # Never zero: a record with no latency reads as a call that never happened.
        return max((time.perf_counter() - started) * 1000, 1e-6)
