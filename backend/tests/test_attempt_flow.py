"""A student takes a simulation, end to end.

Also the place where the three rules that cannot live in the browser are
tested: consent before capture, one prompt play, one recording per item.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.db import tenant_sessionmaker
from app.models.tenant import (Attempt, ConsentRecord, ResponseAudio,
                               SimulationProfile, User)
from app.retention import sweep_tenant
from app.storage import get_storage
from tests.audio_fixtures import FLUENT, HESITANT, silence, to_wav
from tests.conftest import auth, login

pytestmark = pytest.mark.asyncio

SLUG = "stmarys"


async def _baseline_profile_id(client, token) -> str:
    profiles = (await client.get("/api/v1/student/profiles", headers=auth(token))).json()
    baseline = next(p for p in profiles if p["is_baseline"])
    return baseline["id"]


async def _start(client, token) -> dict:
    profile_id = await _baseline_profile_id(client, token)
    res = await client.post("/api/v1/student/attempts",
                            json={"profile_id": profile_id, "mode": "practice"},
                            headers=auth(token))
    assert res.status_code == 201, res.text
    return res.json()


async def _env_check(client, token, attempt_id, noise_dbfs=-58.0):
    return await client.post(
        f"/api/v1/student/attempts/{attempt_id}/env-check",
        json={"mic_ok": True, "playback_ok": True, "headphones": True,
              "noise_dbfs": noise_dbfs, "input_peak_dbfs": -12.0,
              "device_label": "Test mic", "user_agent": "pytest"},
        headers=auth(token),
    )


async def _upload(client, token, attempt_id, response_id, samples,
                  ended_by: str = ""):
    return await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/{response_id}/audio",
        files={"file": ("answer.wav", to_wav(samples), "audio/wav")},
        data={"ended_by": ended_by} if ended_by else {},
        headers=auth(token),
    )


# --------------------------------------------------------------------------

async def test_a_full_attempt_produces_a_real_diagnosis(client):
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]

    assert payload["items"], "the attempt should have items"
    assert payload["env_check_done"] is False

    check = await _env_check(client, token, attempt_id)
    assert check.status_code == 200
    assert check.json()["warning"] == ""

    for item in payload["items"]:
        if item["prompt_plays_allowed"] > 0:
            prompt = await client.post(
                f"/api/v1/student/attempts/{attempt_id}/responses/{item['response_id']}/prompt",
                headers=auth(token))
            assert prompt.status_code == 200
            assert prompt.json()["text"]
        res = await _upload(client, token, attempt_id, item["response_id"], FLUENT())
        assert res.status_code == 201, res.text
        assert res.json()["quality"] == "good"

    submitted = await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                  headers=auth(token))
    assert submitted.status_code == 200, submitted.text
    result = submitted.json()

    assert result["status"] == "scored"
    assert result["overall"] is not None
    assert "fluency" in result["dimensions"]
    assert "latency" in result["dimensions"]
    assert result["band"]
    assert len(result["responses"]) == len(payload["items"])
    # Every response carries measured features, not placeholders.
    assert all(r["onset_ms"] is not None for r in result["responses"])


async def test_scoring_stays_inside_the_latency_budget(client):
    """NFR-01: five seconds for scripted tasks. The student is watching."""
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)

    for item in payload["items"]:
        await _upload(client, token, attempt_id, item["response_id"], FLUENT())

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(token))).json()
    assert result["scoring_ms"] is not None
    assert result["scoring_ms"] < 5000, f"scoring took {result['scoring_ms']}ms"


async def test_every_score_names_the_provider_that_produced_it(client):
    """ENG-21. A score whose origin is unknown cannot be audited or replaced."""
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)
    for item in payload["items"]:
        await _upload(client, token, attempt_id, item["response_id"], FLUENT())
    await client.post(f"/api/v1/student/attempts/{attempt_id}/submit", headers=auth(token))

    from app.models.tenant import ScoreRecord
    async with tenant_sessionmaker(SLUG)() as session:
        rows = list((await session.execute(
            select(ScoreRecord).where(ScoreRecord.attempt_id == attempt_id,
                                      ScoreRecord.response_id.is_not(None))
        )).scalars().all())
    assert rows
    for row in rows:
        assert row.provider_key, f"{row.dimension} has no provider stamped"
        assert row.provider_version


async def test_a_hesitant_answer_scores_below_a_fluent_one(client):
    """The engine has to discriminate, or the diagnosis is decoration."""
    token = await login(client, "student")

    async def score_with(samples) -> float:
        payload = await _start(client, token)
        attempt_id = payload["attempt_id"]
        await _env_check(client, token, attempt_id)
        for item in payload["items"]:
            await _upload(client, token, attempt_id, item["response_id"], samples())
        return (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                  headers=auth(token))).json()["overall"]

    assert await score_with(HESITANT) < await score_with(FLUENT)


async def test_an_unanswered_item_is_not_scored_as_a_bad_answer(client):
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)

    first, rest = payload["items"][0], payload["items"][1:]
    await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/{first['response_id']}/skip",
        headers=auth(token))
    for item in rest:
        await _upload(client, token, attempt_id, item["response_id"], FLUENT())

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(token))).json()
    skipped = next(r for r in result["responses"] if r["response_id"] == first["response_id"])
    assert skipped["skipped"] is True
    assert skipped["scores"] == {}


# -- the three rules the browser cannot be trusted with --------------------

async def test_a_prompt_is_served_once_and_the_server_is_what_counts(client):
    """SIM-02. Reloading the page must not buy a replay."""
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)

    listening = next(i for i in payload["items"] if i["prompt_plays_allowed"] == 1)
    url = f"/api/v1/student/attempts/{attempt_id}/responses/{listening['response_id']}/prompt"

    first = await client.post(url, headers=auth(token))
    assert first.status_code == 200
    assert first.json()["plays_remaining"] == 0

    second = await client.post(url, headers=auth(token))
    assert second.status_code == 409


async def test_a_read_aloud_item_has_no_prompt_to_play(client):
    token = await login(client, "student")
    payload = await _start(client, token)
    reading = next(i for i in payload["items"] if i["task_type"] == "read_aloud")
    assert reading["prompt_text"], "the student is meant to see this one"

    res = await client.post(
        f"/api/v1/student/attempts/{payload['attempt_id']}/responses/{reading['response_id']}/prompt",
        headers=auth(token))
    assert res.status_code == 400


async def test_a_repeat_sentence_text_is_withheld_until_it_is_played(client):
    """Shipping the sentence with the runner payload would turn a listening
    task into a reading task."""
    token = await login(client, "student")
    payload = await _start(client, token)
    listening = [i for i in payload["items"] if i["task_type"] == "repeat_sentence"]
    assert listening
    assert all(i["prompt_text"] == "" for i in listening)


async def test_one_recording_per_item(client):
    """A second take would quietly undo one-shot."""
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)

    item = payload["items"][0]
    assert (await _upload(client, token, attempt_id, item["response_id"], FLUENT())).status_code == 201
    assert (await _upload(client, token, attempt_id, item["response_id"], FLUENT())).status_code == 409


async def test_nothing_is_recorded_without_consent(client):
    """STU-02. Enforced on ingest, not in the UI."""
    token = await login(client, "student")
    student_email = "aarav.reddy1@stmarys.edu"

    async with tenant_sessionmaker(SLUG)() as session:
        user = (await session.execute(
            select(User).where(User.email == student_email))).scalar_one()
        saved = list((await session.execute(
            select(ConsentRecord).where(ConsentRecord.user_id == user.id,
                                        ConsentRecord.scope == "recording")
        )).scalars().all())
        await session.execute(delete(ConsentRecord).where(
            ConsentRecord.user_id == user.id, ConsentRecord.scope == "recording"))
        await session.commit()

    try:
        profile_id = await _baseline_profile_id(client, token)
        res = await client.post("/api/v1/student/attempts",
                                json={"profile_id": profile_id},
                                headers=auth(token))
        assert res.status_code == 403
        assert "consent" in res.json()["detail"].lower()
    finally:
        async with tenant_sessionmaker(SLUG)() as session:
            for row in saved:
                session.add(ConsentRecord(
                    user_id=row.user_id, scope=row.scope, granted=row.granted,
                    notice_version=row.notice_version, retention_days=row.retention_days,
                ))
            await session.commit()


async def test_a_student_cannot_open_another_students_attempt(client):
    token = await login(client, "student")
    payload = await _start(client, token)

    async with tenant_sessionmaker(SLUG)() as session:
        me = (await session.execute(
            select(Attempt.user_id).where(Attempt.id == payload["attempt_id"])
        )).scalar_one()
        other = (await session.execute(
            select(Attempt).where(Attempt.user_id != me)
        )).scalars().first()

    assert other is not None
    res = await client.get(f"/api/v1/student/attempts/{other.id}/runner", headers=auth(token))
    # 404, not 403: confirming the attempt exists is itself a disclosure.
    assert res.status_code == 404


async def test_a_non_wav_upload_is_refused(client):
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)

    res = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/{payload['items'][0]['response_id']}/audio",
        files={"file": ("answer.wav", b"not audio at all", "audio/wav")},
        headers=auth(token))
    assert res.status_code == 415


async def test_a_noisy_room_is_flagged_before_the_test_rather_than_blamed_after(client):
    token = await login(client, "student")
    payload = await _start(client, token)
    check = await _env_check(client, token, payload["attempt_id"], noise_dbfs=-30.0)
    assert check.status_code == 200
    assert "noisy" in check.json()["warning"].lower()


async def test_a_failed_microphone_stops_the_attempt_starting(client):
    token = await login(client, "student")
    payload = await _start(client, token)
    res = await client.post(
        f"/api/v1/student/attempts/{payload['attempt_id']}/env-check",
        json={"mic_ok": False}, headers=auth(token))
    assert res.status_code == 400


# -- retention -------------------------------------------------------------

async def test_expired_recordings_are_deleted_but_the_diagnosis_survives(client):
    """The audio goes; the features stay. That split is why they are separate
    tables — a student's progress history must outlive their voice."""
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)
    for item in payload["items"]:
        await _upload(client, token, attempt_id, item["response_id"], FLUENT())
    await client.post(f"/api/v1/student/attempts/{attempt_id}/submit", headers=auth(token))

    response_ids = [i["response_id"] for i in payload["items"]]
    async with tenant_sessionmaker(SLUG)() as session:
        rows = list((await session.execute(
            select(ResponseAudio).where(ResponseAudio.response_id.in_(response_ids))
        )).scalars().all())
        assert rows
        keys = [r.storage_key for r in rows]
        assert all(get_storage().exists(k) for k in keys)
        # Bring the retention date forward instead of waiting thirty days.
        for row in rows:
            row.delete_after = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    deleted, _ = await sweep_tenant(SLUG)
    assert deleted >= len(rows)

    assert not any(get_storage().exists(k) for k in keys)

    from app.models.tenant import FeatureRecord
    async with tenant_sessionmaker(SLUG)() as session:
        after = list((await session.execute(
            select(ResponseAudio).where(ResponseAudio.response_id.in_(response_ids))
        )).scalars().all())
        features = list((await session.execute(
            select(FeatureRecord).where(FeatureRecord.response_id.in_(response_ids))
        )).scalars().all())

    assert all(r.deleted_at is not None and r.storage_key == "" for r in after)
    assert features, "the diagnosis must outlive the recording"


