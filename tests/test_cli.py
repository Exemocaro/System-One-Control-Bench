import json

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
    assert out.read_text() == "earlier results\n"


def test_different_runs_get_different_file_names():
    names = {
        _run_name(["jev"], "all", "all", first_move_only=False),
        _run_name(["jev"], "all", "all", first_move_only=True),
        _run_name(["jev"], "all", "gen-10-01", first_move_only=False),
        _run_name(["jev"], "map,everything", "all", first_move_only=False),
    }
    assert len(names) == 4
    assert _run_name(["jev"], "all", "all", first_move_only=True).endswith("_jev_all_first-move")


def test_generate_fills_every_level_to_the_requested_count(tmp_path):
    result = runner.invoke(app, ["generate", "--per-level", "2", "--folder", str(tmp_path)])
    assert result.exit_code == 0, result.output
    for level in range(1, 11):
        assert len(list((tmp_path / f"level-{level:02d}").glob("gen-*.yaml"))) == 2


def test_examples_are_written_for_every_condition():
    result = runner.invoke(app, ["examples"])
    assert result.exit_code == 0, result.output
    assert "everything-memory.txt" in result.output


def test_unknown_scenarios_are_refused(tmp_path):
    out = tmp_path / "results.jsonl"
    result = runner.invoke(app, ["benchmark", "--scenarios", "nowhere", "--out", str(out)])
    assert result.exit_code != 0
    assert "nowhere" in result.output
