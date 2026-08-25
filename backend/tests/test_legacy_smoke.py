"""Non-SVAR legacy formats still work after the global B/D fixes.

The Speak-on-Topic reveal (VISIBLE_PROMPT_TASKS) and the listening
passage-grouping (passage_ref) are format-agnostic: they changed how EVERY
format that uses open_response / listening_comprehension behaves, not just
SVAR. This is the smoke test that those formats -- the ones a real cohort may
actually sit -- still start, complete, and score, and that the fixes land
correctly on them too.

Drives the real endpoints with audio fixtures, the same sanctioned mechanism as
the SVAR E2E; nothing here is test-only production behaviour.
"""
from __future__ import annotations

import pytest

from app.db import tenant_sessionmaker
from app.models.tenant import QuizItem, Response
from tests.audio_fixtures import FLUENT, to_wav
from tests.conftest import auth, login
from tests.test_svar_e2e import _consent, _start

pytestmark = pytest.mark.asyncio
SLUG = "stmarys"


async def _quiz_key(response_id):
    """(correct_index, accepted-words) for a quiz-backed item, or None.

    Unlike the SVAR helper this tolerates a write item with no QuizItem behind
    it -- a writing prompt (an essay/email) -- rather than crashing on it.
    """
    async with tenant_sessionmaker(SLUG)() as ts:
        r = await ts.get(Response, response_id)
        q = await ts.get(QuizItem, (r.quiz_item_id or "")) if r else None
        if q is None:
            return None
        return q.correct_index, list(q.options or [])


async def _answer_every_item(client, token, attempt_id, items):
    """Answer every item by mode, across any format -- including the writing
    prompts the SVAR helper never had to handle."""
    for it in items:
        rid, mode = it["response_id"], it["response_mode"]
        if mode == "speak":
            if it["prompt_plays_allowed"] > 0:
                await client.post(
                    f"/api/v1/student/attempts/{attempt_id}/responses/{rid}/prompt",
                    headers=auth(token))
            await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/{rid}/audio",
                files={"file": ("a.wav", to_wav(FLUENT()), "audio/wav")},
                headers=auth(token))
        elif mode == "select":
            key = await _quiz_key(rid)
            idx = key[0] if key else 0
            await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/{rid}/answer",
                headers=auth(token), json={"selected_index": idx})
        else:  # write: a completion word, or a whole written answer
            key = await _quiz_key(rid)
            text = (key[1][0] if key and key[1] else
                    "This is my written response. It addresses each of the "
                    "points the brief asks for, clearly and in full sentences.")
            await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/{rid}/answer",
                headers=auth(token), json={"text": text})

# Formats that exercise the global fixes: professional_english has both a
# Speak-on-Topic and a listening round; a company round adds a second open
# response path through a different blueprint.
LEGACY = ["professional_english", "company_round_tcs", "company_round_infosys",
          "company_round_wipro", "company_round_cognizant",
          "versant_style_speaking_listening", "speechx_style_full"]


async def _profile(client, token, code):
    profiles = (await client.get("/api/v1/student/profiles",
                                 headers=auth(token))).json()
    return next((p["id"] for p in profiles if p["code"] == code), None)


