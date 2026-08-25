"""How each format combines what was measured.

The rules that make this faithful rather than decorative:

* a sub-score draws only from the tasks its format counts towards it -- Read
  Aloud must never reach Sentence Mastery, because reading a visible sentence
  demonstrates nothing about producing one;
* a sub-score with too little behind it is named as missing, not quietly
  dropped, because dropping it changes what the overall means without saying
  so;
* and none of it can touch a dimension score. Everything here rearranges
  numbers the frozen pipeline already produced.
"""
from __future__ import annotations

import pytest

from app import evaluation, formats


def response(task_type: str, **scores: float) -> dict:
    return {"task_type": task_type, "scores": scores}


def versant_attempt(**overrides: float) -> list[dict]:
    """A full Versant-style attempt with every task type represented."""
    base = {"pronunciation": 70.0, "accuracy": 70.0, "fluency": 70.0,
            "latency": 70.0, "disfluency": 70.0, "grammar": 70.0,
            "content": 70.0}
    base.update(overrides)
    out: list[dict] = []
    for _ in range(8):
        out.append(response("read_aloud", pronunciation=base["pronunciation"],
                            accuracy=base["accuracy"], fluency=base["fluency"],
                            latency=base["latency"],
                            disfluency=base["disfluency"]))
    for _ in range(8):
        out.append(response("repeat_sentence",
                            pronunciation=base["pronunciation"],
                            accuracy=base["accuracy"], fluency=base["fluency"],
                            latency=base["latency"],
                            disfluency=base["disfluency"]))
    for _ in range(4):
        out.append(response("short_answer", content=base["content"],
                            latency=base["latency"]))
    for _ in range(4):
        out.append(response("sentence_build", pronunciation=base["pronunciation"],
                            accuracy=base["accuracy"], grammar=base["grammar"],
                            fluency=base["fluency"], latency=base["latency"],
                            disfluency=base["disfluency"]))
    out.append(response("story_retell", content=base["content"],
                        grammar=base["grammar"], fluency=base["fluency"],
                        latency=base["latency"], disfluency=base["disfluency"]))
    out.append(response("open_response", grammar=base["grammar"],
                        fluency=base["fluency"], latency=base["latency"],
                        disfluency=base["disfluency"]))
    return out


# --------------------------------------------------------------------------
# Task scoping -- the whole point
# --------------------------------------------------------------------------

def test_read_aloud_never_reaches_sentence_mastery() -> None:
    """The defining property of the mapping. If reading a sentence you can see
    counted towards Sentence Mastery, the sub-score would measure reading."""
    result = evaluation.evaluate("versant_style_speaking_listening", versant_attempt())
    assert result is not None
    mastery = next(s for s in result.subscores if s.label == "Sentence Mastery")
    assert "read_aloud" not in mastery.task_types


def test_a_strong_reader_who_cannot_repeat_scores_badly_on_mastery() -> None:
    """The behavioural version of the rule above, which is what actually
    protects a student from a flattering score."""
    responses = []
    for _ in range(8):
        responses.append(response("read_aloud", pronunciation=80.0,
                                  accuracy=80.0, fluency=80.0,
                                  latency=80.0, disfluency=80.0))
    for _ in range(8):
        responses.append(response("repeat_sentence", pronunciation=80.0,
                                  accuracy=25.0, fluency=80.0,
                                  latency=80.0, disfluency=80.0))
    for _ in range(4):
        responses.append(response("sentence_build", pronunciation=80.0,
                                  accuracy=25.0, grammar=25.0, fluency=80.0,
                                  latency=80.0, disfluency=80.0))
    for _ in range(4):
        responses.append(response("short_answer", content=80.0, latency=80.0))
    responses.append(response("story_retell", content=80.0, grammar=80.0,
                              fluency=80.0, latency=80.0, disfluency=80.0))

    result = evaluation.evaluate("versant_style_speaking_listening", responses)
    assert result is not None
    by_label = {s.label: s.value for s in result.subscores}
    assert by_label["Sentence Mastery"] == pytest.approx(25.0, abs=0.1)
    assert by_label["Pronunciation"] == pytest.approx(80.0, abs=0.1)


def test_active_listening_excludes_reading() -> None:
    """SVAR-style. You cannot demonstrate listening by reading."""
    listening = next(s for s in evaluation.SVAR.subscores
                     if s.label == "Active Listening")
    assert "read_aloud" not in listening.task_types
    assert "repeat_sentence" in listening.task_types


