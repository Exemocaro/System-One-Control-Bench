"""The dynamics diagnostic: does the model understand the rules at all?

Every correct answer here is computed by the pure transition function, so the
diagnostic inherits the same ground truth as the benchmark itself.
"""

from system_one_control.agents.baselines import RandomAgent
from system_one_control.diagnostics import (
    CATEGORIES,
    accuracy_by_fact,
    balance_states,
    build_diagnostic,
    diagnostic_metrics,
    diagnostic_record,
    find_key_states,
    format_diagnostic_report,
    run_diagnostic,
)
from system_one_control.env import extract_snapshot, make_env
from system_one_control.transition import EAST, NORTH, SOUTH, WEST
from tests.helpers import snapshot_from_ascii
from tests.maps import CORRIDOR, KEY_ROOM


class _PerfectAgent:
    """Answers every item correctly. Test-only: it is handed the key."""

    name = "perfect"
    privileged = False

    def __init__(self, items):
        self._answers = {item.request.request_id: item.correct_display_id for item in items}

    def choose(self, request):
        from system_one_control.agents.base import DecisionResult

        return DecisionResult(
            agent=self.name, selected_display_id=self._answers[request.request_id]
        )


def _snapshot():
    return snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)


def test_a_diagnostic_covers_every_category():
    items = build_diagnostic([_snapshot()], rng_seed=0)
    assert {item.category for item in items} == set(CATEGORIES)


def test_every_item_offers_its_correct_answer():
    items = build_diagnostic([_snapshot()], rng_seed=0)
    for item in items:
        assert item.correct_display_id in item.request.display_ids


def test_the_orientation_item_agrees_with_the_transition_function():
    from system_one_control.transition import LEFT, step

    snapshot = _snapshot()
    items = [i for i in build_diagnostic([snapshot], rng_seed=0) if i.category == "orientation"]
    assert items
    for item in items:
        expected = step(snapshot, item.action).snapshot.agent_dir
        assert item.answer_text == ("east", "south", "west", "north")[expected]
    # Turning left from east faces north, which is the fact being tested.
    assert step(snapshot, LEFT).snapshot.agent_dir == NORTH


def test_the_movement_item_agrees_with_the_transition_function():
    from system_one_control.transition import FORWARD, step

    snapshot = _snapshot()
    items = [i for i in build_diagnostic([snapshot], rng_seed=0) if i.category == "movement"]
    assert items
    after = step(snapshot, FORWARD).snapshot
    for item in items:
        assert item.answer_text == f"({after.agent_pos[0]}, {after.agent_pos[1]})"


def test_a_blocked_move_is_asked_about_too():
    """Facing a wall, the honest answer is that the agent does not move."""
    facing_wall = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=WEST)
    items = [i for i in build_diagnostic([facing_wall], rng_seed=0) if i.category == "movement"]
    assert items
    assert items[0].answer_text == "(1, 1)"


def test_the_affordance_item_knows_a_key_is_out_of_reach():
    away_from_key = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 2), agent_dir=SOUTH)
    items = [i for i in build_diagnostic([away_from_key], rng_seed=0) if i.category == "affordance"]
    assert items
    assert items[0].answer_text == "no"


def test_the_affordance_item_knows_a_key_is_in_reach():
    facing_key = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=WEST)
    items = [i for i in build_diagnostic([facing_key], rng_seed=0) if i.category == "affordance"]
    assert items
    assert items[0].answer_text == "yes"


def test_no_item_reveals_its_own_answer_in_the_question():
    items = build_diagnostic([_snapshot()], rng_seed=0)
    for item in items:
        text = item.request.question.lower()
        for forbidden in ("correct", "answer is", "optimal", "distance"):
            assert forbidden not in text


def test_options_are_shuffled_so_position_carries_no_signal():
    """A fixed answer position would let a model score well by always guessing it."""
    positions = set()
    for seed in range(12):
        for item in build_diagnostic([_snapshot()], rng_seed=seed):
            if item.category == "orientation":
                positions.add(item.request.display_ids.index(item.correct_display_id))
    assert len(positions) > 1


def test_a_perfect_agent_scores_one_in_every_category():
    items = build_diagnostic([_snapshot()], rng_seed=0)
    results = run_diagnostic(_PerfectAgent(items), items)
    report = diagnostic_metrics(results)
    assert report.overall == 1.0
    for category in CATEGORIES:
        assert report.by_category[category] == 1.0


def test_a_random_agent_scores_below_a_perfect_one():
    items = build_diagnostic(
        [_snapshot(), snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=WEST)],
        rng_seed=0,
    )
    report = diagnostic_metrics(run_diagnostic(RandomAgent(seed=3), items))
    assert 0.0 <= report.overall < 1.0


