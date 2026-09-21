"""Running agents over the state bank, and over live episodes.

The offline sweep comes first by design: every agent answers the same frozen
states, so no agent is judged on a distribution its own mistakes created. Online
episodes then measure what happens when those errors compound. Every call passes
through a budget guard, which stops being redundant once an adapter costs money.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from system_one_control.agents.base import Agent
from system_one_control.agents.registry import AgentRegistry, build_agent
from system_one_control.candidates import build_candidate_set
from system_one_control.controllers import (
    CONTROLLERS,
    MACRO_OPEN_LOOP,
    MACRO_RECEDING,
    REACTIVE,
    Controller,
    EpisodeResult,
    decide,
    run_episode,
)
from system_one_control.dataset import StateBank, StateRecord
from system_one_control.oracle import label_candidate_set
from system_one_control.records import decision_record

__all__ = [
    "CONTROLLERS",
    "MACRO_OPEN_LOOP",
    "MACRO_RECEDING",
    "REACTIVE",
    "AgentRegistry",
    "BudgetExceeded",
    "CallBudget",
    "OfflineSweep",
    "OnlineSweep",
    "build_agent",
    "estimate_calls",
    "evaluate_offline",
    "evaluate_online",
    "select_states",
]


class BudgetExceeded(RuntimeError):
    """Raised when a run would make more calls than it was allowed."""


@dataclass
class CallBudget:
    """A hard ceiling on requests, checked before every call."""

    max_calls: int | None = None
    used: int = 0

    def spend(self, amount: int = 1) -> None:
        if self.max_calls is not None and self.used + amount > self.max_calls:
            raise BudgetExceeded(
                f"run would make {self.used + amount} calls, limit is {self.max_calls}"
            )
        self.used += amount


@dataclass(frozen=True, slots=True)
class SweepSettings:
    """The knobs both sweeps share, so neither drifts from the other."""

    run_id: str
    max_options: int
    rng_seed: int
    description_mode: str = "action_only"
    randomize_display_ids: bool = True


def estimate_calls(
    states: Sequence[StateRecord], agents: Sequence[str], horizons: Sequence[int]
) -> int:
    """How many decisions a sweep would ask for, before running it."""
    return len(states) * len(agents) * len(horizons)


def select_states(bank: StateBank, *, split: str, limit: int | None) -> tuple[StateRecord, ...]:
    """Take the evaluation states for one split, deterministically."""
    states = bank.by_split(split)
    return states if limit is None else states[:limit]


class OfflineSweep:
    """Asks one agent for a decision on every state in the bank."""

    def __init__(self, settings: SweepSettings, budget: CallBudget | None = None) -> None:
        self.settings = settings
        self.budget = budget or CallBudget()

    def run(
        self, states: Iterable[StateRecord], agent: Agent, *, horizon: int
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for index, state in enumerate(states):
            candidate_set = build_candidate_set(
                state.snapshot,
                horizon=horizon,
                max_options=self.settings.max_options,
                rng_seed=self.settings.rng_seed + index,
                randomize_display_ids=self.settings.randomize_display_ids,
            )
            if not candidate_set.candidates:
                continue

            self.budget.spend()
            request_id = f"{self.settings.run_id}:{state.state_id[-12:]}:{horizon}"
            result = decide(
                agent,
                state.snapshot,
                candidate_set,
                request_id=request_id,
                description_mode=self.settings.description_mode,
            )
            records.append(
                decision_record(
                    run_id=self.settings.run_id,
                    request_id=request_id,
                    snapshot=state.snapshot,
                    candidate_set=candidate_set,
                    result=result,
                    labels=label_candidate_set(state.snapshot, candidate_set),
                    controller="offline",
                    split=state.split,
                    layout_id=state.layout_id,
                    step_index=state.step_index,
                )
            )
        return records


class OnlineSweep:
    """Runs one agent through whole episodes, recording every decision."""

    def __init__(self, settings: SweepSettings, budget: CallBudget | None = None) -> None:
        self.settings = settings
        self.budget = budget or CallBudget()

    def run(
        self, starts: Sequence[StateRecord], agent: Agent, controller: Controller
    ) -> tuple[list[EpisodeResult], list[dict[str, Any]]]:
        episodes: list[EpisodeResult] = []
        records: list[dict[str, Any]] = []

        for index, state in enumerate(starts):
            episode_id = f"{self.settings.run_id}:{controller.name}:{index}"
            episode = run_episode(
                state.snapshot,
                agent,
                controller,
                rng_seed=self.settings.rng_seed + index,
                max_options=self.settings.max_options,
                description_mode=self.settings.description_mode,
                episode_id=episode_id,
                layout_id=state.layout_id,
            )
            self.budget.spend(len(episode.decisions))
            episodes.append(episode)
            records.extend(self._records_for(episode, state, controller, episode_id))
        return episodes, records

    def _records_for(
        self,
        episode: EpisodeResult,
        state: StateRecord,
        controller: Controller,
        episode_id: str,
    ) -> list[dict[str, Any]]:
        return [
            decision_record(
                run_id=self.settings.run_id,
                request_id=f"{episode_id}:{decision.step_index}",
                snapshot=decision.snapshot,
                candidate_set=decision.candidate_set,
                result=decision.result,
                labels=decision.labels,
                controller=controller.name,
                split=state.split,
                layout_id=state.layout_id,
                episode_id=episode_id,
                step_index=decision.step_index,
            )
            for decision in episode.decisions
        ]


def evaluate_offline(
    states: Iterable[StateRecord],
    agent: Agent,
    *,
    run_id: str,
    horizon: int,
    max_options: int,
    rng_seed: int,
    description_mode: str = "action_only",
    randomize_display_ids: bool = True,
    budget: CallBudget | None = None,
) -> list[dict[str, Any]]:
    """Ask one agent for a decision on every state in the bank."""
    settings = SweepSettings(
        run_id=run_id,
        max_options=max_options,
        rng_seed=rng_seed,
        description_mode=description_mode,
        randomize_display_ids=randomize_display_ids,
    )
    return OfflineSweep(settings, budget).run(states, agent, horizon=horizon)


def evaluate_online(
    starts: Sequence[StateRecord],
    agent: Agent,
    controller: Controller,
    *,
    run_id: str,
    max_options: int,
    rng_seed: int,
    description_mode: str = "action_only",
    budget: CallBudget | None = None,
) -> tuple[list[EpisodeResult], list[dict[str, Any]]]:
    """Run one agent through whole episodes, recording every decision."""
    settings = SweepSettings(
        run_id=run_id,
        max_options=max_options,
        rng_seed=rng_seed,
        description_mode=description_mode,
    )
    return OnlineSweep(settings, budget).run(starts, agent, controller)
