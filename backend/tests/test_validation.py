"""The validation harness.

This is the tooling that decides whether the engine ships, so the tests here
are mostly about it being willing to say no: refusing when raters disagree,
failing on group bias even when the aggregate looks good, and never handing
back a calibration for a dimension that did not clear every gate.
"""
from __future__ import annotations

import random

import pytest

from app.engine import calibration
from app.validation import statistics as stats
from app.validation.study import (DIMENSIONS, Rating, Recording, Study,
                                  rating_to_scale)


# ==========================================================================
# Statistics — checked against worked examples, not against themselves
# ==========================================================================

def test_pearson_matches_a_known_answer():
    pairs = [(1, 2), (2, 4), (3, 6), (4, 8)]
    assert stats.pearson(pairs) == pytest.approx(1.0)
    assert stats.pearson([(1, 8), (2, 6), (3, 4), (4, 2)]) == pytest.approx(-1.0)


def test_correlation_of_a_flat_column_is_zero_not_a_crash():
    assert stats.pearson([(1, 5), (2, 5), (3, 5)]) == 0.0
    assert stats.pearson([]) == 0.0


def test_spearman_sees_a_monotonic_relationship_pearson_understates():
    pairs = [(1, 1), (2, 2), (3, 4), (4, 8), (5, 16)]
    assert stats.spearman(pairs) == pytest.approx(1.0)
    assert stats.pearson(pairs) < 1.0


def test_tied_ranks_share_their_average():
    """A rater who only ever used three of five points would otherwise
    distort the coefficient."""
    assert stats.spearman([(1, 3), (2, 3), (3, 3), (4, 5)]) < 1.0


def test_icc_is_high_when_raters_agree_and_low_when_they_do_not():
    agree = [[4, 4, 5], [2, 2, 2], [5, 5, 5], [1, 2, 1], [3, 3, 3], [4, 5, 4]]
    assert stats.icc_two_way_random(agree) > 0.8

    rng = random.Random(5)
    noise = [[rng.randint(1, 5) for _ in range(3)] for _ in range(30)]
    assert stats.icc_two_way_random(noise) < 0.5


def test_icc_counts_a_constant_offset_as_disagreement():
    """Absolute agreement, not consistency. Two raters two points apart do not
    agree about whether a student passes, however well they correlate."""
    offset = [[1, 4], [2, 5], [3, 6], [1, 4], [2, 5], [3, 6]]
    assert stats.icc_two_way_random(offset) < 0.6


def test_a_ragged_rating_matrix_is_refused():
    with pytest.raises(ValueError):
        stats.icc_two_way_random([[1, 2, 3], [1, 2]])


def test_a_linear_fit_recovers_a_planted_mapping():
    pairs = [(x, 0.5 * x + 10) for x in range(20, 80, 3)]
    fit = stats.fit_linear(pairs)
    assert fit.slope == pytest.approx(0.5, abs=0.01)
    assert fit.intercept == pytest.approx(10, abs=0.5)
    assert fit.mean_absolute_error < 0.01


def test_error_is_measured_after_calibration_not_before():
    """An engine sitting ten points low but tracking perfectly is
    calibratable. Reporting raw error would call that a failure."""
    pairs = [(x, x + 10) for x in range(20, 80, 4)]
    fit = stats.fit_linear(pairs)
    assert fit.correlation == pytest.approx(1.0)
    assert fit.mean_absolute_error < 0.01


def test_group_bias_is_the_spread_between_groups():
    assert stats.group_bias({"telugu": [1.0, 1.0], "hindi": [-2.0, -2.0]}) == 3.0
    assert stats.group_bias({"telugu": [1.0]}) == 0.0


# ==========================================================================
# The study
# ==========================================================================

L1_GROUPS = ["telugu", "hindi", "tamil"]


def build(n_speakers: int = 30, n_raters: int = 4, noise: float = 3.0,
          bias: dict[str, float] | None = None, rater_noise: float = 0.3,
          seed: int = 3) -> Study:
    """A study where the engine tracks the humans, with controllable flaws."""
    rng = random.Random(seed)
    study = Study("simulated")
    bias = bias or {}

    truth: dict[str, float] = {}
    for i in range(n_speakers):
        l1 = L1_GROUPS[i % len(L1_GROUPS)]
        for task in ("read_aloud", "repeat_sentence"):
            rid = f"r{i}_{task}"
            human_truth = rng.uniform(25, 75)
            truth[rid] = human_truth
            engine = human_truth - bias.get(l1, 0.0) + rng.gauss(0, noise)
            study.add_recording(Recording(
                recording_id=rid, speaker_id=f"sp{i}", l1_language=l1,
                task_type=task,
                engine_scores={"pronunciation": engine, "fluency": engine,
                               "overall": engine},
            ))

    for rater in range(n_raters):
        for rid, human_truth in truth.items():
            rating = max(1, min(5, round((human_truth - 20) / 15 + 1
                                         + rng.gauss(0, rater_noise))))
            study.add_rating(Rating(recording_id=rid, rater_id=f"rater{rater}",
                                    scores={d: rating for d in DIMENSIONS}))
    return study


