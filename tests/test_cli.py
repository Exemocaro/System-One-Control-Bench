"""End-to-end smoke tests: the documented commands must actually work."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from system_one_control.cli import app

runner = CliRunner()
PILOT = Path("configs/pilot.yaml")


def _run(*args):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output + str(result.exception)
    return result.output


def test_doctor_reports_the_stack_and_which_adapters_are_missing():
    output = _run("doctor", "--config", str(PILOT))
    assert "minigrid" in output
    assert "typesafe_sdk" in output
    assert "pilot" in output


def test_doctor_is_explicit_when_the_config_is_absent():
    output = _run("doctor", "--config", "configs/nope.yaml")
    assert "NOT FOUND" in output


def test_census_reports_distinct_layouts():
    output = _run("census", "MiniGrid-DoorKey-6x6-v0", "--seeds", "40")
    assert "distinct layouts" in output


def test_estimate_prints_the_call_count_without_making_any(tmp_path):
    output = _run("estimate", "--config", str(PILOT))
    assert "total offline decisions" in output


def test_audit_inputs_reports_the_largest_request():
    output = _run("audit-inputs", "--config", str(PILOT))
    assert "largest request" in output
    assert "characters" in output


def test_build_dataset_writes_a_manifest_with_a_checksum(tmp_path):
    _run("build-dataset", "--config", str(PILOT), "--runs", str(tmp_path))
    manifests = list((tmp_path / "pilot").glob("dataset_*.json"))
    assert manifests
    assert "sha256:" in manifests[0].read_text(encoding="utf-8")


def test_the_whole_offline_pipeline_runs_and_reports(tmp_path):
    _run("evaluate-offline", "--config", str(PILOT), "--runs", str(tmp_path))
    decisions = tmp_path / "pilot" / "decisions.jsonl"
    assert decisions.exists()
    assert (tmp_path / "pilot" / "manifest.json").exists()

    output = _run("report", "--run", str(tmp_path / "pilot"), "--bootstrap-samples", "100")
    assert "horizon 1" in output
    assert "oracle" in output and "random" in output


def test_the_whole_online_pipeline_runs(tmp_path):
    output = _run("evaluate-online", "--config", str(PILOT), "--runs", str(tmp_path))
    assert "success" in output
    assert (tmp_path / "pilot" / "episodes.jsonl").exists()


def test_report_refuses_a_directory_with_no_records(tmp_path):
    result = runner.invoke(app, ["report", "--run", str(tmp_path)])
    assert result.exit_code != 0


def test_a_dry_run_with_the_fake_agent_completes_both_pipelines(tmp_path):
    """Phase 7's check that the harness works without any real model."""
    _run("evaluate-offline", "--config", str(PILOT), "--runs", str(tmp_path), "--agents", "fake")
    _run("evaluate-online", "--config", str(PILOT), "--runs", str(tmp_path), "--agents", "fake")
    assert (tmp_path / "pilot" / "decisions.jsonl").exists()
    assert (tmp_path / "pilot" / "episodes.jsonl").exists()


@pytest.mark.parametrize("command", ["doctor", "census", "build-dataset", "report"])
def test_every_command_has_help_text(command):
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_an_empty_split_is_reported_rather_than_crashing(tmp_path):
    """A split with no states used to end the online run in a traceback."""
    config = tmp_path / "empty.yaml"
    config.write_text(
        "experiment_id: empty\n"
        "environments: [MiniGrid-DoorKey-6x6-v0]\n"
        "agents: [oracle]\n"
        "dataset:\n  seeds: 3\n  states_per_episode: 1\n  split: calibration\n"
        "online:\n  starts_per_environment: 2\n",
        encoding="utf-8",
    )
    output = _run("evaluate-online", "--config", str(config), "--runs", str(tmp_path))
    assert "skipping" in output or "success" in output


def test_build_dataset_flags_an_environment_that_has_only_one_layout(tmp_path):
    config = tmp_path / "single.yaml"
    config.write_text(
        "experiment_id: single\n"
        "environments: [MiniGrid-Empty-Random-6x6-v0]\n"
        "agents: [oracle]\n"
        "dataset:\n  seeds: 20\n  states_per_episode: 1\n",
        encoding="utf-8",
    )
    output = _run("build-dataset", "--config", str(config), "--runs", str(tmp_path))
    assert "within-layout" in output
    assert "sanity check" in output


def test_diagnose_can_show_the_questions_without_making_any_calls(tmp_path):
    output = _run(
        "diagnose",
        "--agent",
        "random",
        "--config",
        str(PILOT),
        "--runs",
        str(tmp_path),
        "--states",
        "2",
        "--dry-run",
    )
    assert "items over" in output
    assert "[orientation]" in output and "[movement]" in output


def test_diagnose_scores_an_agent_and_saves_records(tmp_path):
    output = _run(
        "diagnose",
        "--agent",
        "random",
        "--config",
        str(PILOT),
        "--runs",
        str(tmp_path),
        "--states",
        "3",
    )
    assert "overall accuracy" in output
    assert (tmp_path / "pilot" / "diagnostics.jsonl").exists()


def test_diagnose_refuses_a_privileged_agent(tmp_path):
    result = runner.invoke(
        app,
        ["diagnose", "--agent", "oracle", "--config", str(PILOT), "--runs", str(tmp_path)],
    )
    assert result.exit_code != 0


def test_diagnose_covers_every_configured_environment(tmp_path):
    """Taking the first N states of a concatenated list drops later environments."""
    config = tmp_path / "two.yaml"
    config.write_text(
        "experiment_id: two\n"
        "environments: [MiniGrid-DoorKey-6x6-v0, MiniGrid-Empty-Random-6x6-v0]\n"
        "agents: [random]\n"
        "dataset:\n  seeds: 12\n  states_per_episode: 1\n  split: development\n",
        encoding="utf-8",
    )
    _run(
        "diagnose",
        "--agent",
        "random",
        "--config",
        str(config),
        "--runs",
        str(tmp_path),
        "--states",
        "4",
    )

    rows = [
        json.loads(line)
        for line in (tmp_path / "two" / "diagnostics.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert {row["environment"] for row in rows} == {
        "MiniGrid-DoorKey-6x6-v0",
        "MiniGrid-Empty-Random-6x6-v0",
    }


def test_report_takes_its_bootstrap_count_from_the_run_that_produced_it(tmp_path):
    """The option's help promises this; nothing was reading the manifest."""
    config = tmp_path / "few.yaml"
    config.write_text(
        "experiment_id: few\n"
        "environments: [MiniGrid-DoorKey-6x6-v0]\n"
        "agents: [random]\n"
        "dataset:\n  seeds: 4\n  states_per_episode: 1\n  split: development\n"
        "  states_per_environment: 4\n"
        "offline:\n  horizons: [1]\n"
        "statistics:\n  bootstrap_samples: 37\n",
        encoding="utf-8",
    )
    _run("evaluate-offline", "--config", str(config), "--runs", str(tmp_path))
    output = _run("report", "--run", str(tmp_path / "few"))
    assert "37 bootstrap resamples" in output


def test_diagnose_asks_about_pickups_when_any_are_in_reach(tmp_path):
    """An affordance question everyone answers "no" to measures nothing."""
    _run(
        "diagnose",
        "--agent",
        "random",
        "--config",
        str(PILOT),
        "--runs",
        str(tmp_path),
        "--states",
        "8",
    )
    rows = [
        json.loads(line)
        for line in (tmp_path / "pilot" / "diagnostics.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    reachable = [row["facts"].get("reachable") for row in rows if row["category"] == "affordance"]
    assert "true" in reachable
