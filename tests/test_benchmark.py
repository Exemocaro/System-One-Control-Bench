import json

from system_one_control.benchmark import (
    GameRecord,
    MoveRecord,
    estimate_paid_calls,
    run_benchmark,
    save,
    summarize,
    usage,
)
from system_one_control.conditions import CONDITIONS
from system_one_control.players import RandomPlayer, SolverPlayer, WallAwareGreedyPlayer
from system_one_control.scenario import load_scenarios
from tests.helpers import AlwaysPlayer, scenario

SCENARIOS = list(load_scenarios().values())
ALL_CONDITIONS = list(CONDITIONS.values())
MAP = [CONDITIONS["map"]]


def rows(table: str) -> dict[str, list[str]]:
    """Each row of a summary, split into cells, by player."""
    return {line.split()[0]: line.split() for line in table.splitlines()[2:]}


def test_there_is_one_record_per_scenario_condition_and_player():
    records = run_benchmark(SCENARIOS[:2], ALL_CONDITIONS, [SolverPlayer, RandomPlayer])
    assert len(records) == 2 * len(ALL_CONDITIONS) * 2
    assert {r.condition for r in records} == set(CONDITIONS)


def test_the_solver_gets_every_first_move_right_and_wins_in_the_fewest_moves():
    for record in run_benchmark(SCENARIOS, MAP, [SolverPlayer]):
        assert record.moves[0].optimal and record.won
        assert len(record.moves) == record.moves_to_goal


def test_first_move_only_plays_a_single_move():
    records = run_benchmark(SCENARIOS, MAP, [RandomPlayer], first_move_only=True)
    assert all(len(record.moves) == 1 for record in records)


def test_records_are_saved_one_json_line_each(tmp_path):
    records = run_benchmark(SCENARIOS[:2], MAP, [SolverPlayer])
    lines = save(records, tmp_path / "out.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["player"] == "solver"
    assert json.loads(lines[0])["condition"] == "map"


def test_every_move_is_saved_with_its_options_answer_and_probabilities(tmp_path):
    records = run_benchmark(SCENARIOS[:1], MAP, [SolverPlayer])
    line = json.loads(save(records, tmp_path / "out.jsonl").read_text())
    first = line["moves"][0]
    assert sorted(first["options"]) == ["east", "north", "south", "west"]
    assert first["move"] in first["best_moves"]
    assert first["probabilities"] == {first["move"]: 1.0}
    assert first["optimal"]


def test_the_summary_scores_whole_games_with_wins_optimal_moves_spl_and_errors():
    table = summarize(run_benchmark(SCENARIOS, MAP, [SolverPlayer]))
    header = table.splitlines()[0].split()
    assert header[:2] == ["player", "condition"]
    assert header[-4:] == ["won", "optimal", "SPL", "errors"]
    games = len(SCENARIOS)
    assert rows(table)["solver"][-4:] == [f"{games}/{games}", "100%", "1.00", "0"]


def test_a_lost_game_scores_zero_spl_and_a_slow_win_scores_less_than_one():
    lost = scenario("#####\n#A.G#\n#####", 2)
    slow = scenario("######\n#.A.G#\n######", 2)
    records = [
        *run_benchmark([lost], MAP, [lambda: AlwaysPlayer("west")]),
        *run_benchmark([slow], MAP, [lambda: AlwaysPlayer("west"), SolverPlayer]),
    ]
    table = rows(summarize(records))
    assert table["always"][-4:] == ["0/2", "0%", "0.00", "0"]
    assert table["solver"][-4:] == ["1/1", "100%", "1.00", "0"]


def test_games_that_end_in_an_error_are_counted():
    records = run_benchmark(SCENARIOS[:3], MAP, [lambda: AlwaysPlayer("jump")])
    assert rows(summarize(records))["always"][-1] == "3"


def test_a_first_move_summary_counts_optimal_first_moves_and_leaves_out_won_and_spl():
    records = run_benchmark(SCENARIOS, MAP, [SolverPlayer], first_move_only=True)
    table = summarize(records, first_move_only=True)
    assert table.splitlines()[0].split()[-2:] == ["optimal", "errors"]
    assert "won" not in table and "SPL" not in table
    assert rows(table)["solver"][2] == "10/10"


def test_paid_calls_are_estimated_before_anything_runs():
    one_move = estimate_paid_calls(
        SCENARIOS, ALL_CONDITIONS, ["jev", "random"], first_move_only=True
    )
    assert one_move == len(SCENARIOS) * len(ALL_CONDITIONS)
    assert estimate_paid_calls(SCENARIOS, ALL_CONDITIONS, ["random"], first_move_only=False) == 0


def test_games_played_side_by_side_give_the_same_records_in_the_same_order():
    one_at_a_time = run_benchmark(SCENARIOS, MAP, [RandomPlayer, SolverPlayer])
    side_by_side = run_benchmark(SCENARIOS, MAP, [RandomPlayer, SolverPlayer], workers=8)
    assert side_by_side == one_at_a_time


def test_rows_run_from_random_to_the_solver_with_other_players_below():
    records = run_benchmark(
        SCENARIOS[:3], MAP, [lambda: AlwaysPlayer("west"), SolverPlayer, RandomPlayer]
    )
    assert list(rows(summarize(records))) == ["random", "solver", "always"]


def test_the_best_number_in_each_column_is_bold_leaving_out_the_solver():
    records = run_benchmark(SCENARIOS, MAP, [RandomPlayer, SolverPlayer])
    plain = summarize(records)
    bold = summarize(records, bold_best=True)
    random_row, solver_row = bold.splitlines()[2:]
    assert "\x1b[1m" in random_row and "\x1b[1m" not in solver_row
    assert "\x1b[" not in plain


def test_usage_counts_the_calls_and_tokens_of_paid_players_only():
    move = MoveRecord(("east",), "east", {}, ("east",), True, input_tokens=100)
    jev = GameRecord("s", "map", "jev", 1, True, None, (move, move))
    free = GameRecord("s", "map", "random", 1, True, None, (move,))
    assert usage([jev, free]) == "jev: 2 calls, 200 input tokens"


def test_the_columns_line_up():
    records = run_benchmark(SCENARIOS, MAP, [RandomPlayer, WallAwareGreedyPlayer])
    assert len({len(line) for line in summarize(records).splitlines()}) == 1
