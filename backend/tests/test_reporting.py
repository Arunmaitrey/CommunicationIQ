"""The report, beyond the numbers.

Pure functions first — everything in ``app/reporting.py`` takes dictionaries
and returns dataclasses, so the interesting cases (nothing scored, everything
level, one measure only) are ordinary assertions rather than fixtures.

The property running through all of it: this module rearranges measurements
and never makes one. A test asserts its mirrored weights match the frozen
engine's, because a drift there would silently change which recommendation
comes first.
"""
from __future__ import annotations

from app import reporting

from tests.test_game_and_practice import auth, login

BALANCED = {"pronunciation": 55.0, "accuracy": 55.0, "fluency": 55.0,
            "grammar": 55.0, "content": 55.0}
UNEVEN = {"pronunciation": 62.0, "accuracy": 48.0, "fluency": 58.0,
          "grammar": 44.0, "content": 60.0}


def test_the_mirrored_weights_match_the_engine() -> None:
    """Duplicated deliberately so this module works if the frozen set is
    re-cut. Drift would reorder the recommendations without changing a
    number, which is the kind of wrong nobody notices."""
    from app.engine.pipeline import WEIGHTS

    assert reporting.WEIGHTS == WEIGHTS


# -- strengths and weaknesses ------------------------------------------------

def test_a_report_says_what_went_well_as_well_as_what_did_not() -> None:
    """The result gave one weakness and nothing else, every time. Somebody
    reading that after each attempt learns that practising produces
    criticism."""
    strong, weak = reporting.highlights(UNEVEN)

    assert [h.dimension for h in strong] == ["pronunciation", "content", "fluency"]
    assert [h.dimension for h in weak] == ["grammar", "accuracy"]
    # Ordered by how far from their own average, most notable first.
    assert strong[0].delta > strong[-1].delta
    assert weak[0].delta < weak[-1].delta


def test_level_measures_produce_neither() -> None:
    """Inventing a strength out of rounding teaches a student to distrust the
    whole report."""
    strong, weak = reporting.highlights(BALANCED)
    assert strong == []
    assert weak == []


def test_one_measure_is_not_compared_with_itself() -> None:
    assert reporting.highlights({"fluency": 60.0}) == ([], [])
    assert reporting.highlights({}) == ([], [])


def test_a_strength_is_measured_against_the_student_not_a_cohort() -> None:
    """This product has no population norms. "Ahead of your own average" needs
    none; "good" would be a claim about people we have never measured."""
    # Every dimension low, but one clearly ahead of the rest.
    strong, _ = reporting.highlights(
        {"grammar": 24.0, "fluency": 22.0, "accuracy": 34.0})
    assert [h.dimension for h in strong] == ["accuracy"]


# -- recommendations ---------------------------------------------------------

def test_recommendations_are_a_ranked_set_not_a_single_instruction() -> None:
    picks = reporting.recommendations(UNEVEN)

    assert len(picks) >= 2
    assert picks == sorted(picks, key=lambda r: r.predicted_gain, reverse=True)
    assert all(r.advice for r in picks), "a recommendation with no action"


def test_the_gain_is_computed_rather_than_asserted() -> None:
    """What the overall would become if this matched their own best. The same
    arithmetic the frozen `biggest_lever` uses, and checkable by hand."""
    picks = reporting.recommendations(UNEVEN)
    first = picks[0]

    before = reporting._weighted_mean(UNEVEN)
    after = reporting._weighted_mean({**UNEVEN, first.dimension: first.target})
    assert first.predicted_gain == round(after - before, 1)


def test_nothing_is_recommended_that_would_change_nothing() -> None:
    """A suggestion that moves the number by nothing still costs a week of
    somebody's practice."""
    assert reporting.recommendations(BALANCED) == []


def test_the_set_is_capped_so_it_stays_a_plan() -> None:
    """Seven recommendations is the chart, retyped."""
    spread = {"pronunciation": 70.0, "accuracy": 40.0, "fluency": 42.0,
              "latency": 44.0, "disfluency": 46.0, "grammar": 48.0,
              "content": 50.0}
    assert len(reporting.recommendations(spread)) == reporting.MAX_LEVERS


