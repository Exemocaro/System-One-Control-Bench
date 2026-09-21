"""Cross-check the pure transition function against the real environment."""

import random

import pytest

from system_one_control.domain import Snapshot
from system_one_control.env import extract_snapshot, make_env, restore_snapshot
from system_one_control.transition import EMPTY_CELL, FORWARD, GOAL, NORTH, step
from system_one_control.transition import step as pure_step

ALL_ACTIONS = (0, 1, 2, 3, 4, 5, 6)

FAST_CASES = [("MiniGrid-DoorKey-6x6-v0", 1), ("MiniGrid-Empty-Random-6x6-v0", 3)]
SLOW_CASES = [
    (env_id, seed)
    for env_id in ("MiniGrid-DoorKey-6x6-v0", "MiniGrid-Empty-Random-6x6-v0")
    for seed in range(12)
]


def _real_step(env, snapshot, action):
    """Ground truth: apply `action` to the real environment from `snapshot`."""
    restore_snapshot(env, snapshot)
    _, reward, terminated, truncated, _ = env.step(action)
    return extract_snapshot(env), float(reward), bool(terminated), bool(truncated)


def _compare_all_actions(env, snapshot):
    for action in ALL_ACTIONS:
        expected = _real_step(env, snapshot, action)
        result = pure_step(snapshot, action)
        actual = (result.snapshot, result.reward, result.terminated, result.truncated)
        assert actual == expected, (
            f"action {action} diverged at agent_pos={snapshot.agent_pos} "
            f"dir={snapshot.agent_dir} carrying={snapshot.carrying}"
        )


def _walk_and_compare(env_id, seed, walk_length, rng_seed):
    """Random-walk the real environment, cross-checking every action en route."""
    env = make_env(env_id, max_steps=100)
    env.reset(seed=seed)
    rng = random.Random(rng_seed)
    visited = 0

    snapshot = extract_snapshot(env)
    for _ in range(walk_length):
        _compare_all_actions(env, snapshot)
        visited += 1

        action = rng.choice(ALL_ACTIONS)
        snapshot, _, terminated, truncated = _real_step(env, snapshot, action)
        if terminated or truncated:
            env.reset(seed=seed)
            snapshot = extract_snapshot(env)
    return visited


@pytest.mark.parametrize(("env_id", "seed"), FAST_CASES)
def test_pure_transition_matches_minigrid_on_a_random_walk(env_id, seed):
    assert _walk_and_compare(env_id, seed, walk_length=60, rng_seed=0) == 60


def test_pure_transition_handles_the_full_doorkey_unlock():
    """Walk a hand-written unlock path so pickup/toggle are certainly exercised."""
    env = make_env("MiniGrid-DoorKey-6x6-v0", max_steps=100)
    env.reset(seed=1)
    snapshot = extract_snapshot(env)

    for action in (2, 2, 3, 2, 1, 5, 2, 2):
        _compare_all_actions(env, snapshot)
        snapshot, _, _, _ = _real_step(env, snapshot, action)

    assert snapshot.carrying is not None, "path should end holding the key"


@pytest.mark.slow
@pytest.mark.parametrize(("env_id", "seed"), SLOW_CASES)
def test_pure_transition_matches_minigrid_exhaustively(env_id, seed):
    assert _walk_and_compare(env_id, seed, walk_length=200, rng_seed=seed) == 200


def test_facing_off_the_edge_of_a_borderless_grid_is_treated_as_a_wall():
    """Negative indices would silently wrap to the far side of the grid."""
    open_field = Snapshot(
        env_id="hand-built",
        width=2,
        height=2,
        cells=((EMPTY_CELL, EMPTY_CELL), (EMPTY_CELL, (GOAL, 1, 0))),
        agent_pos=(0, 0),
        agent_dir=NORTH,
        carrying=None,
        mission="hand-built",
        step_count=0,
        max_steps=100,
    )
    result = step(open_field, FORWARD)
    assert result.snapshot.agent_pos == (0, 0)
    assert not result.terminated
