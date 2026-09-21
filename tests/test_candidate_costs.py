"""Exact candidate costs and the labels derived from them."""

from dataclasses import replace

from system_one_control.candidates import build_candidate_set, enumerate_candidates
from system_one_control.env import extract_snapshot, make_env
from system_one_control.oracle import candidate_cost, distance_to_goal, label_candidate_set
from system_one_control.transition import EAST
from tests.helpers import snapshot_from_ascii
from tests.maps import LAVA_ROOM, LONG_CORRIDOR


def _candidate(snapshot, actions, horizon):
    return next(c for c in enumerate_candidates(snapshot, horizon) if c.actions == actions)


def test_cost_is_actions_taken_plus_distance_remaining():
    snapshot = snapshot_from_ascii(LONG_CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    assert distance_to_goal(snapshot) == 3

    forward_twice = _candidate(snapshot, (2, 2), horizon=2)
    assert candidate_cost(snapshot, forward_twice) == 3  # two taken, one left

    turn_then_back = _candidate(snapshot, (0, 1), horizon=2)
    assert candidate_cost(snapshot, turn_then_back) == 5  # two wasted, three left


def test_a_candidate_that_reaches_the_goal_costs_only_the_actions_it_used():
    snapshot = snapshot_from_ascii(LONG_CORRIDOR, agent_pos=(3, 1), agent_dir=EAST)
    winner = _candidate(snapshot, (2,), horizon=2)
    assert winner.success
    assert candidate_cost(snapshot, winner) == 1


def test_a_candidate_that_cannot_finish_within_the_budget_has_infinite_cost():
    snapshot = snapshot_from_ascii(LONG_CORRIDOR, agent_pos=(1, 1), agent_dir=EAST, max_steps=4)
    tight = replace(snapshot, step_count=2)  # two actions left, three needed

    forward = _candidate(tight, (2,), horizon=1)
    assert candidate_cost(tight, forward) is None


def test_stepping_into_lava_has_infinite_cost():
    snapshot = snapshot_from_ascii(LAVA_ROOM, agent_pos=(1, 1), agent_dir=EAST)
    doomed = _candidate(snapshot, (2,), horizon=1)
    assert doomed.terminated and not doomed.success
    assert candidate_cost(snapshot, doomed) is None


def test_labels_name_every_tied_best_candidate():
    snapshot = snapshot_from_ascii(LONG_CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    built = build_candidate_set(snapshot, horizon=1, max_options=99, rng_seed=0)
    labels = label_candidate_set(snapshot, built)

    assert labels.distance == 3
    assert labels.best_offered_cost == 3
    assert labels.candidate_gap == 0
    assert labels.global_optimal_present is True

    best = {built.by_display_id(i).actions for i in labels.optimal_offered_ids}
    assert best == {(2,)}


def test_a_menu_where_everything_fails_is_recorded_as_failure_not_as_a_tie():
    """An infinity tie must never mark every candidate correct."""
    snapshot = snapshot_from_ascii(LAVA_ROOM, agent_pos=(1, 1), agent_dir=EAST)
    forward_only = build_candidate_set(snapshot, horizon=1, max_options=99, rng_seed=0)
    only_lava = replace(
        forward_only,
        candidates=tuple(c for c in forward_only.candidates if c.actions == (2,)),
    )

    labels = label_candidate_set(snapshot, only_lava)
    assert labels.all_candidates_fail is True
    assert labels.optimal_offered_ids == frozenset()
    assert labels.best_offered_cost is None


def test_candidate_gap_shows_when_the_menu_omits_the_best_move():
    snapshot = snapshot_from_ascii(LONG_CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    full = build_candidate_set(snapshot, horizon=1, max_options=99, rng_seed=0)
    without_forward = replace(
        full, candidates=tuple(c for c in full.candidates if c.actions != (2,))
    )

    labels = label_candidate_set(snapshot, without_forward)
    assert labels.global_optimal_present is False
    assert labels.candidate_gap == 2  # a wasted turn, then the three real steps


def test_globally_optimal_first_actions_are_reported_independently_of_the_menu():
    snapshot = snapshot_from_ascii(LONG_CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    empty = build_candidate_set(snapshot, horizon=1, max_options=99, rng_seed=0)
    labels = label_candidate_set(snapshot, replace(empty, candidates=()))
    assert labels.global_optimal_first_actions == frozenset({2})


def test_labels_on_a_real_doorkey_state_are_self_consistent():
    env = make_env("MiniGrid-DoorKey-6x6-v0", max_steps=100)
    env.reset(seed=4)
    snapshot = extract_snapshot(env)
    built = build_candidate_set(snapshot, horizon=2, max_options=8, rng_seed=0)
    labels = label_candidate_set(snapshot, built)

    assert labels.distance is not None
    assert labels.best_offered_cost is not None
    assert labels.best_offered_cost >= labels.distance
    assert labels.candidate_gap == labels.best_offered_cost - labels.distance
    for display_id in labels.optimal_offered_ids:
        assert candidate_cost(snapshot, built.by_display_id(display_id)) == labels.best_offered_cost