def test_only_dimensions_the_overall_is_built_from_are_recommended() -> None:
    """Recommending a change to something the composite ignores would predict
    a gain that cannot happen."""
    with_extras = {**UNEVEN, "comprehension": 30.0, "vocabulary": 28.0}
    picked = {r.dimension for r in reporting.recommendations(with_extras)}
    assert "comprehension" not in picked
    assert "vocabulary" not in picked


# -- the plain summary -------------------------------------------------------

def test_the_summary_leads_with_language_not_a_number() -> None:
    from app.diagnosis import diagnose
    counts = {d: 4 for d in UNEVEN}
    text = reporting.summary(55.2, UNEVEN, {"speaking": 55.2, "listening": 61.0},
                             primary=diagnose(UNEVEN, response_counts=counts))

    assert text.startswith("You scored")
    assert "out of 80" in text
    # Says what to do, in words a student uses.
    assert "worth working on first" in text
    # And no internal vocabulary.
    for jargon in ("dimension", "composite", "rollup", "IRT", "provider"):
        assert jargon not in text


def test_the_summary_names_the_stronger_skill_when_there_is_one() -> None:
    text = reporting.summary(55.0, UNEVEN,
                             {"speaking": 50.0, "listening": 65.0})
    assert "listening is ahead of your speaking" in text


def test_a_narrow_skill_gap_is_not_reported_as_a_difference() -> None:
    text = reporting.summary(55.0, UNEVEN,
                             {"speaking": 55.0, "listening": 56.0})
    assert "ahead of" not in text


def test_an_unscored_attempt_says_so_instead_of_leading_with_a_number() -> None:
    """The failure this whole product is careful about: a blank score with no
    explanation reads as a broken app rather than an incomplete install."""
    text = reporting.summary(None, {}, {},
                             {"pronunciation": "no model on this server"})

    assert "could not be given an overall score" in text
    assert "left out rather than guessed at" in text
    assert "recordings are kept" in text


def test_a_level_attempt_is_told_there_is_no_single_weak_spot() -> None:
    from app.diagnosis import diagnose
    counts = {d: 4 for d in BALANCED}
    text = reporting.summary(55.0, BALANCED,
                             primary=diagnose(BALANCED, response_counts=counts))
    assert "no single weak spot" in text
    assert "Nothing clearly stands out yet" in text


def test_the_summary_never_chooses_without_a_diagnosis() -> None:
    """The action sentence comes from the diagnosis object or not at all.
    Given none (a practice result, for instance) the summary makes no
    "work on this first" claim -- it used to pick the largest weighted
    gain on its own, which is how one page came to name two areas."""
    text = reporting.summary(55.2, UNEVEN)
    assert "worth working on first" not in text
    assert "Nothing clearly stands out" not in text


# -- evidence ----------------------------------------------------------------

def test_evidence_is_grouped_by_the_measure_it_produced() -> None:
    rows = [
        {"response_id": "a", "position": 1, "task_type": "read_aloud",
         "scores": {"fluency": 58.0, "pronunciation": 62.0},
         "words_per_minute": 118.0, "pauses": [{"ms": 900}],
         "word_errors": [{"word": "schedule"}]},
        {"response_id": "b", "position": 2, "task_type": "open_response",
         "scores": {"grammar": 44.0}, "transcript": "i has three year",
         "grammar_errors": [{"rule": "subject-verb"}]},
    ]
    index = reporting.evidence_index(rows)

    assert set(index) == {"fluency", "pronunciation", "grammar"}
    assert index["fluency"][0]["words_per_minute"] == 118.0
    assert index["grammar"][0]["transcript"] == "i has three year"
    # Only what belongs to that measure: a pause count is not evidence of
    # grammar, and showing it there implies a link that is not real.
    assert "words_per_minute" not in index["grammar"][0]


