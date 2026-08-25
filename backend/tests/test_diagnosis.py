"""One answer to "what should I work on first?" -- and proof it stays one.

The defect these tests exist for: the result page computed that answer by
three rules (engine lever = lowest composite score; summary sentence =
largest weighted gain; priorities = lowest score with the lever pinned) and
showed all three. On a student with Content 20.0 / Pronunciation 20.6 the
page said Pronunciation at the top and Content twice below it.

app/diagnosis.py is now the only place the rule lives. Every test here is
written so that it FAILS if a second chooser ever comes back.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app import diagnosis as D
from app import reporting
from app.diagnosis import diagnose
from app.priorities import PRACTICE_CODE, priorities_for

# The live defect, to the decimal: TCS attempt 4e09c731, 2026-08-23.
TCS_LIVE = {"disfluency": 48.1, "content": 20.0, "fluency": 57.3,
            "latency": 77.5, "pronunciation": 20.6, "accuracy": 22.0,
            "completeness": 26.0, "grammar": 80.0}
TCS_COUNTS = {"disfluency": 15, "content": 5, "fluency": 15, "latency": 15,
              "pronunciation": 15, "accuracy": 3, "completeness": 5,
              "grammar": 3}


def _solid(dims: dict) -> dict:
    return {d: 6 for d in dims}


# --------------------------------------------------------------------------
# The rule itself
# --------------------------------------------------------------------------

def test_the_lowest_evidenced_practisable_dimension_is_the_primary():
    dims = {"pronunciation": 62, "fluency": 41, "grammar": 55, "content": 70}
    out = diagnose(dims, response_counts=_solid(dims))
    assert out.status == "identified"
    assert out.dimension == "fluency"
    assert out.label == "Fluency"
    assert out.headline == "Fluency"
    assert out.practice_code == "practice_fluency"
    assert "across 6 answers" in out.evidence
    assert out.confidence == "solid"
    # Student copy, no internals.
    for jargon in ("dimension", "composite", "weight", "lever"):
        assert jargon not in (out.reason + out.evidence).lower()


def test_the_weighted_lever_is_not_the_rule():
    """The engine's weighted gain says Pronunciation (+11.9) on the live
    defect; the lowest score says Content. Neither wins alone: they are
    0.6 apart, which is a tie, and the product says so."""
    out = diagnose(TCS_LIVE, response_counts=TCS_COUNTS)
    assert out.status == "tied"
    assert {c.dimension for c in out.candidates} == {"content", "pronunciation",
                                                     "accuracy"}
    assert out.headline == D.NO_CLEAR_WINNER
    assert out.practice_code == ""
    assert D.first_practice(out) == ""
    # And the gain-ranked table still disagrees with the lowest score --
    # which is exactly why it is no longer allowed to be a diagnosis.
    gains = reporting.recommendations(TCS_LIVE)
    assert gains[0].dimension == "pronunciation"
    assert min(TCS_LIVE, key=TCS_LIVE.get) == "content"


def test_tied_dimensions_do_not_produce_a_winner():
    dims = {"pronunciation": 41.0, "fluency": 41.5, "grammar": 70}
    out = diagnose(dims, response_counts=_solid(dims))
    assert out.status == "tied"
    assert out.dimension == ""
    assert [c.dimension for c in out.candidates] == ["pronunciation", "fluency"]
    assert "Pronunciation and Fluency" in out.reason
    assert "more evidence" in out.reason


def test_a_clear_gap_breaks_the_tie():
    dims = {"pronunciation": 41.0, "fluency": 44.5, "grammar": 70}
    out = diagnose(dims, response_counts=_solid(dims))
    assert out.status == "identified" and out.dimension == "pronunciation"


def test_level_measures_are_not_a_weakness():
    dims = {"pronunciation": 55, "fluency": 56, "grammar": 57}
    out = diagnose(dims, response_counts=_solid(dims))
    assert out.status == "level"
    assert out.headline == D.NO_CLEAR_WINNER
    assert "close together" in out.reason


def test_insufficient_evidence_produces_no_fabricated_winner():
    # One answer each: an anecdote, not a pattern.
    dims = {"pronunciation": 30, "fluency": 60}
    out = diagnose(dims, response_counts={"pronunciation": 1, "fluency": 1})
    assert out.status == "insufficient"
    assert out.dimension == "" and out.practice_code == ""
    assert out.headline == D.NOT_ENOUGH
    assert "only one answer" in out.evidence
    # Nothing measured at all.
    assert diagnose({}).status == "none"
    assert diagnose({"overall": 50.0}).status == "none"


def test_a_thinly_measured_lower_score_is_disclosed_not_promoted():
    """Content at 20 on one answer, fluency at 40 on six: fluency is the
    primary, and the student is told why content was not."""
    dims = {"content": 20.0, "fluency": 40.0, "grammar": 70.0}
    out = diagnose(dims, response_counts={"content": 1, "fluency": 6, "grammar": 6})
    assert out.status == "identified" and out.dimension == "fluency"
    assert ("content", "it was measured on only one answer") in out.excluded
    assert "Content was lower" in out.evidence


def test_unmapped_dimensions_cannot_become_the_primary():
    """An engine dimension with no targeted practice never gets a button --
    and is never silently ignored either."""
    dims = {"register": 20.0, "fluency": 40.0, "grammar": 70.0}
    out = diagnose(dims, response_counts={"register": 6, "fluency": 6, "grammar": 6})
    assert out.dimension == "fluency"
    assert out.practice_code in PRACTICE_CODE.values()
    assert ("register", "we do not have a targeted practice for it yet") in out.excluded


def test_a_practice_the_tenant_lacks_cannot_be_prescribed():
    dims = {"fluency": 30.0, "grammar": 45.0, "content": 70.0}
    out = diagnose(dims, response_counts=_solid(dims),
                   available_practice={"practice_grammar", "practice_content"})
    assert out.dimension == "grammar"
    assert ("fluency", "its practice session is not available here") in out.excluded


def test_the_primary_always_has_a_runnable_targeted_practice():
    from app import formats
    from app.evaluation import DIMENSIONS_BY_TASK
    for dim in PRACTICE_CODE:
        dims = {dim: 30.0, "grammar" if dim != "grammar" else "fluency": 70.0}
        out = diagnose(dims, response_counts=_solid(dims))
        assert out.status == "identified" and out.dimension == dim
        blueprint = formats.BY_CODE[out.practice_code]
        emitted = set().union(*(DIMENSIONS_BY_TASK[s.task_type]
                                for s in blueprint.sections))
        assert dim in emitted, f"{out.practice_code} does not measure {dim}"


def test_labels_match_the_frontend():
    src = (Path(__file__).resolve().parents[2]
           / "frontend" / "lib" / "dimensions.ts").read_text()
    block = src.split("DIMENSION_LABEL")[1].split("};")[0]
    found = dict(re.findall(r'^\s+(\w+): "([^"]+)",', block, re.M))
    for dim, label in D.LABEL.items():
        assert found.get(dim) == label, f"{dim}: backend {label!r} vs frontend {found.get(dim)!r}"


# --------------------------------------------------------------------------
# Every downstream surface consumes the same object
# --------------------------------------------------------------------------

def test_summary_sentence_agrees_with_the_diagnosis():
    dims = {"pronunciation": 62, "fluency": 41, "grammar": 55}
    primary = diagnose(dims, response_counts=_solid(dims))
    text = reporting.summary(52.0, dims, primary=primary)
    assert reporting._say("fluency") in text
    assert "worth working on first" in text
    # The gain-ranked choice on these numbers is pronunciation-free but the
    # old sentence quoted a points figure; the new one never does.
    assert "points" not in text


def test_summary_sentence_says_nothing_stands_out_on_a_tie():
    primary = diagnose(TCS_LIVE, response_counts=TCS_COUNTS)
    text = reporting.summary(41.3, TCS_LIVE, primary=primary)
    assert "Nothing clearly stands out yet" in text
    assert "worth working on first" not in text


def test_priorities_lead_with_the_diagnosis_and_only_it_is_needs_most():
    dims = {"pronunciation": 62, "fluency": 41, "grammar": 55}
    primary = diagnose(dims, response_counts=_solid(dims))
    out = priorities_for(dims, scale_max=80, response_counts=_solid(dims),
                         primary=primary)
    assert out[0].dimension == primary.dimension
    assert out[0].practice_code == primary.practice_code == D.first_practice(primary)
    assert [p.verdict for p in out].count("needs_most") == 1


def test_priorities_never_crown_anyone_when_the_diagnosis_did_not():
    for dims, counts in (
        (TCS_LIVE, TCS_COUNTS),                                   # tied
        ({"pronunciation": 55, "fluency": 56, "grammar": 57}, None),  # level
        ({"pronunciation": 30, "fluency": 60}, {"pronunciation": 1, "fluency": 1}),
    ):
        counts = counts or _solid(dims)
        primary = diagnose(dims, response_counts=counts)
        assert primary.status != "identified"
        out = priorities_for(dims, scale_max=80, response_counts=counts,
                             primary=primary)
        assert all(p.verdict != "needs_most" for p in out), dims


# --------------------------------------------------------------------------
# Adversarial fixtures: each reproduces a contradiction and must stay red
# --------------------------------------------------------------------------

def _evidence(primary: dict | None, **kw):
    from app.narration.contract import NarrationEvidence
    base = dict(schema_version="2.0",
                attempt={"status": "scored", "has_overall": True, "overall": 41.3,
                         "scale": [20, 80], "band_phrase": "some way off",
                         "calibrated": False, "has_audio": True},
                dimensions=[{"key": d, "score": s, "gloss": reporting._say(d)}
                            for d, s in TCS_LIVE.items()],
                primary_diagnosis=primary, strengths=[], recommendations=[],
                unscored={}, evidence_facts=[], l1_language="")
    base.update(kw)
    return NarrationEvidence(**base)


def _primary_dict(dimension: str) -> dict:
    return {"status": "identified", "dimension": dimension,
            "gloss": reporting._say(dimension), "label": D.label(dimension),
            "score": TCS_LIVE[dimension], "responses": 5,
            "reason": "", "evidence": "", "candidates": []}


def test_adversarial_narration_says_a_while_diagnosis_says_b():
    """Narration A / priority B: the draft focuses on pronunciation while the
    authoritative diagnosis is content. Must be refused."""
    from app.narration import validate as V
    from app.narration.contract import NarrationDraft, NarratorError
    draft = NarrationDraft(
        headline="Some way off.", summary="Your speaking is developing.",
        primary_focus="The one thing worth working on first is how clearly you pronounce words.",
        practice_action="Read a paragraph aloud.")
    with pytest.raises(NarratorError, match="contradicts primary_diagnosis"):
        V.check(draft, _evidence(_primary_dict("content")))


def test_adversarial_narration_picks_a_winner_on_a_tie():
    """The diagnosis found a tie; the draft crowns pronunciation anyway."""
    from app.narration import validate as V
    from app.narration.contract import NarrationDraft, NarratorError
    tied = {"status": "tied", "dimension": "", "gloss": "", "label": "",
            "score": None, "responses": 0, "reason": "", "evidence": "",
            "candidates": [{"dimension": "content", "gloss": reporting._say("content"),
                            "score": 20.0, "responses": 5},
                           {"dimension": "pronunciation",
                            "gloss": reporting._say("pronunciation"),
                            "score": 20.6, "responses": 15}]}
    draft = NarrationDraft(
        headline="Some way off.", summary="Your speaking is developing.",
        primary_focus="Focus on pronunciation first.",
        practice_action="Read a paragraph aloud.")
    with pytest.raises(NarratorError, match="does not say so"):
        V.check(draft, _evidence(tied))
    # Naming an area outside the tied group, even while hedging, also fails.
    draft2 = NarrationDraft(
        headline="Some way off.", summary="Your speaking is developing.",
        primary_focus="Nothing clearly stands out yet, but grammar is the one to fix.",
        practice_action="Read a paragraph aloud.")
    with pytest.raises(NarratorError, match="names grammar"):
        V.check(draft2, _evidence(tied))
    # The honest version passes.
    ok = NarrationDraft(
        headline="Some way off.", summary="Your speaking is developing.",
        primary_focus="Nothing clearly stands out yet -- content and pronunciation are level, so a little more evidence is needed.",
        practice_action="Read a paragraph aloud.")
    V.check(ok, _evidence(tied))


def test_adversarial_lever_says_a_while_diagnosis_says_b():
    """Lever A / priority B: the engine lever (lowest composite score) and
    the diagnosis can legitimately differ -- so the lever must have no
    route to any surface that names a weakness."""
    from app.engine.pipeline import biggest_lever
    from app.narration import evidence as E

    dims = {"content": 20.0, "pronunciation": 24.0, "fluency": 60.0,
            "comprehension": 15.0}  # not in WEIGHTS: invisible to the lever
    counts = _solid(dims)
    lever = biggest_lever(dims)
    primary = diagnose(dims, response_counts=counts)
    assert lever["dimension"] == "content"
    assert primary.dimension == "comprehension"      # genuinely lowest, practisable

    # 1. Priorities take the diagnosis, not the lever.
    out = priorities_for(dims, scale_max=80, response_counts=counts, primary=primary)
    assert out[0].dimension == "comprehension"
    # 2. The summary sentence takes the diagnosis.
    assert reporting._say("comprehension") in reporting.summary(40.0, dims, primary=primary)
    # 3. The narrator is not given the lever at all.
    class R:  # a result with both fields present
        dimensions = dims; overall = 40.0; status = "scored"; scale_min = 20
        scale_max = 80; calibrated = False; responses = []; strengths = []
        unscored = {}; priorities = []
        biggest_lever = lever
        primary_diagnosis = {"status": primary.status, "dimension": primary.dimension,
                             "label": primary.label, "score": primary.score,
                             "responses": primary.responses, "reason": primary.reason,
                             "evidence": primary.evidence, "candidates": []}
    payload = E.as_payload(E.build(R()))
    assert "biggest_lever" not in payload
    assert payload["primary_diagnosis"]["dimension"] == "comprehension"
    assert "predicted_gain" not in str(payload)


def test_adversarial_practice_profile_mismatch_is_impossible_by_construction():
    """The button starts diagnosis.practice_code, and PRACTICE_CODE is the
    only mapping. A practice that does not measure its dimension is a
    blueprint defect test_priorities already catches; here: the diagnosis
    can never carry a code PRACTICE_CODE does not map to its dimension."""
    for dim, code in PRACTICE_CODE.items():
        dims = {dim: 25.0, ("grammar" if dim != "grammar" else "fluency"): 70.0}
        out = diagnose(dims, response_counts=_solid(dims))
        assert out.practice_code == code == PRACTICE_CODE[out.dimension]


def test_no_other_module_chooses_a_first_thing_to_work_on():
    """Grep-level guard: the phrases that name a first weakness appear only
    in the diagnosis module and the summary sentence that consumes it."""
    root = Path(__file__).resolve().parents[1] / "app"
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text()
        if "lift your score most" in text or "would have been worth about" in text:
            offenders.append(str(path.relative_to(root)))
        if "lever_dimension" in text:
            offenders.append(str(path.relative_to(root)) + " (lever_dimension)")
    assert not offenders, offenders


# --------------------------------------------------------------------------
# Through the API: result, narration, practice, retake -- one chain
# --------------------------------------------------------------------------

async def _sit(client, token, profile_id: str, source_attempt_id: str | None = None) -> dict:
    from tests.test_legacy_smoke import _answer_every_item
    body = {"profile_id": profile_id, "mode": "practice"}
    if source_attempt_id:
        body["source_attempt_id"] = source_attempt_id
    payload = (await client.post("/api/v1/student/attempts",
                                 headers={"Authorization": f"Bearer {token}"},
                                 json=body)).json()
    aid = payload["attempt_id"]
    await client.post(f"/api/v1/student/attempts/{aid}/env-check",
                      headers={"Authorization": f"Bearer {token}"},
                      json={"mic_ok": True, "playback_ok": True, "headphones": True,
                            "noise_dbfs": -58.0, "input_peak_dbfs": -12.0,
                            "device_label": "Test mic", "user_agent": "pytest"})
    await _answer_every_item(client, token, aid, payload["items"])
    return (await client.post(f"/api/v1/student/attempts/{aid}/submit",
                              headers={"Authorization": f"Bearer {token}"})).json()


async def test_result_narration_practice_and_retake_share_one_diagnosis(client, monkeypatch):
    from app.config import settings
    from app.narration import worker
    from tests.conftest import auth, login
    from tests.test_svar_e2e import SLUG, _consent
    from tests.test_legacy_smoke import _profile as _profile_id_for

    monkeypatch.setattr(settings, "narration_enabled", True)
    monkeypatch.setattr(settings, "narration_provider", "echo")

    token = await login(client, "student")
    await _consent(client, token)
    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording", "ai_explanation"]})
    pid = await _profile_id_for(client, token, "company_round_cognizant")
    result = await _sit(client, token, pid)
    assert result["status"] == "scored"

    primary = result["primary_diagnosis"]
    assert primary is not None
    assert primary["source_attempt_id"] == result["attempt_id"]
    assert primary["source_profile_id"] == pid
    assert primary["status"] in {"identified", "tied", "level", "insufficient", "none"}

    # 1. The summary sentence agrees.
    if primary["status"] == "identified":
        assert reporting._say(primary["dimension"]) in result["summary"]
    else:
        assert "worth working on first" not in result["summary"]

    # 2. The first practice recommendation IS the diagnosis (or there is no
    #    "needs_most" at all), and its button starts the diagnosis's profile.
    priorities = result["priorities"]
    if primary["status"] == "identified":
        assert priorities[0]["dimension"] == primary["dimension"]
        assert priorities[0]["verdict"] == "needs_most"
        assert priorities[0]["practice_profile_id"] == primary["practice_profile_id"] != ""
        assert primary["practice_code"] == PRACTICE_CODE[primary["dimension"]]
    else:
        assert all(p["verdict"] != "needs_most" for p in priorities)
        assert primary["practice_profile_id"] == ""

    # 3. The AI narration explains the same diagnosis. The echo provider is a
    #    real, validated provider; the validator is what makes disagreement
    #    impossible for every provider.
    await worker.tick_tenant(SLUG)
    fresh = (await client.get(f"/api/v1/student/attempts/{result['attempt_id']}/result",
                              headers=auth(token))).json()
    narration = fresh["narration"]
    assert narration is not None and narration["status"] == "ready", narration
    from app.narration import validate as V
    if primary["status"] == "identified":
        assert V._mentions_dimension(narration["primary_focus"].lower(),
                                     {"dimension": primary["dimension"],
                                      "gloss": reporting._say(primary["dimension"])})
    else:
        assert "stand" in narration["primary_focus"].lower() \
            or "more evidence" in narration["primary_focus"].lower()

    # 4. Practise what was diagnosed (or, with no primary, the first listed),
    #    anchored to this result. The practice result knows what assessment
    #    prescribed it, what it diagnosed, and what was practised.
    target = priorities[0] if priorities else None
    if target is None:
        pytest.skip("fixture produced no practisable dimension")
    practice = await _sit(client, token, target["practice_profile_id"],
                          source_attempt_id=result["attempt_id"])
    outcome = practice["practice"]
    assert outcome["source_linked"] is True
    assert outcome["source_attempt_id"] == result["attempt_id"]
    assert outcome["assessment_profile_id"] == pid
    assert outcome["dimension"] == target["dimension"]
    assert outcome["prescribed_status"] == primary["status"]
    assert outcome["prescribed_dimension"] == primary["dimension"]
    assert outcome["trained_primary"] == (primary["status"] == "identified"
                                          and target["dimension"] == primary["dimension"])
    # The practice result carries the PRESCRIBING assessment's diagnosis,
    # recomputed from its stored scores -- identical to what its page said.
    carried = practice["primary_diagnosis"]
    assert carried["status"] == primary["status"]
    assert carried["dimension"] == primary["dimension"]
    assert carried["source_attempt_id"] == result["attempt_id"]
    assert carried["source_profile_name"] == result["profile_name"]
    # A practice result never prescribes, and never re-diagnoses itself.
    assert practice["priorities"] == []
    assert "worth working on first" not in practice["summary"]

    # 5. Scores cannot be confused: the practice's own measurement and the
    #    assessment's measurement of the trained dimension are separate
    #    fields, each equal to its own source.
    trained = outcome["dimension"]
    if outcome["assessment_score"] is not None:
        assert outcome["assessment_score"] == round(result["dimensions"][trained], 1)
    if outcome["practice_score"] is not None:
        assert outcome["practice_score"] == round(practice["dimensions"][trained], 1)


async def test_an_unlinked_practice_never_claims_a_prescriber(client):
    from tests.conftest import auth, login
    from tests.test_svar_e2e import _consent
    from tests.test_legacy_smoke import _profile as _profile_id_for

    token = await login(client, "student")
    await _consent(client, token)
    pid = await _profile_id_for(client, token, "company_round_cognizant")
    await _sit(client, token, pid)                     # an assessment exists
    practice_pid = await _profile_id_for(client, token, "practice_fluency")
    practice = await _sit(client, token, practice_pid)  # no source link
    outcome = practice["practice"]
    assert outcome["source_linked"] is False
    assert outcome["prescribed_status"] == "" and outcome["prescribed_dimension"] == ""
    assert outcome["trained_primary"] is False
    # No diagnosis is guessed for it.
    assert practice["primary_diagnosis"] is None
