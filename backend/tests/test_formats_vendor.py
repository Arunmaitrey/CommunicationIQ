"""Vendor-style formats: the blueprints and the scale they report on.

The scale is the part worth testing hardest. It restates a score under the
name of a commercial test, which is the strongest claim anything in this
product makes, and it rests on a linear mapping that has never been checked
against a real result. The rules: it must track the engine's own range, it
must never appear without a composite behind it, and it must never lose the
sentence that says it is an estimate.
"""
from __future__ import annotations

import pytest

from app import formats
from app.engine.pipeline import SCALE_MAX, SCALE_MIN


VENDOR_CODES = ("versant_style_speaking_listening", "svar_full_simulation", "speechx_style_full")


# --------------------------------------------------------------------------
# The mirrored scale
# --------------------------------------------------------------------------

def test_internal_range_matches_the_engine() -> None:
    """formats.py mirrors the engine's scale rather than importing it, to stay
    off the scoring path. This is what stops the two drifting apart."""
    assert formats.INTERNAL_MIN == SCALE_MIN
    assert formats.INTERNAL_MAX == SCALE_MAX


def test_projection_is_identity_where_the_ranges_agree() -> None:
    """The internal scale was designed 20-80, so a Versant-style presentation
    is the same number. If this ever stops holding, the mapping has acquired
    an unexplained transformation."""
    versant = formats.BY_CODE["versant_style_speaking_listening"].scale
    assert versant is not None
    for value in (20.0, 35.5, 60.0, 72.3, 80.0):
        assert versant.project(value) == pytest.approx(value)


def test_projection_clamps_outside_the_internal_range() -> None:
    versant = formats.BY_CODE["versant_style_speaking_listening"].scale
    assert versant is not None
    assert versant.project(-40.0) == 20.0
    assert versant.project(200.0) == 80.0


def test_only_an_anchored_scale_publishes_a_number() -> None:
    """The heart of it. A number under a vendor's name is only defensible
    where the internal scale was built on that vendor's range -- which is true
    for exactly one format. Anywhere else it would be invented, and because
    our range is narrower it would also inflate: an internal 70 stretched onto
    0-100 reads as 83, and 77.5 reads as 96.
    """
    assert formats.BY_CODE["versant_style_speaking_listening"].scale.anchored is True
    for code in ("svar_full_simulation", "speechx_style_full"):
        scale = formats.BY_CODE[code].scale
        assert scale is not None
        assert scale.anchored is False
        assert scale.project(70.0) is None


def test_an_unanchored_format_still_orders_correctly() -> None:
    """Losing the number must not lose the ranking."""
    scale = formats.BY_CODE["svar_full_simulation"].scale
    assert scale is not None
    assert scale.band_for(25.0) == "Beginning"
    assert scale.band_for(45.0) == "Developing"
    assert scale.band_for(60.0) == "Competent"
    assert scale.band_for(75.0) == "Strong"


def test_an_unanchored_format_explains_the_missing_number() -> None:
    out = formats.presentation("svar_full_simulation", 70.0, DIMENSIONS)
    assert out is not None
    assert out["score"] is None
    assert out["scale_min"] is None and out["scale_max"] is None
    assert out["note"] == formats.UNANCHORED_NOTE
    assert "would be invented" in out["note"]
    assert all(s["score"] is None and s["band"] for s in out["subscores"])


def test_projection_is_monotonic() -> None:
    """A better internal score can never present as a worse one."""
    scale = formats.BY_CODE["versant_style_speaking_listening"].scale
    assert scale is not None
    previous = -1.0
    for step in range(0, 101):
        value = SCALE_MIN + (SCALE_MAX - SCALE_MIN) * step / 100
        current = scale.project(value)
        assert current is not None and current >= previous
        previous = current


# --------------------------------------------------------------------------
# Presentation
# --------------------------------------------------------------------------

DIMENSIONS = {"pronunciation": 70.0, "accuracy": 75.0, "fluency": 60.0,
              "latency": 80.0, "disfluency": 65.0, "grammar": 55.0,
              "content": 50.0}


@pytest.mark.parametrize("code", VENDOR_CODES)
def test_vendor_formats_present_a_band_and_sub_scores(code: str) -> None:
    out = formats.presentation(code, 65.0, DIMENSIONS)
    assert out is not None
    assert out["estimated"] is True
    assert out["band"]
    assert out["note"]
    assert out["subscores"], "a vendor format with no sub-scores says nothing"


def test_an_anchored_format_says_the_number_is_an_estimate() -> None:
    out = formats.presentation("versant_style_speaking_listening", 65.0, DIMENSIONS)
    assert out is not None
    assert out["score"] == pytest.approx(65.0)
    assert out["note"] == formats.ESTIMATED_SCALE_NOTE
    assert "has not been compared" in out["note"]


def test_no_presentation_without_a_composite() -> None:
    for code in VENDOR_CODES:
        assert formats.presentation(code, None, DIMENSIONS) is None


def test_company_rounds_have_no_scale() -> None:
    """They report an outcome instead. Offering both would be two answers to
    the same question."""
    for blueprint in formats.BLUEPRINTS:
        assert blueprint.scale is None
        assert formats.presentation(blueprint.code, 70.0, DIMENSIONS) is None


def test_unknown_code_presents_nothing() -> None:
    assert formats.presentation("something_an_admin_authored", 70.0, DIMENSIONS) is None