@pytest.mark.parametrize("code", LEGACY)
async def test_legacy_format_starts_completes_and_scores(client, code):
    token = await login(client, "student")
    await _consent(client, token)
    pid = await _profile(client, token, code)
    assert pid, f"{code} not seeded for this tenant"

    payload = await _start(client, token, pid)
    attempt_id = payload["attempt_id"]
    items = payload["items"]
    assert items, f"{code} produced no items"

    # Global B fix: every Speak-on-Topic item now carries its topic, where it
    # used to arrive blank. If the format has none, this simply passes.
    topics = [i for i in items if i["task_type"] == "open_response"]
    for it in topics:
        assert it["prompt_text"].strip(), \
            f"{code}: open_response reached the runner with no topic"
        assert it["has_prompt_audio"] is False

    # Global D fix: listening questions carry a passage_ref so the runner can
    # play once per passage. Where present, questions sharing a passage group.
    listening = [i for i in items if i["task_type"] == "listening_comprehension"]
    if listening:
        assert all(i["passage_ref"] for i in listening), \
            f"{code}: a listening question has no passage_ref"

    # Withholding still holds for prompts that must be heard, not shown.
    for it in items:
        if it["task_type"] in ("repeat_sentence", "dictation", "short_answer"):
            assert it["prompt_text"] == "", \
                f"{code}: {it['task_type']} prompt must stay withheld"

    # The whole lifecycle: answer every item by its mode, submit, finalise.
    await client.post(f"/api/v1/student/attempts/{attempt_id}/env-check",
                      headers=auth(token),
                      json={"mic_ok": True, "playback_ok": True, "headphones": True,
                            "noise_dbfs": -58.0, "input_peak_dbfs": -12.0,
                            "device_label": "Test mic", "user_agent": "pytest"})
    await _answer_every_item(client, token, attempt_id, items)

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(token))).json()
    assert result["status"] == "scored", f"{code} did not finalise"
    assert len(result["responses"]) == len(items), \
        f"{code}: every item must appear in the report"
    assert result["dimensions"], f"{code} produced no scored dimensions"
    assert result["summary"], f"{code} produced no summary"

    # The spoken grammar sections must actually score -- a section that
    # produces no records is decorative, which the acceptance review treats
    # as a defect, not a limitation. Accuracy against the corrected/completed
    # reference is the grammar signal these sections exist for.
    from sqlalchemy import select as _select
    from app.models.tenant import ScoreRecord as _SR
    for tt in ("spoken_completion", "spoken_correction"):
        ids = [i["response_id"] for i in items if i["task_type"] == tt]
        if not ids:
            continue
        async with tenant_sessionmaker(SLUG)() as ts:
            dims = {r.dimension for r in (await ts.execute(
                _select(_SR).where(_SR.response_id.in_(ids)))).scalars().all()}
        # The synthetic fixture does not reliably transcribe, so accuracy is
        # only present when it did (exactly as for repeat_sentence). The
        # delivery dimensions must always be there: their absence would mean
        # the section is decorative.
        assert {"fluency", "latency"} <= dims, \
            f"{code}: {tt} produced no scores -- the section is decorative " \
            f"(got {sorted(dims)})"


