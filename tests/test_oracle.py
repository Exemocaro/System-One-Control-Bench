"""Oracle checks: hand-counted distances, real replays, and complete tie sets.

Hand-built maps matter here: they stop the simulator and the oracle passing
together by sharing one bug.
"""

import pytest

from system_one_control.env import extract_snapshot, make_env
from system_one_control.oracle import distance_to_goal, optimal_actions, optimal_plan
from system_one_control.transition import EAST, FORWARD, LEFT, NORTH, RIGHT, is_goal_reached, step
from tests.helpers import snapshot_from_ascii
from tests.maps import (
    CORNER_ROOM,
    FAR_CORNER_ROOM,
    KEY_ROOM,
    LAVA_SHORTCUT,
    OPEN_ROOM,
    SEALED_ROOM,
)


def test_distance_counts_forward_moves_when_already_facing_the_goal():
    snapshot = snapshot_from_ascii(OPEN_ROOM, agent_pos=(1, 1), agent_dir=EAST)
    assert distance_to_goal(snapshot) == 2


def test_distance_includes_the_turns_needed_to_face_the_goal():
    snapshot = snapshot_from_ascii(OPEN_ROOM, agent_pos=(1, 1), agent_dir=NORTH)
    assert distance_to_goal(snapshot) == 3


def test_distance_accounts_for_fetching_the_key_and_unlocking_the_door():
    """Hand-counted from (2,1) facing east: turn west (2) + pickup (1) +
    turn east (2) + toggle (1) + forward to (3,1) and (4,1) (2) + turn south (1)
    + forward to (4,2) and (4,3) (2) = 11."""
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    assert distance_to_goal(snapshot) == 11


def test_unreachable_goal_has_no_distance():
    snapshot = snapshot_from_ascii(SEALED_ROOM, agent_pos=(1, 1), agent_dir=EAST)
    assert distance_to_goal(snapshot) is None


def test_optimal_actions_keep_every_tie():
    """Goal directly behind the agent: turning either way costs the same two turns."""
    snapshot = snapshot_from_ascii(CORNER_ROOM, agent_pos=(1, 1), agent_dir=NORTH)
    assert distance_to_goal(snapshot) == 4  # two turns to face south, two forwards
    assert optimal_actions(snapshot) == frozenset({LEFT, RIGHT})


def test_turning_is_never_free_so_advancing_first_beats_turning_first():
    """Every path needs four forwards, so the cheapest spends only one turn."""
    snapshot = snapshot_from_ascii(FAR_CORNER_ROOM, agent_pos=(1, 1), agent_dir=EAST)
    assert distance_to_goal(snapshot) == 5
    assert optimal_actions(snapshot) == frozenset({FORWARD})


def test_a_turn_away_from_the_goal_is_not_optimal():
    snapshot = snapshot_from_ascii(OPEN_ROOM, agent_pos=(1, 1), agent_dir=EAST)
    assert optimal_actions(snapshot) == frozenset({FORWARD})
    assert LEFT not in optimal_actions(snapshot)


@pytest.mark.parametrize("env_id", ["MiniGrid-DoorKey-6x6-v0", "MiniGrid-Empty-Random-6x6-v0"])
@pytest.mark.parametrize("seed", range(10))
def test_optimal_plan_replays_to_success_in_the_real_environment(env_id, seed):
    """The strongest check: the plan must actually solve the real environment."""
    env = make_env(env_id, max_steps=100)
    env.reset(seed=seed)
    snapshot = extract_snapshot(env)

    plan = optimal_plan(snapshot)
    assert plan is not None, f"{env_id} seed {seed} should be solvable"
    assert len(plan) == distance_to_goal(snapshot)

    terminated = False
    for action in plan:
        _, reward, terminated, truncated, _ = env.step(action)
        assert not truncated, "optimal plan should not exhaust the step budget"
    assert terminated and reward > 0, "plan must end on the goal"


@pytest.mark.parametrize("seed", range(10))
def test_every_optimal_action_leads_to_a_state_one_step_closer(seed):
    env = make_env("MiniGrid-DoorKey-6x6-v0", max_steps=100)
    env.reset(seed=seed)
    snapshot = extract_snapshot(env)
    here = distance_to_goal(snapshot)

    actions = optimal_actions(snapshot)
    assert actions, "a solvable state must offer at least one optimal action"
    for action in actions:
        assert distance_to_goal(step(snapshot, action).snapshot) == here - 1


def test_an_action_that_walks_into_lava_is_never_called_optimal():
    """BFS from the lava cell still finds the goal, but the agent is already dead."""
    snapshot = snapshot_from_ascii(LAVA_SHORTCUT, agent_pos=(1, 2), agent_dir=EAST)
    assert distance_to_goal(snapshot) == 5
    assert FORWARD not in optimal_actions(snapshot)
    assert optimal_actions(snapshot) == {LEFT}


def test_every_optimal_action_survives_the_step_it_names():
    snapshot = snapshot_from_ascii(LAVA_SHORTCUT, agent_pos=(1, 2), agent_dir=EAST)
    for action in optimal_actions(snapshot):
        result = step(snapshot, action)
        assert not result.terminated or is_goal_reached(result.snapshot)
