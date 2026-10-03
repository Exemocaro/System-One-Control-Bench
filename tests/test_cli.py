import json
from datetime import datetime

import pytest
from typer.testing import CliRunner

from system_one_control.cli import _run_name, app
from system_one_control.puzzles import LEVELS

runner = CliRunner()
THREE = "gen-01-01,gen-01-02,gen-01-03"
SOLVER = ["--players", "solver", "--puzzles", THREE]
WHEN = datetime(2026, 9, 23, 18, 45)


def run(tmp_path, *args):
    out = tmp_path / "results.jsonl"
    return runner.invoke(app, ["benchmark", *args, "--out", str(out)]), out


def records(out):
    return [json.loads(line) for line in out.read_text().splitlines()]


def test_a_benchmark_of_free_players_prints_a_summary_and_saves_the_games_and_the_table(tmp_path):
    result, out = run(tmp_path, "--players", "solver,random")
    assert result.exit_code == 0, result.output
    assert "solver" in result.output
    assert "SPL" in out.with_suffix(".txt").read_text()
    assert {record["condition"] for record in records(out)} == {"map"}


@pytest.mark.parametrize(
    ("args", "message"),
    [
        pytest.param(["--players", "jev"], "--allow-paid", id="a paid player needs permission"),
        pytest.param(
            ["--players", "greedy", "--rules", "two-moves"], "compass", id="greedy on other rules"
        ),
        pytest.param(["--puzzles", "nowhere"], "nowhere", id="unknown puzzles"),
        pytest.param(["--levels", "one"], "levels must look like", id="levels that cannot be read"),
    ],
)
def test_a_benchmark_that_cannot_run_is_refused_before_anything_is_saved(tmp_path, args, message):
    result, out = run(tmp_path, *args)
    assert result.exit_code != 0
    assert message in result.output
    assert not out.exists()


def test_a_benchmark_never_overwrites_an_earlier_one(tmp_path):
    out = tmp_path / "results.jsonl"
    out.write_text("earlier results\n")
    result, _ = run(tmp_path, "--players", "solver")
    assert result.exit_code != 0
    assert "already exists" in result.output and "--resume" in result.output
    assert out.read_text() == "earlier results\n"


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        pytest.param(["--players", "random"], "would not play", id="other players"),
        pytest.param(["--rules", "two-moves"], "--rules", id="other rules"),
    ],
)
def test_resume_refuses_a_file_from_a_different_run(tmp_path, changed, message):
    _, out = run(tmp_path, *SOLVER)
    before = out.read_text()
    result, _ = run(tmp_path, *SOLVER, *changed, "--resume")
    assert result.exit_code != 0
    assert message in result.output
    assert out.read_text() == before


def test_resume_replays_the_missing_games_and_the_errors_and_keeps_the_rest(tmp_path):
    _, out = run(tmp_path, *SOLVER)
    errored, kept, _missing = out.read_text().splitlines()
    broken = json.loads(errored) | {"error": "ConnectionError: the API is down", "won": False}
    out.write_text(f"{json.dumps(broken)}\n{kept}\n")
    result, _ = run(tmp_path, *SOLVER, "--resume")
    assert result.exit_code == 0, result.output
    assert "Keeping 1 finished games, playing 2" in result.output
    assert kept in out.read_text().splitlines()
    assert [record["error"] for record in records(out)] == [None, None, None]


def test_a_run_on_a_few_levels_can_be_extended_to_all_of_them_in_the_same_file(tmp_path):
    first, out = run(tmp_path, "--players", "solver", "--levels", "1-3")
    rest, _ = run(tmp_path, "--players", "solver", "--resume")
    assert (first.exit_code, rest.exit_code) == (0, 0)
    assert "Keeping 20 finished games, playing 80" in rest.output
    assert len(records(out)) == 100


def test_a_benchmark_can_play_every_puzzle_under_other_rules(tmp_path):
    result, out = run(tmp_path, *SOLVER, "--rules", "three-moves")
    assert result.exit_code == 0, result.output
    assert {record["rules"] for record in records(out)} == {"three-moves"}
    assert all(record["won"] and "," in record["moves"][0]["move"] for record in records(out))


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        pytest.param((["jev"], "all", "all", "all"), "jev_all", id="everything"),
        pytest.param(
            (["jev"], "map,everything", "1-3", "gen-10-01"),
            "jev_map+everything_levels-1-3_gen-10-01",
            id="narrowed",
        ),
        pytest.param(
            (["jev"], "all", "all", "all", "two-moves"), "jev_all_two-moves", id="other rules"
        ),
        pytest.param(
            (["jev"], "all", "all", "all", "compass"), "jev_all", id="compass says nothing"
        ),
    ],
)
def test_a_run_is_named_after_the_date_and_time_and_what_was_run(args, expected):
    assert _run_name(*args[:4], WHEN, *args[4:]) == f"2026-09-23_18-45_{expected}"


def test_generate_fills_every_level_to_the_requested_count(tmp_path):
    result = runner.invoke(app, ["generate", "--per-level", "2", "--folder", str(tmp_path)])
    assert result.exit_code == 0, result.output
    counts = [len(list((tmp_path / f"level-{level:02d}").glob("gen-*.yaml"))) for level in LEVELS]
    assert counts == [2] * len(LEVELS)