def test_a_measure_with_no_evidence_is_absent_rather_than_empty() -> None:
    """An empty panel reads as a system that lost the evidence, which is worse
    than one saying the measure was not taken."""
    index = reporting.evidence_index(
        [{"response_id": "a", "position": 1, "task_type": "read_aloud",
          "scores": {"fluency": 58.0}}])
    assert "pronunciation" not in index
    assert "fluency" in index


def test_a_zero_is_evidence_and_an_empty_list_is_not() -> None:
    """Nought pauses is a measurement worth showing. An empty list is an
    absence."""
    index = reporting.evidence_index(
        [{"response_id": "a", "position": 1, "task_type": "read_aloud",
          "scores": {"fluency": 58.0, "latency": 60.0},
          "onset_ms": 0, "pauses": []}])
    assert index["latency"][0]["onset_ms"] == 0
    assert "pauses" not in index["fluency"][0]


def test_every_scored_dimension_has_a_declared_evidence_source() -> None:
    """A dimension added later with no entry shows an empty panel forever, and
    nothing fails. That is the pattern this codebase keeps catching."""
    from app.evaluation import DIMENSIONS_BY_TASK

    produced = {d for dims in DIMENSIONS_BY_TASK.values() for d in dims}
    missing = sorted(produced - set(reporting.EVIDENCE_FOR))
    assert not missing, f"no evidence declared for {missing}"


# -- through the API ---------------------------------------------------------

async def test_the_result_carries_a_summary_and_a_plan(client):
    from tests.test_sections import _mixed_profile

    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Reporting round", [
        {"title": "Reading", "task_type": "reading_comprehension",
         "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    for item in payload["items"]:
        await client.post(
            f"/api/v1/student/attempts/{payload['attempt_id']}/responses/"
            f"{item['response_id']}/answer",
            headers=auth(student), json={"selected_index": 0})

    result = (await client.post(
        f"/api/v1/student/attempts/{payload['attempt_id']}/submit",
        headers=auth(student), json={})).json()

    assert result["summary"], "the report opens with no plain summary"
    assert isinstance(result["strengths"], list)
    assert isinstance(result["weaknesses"], list)
    assert isinstance(result["recommendations"], list)
    assert isinstance(result["evidence"], dict)


async def test_a_result_exports_as_a_spreadsheet(client):
    """Long format, one row per measurement. A wide row stops working the
    moment an attempt produces fewer dimensions -- which every attempt on a
    server without speech models does."""
    import csv
    import io as _io

    from tests.test_sections import _mixed_profile

    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Export round", [
        {"title": "Reading", "task_type": "reading_comprehension",
         "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]
    for item in payload["items"]:
        await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/answer",
            headers=auth(student), json={"selected_index": 0})
    await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                      headers=auth(student), json={})

    export = await client.get(
        f"/api/v1/student/attempts/{attempt_id}/export.csv",
        headers=auth(student))
    assert export.status_code == 200, export.text
    assert "text/csv" in export.headers["content-type"]
    assert "attachment" in export.headers["content-disposition"]

    rows = list(csv.reader(_io.StringIO(export.text)))
    assert rows[0] == ["section", "item", "task_type", "measure", "value",
                       "confidence", "note"]
    measures = {r[3] for r in rows[1:]}
    assert "overall" in measures
    assert any(m.startswith("skill:") for m in measures)
    assert "section score" in measures


async def test_an_export_belongs_to_its_own_student(client):
    """A result is personal. Guessing an attempt id must not hand somebody
    else's recording metrics over."""
    from tests.test_sections import _mixed_profile

    admin = await login(client, "tenant_admin")
    profile_id = await _mixed_profile(client, admin, "Private export", [
        # Three, not two: reading questions come a whole passage at a time and
        # no combination of passages reaches exactly two, so the publish guard
        # correctly refuses -- which is the guard working, not a bug.
        {"title": "Reading", "task_type": "reading_comprehension",
         "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
         "prompt_plays_allowed": 0, "allow_replay": False}])

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    other = await login(client, "trainer")
    refused = await client.get(
        f"/api/v1/student/attempts/{payload['attempt_id']}/export.csv",
        headers=auth(other))
    assert refused.status_code in (403, 404)


