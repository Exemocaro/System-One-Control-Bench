"""Enumeration of the offered action sequences.

The effectiveness filter removes actions that cannot change the world. It is
neither the legal-action set nor a safety shield: walking into lava is effective
and stays on the menu. Nothing here consults the oracle, so candidate recall is
something the evaluator measures rather than something the generator arranged.
"""

from __future__ import annotations

import random

from system_one_control.domain import Candidate, CandidateSet, Snapshot
from system_one_control.transition import (
    DROP,
    FORWARD,
    LEFT,
    PICKUP,
    RIGHT,
    TOGGLE,
    is_goal_reached,
    physical,
    step,
)

# `done` is omitted for the supported static tasks: it changes nothing. In a
# dynamic task a physical no-op may be a useful wait, so this is task-specific.
PRIMITIVE_ACTIONS = (LEFT, RIGHT, FORWARD, PICKUP, DROP, TOGGLE)


def effective_actions(snapshot: Snapshot) -> tuple[int, ...]:
    """Actions that change the physical world or end the episode."""
    here = physical(snapshot)
    effective = []
    for action in PRIMITIVE_ACTIONS:
        result = step(snapshot, action)
        if result.terminated or physical(result.snapshot) != here:
            effective.append(action)
    return tuple(effective)


def _semantic_id(actions: tuple[int, ...]) -> str:
    return "-".join(str(action) for action in actions)


def enumerate_candidates(snapshot: Snapshot, horizon: int) -> tuple[Candidate, ...]:
    """All sequences of up to `horizon` effective actions.

    A sequence stops as soon as the episode ends, so a win two steps early is
    one candidate rather than several padded copies of the same win.
    """
    if horizon < 1:
        raise ValueError(f"horizon must be at least 1, got {horizon}")

    found: list[Candidate] = []

    def extend(state: Snapshot, prefix: tuple[int, ...]) -> None:
        for action in effective_actions(state):
            result = step(state, action)
            actions = (*prefix, action)
            ended = result.terminated or result.truncated
            if ended or len(actions) == horizon:
                found.append(
                    Candidate(
                        actions=actions,
                        semantic_id=_semantic_id(actions),
                        display_id="",
                        executed=len(actions),
                        outcome=result.snapshot,
                        terminated=result.terminated,
                        truncated=result.truncated,
                        success=is_goal_reached(result.snapshot),
                    )
                )
            else:
                extend(result.snapshot, actions)

    extend(snapshot, ())
    return tuple(found)


def build_candidate_set(
    snapshot: Snapshot,
    *,
    horizon: int,
    max_options: int,
    rng_seed: int,
    randomize_display_ids: bool = True,
) -> CandidateSet:
    """Enumerate, cap and order the candidates for one decision.

    Subsampling is seeded and uniform over the pool. It does not preferentially
    keep good candidates, so the optimal one can be absent; that is what the
    candidate-recall metric is for.
    """
    pool = enumerate_candidates(snapshot, horizon)
    rng = random.Random(rng_seed)

    chosen = list(pool)
    subsampled = len(chosen) > max_options
    if subsampled:
        chosen = rng.sample(chosen, max_options)
    if randomize_display_ids:
        rng.shuffle(chosen)

    labelled = tuple(
        Candidate(
            actions=candidate.actions,
            semantic_id=candidate.semantic_id,
            display_id=f"option_{index:03d}",
            executed=candidate.executed,
            outcome=candidate.outcome,
            terminated=candidate.terminated,
            truncated=candidate.truncated,
            success=candidate.success,
        )
        for index, candidate in enumerate(chosen)
    )
    return CandidateSet(
        candidates=labelled,
        horizon=horizon,
        pool_size=len(pool),
        subsampled=subsampled,
        rng_seed=rng_seed,
    )
