"""The statistics the validation study turns on.

Small, dependency-free, and tested against worked examples with known answers.
These four numbers decide whether the engine ships, so they are not a place to
trust an unfamiliar library call.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def pearson(pairs: list[tuple[float, float]]) -> float:
    """Correlation. Zero when either side is constant, rather than a crash."""
    n = len(pairs)
    if n < 3:
        return 0.0
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    var_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    var_y = sum((y - mean_y) ** 2 for _, y in pairs)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def spearman(pairs: list[tuple[float, float]]) -> float:
    """Rank correlation.

    Reported alongside Pearson because for a placement decision the ordering
    matters more than the spacing: a system that ranks students correctly but
    compresses the scale is fixable with a linear map, and one that gets the
    ordering wrong is not fixable at all.
    """
    if len(pairs) < 3:
        return 0.0
    return pearson(list(zip(_ranks([x for x, _ in pairs]),
                            _ranks([y for _, y in pairs]))))


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        # Ties share the average rank, or a rater who used only three of five
        # points would distort the coefficient.
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def icc_two_way_random(ratings: list[list[float]]) -> float:
    """ICC(2,k) — agreement among raters who each rated every subject.

    ``ratings`` is one row per subject, one column per rater.

    Absolute agreement, not consistency: two raters whose scores correlate
    perfectly but sit two points apart do not agree about whether a student
    passes, and the study needs the stricter question answered.
    """
    subjects = [row for row in ratings if len(row) >= 2 and None not in row]
    if not subjects:
        return 0.0

    # Shape is checked before the sample-size guard. A ragged matrix is a
    # caller mistake at any size, and returning 0.0 for it would hide the
    # mistake behind a plausible-looking "the raters disagree".
    k = len(subjects[0])
    if any(len(row) != k for row in subjects):
        raise ValueError("every subject must be rated by the same raters")

    if len(subjects) < 3:
        return 0.0
    n = len(subjects)

    grand = sum(sum(row) for row in subjects) / (n * k)
    subject_means = [sum(row) / k for row in subjects]
    rater_means = [sum(row[j] for row in subjects) / n for j in range(k)]

    ms_between_subjects = k * sum((m - grand) ** 2 for m in subject_means) / (n - 1)
    ms_between_raters = n * sum((m - grand) ** 2 for m in rater_means) / (k - 1) \
        if k > 1 else 0.0
    residual = sum(
        (subjects[i][j] - subject_means[i] - rater_means[j] + grand) ** 2
        for i in range(n) for j in range(k)
    )
    ms_error = residual / ((n - 1) * (k - 1)) if (n - 1) * (k - 1) > 0 else 0.0

    denominator = ms_between_subjects + (ms_between_raters - ms_error) / n
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, (ms_between_subjects - ms_error) / denominator))


@dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    correlation: float
    mean_absolute_error: float
    n: int


def fit_linear(pairs: list[tuple[float, float]]) -> LinearFit:
    """Least squares from engine score to human score.

    The error is reported *after* the fit, on purpose. An engine whose raw
    numbers sit ten points below the humans but track them perfectly is
    calibratable; one that is close on average and uncorrelated is not. Only
    the second is a failure, and reporting raw error would confuse the two.
    """
    n = len(pairs)
    if n < 3:
        return LinearFit(1.0, 0.0, 0.0, 0.0, n)

    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    var_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    if var_x <= 0:
        return LinearFit(1.0, 0.0, 0.0, 0.0, n)

    slope = sum((x - mean_x) * (y - mean_y) for x, y in pairs) / var_x
    intercept = mean_y - slope * mean_x
    mae = sum(abs(y - (slope * x + intercept)) for x, y in pairs) / n
    return LinearFit(slope, intercept, pearson(pairs), mae, n)


def group_bias(residuals_by_group: dict[str, list[float]]) -> float:
    """The spread of mean residual across groups.

    The single most important number in the study. An engine can correlate
    beautifully overall and still sit four points low on every Tamil-L1
    speaker, and aggregate statistics will never show it. This is what makes
    that visible, and it is a hard gate rather than a note.
    """
    means = [sum(v) / len(v) for v in residuals_by_group.values() if v]
    if len(means) < 2:
        return 0.0
    return max(means) - min(means)
