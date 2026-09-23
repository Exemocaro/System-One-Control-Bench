from dataclasses import replace

import pytest

from system_one_control.scenario import SCENARIO_DIR, Scenario, load_scenarios
from system_one_control.solver import Solver

SCENARIOS = load_scenarios()


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_solver_agrees_with_what_each_scenario_file_claims(name):
    scenario = SCENARIOS[name]
    solver = Solver(scenario.rules)
    assert solver.moves_to_goal(scenario.board) == scenario.moves_to_goal


def test_every_level_from_one_to_ten_has_a_scenario():
    assert {s.moves_to_goal for s in SCENARIOS.values()} == set(range(1, 11))


@pytest.mark.parametrize("path", sorted(SCENARIO_DIR.rglob("*.yaml")), ids=lambda p: p.stem)
def test_each_scenario_sits_in_the_folder_for_its_level(path):
    assert path.parent.name == f"level-{Scenario.load(path).moves_to_goal:02d}"


@pytest.mark.parametrize("name", [n for n, s in SCENARIOS.items() if s.board.find("K")])
def test_where_there_is_a_key_the_goal_cannot_be_reached_without_it(name):
    scenario = SCENARIOS[name]
    keyless = replace(scenario.board, rows=tuple(r.replace("K", ".") for r in scenario.board.rows))
    assert Solver(scenario.rules).moves_to_goal(keyless) is None


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
def test_a_game_allows_three_times_the_moves_the_solver_needs(name):
    assert SCENARIOS[name].max_moves == 3 * SCENARIOS[name].moves_to_goal


def test_two_scenarios_may_not_share_a_name(tmp_path):
    tiny = "moves_to_goal: 1\nmap: |\n  ####\n  #AG#\n  ####\n"
    for level in ("level-01", "level-02"):
        (tmp_path / level).mkdir()
        (tmp_path / level / "tiny.yaml").write_text(tiny)
    with pytest.raises(ValueError, match="tiny"):
        load_scenarios(tmp_path)
