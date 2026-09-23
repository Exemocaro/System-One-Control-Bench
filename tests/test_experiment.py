import json

from system_one_control.experiment import estimate_paid_calls, run_experiment, save, summarize
from system_one_control.players import RandomPlayer, SolverPlayer
from system_one_control.prompt import load_prompts
from system_one_control.scenario import load_scenarios
from tests.helpers import AlwaysPlayer, scenario

SCENARIOS = list(load_scenarios().values())
PROMPTS = list(load_prompts().values())


def test_there_is_one_result_per_scenario_prompt_and_player():
    results = list(run_experiment(SCENARIOS, PROMPTS, [SolverPlayer(), RandomPlayer()]))
    assert len(results) == len(SCENARIOS) * len(PROMPTS) * 2


def test_the_solver_gets_every_first_move_right_and_wins_in_the_fewest_moves():
    for result in run_experiment(SCENARIOS, PROMPTS[:1], [SolverPlayer()]):
        assert result.moves[0].correct and result.won
        assert len(result.moves) == result.moves_to_goal


def test_first_move_only_plays_a_single_move():
    results = run_experiment(SCENARIOS, PROMPTS[:1], [RandomPlayer()], first_move_only=True)
    assert all(len(result.moves) == 1 for result in results)


def test_results_are_saved_one_json_line_each(tmp_path):
    results = list(run_experiment(SCENARIOS[:2], PROMPTS[:1], [SolverPlayer()]))
    path = save(results, tmp_path / "out.jsonl")
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["player"] == "solver"


def test_every_move_is_saved_with_its_options_answer_and_probabilities(tmp_path):
    results = list(run_experiment(SCENARIOS[:1], PROMPTS[:1], [SolverPlayer()]))
    line = json.loads(save(results, tmp_path / "out.jsonl").read_text())
    first = line["moves"][0]
    assert sorted(first["options"]) == ["east", "north", "south", "west"]
    assert first["move"] in first["best_moves"]
    assert first["probabilities"] == {first["move"]: 1.0}
    assert first["correct"]


def test_the_summary_shows_each_player_and_prompt():
    table = summarize(list(run_experiment(SCENARIOS, PROMPTS[:1], [SolverPlayer()])))
    assert "solver" in table and PROMPTS[0].name in table
    assert "10/10" in table


def test_the_summary_scores_whole_games_with_wins_optimal_moves_and_spl():
    table = summarize(list(run_experiment(SCENARIOS, PROMPTS[:1], [SolverPlayer()])))
    header, _, solver = table.splitlines()
    assert header.split()[-3:] == ["won", "optimal", "SPL"]
    assert solver.split()[-3:] == [f"{len(SCENARIOS)}/{len(SCENARIOS)}", "100%", "1.00"]


def test_a_lost_game_scores_zero_spl_and_a_slow_win_scores_less_than_one():
    lost = scenario("#####\n#A.G#\n#####", 2)
    slow = scenario("######\n#.A.G#\n######", 2)
    results = [
        *run_experiment([lost], PROMPTS[:1], [AlwaysPlayer("west")]),
        *run_experiment([slow], PROMPTS[:1], [AlwaysPlayer("west"), SolverPlayer()]),
    ]
    rows = {line.split()[0]: line.split() for line in summarize(results).splitlines()[2:]}
    assert rows["always"][-3:] == ["0/2", "0%", "0.00"]
    assert rows["solver"][-3:] == ["1/1", "100%", "1.00"]


def test_paid_calls_are_estimated_before_anything_runs():
    one_move = estimate_paid_calls(SCENARIOS, PROMPTS, ["jev", "random"], first_move_only=True)
    assert one_move == len(SCENARIOS) * len(PROMPTS)
    assert estimate_paid_calls(SCENARIOS, PROMPTS, ["random"], first_move_only=False) == 0
