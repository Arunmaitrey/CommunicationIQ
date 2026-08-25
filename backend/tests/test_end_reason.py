"""'Ran out of time' may only be said about an answer the clock actually cut.

The defect (candidate UAT 2026-08-23, P2; PM increment 2026-08-24): the
report counted any recording whose speech ran to the end of the file as
"ran out of time while you were still speaking" — including answers the
candidate deliberately ended with Stop / "I have finished" while talking.
A report that contradicts the candidate's own behaviour teaches them to
distrust everything else on the page.

The rule now: TIMEOUT requires BOTH facts — the acoustic ended-mid-speech
signal AND the client's statement that the window expired. The end reasons
are kept as distinct states (user_ended / auto_advance / window_expired /
cancelled / "" unknown), never collapsed, and unknown is never a timeout.

Run on a NON-TCS profile throughout, to prove nothing here is format-bound.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import tenant_sessionmaker
from app.models.tenant import FeatureRecord, Response
from app.reporting import END_REASONS, ran_out_of_time
from tests.audio_fixtures import FLUENT, to_wav
from tests.conftest import auth, login
from tests.test_svar_e2e import SLUG, _consent

pytestmark = pytest.mark.asyncio


# --------------------------------------------------------------------------
# The rule itself — cases A–E from the acceptance list
# --------------------------------------------------------------------------

def test_case_a_and_d_window_expiry_while_speaking_is_a_timeout():
    assert ran_out_of_time(True, "window_expired") is True


def test_case_b_stop_pressed_while_speaking_is_not_a_timeout():
    assert ran_out_of_time(True, "user_ended") is False


def test_case_c_explicit_finish_control_is_not_a_timeout():
    # "I have finished" and Stop & submit both report user_ended.
    assert ran_out_of_time(True, "user_ended") is False
    # The runner's silence advance is its own state, and also not a timeout.
    assert ran_out_of_time(True, "auto_advance") is False


def test_case_e_unknown_or_cancelled_is_never_guessed_as_timeout():
    # A legacy row, an older client, or a failed/cancelled path cannot say
    # why the recording ended — and a claim about behaviour needs evidence.
    assert ran_out_of_time(True, "") is False
    assert ran_out_of_time(True, "cancelled") is False


def test_no_mid_speech_signal_is_never_a_timeout_whatever_the_reason():
    for reason in ("", *END_REASONS):
        assert ran_out_of_time(False, reason) is False


def test_the_states_are_distinct_not_a_single_truncated_concept():
    assert set(END_REASONS) == {"user_ended", "auto_advance",
                                "window_expired", "cancelled"}


# --------------------------------------------------------------------------
# Through the API, on a non-TCS profile
# --------------------------------------------------------------------------

async def _profile_id(client, token, code: str) -> str:
    profiles = (await client.get("/api/v1/student/profiles",
                                 headers=auth(token))).json()
    return next(p["id"] for p in profiles if p["code"] == code)


async def _sit_spoken(client, token, code: str) -> dict:
    """Sit a short spoken profile, sending ended_by with every upload."""
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": await _profile_id(client, token, code),
              "mode": "practice"})).json()
    aid = payload["attempt_id"]
    await client.post(f"/api/v1/student/attempts/{aid}/env-check",
                      headers=auth(token),
                      json={"mic_ok": True, "playback_ok": True,
                            "headphones": True, "noise_dbfs": -58.0,
                            "input_peak_dbfs": -12.0,
                            "device_label": "Test mic", "user_agent": "pytest"})
    spoken = [i for i in payload["items"] if i["response_mode"] == "speak"]
    assert len(spoken) >= 2, "fixture needs at least two spoken items"
    # First answer: the candidate pressed Stop. Second: the window expired.
    # The rest: an older client that sends nothing.
    reasons = ["user_ended", "window_expired"] + [None] * (len(spoken) - 2)
    for it, reason in zip(spoken, reasons):
        rid = it["response_id"]
        if it["prompt_plays_allowed"] > 0:
            await client.post(
                f"/api/v1/student/attempts/{aid}/responses/{rid}/prompt",
                headers=auth(token))
        data = {"ended_by": reason} if reason else {}
        res = await client.post(
            f"/api/v1/student/attempts/{aid}/responses/{rid}/audio",
            files={"file": ("a.wav", to_wav(FLUENT()), "audio/wav")},
            data=data, headers=auth(token))
        assert res.status_code == 201, res.text
    return (await client.post(f"/api/v1/student/attempts/{aid}/submit",
                              headers=auth(token))).json()


async def _force_mid_speech(attempt_id: str) -> None:
    """Make every scored answer read as ended-mid-speech, so the note logic
    is decided purely by the stored end reasons."""
    async with tenant_sessionmaker(SLUG)() as s:
        rows = list((await s.execute(
            select(Response).where(Response.attempt_id == attempt_id)
        )).scalars().all())
        features = list((await s.execute(
            select(FeatureRecord).where(
                FeatureRecord.response_id.in_([r.id for r in rows]))
        )).scalars().all())
        for f in features:
            metrics = dict(f.metrics or {})
            metrics["ended_mid_speech"] = True
            f.metrics = metrics
        await s.commit()


async def test_only_window_expired_answers_are_reported_as_out_of_time(client):
    """One sitting, three end reasons: the note counts ONLY the expired one,
    the stored states stay distinct, and the metrics say which is which."""
    token = await login(client, "student")
    await _consent(client, token)
    result = await _sit_spoken(client, token, "practice_fluency")
    aid = result["attempt_id"]

    await _force_mid_speech(aid)
    fresh = (await client.get(f"/api/v1/student/attempts/{aid}/result",
                              headers=auth(token))).json()

    by_reason = {r["ended_by"]: r for r in fresh["responses"]
                 if not r["skipped"] and r["ended_by"] is not None}
    assert "user_ended" in by_reason and "window_expired" in by_reason
    mid = [r for r in fresh["responses"] if r["ended_mid_speech"]]
    assert len(mid) >= 2, "the forced signal must be visible"

    note = fresh["environment_note"]
    assert "1 of your answers ran out of time" in note, note
    # Never the user-ended or unknown ones.
    expired = [r for r in fresh["responses"]
               if r["ended_mid_speech"] and r["ended_by"] == "window_expired"]
    assert len(expired) == 1


async def test_stop_pressed_everywhere_produces_no_timeout_note(client):
    token = await login(client, "student")
    await _consent(client, token)
    result = await _sit_spoken(client, token, "practice_pronunciation")
    aid = result["attempt_id"]

    # Rewrite the one expired answer as user-ended: same audio, same acoustic
    # signal — the note must vanish, because nobody actually timed out.
    async with tenant_sessionmaker(SLUG)() as s:
        rows = list((await s.execute(
            select(Response).where(Response.attempt_id == aid)
        )).scalars().all())
        for r in rows:
            if r.ended_by == "window_expired":
                r.ended_by = "user_ended"
        await s.commit()
    await _force_mid_speech(aid)

    fresh = (await client.get(f"/api/v1/student/attempts/{aid}/result",
                              headers=auth(token))).json()
    assert "ran out of time" not in fresh["environment_note"]


async def test_an_unrecognised_reason_is_stored_as_unknown(client):
    """A hostile or buggy client cannot invent a state: anything outside the
    enum is stored as "" — and "" is never reported as a timeout."""
    token = await login(client, "student")
    await _consent(client, token)
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": await _profile_id(client, token, "practice_latency"),
              "mode": "practice"})).json()
    aid = payload["attempt_id"]
    await client.post(f"/api/v1/student/attempts/{aid}/env-check",
                      headers=auth(token),
                      json={"mic_ok": True, "playback_ok": True,
                            "headphones": True, "noise_dbfs": -58.0,
                            "input_peak_dbfs": -12.0,
                            "device_label": "Test mic", "user_agent": "pytest"})
    it = next(i for i in payload["items"] if i["response_mode"] == "speak")
    if it["prompt_plays_allowed"] > 0:
        await client.post(
            f"/api/v1/student/attempts/{aid}/responses/{it['response_id']}/prompt",
            headers=auth(token))
    res = await client.post(
        f"/api/v1/student/attempts/{aid}/responses/{it['response_id']}/audio",
        files={"file": ("a.wav", to_wav(FLUENT()), "audio/wav")},
        data={"ended_by": "totally_made_up"}, headers=auth(token))
    assert res.status_code == 201
    async with tenant_sessionmaker(SLUG)() as s:
        row = await s.get(Response, it["response_id"])
        assert row.ended_by == ""
