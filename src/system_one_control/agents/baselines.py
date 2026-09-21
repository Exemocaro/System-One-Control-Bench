"""Non-neural baselines: random, greedy, rollout heuristic, oracle, and a fake.

Random is the matched-chance reference for whatever menu was offered. Greedy is
the cheap goal-following heuristic, and its DoorKey failure is the point of
including it. The rollout heuristic scores the same simulated endpoints a model
would be shown, separating what the simulator contributes from what the
selection contributes. The oracle is the achievable ceiling.
"""

from __future__ import annotations

import hashlib
import random
import time
from abc import ABC, abstractmethod

from system_one_control.agents.base import DecisionRequest, DecisionResult
from system_one_control.domain import Candidate, CandidateSet, Snapshot
from system_one_control.oracle import label_candidate_set
from system_one_control.transition import GOAL, step


class Timer:
    """Wall-clock duration of one decision, in milliseconds."""

    def __enter__(self) -> Timer:
        self._started = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.elapsed_ms = (time.perf_counter() - self._started) * 1000


class UnprivilegedBaseline(ABC):
    """A baseline that answers from the sanitized request, like a model does."""

    privileged = False

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def choose(self, request: DecisionRequest) -> DecisionResult: ...


class PrivilegedBaseline(ABC):
    """A baseline allowed to read the true world state. Never a model."""

    privileged = True

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def choose_privileged(
        self, snapshot: Snapshot, candidate_set: CandidateSet
    ) -> DecisionResult: ...


class ScoringBaseline(PrivilegedBaseline):
    """Picks the candidate with the lowest score, ties broken by display id."""

    def choose_privileged(self, snapshot: Snapshot, candidate_set: CandidateSet) -> DecisionResult:
        with Timer() as timer:
            goal = _goal_position(snapshot)
            ranked = sorted(
                candidate_set.candidates,
                key=lambda c: (*self.score(snapshot, c, goal), c.display_id),
            )
            chosen = ranked[0].display_id if ranked else None
        return DecisionResult(
            agent=self.name, selected_display_id=chosen, latency_ms=timer.elapsed_ms
        )

    @abstractmethod
    def score(
        self, snapshot: Snapshot, candidate: Candidate, goal: tuple[int, int] | None
    ) -> tuple[int, ...]: ...


def _goal_position(snapshot: Snapshot) -> tuple[int, int] | None:
    for y, row in enumerate(snapshot.cells):
        for x, cell in enumerate(row):
            if cell[0] == GOAL:
                return (x, y)
    return None


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _distance_from(position: tuple[int, int], goal: tuple[int, int] | None) -> int:
    return 0 if goal is None else _manhattan(position, goal)


class RandomAgent(UnprivilegedBaseline):
    """Uniform choice over the candidates actually offered."""

    def __init__(self, seed: int = 0) -> None:
        super().__init__("random")
        self._rng = random.Random(seed)

    def choose(self, request: DecisionRequest) -> DecisionResult:
        with Timer() as timer:
            chosen = self._rng.choice(request.display_ids)
            uniform = 1.0 / len(request.candidates)
        return DecisionResult(
            agent=self.name,
            selected_display_id=chosen,
            probabilities=dict.fromkeys(request.display_ids, uniform),
            latency_ms=timer.elapsed_ms,
        )


class FakeProbabilityAgent(UnprivilegedBaseline):
    """Deterministic stand-in so the pipeline can be exercised without a model."""

    def __init__(self) -> None:
        super().__init__("fake")

    def choose(self, request: DecisionRequest) -> DecisionResult:
        with Timer() as timer:
            weights = {}
            for candidate in request.candidates:
                seed = f"{request.request_id}|{candidate.display_id}|{candidate.description}"
                digest = hashlib.sha256(seed.encode()).digest()
                weights[candidate.display_id] = int.from_bytes(digest[:4], "big") + 1
            total = sum(weights.values())
            probabilities = {key: value / total for key, value in weights.items()}
            chosen = max(probabilities, key=lambda key: probabilities[key])
        return DecisionResult(
            agent=self.name,
            selected_display_id=chosen,
            probabilities=probabilities,
            confidence=probabilities[chosen],
            latency_ms=timer.elapsed_ms,
        )


class GreedyAgent(ScoringBaseline):
    """Take whichever first action moves closest to the goal, ignoring detours.

    Straight-line distance says nothing about fetching a key, so on DoorKey this
    walks at the door and stalls. That local optimum is why it is here.
    """

    def __init__(self) -> None:
        super().__init__("greedy")

    def score(
        self, snapshot: Snapshot, candidate: Candidate, goal: tuple[int, int] | None
    ) -> tuple[int, ...]:
        after = step(snapshot, candidate.actions[0]).snapshot
        return (_distance_from(after.agent_pos, goal),)


class RolloutHeuristicAgent(ScoringBaseline):
    """Score the simulated endpoint of each whole candidate, cheaply.

    It sees exactly the rollout information the endpoint description shows a
    model, so the gap between the two measures selection rather than simulation.
    """

    def __init__(self) -> None:
        super().__init__("rollout_heuristic")

    def score(
        self, snapshot: Snapshot, candidate: Candidate, goal: tuple[int, int] | None
    ) -> tuple[int, ...]:
        if candidate.success:
            return (-1, candidate.executed, 0)
        dead_end = 1 if candidate.terminated else 0
        return (dead_end, _distance_from(candidate.outcome.agent_pos, goal), candidate.executed)


class OracleAgent(PrivilegedBaseline):
    """Pick a candidate of minimum exact cost — the achievable ceiling."""

    def __init__(self) -> None:
        super().__init__("oracle")

    def choose_privileged(self, snapshot: Snapshot, candidate_set: CandidateSet) -> DecisionResult:
        with Timer() as timer:
            labels = label_candidate_set(snapshot, candidate_set)
            if labels.optimal_offered_ids:
                chosen = min(labels.optimal_offered_ids)
            elif candidate_set.candidates:
                chosen = candidate_set.candidates[0].display_id
            else:
                chosen = None
        return DecisionResult(
            agent=self.name,
            selected_display_id=chosen,
            latency_ms=timer.elapsed_ms,
            extra={"all_candidates_fail": "true" if labels.all_candidates_fail else "false"},
        )
