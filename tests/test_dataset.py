"""The offline state bank: layouts, splits, collection policies, manifest."""

import pytest

from system_one_control.dataset import (
    COLLECTION_POLICIES,
    assign_splits,
    build_state_bank,
    census_layouts,
    layout_id,
)
from system_one_control.env import extract_snapshot, make_env

DOORKEY = "MiniGrid-DoorKey-6x6-v0"
EMPTY_RANDOM = "MiniGrid-Empty-Random-6x6-v0"


def test_layout_id_ignores_where_the_agent_happens_to_stand():
    from dataclasses import replace

    env = make_env(DOORKEY, max_steps=100)
    env.reset(seed=1)
    snapshot = extract_snapshot(env)
    moved = replace(snapshot, agent_pos=(3, 3), agent_dir=0)
    assert layout_id(moved) == layout_id(snapshot)


def test_layout_id_separates_genuinely_different_maps():
    env = make_env(DOORKEY, max_steps=100)
    env.reset(seed=0)
    first = layout_id(extract_snapshot(env))
    seeds = (s for s in range(1, 50))
    different = next(
        layout_id(extract_snapshot(env))
        for seed in seeds
        if (env.reset(seed=seed), True)[1] and layout_id(extract_snapshot(env)) != first
    )
    assert different != first


def test_census_counts_distinct_layouts_and_distinct_starts():
    census = census_layouts(DOORKEY, seeds=range(60))
    assert census.env_id == DOORKEY
    assert 1 < census.layout_count <= 60
    assert census.start_state_count >= census.layout_count
    assert sum(len(seeds) for seeds in census.layouts.values()) == 60


def test_empty_random_is_one_layout_so_it_can_only_be_a_sanity_check():
    census = census_layouts(EMPTY_RANDOM, seeds=range(40))
    assert census.layout_count == 1
    assert census.start_state_count > 1


def test_splits_are_assigned_to_layouts_and_are_reproducible():
    census = census_layouts(DOORKEY, seeds=range(80))
    first = assign_splits(census.layouts, rng_seed=1)
    again = assign_splits(census.layouts, rng_seed=1)
    other = assign_splits(census.layouts, rng_seed=2)

    assert first == again
    assert first != other
    assert set(first) == set(census.layouts)
    assert set(first.values()) <= {"development", "calibration", "test"}


def test_every_split_receives_at_least_one_layout():
    census = census_layouts(DOORKEY, seeds=range(120))
    splits = assign_splits(census.layouts, rng_seed=0)
    assert set(splits.values()) == {"development", "calibration", "test"}


def test_a_layout_never_appears_in_two_splits():
    bank = build_state_bank(
        DOORKEY, seeds=range(60), states_per_episode=3, rng_seed=0, max_steps=100
    )
    by_layout: dict[str, set[str]] = {}
    for state in bank.states:
        by_layout.setdefault(state.layout_id, set()).add(state.split)
    assert all(len(splits) == 1 for splits in by_layout.values())


def test_states_are_deduplicated():
    bank = build_state_bank(
        DOORKEY, seeds=range(40), states_per_episode=4, rng_seed=0, max_steps=100
    )
    ids = [state.state_id for state in bank.states]
    assert len(ids) == len(set(ids))


def test_states_come_from_every_collection_policy():
    bank = build_state_bank(
        DOORKEY, seeds=range(40), states_per_episode=4, rng_seed=0, max_steps=100
    )
    assert {state.policy for state in bank.states} == set(COLLECTION_POLICIES)


def test_the_bank_is_reproducible_for_a_fixed_seed():
    kwargs = dict(seeds=range(30), states_per_episode=3, rng_seed=7, max_steps=100)
    first = build_state_bank(DOORKEY, **kwargs)
    again = build_state_bank(DOORKEY, **kwargs)
    assert [s.state_id for s in first.states] == [s.state_id for s in again.states]
    assert first.manifest.checksum == again.manifest.checksum


def test_the_manifest_records_what_the_bank_contains():
    bank = build_state_bank(
        DOORKEY, seeds=range(30), states_per_episode=3, rng_seed=0, max_steps=100
    )
    manifest = bank.manifest
    assert manifest.env_id == DOORKEY
    assert manifest.state_count == len(bank.states)
    assert manifest.layout_count > 0
    assert manifest.serializer_version and manifest.checksum.startswith("sha256:")
    assert sum(manifest.states_per_split.values()) == manifest.state_count


def test_collected_states_are_solvable_or_explicitly_flagged():
    bank = build_state_bank(
        DOORKEY, seeds=range(30), states_per_episode=3, rng_seed=0, max_steps=100
    )
    for state in bank.states:
        assert state.distance is not None or state.solvable is False


def test_no_collected_state_is_already_finished():
    bank = build_state_bank(
        DOORKEY, seeds=range(30), states_per_episode=3, rng_seed=0, max_steps=100
    )
    assert all(state.distance != 0 for state in bank.states if state.distance is not None)


@pytest.mark.parametrize("split", ["development", "calibration", "test"])
def test_states_can_be_selected_by_split(split):
    bank = build_state_bank(
        DOORKEY, seeds=range(80), states_per_episode=3, rng_seed=0, max_steps=100
    )
    chosen = bank.by_split(split)
    assert chosen
    assert all(state.split == split for state in chosen)


def test_a_single_layout_environment_falls_back_to_splitting_within_the_layout():
    """Empty-Random has one map. Splitting by layout would put everything in one
    split and leave the others empty, so the bank splits by episode instead and
    says so, because such a result is only a within-layout sanity check."""
    bank = build_state_bank(
        EMPTY_RANDOM, seeds=range(40), states_per_episode=3, rng_seed=0, max_steps=100
    )
    assert bank.manifest.layout_count == 1
    assert bank.manifest.within_layout_split is True
    assert all(count > 0 for count in bank.manifest.states_per_split.values())


def test_a_multi_layout_environment_still_splits_by_layout():
    bank = build_state_bank(
        DOORKEY, seeds=range(80), states_per_episode=3, rng_seed=0, max_steps=100
    )
    assert bank.manifest.within_layout_split is False
    assert bank.manifest.layout_count > 1
