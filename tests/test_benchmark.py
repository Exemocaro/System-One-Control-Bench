import json

import pytest

from system_one_control.benchmark import (
    GameRecord,
    MoveRecord,
    estimate_paid_calls,
    load,
    run_benchmark,
    save,
    summarize,
    usage,
)
from system_one_control.conditions import CONDITIONS
from system_one_control.players import (
    Player,
    RandomPlayer,
    ScriptedPlayer,
    SolverPlayer,
    WallAwareGreedyPlayer,
)
from system_one_control.scenario import load_scenarios
from tests.helpers import AlwaysPlayer, scenario

SCENARIOS = list(load_scenarios().values())
ALL_CONDITIONS = list(CONDITIONS.values())
MAP = [CONDITIONS["map"]]


def rows(table: str) -> dict[str, list[str]]:
    """Each row of a summary, split into cells, by player."""
    return {line.split()[0]: line.split() for line in table.splitlines()[2:]}


def test_there_is_one_record_per_scenario_condition_and_player():
    records = run_benchmark(
        SCENARIOS[:2], ALL_CONDITIONS, {"solver": SolverPlayer, "random": RandomPlayer}
    )
    assert len(records) == 2 * len(ALL_CONDITIONS) * 2
    assert {r.condition for r in records} == set(CONDITIONS)


def test_the_solver_gets_every_first_move_right_and_wins_in_the_fewest_moves():
    for record in run_benchmark(SCENARIOS, MAP, {"solver": SolverPlayer}):
        assert record.moves[0].optimal and record.won
        assert len(record.moves) == record.moves_to_goal