def test_a_diagnostic_record_is_json_ready_and_says_what_was_asked():
    import json

    items = build_diagnostic([_snapshot()], rng_seed=0)
    results = run_diagnostic(_PerfectAgent(items), items)
    record = diagnostic_record(run_id="run", item=items[0], result=results[0][1])
    json.dumps(record)
    assert record["category"] in CATEGORIES
    assert record["correct"] is True
    assert record["agent"] == "perfect"


def test_items_are_built_from_real_environment_states_too():
    env = make_env("MiniGrid-DoorKey-6x6-v0", max_steps=100)
    env.reset(seed=3)
    items = build_diagnostic([extract_snapshot(env)], rng_seed=0)
    assert len(items) == len(CATEGORIES)


def test_the_same_seed_builds_the_same_diagnostic():
    first = build_diagnostic([_snapshot()], rng_seed=7)
    second = build_diagnostic([_snapshot()], rng_seed=7)
    assert [i.request.display_ids for i in first] == [i.request.display_ids for i in second]
    assert [i.correct_display_id for i in first] == [i.correct_display_id for i in second]


def test_an_item_carries_the_same_legend_the_benchmark_uses():
    """A diagnostic on different wording would not explain benchmark results."""
    from system_one_control.observation import DYNAMICS_LEGEND

    for item in build_diagnostic([_snapshot()], rng_seed=0):
        assert item.request.legend == DYNAMICS_LEGEND


def test_a_movement_item_records_whether_the_way_was_blocked():
    """The blocked/free split is the breakdown that explains a movement score."""
    free = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    blocked = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=WEST)
    free_item = [i for i in build_diagnostic([free], rng_seed=0) if i.category == "movement"][0]
    blocked_item = [i for i in build_diagnostic([blocked], rng_seed=0) if i.category == "movement"][
        0
    ]
    assert free_item.facts["blocked"] == "false"
    assert blocked_item.facts["blocked"] == "true"


def test_an_affordance_item_records_whether_anything_was_in_reach():
    facing_key = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=WEST)
    item = [i for i in build_diagnostic([facing_key], rng_seed=0) if i.category == "affordance"][0]
    assert item.facts["reachable"] == "true"


def test_an_orientation_item_records_which_way_it_turned():
    items = [i for i in build_diagnostic([_snapshot()], rng_seed=0) if i.category == "orientation"]
    assert items[0].facts["turn"] in ("left", "right")


def test_facts_never_reach_the_model():
    """Facts are joined after the answer, exactly like an oracle label."""
    for item in build_diagnostic([_snapshot()], rng_seed=0):
        rendered = item.request.state + item.request.question + item.request.legend
        for value in item.facts.values():
            assert f"blocked={value}" not in rendered


def test_accuracy_can_be_broken_down_by_a_recorded_fact():
    free = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    blocked = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=WEST)
    items = [i for i in build_diagnostic([free, blocked], rng_seed=0) if i.category == "movement"]
    results = run_diagnostic(_PerfectAgent(items), items)
    split = accuracy_by_fact(results, "blocked")
    assert split == {"true": 1.0, "false": 1.0}


def test_a_record_carries_the_facts_for_later_analysis():
    items = build_diagnostic([_snapshot()], rng_seed=0)
    results = run_diagnostic(_PerfectAgent(items), items)
    record = diagnostic_record(run_id="run", item=items[0], result=results[0][1])
    assert record["facts"] == items[0].facts


def test_a_fact_breakdown_reports_how_many_items_backed_each_rate():
    """0.000 over two items and 0.000 over fifty are not the same claim."""
    free = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    blocked = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=WEST)
    items = [i for i in build_diagnostic([free, blocked], rng_seed=0) if i.category == "movement"]
    report = diagnostic_metrics(run_diagnostic(_PerfectAgent(items), items))
    assert report.counts_by_fact["blocked"] == {"false": 1, "true": 1}


def test_the_printed_report_shows_those_counts():
    items = build_diagnostic([_snapshot()], rng_seed=0)
    report = diagnostic_metrics(run_diagnostic(_PerfectAgent(items), items))
    assert "n=" in format_diagnostic_report(report)


def test_balanced_states_put_pickups_within_reach_when_any_exist():
    """If almost every answer is "no", always answering no scores well."""
    facing_key = snapshot_from_ascii(KEY_ROOM, agent_pos=(2, 1), agent_dir=WEST)
    empty = snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)
    pool = [empty] * 20 + [facing_key] * 5

    chosen = balance_states(pool, total=8)
    assert len(chosen) == 8
    in_reach = set(find_key_states(pool))
    assert sum(1 for s in chosen if s in in_reach) >= 2


def test_balanced_states_are_unchanged_when_nothing_is_ever_in_reach():
    pool = [snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)] * 5
    assert len(balance_states(pool, total=3)) == 3


def test_balanced_states_never_ask_for_more_than_the_pool_holds():
    pool = [snapshot_from_ascii(CORRIDOR, agent_pos=(1, 1), agent_dir=EAST)] * 2
    assert len(balance_states(pool, total=10)) == 2
