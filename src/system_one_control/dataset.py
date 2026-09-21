"""The offline state bank: the common states every agent is scored on.

Order matters. Worlds are generated first, deduplicated into layouts, and the
layouts are assigned to splits *before* any state is collected, so correlated
states from one map cannot straddle a split.

States are collected under several policies, so the bank is not made only of
states an optimal player would visit.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from system_one_control.agents.base import Agent, DecisionResult
from system_one_control.agents.baselines import GreedyAgent, OracleAgent, RandomAgent
from system_one_control.controllers import REACTIVE, run_episode
from system_one_control.domain import CandidateSet, Snapshot
from system_one_control.env import extract_snapshot, make_env
from system_one_control.observation import (
    LEGEND_VERSION,
    SERIALIZER_VERSION,
    evaluation_state_id,
    physical_state_id,
)
from system_one_control.oracle import distance_to_goal

COLLECTION_POLICIES = ("oracle", "random", "greedy", "perturbed")
SPLITS = ("development", "calibration", "test")
DEFAULT_SPLIT_WEIGHTS = {"development": 0.3, "calibration": 0.2, "test": 0.5}


def layout_id(snapshot: Snapshot) -> str:
    """Identity of the static map, independent of where the agent stands."""
    return "sha256:" + hashlib.sha256(repr(snapshot.cells).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class LayoutCensus:
    env_id: str
    layouts: dict[str, tuple[int, ...]]
    start_state_count: int

    @property
    def layout_count(self) -> int:
        return len(self.layouts)


def census_layouts(env_id: str, seeds: Iterable[int], max_steps: int = 100) -> LayoutCensus:
    """Count how many genuinely distinct maps a range of seeds produces.

    Worth running before trusting a sample size: several MiniGrid environments
    generate far fewer layouts than seeds.
    """
    env = make_env(env_id, max_steps=max_steps)
    layouts: dict[str, list[int]] = {}
    starts: set[str] = set()
    for seed in seeds:
        env.reset(seed=seed)
        snapshot = extract_snapshot(env)
        layouts.setdefault(layout_id(snapshot), []).append(seed)
        starts.add(physical_state_id(snapshot))
    return LayoutCensus(
        env_id=env_id,
        layouts={key: tuple(value) for key, value in layouts.items()},
        start_state_count=len(starts),
    )


def assign_splits(
    groups: Mapping[str, tuple[int, ...]],
    *,
    rng_seed: int,
    weights: dict[str, float] | None = None,
) -> dict[str, str]:
    """Assign whole groups to splits, giving every split at least one."""
    weights = weights or DEFAULT_SPLIT_WEIGHTS
    keys = sorted(groups)
    rng = random.Random(rng_seed)
    rng.shuffle(keys)

    if len(keys) < len(SPLITS):
        return {key: SPLITS[index % len(SPLITS)] for index, key in enumerate(keys)}

    assignment = {key: SPLITS[index] for index, key in enumerate(keys[: len(SPLITS)])}
    names = list(SPLITS)
    shares = [weights[name] for name in names]
    for key in keys[len(SPLITS) :]:
        assignment[key] = rng.choices(names, weights=shares, k=1)[0]
    return assignment


class SplitPlan:
    """Decides which split a world belongs to, before any state is collected.

    Splitting by layout is what makes a held-out test set held out. When an
    environment has fewer layouts than splits, that is impossible, so the plan
    falls back to splitting by episode seed and says so through
    ``within_layout``; results from such a bank are a sanity check, not
    held-out evidence.
    """

    def __init__(
        self,
        census: LayoutCensus,
        seeds: Sequence[int],
        *,
        rng_seed: int,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.within_layout = census.layout_count < len(SPLITS)
        groups: Mapping[str, tuple[int, ...]] = (
            {str(seed): (seed,) for seed in seeds} if self.within_layout else census.layouts
        )
        self._assignment = assign_splits(groups, rng_seed=rng_seed, weights=weights)

    def split_for(self, *, seed: int, layout: str) -> str:
        return self._assignment[str(seed) if self.within_layout else layout]


@dataclass(frozen=True, slots=True)
class StateRecord:
    state_id: str
    physical_id: str
    layout_id: str
    env_id: str
    env_seed: int
    split: str
    policy: str
    step_index: int
    snapshot: Snapshot
    distance: int | None
    solvable: bool


@dataclass(frozen=True, slots=True)
class StateBankManifest:
    env_id: str
    state_count: int
    layout_count: int
    seeds: tuple[int, ...]
    states_per_split: dict[str, int]
    states_per_policy: dict[str, int]
    rng_seed: int
    max_steps: int
    serializer_version: str
    legend_version: str
    checksum: str
    within_layout_split: bool


@dataclass(frozen=True, slots=True)
class StateBank:
    states: tuple[StateRecord, ...]
    manifest: StateBankManifest
    census: LayoutCensus

    def by_split(self, split: str) -> tuple[StateRecord, ...]:
        return tuple(state for state in self.states if state.split == split)


class PerturbedAgent:
    """Optimal play, derailed for the first few decisions.

    Collecting only from an optimal roll-out would fill the bank with states a
    good player reaches, and never with the ones it has to dig itself out of.
    """

    privileged = True

    def __init__(self, noisy_steps: int, seed: int) -> None:
        self.name = "perturbed"
        self._noisy = noisy_steps
        self._seed = seed
        self._oracle = OracleAgent()
        self._seen = 0

    def choose_privileged(self, snapshot: Snapshot, candidate_set: CandidateSet) -> DecisionResult:
        self._seen += 1
        result = self._oracle.choose_privileged(snapshot, candidate_set)
        if self._seen > self._noisy:
            return result
        ids = [candidate.display_id for candidate in candidate_set.candidates]
        rng = random.Random(f"{self._seed}:{self._seen}:{len(ids)}")
        return replace(result, agent=self.name, selected_display_id=rng.choice(ids))


def collection_agent(policy: str, seed: int) -> Agent:
    """Build the policy that drives one collection roll-out."""
    if policy == "oracle":
        return OracleAgent()
    if policy == "random":
        return RandomAgent(seed=seed)
    if policy == "greedy":
        return GreedyAgent()
    if policy == "perturbed":
        return PerturbedAgent(noisy_steps=2, seed=seed)
    raise ValueError(f"unknown collection policy: {policy!r}")


class StateBankBuilder:
    """Generates layouts, splits them, then collects states inside each split."""

    def __init__(
        self,
        env_id: str,
        *,
        seeds: Sequence[int] | Iterable[int],
        states_per_episode: int,
        rng_seed: int,
        max_steps: int = 100,
        max_options: int = 8,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.env_id = env_id
        self.seeds = tuple(seeds)
        self.states_per_episode = states_per_episode
        self.rng_seed = rng_seed
        self.max_steps = max_steps
        self.max_options = max_options
        self.weights = weights

    def build(self) -> StateBank:
        census = census_layouts(self.env_id, self.seeds, max_steps=self.max_steps)
        plan = SplitPlan(census, self.seeds, rng_seed=self.rng_seed, weights=self.weights)

        env = make_env(self.env_id, max_steps=self.max_steps)
        collected: dict[str, StateRecord] = {}
        for seed in self.seeds:
            env.reset(seed=seed)
            start = extract_snapshot(env)
            layout = layout_id(start)
            split = plan.split_for(seed=seed, layout=layout)
            for offset, policy in enumerate(COLLECTION_POLICIES):
                self._collect(collected, start, seed, offset, policy, layout, split)

        states = tuple(collected[key] for key in sorted(collected))
        return StateBank(
            states=states,
            manifest=self._manifest(states, census, plan),
            census=census,
        )

    def _collect(
        self,
        collected: dict[str, StateRecord],
        start: Snapshot,
        seed: int,
        offset: int,
        policy: str,
        layout: str,
        split: str,
    ) -> None:
        episode_seed = self.rng_seed + seed + offset
        episode = run_episode(
            start,
            collection_agent(policy, seed=episode_seed),
            REACTIVE,
            rng_seed=episode_seed,
            max_options=self.max_options,
            episode_id=f"{self.env_id}:{seed}:{policy}",
            max_decisions=self.states_per_episode,
        )
        for decision in episode.decisions:
            snapshot = decision.snapshot
            distance = distance_to_goal(snapshot)
            if distance == 0:
                continue  # already on the goal: there is nothing to decide
            state_id = evaluation_state_id(snapshot)
            if state_id in collected:
                continue
            collected[state_id] = StateRecord(
                state_id=state_id,
                physical_id=physical_state_id(snapshot),
                layout_id=layout,
                env_id=self.env_id,
                env_seed=seed,
                split=split,
                policy=policy,
                step_index=decision.step_index,
                snapshot=snapshot,
                distance=distance,
                solvable=distance is not None,
            )

    def _manifest(
        self, states: tuple[StateRecord, ...], census: LayoutCensus, plan: SplitPlan
    ) -> StateBankManifest:
        joined = "|".join(state.state_id for state in states).encode()
        return StateBankManifest(
            env_id=self.env_id,
            state_count=len(states),
            layout_count=census.layout_count,
            seeds=self.seeds,
            states_per_split={s: sum(1 for r in states if r.split == s) for s in SPLITS},
            states_per_policy={
                p: sum(1 for r in states if r.policy == p) for p in COLLECTION_POLICIES
            },
            rng_seed=self.rng_seed,
            max_steps=self.max_steps,
            serializer_version=SERIALIZER_VERSION,
            legend_version=LEGEND_VERSION,
            checksum="sha256:" + hashlib.sha256(joined).hexdigest(),
            within_layout_split=plan.within_layout,
        )


def build_state_bank(
    env_id: str,
    *,
    seeds: Sequence[int] | Iterable[int],
    states_per_episode: int,
    rng_seed: int,
    max_steps: int = 100,
    max_options: int = 8,
    weights: dict[str, float] | None = None,
) -> StateBank:
    """Generate layouts, split them, then collect states inside each split."""
    return StateBankBuilder(
        env_id,
        seeds=seeds,
        states_per_episode=states_per_episode,
        rng_seed=rng_seed,
        max_steps=max_steps,
        max_options=max_options,
        weights=weights,
    ).build()