async def test_the_sweeper_leaves_unexpired_recordings_alone(client):
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)
    await _upload(client, token, attempt_id, payload["items"][0]["response_id"], FLUENT())

    deleted, _ = await sweep_tenant(SLUG, dry_run=True)
    async with tenant_sessionmaker(SLUG)() as session:
        row = (await session.execute(
            select(ResponseAudio).where(
                ResponseAudio.response_id == payload["items"][0]["response_id"])
        )).scalar_one()
    assert row.deleted_at is None
    assert get_storage().exists(row.storage_key)


# -- listen-back -----------------------------------------------------------

async def test_a_student_can_play_back_their_own_recording(client):
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)
    item = payload["items"][0]
    await _upload(client, token, attempt_id, item["response_id"], FLUENT())

    res = await client.get(
        f"/api/v1/student/attempts/{attempt_id}/responses/{item['response_id']}/audio",
        headers=auth(token))
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/wav"
    assert len(res.content) > 1000
    # Private, and not cacheable by anything in between.
    assert "private" in res.headers.get("cache-control", "")


async def test_playback_needs_a_session(client):
    token = await login(client, "student")
    payload = await _start(client, token)
    item = payload["items"][0]
    res = await client.get(
        f"/api/v1/student/attempts/{payload['attempt_id']}/responses/{item['response_id']}/audio")
    assert res.status_code == 401


