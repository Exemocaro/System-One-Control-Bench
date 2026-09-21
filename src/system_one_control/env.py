"""MiniGrid construction, snapshot extraction and restoration."""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import gymnasium as gym
import minigrid  # noqa: F401  (registers the MiniGrid environment ids)
from minigrid.core.grid import Grid
from minigrid.core.world_object import WorldObj
from minigrid.minigrid_env import MiniGridEnv

from system_one_control.domain import EncodedCell, Snapshot


def make_env(env_id: str, max_steps: int) -> MiniGridEnv:
    """Build a bare MiniGrid environment with an explicit step budget.

    Returns the unwrapped environment: ``TimeLimit`` and ``OrderEnforcing`` keep
    episode state a snapshot cannot see, so restoring underneath them would
    diverge from the world the oracle reasoned about. MiniGrid enforces
    ``max_steps`` itself.
    """
    env = gym.make(env_id, max_steps=max_steps)
    inner = env.unwrapped
    assert isinstance(inner, MiniGridEnv)
    return inner


def _encode(obj: WorldObj | None) -> EncodedCell:
    if obj is None:
        return (1, 0, 0)  # OBJECT_TO_IDX["empty"]
    a, b, c = obj.encode()
    return (int(a), int(b), int(c))


def extract_snapshot(env: MiniGridEnv) -> Snapshot:
    """Capture everything needed to restore `env` to its current state."""
    grid = env.grid
    cells = tuple(
        tuple(_encode(grid.get(x, y)) for x in range(grid.width)) for y in range(grid.height)
    )
    x, y = env.agent_pos
    return Snapshot(
        env_id=env.spec.id if env.spec is not None else "",
        width=grid.width,
        height=grid.height,
        cells=cells,
        agent_pos=(int(x), int(y)),
        agent_dir=int(env.agent_dir),
        carrying=None if env.carrying is None else _encode(env.carrying),
        mission=str(env.mission),
        step_count=int(env.step_count),
        max_steps=int(env.max_steps),
    )


def restore_snapshot(env: MiniGridEnv, snapshot: Snapshot) -> None:
    """Overwrite `env`'s world state with `snapshot`."""
    grid = Grid(snapshot.width, snapshot.height)
    for y in range(snapshot.height):
        for x in range(snapshot.width):
            grid.set(x, y, WorldObj.decode(*snapshot.cells[y][x]))
    env.grid = grid
    env.agent_pos = snapshot.agent_pos
    env.agent_dir = snapshot.agent_dir
    # MiniGrid leaves `carrying` unannotated, so mypy infers None from its initialiser.
    carried = None if snapshot.carrying is None else WorldObj.decode(*snapshot.carrying)
    env.carrying = carried  # type: ignore[assignment]
    env.mission = snapshot.mission
    env.step_count = snapshot.step_count
    env.max_steps = snapshot.max_steps
