"""The assessment clock.

Pure arithmetic first, then the two things that matter at the API: a new
answer is refused after the deadline, and a submit is not. The asymmetry is
the invariant -- expiry means the candidate did not reach the rest, not that
what they said is void.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import deadline

from tests.test_game_and_practice import SLUG, auth, login

NOON = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def test_an_attempt_that_never_started_has_no_deadline():
    """The clock starts at the environment check, not when somebody opened
    the page and went to find headphones."""
    assert deadline.deadline_for(None, 20) is None
    clock = deadline.clock_for(None, 20, now=NOON)
    assert clock.deadline_at is None
    assert clock.seconds_remaining is None
    assert not clock.expired
    assert deadline.accepts_answer(None, 20, now=NOON)


def test_the_allowance_is_the_estimate_plus_grace():
    """The estimate assumes every window is used in full and nobody hesitates.
    Cutting a real candidate off at exactly that would expire most honest
    sittings."""
    assert deadline.allowance_minutes(60) == 90
    assert deadline.allowance_minutes(20) == 30
    # A short round gets a floor rather than a proportional pittance: half of
    # six minutes is three, and three minutes of grace on a six-minute round
    # is tighter than it sounds.
    assert deadline.allowance_minutes(6) == 11
    assert deadline.allowance_minutes(0) >= 1


def test_the_countdown_runs_down_and_stops_at_zero():
    started = NOON
    early = deadline.clock_for(started, 20, now=NOON + timedelta(minutes=5))
    assert early.seconds_remaining == 25 * 60
    assert not early.expired

    late = deadline.clock_for(started, 20, now=NOON + timedelta(minutes=45))
    assert late.seconds_remaining == 0, "never negative"
    assert late.expired


def test_an_answer_in_flight_at_the_bell_is_still_taken():
    """Refusing the answer somebody submitted at the last second, whose
    request was still crossing the network, punishes latency rather than
    lateness."""
    started = NOON
    at_deadline = NOON + timedelta(minutes=30)

    assert deadline.accepts_answer(started, 20, now=at_deadline)
    assert deadline.accepts_answer(
        started, 20, now=at_deadline + timedelta(seconds=10))
    assert not deadline.accepts_answer(
        started, 20, now=at_deadline + timedelta(seconds=60))


def test_a_naive_start_time_is_read_as_utc():
    """Postgres hands back an aware datetime, but a fixture or an older row
    may not. Subtracting a naive from an aware one raises, and it would raise
    inside the answer path."""
    naive = NOON.replace(tzinfo=None)
    assert deadline.deadline_for(naive, 10) == deadline.deadline_for(NOON, 10)


# -- at the API --------------------------------------------------------------

async def _started_attempt(client, token, profile_id):
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    await client.post(
        f"/api/v1/student/attempts/{payload['attempt_id']}/env-check",
        headers=auth(token),
        json={"mic_ok": True, "playback_ok": True, "headphones": True,
              "noise_dbfs": -60.0, "input_peak_dbfs": -20.0,
              "device_label": "test", "user_agent": "test"})
    return payload


async def _reading_profile(client, admin):
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Deadline round", "style": "company_round",
              "company": "Testco", "description": "x", "estimated_minutes": 10,
              "sections": [{"title": "Reading",
                            "task_type": "reading_comprehension",
                            "item_count": 3, "prep_seconds": 0,
                            "response_seconds": 0, "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})
    return created["id"]


async def test_the_runner_is_told_the_deadline_and_the_server_clock(client):
    """A countdown that trusted the device clock would expire an attempt early
    on a laptop whose time is wrong. Both numbers are sent so the client can
    take the difference once."""
    admin = await login(client, "tenant_admin")
    profile_id = await _reading_profile(client, admin)
    student = await login(client, "student")

    payload = await _started_attempt(client, student, profile_id)
    runner = (await client.get(
        f"/api/v1/student/attempts/{payload['attempt_id']}/runner",
        headers=auth(student))).json()

    assert runner["deadline_at"], "no deadline after the environment check"
    assert runner["server_now"], "no server clock to correct against"
    assert runner["seconds_remaining"] > 0
    # 10-minute round, so 15 minutes of allowance.
    assert 14 * 60 < runner["seconds_remaining"] <= 15 * 60


async def test_an_expired_sitting_refuses_a_new_answer_and_still_submits(client):
    """The invariant, end to end.

    Wound forward by editing `started_at` rather than by waiting, so the test
    is deterministic and takes a millisecond.
    """
    from sqlalchemy import select

    from app.db import tenant_sessionmaker
    from app.models.tenant import Attempt

    admin = await login(client, "tenant_admin")
    profile_id = await _reading_profile(client, admin)
    student = await login(client, "student")
    payload = await _started_attempt(client, student, profile_id)
    attempt_id = payload["attempt_id"]

    items = payload["items"]
    assert len(items) >= 2, "need one answer before the bell and one after"

    # One answer while there is still time.
    first = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/"
        f"{items[0]['response_id']}/answer",
        headers=auth(student), json={"selected_index": 0})
    assert first.status_code == 201, first.text

    # The bell.
    async with tenant_sessionmaker(SLUG)() as session:
        attempt = (await session.execute(
            select(Attempt).where(Attempt.id == attempt_id))).scalars().first()
        attempt.started_at = datetime.now(timezone.utc) - timedelta(hours=3)
        await session.commit()

    late = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/"
        f"{items[1]['response_id']}/answer",
        headers=auth(student), json={"selected_index": 0})
    # 410 rather than 409: the runner reads 409 as "the server already has
    # this" and deletes its queued copy, so the two refusals must not share a
    # code. See `_within_deadline`.
    assert late.status_code == 410, late.text
    assert "run out" in late.text

    # And the work that exists is kept.
    result = await client.post(f"/api/v1/student/attempts/{attempt_id}/submit",
                               headers=auth(student), json={})
    assert result.status_code == 200, result.text
    body = result.json()
    # By what was scored, not by `skipped` -- that flag defaults to False, so
    # an item nobody ever reached reads exactly like one that was answered.
    # Asserting on it would have passed whatever the deadline did.
    scored = [r for r in body["responses"] if r.get("scores")]
    assert len(scored) == 1, (
        f"expected the one pre-deadline answer to survive, got {len(scored)}")


async def test_expiry_does_not_reach_back_into_a_finished_attempt(client):
    """An attempt already submitted is read back whatever the clock says. A
    result that stopped being readable once its deadline passed would be a
    strange kind of record."""
    from datetime import timedelta as _td

    from sqlalchemy import select

    from app.db import tenant_sessionmaker
    from app.models.tenant import Attempt

    admin = await login(client, "tenant_admin")
    profile_id = await _reading_profile(client, admin)
    student = await login(client, "student")
    payload = await _started_attempt(client, student, profile_id)
    attempt_id = payload["attempt_id"]

    for item in payload["items"]:
        await client.post(
            f"/api/v1/student/attempts/{attempt_id}/responses/"
            f"{item['response_id']}/answer",
            headers=auth(student), json={"selected_index": 0})
    assert (await client.post(
        f"/api/v1/student/attempts/{attempt_id}/submit",
        headers=auth(student), json={})).status_code == 200

    async with tenant_sessionmaker(SLUG)() as session:
        attempt = (await session.execute(
            select(Attempt).where(Attempt.id == attempt_id))).scalars().first()
        attempt.started_at = datetime.now(timezone.utc) - _td(hours=5)
        await session.commit()

    again = await client.get(f"/api/v1/student/attempts/{attempt_id}/result",
                             headers=auth(student))
    assert again.status_code == 200, again.text


def test_a_recording_gets_a_recovery_window_an_answer_does_not():
    """The correction that matters most in this phase.

    A chosen or written answer is composed at the moment it is sent, so
    refusing it after the bell refuses a late answer. A recording is not: the
    audio existed before the bell, and the request carrying it may be a retry
    after a dropped connection or a reload. Refusing that discards an answer
    the candidate gave inside their own time -- which is the silent loss the
    whole phase exists to prevent, arriving through the door built to prevent
    it.

    The first version of this applied one rule to both paths. It would have
    thrown away exactly the recordings the retry queue was written to save.
    """
    start = NOON
    bell = start + timedelta(minutes=30)      # 20-minute round

    just_after = bell + timedelta(minutes=2)
    assert not deadline.accepts_answer(start, 20, now=just_after)
    assert deadline.accepts_recording(start, 20, now=just_after), (
        "a retry two minutes after the bell must still deliver its audio")

    # Bounded, though. It is a recovery window, not an extension of the test.
    long_after = bell + timedelta(minutes=30)
    assert not deadline.accepts_recording(start, 20, now=long_after)


async def test_a_retry_after_the_bell_still_delivers_its_audio(client):
    """End to end, with real audio.

    The queue's whole purpose is that a recording made in time survives a
    connection that was not. If the server refuses it on arrival, the queue is
    a device for storing answers nobody will ever score.
    """
    from datetime import timedelta as _td

    from sqlalchemy import select

    from app.db import tenant_sessionmaker
    from app.models.tenant import Attempt

    from tests.audio_fixtures import speech_like, to_wav

    admin = await login(client, "tenant_admin")
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Late upload", "style": "company_round",
              "company": "Testco", "description": "x", "estimated_minutes": 10,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 2, "prep_seconds": 0,
                            "response_seconds": 20, "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})

    student = await login(client, "student")
    payload = await _started_attempt(client, student, created["id"])
    attempt_id = payload["attempt_id"]

    # The bell rings while the recording is still on the candidate's device.
    async with tenant_sessionmaker(SLUG)() as session:
        attempt = (await session.execute(
            select(Attempt).where(Attempt.id == attempt_id))).scalars().first()
        attempt.started_at = (datetime.now(timezone.utc)
                              - _td(minutes=17))      # 15 allowance, 2 past
        await session.commit()

    wav = to_wav(speech_like(3.0))
    late = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/"
        f"{payload['items'][0]['response_id']}/audio",
        headers=auth(student),
        files={"file": ("answer.wav", wav, "audio/wav")})
    assert late.status_code == 201, late.text

    # A *fresh* answer at the same moment is refused, which is the asymmetry.
    # It carries no composition stamp, so it is what it looks like: somebody
    # answering after the bell.
    refused = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/"
        f"{payload['items'][1]['response_id']}/answer",
        headers=auth(student), json={"text": "typed after the bell"})
    assert refused.status_code == 410


async def test_a_recording_from_a_different_day_is_refused(client):
    """The window is a recovery path, not an open door. Somebody uploading an
    hour later is not recovering from a dropped connection."""
    from datetime import timedelta as _td

    from sqlalchemy import select

    from app.db import tenant_sessionmaker
    from app.models.tenant import Attempt

    from tests.audio_fixtures import speech_like, to_wav

    admin = await login(client, "tenant_admin")
    profile_id = await _reading_profile(client, admin)
    student = await login(client, "student")
    payload = await _started_attempt(client, student, profile_id)
    attempt_id = payload["attempt_id"]

    async with tenant_sessionmaker(SLUG)() as session:
        attempt = (await session.execute(
            select(Attempt).where(Attempt.id == attempt_id))).scalars().first()
        attempt.started_at = datetime.now(timezone.utc) - _td(days=1)
        await session.commit()

    late = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/"
        f"{payload['items'][0]['response_id']}/audio",
        headers=auth(student),
        files={"file": ("answer.wav", to_wav(speech_like(2.0)), "audio/wav")})
    assert late.status_code == 410
    assert "too long after" in late.text


async def test_a_typed_answer_given_in_time_survives_a_late_delivery(client):
    """The fix for the gap Phase 7 left behind.

    A candidate writes a paragraph, the POST carrying it fails, and the
    browser queues it and retries. By the time the connection comes back the
    bell has rung. Before this, the retry was refused and -- worse -- the
    runner had already called `skip`, so the paragraph became a recorded
    refusal to answer. One-shot means they never see the question again.

    The stamp is what separates the two cases: this answer was set down inside
    the candidate's own time, and only its delivery is late.
    """
    from sqlalchemy import select

    from app.db import tenant_sessionmaker
    from app.models.tenant import Attempt

    admin = await login(client, "tenant_admin")
    profile_id = await _reading_profile(client, admin)
    student = await login(client, "student")
    payload = await _started_attempt(client, student, profile_id)
    attempt_id = payload["attempt_id"]
    items = payload["items"]
    assert len(items) >= 2, "need a queued answer and a fresh one"

    # Wind the start back so the bell has rung two minutes ago -- past the
    # late tolerance, inside the recovery window -- and stamp the answer a
    # minute before it, which is when the candidate actually gave it.
    async with tenant_sessionmaker(SLUG)() as session:
        attempt = (await session.execute(
            select(Attempt).where(Attempt.id == attempt_id))).scalars().first()
        allowance = deadline.allowance_minutes(
            await _profile_minutes(session, attempt))
        attempt.started_at = (datetime.now(timezone.utc)
                              - timedelta(minutes=allowance + 2))
        composed = attempt.started_at + timedelta(minutes=allowance - 1)
        await session.commit()

    recovered = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/"
        f"{items[0]['response_id']}/answer",
        headers=auth(student),
        json={"selected_index": 0, "composed_at": composed.isoformat()})
    assert recovered.status_code == 201, recovered.text

    # And the window is not an extension: a stamp from after the bell is
    # somebody still answering, and gets the same refusal as no stamp at all.
    still_typing = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/"
        f"{items[1]['response_id']}/answer",
        headers=auth(student),
        json={"selected_index": 0,
              "composed_at": datetime.now(timezone.utc).isoformat()})
    assert still_typing.status_code == 410, still_typing.text


async def _profile_minutes(session, attempt) -> int:
    from app.models.tenant import SimulationProfile
    profile = await session.get(SimulationProfile, attempt.profile_id)
    return profile.estimated_minutes if profile else 0
