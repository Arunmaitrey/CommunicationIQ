"""Phase 1: the two things that looked like features and were not.

`scoring_weights` was a column no endpoint wrote and no scorer read, and
Story Retell reported one number for two unrelated abilities. Both read as
working, which is why each gets tests that fail loudly if they regress.
"""
from __future__ import annotations

import pytest

from app import retell, weighting
from app.engine.pipeline import WEIGHTS

from tests.test_game_and_practice import auth, login


# -- weighting -------------------------------------------------------------

def test_the_mirror_of_the_frozen_weights_has_not_drifted():
    """weighting.py duplicates the engine set deliberately; keep them equal.

    The duplication is so this module survives a re-cut of the frozen path and
    so "engine default" stays a stable reference. A silent divergence would
    make the comparison meaningless.
    """
    assert weighting.ENGINE_WEIGHTS == WEIGHTS


def test_configured_weights_actually_change_the_score():
    """The regression: the column existed and changed nothing."""
    dimensions = {"pronunciation": 40.0, "accuracy": 70.0, "fluency": 65.0,
                  "latency": 60.0, "grammar": 70.0}

    default = weighting.apply(dimensions, profile_weights={},
                              pass_threshold=None, skill_thresholds={},
                              min_dimensions=3)
    pronunciation_heavy = weighting.apply(
        dimensions,
        profile_weights={"pronunciation": 70, "accuracy": 10, "fluency": 10,
                         "grammar": 10},
        pass_threshold=None, skill_thresholds={}, min_dimensions=3)

    assert default.using_engine_default is True
    assert pronunciation_heavy.using_engine_default is False
    assert default.score != pronunciation_heavy.score
    # Weighting hard on the weakest dimension must pull the score down.
    assert pronunciation_heavy.score < default.score


def test_percentages_and_fractions_both_work():
    dimensions = {"fluency": 60.0, "grammar": 60.0, "accuracy": 60.0}
    as_pct = weighting.apply(dimensions,
                             profile_weights={"fluency": 50, "grammar": 30,
                                              "accuracy": 20},
                             pass_threshold=None, skill_thresholds={},
                             min_dimensions=3)
    as_frac = weighting.apply(dimensions,
                              profile_weights={"fluency": 0.5, "grammar": 0.3,
                                               "accuracy": 0.2},
                              pass_threshold=None, skill_thresholds={},
                              min_dimensions=3)
    assert as_pct.score == as_frac.score


def test_an_unmeasured_dimension_is_named_not_counted_as_zero():
    """Treating "we could not measure it" as zero fails the candidate for us."""
    result = weighting.apply(
        {"fluency": 70.0, "grammar": 70.0, "accuracy": 70.0},
        profile_weights={"fluency": 25, "grammar": 25, "accuracy": 25,
                         "content": 25},
        pass_threshold=None, skill_thresholds={}, min_dimensions=3)

    assert result.unmeasured == ["content"]
    # Renormalised over what exists: three 70s is 70, not 52.5.
    assert result.score == 70.0


def test_a_skill_floor_overrides_a_passing_overall():
    """A round that accepts unintelligible speech is not measuring the job."""
    result = weighting.apply(
        {"pronunciation": 30.0, "accuracy": 75.0, "fluency": 75.0,
         "grammar": 75.0},
        profile_weights={}, pass_threshold=55.0,
        skill_thresholds={"pronunciation": 50.0}, min_dimensions=3)

    assert result.score is not None and result.score >= 55.0
    assert result.passed is False
    assert "pronunciation" in result.why


def test_an_unmeasured_floor_is_not_a_failure():
    result = weighting.apply(
        {"fluency": 70.0, "grammar": 70.0, "accuracy": 70.0},
        profile_weights={}, pass_threshold=50.0,
        skill_thresholds={"content": 50.0}, min_dimensions=3)

    check = next(c for c in result.thresholds if c.dimension == "content")
    assert check.met is None, "an unmeasured dimension must not read as failed"
    assert result.passed is True


def test_no_pass_mark_means_no_verdict():
    """Practice does not pass or fail anybody."""
    result = weighting.apply({"fluency": 30.0, "grammar": 30.0, "accuracy": 30.0},
                             profile_weights={}, pass_threshold=None,
                             skill_thresholds={}, min_dimensions=3)
    assert result.passed is None


def test_too_little_measured_is_undecided_not_failed():
    result = weighting.apply({"fluency": 70.0}, profile_weights={},
                             pass_threshold=50.0, skill_thresholds={},
                             min_dimensions=3)
    assert result.score is None
    assert result.passed is None
    assert "undecided" in result.why.lower()


