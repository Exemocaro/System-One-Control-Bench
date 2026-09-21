"""Snapshots must round-trip without changing semantics."""

from system_one_control.env import extract_snapshot, make_env, restore_snapshot

DOORKEY = "MiniGrid-DoorKey-6x6-v0"

# From (1,4) facing north on seed 1: take the key, unlock the door, step through.
UNLOCK_SEQUENCE = (2, 2, 3, 2, 1, 5, 2, 2)


def _trace(env, actions):
    """Step the environment, recording the full semantic result of each action."""
    trace = []
    for action in actions:
        _, reward, terminated, truncated, _ = env.step(action)
        trace.append((extract_snapshot(env), reward, terminated, truncated))
        if terminated or truncated:
            break
    return trace


def test_restored_snapshot_reproduces_the_same_step_sequence():
    env = make_env(DOORKEY, max_steps=100)
    env.reset(seed=1)

    start = extract_snapshot(env)
    baseline = _trace(env, UNLOCK_SEQUENCE)

    restore_snapshot(env, start)
    assert extract_snapshot(env) == start

    replayed = _trace(env, UNLOCK_SEQUENCE)
    assert replayed == baseline


def test_snapshot_records_the_dynamics_that_the_sequence_changes():
    """Guard against a snapshot that round-trips because it captures nothing."""
    env = make_env(DOORKEY, max_steps=100)
    env.reset(seed=1)

    start = extract_snapshot(env)
    after = _trace(env, UNLOCK_SEQUENCE)[-1][0]

    assert after != start
    assert start.carrying is None and after.carrying is not None
    assert after.agent_pos != start.agent_pos
    assert after.step_count == len(UNLOCK_SEQUENCE)