def test_a_sound_study_passes_and_produces_calibrations():
    report = (study := build()).analyse()
    assert report.verdict == "pass", report.blocking
    assert all(d.rater_agreement >= calibration.MIN_RATER_AGREEMENT
               for d in report.dimensions)

    fits = study.calibrations(report)
    assert "pronunciation" in fits
    assert fits["pronunciation"].usable


def test_disagreeing_raters_make_the_study_inconclusive_not_failed():
    """If the humans do not agree with each other, nothing can be concluded
    about the machine — and that is a different answer from 'the machine is
    wrong'."""
    report = build(rater_noise=3.0, seed=11).analyse()
    assert report.verdict == "inconclusive"
    assert any("do not agree" in reason for reason in report.blocking)


def test_group_bias_fails_the_study_even_when_the_correlation_is_strong():
    """The most important test here. An engine can correlate beautifully
    overall and still sit five points low on every Tamil speaker."""
    report = build(noise=1.0, bias={"tamil": 8.0}).analyse()

    assert report.verdict == "fail"
    pronunciation = next(d for d in report.dimensions
                         if d.dimension == "pronunciation")
    assert pronunciation.pearson > 0.9, "the aggregate correlation is fine"
    assert pronunciation.l1_group_bias > calibration.MAX_L1_GROUP_BIAS
    assert any("fairness failure" in reason for reason in report.blocking)


def test_a_weakly_correlated_engine_fails():
    report = build(noise=30.0, seed=23).analyse()
    assert report.verdict == "fail"


def test_no_calibration_is_produced_for_a_dimension_that_failed():
    study = build(noise=1.0, bias={"tamil": 8.0})
    report = study.analyse()
    assert study.calibrations(report) == {}


def test_a_study_with_no_ratings_says_it_has_not_run():
    study = Study("empty")
    study.add_recording(Recording(recording_id="r1", speaker_id="s1",
                                  l1_language="telugu", task_type="read_aloud"))
    report = study.analyse()
    assert report.verdict == "not run"


def test_too_few_rated_recordings_is_a_failure_not_a_pass():
    study = Study("thin")
    for i in range(4):
        study.add_recording(Recording(recording_id=f"r{i}", speaker_id=f"s{i}",
                                      l1_language="telugu", task_type="read_aloud",
                                      engine_scores={"pronunciation": 50.0 + i}))
        for rater in range(3):
            study.add_rating(Rating(recording_id=f"r{i}", rater_id=f"rater{rater}",
                                    scores={d: 3 for d in DIMENSIONS}))
    report = study.analyse()
    assert report.verdict != "pass"


# -- the rating sheet ------------------------------------------------------

def test_the_rating_sheet_never_contains_a_machine_score():
    """A rater who can see the engine's answer is not an independent check,
    and anchoring is how a validation study quietly confirms itself."""
    study = build(n_speakers=3)
    sheet = study.rating_sheet()

    assert "pronunciation" in sheet.splitlines()[0]   # the column to fill in
    for recording in study.recordings.values():
        for score in recording.engine_scores.values():
            assert f"{score:.1f}" not in sheet
    assert "engine" not in sheet.lower()


def test_ratings_round_trip_through_csv():
    study = build(n_speakers=3, n_raters=1)
    original = len(study.ratings)

    rows = ["recording_id,rater_id," + ",".join(DIMENSIONS) + ",note"]
    for rid in list(study.recordings)[:2]:
        rows.append(f"{rid},new_rater," + ",".join("4" for _ in DIMENSIONS) + ",fine")
    loaded = study.load_ratings_csv("\n".join(rows))

    assert loaded == 2
    assert len(study.ratings) == original + 2


