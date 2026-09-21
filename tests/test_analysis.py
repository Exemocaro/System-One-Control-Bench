"""Metrics, and the statistical conventions the benchmark depends on."""

from types import SimpleNamespace

import pytest

from system_one_control.analysis import (
    brier_score,
    cluster_bootstrap,
    decision_metrics,
    episode_metrics,
    expected_calibration_error,
    format_decision_table,
    risk_coverage,
    selective_accuracy,
)


def _fake_episode(*, success, layout):
    """The few EpisodeResult fields the metrics actually read."""
    return SimpleNamespace(
        agent="demo",
        controller="reactive",
        success=success,
        truncated=not success,
        invalid_selection=False,
        steps_used=3,
        layout_id=layout,
    )


def _row(**overrides):
    row = {
        "agent": "demo",
        "layout_id": "L0",
        "state_id": "S0",
        "correct": True,
        "regret": 0,
        "global_regret": 0,
        "selected_cost": 3,
        "global_optimal_present": True,
        "all_candidates_fail": False,
        "candidate_subsampled": False,
        "error": None,
        "latency_ms": 1.0,
        "probabilities": {"option_000": 0.9, "option_001": 0.1},
        "selected_candidate_id": "option_000",
        "reported_confidence": None,
    }
    row.update(overrides)
    return row


def test_accuracy_counts_only_the_decisions_it_can_score():
    rows = [
        _row(correct=True),
        _row(correct=False),
        _row(correct=None, error="boom"),
        _row(correct=None, all_candidates_fail=True),
    ]
    metrics = decision_metrics(rows, bootstrap_samples=200)

    assert metrics.n == 4
    assert metrics.scored == 2
    assert metrics.accuracy.point == pytest.approx(0.5)
    assert metrics.error_rate == pytest.approx(0.25)
    assert metrics.all_fail_rate == pytest.approx(0.25)


def test_a_menu_where_everything_fails_is_never_counted_as_a_correct_answer():
    rows = [_row(correct=None, all_candidates_fail=True) for _ in range(5)]
    metrics = decision_metrics(rows, bootstrap_samples=50)
    assert metrics.scored == 0
    assert metrics.accuracy is None
    assert metrics.all_fail_rate == 1.0


def test_candidate_recall_reports_how_often_the_best_move_was_even_offered():
    rows = [_row(global_optimal_present=True), _row(global_optimal_present=False)]
    assert decision_metrics(rows, bootstrap_samples=50).candidate_recall == pytest.approx(0.5)


def test_a_selection_with_infinite_cost_counts_as_a_failure():
    rows = [_row(selected_cost=None, correct=False, regret=None), _row(selected_cost=2)]
    metrics = decision_metrics(rows, bootstrap_samples=50)
    assert metrics.failure_rate == pytest.approx(0.5)


def test_layouts_are_counted_so_the_effective_sample_size_is_visible():
    rows = [_row(layout_id=f"L{index % 3}") for index in range(30)]
    assert decision_metrics(rows, bootstrap_samples=50).layouts == 3


def test_the_interval_brackets_the_point_estimate_and_is_reproducible():
    clusters = {f"L{index}": [float(index % 2)] for index in range(20)}
    first = cluster_bootstrap(clusters, lambda v: sum(v) / len(v), samples=500, seed=1)
    again = cluster_bootstrap(clusters, lambda v: sum(v) / len(v), samples=500, seed=1)

    assert first == again
    assert first.low <= first.point <= first.high


def test_correlated_states_inside_few_layouts_give_a_wider_interval():
    """The whole reason for clustering: 40 states from 2 maps are not 40 samples."""
    many_layouts = {f"L{index}": [float(index % 2)] for index in range(40)}
    few_layouts = {"L0": [1.0] * 20, "L1": [0.0] * 20}

    wide = cluster_bootstrap(few_layouts, lambda v: sum(v) / len(v), samples=800, seed=0)
    narrow = cluster_bootstrap(many_layouts, lambda v: sum(v) / len(v), samples=800, seed=0)
    assert (wide.high - wide.low) > (narrow.high - narrow.low)


