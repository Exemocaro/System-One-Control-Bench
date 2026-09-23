import pytest

from system_one_control.conditions import CONDITIONS
from system_one_control.examples import EXAMPLE_DIR, EXAMPLE_SCENARIO, example, write_examples
from system_one_control.scenario import load_scenarios

SCENARIO = load_scenarios()[EXAMPLE_SCENARIO]


@pytest.mark.parametrize("name", CONDITIONS)
def test_the_saved_example_is_what_the_condition_shows_today(name):
    """If this fails, the wording changed: check the change, then run `socb examples`."""
    saved = (EXAMPLE_DIR / f"{name}.txt").read_text(encoding="utf-8")
    assert saved == example(CONDITIONS[name], SCENARIO)


def test_an_example_is_taken_after_a_move_and_a_blocked_move():
    text = example(CONDITIONS["everything"], SCENARIO)
    assert "1. east: you move to (7, 1)\n2. north: blocked, you stay at (7, 1)" in text
    assert "Question: " in text and "option_4: " in text


def test_examples_are_written_one_file_per_condition(tmp_path):
    written = write_examples(tmp_path)
    assert sorted(path.stem for path in written) == sorted(CONDITIONS)
