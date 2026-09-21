"""Breadth-first ground truth: exact distances, plans and optimal-action sets.

Every action costs one step, so BFS is exact. Search runs over physical state
with the step counter normalized away, which keeps physical solvability separate
from whether a plan fits the remaining budget.

Nothing here may be reachable from a model adapter.
"""

from __future__ import annotations

from collections import deque
from functools import lru_cache

from system_one_control.domain import Candidate, CandidateLabels, CandidateSet, Snapshot
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

# `done` is omitted: a no-op can never shorten a plan.
SEARCH_ACTIONS = (LEFT, RIGHT, FORWARD, PICKUP, DROP, TOGGLE)


@lru_cache(maxsize=65536)
def _search(start: Snapshot) -> tuple[int, tuple[int, ...]] | None:
    """Shortest action sequence from `start` to the goal, or None if unreachable."""
    if is_goal_reached(start):
        return 0, ()

    seen = {start}
    frontier: deque[tuple[Snapshot, tuple[int, ...]]] = deque([(start, ())])

    while frontier:
        state, plan = frontier.popleft()
        for action in SEARCH_ACTIONS:
            result = step(state, action)
            successor = physical(result.snapshot)
            if successor in seen:
                continue
            extended = (*plan, action)
            if is_goal_reached(successor):
                return len(extended), extended
            if result.terminated:
                continue  # a terminal that is not success, e.g. lava
            seen.add(successor)
            frontier.append((successor, extended))
    return None


def distance_to_goal(snapshot: Snapshot) -> int | None:
    """Minimum primitive actions to success, ignoring the episode budget."""
    found = _search(physical(snapshot))
    return None if found is None else found[0]


def optimal_plan(snapshot: Snapshot) -> tuple[int, ...] | None:
    """One shortest action sequence to the goal, or None if unreachable."""
    found = _search(physical(snapshot))
    return None if found is None else found[1]


def optimal_actions(snapshot: Snapshot) -> frozenset[int]:
    """Every first action on some shortest path, so ties are never scored wrong."""
    here = distance_to_goal(snapshot)
    if here is None or here == 0:
        return frozenset()

    optimal = set()
    for action in SEARCH_ACTIONS:
        result = step(snapshot, action)
        if result.terminated and not is_goal_reached(result.snapshot):
            continue  # searching on from a dead agent would score lava as optimal
        after = distance_to_goal(result.snapshot)
        if after is not None and after + 1 == here:
            optimal.add(action)
    return frozenset(optimal)


def candidate_cost(snapshot: Snapshot, candidate: Candidate) -> int | None:
    """Actions executed plus the distance still to go; None means infinite.

    None covers both a candidate that ends in failure and one whose total cannot
    fit the remaining budget, so a tight state is never confused with an
    impossible one.
    """
    if candidate.success:
        return candidate.executed
    if candidate.terminated:
        return None  # a terminal that is not success, e.g. lava

    remaining = distance_to_goal(candidate.outcome)
    if remaining is None:
        return None

    total = candidate.executed + remaining
    budget_left = snapshot.max_steps - snapshot.step_count
    return None if total > budget_left else total


def label_candidate_set(snapshot: Snapshot, candidate_set: CandidateSet) -> CandidateLabels:
    """Annotate an offered menu with everything the evaluator scores against."""
    costs = {c.display_id: candidate_cost(snapshot, c) for c in candidate_set.candidates}
    finite = {display_id: cost for display_id, cost in costs.items() if cost is not None}

    best = min(finite.values()) if finite else None
    optimal_ids = frozenset(d for d, cost in finite.items() if cost == best)

    distance = distance_to_goal(snapshot)
    gap = None if best is None or distance is None else best - distance

    return CandidateLabels(
        distance=distance,
        best_offered_cost=best,
        optimal_offered_ids=optimal_ids,
        candidate_gap=gap,
        global_optimal_present=best is not None and best == distance,
        global_optimal_first_actions=optimal_actions(snapshot),
        all_candidates_fail=bool(candidate_set.candidates) and not finite,
        costs=costs,
    )
