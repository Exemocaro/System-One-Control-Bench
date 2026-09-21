"""Candidate generation: effectiveness filtering, macro enumeration, presentation."""

import pytest

from system_one_control.candidates import (
    PRIMITIVE_ACTIONS,
    build_candidate_set,
    effective_actions,
    enumerate_candidates,
)
from system_one_control.env import extract_snapshot, make_env, restore_snapshot
from system_one_control.transition import (
    DROP,
    EAST,
    FORWARD,
    LEFT,
    NORTH,
    PICKUP,
    RIGHT,
    SOUTH,
    TOGGLE,
    WEST,
)
from tests.helpers import snapshot_from_ascii
from tests.maps import CORRIDOR, KEY_ROOM, LAVA_ROOM


def test_turns_are_always_effective():
    snapshot = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    assert {LEFT, RIGHT} <= set(effective_actions(snapshot))


def test_walking_into_a_wall_is_not_effective():
    snapshot = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=NORTH)
    assert FORWARD not in effective_actions(snapshot)


def test_toggling_a_locked_door_without_the_key_is_not_effective():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    assert TOGGLE not in effective_actions(snapshot)


def test_toggling_a_locked_door_while_holding_its_key_is_effective():
    key = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST).cell(1, 1)
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST, carrying=key)
    assert TOGGLE in effective_actions(snapshot)


def test_pickup_is_only_effective_when_something_is_there_to_take():
    facing_key = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=WEST)
    assert PICKUP in effective_actions(facing_key)

    facing_nothing = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=SOUTH)
    assert PICKUP not in effective_actions(facing_nothing)


def test_drop_is_not_effective_with_empty_hands():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=SOUTH)
    assert DROP not in effective_actions(snapshot)


def test_stepping_into_lava_stays_on_the_menu():
    """The filter is an effectiveness filter, not a safety shield."""
    snapshot = snapshot_from_ascii(LAVA_ROOM, agent_pos=(1, 1), agent_dir=EAST)
    assert FORWARD in effective_actions(snapshot)


def test_horizon_one_offers_exactly_the_effective_actions():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    candidates = enumerate_candidates(snapshot, horizon=1)
    assert {c.actions for c in candidates} == {(a,) for a in effective_actions(snapshot)}


def test_horizon_two_extends_each_prefix_by_its_own_effective_actions():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    candidates = enumerate_candidates(snapshot, horizon=2)
    assert all(len(c.actions) == 2 for c in candidates)
    assert len(candidates) > len(enumerate_candidates(snapshot, horizon=1))


def test_an_early_win_is_offered_at_the_length_it_actually_takes():
    """One cell from the goal: the direct win is a length-1 candidate."""
    snapshot = snapshot_from_ascii(CORRIDOR, agent_pos=(2, 1), agent_dir=EAST)
    candidates = enumerate_candidates(snapshot, horizon=3)

    direct = [c for c in candidates if c.actions == (FORWARD,)]
    assert len(direct) == 1
    assert direct[0].success and direct[0].executed == 1


def test_nothing_is_appended_after_a_candidate_has_already_ended():
    """A terminated sequence is never extended, so one win cannot be offered
    several times over as the same prefix plus different padding."""
    snapshot = snapshot_from_ascii(CORRIDOR, agent_pos=(2, 1), agent_dir=EAST)
    candidates = enumerate_candidates(snapshot, horizon=3)

    assert all(c.executed == len(c.actions) for c in candidates)
    ended = {c.actions for c in candidates if c.terminated or c.truncated}
    for candidate in candidates:
        for cut in range(1, len(candidate.actions)):
            assert candidate.actions[:cut] not in ended, (
                f"{candidate.actions} continues past a terminal prefix"
            )


def test_distinct_routes_to_the_same_win_are_kept_as_distinct_candidates():
    """Wasted turns still make a different action sequence, and multiplicity is
    retained in the main condition rather than deduplicated by endpoint."""
    snapshot = snapshot_from_ascii(CORRIDOR, agent_pos=(2, 1), agent_dir=EAST)
    winners = [c for c in enumerate_candidates(snapshot, horizon=3) if c.success]

    assert len(winners) > 1
    assert len({c.actions for c in winners}) == len(winners)


def test_candidates_carry_the_pool_size_and_a_seeded_subsample():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    pool = enumerate_candidates(snapshot, horizon=2)

    first = build_candidate_set(snapshot, horizon=2, max_options=3, rng_seed=7)
    again = build_candidate_set(snapshot, horizon=2, max_options=3, rng_seed=7)
    other = build_candidate_set(snapshot, horizon=2, max_options=3, rng_seed=8)

    assert first.pool_size == len(pool)
    assert len(first.candidates) == 3
    assert first.subsampled is True
    assert [c.actions for c in first.candidates] == [c.actions for c in again.candidates]
    assert [c.actions for c in first.candidates] != [c.actions for c in other.candidates]


def test_display_ids_are_opaque_sequential_and_carry_no_ordering_information():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    built = build_candidate_set(snapshot, horizon=2, max_options=8, rng_seed=1)

    ids = [c.display_id for c in built.candidates]
    assert ids == [f"option_{i:03d}" for i in range(len(ids))]
    assert len({c.semantic_id for c in built.candidates}) == len(built.candidates)


def test_presentation_order_is_shuffled_rather_than_enumeration_order():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    pool = enumerate_candidates(snapshot, horizon=2)
    built = build_candidate_set(snapshot, horizon=2, max_options=len(pool), rng_seed=3)

    assert {c.semantic_id for c in built.candidates} == {c.semantic_id for c in pool}
    assert [c.semantic_id for c in built.candidates] != [c.semantic_id for c in pool]


@pytest.mark.parametrize("seed", range(6))
def test_simulated_outcomes_match_the_real_environment(seed):
    env = make_env("MiniGrid-DoorKey-6x6-v0", max_steps=100)
    env.reset(seed=seed)
    snapshot = extract_snapshot(env)

    for candidate in enumerate_candidates(snapshot, horizon=2):
        restore_snapshot(env, snapshot)
        for action in candidate.actions:
            _, _, terminated, truncated, _ = env.step(action)
            if terminated or truncated:
                break
        assert extract_snapshot(env) == candidate.outcome


def test_primitive_actions_exclude_the_no_op():
    assert 6 not in PRIMITIVE_ACTIONS


def test_display_order_can_be_fixed_for_reproducing_a_single_request():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    ordered = build_candidate_set(
        snapshot, horizon=2, max_options=8, rng_seed=1, randomize_display_ids=False
    )
    pool = enumerate_candidates(snapshot, horizon=2)[: len(ordered)]
    assert [c.semantic_id for c in ordered.candidates] == [c.semantic_id for c in pool]
