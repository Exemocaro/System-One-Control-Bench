"""Baseline agents, and the guarantee that model requests carry no oracle data."""

from dataclasses import fields

import pytest

from system_one_control.agents.base import DecisionRequest, DecisionResult, build_request
from system_one_control.agents.baselines import (
    FakeProbabilityAgent,
    GreedyAgent,
    OracleAgent,
    RandomAgent,
    RolloutHeuristicAgent,
)
from system_one_control.candidates import build_candidate_set
from system_one_control.controllers import decide
from system_one_control.env import extract_snapshot, make_env
from system_one_control.oracle import label_candidate_set
from system_one_control.runner import build_agent
from system_one_control.transition import EAST
from tests.helpers import snapshot_from_ascii
from tests.maps import LAVA_ROOM, LONG_CORRIDOR


def _setup(env_id="MiniGrid-DoorKey-6x6-v0", seed=1, horizon=2, max_options=8):
    env = make_env(env_id, max_steps=100)
    env.reset(seed=seed)
    snapshot = extract_snapshot(env)
    built = build_candidate_set(snapshot, horizon=horizon, max_options=max_options, rng_seed=0)
    return snapshot, built


def test_the_request_type_has_no_field_that_could_carry_an_oracle_label():
    names = {f.name for f in fields(DecisionRequest)}
    for forbidden in ("cost", "costs", "distance", "optimal", "labels", "snapshot", "regret"):
        assert not any(forbidden in name for name in names), f"{forbidden} reachable from request"


def test_the_rendered_request_never_mentions_optimality():
    snapshot, built = _setup()
    request = build_request(snapshot, built, request_id="r1", description_mode="endpoint")
    text = " ".join(
        [request.state, request.legend, request.question]
        + [c.description for c in request.candidates]
    ).lower()
    # "costs one action" is a rule the model needs; oracle vocabulary is not.
    for forbidden in ("optimal", "shortest", "best option", "correct answer", "regret", "oracle"):
        assert forbidden not in text


def test_every_candidate_appears_exactly_once_under_an_opaque_id():
    snapshot, built = _setup()
    request = build_request(snapshot, built, request_id="r1")
    assert request.display_ids == tuple(c.display_id for c in built.candidates)
    assert len(set(request.display_ids)) == len(request.display_ids)


@pytest.mark.parametrize("mode", ["action_only", "endpoint"])
def test_all_agents_return_a_selection_from_the_offered_set(mode):
    snapshot, built = _setup()
    request = build_request(snapshot, built, request_id="r1", description_mode=mode)
    offered = set(request.display_ids)

    for agent in (RandomAgent(seed=0), FakeProbabilityAgent()):
        result = agent.choose(request)
        assert result.selected_display_id in offered
        assert result.error is None

    for agent in (OracleAgent(), GreedyAgent(), RolloutHeuristicAgent()):
        result = agent.choose_privileged(snapshot, built)
        assert result.selected_display_id in offered
        assert result.error is None


def test_random_agent_is_reproducible_and_spreads_over_the_menu():
    snapshot, built = _setup()
    request = build_request(snapshot, built, request_id="r1")

    first = [RandomAgent(seed=5).choose(request).selected_display_id for _ in range(1)]
    again = [RandomAgent(seed=5).choose(request).selected_display_id for _ in range(1)]
    assert first == again

    agent = RandomAgent(seed=5)
    picks = {agent.choose(request).selected_display_id for _ in range(200)}
    assert picks == set(request.display_ids), "uniform choice should cover the whole menu"


def test_fake_agent_returns_a_valid_probability_distribution():
    snapshot, built = _setup()
    request = build_request(snapshot, built, request_id="r1")
    result = FakeProbabilityAgent().choose(request)

    assert result.probabilities is not None
    assert set(result.probabilities) == set(request.display_ids)
    assert all(0.0 <= p <= 1.0 for p in result.probabilities.values())
    assert abs(sum(result.probabilities.values()) - 1.0) < 1e-9
    assert result.probabilities[result.selected_display_id] == max(result.probabilities.values())