def test_a_perfectly_calibrated_agent_has_almost_no_calibration_error():
    rows = [_row(reported_confidence=1.0, correct=True) for _ in range(50)]
    rows += [_row(reported_confidence=0.0, correct=False) for _ in range(50)]
    assert expected_calibration_error(rows) == pytest.approx(0.0, abs=1e-9)


def test_confident_but_wrong_is_penalised():
    rows = [_row(reported_confidence=0.95, correct=False) for _ in range(20)]
    assert expected_calibration_error(rows) == pytest.approx(0.95, abs=1e-6)


def test_confidence_falls_back_to_the_probability_of_the_chosen_option():
    rows = [_row(reported_confidence=None, correct=True) for _ in range(10)]
    assert expected_calibration_error(rows) == pytest.approx(0.1, abs=1e-9)


def test_calibration_is_undefined_when_nothing_reports_confidence():
    rows = [_row(probabilities=None, reported_confidence=None)]
    assert expected_calibration_error(rows) is None


def test_risk_coverage_starts_at_the_most_confident_answer():
    rows = [
        _row(reported_confidence=0.9, correct=True),
        _row(reported_confidence=0.8, correct=True),
        _row(reported_confidence=0.2, correct=False),
    ]
    curve = risk_coverage(rows)
    assert curve[0] == (pytest.approx(1 / 3), pytest.approx(1.0))
    assert curve[-1] == (pytest.approx(1.0), pytest.approx(2 / 3))


def test_brier_score_rewards_honest_probabilities():
    confident_right = [_row(reported_confidence=1.0, correct=True) for _ in range(10)]
    confident_wrong = [_row(reported_confidence=1.0, correct=False) for _ in range(10)]
    assert brier_score(confident_right) == pytest.approx(0.0)
    assert brier_score(confident_wrong) == pytest.approx(1.0)


def test_the_table_lists_one_line_per_agent():
    rows_a = [_row(agent="random", correct=False) for _ in range(4)]
    rows_b = [_row(agent="oracle", correct=True) for _ in range(4)]
    table = format_decision_table(
        [
            decision_metrics(rows_a, bootstrap_samples=50),
            decision_metrics(rows_b, bootstrap_samples=50),
        ]
    )
    assert "random" in table and "oracle" in table
    assert len(table.splitlines()) == 4


def test_summarising_nothing_is_an_error_rather_than_a_silent_zero():
    with pytest.raises(ValueError):
        decision_metrics([])


def test_episode_metrics_report_how_many_clusters_backed_the_interval():
    """One layout cannot support an interval; the count is what says so."""
    episodes = [
        _fake_episode(success=True, layout="L0"),
        _fake_episode(success=False, layout="L0"),
    ]
    metrics = episode_metrics(episodes, layout_of=lambda e: e.layout_id, bootstrap_samples=50)
    assert metrics.layouts == 1
    assert metrics.success_rate is not None
    assert metrics.success_rate.low == metrics.success_rate.high  # degenerate, by construction


def test_more_layouts_are_counted_as_more_clusters():
    episodes = [
        _fake_episode(success=True, layout="L0"),
        _fake_episode(success=False, layout="L1"),
        _fake_episode(success=True, layout="L2"),
    ]
    metrics = episode_metrics(episodes, layout_of=lambda e: e.layout_id, bootstrap_samples=50)
    assert metrics.layouts == 3


def test_selective_accuracy_reports_what_is_kept_at_a_coverage_level():
    """Answering only where confident should beat answering everywhere."""
    rows = [
        _row(agent="a", correct=True, reported_confidence=0.9),
        _row(agent="a", correct=True, reported_confidence=0.8),
        _row(agent="a", correct=False, reported_confidence=0.2),
        _row(agent="a", correct=False, reported_confidence=0.1),
    ]
    assert selective_accuracy(rows, coverage=0.5) == 1.0
    assert selective_accuracy(rows, coverage=1.0) == 0.5


def test_selective_accuracy_is_absent_when_nothing_reported_a_confidence():
    """A probability over the chosen option counts; an agent with neither does not."""
    silent = _row(agent="a", correct=True, probabilities=None, reported_confidence=None)
    assert selective_accuracy([silent]) is None
    assert selective_accuracy([_row(agent="a", correct=True)]) == 1.0
