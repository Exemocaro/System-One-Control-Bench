import json

from typer.testing import CliRunner

from system_one_control.cli import app

runner = CliRunner()


def test_an_experiment_with_free_players_prints_a_summary_and_saves_results(tmp_path):
    out = tmp_path / "results.jsonl"
    result = runner.invoke(app, ["experiment", "--players", "solver,random", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "solver" in result.output
    assert out.exists()


def test_a_paid_player_needs_explicit_permission(tmp_path):
    out = tmp_path / "results.jsonl"
    result = runner.invoke(app, ["experiment", "--players", "jev", "--out", str(out)])
    assert result.exit_code != 0
    assert "--allow-paid" in result.output
    assert not out.exists()


def test_experiments_use_the_full_prompt_unless_told_otherwise(tmp_path):
    out = tmp_path / "results.jsonl"
    runner.invoke(app, ["experiment", "--players", "solver", "--out", str(out)])
    assert {json.loads(line)["prompt"] for line in out.read_text().splitlines()} == {"full"}


def test_generate_fills_every_level_to_the_requested_count(tmp_path):
    result = runner.invoke(app, ["generate", "--per-level", "2", "--folder", str(tmp_path)])
    assert result.exit_code == 0, result.output
    for level in range(1, 11):
        assert len(list((tmp_path / f"level-{level:02d}").glob("gen-*.yaml"))) == 2


def test_unknown_scenarios_are_refused(tmp_path):
    out = tmp_path / "results.jsonl"
    result = runner.invoke(app, ["experiment", "--scenarios", "nowhere", "--out", str(out)])
    assert result.exit_code != 0
    assert "nowhere" in result.output
