import math
from pathlib import Path

import metrics
import pytest


@pytest.mark.parametrize(
    ("level", "distance", "expected"),
    [
        (10, 0, 1.0),
        (10, 10, 0.0),
        (10, 4, 0.6),
        (10, 12, -0.2),
        (10, None, 0.0),
    ],
    ids=["at the goal", "at the start", "part way", "farther than the start", "unknown"],
)
def test_progress(level, distance, expected):
    assert metrics.progress(level, distance) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("won", "fewest", "used", "expected"),
    [
        (True, 5, 5, 1.0),
        (True, 5, 10, 0.5),
        (False, 5, 5, 0.0),
    ],
    ids=["shortest win", "twice as long", "lost"],
)
def test_spl(won, fewest, used, expected):
    assert metrics.spl(won, fewest, used) == expected


@pytest.mark.parametrize(
    ("values", "low", "high"),
    [
        ([1.0] * 10, 1.0, 1.0),
        ([0.0] * 10, 0.0, 0.0),
        ([0.0, 1.0] * 50, 0.4, 0.6),
    ],
    ids=["all ones", "all zeros", "half"],
)
def test_bootstrap_interval(values, low, high):
    found = metrics.bootstrap_interval(values)
    assert low - 0.02 <= found[0] <= found[1] <= high + 0.02


def test_bootstrap_interval_of_nothing():
    assert all(math.isnan(x) for x in metrics.bootstrap_interval([]))


@pytest.mark.parametrize(
    ("probabilities", "expected"),
    [
        ({"north": 0.25, "south": 0.25, "east": 0.25, "west": 0.25}, 0.0),
        ({"north": 1.0, "south": 0.0}, 1.0),
        ({"north": 0.625, "south": 0.125, "east": 0.125, "west": 0.125}, 0.5),
    ],
    ids=["chance", "certain", "halfway"],
)
def test_rescaled_top(probabilities, expected):
    assert metrics.rescaled_top(probabilities) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ([True, False], [True, False], 1.0),
        ([True] * 6, [False] * 6, 2 / 2**6),
        ([True] * 5 + [False], [False] * 5 + [True], 2 * 7 / 2**6),
    ],
    ids=["no discordant pairs", "six for a", "five against one"],
)
def test_mcnemar_p(a, b, expected):
    assert metrics.mcnemar_p(a, b) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        ([0.01, 0.04, 0.03], [0.03, 0.06, 0.06]),
        ([0.5, 0.01], [0.5, 0.02]),
        ([0.9], [0.9]),
    ],
    ids=["three tests", "order kept", "one test"],
)
def test_holm(p, expected):
    assert metrics.holm(p) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("confidences", "correct", "expected"),
    [
        ([0.05, 0.95], [False, True], [(0.05, 0.0, 1), (0.95, 1.0, 1)]),
        ([0.3, 0.3], [True, False], [(0.3, 0.5, 2)]),
        ([1.0], [True], [(1.0, 1.0, 1)]),
    ],
    ids=["two bins", "one bin, half right", "one is in the top bin"],
)
def test_calibration_bins(confidences, correct, expected):
    assert metrics.calibration_bins(confidences, correct) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("confidences", "correct", "ece", "brier"),
    [
        ([1.0, 0.0], [True, False], 0.0, 0.0),
        ([0.9, 0.9], [False, False], 0.9, 0.81),
        ([0.5, 0.5], [True, False], 0.0, 0.25),
    ],
    ids=["perfect", "sure and wrong", "unsure and half right"],
)
def test_ece_and_brier(confidences, correct, ece, brier):
    assert metrics.expected_calibration_error(confidences, correct) == pytest.approx(ece)
    assert metrics.brier_score(confidences, correct) == pytest.approx(brier)


@pytest.mark.parametrize(
    ("xs", "ys", "expected"),
    [
        ([1, 2, 3], [1, 2, 3], 1.0),
        ([1, 2, 3], [1, 1, 1], 0.0),
        ([1, 2, 3], [1, 0, 0], -0.5),
    ],
    ids=["rising", "flat", "falling"],
)
def test_slope(xs, ys, expected):
    assert metrics.slope(xs, ys) == pytest.approx(expected)


def test_the_folder_stays_small():
    """See README.md: three Python files, and analyze.py stays short."""
    here = Path(__file__).parent
    assert sorted(p.name for p in here.glob("*.py")) == [
        "analyze.py",
        "metrics.py",
        "test_metrics.py",
    ]
    assert len((here / "analyze.py").read_text(encoding="utf-8").splitlines()) <= 660
