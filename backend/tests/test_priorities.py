"""The practise-next ranking: weakest first, lever pinned, honest evidence."""
from app.priorities import PRACTICE_SURFACE, priorities_for


def test_ranks_weakest_first_and_caps_at_three():
    dims = {"pronunciation": 62, "fluency": 41, "grammar": 55,
            "comprehension": 70, "vocabulary": 47}
    out = priorities_for(dims, scale_max=80)
    assert [p.dimension for p in out] == ["fluency", "vocabulary", "grammar"]
    assert all(p.practice == PRACTICE_SURFACE[p.dimension] for p in out)


def test_the_primary_diagnosis_leads_and_is_the_only_needs_most():
    from app.diagnosis import diagnose
    dims = {"pronunciation": 62, "fluency": 41, "grammar": 55}
    counts = {d: 4 for d in dims}
    primary = diagnose(dims, response_counts=counts)
    out = priorities_for(dims, scale_max=80, response_counts=counts,
                         primary=primary)
    assert out[0].dimension == primary.dimension == "fluency"
    assert [p.verdict for p in out] == ["needs_most", "needs_work", "needs_work"]
    # The old lever sentence asserted something the report did not say.
    assert all("lift your score most" not in p.evidence for p in out)
    assert all(p.advice for p in out)


def test_without_an_identified_primary_nobody_is_needs_most():
    from app.diagnosis import diagnose
    dims = {"pronunciation": 41.0, "fluency": 41.5, "grammar": 70}
    counts = {d: 4 for d in dims}
    primary = diagnose(dims, response_counts=counts)
    assert primary.status == "tied"
    out = priorities_for(dims, scale_max=80, response_counts=counts,
                         primary=primary)
    assert [p.dimension for p in out[:2]] == ["pronunciation", "fluency"]
    assert all(p.verdict == "needs_work" for p in out)


def test_evidence_states_scale_and_answer_count():
    out = priorities_for({"fluency": 34.4}, scale_max=80,
                         response_counts={"fluency": 12})
    assert out[0].evidence.startswith("Measured at 34 of 80 across 12 answers")
    # With no diagnosis passed, nothing is called "your lowest measured
    # area" -- that verdict belongs to the diagnosis alone.
    assert "lowest measured area" not in out[0].evidence


def test_unmeasured_and_unmapped_dimensions_never_become_priorities():
    assert priorities_for({}, scale_max=80) == []
    out = priorities_for({"overall": 50, "fluency": 40}, scale_max=80)
    assert [p.dimension for p in out] == ["fluency"]


def test_every_surface_is_one_that_runs():
    assert set(PRACTICE_SURFACE.values()) == {
        "speaking", "grammar", "vocabulary", "listening"}


def test_every_practice_code_is_a_real_seeded_blueprint():
    """The button must start what it names: every prescribable code exists,
    is drill-style, short, and its sections emit the dimension it trains."""
    from app import formats
    from app.evaluation import DIMENSIONS_BY_TASK
    from app.priorities import PRACTICE_CODE

    for dimension, code in PRACTICE_CODE.items():
        blueprint = formats.BY_CODE.get(code)
        assert blueprint is not None, f"{code} is not a blueprint"
        assert blueprint.style == "drill"
        assert 0 < blueprint.estimated_minutes <= 10, f"{code} is not short"
        emitted = set().union(*(DIMENSIONS_BY_TASK[s.task_type]
                                for s in blueprint.sections))
        assert dimension in emitted, \
            f"{code} never measures {dimension} -- the practice would be fake"


def test_practice_verdicts_refuse_to_oversell():
    """§1/§16/§17: noise is 'level', thin evidence is no verdict at all, and
    a real drop is said plainly -- no fake positivity in any direction."""
    from app.priorities import (PRACTICE_LEVEL_BAND, PRACTICE_MIN_RESPONSES,
                                practice_verdict)
    # The defect that triggered this gate: +0.4 must NOT read as improvement.
    assert practice_verdict(0.4, 10) == "level"
    assert practice_verdict(-0.4, 10) == "level"
    assert practice_verdict(PRACTICE_LEVEL_BAND, 10) == "higher"
    assert practice_verdict(-PRACTICE_LEVEL_BAND, 10) == "lower"
    # Thin measurement: no verdict, whatever the number says.
    assert practice_verdict(30.0, PRACTICE_MIN_RESPONSES - 1) == "insufficient"
    assert practice_verdict(None, 10) == "insufficient"