async def test_a_deleted_recording_says_so_rather_than_pretending_it_never_existed(client):
    """410, not 404. A student who asks for a recording we deleted deserves
    the real answer — it existed, its time was up, it is gone."""
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)
    item = payload["items"][0]
    await _upload(client, token, attempt_id, item["response_id"], FLUENT())

    async with tenant_sessionmaker(SLUG)() as session:
        row = (await session.execute(
            select(ResponseAudio).where(
                ResponseAudio.response_id == item["response_id"])
        )).scalar_one()
        row.delete_after = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    await sweep_tenant(SLUG)

    res = await client.get(
        f"/api/v1/student/attempts/{attempt_id}/responses/{item['response_id']}/audio",
        headers=auth(token))
    assert res.status_code == 410
    assert "retention" in res.json()["detail"].lower()


async def test_a_scored_answer_carries_everything_the_listen_back_needs(client):
    """The report is only as good as what the result payload can draw."""
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)
    for item in payload["items"]:
        await _upload(client, token, attempt_id, item["response_id"], FLUENT())

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(token))).json()
    while result["status"] != "scored":
        result = (await client.get(f"/api/v1/student/attempts/{attempt_id}/result",
                                   headers=auth(token))).json()

    answered = [r for r in result["responses"] if not r["skipped"]]
    assert answered
    for row in answered:
        assert row["has_audio"] is True
        # Present as fields even when the synthesised tone yields no words —
        # the page must never have to guess whether a key exists.
        assert isinstance(row["words"], list)
        assert isinstance(row["pauses"], list)
        assert isinstance(row["disfluencies"], list)