def test_fake_agent_is_deterministic_for_the_same_request():
    snapshot, built = _setup()
    request = build_request(snapshot, built, request_id="r1")
    first = FakeProbabilityAgent().choose(request)
    again = FakeProbabilityAgent().choose(request)
    # latency is measured, not derived, so compare the decision itself.
    assert (first.selected_display_id, first.probabilities) == (
        again.selected_display_id,
        again.probabilities,
    )


@pytest.mark.parametrize("seed", range(8))
def test_oracle_agent_always_picks_a_best_offered_candidate(seed):
    snapshot, built = _setup(seed=seed)
    labels = label_candidate_set(snapshot, built)
    chosen = OracleAgent().choose_privileged(snapshot, built).selected_display_id
    assert chosen in labels.optimal_offered_ids


def test_oracle_agent_reports_failure_when_every_candidate_fails():
    from dataclasses import replace

    snapshot = snapshot_from_ascii(LAVA_ROOM, agent_pos=(1, 1), agent_dir=EAST)
    built = build_candidate_set(snapshot, horizon=1, max_options=99, rng_seed=0)
    only_lava = replace(built, candidates=tuple(c for c in built.candidates if c.actions == (2,)))

    result = OracleAgent().choose_privileged(snapshot, only_lava)
    assert result.selected_display_id in {c.display_id for c in only_lava.candidates}
    assert result.extra.get("all_candidates_fail") == "true"


def test_greedy_follows_the_goal_when_nothing_is_in_the_way():
    snapshot = snapshot_from_ascii(LONG_CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    built = build_candidate_set(snapshot, horizon=1, max_options=99, rng_seed=0)
    chosen = GreedyAgent().choose_privileged(snapshot, built).selected_display_id
    assert built.by_display_id(chosen).actions == (2,)


def test_greedy_is_trapped_by_the_detour_that_doorkey_requires():
    """The documented local-optimum failure: walking at the goal ignores the key."""
    env = make_env("MiniGrid-DoorKey-6x6-v0", max_steps=100)
    env.reset(seed=1)
    snapshot = extract_snapshot(env)
    built = build_candidate_set(snapshot, horizon=1, max_options=99, rng_seed=0)

    labels = label_candidate_set(snapshot, built)
    chosen = GreedyAgent().choose_privileged(snapshot, built).selected_display_id
    assert chosen not in labels.optimal_offered_ids


def test_rollout_heuristic_scores_the_endpoint_of_the_whole_sequence():
    snapshot = snapshot_from_ascii(LONG_CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    built = build_candidate_set(snapshot, horizon=2, max_options=99, rng_seed=0)
    chosen = RolloutHeuristicAgent().choose_privileged(snapshot, built).selected_display_id
    assert built.by_display_id(chosen).actions == (2, 2)


def test_agents_report_a_latency_and_their_own_name():
    snapshot, built = _setup()
    request = build_request(snapshot, built, request_id="r1")
    for result in (
        RandomAgent(seed=0).choose(request),
        FakeProbabilityAgent().choose(request),
        OracleAgent().choose_privileged(snapshot, built),
        GreedyAgent().choose_privileged(snapshot, built),
        RolloutHeuristicAgent().choose_privileged(snapshot, built),
    ):
        assert result.agent
        assert result.latency_ms >= 0.0


def test_privilege_is_declared_not_inferred_from_a_method_name():
    """A model adapter must never reach the true state by defining a method."""

    class Impostor:
        name = "impostor"

        def choose(self, request):
            return DecisionResult(agent=self.name, selected_display_id=request.display_ids[0])

        def choose_privileged(self, snapshot, candidate_set):
            raise AssertionError("an unprivileged agent was handed the true world state")

    snapshot, candidate_set = _setup()
    result = decide(Impostor(), snapshot, candidate_set, request_id="r")
    assert result.selected_display_id == candidate_set.candidates[0].display_id


def test_every_shipped_baseline_states_whether_it_is_privileged():
    for name in ("random", "fake", "greedy", "rollout_heuristic", "oracle"):
        agent = build_agent(name)
        assert isinstance(agent.privileged, bool)
