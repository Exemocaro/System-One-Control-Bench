"""Raw records: the schema, the manifest, and append-only durability."""

import json

from system_one_control.agents.base import build_request
from system_one_control.agents.baselines import FakeProbabilityAgent, OracleAgent
from system_one_control.candidates import build_candidate_set
from system_one_control.controllers import REACTIVE
from system_one_control.env import extract_snapshot, make_env
from system_one_control.oracle import label_candidate_set
from system_one_control.records import (
    JsonlWriter,
    build_manifest,
    decision_record,
    read_jsonl,
    write_manifest,
)

DOORKEY = "MiniGrid-DoorKey-6x6-v0"


def _decision(agent=None, seed=1):
    env = make_env(DOORKEY, max_steps=100)
    env.reset(seed=seed)
    snapshot = extract_snapshot(env)
    built = build_candidate_set(snapshot, horizon=2, max_options=8, rng_seed=0)
    labels = label_candidate_set(snapshot, built)
    if agent is None:
        result = FakeProbabilityAgent().choose(build_request(snapshot, built, request_id="r1"))
    else:
        result = agent.choose_privileged(snapshot, built)
    return snapshot, built, result, labels


def _record(**overrides):
    snapshot, built, result, labels = _decision(**overrides)
    return decision_record(
        run_id="run",
        request_id="r1",
        snapshot=snapshot,
        candidate_set=built,
        result=result,
        labels=labels,
        controller=REACTIVE.name,
        split="test",
        layout_id="sha256:abc",
    )


def test_a_record_carries_the_menu_the_model_saw_and_the_label_joined_after():
    record = _record()
    assert record["candidate_ids"]
    assert set(record["candidate_semantics"]) == set(record["candidate_ids"])
    assert record["selected_candidate_id"] in record["candidate_ids"]
    assert isinstance(record["correct"], bool)
    assert record["oracle_distance"] is not None


def test_regret_is_zero_when_the_oracle_itself_chooses():
    record = _record(agent=OracleAgent())
    assert record["regret"] == 0
    assert record["correct"] is True


def test_global_regret_separates_menu_quality_from_choice_quality():
    record = _record(agent=OracleAgent())
    assert record["global_regret"] == record["candidate_gap"]


def test_a_record_is_json_serialisable_without_custom_encoders():
    json.dumps(_record())


def test_probabilities_round_trip_and_sum_to_one():
    record = _record()
    probabilities = record["probabilities"]
    assert set(probabilities) == set(record["candidate_ids"])
    assert abs(sum(probabilities.values()) - 1.0) < 1e-9


def test_records_append_and_read_back_in_order(tmp_path):
    path = tmp_path / "raw" / "decisions.jsonl"
    with JsonlWriter(path) as writer:
        for index in range(3):
            writer.write({"index": index})
    with JsonlWriter(path) as writer:
        writer.write({"index": 3})

    assert [row["index"] for row in read_jsonl(path)] == [0, 1, 2, 3]


def test_a_truncated_final_line_does_not_lose_the_records_before_it(tmp_path):
    path = tmp_path / "decisions.jsonl"
    with JsonlWriter(path) as writer:
        writer.write({"index": 0})
        writer.write({"index": 1})
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"index": 2, "unterminated"')

    assert [row["index"] for row in read_jsonl(path)] == [0, 1]


def test_the_manifest_records_provenance_and_a_config_hash(tmp_path):
    manifest = build_manifest("run-1", {"horizon": 2, "agents": ["random"]})
    assert manifest.run_id == "run-1"
    assert manifest.python_version.startswith("3.11")
    assert manifest.serializer_version
    assert manifest.config_hash.startswith("sha256:")

    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["run_id"] == "run-1"
    assert loaded["config_hash"] == manifest.config_hash


def test_the_config_hash_changes_when_the_config_does():
    first = build_manifest("run", {"horizon": 2})
    second = build_manifest("run", {"horizon": 3})
    assert first.config_hash != second.config_hash


def test_an_agent_that_answers_nothing_is_recorded_rather_than_dropped():
    from system_one_control.agents.base import DecisionResult

    snapshot, built, _, labels = _decision()
    failed = DecisionResult(agent="broken", selected_display_id=None, error="schema failure")
    record = decision_record(
        run_id="run",
        request_id="r1",
        snapshot=snapshot,
        candidate_set=built,
        result=failed,
        labels=labels,
        controller=REACTIVE.name,
    )
    assert record["error"] == "schema failure"
    assert record["selected_candidate_id"] is None
    assert record["correct"] is None
    assert record["regret"] is None
