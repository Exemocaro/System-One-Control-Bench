"""A pure reimplementation of ``MiniGridEnv.step``, which the oracle searches over."""

from __future__ import annotations

from dataclasses import replace

from system_one_control.domain import EncodedCell, Snapshot, Transition

# minigrid.core.constants.OBJECT_TO_IDX
EMPTY = 1
WALL = 2
FLOOR = 3
DOOR = 4
KEY = 5
BALL = 6
BOX = 7
GOAL = 8
LAVA = 9

# minigrid.core.constants.STATE_TO_IDX
OPEN = 0
CLOSED = 1
LOCKED = 2

EMPTY_CELL: EncodedCell = (EMPTY, 0, 0)
WALL_CELL: EncodedCell = (WALL, 0, 0)

# minigrid.core.constants.DIR_TO_VEC
EAST, SOUTH, WEST, NORTH = range(4)
DIR_TO_VEC = ((1, 0), (0, 1), (-1, 0), (0, -1))

LEFT, RIGHT, FORWARD, PICKUP, DROP, TOGGLE, DONE = range(7)

_PICKABLE = frozenset({KEY, BALL, BOX})
_ALWAYS_OVERLAPPABLE = frozenset({FLOOR, GOAL, LAVA})


def _can_overlap(cell: EncodedCell) -> bool:
    kind, _, state = cell
    if kind == EMPTY:
        return True
    if kind == DOOR:
        return state == OPEN
    return kind in _ALWAYS_OVERLAPPABLE


def _with_cell(
    snapshot: Snapshot, x: int, y: int, cell: EncodedCell
) -> tuple[tuple[EncodedCell, ...], ...]:
    row = snapshot.cells[y]
    new_row = row[:x] + (cell,) + row[x + 1 :]
    return snapshot.cells[:y] + (new_row,) + snapshot.cells[y + 1 :]


def is_goal_reached(snapshot: Snapshot) -> bool:
    """True when the agent stands on a goal cell."""
    x, y = snapshot.agent_pos
    return snapshot.cells[y][x][0] == GOAL


def physical(snapshot: Snapshot) -> Snapshot:
    """Strip the clock so equivalent worlds compare and hash as equal."""
    return replace(snapshot, step_count=0)


def step(snapshot: Snapshot, action: int) -> Transition:
    """Apply one primitive action. Pure: `snapshot` is never mutated.

    Mirrors MiniGrid 3.1.0 exactly, down to ``step_count`` incrementing before
    the reward is computed and a locked door consuming a toggle with no effect.
    """
    if not 0 <= action <= DONE:
        raise ValueError(f"Unknown action: {action}")

    step_count = snapshot.step_count + 1
    reward = 0.0
    terminated = False

    agent_pos = snapshot.agent_pos
    agent_dir = snapshot.agent_dir
    carrying = snapshot.carrying
    cells = snapshot.cells

    dx, dy = DIR_TO_VEC[agent_dir]
    fx, fy = agent_pos[0] + dx, agent_pos[1] + dy
    # Off-grid counts as wall; a negative index would otherwise wrap silently.
    in_bounds = 0 <= fx < snapshot.width and 0 <= fy < snapshot.height
    fwd = cells[fy][fx] if in_bounds else WALL_CELL
    fwd_kind = fwd[0]

    if action == LEFT:
        agent_dir = (agent_dir - 1) % 4

    elif action == RIGHT:
        agent_dir = (agent_dir + 1) % 4

    elif action == FORWARD:
        if _can_overlap(fwd):
            agent_pos = (fx, fy)
        if fwd_kind == GOAL:
            terminated = True
            reward = 1 - 0.9 * (step_count / snapshot.max_steps)
        elif fwd_kind == LAVA:
            terminated = True

    elif action == PICKUP:
        if fwd_kind in _PICKABLE and carrying is None:
            carrying = fwd
            cells = _with_cell(snapshot, fx, fy, EMPTY_CELL)

    elif action == DROP:
        if fwd_kind == EMPTY and carrying is not None:
            cells = _with_cell(snapshot, fx, fy, carrying)
            carrying = None

    elif action == TOGGLE:
        if fwd_kind == DOOR:
            _, door_color, door_state = fwd
            if door_state == LOCKED:
                if carrying is not None and carrying[0] == KEY and carrying[1] == door_color:
                    cells = _with_cell(snapshot, fx, fy, (DOOR, door_color, OPEN))
            else:
                new_state = CLOSED if door_state == OPEN else OPEN
                cells = _with_cell(snapshot, fx, fy, (DOOR, door_color, new_state))
        elif fwd_kind == BOX:
            raise NotImplementedError(
                "Box.toggle replaces the box with its contents, which Snapshot does not record."
            )

    # DONE is a no-op, but still consumes a step.

    return Transition(
        snapshot=replace(
            snapshot,
            cells=cells,
            agent_pos=agent_pos,
            agent_dir=agent_dir,
            carrying=carrying,
            step_count=step_count,
        ),
        reward=reward,
        terminated=terminated,
        truncated=step_count >= snapshot.max_steps,
    )