def test_subscores_skip_dimensions_that_were_not_measured() -> None:
    """A short attempt measures fewer things. A sub-score built from nothing
    must be absent, not zero -- zero reads as "you scored badly at it"."""
    out = formats.presentation("versant_style_speaking_listening", 65.0,
                               {"pronunciation": 70.0, "fluency": 60.0})
    assert out is not None
    labels = {s["label"] for s in out["subscores"]}
    assert "Pronunciation" in labels
    assert "Fluency" in labels
    assert "Vocabulary" not in labels        # content was not measured
    assert "Sentence Mastery" not in labels  # accuracy and grammar were not


def test_subscores_name_what_they_were_built_from() -> None:
    """The grouping is ours, so the report has to be able to show its working."""
    out = formats.presentation("versant_style_speaking_listening", 65.0, DIMENSIONS)
    assert out is not None
    by_label = {s["label"]: s for s in out["subscores"]}
    assert set(by_label["Fluency"]["from"]) == {"fluency", "latency", "disfluency"}
    assert by_label["Pronunciation"]["from"] == ["pronunciation"]
    assert out["subscore_note"] == formats.SUBSCORE_NOTE


def test_subscore_is_the_mean_of_its_dimensions_projected() -> None:
    scale = formats.BY_CODE["versant_style_speaking_listening"].scale
    assert scale is not None
    out = formats.presentation("versant_style_speaking_listening", 65.0, DIMENSIONS)
    assert out is not None
    fluency = next(s for s in out["subscores"] if s["label"] == "Fluency")
    expected = scale.project((60.0 + 80.0 + 65.0) / 3)
    assert expected is not None
    assert fluency["score"] == pytest.approx(expected)


# --------------------------------------------------------------------------
# Blueprint sanity
# --------------------------------------------------------------------------

def test_all_blueprints_have_unique_codes() -> None:
    codes = [b.code for b in formats.ALL_BLUEPRINTS]
    assert len(codes) == len(set(codes))


def test_every_blueprint_section_is_a_task_type_the_runner_serves() -> None:
    """This used to assert every section was *speaking*, which was a true
    description of a limitation and became a rule that outlived it.

    The runner has had three response modes since Phase 3, and the four
    templates exist precisely because a blueprint can now hold a listening,
    reading or writing section. What still has to hold is the reason the old
    rule existed: a section the runner cannot dispatch is dropped without
    comment, and a candidate gets a shorter test than the one they were shown.
    """
    from app.sections import SKILL_OF_TASK, mode_of

    for b in formats.ALL_BLUEPRINTS:
        for s in b.sections:
            assert s.task_type in SKILL_OF_TASK, (
                f"{b.code}/{s.title}: {s.task_type} is unclassified")
            assert mode_of(s.task_type) in ("speak", "select", "write"), (
                f"{b.code}/{s.title}: no response mode")


def test_formats_that_omit_parts_of_the_real_test_say_so() -> None:
    """Silence about a missing half is the misleading option.

    Conditional now, because it stopped being true of every vendor format:
    SVAR-style contains the listening and vocabulary parts it used to
    disclaim. The rule is the one that always mattered -- a format that leaves
    out a whole skill has to say where to find it.
    """
    from app.sections import skill_of

    for code, blueprint in formats.BY_CODE.items():
        if blueprint.scale is None:      # company rounds report an outcome
            continue
        covered = {skill_of(s.task_type) for s in blueprint.sections}
        if covered == {"speaking"}:
            assert blueprint.not_included, (
                f"{code} is speaking-only and says nothing about the rest")
            # And it points somewhere. A note that names a gap and leaves the
            # student with nowhere to go is only half an answer.
            assert ("Practice" in blueprint.not_included
                    or "4 Skills" in blueprint.not_included), code

    # And the one that still is speaking-only has not quietly lost its note.
    assert formats.BY_CODE["speechx_style_full"].not_included


def test_the_item_bank_is_deeper_than_the_longest_section() -> None:
    """A section asking for more items than exist gets silently truncated.
    Worse, a bank exactly the size of a section serves the same test every
    time, and the retake measures memory.

    Only the spoken banks are checked here, from ``build_item_bank``. The
    quiz and writing banks are checked against the live database by
    ``test_templates.py``, which is the only place their real depth is known
    -- counting them from a seed function would prove the seed agrees with
    itself.
    """
    from app.sections import source_of
    from app.seed import build_item_bank

    have: dict[str, int] = {}
    for item in build_item_bank():
        have[item.task_type] = have.get(item.task_type, 0) + 1

    for b in formats.ALL_BLUEPRINTS:
        for s in b.sections:
            kind, key = source_of(s.task_type)
            if kind != "task":
                continue
            available = have.get(key, 0)
            assert available >= s.item_count, (
                f"{b.code}/{s.title} wants {s.item_count} {key} "
                f"items; the bank has {available}"
            )


def test_no_two_items_read_as_the_same_item() -> None:
    """Two sentences differing only after forty characters are, to a student
    reading both aloud in one sitting, the same question twice.

    This caught a real one: widening the bank reworded four sentences instead
    of replacing them, so both editions were published and an SVAR-style
    attempt served the pair.
    """
    from app.seed import NEAR_DUPLICATE_PREFIX, build_item_bank, _is_reworded

    by_type: dict[str, list[str]] = {}
    for item in build_item_bank():
        text = (item.reference_text or item.prompt_text or "").strip()
        by_type.setdefault(item.task_type, []).append(text)

    for task_type, texts in by_type.items():
        seen: dict[str, str] = {}
        for text in texts:
            key = text.lower()[:NEAR_DUPLICATE_PREFIX]
            assert key not in seen, (
                f"{task_type}: {text!r} and {seen[key]!r} share their opening"
            )
            seen[key] = text

        for a in texts:
            for b in texts:
                assert not _is_reworded(a, b), (
                    f"{task_type}: {b!r} is {a!r} with words inserted"
                )