# -- the timer-stop case ---------------------------------------------------

def _truncate(samples, keep: float):
    """A recording that stops the instant the speaker does — what the runner
    produces when the response timer cuts."""
    return samples[: int(len(samples) * keep)]


async def test_a_recording_cut_by_the_timer_is_reported_as_running_out_of_time(client):
    """Scenario 7. The engine cannot otherwise tell "you ran out of time" from
    "these words were unclear": the words never said score as unclear and the
    accuracy they were never given a chance to earn is charged against them.
    A student reading the wrong one of those takes away the wrong lesson."""
    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)

    # Speech that runs to the final sample, with no trailing silence at all,
    # AND the client's statement that the window expired. Both are required
    # now (PM increment 2026-08-24): the acoustic signal alone cannot tell a
    # timeout from a candidate who pressed Stop mid-sentence, so a truncated
    # upload with no end reason no longer produces the timeout note --
    # tests/test_end_reason.py pins that side.
    for item in payload["items"]:
        await _upload(client, token, attempt_id, item["response_id"],
                      _truncate(FLUENT(), 0.72), ended_by="window_expired")

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(token))).json()
    while result["status"] != "scored":
        result = (await client.get(f"/api/v1/student/attempts/{attempt_id}/result",
                                   headers=auth(token))).json()

    answered = [r for r in result["responses"] if not r["skipped"]]
    assert answered
    assert any(r["ended_mid_speech"] for r in answered), \
        "speech running to the last sample should be detected as truncated"
    assert "ran out of time" in result["environment_note"]


async def test_a_recording_with_trailing_silence_is_not_called_truncated(client):
    """The other half: a student who finished and stopped must not be told
    they ran out of time."""
    import numpy as np

    token = await login(client, "student")
    payload = await _start(client, token)
    attempt_id = payload["attempt_id"]
    await _env_check(client, token, attempt_id)

    quiet_tail = np.concatenate([FLUENT(), silence(1.5)])
    for item in payload["items"]:
        await _upload(client, token, attempt_id, item["response_id"], quiet_tail)

    result = (await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                                headers=auth(token))).json()
    while result["status"] != "scored":
        result = (await client.get(f"/api/v1/student/attempts/{attempt_id}/result",
                                   headers=auth(token))).json()

    answered = [r for r in result["responses"] if not r["skipped"]]
    assert answered
    assert not any(r["ended_mid_speech"] for r in answered)
    assert "ran out of time" not in result["environment_note"]
