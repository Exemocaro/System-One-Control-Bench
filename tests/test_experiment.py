import json

from system_one_control.experiment import estimate_paid_calls, run_experiment, save, summarize
from system_one_control.players import RandomPlayer, SolverPlayer
from system_one_control.prompt import load_prompts
from system_one_control.scenario import load_scenarios

SCENARIOS = list(load_scenarios().values())
PROMPTS = list(load_prompts().values())


def test_there_is_one_result_per_scenario_prompt_and_player():
    results = list(run_experiment(SCENARIOS, PROMPTS, [SolverPlayer(), RandomPlayer()]))
    assert len(results) == len(SCENARIOS) * len(PROMPTS) * 2


def test_the_solver_gets_every_first_move_right_and_wins_in_the_fewest_moves():
    for result in run_experiment(SCENARIOS, PROMPTS[:1], [SolverPlayer()]):
        assert result.first_move_correct and result.won
        assert result.moves_used == result.moves_to_goal


def test_first_move_only_plays_a_single_move():
    results = run_experiment(SCENARIOS, PROMPTS[:1], [RandomPlayer()], first_move_only=True)
    assert all(result.moves_used == 1 for result in results)


def test_results_are_saved_one_json_line_each(tmp_path):
    results = list(run_experiment(SCENARIOS[:2], PROMPTS[:1], [SolverPlayer()]))
    path = save(results, tmp_path / "out.jsonl")
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["player"] == "solver"


def test_the_summary_shows_each_player_and_prompt():
    table = summarize(list(run_experiment(SCENARIOS, PROMPTS[:1], [SolverPlayer()])))
    assert "solver" in table and PROMPTS[0].name in table
    assert "10/10" in table


def test_paid_calls_are_estimated_before_anything_runs():
    one_move = estimate_paid_calls(SCENARIOS, PROMPTS, ["jev", "random"], first_move_only=True)
    assert one_move == len(SCENARIOS) * len(PROMPTS)
    assert estimate_paid_calls(SCENARIOS, PROMPTS, ["random"], first_move_only=False) == 0