async def test_the_evidence_a_dimension_names_actually_arrives(client):
    """The gap this test was written to catch, and did.

    `EVIDENCE_FOR` names `grammar_errors` and `word_errors` behind the grammar
    and pronunciation scores. Both had been stored on FeatureRecord since M2
    and neither was in the response payload, so the panel would have shown a
    grammar score with nothing underneath it -- an evidence panel with no
    evidence, which is worse than none.
    """
    from app.schemas import ResponseMetrics

    fields = set(ResponseMetrics.model_fields)
    named = {field for fields_ in reporting.EVIDENCE_FOR.values()
             for field in fields_}
    missing = sorted(named - fields)
    assert not missing, (
        f"the evidence panel promises {missing}, which no response carries")


def test_every_dimension_the_engine_scores_has_advice():
    """No scored dimension may reach a student with a blank recommendation.

    Keyed off the engine's own weights rather than a list written here, so
    adding a dimension to the pipeline and forgetting the advice fails at this
    line instead of shipping a card with an empty body.
    """
    from app.engine.pipeline import WEIGHTS

    missing = sorted(d for d in WEIGHTS if not reporting.ADVICE.get(d, "").strip())
    assert not missing, f"scored dimensions with no practice advice: {missing}"


def test_every_dimension_a_task_can_produce_has_advice():
    """The same claim from the other direction.

    ``WEIGHTS`` is what the overall score is built from. ``DIMENSIONS_BY_TASK``
    is what an individual section can report, and it is the wider set -- a
    dimension can be shown per-section without carrying weight overall.
    """
    from app.evaluation import DIMENSIONS_BY_TASK

    producible = {d for dims in DIMENSIONS_BY_TASK.values() for d in dims}
    missing = sorted(d for d in producible
                     if not reporting.ADVICE.get(d, "").strip())
    assert not missing, f"reportable dimensions with no practice advice: {missing}"


def test_no_advice_names_a_dimension_that_does_not_exist():
    """The other direction again: advice for something nothing scores is dead
    text, and dead text is how a table drifts out of step with the engine."""
    from app.evaluation import DIMENSIONS_BY_TASK
    from app.engine.pipeline import WEIGHTS

    real = set(WEIGHTS) | {d for dims in DIMENSIONS_BY_TASK.values() for d in dims}
    orphans = sorted(set(reporting.ADVICE) - real)
    assert not orphans, f"advice for dimensions nothing produces: {orphans}"


def test_the_advice_is_something_a_student_could_actually_do():
    """Quality, not just presence.

    Advice that restates the score ("improve your fluency") is what an empty
    string looks like once somebody notices empty strings are checked for. The
    checks below are crude on purpose -- they cannot judge whether advice is
    good, only rule out the specific failures that would be embarrassing.
    """
    for dimension, text in reporting.ADVICE.items():
        assert text == text.strip(), f"{dimension}: stray whitespace"
        assert text.endswith((".", "'.", '".')), (
            f"{dimension}: does not end as a sentence -- {text!r}")
        assert 60 <= len(text) <= 400, (
            f"{dimension}: {len(text)} characters, which is either too thin to "
            f"act on or too long to read on a result screen")
        assert "TODO" not in text and "TBD" not in text, f"{dimension}: placeholder"

        # It has to tell them to do something, not tell them what they are.
        lowered = text.lower()
        assert f"improve your {dimension}" not in lowered, (
            f"{dimension}: restates the score instead of giving an action")
        assert not lowered.startswith("your "), (
            f"{dimension}: opens by describing them rather than by an action")


