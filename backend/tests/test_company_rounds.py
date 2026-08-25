"""Company rounds: the blueprints, the verdict, and the builder.

The verdict is the part worth testing hardest. It is the only place in the
product that turns a number into a claim about what an employer would do, and
an outcome claim is far easier to overread than a score. The rules it has to
keep: never appear without a composite behind it, never appear for a style
that does not report one, and never lose its hedge.
"""
from __future__ import annotations

import pytest

from app import formats
from app.schemas import ProfileRequest, ProfileSectionRequest


# --------------------------------------------------------------------------
# Blueprints
# --------------------------------------------------------------------------

def test_five_company_rounds_are_defined() -> None:
    assert len(formats.BLUEPRINTS) == 5
    assert formats.companies() == ["TCS", "Infosys", "Wipro", "Cognizant", "Accenture"]


def test_every_blueprint_has_sections_and_a_company() -> None:
    for b in formats.BLUEPRINTS:
        assert b.sections, f"{b.code} has no sections"
        assert b.company, f"{b.code} has no company"
        assert b.style == "company_round"
        assert b.what_to_expect, f"{b.code} tells the student nothing"


def test_blueprint_codes_are_unique() -> None:
    codes = [b.code for b in formats.BLUEPRINTS]
    assert len(codes) == len(set(codes))


def test_section_task_types_are_ones_the_engine_can_score() -> None:
    """A blueprint asking for a task type the runner cannot serve is a round
    that silently comes out short -- ``_pick_items`` skips a section with an
    empty pool rather than failing."""
    # Every task type the engine scores (speaking, select and write modes) --
    # the researched rounds include typed/chosen grammar and listening
    # sections, which score in the router rather than the speech engine.
    from app.evaluation import DIMENSIONS_BY_TASK
    known = set(DIMENSIONS_BY_TASK)
    for b in formats.BLUEPRINTS:
        for s in b.sections:
            assert s.task_type in known, f"{b.code}/{s.title}: {s.task_type}"


def test_one_shot_prompts_where_the_student_must_listen() -> None:
    """Anything the student has to hear plays exactly once, never twice."""
    must_hear = {"repeat_sentence", "short_answer", "story_retell"}
    for b in formats.BLUEPRINTS:
        for s in b.sections:
            if s.task_type in must_hear:
                assert s.prompt_plays_allowed == 1, f"{b.code}/{s.title}"


def test_read_aloud_never_plays_a_prompt() -> None:
    """Reading aloud means reading. Playing the sentence first would turn it
    into Repeat Sentence and score something else entirely."""
    for b in formats.BLUEPRINTS:
        for s in b.sections:
            if s.task_type == "read_aloud":
                assert s.prompt_plays_allowed == 0, f"{b.code}/{s.title}"


def test_free_speech_gives_thinking_time() -> None:
    """The researched TCS-family free-speech section is prepared speaking:
    thirty seconds to think, then the clock. (The earlier Just-A-Minute
    section, which deliberately had no preparation, is not part of the
    researched round and was removed with it.)"""
    for code in ("company_round_tcs", "company_round_infosys"):
        blueprint = formats.BY_CODE[code]
        free = next(s for s in blueprint.sections
                    if s.task_type == "open_response")
        assert free.prep_seconds == 30, f"{code}"
        assert free.response_seconds == 60, f"{code}"


# --------------------------------------------------------------------------
# The verdict
# --------------------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [
    (95.0, "Likely to clear"),
    (72.0, "Likely to clear"),   # boundary, inclusive
    (71.9, "Borderline"),
    (60.0, "Borderline"),
    (59.9, "Not yet"),
    (45.0, "Not yet"),
    (44.9, "Well short"),
    (0.0, "Well short"),
])
def test_verdict_bands(score: float, expected: str) -> None:
    out = formats.verdict("company_round", score)
    assert out is not None
    assert out["label"] == expected


def test_no_verdict_without_a_composite() -> None:
    """An attempt too short to compose an overall must not acquire an outcome
    on the way through the presentation layer."""
    assert formats.verdict("company_round", None) is None


def test_no_verdict_for_other_styles() -> None:
    for style in ("diagnostic", "versant_style", "svar_style", "speechx_style", "drill"):
        assert formats.verdict(style, 80.0) is None


def test_verdict_always_carries_its_hedge() -> None:
    for score in (0.0, 50.0, 72.0, 100.0):
        out = formats.verdict("company_round", score)
        assert out is not None
        assert out["estimated"] is True
        assert out["note"] == formats.COMPANY_ROUND_NOTE
        assert "not been checked" in out["note"]


def test_bands_cover_the_whole_range_without_a_gap() -> None:
    """Every score from 0 to 100 gets exactly one verdict."""
    for i in range(0, 1001):
        assert formats.verdict("company_round", i / 10.0) is not None


# --------------------------------------------------------------------------
# Builder request validation
# --------------------------------------------------------------------------

def test_unknown_task_type_is_refused() -> None:
    with pytest.raises(ValueError):
        ProfileSectionRequest(title="X", task_type="interpretive_dance")


def test_unknown_style_is_refused() -> None:
    with pytest.raises(ValueError):
        ProfileRequest(name="X", style="whatever_style")


def test_response_seconds_is_bounded() -> None:
    """A section with a zero-second answer window would record nothing and
    score it, which is worse than refusing the profile."""
    with pytest.raises(ValueError):
        ProfileSectionRequest(title="X", task_type="read_aloud", response_seconds=0)
