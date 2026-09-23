import json
from datetime import datetime

from typer.testing import CliRunner

from system_one_control.cli import _run_name, app

runner = CliRunner()


def test_a_benchmark_of_free_players_prints_a_summary_and_saves_moves_and_table(tmp_path):
    out = tmp_path / "results.jsonl"
    result = runner.invoke(app, ["benchmark", "--players", "solver,random", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "solver" in result.output
    assert out.exists()
    assert "SPL" in out.with_suffix(".txt").read_text()


def test_a_paid_player_needs_explicit_permission(tmp_path):
    out = tmp_path / "results.jsonl"
    result = runner.invoke(app, ["benchmark", "--players", "jev", "--out", str(out)])
    assert result.exit_code != 0
    assert "--allow-paid" in result.output
    assert not out.exists()


def test_benchmarks_use_the_map_condition_unless_told_otherwise(tmp_path):
    out = tmp_path / "results.jsonl"
    runner.invoke(app, ["benchmark", "--players", "solver", "--out", str(out)])
    assert {json.loads(line)["condition"] for line in out.read_text().splitlines()} == {"map"}


def test_a_benchmark_never_overwrites_an_earlier_one(tmp_path):
    out = tmp_path / "results.jsonl"
    out.write_text("earlier results\n")
    result = runner.invoke(app, ["benchmark", "--players", "solver", "--out", str(out)])
    assert result.exit_code != 0
    assert "already exists" in result.output
    assert "--resume" in result.output
    assert out.read_text() == "earlier results\n"


THREE = "goal-east,goal-north,dead-end"


def test_resume_replays_the_missing_games_and_the_errors_and_keeps_the_rest(tmp_path):
    out = tmp_path / "results.jsonl"
    command = ["benchmark", "--players", "solver", "--scenarios", THREE, "--out", str(out)]
    assert runner.invoke(app, command).exit_code == 0
    errored, kept, _missing = out.read_text().splitlines()
    broken = json.loads(errored) | {"error": "ConnectionError: the API is down", "won": False}
    out.write_text(f"{json.dumps(broken)}\n{kept}\n")

    result = runner.invoke(app, [*command, "--resume"])
    assert result.exit_code == 0, result.output
    assert "Keeping 1 finished games, playing 2" in result.output
    lines = out.read_text().splitlines()
    assert len(lines) == 3 and kept in lines
    assert all(json.loads(line)["error"] is None for line in lines)


def test_resume_refuses_a_file_from_a_different_run(tmp_path):
    out = tmp_path / "results.jsonl"
    runner.invoke(
        app, ["benchmark", "--players", "solver", "--scenarios", THREE, "--out", str(out)]
    )
    before = out.read_text()
    other = ["benchmark", "--players", "random", "--scenarios", THREE, "--out", str(out)]
    result = runner.invoke(app, [*other, "--resume"])
    assert result.exit_code != 0
    assert "would not play" in result.output
    assert out.read_text() == before


def test_different_runs_get_different_file_names_with_the_date_and_time():
    when = datetime(2026, 9, 23, 18, 45)
    names = {
        _run_name(["jev"], "all", "all", "all", when),
        _run_name(["jev"], "all", "1-3", "all", when),
        _run_name(["jev"], "all", "all", "gen-10-01", when),
        _run_name(["jev"], "map,everything", "all", "all", when),
        _run_name(["jev"], "all", "all", "all", datetime(2026, 9, 23, 18, 46)),
    }
    assert len(names) == 5
    assert _run_name(["jev"], "map", "1-3", "all", when) == "2026-09-23_18-45_jev_map_levels-1-3"


def test_levels_choose_the_scenarios_to_play(tmp_path):
    out = tmp_path / "results.jsonl"
    result = runner.invoke(
        app, ["benchmark", "--players", "solver", "--levels", "2,4-5", "--out", str(out)]
    )
    assert result.exit_code == 0, result.output
    levels = {json.loads(line)["moves_to_goal"] for line in out.read_text().splitlines()}
    assert levels == {2, 4, 5}
    assert "3 away" not in result.output


def test_levels_that_cannot_be_read_are_refused(tmp_path):
    result = runner.invoke(
        app, ["benchmark", "--levels", "one", "--out", str(tmp_path / "r.jsonl")]
    )
    assert result.exit_code != 0
    assert "levels must look like" in result.output


def test_generate_fills_every_level_to_the_requested_count(tmp_path):
    result = runner.invoke(app, ["generate", "--per-level", "2", "--folder", str(tmp_path)])
    assert result.exit_code == 0, result.output
    for level in range(1, 11):
        assert len(list((tmp_path / f"level-{level:02d}").glob("gen-*.yaml"))) == 2


def test_examples_are_written_for_every_condition():
    result = runner.invoke(app, ["examples"])
    assert result.exit_code == 0, result.output
    assert "everything-memory.json" in result.output


def test_unknown_scenarios_are_refused(tmp_path):
    out = tmp_path / "results.jsonl"
    result = runner.invoke(app, ["benchmark", "--scenarios", "nowhere", "--out", str(out)])
    assert result.exit_code != 0
    assert "nowhere" in result.output
