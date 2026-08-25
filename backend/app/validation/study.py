"""The validation study: dataset, ratings, and the verdict.

This is the tooling for the question everything else waits on — *does the AI
score intelligibility the way human listeners do?* — and it is deliberately
built so that the answer can come back "no".

The design decisions that matter:

* **Raters are blind to the engine.** A rating file never contains a machine
  score. Anchoring is the classic way a validation study quietly confirms
  whatever the model already said.
* **Every gate is a hard gate.** Aggregate correlation cannot buy its way past
  a group-bias failure. An engine that works well on average and sits four
  points low for one L1 group has failed, and the report says so in those
  words.
* **Rater agreement is checked first.** If the humans do not agree with each
  other, nothing can be concluded about whether the machine agrees with them,
  and every other number in the report is noise.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from app.engine import calibration
from app.validation import statistics as stats

# The rubric. Five points, anchored, and the anchors are about a listener's
# experience rather than a linguistic property — "would a hiring panel follow
# this" is the question the product claims to answer.
RUBRIC = {
    "intelligibility": {
        1: "I could not follow this. I would ask them to repeat most of it.",
        2: "I followed some of it, with effort and some guessing.",
        3: "I followed it, but I had to concentrate.",
        4: "Easy to follow. An occasional word took a moment.",
        5: "Effortless. I would not think about it.",
    },
    "pronunciation": {
        1: "Individual words were often unrecognisable.",
        2: "Several words unclear enough to interrupt me.",
        3: "Mostly clear; a few words needed working out.",
        4: "Clear throughout. Accent present, comprehension unaffected.",
        5: "Consistently crisp and easy to catch.",
    },
    "fluency": {
        1: "Halting. Long pauses; hard to hold the thread.",
        2: "Frequent hesitation that got in the way.",
        3: "Some hesitation, thread intact.",
        4: "Mostly smooth; natural pauses only.",
        5: "Even and unforced throughout.",
    },
    "overall": {
        1: "Not ready for a communication round.",
        2: "Would struggle in a communication round.",
        3: "Borderline. Could go either way on the day.",
        4: "Would pass a communication round.",
        5: "Would do well in a communication round.",
    },
}

DIMENSIONS = list(RUBRIC)

# Human ratings are 1-5; engine scores are 20-80. Everything is compared on
# the engine's scale, so the ratings are mapped up rather than the scores down
# — the engine's resolution is the thing being tested.
def rating_to_scale(rating: float) -> float:
    return 20.0 + (rating - 1.0) * 15.0


@dataclass
class Recording:
    """One recording in the study, with what is known about the speaker."""

    recording_id: str
    speaker_id: str
    l1_language: str
    task_type: str
    reference_text: str = ""
    condition: str = "quiet"        # quiet | noisy | poor_mic
    storage_key: str = ""
    engine_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class Rating:
    recording_id: str
    rater_id: str
    scores: dict[str, int] = field(default_factory=dict)
    note: str = ""


@dataclass
class DimensionResult:
    dimension: str
    n: int = 0
    rater_agreement: float = 0.0
    pearson: float = 0.0
    spearman: float = 0.0
    slope: float = 1.0
    intercept: float = 0.0
    mean_absolute_error: float = 0.0
    l1_group_bias: float = 0.0
    group_means: dict[str, float] = field(default_factory=dict)
    passed: bool = False
    failures: list[str] = field(default_factory=list)


@dataclass
class StudyReport:
    name: str
    recordings: int = 0
    speakers: int = 0
    raters: int = 0
    l1_distribution: dict[str, int] = field(default_factory=dict)
    condition_distribution: dict[str, int] = field(default_factory=dict)
    dimensions: list[DimensionResult] = field(default_factory=list)
    verdict: str = "not run"
    blocking: list[str] = field(default_factory=list)
    generated_at: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"


class Study:
    """A validation run: recordings in, ratings in, verdict out."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.recordings: dict[str, Recording] = {}
        self.ratings: list[Rating] = []

    # -- collection --------------------------------------------------------

    def add_recording(self, recording: Recording) -> None:
        self.recordings[recording.recording_id] = recording

    def add_rating(self, rating: Rating) -> None:
        if rating.recording_id not in self.recordings:
            raise ValueError(f"rating for unknown recording {rating.recording_id}")
        for dimension, value in rating.scores.items():
            if dimension not in RUBRIC:
                raise ValueError(f"unknown rubric dimension {dimension}")
            if not 1 <= value <= 5:
                raise ValueError(f"{dimension} must be 1-5, got {value}")
        self.ratings.append(rating)

    def rating_sheet(self) -> str:
        """A CSV for the raters — deliberately without any machine score.

        Shuffling is the caller's job; what this guarantees is that no column
        in the file can anchor a rater to what the engine already decided.
        """
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["recording_id", "rater_id", *DIMENSIONS, "note"])
        for recording_id in self.recordings:
            writer.writerow([recording_id, "", *["" for _ in DIMENSIONS], ""])
        return buffer.getvalue()

    def load_ratings_csv(self, text: str) -> int:
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
        loaded = 0
        for row in reader:
            scores = {}
            for dimension in DIMENSIONS:
                raw = (row.get(dimension) or "").strip()
                if raw:
                    scores[dimension] = int(float(raw))
            if not scores or not (row.get("rater_id") or "").strip():
                continue
            self.add_rating(Rating(recording_id=row["recording_id"].strip(),
                                   rater_id=row["rater_id"].strip(),
                                   scores=scores,
                                   note=(row.get("note") or "").strip()))
            loaded += 1
        return loaded

    # -- analysis ----------------------------------------------------------

    def analyse(self) -> StudyReport:
        report = StudyReport(
            name=self.name,
            recordings=len(self.recordings),
            speakers=len({r.speaker_id for r in self.recordings.values()}),
            raters=len({r.rater_id for r in self.ratings}),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        for recording in self.recordings.values():
            report.l1_distribution[recording.l1_language] = \
                report.l1_distribution.get(recording.l1_language, 0) + 1
            report.condition_distribution[recording.condition] = \
                report.condition_distribution.get(recording.condition, 0) + 1

        if not self.ratings:
            report.verdict = "not run"
            report.blocking = ["no human ratings collected"]
            return report

        for dimension in DIMENSIONS:
            report.dimensions.append(self._analyse_dimension(dimension))

        agreement_failures = [d.dimension for d in report.dimensions
                              if d.rater_agreement < calibration.MIN_RATER_AGREEMENT]
        if agreement_failures:
            # Everything downstream is measured against the humans. If they do
            # not agree with each other, no statement about the machine can be
            # supported by this data.
            report.verdict = "inconclusive"
            report.blocking = [
                f"raters do not agree on {', '.join(agreement_failures)} "
                f"(ICC below {calibration.MIN_RATER_AGREEMENT}) — the ground "
                f"truth is not usable and nothing else in this report can be "
                f"relied on"
            ]
            return report

        failures = [f"{d.dimension}: {reason}"
                    for d in report.dimensions for reason in d.failures]
        report.blocking = failures
        report.verdict = "pass" if not failures else "fail"
        return report

    def _analyse_dimension(self, dimension: str) -> DimensionResult:
        result = DimensionResult(dimension=dimension)

        by_recording: dict[str, dict[str, int]] = {}
        for rating in self.ratings:
            if dimension in rating.scores:
                by_recording.setdefault(rating.recording_id, {})[rating.rater_id] = \
                    rating.scores[dimension]

        # Agreement is computed only on recordings every rater covered — a
        # ragged matrix would silently become a different statistic.
        raters = sorted({r for scores in by_recording.values() for r in scores})
        complete = [[scores[r] for r in raters]
                    for scores in by_recording.values()
                    if all(r in scores for r in raters)]
        result.rater_agreement = round(stats.icc_two_way_random(complete), 3)

        engine_dimension = _engine_dimension_for(dimension)
        pairs: list[tuple[float, float]] = []
        residual_groups: dict[str, list[float]] = {}

        for recording_id, scores in by_recording.items():
            recording = self.recordings[recording_id]
            engine = recording.engine_scores.get(engine_dimension)
            if engine is None:
                continue
            human = rating_to_scale(sum(scores.values()) / len(scores))
            pairs.append((engine, human))
            residual_groups.setdefault(recording.l1_language, []).append(human - engine)

        result.n = len(pairs)
        if result.n < 10:
            result.failures.append(f"only {result.n} rated recordings with an "
                                   f"engine score for this dimension")
            return result

        fit = stats.fit_linear(pairs)
        result.pearson = round(fit.correlation, 3)
        result.spearman = round(stats.spearman(pairs), 3)
        result.slope = round(fit.slope, 3)
        result.intercept = round(fit.intercept, 2)
        result.mean_absolute_error = round(fit.mean_absolute_error, 2)

        # Residuals after calibration are what a group comparison should use;
        # before it, a constant offset would look like bias against everyone.
        calibrated_residuals = {
            group: [h - (fit.slope * e + fit.intercept)
                    for (e, h), g in zip(pairs, _groups(by_recording, self.recordings))
                    if g == group]
            for group in residual_groups
        }
        result.group_means = {g: round(sum(v) / len(v), 2)
                              for g, v in calibrated_residuals.items() if v}
        result.l1_group_bias = round(stats.group_bias(calibrated_residuals), 2)

        threshold = (calibration.MIN_OVERALL_CORRELATION if dimension == "overall"
                     else calibration.MIN_CORRELATION)
        if result.pearson < threshold:
            result.failures.append(
                f"correlation {result.pearson} is below the {threshold} gate")
        if result.mean_absolute_error > calibration.MAX_MEAN_ABSOLUTE_ERROR:
            result.failures.append(
                f"mean absolute error {result.mean_absolute_error} exceeds "
                f"{calibration.MAX_MEAN_ABSOLUTE_ERROR} points")
        if result.l1_group_bias > calibration.MAX_L1_GROUP_BIAS:
            worst = sorted(result.group_means.items(), key=lambda kv: kv[1])
            result.failures.append(
                f"scores differ by {result.l1_group_bias} points between L1 "
                f"groups ({worst[0][0]} {worst[0][1]:+}, "
                f"{worst[-1][0]} {worst[-1][1]:+}) — this is a fairness "
                f"failure regardless of the aggregate correlation")

        result.passed = not result.failures
        return result

    # -- output ------------------------------------------------------------

    def calibrations(self, report: StudyReport) -> dict[str, calibration.Calibration]:
        """Fits for the dimensions that cleared every gate. Only those."""
        fits: dict[str, calibration.Calibration] = {}
        for result in report.dimensions:
            if not result.passed:
                continue
            fits[_engine_dimension_for(result.dimension)] = calibration.Calibration(
                dimension=_engine_dimension_for(result.dimension),
                slope=result.slope, intercept=result.intercept,
                correlation=result.pearson,
                mean_absolute_error=result.mean_absolute_error,
                n_recordings=result.n, n_raters=report.raters,
                rater_agreement=result.rater_agreement,
                l1_group_bias=result.l1_group_bias,
                fitted_at=datetime.now(timezone.utc), study=self.name,
            )
        return fits

    def save(self, path: Path, report: StudyReport) -> None:
        path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")


def _engine_dimension_for(rubric_dimension: str) -> str:
    return {"intelligibility": "pronunciation", "pronunciation": "pronunciation",
            "fluency": "fluency", "overall": "overall"}[rubric_dimension]


def _groups(by_recording: dict, recordings: dict[str, Recording]) -> list[str]:
    return [recordings[rid].l1_language for rid in by_recording]