def test_every_subscore_names_the_tasks_it_used() -> None:
    result = evaluation.evaluate("versant_style_speaking_listening", versant_attempt())
    assert result is not None
    for sub in result.subscores:
        assert sub.task_types, f"{sub.label} reports no source tasks"
        assert sub.responses >= evaluation.MIN_RESPONSES_PER_SUBSCORE
        assert sub.means, f"{sub.label} does not say what it means"


# --------------------------------------------------------------------------
# Weighting
# --------------------------------------------------------------------------

def test_versant_weights_sum_to_one() -> None:
    assert sum(s.weight for s in evaluation.VERSANT.subscores) == pytest.approx(1.0)


@pytest.mark.parametrize("model", [evaluation.VERSANT, evaluation.SVAR,
                                   evaluation.SPEECHX])
def test_every_model_weights_sum_to_one(model: evaluation.ScoringModel) -> None:
    assert sum(s.weight for s in model.subscores) == pytest.approx(1.0)


def test_the_overall_follows_the_formats_weighting_not_ours() -> None:
    """A format that weights vocabulary at 30% must produce a different
    overall from our internal composite, which weights content at 7%. If these
    ever agree, the format model is not doing anything."""
    responses = versant_attempt(content=20.0)
    result = evaluation.evaluate("versant_style_speaking_listening", responses)
    assert result is not None

    by_label = {s.label: s for s in result.subscores}
    expected = sum(by_label[k].value * by_label[k].weight for k in by_label)
    expected /= sum(by_label[k].weight for k in by_label)
    assert result.overall == pytest.approx(round(expected, 1))

    # And the weak vocabulary has to have pulled it well below the others.
    assert result.overall < by_label["Pronunciation"].value


def test_unpublished_weightings_are_equal_and_declared() -> None:
    """Inventing a hierarchy we cannot source would be worse than admitting we
    have none."""
    for model in (evaluation.SVAR, evaluation.SPEECHX):
        assert model.weights_published is False
        weights = {s.weight for s in model.subscores}
        assert len(weights) == 1, "unpublished weights must be equal"
    assert evaluation.VERSANT.weights_published is True


# --------------------------------------------------------------------------
# Thin attempts
# --------------------------------------------------------------------------

def test_a_subscore_with_one_response_is_not_reported() -> None:
    """One response wearing a category name is not a measurement of it."""
    responses = [response("story_retell", content=70.0, grammar=70.0,
                          fluency=70.0, latency=70.0, disfluency=70.0)]
    responses += [response("read_aloud", pronunciation=70.0, accuracy=70.0,
                           fluency=70.0, latency=70.0, disfluency=70.0)
                  for _ in range(4)]
    result = evaluation.evaluate("versant_style_speaking_listening", responses)
    assert result is not None
    assert "Vocabulary" in result.missing
    assert "1" in result.missing["Vocabulary"]
    assert all(s.label != "Vocabulary" for s in result.subscores)


def test_missing_subscores_say_what_they_needed() -> None:
    result = evaluation.evaluate("versant_style_speaking_listening", [
        response("read_aloud", pronunciation=70.0, fluency=70.0,
                 latency=70.0, disfluency=70.0) for _ in range(4)
    ])
    assert result is not None
    assert "Vocabulary" in result.missing
    assert "short_answer" in result.missing["Vocabulary"]


def test_no_overall_from_a_single_surviving_subscore() -> None:
    """It would just be that sub-score relabelled."""
    result = evaluation.evaluate("versant_style_speaking_listening", [
        response("read_aloud", pronunciation=70.0) for _ in range(4)
    ])
    assert result is not None
    assert len(result.subscores) < evaluation.MIN_SUBSCORES_FOR_OVERALL
    assert result.overall is None


def test_an_empty_attempt_produces_nothing() -> None:
    result = evaluation.evaluate("versant_style_speaking_listening", [])
    assert result is not None
    assert result.overall is None
    assert result.subscores == ()
    assert result.missing


# --------------------------------------------------------------------------
# Scope
# --------------------------------------------------------------------------

def test_company_rounds_have_no_evaluation_model() -> None:
    """They report an outcome, not sub-scores on a scale."""
    for blueprint in formats.BLUEPRINTS:
        assert evaluation.evaluate(blueprint.code, versant_attempt()) is None


