"""Where an agent name becomes an agent. Model adapters register here."""

from __future__ import annotations

from collections.abc import Callable

from system_one_control.agents.base import Agent
from system_one_control.agents.baselines import (
    FakeProbabilityAgent,
    GreedyAgent,
    OracleAgent,
    RandomAgent,
    RolloutHeuristicAgent,
)

Builder = Callable[[int], Agent]


class AgentRegistry:
    """Name to constructor, with the seed passed to whoever wants one."""

    def __init__(self) -> None:
        self._builders: dict[str, Builder] = {}

    def register(self, name: str, builder: Builder) -> None:
        if name in self._builders:
            raise ValueError(f"agent already registered: {name!r}")
        self._builders[name] = builder

    def build(self, name: str, *, seed: int = 0) -> Agent:
        if name not in self._builders:
            raise ValueError(f"unknown agent: {name!r}. Known agents: {self.names()}")
        return self._builders[name](seed)

    def names(self) -> list[str]:
        return sorted(self._builders)

    def __contains__(self, name: object) -> bool:
        return name in self._builders


DEFAULT_REGISTRY = AgentRegistry()
DEFAULT_REGISTRY.register("random", lambda seed: RandomAgent(seed=seed))
DEFAULT_REGISTRY.register("greedy", lambda _seed: GreedyAgent())
DEFAULT_REGISTRY.register("rollout_heuristic", lambda _seed: RolloutHeuristicAgent())
DEFAULT_REGISTRY.register("oracle", lambda _seed: OracleAgent())
DEFAULT_REGISTRY.register("fake", lambda _seed: FakeProbabilityAgent())


def _jev(_seed: int) -> Agent:
    """Imported on use: the TypeSafe SDK is an optional dependency."""
    from system_one_control.agents.jev import JevAgent

    return JevAgent()


DEFAULT_REGISTRY.register("jev", _jev)


def build_agent(name: str, *, seed: int = 0) -> Agent:
    """Construct a baseline by name from the default registry."""
    return DEFAULT_REGISTRY.build(name, seed=seed)