def test_a_rating_outside_the_scale_is_refused():
    study = build(n_speakers=2, n_raters=1)
    rid = next(iter(study.recordings))
    with pytest.raises(ValueError):
        study.add_rating(Rating(recording_id=rid, rater_id="x",
                                scores={"overall": 9}))
    with pytest.raises(ValueError):
        study.add_rating(Rating(recording_id="nope", rater_id="x",
                                scores={"overall": 3}))


def test_the_rubric_maps_onto_the_engine_scale():
    assert rating_to_scale(1) == 20.0
    assert rating_to_scale(5) == 80.0
    assert rating_to_scale(3) == 50.0


# ==========================================================================
# Calibration state
# ==========================================================================

def test_nothing_is_calibrated_by_default():
    """The honest starting state, and the one the product ships in."""
    calibration.reset()
    state = calibration.current()
    assert state.any_calibrated is False
    assert "not yet checked against human listeners" in state.note_for("pronunciation").lower()


def test_a_fit_that_misses_a_gate_is_not_usable():
    poor = calibration.Calibration(dimension="pronunciation", correlation=0.4,
                                   rater_agreement=0.8, mean_absolute_error=5,
                                   l1_group_bias=1.0)
    assert poor.usable is False

    biased = calibration.Calibration(dimension="pronunciation", correlation=0.8,
                                     rater_agreement=0.8, mean_absolute_error=5,
                                     l1_group_bias=6.0)
    assert biased.usable is False


def test_installing_a_failing_fit_does_nothing():
    calibration.reset()
    calibration.install({"pronunciation": calibration.Calibration(
        dimension="pronunciation", correlation=0.2, rater_agreement=0.9)})
    assert calibration.current().any_calibrated is False
    calibration.reset()


# ==========================================================================
# The frozen baseline
# ==========================================================================

def test_a_fresh_freeze_reports_no_drift(tmp_path, monkeypatch):
    from app.engine import freeze

    monkeypatch.setattr(freeze, "FREEZE_DIR", tmp_path)
    baseline = freeze.freeze("study-under-test")

    assert baseline.engine_hash
    assert len(baseline.files) == len(freeze.SCORING_PATH)
    assert freeze.drift("study-under-test") == []
    assert freeze.matches("study-under-test")


def test_changing_a_scoring_constant_is_detected(tmp_path, monkeypatch):
    """The failure this exists to stop: a threshold nudged mid-study, then a
    correlation reported as though it described the engine that produced the
    data."""
    from app.engine import freeze

    monkeypatch.setattr(freeze, "FREEZE_DIR", tmp_path)
    freeze.freeze("study-under-test")

    target = freeze.BACKEND_ROOT / "app/engine/providers/tier0/fluency.py"
    original = target.read_text(encoding="utf-8")
    try:
        target.write_text(original.replace("RATE_FLOOR = 2.6", "RATE_FLOOR = 2.9"),
                          encoding="utf-8")
        changes = freeze.drift("study-under-test")
        assert changes
        assert any("tier0/fluency.py" in line for line in changes)
        assert not freeze.matches("study-under-test")
    finally:
        target.write_text(original, encoding="utf-8")

    assert freeze.drift("study-under-test") == []


def test_swapping_the_model_is_drift_even_with_identical_code(tmp_path, monkeypatch):
    """Weights matter as much as the code around them — base.en produces
    different transcripts and therefore different scores."""
    from app.config import settings
    from app.engine import freeze

    monkeypatch.setattr(freeze, "FREEZE_DIR", tmp_path)
    freeze.freeze("study-under-test")

    monkeypatch.setattr(settings, "whisper_model", "base.en")
    changes = freeze.drift("study-under-test")
    assert any("model asr" in line for line in changes)


def test_an_unfrozen_study_reports_that_nothing_was_frozen(tmp_path, monkeypatch):
    from app.engine import freeze

    monkeypatch.setattr(freeze, "FREEZE_DIR", tmp_path)
    changes = freeze.drift("never-frozen")
    assert changes and "nothing was frozen" in changes[0]


def test_the_scoring_path_covers_every_active_provider():
    """A provider missing from the list can drift through an entire study
    unnoticed, so adding one is part of writing it."""
    from app.engine import freeze

    providers = sorted(
        str(p.relative_to(freeze.BACKEND_ROOT)).replace("\\", "/")
        for p in (freeze.BACKEND_ROOT / "app/engine/providers").rglob("*.py")
        if p.name != "__init__.py" and "tier2" not in p.parts
    )
    missing = [p for p in providers if p not in freeze.SCORING_PATH]
    assert not missing, f"providers absent from the frozen scoring path: {missing}"
