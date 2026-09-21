"""Turning a Snapshot into the text a decision model receives.

The state and the candidate descriptions are rendered by separate objects on
purpose: holding the candidates fixed while only their description changes is
what makes the action-only and endpoint conditions comparable.
"""

from __future__ import annotations

import hashlib

from system_one_control.domain import Candidate, Snapshot
from system_one_control.transition import (
    BALL,
    BOX,
    CLOSED,
    DOOR,
    EMPTY,
    FLOOR,
    GOAL,
    KEY,
    LAVA,
    LOCKED,
    OPEN,
    WALL,
)

SERIALIZER_VERSION = "compact_grid_v1"
LEGEND_VERSION = "minigrid_static_v2"
QUESTION_VERSION = "action_choice_v1"

QUESTION_TEXT = "Choose the option that reaches the goal in the fewest remaining actions."

DESCRIPTION_MODES = ("action_only", "endpoint")

DIRECTION_NAMES = ("east", "south", "west", "north")

ACTION_NAMES = {
    0: "turn left",
    1: "turn right",
    2: "move forward",
    3: "pick up",
    4: "drop",
    5: "toggle",
    6: "do nothing",
}

# Order and spelling follow minigrid.core.constants.COLOR_TO_IDX, "grey" included.
COLOR_NAMES = ("red", "green", "blue", "purple", "yellow", "grey")

SYMBOLS = {
    EMPTY: (".", "empty floor"),
    FLOOR: (".", "empty floor"),
    WALL: ("W", "wall"),
    DOOR: ("D", "door"),
    KEY: ("K", "key"),
    BALL: ("B", "ball"),
    BOX: ("X", "box"),
    GOAL: ("G", "goal"),
    LAVA: ("L", "lava"),
}

DOOR_STATES = {OPEN: "open", CLOSED: "closed but unlocked", LOCKED: "locked"}

# Versioned: changing a word here changes what every model was asked.
DYNAMICS_LEGEND = (
    "Rules. Coordinates are (x, y) with (0, 0) at the upper left; x increases to "
    "the right and y increases downward. The four orientations are east, south, "
    "west and north. A turn changes orientation by 90 degrees, costs one action "
    "and does not move the agent. Moving forward costs one action and moves the "
    "agent one cell in the direction it faces, unless that cell is a wall or a "
    "closed door, in which case the agent stays where it is and the action is "
    "wasted. Picking up takes the object in the cell directly ahead, and only "
    "one object can be carried at a time. Dropping places the carried object in "
    "the cell directly ahead, which must be empty. Toggling a door in the cell "
    "directly ahead opens or closes it; a locked door opens only while carrying "
    "a key of the matching color, and toggling it without that key wastes the "
    "action. Every cell not drawn on the map is a wall, and the whole boundary "
    "of the grid is wall. Reaching the goal ends the episode."
)


def color_name(index: int) -> str:
    return COLOR_NAMES[index] if 0 <= index < len(COLOR_NAMES) else f"color{index}"


def _name_carried(cell: tuple[int, int, int]) -> str:
    return f"a {color_name(cell[1])} {SYMBOLS[cell[0]][1]}"