def test_an_authored_profile_has_no_model() -> None:
    assert evaluation.evaluate("something_an_admin_made", versant_attempt()) is None


def test_every_vendor_blueprint_has_a_model() -> None:
    for blueprint in formats.VENDOR_BLUEPRINTS:
        assert blueprint.code in evaluation.MODELS, blueprint.code


def test_models_only_reference_dimensions_something_produces() -> None:
    """A sub-score built from a dimension nothing emits would be permanently
    missing, and the report would blame the attempt for it.

    Checked against ``DIMENSIONS_BY_TASK`` rather than the engine's own
    weights. The engine is no longer the only thing that produces a
    dimension -- comprehension, appropriacy and vocabulary come from the
    router's marking of chosen and typed answers -- and a test that knows
    only about the speech path would reject a sub-score built on a real
    measurement.
    """
    known = {d for dims in evaluation.DIMENSIONS_BY_TASK.values() for d in dims}
    for name, model in evaluation.MODELS.items():
        for sub in model.subscores:
            unknown = set(sub.dimensions) - known
            assert not unknown, f"{name}/{sub.label} references {unknown}"


def test_models_only_reference_task_types_the_runner_serves() -> None:
    """Against the central classification, not a set written out here.

    The list used to be the six speaking types, which is what every task type
    was when it was written.
    """
    from app.sections import SKILL_OF_TASK

    for name, model in evaluation.MODELS.items():
        for sub in model.subscores:
            unknown = sub.task_types - set(SKILL_OF_TASK)
            assert not unknown, f"{name}/{sub.label} references {unknown}"


def test_each_models_tasks_exist_in_its_own_blueprint() -> None:
    """A sub-score drawing on a task the simulation never runs can never be
    reported -- the model and the blueprint have to agree."""
    for code, model in evaluation.MODELS.items():
        available = {s.task_type for s in formats.BY_CODE[code].sections}
        for sub in model.subscores:
            assert sub.task_types & available, (
                f"{code}/{sub.label} draws only on tasks this simulation "
                f"does not contain: {sorted(sub.task_types)}"
            )


def test_the_dimension_table_matches_what_the_engine_emits() -> None:
    """DIMENSIONS_BY_TASK is mirrored, not imported, so it can drift. These
    are the pipeline's own rules about which measures apply to which task."""
    from app.engine.pipeline import (NOT_A_GRAMMAR_SAMPLE,
                                     SCRIPTED_FOR_PRONUNCIATION)
    from app.sections import mode_of

    for task, dims in evaluation.DIMENSIONS_BY_TASK.items():
        spoken = mode_of(task) == "speak"
        if spoken and task in NOT_A_GRAMMAR_SAMPLE:
            assert "grammar" not in dims, f"{task} cannot yield grammar"
        if task not in SCRIPTED_FOR_PRONUNCIATION:
            assert "pronunciation" not in dims, (
                f"{task} has no reference text, so no pronunciation score")
        # Timing applies to anything that was spoken at all -- and only to
        # that. A chosen or typed answer has no speaking rate to measure, and
        # the first version of this loop asserted it of every task type
        # because every task type was spoken when it was written.
        if spoken:
            assert {"fluency", "latency", "disfluency"} <= dims, task
        else:
            assert not ({"fluency", "latency", "disfluency"} & dims), (
                f"{task} is not spoken, so it can produce no timing measure")


def test_every_format_can_actually_report_every_subscore_it_advertises() -> None:
    """The one that caught a real fault.

    SpeechX-style advertised a Grammar sub-score drawn from Short Answer and
    Open Response. Short answers yield no grammar measure, and the blueprint
    had a single open response -- one below the floor for reporting. Grammar
    could never appear, and the report would have told the student their
    attempt was too thin when the format was the thing at fault.
    """
    for code in evaluation.MODELS:
        sections = [(s.task_type, s.item_count)
                    for s in formats.BY_CODE[code].sections]
        problems = evaluation.unreportable(code, sections)
        assert not problems, f"{code}: {problems}"


def test_unreportable_detects_a_format_that_cannot_deliver() -> None:
    """The check has to be able to fail, or it is decoration."""
    # Read Aloud only: no grammar, no content, so most sub-scores are dead.
    problems = evaluation.unreportable("versant_style_speaking_listening",
                                       [("read_aloud", 8)])
    assert "Vocabulary" in problems
    assert "Sentence Mastery" in problems