def test_records_are_saved_one_json_line_each(tmp_path):
    records = run_benchmark(SCENARIOS[:2], MAP, {"solver": SolverPlayer})
    lines = save(records, tmp_path / "out.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["player"] == "solver"
    assert json.loads(lines[0])["condition"] == "map"


def test_every_move_is_saved_with_its_options_answer_and_probabilities(tmp_path):
    records = run_benchmark(SCENARIOS[:1], MAP, {"solver": SolverPlayer})
    line = json.loads(save(records, tmp_path / "out.jsonl").read_text())
    first = line["moves"][0]
    assert sorted(first["options"]) == ["east", "north", "south", "west"]
    assert first["move"] in first["best_moves"]
    assert first["probabilities"] == {first["move"]: 1.0}
    assert first["optimal"]


def test_the_summary_scores_games_won_at_each_level_then_won_progress_spl_and_errors():
    table = summarize(run_benchmark(SCENARIOS, MAP, {"solver": SolverPlayer}))
    header = table.splitlines()[0].split()
    assert header[:4] == ["player", "condition", "1", "away"]
    assert header[-4:] == ["won", "progress", "SPL", "errors"]
    games = len(SCENARIOS)
    assert rows(table)["solver"][-4:] == [f"{games}/{games}", "1.00", "1.00", "0"]


def test_progress_is_how_much_of_the_way_a_game_covered_at_its_closest():
    corridor = scenario("#######\n#A...G#\n#######", 4)
    [east_then_back] = run_benchmark(
        [corridor], MAP, {"scripted": lambda: ScriptedPlayer(["east", "east", "west"])}
    )
    assert east_then_back.closest == 2
    assert east_then_back.progress == 0.5
    [stuck] = run_benchmark([corridor], MAP, {"always": lambda: AlwaysPlayer("west")})
    assert stuck.closest == 4 and stuck.progress == 0.0


def test_a_lost_game_scores_zero_spl_and_a_slow_win_scores_less_than_one():
    lost = scenario("#####\n#A.G#\n#####", 2)
    slow = scenario("######\n#.A.G#\n######", 2)
    records = [
        *run_benchmark([lost], MAP, {"always": lambda: AlwaysPlayer("west")}),
        *run_benchmark(
            [slow], MAP, {"always": lambda: AlwaysPlayer("west"), "solver": SolverPlayer}
        ),
    ]
    table = rows(summarize(records))
    assert table["always"][-4:] == ["0/2", "0.00", "0.00", "0"]
    assert table["solver"][-4:] == ["1/1", "1.00", "1.00", "0"]


def test_games_that_end_in_an_error_are_counted():
    records = run_benchmark(SCENARIOS[:3], MAP, {"always": lambda: AlwaysPlayer("jump")})
    assert rows(summarize(records))["always"][-1] == "3"


def test_paid_calls_are_estimated_before_anything_runs():
    calls = estimate_paid_calls(SCENARIOS, ALL_CONDITIONS, ["jev", "random"])
    assert calls == sum(s.max_moves for s in SCENARIOS) * len(ALL_CONDITIONS)
    assert estimate_paid_calls(SCENARIOS, ALL_CONDITIONS, ["random"]) == 0


def test_games_played_side_by_side_give_the_same_records_in_the_same_order():
    one_at_a_time = run_benchmark(SCENARIOS, MAP, {"random": RandomPlayer, "solver": SolverPlayer})
    side_by_side = run_benchmark(
        SCENARIOS, MAP, {"random": RandomPlayer, "solver": SolverPlayer}, workers=8
    )
    assert side_by_side == one_at_a_time


def test_rows_run_from_random_to_the_solver_with_other_players_below():
    records = run_benchmark(
        SCENARIOS[:3],
        MAP,
        {"always": lambda: AlwaysPlayer("west"), "solver": SolverPlayer, "random": RandomPlayer},
    )
    assert list(rows(summarize(records))) == ["random", "solver", "always"]


def test_the_best_number_in_each_column_is_bold_leaving_out_the_solver():
    records = run_benchmark(SCENARIOS, MAP, {"random": RandomPlayer, "solver": SolverPlayer})
    plain = summarize(records)
    bold = summarize(records, bold_best=True)
    random_row, solver_row = bold.splitlines()[2:]
    assert "\x1b[1m" in random_row and "\x1b[1m" not in solver_row
    assert "\x1b[" not in plain


def test_usage_counts_the_calls_and_tokens_of_paid_players_only():
    move = MoveRecord(("east",), "east", {}, ("east",), True, input_tokens=100)
    jev = GameRecord("s", "map", "jev", 1, True, 0, None, (move, move))
    free = GameRecord("s", "map", "random", 1, True, 0, None, (move,))
    assert usage([jev, free]) == "jev: 2 calls, 200 input tokens"


def test_each_game_is_handed_over_as_soon_as_it_finishes():
    handed: list[GameRecord] = []
    records = run_benchmark(
        SCENARIOS[:5], MAP, {"solver": SolverPlayer}, workers=4, on_record=handed.append
    )
    assert sorted(handed, key=records.index) == records


def test_games_already_done_are_skipped():
    first, second = SCENARIOS[:2]
    records = run_benchmark(
        [first, second], MAP, {"solver": SolverPlayer}, done={(first.name, "map", "solver")}
    )
    assert [record.scenario for record in records] == [second.name]


def test_a_failure_outside_a_move_stops_the_run_and_keeps_the_games_already_handed_over():
    handed: list[GameRecord] = []
    built = 0

    def build() -> Player:
        nonlocal built
        built += 1
        if built == 3:
            raise RuntimeError("could not start a player")
        return SolverPlayer()

    with pytest.raises(RuntimeError, match="could not start"):
        run_benchmark(SCENARIOS, MAP, {"solver": build}, on_record=handed.append)
    assert len(handed) == 2
    assert built == 3  # the games after it were never started


def test_every_player_is_closed_after_its_game():
    closed = []

    class ClosingPlayer(SolverPlayer):
        def close(self) -> None:
            closed.append(self)

    run_benchmark(SCENARIOS[:3], MAP, {"solver": ClosingPlayer}, workers=2)
    assert len(closed) == 3


def test_saved_games_load_back_unchanged_and_a_cut_off_last_line_is_skipped(tmp_path):
    records = run_benchmark(SCENARIOS[:3], MAP, {"solver": SolverPlayer})
    path = save(records, tmp_path / "out.jsonl")
    assert load(path) == records

    with path.open("a", encoding="utf-8") as file:
        file.write('{"scenario": "half a li')
    assert load(path) == records


def test_a_corrupt_line_before_the_last_is_an_error(tmp_path):
    path = save(run_benchmark(SCENARIOS[:2], MAP, {"solver": SolverPlayer}), tmp_path / "out.jsonl")
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(f"{lines[0][:20]}\n{lines[1]}\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load(path)


def test_paid_calls_leave_out_the_games_already_done():
    first = SCENARIOS[0]
    done = {(first.name, "map", "jev")}
    all_games = estimate_paid_calls(SCENARIOS, MAP, ["jev"])
    rest = estimate_paid_calls(SCENARIOS, MAP, ["jev"], done=done)
    assert all_games - rest == first.max_moves


def test_the_columns_line_up():
    records = run_benchmark(
        SCENARIOS, MAP, {"random": RandomPlayer, "greedy-walls": WallAwareGreedyPlayer}
    )
    assert len({len(line) for line in summarize(records).splitlines()}) == 1
