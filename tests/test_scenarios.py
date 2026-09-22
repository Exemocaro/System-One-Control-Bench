from dataclasses import replace

import pytest

from system_one_control.scenario import SCENARIO_DIR, Scenario, load_scenarios
from system_one_control.solver import Solver

SCENARIOS = load_scenarios()


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_solver_agrees_with_what_each_scenario_file_claims(name):
    scenario = SCENARIOS[name]
    solver = Solver(scenario.rules)
    assert solver.distance(scenario.board) == scenario.moves_to_goal


def test_every_level_from_one_to_ten_has_a_scenario():
    assert {s.moves_to_goal for s in SCENARIOS.values()} == set(range(1, 11))


@pytest.mark.parametrize("path", sorted(SCENARIO_DIR.rglob("*.yaml")), ids=lambda p: p.stem)
def test_each_scenario_sits_in_the_folder_for_its_level(path):
    assert path.parent.name == f"level-{Scenario.load(path).moves_to_goal:02d}"


@pytest.mark.parametrize("name", [n for n, s in SCENARIOS.items() if s.board.find("K")])
def test_where_there_is_a_key_the_goal_cannot_be_reached_without_it(name):
    scenario = SCENARIOS[name]
    keyless = replace(scenario.board, rows=tuple(r.replace("K", ".") for r in scenario.board.rows))
    assert Solver(scenario.rules).distance(keyless) is None


def test_there_are_at_least_five_scenarios_with_a_key_and_a_maze():
    with_key = [s for s in SCENARIOS.values() if s.board.find("K")]
    assert len(with_key) >= 5
    assert "maze" in SCENARIOS


def test_scenarios_are_named_after_their_file_and_sorted_by_difficulty():
    assert "key-first" in SCENARIOS
    distances = [s.moves_to_goal for s in SCENARIOS.values()]
    assert distances == sorted(distances)


def test_a_scenario_file_can_choose_its_rules(tmp_path):
    path = tmp_path / "tiny.yaml"
    path.write_text("rules: compass\nmoves_to_goal: 1\nmap: |\n  ####\n  #AG#\n  ####\n")
    scenario = Scenario.load(path)
    assert scenario.name == "tiny"
    assert scenario.rules.name == "compass"


@pytest.mark.parametrize("name", SCENARIOS)
def test_a_game_allows_twice_the_moves_the_solver_needs(name):
    assert SCENARIOS[name].max_moves == 2 * SCENARIOS[name].moves_to_goal


@pytest.mark.parametrize("path", sorted(SCENARIO_DIR.rglob("*.yaml")), ids=lambda p: p.stem)
def test_scenario_files_do_not_repeat_what_the_solver_computes(path):
    assert "best_first_moves" not in path.read_text()
