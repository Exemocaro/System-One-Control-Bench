"""Execution cadence, shared by every agent.

A controller is two numbers: how long a plan it asks for (``horizon``) and how
much of it runs before replanning (``execute``). Reactive is 1/1, open-loop
macro is h/h, receding-horizon is h/k with k < h. Episodes roll out on the pure
transition function, which the tests replay in MiniGrid to confirm they agree.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import cast

from system_one_control.agents.base import (
    Agent,
    DecisionAgent,
    DecisionResult,
    PrivilegedAgent,
    build_request,
    is_privileged,
)
from system_one_control.candidates import build_candidate_set
from system_one_control.domain import Candidate, CandidateLabels, CandidateSet, Snapshot
from system_one_control.oracle import label_candidate_set
from system_one_control.transition import is_goal_reached, step


@dataclass(frozen=True, slots=True)
class Controller:
    name: str
    horizon: int
    execute: int

    def __post_init__(self) -> None:
        if self.horizon < 1:
            raise ValueError(f"horizon must be at least 1, got {self.horizon}")
        if not 1 <= self.execute <= self.horizon:
            raise ValueError(
                f"execute must be between 1 and horizon ({self.horizon}), got {self.execute}"
            )


REACTIVE = Controller(name="reactive", horizon=1, execute=1)
MACRO_OPEN_LOOP = Controller(name="macro_open_loop", horizon=2, execute=2)
MACRO_RECEDING = Controller(name="macro_receding", horizon=2, execute=1)

CONTROLLERS = {c.name: c for c in (REACTIVE, MACRO_OPEN_LOOP, MACRO_RECEDING)}


@dataclass(frozen=True, slots=True)
class DecisionStep:
    step_index: int
    snapshot: Snapshot
    candidate_set: CandidateSet
    result: DecisionResult
    labels: CandidateLabels
    executed_actions: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EpisodeResult:
    agent: str
    controller: str
    success: bool
    terminated: bool
    truncated: bool
    invalid_selection: bool
    steps_used: int
    final: Snapshot | None
    decisions: tuple[DecisionStep, ...] = field(default_factory=tuple)
    layout_id: str | None = None


def decide(
    agent: Agent,
    snapshot: Snapshot,
    candidate_set: CandidateSet,
    *,
    request_id: str,
    description_mode: str = "action_only",
) -> DecisionResult:
    """Ask an agent for a decision, giving declared baselines the real state."""
    if is_privileged(agent):
        return cast(PrivilegedAgent, agent).choose_privileged(snapshot, candidate_set)
    request = build_request(
        snapshot, candidate_set, request_id=request_id, description_mode=description_mode
    )
    return cast(DecisionAgent, agent).choose(request)


class EpisodeRunner:
    """Drives one episode under one controller, recording every decision."""

    def __init__(
        self,
        agent: Agent,
        controller: Controller,
        *,
        rng_seed: int,
        max_options: int,
        description_mode: str = "action_only",
        episode_id: str = "episode",
        max_decisions: int | None = None,
    ) -> None:
        self.agent = agent
        self.controller = controller
        self.rng_seed = rng_seed
        self.max_options = max_options
        self.description_mode = description_mode
        self.episode_id = episode_id
        self.max_decisions = max_decisions

    def run(self, start: Snapshot) -> EpisodeResult:
        snapshot = start
        decisions: list[DecisionStep] = []
        terminated = truncated = invalid = False

        while not (terminated or truncated):
            if self.max_decisions is not None and len(decisions) >= self.max_decisions:
                break
            if snapshot.step_count >= snapshot.max_steps:
                truncated = True
                break

            before = snapshot
            index = len(decisions)
            candidate_set = self._candidates(before, index)
            if not candidate_set.candidates:
                break

            result = self._ask(before, candidate_set, index)
            labels = label_candidate_set(before, candidate_set)
            chosen = self._resolve(candidate_set, result)

            if chosen is None:
                invalid = True
                decisions.append(DecisionStep(index, before, candidate_set, result, labels, ()))
                break

            snapshot, executed, terminated, truncated = self._execute(snapshot, chosen)
            decisions.append(DecisionStep(index, before, candidate_set, result, labels, executed))

        return EpisodeResult(
            agent=getattr(self.agent, "name", "unknown"),
            controller=self.controller.name,
            success=is_goal_reached(snapshot),
            terminated=terminated,
            truncated=truncated,
            invalid_selection=invalid,
            steps_used=snapshot.step_count - start.step_count,
            final=snapshot,
            decisions=tuple(decisions),
        )

    def _candidates(self, snapshot: Snapshot, index: int) -> CandidateSet:
        return build_candidate_set(
            snapshot,
            horizon=self.controller.horizon,
            max_options=self.max_options,
            rng_seed=self.rng_seed + index,
        )

    def _ask(self, snapshot: Snapshot, candidate_set: CandidateSet, index: int) -> DecisionResult:
        return decide(
            self.agent,
            snapshot,
            candidate_set,
            request_id=f"{self.episode_id}:{index}",
            description_mode=self.description_mode,
        )

    def _resolve(self, candidate_set: CandidateSet, result: DecisionResult) -> Candidate | None:
        """The candidate the agent named, or None if it named nothing valid."""
        if result.selected_display_id is None:
            return None
        try:
            return candidate_set.by_display_id(result.selected_display_id)
        except KeyError:
            return None

    def _execute(
        self, snapshot: Snapshot, chosen: Candidate
    ) -> tuple[Snapshot, tuple[int, ...], bool, bool]:
        executed: list[int] = []
        terminated = truncated = False
        for action in chosen.actions[: self.controller.execute]:
            outcome = step(snapshot, action)
            snapshot = outcome.snapshot
            executed.append(action)
            terminated, truncated = outcome.terminated, outcome.truncated
            if terminated or truncated:
                break
        return snapshot, tuple(executed), terminated, truncated


def run_episode(
    start: Snapshot,
    agent: Agent,
    controller: Controller,
    *,
    rng_seed: int,
    max_options: int,
    description_mode: str = "action_only",
    episode_id: str = "episode",
    max_decisions: int | None = None,
    layout_id: str | None = None,
) -> EpisodeResult:
    """Drive one episode to success, failure or the end of its step budget.

    ``max_decisions`` stops early, for callers that want the first few states of
    a trajectory rather than its outcome.
    """
    runner = EpisodeRunner(
        agent,
        controller,
        rng_seed=rng_seed,
        max_options=max_options,
        description_mode=description_mode,
        episode_id=episode_id,
        max_decisions=max_decisions,
    )
    return replace(runner.run(start), layout_id=layout_id)