class StateSerializer:
    """Renders one snapshot as compact, lossless text.

    Full per-object JSON is deliberately not the default: it costs hundreds of
    tokens on a 6x6 map and crowds out real content in a small input budget.
    """

    version = SERIALIZER_VERSION

    def render(self, snapshot: Snapshot) -> str:
        rows, symbols, objects = self._render_grid(snapshot)
        parts = [
            f"Task: {snapshot.mission}",
            f"Grid: {snapshot.width} wide, {snapshot.height} high.",
            "Map, one character per cell, first row is y=0:",
            *rows,
            f"Symbols: {symbols}.",
        ]
        if objects:
            parts.append("Objects: " + "; ".join(objects) + ".")
        parts.append(self._render_agent(snapshot))
        remaining = snapshot.max_steps - snapshot.step_count
        parts.append(f"Budget: {snapshot.step_count} actions used, {remaining} remaining.")
        return "\n".join(parts)

    def _render_grid(self, snapshot: Snapshot) -> tuple[list[str], str, list[str]]:
        rows: list[str] = []
        present: dict[str, str] = {}
        objects: list[str] = []
        for y, row in enumerate(snapshot.cells):
            line = []
            for x, cell in enumerate(row):
                symbol, name = SYMBOLS[cell[0]]
                line.append(symbol)
                present[symbol] = name
                described = self._describe_object(x, y, cell)
                if described is not None:
                    objects.append(described)
            rows.append("".join(line))
        symbols = ", ".join(f"{s}={name}" for s, name in sorted(present.items()))
        return rows, symbols, objects

    def _render_agent(self, snapshot: Snapshot) -> str:
        carrying = (
            "carrying nothing"
            if snapshot.carrying is None
            else f"carrying {_name_carried(snapshot.carrying)}"
        )
        x, y = snapshot.agent_pos
        return f"Agent: at ({x}, {y}), facing {DIRECTION_NAMES[snapshot.agent_dir]}, {carrying}."

    def _describe_object(self, x: int, y: int, cell: tuple[int, int, int]) -> str | None:
        kind, color, state = cell
        if kind == GOAL:
            return f"goal at ({x}, {y})"
        if kind == KEY:
            return f"{color_name(color)} key at ({x}, {y})"
        if kind == DOOR:
            return f"{color_name(color)} door at ({x}, {y}), {DOOR_STATES[state]}"
        if kind == LAVA:
            return f"lava at ({x}, {y})"
        if kind in (BALL, BOX):
            name = "ball" if kind == BALL else "box"
            return f"{color_name(color)} {name} at ({x}, {y})"
        return None


class CandidateDescriber:
    """Renders one offered action sequence, in one of the description modes.

    ``action_only`` names the actions. ``endpoint`` adds where the sequence ends
    up — information ordinary code computed, so any gain it buys is evidence
    about supplied simulation rather than the model's own lookahead.
    """

    def describe(self, candidate: Candidate, mode: str) -> str:
        if mode not in DESCRIPTION_MODES:
            raise ValueError(f"unknown description mode: {mode!r}")
        actions = ", then ".join(ACTION_NAMES[action] for action in candidate.actions)
        if mode == "action_only":
            return actions
        return f"{actions}; {self._endpoint(candidate)}"

    def _endpoint(self, candidate: Candidate) -> str:
        end = candidate.outcome
        x, y = end.agent_pos
        text = f"ends at ({x}, {y}) facing {DIRECTION_NAMES[end.agent_dir]}"
        if end.carrying is not None:
            text += f", carrying {_name_carried(end.carrying)}"
        if candidate.success:
            text += ", reaching the goal and ending the episode"
        elif candidate.terminated:
            text += ", ending the episode without reaching the goal"
        return text


DEFAULT_SERIALIZER = StateSerializer()
DEFAULT_DESCRIBER = CandidateDescriber()


def serialize_state(snapshot: Snapshot) -> str:
    """Render the compact observation with the default serializer."""
    return DEFAULT_SERIALIZER.render(snapshot)


def describe_candidate(candidate: Candidate, mode: str) -> str:
    """Describe one candidate with the default describer."""
    return DEFAULT_DESCRIBER.describe(candidate, mode)


def _digest(*parts: object) -> str:
    payload = "|".join(repr(part) for part in parts).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def physical_state_id(snapshot: Snapshot) -> str:
    """Identity of the world alone, independent of the clock."""
    return _digest(snapshot.cells, snapshot.agent_pos, snapshot.agent_dir, snapshot.carrying)


def evaluation_state_id(snapshot: Snapshot) -> str:
    """Identity of the whole decision problem, including budget and mission."""
    return _digest(
        physical_state_id(snapshot),
        snapshot.mission,
        snapshot.step_count,
        snapshot.max_steps,
    )
