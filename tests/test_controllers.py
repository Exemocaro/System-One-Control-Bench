"""Execution cadence: reactive, open-loop macro and receding-horizon control."""

import pytest

from system_one_control.agents.baselines import (
    FakeProbabilityAgent,
    GreedyAgent,
    OracleAgent,
    RandomAgent,
)
from system_one_control.controllers import (
    MACRO_OPEN_LOOP,
    MACRO_RECEDING,
    REACTIVE,
    Controller,
    run_episode,
)
from system_one_control.env import extract_snapshot, make_env, restore_snapshot

DOORKEY = "MiniGrid-DoorKey-6x6-v0"


def _start(env_id=DOORKEY, seed=1, max_steps=100):
    env = make_env(env_id, max_steps=max_steps)
    env.reset(seed=seed)
    return extract_snapshot(env)


def test_controller_rejects_executing_more_actions_than_it_planned():
    with pytest.raises(ValueError):
        Controller(name="bad", horizon=2, execute=3)


def test_reactive_is_horizon_one_executing_one_action():
    assert (REACTIVE.horizon, REACTIVE.execute) == (1, 1)


def test_open_loop_executes_the_whole_plan_and_receding_executes_one_step():
    assert MACRO_OPEN_LOOP.execute == MACRO_OPEN_LOOP.horizon
    assert MACRO_RECEDING.execute == 1 and MACRO_RECEDING.horizon > 1


@pytest.mark.parametrize("seed", range(6))
def test_the_oracle_solves_every_doorkey_start_under_reactive_control(seed):
    episode = run_episode(_start(seed=seed), OracleAgent(), REACTIVE, rng_seed=0, max_options=8)
    assert episode.success
    assert episode.steps_used <= 100


@pytest.mark.parametrize("controller", [REACTIVE, MACRO_OPEN_LOOP, MACRO_RECEDING])
def test_the_oracle_solves_doorkey_under_every_cadence(controller):
    episode = run_episode(_start(seed=2), OracleAgent(), controller, rng_seed=0, max_options=32)
    assert episode.success


def test_open_loop_executes_every_action_of_the_chosen_plan():
    episode = run_episode(
        _start(seed=3), OracleAgent(), MACRO_OPEN_LOOP, rng_seed=0, max_options=32
    )
    for decision in episode.decisions[:-1]:
        chosen = decision.candidate_set.by_display_id(decision.result.selected_display_id)
        assert decision.executed_actions == chosen.actions


def test_receding_horizon_executes_only_the_first_action_of_a_longer_plan():
    episode = run_episode(_start(seed=3), OracleAgent(), MACRO_RECEDING, rng_seed=0, max_options=32)
    for decision in episode.decisions:
        chosen = decision.candidate_set.by_display_id(decision.result.selected_display_id)
        if not chosen.terminated:
            assert decision.executed_actions == chosen.actions[:1]


def test_greedy_fails_to_solve_doorkey_and_exhausts_its_budget():
    """The detour it cannot see is what makes it a useful baseline."""
    episode = run_episode(_start(seed=1), GreedyAgent(), REACTIVE, rng_seed=0, max_options=8)
    assert not episode.success
    assert episode.truncated


def test_an_episode_stops_at_the_step_budget():
    episode = run_episode(
        _start(seed=1, max_steps=12), RandomAgent(seed=0), REACTIVE, rng_seed=0, max_options=8
    )
    assert episode.steps_used <= 12
    assert episode.success or episode.truncated


def test_every_decision_is_recorded_with_its_labels_and_the_menu_it_saw():
    episode = run_episode(
        _start(seed=1), FakeProbabilityAgent(), REACTIVE, rng_seed=0, max_options=8
    )
    assert episode.decisions
    for decision in episode.decisions:
        assert decision.result.selected_display_id in {
            c.display_id for c in decision.candidate_set.candidates
        }
        assert decision.labels.distance is not None or decision.labels.all_candidates_fail
        assert decision.executed_actions


@pytest.mark.parametrize("seed", range(4))
def test_an_episode_replays_identically_in_the_real_environment(seed):
    """Episodes run on the pure transition function; this proves that is the
    same thing as running them in MiniGrid."""
    start = _start(seed=seed)
    episode = run_episode(start, OracleAgent(), REACTIVE, rng_seed=0, max_options=8)

    env = make_env(DOORKEY, max_steps=100)
    env.reset(seed=seed)
    restore_snapshot(env, start)

    terminated = truncated = False
    steps = 0
    for decision in episode.decisions:
        for action in decision.executed_actions:
            _, reward, terminated, truncated, _ = env.step(action)
            steps += 1
            if terminated or truncated:
                break
        if terminated or truncated:
            break

    assert steps == episode.steps_used
    assert (terminated and reward > 0) == episode.success


def test_an_agent_that_selects_nothing_ends_the_episode_as_a_recorded_failure():
    class Mute:
        name = "mute"

        def choose(self, request):
            from system_one_control.agents.base import DecisionResult

            return DecisionResult(agent="mute", selected_display_id=None, error="no answer")

    episode = run_episode(_start(seed=1), Mute(), REACTIVE, rng_seed=0, max_options=8)
    assert not episode.success
    assert episode.invalid_selection
    assert episode.decisions[-1].result.error == "no answer"


def test_an_episode_can_be_capped_at_a_number_of_decisions():
    """State collection takes a few states per episode; rolling the whole
    episode out first would do far more search than it needs."""
    capped = run_episode(
        _start(seed=1), RandomAgent(seed=0), REACTIVE, rng_seed=0, max_options=8, max_decisions=3
    )
    assert len(capped.decisions) == 3
    assert not capped.truncated

    full = run_episode(_start(seed=1), RandomAgent(seed=0), REACTIVE, rng_seed=0, max_options=8)
    assert len(full.decisions) > 3
    assert [d.executed_actions for d in full.decisions[:3]] == [
        d.executed_actions for d in capped.decisions
    ]