@pytest.mark.parametrize("weights,ok", [
    ({}, True),
    ({"fluency": 50, "grammar": 50}, True),
    ({"fluency": 0.5, "grammar": 0.5}, True),
    ({"nonsense": 100}, False),
    ({"fluency": -10, "grammar": 110}, False),
    ({"fluency": 10, "grammar": 10}, False),          # sums to 20
])
def test_weight_validation(weights, ok):
    assert weighting.weights_are_valid(weights)[0] is ok


# -- story retell ----------------------------------------------------------

def test_retell_reports_two_axes_and_never_one():
    """The brief's own requirement, and the thing that was wrong."""
    result = retell.breakdown({"content": 70.0, "fluency": 40.0,
                               "grammar": 45.0, "disfluency": 40.0})
    assert result.content.score is not None
    assert result.language.score is not None
    assert result.content.score != result.language.score
    # There is deliberately no merged number.
    assert result.combined is None


def test_the_two_failure_modes_are_distinguishable():
    """This is the whole point: they need different practice."""
    remembered_said_badly = retell.breakdown(
        {"content": 75.0, "fluency": 35.0, "grammar": 40.0, "disfluency": 35.0})
    spoke_well_forgot = retell.breakdown(
        {"content": 25.0, "fluency": 75.0, "grammar": 72.0, "disfluency": 74.0})

    assert remembered_said_badly.content.score > remembered_said_badly.language.score
    assert spoke_well_forgot.language.score > spoke_well_forgot.content.score
    # And they are told different things.
    assert remembered_said_badly.note != spoke_well_forgot.note
    assert "memory" in spoke_well_forgot.note.lower()


def test_an_unmeasured_axis_is_none_not_zero():
    result = retell.breakdown({"fluency": 60.0, "grammar": 60.0})
    assert result.content.score is None
    assert "not enough" in result.content.note.lower()


def test_content_parts_admit_what_is_not_measured():
    """Sequence needs ordered rubric points and is not built. Say so."""
    parts = retell.breakdown({"content": 60.0}).parts_measured
    assert parts["sequence"] is False
    assert parts["key facts"] is True


def test_language_dimensions_are_listed_not_inferred():
    """Adding a dimension to the engine must not silently join an axis."""
    assert "content" not in retell.LANGUAGE_DIMENSIONS
    assert set(retell.CONTENT_DIMENSIONS) & set(retell.LANGUAGE_DIMENSIONS) == set()


# -- the builder -----------------------------------------------------------

async def test_an_admin_can_store_weights_and_thresholds(client):
    """End to end: the column stopped being decorative."""
    token = await login(client, "tenant_admin")

    created = await client.post(
        "/api/v1/tenant/profiles", headers=auth(token),
        json={
            "name": "Support round with weights",
            "style": "company_round", "company": "Testco",
            "description": "Weighted towards intelligibility.",
            "estimated_minutes": 12,
            "scoring_weights": {"pronunciation": 40, "accuracy": 30,
                                "fluency": 20, "grammar": 10},
            "pass_threshold": 55.0,
            "skill_thresholds": {"pronunciation": 45.0},
            "target_role": "Customer Support Executive",
            "department": "Operations",
            "difficulty_band": "B2",
            "sections": [{
                "title": "Read Aloud", "task_type": "read_aloud",
                "item_count": 4, "prep_seconds": 5, "response_seconds": 20,
                "prompt_plays_allowed": 0, "allow_replay": False,
            }],
        })
    assert created.status_code in (200, 201), created.text
    body = created.json()

    # Read back through the list, which is the endpoint an admin console
    # actually uses; there is no single-profile GET.
    listed = (await client.get("/api/v1/tenant/profiles",
                               headers=auth(token))).json()
    fetched = next(p for p in listed if p["id"] == body["id"])
    assert fetched["scoring_weights"]["pronunciation"] == 40
    assert fetched["pass_threshold"] == 55.0
    assert fetched["skill_thresholds"]["pronunciation"] == 45.0
    assert fetched["target_role"] == "Customer Support Executive"
    assert fetched["difficulty_band"] == "B2"


async def test_nonsense_weights_are_refused_with_a_reason(client):
    token = await login(client, "tenant_admin")
    refused = await client.post(
        "/api/v1/tenant/profiles", headers=auth(token),
        json={"name": "Bad weights", "style": "company_round",
              "description": "x", "estimated_minutes": 10,
              "scoring_weights": {"telepathy": 100},
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 4, "prep_seconds": 5,
                            "response_seconds": 20,
                            "prompt_plays_allowed": 0, "allow_replay": False}]})
    assert refused.status_code == 422
    assert "telepathy" in refused.text
