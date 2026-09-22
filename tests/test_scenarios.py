import pytest

from system_one_control.scenario import Scenario, load_scenarios
from system_one_control.solver import Solver

SCENARIOS = load_scenarios()


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_solver_agrees_with_what_each_scenario_file_claims(name):
    scenario = SCENARIOS[name]
    solver = Solver(scenario.rules)
    assert solver.distance(scenario.board) == scenario.moves_to_goal
    assert set(solver.best_moves(scenario.board)) == set(scenario.best_first_moves)


def test_there_are_scenarios_one_two_and_three_moves_from_the_goal():
    assert {s.moves_to_goal for s in SCENARIOS.values()} == {1, 2, 3}


def test_scenarios_are_named_after_their_file_and_sorted_by_difficulty():
    assert "key-first" in SCENARIOS
    distances = [s.moves_to_goal for s in SCENARIOS.values()]
    assert distances == sorted(distances)


def test_a_scenario_file_can_choose_its_rules(tmp_path):
    path = tmp_path / "tiny.yaml"
    lines = ["rules: compass", "moves_to_goal: 1", "best_first_moves: [east]", "map: |"]
    path.write_text("\n".join([*lines, "  ####", "  #AG#", "  ####"]))
    scenario = Scenario.load(path)
    assert scenario.name == "tiny"
    assert scenario.rules.name == "compass"
    assert scenario.max_moves == 20