def test_a_dimension_with_no_advice_says_so_rather_than_showing_a_blank():
    """The guard behind the tests above.

    If a dimension ever slips through, the student gets a sentence explaining
    the gap -- not a heading, a predicted gain, and white space.
    """
    written = reporting._advice_for("something_nobody_wrote_advice_for")
    assert written.strip(), "an unknown dimension produced an empty card"
    assert "trainer" in written.lower(), (
        "the fallback should point somewhere, not just apologise")


async def test_the_result_payload_carries_the_skill_rollup(client):
    """The rollup is computed on every attempt. It has to arrive.

    It did not, for a while, in the way that is hardest to notice: the server
    returned `sections` and `skills`, the client's type declared neither, and
    no screen drew them. Everything was correct and nobody saw it. This
    asserts the payload, which is the half of that seam a backend test can
    hold; the client type is held by its own compile.
    """
    from tests.test_game_and_practice import auth, login

    admin = await login(client, "tenant_admin")
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Rollup round", "style": "company_round",
              "company": "Testco", "description": "x", "estimated_minutes": 10,
              "sections": [
                  {"title": "Speaking", "task_type": "read_aloud",
                   "item_count": 1, "prep_seconds": 0, "response_seconds": 20,
                   "prompt_plays_allowed": 0, "allow_replay": False,
                   "weight": 2.0},
                  {"title": "Reading", "task_type": "reading_comprehension",
                   "item_count": 3, "prep_seconds": 0, "response_seconds": 0,
                   "prompt_plays_allowed": 0, "allow_replay": False}]})).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": created["id"], "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]
    await client.post(f"/api/v1/student/attempts/{attempt_id}/env-check",
                      headers=auth(student),
                      json={"mic_ok": True, "playback_ok": True,
                            "headphones": True, "noise_dbfs": -60.0,
                            "input_peak_dbfs": -20.0, "device_label": "t",
                            "user_agent": "t"})

    # Answer the reading questions so at least one skill scores.
    for item in payload["items"]:
        if item["response_mode"] == "select":
            await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/"
                f"{item['response_id']}/answer",
                headers=auth(student), json={"selected_index": 0})

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(student), json={})).json()

    assert result["sections"], "no per-section results in the payload"
    assert result["skills"], "no skill rollup in the payload"

    by_title = {s["title"]: s for s in result["sections"]}
    assert by_title["Speaking"]["weight"] == 2.0, (
        "the configured weight did not survive to the report -- which is where "
        "somebody would look to find out why a score is what it is")
    assert by_title["Reading"]["weight"] == 1.0

    # And the skills are the ones the sections actually carry, not a fixed
    # four with two of them empty.
    assert {s["skill"] for s in result["skills"]} == {"speaking", "reading"}
    reading = next(s for s in result["skills"] if s["skill"] == "reading")
    assert reading["score"] is not None, "the answered section produced nothing"


def test_the_cefr_band_never_travels_without_its_caveat():
    """A band on a screen becomes a certificate the moment somebody
    screenshots it, so the disclaimer is part of the payload rather than
    something each client is trusted to remember."""
    for score in (25.0, 45.0, 55.0, 70.0, 79.0):
        band = reporting.cefr(score)
        assert band is not None
        assert band.level and band.descriptor
        assert band.caveat, f"{band.level} arrived with nothing attached"
        assert "not a CEFR result" in band.caveat


def test_an_unscored_attempt_gets_no_cefr_level_rather_than_the_lowest():
    """A1 for an engine failure is an accusation. An attempt that could not be
    scored has demonstrated nothing, which is not the same as demonstrating
    the least."""
    assert reporting.cefr(None) is None


def test_the_cefr_cuts_agree_with_the_bands_the_report_already_publishes():
    """Two ladders on one screen that disagree is worse than one ladder.

    The CEFR boundaries are deliberately the same numbers as `BANDS`, so a
    report can never say "close, with work to do" beside a level that implies
    otherwise. Asserted rather than trusted to two tables staying in step.
    """
    band_edges = {edge for edge, _ in reporting.BANDS}
    cefr_edges = {edge for edge, _, _ in reporting.CEFR_BANDS}
    assert band_edges == cefr_edges, (
        f"the two ladders cut at different places: {band_edges ^ cefr_edges}")


