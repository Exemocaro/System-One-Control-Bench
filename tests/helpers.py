"""Building hand-written worlds from the ASCII maps in `tests/maps.py`."""

from system_one_control.domain import Snapshot
from system_one_control.transition import (
    CLOSED,
    DOOR,
    EMPTY,
    GOAL,
    KEY,
    LAVA,
    LOCKED,
    OPEN,
    WALL,
)

# minigrid.core.constants.COLOR_TO_IDX
GREEN = 1
YELLOW = 4
GREY = 5

CHARS = {
    "#": (WALL, GREY, 0),
    ".": (EMPTY, 0, 0),
    "G": (GOAL, GREEN, 0),
    "K": (KEY, YELLOW, 0),
    "D": (DOOR, YELLOW, LOCKED),
    "d": (DOOR, YELLOW, CLOSED),
    "o": (DOOR, YELLOW, OPEN),
    "L": (LAVA, 0, 0),
}


def snapshot_from_ascii(rows, agent_pos, agent_dir, *, carrying=None, max_steps=100):
    """Build a Snapshot from an ASCII map. Rows are y, columns are x."""
    return Snapshot(
        env_id="hand-built",
        width=len(rows[0]),
        height=len(rows),
        cells=tuple(tuple(CHARS[char] for char in row) for row in rows),
        agent_pos=agent_pos,
        agent_dir=agent_dir,
        carrying=carrying,
        mission="hand-built",
        step_count=0,
        max_steps=max_steps,
    )


def render(snapshot):
    """Draw a snapshot as text, with the agent as an arrow. For failure messages."""
    arrows = {0: ">", 1: "v", 2: "<", 3: "^"}
    symbols = {value: key for key, value in CHARS.items()}
    lines = []
    for y, row in enumerate(snapshot.cells):
        line = ""
        for x, cell in enumerate(row):
            if (x, y) == tuple(snapshot.agent_pos):
                line += arrows[snapshot.agent_dir]
            else:
                line += symbols.get(cell, "?")
        lines.append(line)
    return "\n".join(lines)