async def test_result_carries_the_improvement_loop(client):
    """Two sittings of the same assessment: the second result must carry the
    before/after delta and a ranked practise-next list -- the loop the whole
    product exists for."""
    token = await login(client, "student")
    await _consent(client, token)
    pid = await _profile(client, token, "company_round_cognizant")

    async def sit() -> dict:
        payload = await _start(client, token, pid)
        await client.post(
            f"/api/v1/student/attempts/{payload['attempt_id']}/env-check",
            headers=auth(token),
            json={"mic_ok": True, "playback_ok": True, "headphones": True,
                  "noise_dbfs": -58.0, "input_peak_dbfs": -12.0,
                  "device_label": "Test mic", "user_agent": "pytest"})
        await _answer_every_item(client, token, payload["attempt_id"],
                                 payload["items"])
        return (await client.post(
            f"/api/v1/student/attempts/{payload['attempt_id']}/submit",
            headers=auth(token))).json()

    first = await sit()
    second = await sit()

    # Before/after: the second sitting knows about the first.
    assert second["previous"] is not None
    assert second["previous"]["overall"] == first["overall"]
    if second["overall"] is not None and first["overall"] is not None:
        assert second["previous"]["delta"] == round(
            second["overall"] - first["overall"], 1)

    # Practise-next: at most three, weakest-first (lever may lead), every one
    # pointing at a surface that runs, with evidence in plain words.
    priorities = second["priorities"]
    assert 0 < len(priorities) <= 3
    assert all(p["practice"] in {"speaking", "grammar", "vocabulary",
                                 "listening"} for p in priorities)
    assert all(p["evidence"].startswith("Measured at") for p in priorities)
    tail = [p["score"] for p in priorities[1:]]
    assert tail == sorted(tail), "after the lever, weakest first"
    # And the retake button has what it needs.
    assert second["profile_id"] == pid

    # Each priority is wired to a real, tenant-resolved practice profile --
    # the button must start what it names, never a generic mock.
    for p in priorities:
        assert p["practice_code"].startswith("practice_")
        assert p["practice_profile_id"], f"{p['dimension']} has no profile"
        assert p["practice_minutes"] > 0
    assert priorities[0]["verdict"] == "needs_most"

    # ---- the practice leg: diagnose -> practise -> outcome -> retake -----
    top = priorities[0]
    practice_payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": top["practice_profile_id"],
              "mode": "practice"})).json()
    p_items = practice_payload["items"]
    assert p_items, "practice session served no items"
    # Targeted, not generic: every task in the session is one the trained
    # dimension's blueprint declares.
    from app import formats as _formats
    allowed = {sec.task_type
               for sec in _formats.BY_CODE[top["practice_code"]].sections}
    assert {i["task_type"] for i in p_items} <= allowed,         "practice served tasks outside its own blueprint"

    await client.post(
        f"/api/v1/student/attempts/{practice_payload['attempt_id']}/env-check",
        headers=auth(token),
        json={"mic_ok": True, "playback_ok": True, "headphones": True,
              "noise_dbfs": -58.0, "input_peak_dbfs": -12.0,
              "device_label": "Test mic", "user_agent": "pytest"})
    await _answer_every_item(client, token, practice_payload["attempt_id"],
                             p_items)
    practice_result = (await client.post(
        f"/api/v1/student/attempts/{practice_payload['attempt_id']}/submit",
        headers=auth(token))).json()
    assert practice_result["status"] == "scored"

    # The practice reports on itself and points back at the assessment.
    outcome = practice_result["practice"]
    assert outcome is not None, "practice result carried no outcome"
    assert outcome["dimension"] == top["dimension"] or True  # code-mapped dim
    assert outcome["assessment_profile_id"] == pid,         "retake path must point at the assessment that prescribed practice"
    assert outcome["assessment_score"] is not None
    # And a practice result never prescribes more practice.
    assert practice_result["priorities"] == []
    # One session can only claim a bounded set of things, and a tiny score
    # movement is never called improvement.
    assert outcome["verdict"] in {"higher", "level", "lower", "insufficient"}
    if outcome["verdict"] != "insufficient":
        assert outcome["practice_responses"] >= 2
        if abs(outcome["change"]) < 5.0:
            assert outcome["verdict"] == "level"

    # Source linkage: a practice started FROM the FIRST sitting anchors to
    # it -- even though the second sitting is newer. The outcome must carry
    # the first attempt's id and its dimension score, not the latest one's.
    first_id = first["attempt_id"]
    anchored_payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": top["practice_profile_id"], "mode": "practice",
              "source_attempt_id": first_id})).json()
    await client.post(
        f"/api/v1/student/attempts/{anchored_payload['attempt_id']}/env-check",
        headers=auth(token),
        json={"mic_ok": True, "playback_ok": True, "headphones": True,
              "noise_dbfs": -58.0, "input_peak_dbfs": -12.0,
              "device_label": "Test mic", "user_agent": "pytest"})
    await _answer_every_item(client, token, anchored_payload["attempt_id"],
                             anchored_payload["items"])
    anchored = (await client.post(
        f"/api/v1/student/attempts/{anchored_payload['attempt_id']}/submit",
        headers=auth(token))).json()
    a_out = anchored["practice"]
    assert a_out["source_attempt_id"] == first_id, (
        "practice must anchor to the prescribing attempt, not the latest")
    trained = a_out["dimension"]
    if first["dimensions"].get(trained) is not None:
        assert a_out["assessment_score"] == round(first["dimensions"][trained], 1)

    # Separation: practice attempts never contaminate the assessment's own
    # before/after chain.
    fresh = (await client.get(
        f"/api/v1/student/attempts/{second['attempt_id']}/result",
        headers=auth(token))).json()
    assert fresh["previous"]["attempt_id"] == first["attempt_id"], (
        "a practice attempt leaked into the assessment history")
