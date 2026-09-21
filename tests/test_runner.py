"""The offline sweep, online episodes, budget guards and config loading."""

import pytest

from system_one_control.analysis import decision_metrics, episode_metrics
from system_one_control.config import ExperimentConfig, load_config
from system_one_control.controllers import REACTIVE, EpisodeResult
from system_one_control.dataset import build_state_bank
from system_one_control.runner import (
    BudgetExceeded,
    CallBudget,
    build_agent,
    estimate_calls,
    evaluate_offline,
    evaluate_online,
    select_states,
)

DOORKEY = "MiniGrid-DoorKey-6x6-v0"


def _episode(*, success, layout):
    """A bare EpisodeResult, for testing how episodes are aggregated."""
    return EpisodeResult(
        agent="demo",
        controller="reactive",
        success=success,
        terminated=success,
        truncated=not success,
        invalid_selection=False,
        steps_used=3,
        final=None,
        layout_id=layout,
    )


@pytest.fixture(scope="module")
def bank():
    return build_state_bank(
        DOORKEY, seeds=range(40), states_per_episode=2, rng_seed=0, max_steps=100
    )


def test_every_named_baseline_can_be_constructed():
    for name in ("random", "greedy", "rollout_heuristic", "oracle", "fake"):
        assert build_agent(name) is not None


def test_an_unknown_agent_is_rejected_by_name():
    with pytest.raises(ValueError, match="unknown agent"):
        build_agent("no-such-model")


def test_every_agent_answers_the_same_frozen_states(bank):
    states = select_states(bank, split="test", limit=15)
    runs = {
        name: evaluate_offline(
            states, build_agent(name), run_id="r", horizon=1, max_options=8, rng_seed=0
        )
        for name in ("random", "greedy", "oracle")
    }
    state_ids = {name: [row["state_id"] for row in rows] for name, rows in runs.items()}
    assert len(set(map(tuple, state_ids.values()))) == 1, "comparisons must be paired"


def test_the_oracle_is_always_correct_on_the_offline_bank(bank):
    states = select_states(bank, split="test", limit=20)
    records = evaluate_offline(
        states, build_agent("oracle"), run_id="r", horizon=2, max_options=8, rng_seed=0
    )
    scorable = [row for row in records if not row["all_candidates_fail"]]
    assert scorable
    assert all(row["correct"] for row in scorable)
    assert all(row["regret"] == 0 for row in scorable)


def test_random_scores_worse_than_the_oracle_on_the_same_states(bank):
    states = select_states(bank, split="test", limit=25)
    oracle = decision_metrics(
        evaluate_offline(
            states, build_agent("oracle"), run_id="r", horizon=1, max_options=8, rng_seed=0
        ),
        bootstrap_samples=100,
    )
    random_agent = decision_metrics(
        evaluate_offline(
            states, build_agent("random"), run_id="r", horizon=1, max_options=8, rng_seed=0
        ),
        bootstrap_samples=100,
    )
    assert oracle.accuracy.point > random_agent.accuracy.point


def test_records_carry_the_split_and_layout_needed_for_clustering(bank):
    states = select_states(bank, split="test", limit=10)
    records = evaluate_offline(
        states, build_agent("random"), run_id="r", horizon=1, max_options=8, rng_seed=0
    )
    assert all(row["split"] == "test" for row in records)
    assert all(row["layout_id"] for row in records)


def test_a_call_budget_stops_a_run_before_it_overspends(bank):
    states = select_states(bank, split="test", limit=20)
    budget = CallBudget(max_calls=5)
    with pytest.raises(BudgetExceeded):
        evaluate_offline(
            states,
            build_agent("random"),
            run_id="r",
            horizon=1,
            max_options=8,
            rng_seed=0,
            budget=budget,
        )
    assert budget.used == 5


def test_the_call_count_can_be_estimated_before_spending_anything(bank):
    states = select_states(bank, split="test", limit=10)
    assert estimate_calls(states, ["a", "b"], [1, 2]) == 40


def test_online_episodes_produce_one_record_per_decision(bank):
    starts = select_states(bank, split="test", limit=5)
    episodes, records = evaluate_online(
        starts, build_agent("oracle"), REACTIVE, run_id="r", max_options=8, rng_seed=0
    )
    assert len(episodes) == 5
    assert len(records) == sum(len(e.decisions) for e in episodes)
    assert all(row["episode_id"] for row in records)


def test_the_oracle_solves_the_online_episodes_it_is_given(bank):
    starts = select_states(bank, split="test", limit=8)
    episodes, _ = evaluate_online(
        starts, build_agent("oracle"), REACTIVE, run_id="r", max_options=8, rng_seed=0
    )
    assert all(episode.success for episode in episodes)


def test_online_budget_counts_every_decision_in_an_episode(bank):
    starts = select_states(bank, split="test", limit=8)
    budget = CallBudget(max_calls=3)
    with pytest.raises(BudgetExceeded):
        evaluate_online(
            starts,
            build_agent("random"),
            REACTIVE,
            run_id="r",
            max_options=8,
            rng_seed=0,
            budget=budget,
        )


def test_the_default_config_validates():
    config = ExperimentConfig(experiment_id="v0")
    assert config.dataset.split == "test"
    assert config.offline.horizons == (1, 2)


def test_a_typo_in_a_config_is_rejected_rather_than_ignored():
    with pytest.raises(ValueError):
        ExperimentConfig(experiment_id="v0", horizon=2)


def test_an_unknown_split_is_rejected():
    with pytest.raises(ValueError):
        ExperimentConfig(experiment_id="v0", dataset={"split": "holdout"})


def test_a_config_round_trips_through_yaml(tmp_path):
    path = tmp_path / "v0.yaml"
    path.write_text(
        "experiment_id: v0_symbolic\nseed: 7\nagents: [random, oracle]\n"
        "offline:\n  horizons: [1]\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.experiment_id == "v0_symbolic"
    assert config.seed == 7
    assert config.agents == ("random", "oracle")
    assert config.offline.horizons == (1,)


def test_online_success_intervals_resample_layouts_not_episodes():
    """Episodes from one map move together; treating them as independent lies."""
    episodes = [
        _episode(success=True, layout="L0"),
        _episode(success=True, layout="L0"),
        _episode(success=False, layout="L1"),
    ]
    by_layout = episode_metrics(episodes, layout_of=lambda e: e.layout_id, bootstrap_samples=200)
    by_episode = episode_metrics(episodes, bootstrap_samples=200)
    assert by_layout.success_rate is not None and by_episode.success_rate is not None
    spread = by_layout.success_rate.high - by_layout.success_rate.low
    assert spread > by_episode.success_rate.high - by_episode.success_rate.low


def test_a_config_naming_an_unknown_controller_is_rejected():
    with pytest.raises(ValueError, match="unknown controllers"):
        ExperimentConfig(experiment_id="x", online={"controllers": ["teleport"]})


def test_a_config_naming_a_known_controller_is_accepted():
    config = ExperimentConfig(experiment_id="x", online={"controllers": ["macro_receding"]})
    assert config.online.controllers == ("macro_receding",)
