"""The numbers the paper reports, as small pure functions."""

from __future__ import annotations

import math

import numpy as np


def progress(level: int, distance: int | None) -> float:
    """Share of the way to the goal at a position `distance` steps from it; 0 when unknown."""
    return 0.0 if distance is None else 1 - distance / level


def spl(won: bool, fewest_moves: int, moves_used: int) -> float:
    """Success weighted by path length: fewest / max(fewest, used) for a win, else 0."""
    return fewest_moves / max(fewest_moves, moves_used) if won else 0.0


def bootstrap_interval(
    values: list[float], samples: int = 10_000, seed: int = 0
) -> tuple[float, float]:
    """95% percentile bootstrap interval for the mean (one value per puzzle)."""
    if not values:
        return (math.nan, math.nan)
    array = np.asarray(values, dtype=float)
    draws = np.random.default_rng(seed).integers(0, len(array), size=(samples, len(array)))
    low, high = np.percentile(array[draws].mean(axis=1), [2.5, 97.5])
    return float(low), float(high)


def mcnemar_p(a_won: list[bool], b_won: list[bool]) -> float:
    """Exact two-sided McNemar p-value from the discordant pairs."""
    a_only = sum(a and not b for a, b in zip(a_won, b_won, strict=True))
    b_only = sum(b and not a for a, b in zip(a_won, b_won, strict=True))
    n = a_only + b_only
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(a_only, b_only) + 1)) / 2**n
    return min(1.0, 2 * tail)


def holm(p_values: list[float]) -> list[float]:
    """Holm-adjusted p-values, in the order given."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted = [1.0] * len(p_values)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def calibration_bins(
    confidences: list[float], correct: list[bool], bins: int = 10
) -> list[tuple[float, float, int]]:
    """Per equal-width bin: (mean confidence, share correct, count); empty bins are left out."""
    groups: list[list[int]] = [[] for _ in range(bins)]
    for i, c in enumerate(confidences):
        groups[min(int(c * bins), bins - 1)].append(i)
    return [
        (
            sum(confidences[i] for i in group) / len(group),
            sum(correct[i] for i in group) / len(group),
            len(group),
        )
        for group in groups
        if group
    ]


def expected_calibration_error(
    confidences: list[float], correct: list[bool], bins: int = 10
) -> float:
    """Count-weighted mean gap between a bin's confidence and its share correct."""
    return sum(n * abs(c - a) for c, a, n in calibration_bins(confidences, correct, bins)) / len(
        confidences
    )


def brier_score(confidences: list[float], correct: list[bool]) -> float:
    """Mean squared gap between the confidence and the outcome (1 correct, 0 not)."""
    return sum((c - y) ** 2 for c, y in zip(confidences, correct, strict=True)) / len(confidences)


def slope(xs: list[float], ys: list[float]) -> float:
    """Slope of the least-squares line through the points."""
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sxx