def test_the_cefr_band_rises_with_the_score():
    levels = [reporting.cefr(s).level for s in (10.0, 40.0, 55.0, 70.0, 78.0)]
    assert levels == ["A1", "A2", "B1", "B2", "C1"]


def test_a_written_attempt_is_not_told_its_recordings_are_kept():
    """The reassurance has to be true.

    An assessment can now be entirely reading and writing. Telling somebody
    their recordings are safe when they never made one reads as a report about
    somebody else's attempt -- and the copy was written when speaking was the
    only thing here, which is the same root as every other fault found in this
    pass over the product.
    """
    spoken = reporting.summary(None, {}, has_audio=True)
    written = reporting.summary(None, {}, has_audio=False)

    assert "recordings" in spoken
    assert "recordings" not in written, written
    assert "answers are kept" in written, written


def test_the_same_holds_when_there_is_a_reason_the_score_is_missing():
    """The other branch of the same sentence, which is easy to fix once and
    then leave broken in the case that actually reaches most people."""
    reason = {"pronunciation": "No microphone input was detected."}
    written = reporting.summary(None, {}, unscored=reason, has_audio=False)
    assert "recordings" not in written, written


def test_a_spoken_attempt_still_gets_the_original_reassurance():
    """The default has to stay what it was: every existing caller that does
    not pass this argument is a speaking attempt."""
    assert "recordings are kept" in reporting.summary(None, {})


# -- what the product claims about its own validity ------------------------

def test_nothing_claims_to_be_validated_because_nothing_is():
    """The constants that carry no evidence must not read as though they do.

    Three things are unvalidated and must stay labelled that way until a
    study exists: the engine's weights against human judgement, the CEFR
    placement against the framework's own descriptors, and the two numbers
    chosen by argument in the last engine re-cut -- completeness at 0.08 and
    the 0.2/0.8 construction split.
    """
    from app.engine import calibration

    assert calibration.OVERALL_UNCALIBRATED_NOTE, (
        "there is no note to attach when the engine is uncalibrated")
    note = calibration.OVERALL_UNCALIBRATED_NOTE.lower()
    assert "not been validated" in note or "unvalidated" in note, (
        f"the uncalibrated note does not say so: {note}")


def test_the_cefr_band_is_offered_as_an_indication_and_never_as_a_result():
    band = reporting.cefr(70.0)
    assert band is not None
    lowered = band.caveat.lower()

    assert "not a cefr result" in lowered
    assert "no study" in lowered
    # And it must not undercut itself by also sounding official.
    for overclaim in ("certified", "accredited", "equivalent to",
                      "officially", "validated"):
        assert overclaim not in lowered, (
            f"the CEFR caveat contains {overclaim!r}, which reads as a claim")


def test_the_judgement_constants_are_documented_as_judgements():
    """0.08 and 0.2/0.8 were chosen by argument, not measured.

    Written into the source next to the constants so a reader cannot mistake
    them for findings. Asserted here so a later edit cannot quietly delete the
    admission while keeping the number.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    pipeline = (root / "app" / "engine" / "pipeline.py").read_text(encoding="utf-8")
    assert "completeness" in pipeline

    accuracy = (root / "app" / "engine" / "providers" / "tier1"
                / "accuracy.py").read_text(encoding="utf-8")
    window = accuracy[accuracy.index("COVERAGE_SHARE"):]
    assert "judgement, not a finding" in accuracy or "not a finding" in accuracy, (
        "the construction split no longer says it is a judgement")
    assert "0.2" in window and "0.8" in window


def test_an_uncalibrated_engine_never_reports_itself_calibrated():
    from app.engine import calibration

    state = calibration.current()
    if state.any_calibrated:
        pytest.skip("a calibration has been installed; this guard is for the "
                    "state the product actually ships in")
    assert not state.any_calibrated
