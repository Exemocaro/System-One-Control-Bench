"""The agent registry, which is where model adapters will plug in."""

import pytest

from system_one_control.agents.baselines import RandomAgent
from system_one_control.agents.registry import AgentRegistry, build_agent


def test_a_registered_agent_is_built_by_name():
    registry = AgentRegistry()
    registry.register("demo", lambda seed: RandomAgent(seed=seed))
    assert registry.build("demo").name == "random"
    assert "demo" in registry


def test_registering_the_same_name_twice_is_refused():
    """Two adapters silently sharing a name would mislabel every record."""
    registry = AgentRegistry()
    registry.register("demo", lambda seed: RandomAgent(seed=seed))
    with pytest.raises(ValueError, match="already registered"):
        registry.register("demo", lambda seed: RandomAgent(seed=seed))


def test_an_unknown_name_lists_what_is_available():
    registry = AgentRegistry()
    registry.register("demo", lambda seed: RandomAgent(seed=seed))
    with pytest.raises(ValueError, match="demo"):
        registry.build("nope")


def test_the_seed_reaches_the_agent_that_wants_one():
    ids = tuple(f"option_{i:03d}" for i in range(8))
    assert _draw(build_agent("random", seed=1), ids) == _draw(build_agent("random", seed=1), ids)
    # 20 draws over 8 options: two seeds agreeing by chance is 8**-20.
    assert _draw(build_agent("random", seed=1), ids) != _draw(build_agent("random", seed=2), ids)


def _draw(agent, ids):
    from system_one_control.agents.base import CandidateView, DecisionRequest

    request = DecisionRequest(
        request_id="r",
        state="s",
        legend="l",
        question="q",
        candidates=tuple(CandidateView(i, "d") for i in ids),
    )
    return [agent.choose(request).selected_display_id for _ in range(20)]


def test_every_default_agent_is_registered():
    from system_one_control.agents.registry import DEFAULT_REGISTRY

    assert DEFAULT_REGISTRY.names() == [
        "fake",
        "greedy",
        "jev",
        "oracle",
        "random",
        "rollout_heuristic",
    ]
