"""The model observation must be compact, lossless and free of oracle hints."""

from dataclasses import replace

import pytest

from system_one_control.candidates import enumerate_candidates
from system_one_control.env import extract_snapshot, make_env
from system_one_control.observation import (
    DYNAMICS_LEGEND,
    describe_candidate,
    evaluation_state_id,
    physical_state_id,
    serialize_state,
)
from system_one_control.transition import EAST, FORWARD, LEFT, SOUTH, TOGGLE
from tests.helpers import snapshot_from_ascii
from tests.maps import CORRIDOR, KEY_ROOM


def _doorkey(seed=1):
    env = make_env("MiniGrid-DoorKey-6x6-v0", max_steps=100)
    env.reset(seed=seed)
    return extract_snapshot(env)


def test_serialization_is_deterministic():
    snapshot = _doorkey()
    assert serialize_state(snapshot) == serialize_state(snapshot)


def test_every_object_on_the_map_is_described():
    text = serialize_state(_doorkey())
    assert "yellow" in text
    assert "key" in text and "door" in text and "goal" in text
    assert "locked" in text


def test_the_agent_position_orientation_and_budget_are_stated():
    snapshot = _doorkey()
    text = serialize_state(snapshot)
    assert str(snapshot.agent_pos[0]) in text and str(snapshot.agent_pos[1]) in text
    assert "north" in text
    assert "100" in text  # remaining steps


def test_carrying_is_stated_explicitly_when_hands_are_empty():
    text = serialize_state(_doorkey())
    assert "carrying nothing" in text.lower()


@pytest.mark.parametrize("cell", [(1, 1), (2, 1), (3, 2), (4, 4)])
def test_changing_any_single_cell_changes_the_serialization(cell):
    """A lossless representation cannot collapse two different worlds."""
    snapshot = _doorkey()
    x, y = cell
    rows = list(snapshot.cells)
    row = list(rows[y])
    row[x] = (2, 5, 0) if row[x][0] != 2 else (1, 0, 0)  # swap wall and empty
    rows[y] = tuple(row)
    mutated = replace(snapshot, cells=tuple(rows))
    assert serialize_state(mutated) != serialize_state(snapshot)


def test_the_legend_explains_the_rules_the_model_must_not_have_to_guess():
    legend = DYNAMICS_LEGEND.lower()
    assert "turn" in legend and "does not move" in legend
    assert "forward" in legend
    assert "matching" in legend and "key" in legend
    assert "one action" in legend


def test_no_oracle_language_leaks_into_the_observation():
    text = (serialize_state(_doorkey()) + DYNAMICS_LEGEND).lower()
    for forbidden in ("optimal", "shortest", "distance to goal", "best action", "regret"):
        assert forbidden not in text


def test_action_only_descriptions_name_the_actions_and_nothing_else():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    candidate = next(c for c in enumerate_candidates(snapshot, horizon=1) if c.actions == (LEFT,))
    text = describe_candidate(candidate, mode="action_only")
    assert "turn left" in text
    assert "(" not in text, "action-only descriptions must not reveal endpoints"


def test_endpoint_descriptions_add_the_simulated_result():
    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=SOUTH)
    candidate = next(
        c for c in enumerate_candidates(snapshot, horizon=1) if c.actions == (FORWARD,)
    )
    action_only = describe_candidate(candidate, mode="action_only")
    endpoint = describe_candidate(candidate, mode="endpoint")

    assert endpoint != action_only
    assert "2, 2" in endpoint or "(2,2)" in endpoint


def test_endpoint_descriptions_report_success_without_scoring_it():
    snapshot = snapshot_from_ascii(CORRIDOR, agent_pos=(2, 1), agent_dir=EAST)
    candidate = next(
        c for c in enumerate_candidates(snapshot, horizon=1) if c.actions == (FORWARD,)
    )
    text = describe_candidate(candidate, mode="endpoint").lower()
    assert "goal" in text
    assert "optimal" not in text and "correct" not in text


def test_unknown_description_mode_is_rejected():
    snapshot = _doorkey()
    candidate = enumerate_candidates(snapshot, horizon=1)[0]
    with pytest.raises(ValueError):
        describe_candidate(candidate, mode="telepathy")


def test_physical_id_ignores_the_clock_but_the_evaluation_id_does_not():
    snapshot = _doorkey()
    later = replace(snapshot, step_count=17)

    assert physical_state_id(snapshot) == physical_state_id(later)
    assert evaluation_state_id(snapshot) != evaluation_state_id(later)


def test_toggling_a_door_changes_the_physical_id():
    from system_one_control.transition import step

    snapshot = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=EAST)
    key = snapshot.cell(1, 1)
    holding = replace(snapshot, carrying=key)
    opened = step(holding, TOGGLE).snapshot
    assert physical_state_id(opened) != physical_state_id(holding)
