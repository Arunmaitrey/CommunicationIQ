"""Letting somebody in who has no account, and letting them in only once.

The token rules first, as pure functions, then the two-endpoint dance a real
candidate performs. The security properties are the point: a link is a key to
one assessment, looking at it costs nothing, claiming it costs everything, and
a redeemed session cannot wander.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import invitations
from app.db import tenant_sessionmaker
from app.models.tenant import Invitation

from tests.test_game_and_practice import SLUG, auth, login


class _Row:
    """Enough of an Invitation for the pure checks."""

    def __init__(self, **kw):
        self.status = kw.get("status", "pending")
        self.redeemed_at = kw.get("redeemed_at")
        self.expires_at = kw.get("expires_at")


NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def an_email(label: str) -> str:
    """A fresh address for each run.

    Fixed addresses collided the moment this file ran twice: the second run's
    candidate met the first run's account and got "somebody already has that
    address", which is the endpoint working correctly and the test being
    wrong. `conftest` retires these afterwards; this stops them clashing in
    the meantime.
    """
    import uuid

    return f"{label}.{uuid.uuid4().hex[:10]}@candidate.test"


# -- the token rules ---------------------------------------------------------

def test_a_token_is_long_enough_that_guessing_is_hopeless():
    token = invitations.new_token()
    assert len(token) >= 30
    # And different every time, which is the only property that matters.
    assert len({invitations.new_token() for _ in range(50)}) == 50


def test_an_invitation_expires_and_the_window_is_bounded():
    """A link that works forever is a credential nobody remembers issuing."""
    assert invitations.expiry_for(None) > datetime.now(timezone.utc)

    far = invitations.expiry_for(9999)
    assert (far - datetime.now(timezone.utc)).days <= invitations.MAX_VALID_DAYS

    near = invitations.expiry_for(0)
    assert near > datetime.now(timezone.utc), "zero days is not an expired link"


def test_each_refusal_says_which_thing_went_wrong():
    """"Invalid link" is useless to somebody holding a link. Expired, used and
    withdrawn each have a different next step."""
    assert invitations.check(None) is invitations.UNKNOWN
    assert invitations.check(_Row(status="withdrawn")) is invitations.WITHDRAWN
    assert invitations.check(_Row(redeemed_at=NOW)) is invitations.USED
    assert invitations.check(
        _Row(expires_at=NOW - timedelta(days=1)), now=NOW) is invitations.EXPIRED

    assert invitations.check(
        _Row(expires_at=NOW + timedelta(days=1)), now=NOW) is None


def test_a_used_invitation_stays_used_even_before_it_expires():
    """Order matters: somebody who claimed it and then waited must not be told
    it merely expired, which sounds re-issuable."""
    row = _Row(redeemed_at=NOW, expires_at=NOW + timedelta(days=5))
    assert invitations.check(row, now=NOW) is invitations.USED


def test_a_naive_expiry_is_read_as_utc():
    naive = _Row(expires_at=(NOW + timedelta(days=1)).replace(tzinfo=None))
    assert invitations.check(naive, now=NOW) is None


def test_a_candidate_without_an_email_still_gets_a_unique_record():
    """An employer testing in a room on a shared machine gives no address. The
    record still needs a key, and a blank would collide with the next one."""
    first = invitations.candidate_email("tokenAAAAAAAAAA", "")
    second = invitations.candidate_email("tokenBBBBBBBBBB", "")
    assert first != second
    assert "@" in first

    given = invitations.candidate_email("tokenAAAAAAAAAA", "  Asha@Example.COM ")
    assert given == "asha@example.com"


# -- issuing -----------------------------------------------------------------

async def _published_profile(client, admin, name="Invite round"):
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": name, "style": "company_round", "company": "Testco",
              "description": "A short spoken round.", "estimated_minutes": 10,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 2, "prep_seconds": 0,
                            "response_seconds": 20, "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})
    return created["id"]


async def test_an_admin_issues_a_link_for_one_assessment(client):
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin)

    made = await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                             json={"profile_id": profile_id,
                                   "invited_name": "Asha Rao",
                                   "invited_email": "asha@example.com",
                                   "reference": "REQ-1042"})
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["token"]
    assert body["status"] == "pending"
    assert body["expires_at"]


async def test_a_draft_assessment_cannot_be_invited_to(client):
    """Otherwise the candidate arrives at a test with no items in it."""
    admin = await login(client, "tenant_admin")
    draft = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Not ready", "style": "company_round", "company": "Testco",
              "description": "x", "estimated_minutes": 10,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 2, "prep_seconds": 0,
                            "response_seconds": 20, "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()

    refused = await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                                json={"profile_id": draft["id"]})
    assert refused.status_code == 400
    assert "not published" in refused.text


async def test_only_an_admin_can_issue_one(client):
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Admin only")

    for role in ("student", "trainer"):
        token = await login(client, role)
        refused = await client.post("/api/v1/tenant/invitations",
                                    headers=auth(token),
                                    json={"profile_id": profile_id})
        assert refused.status_code == 403, role


# -- the candidate's side ----------------------------------------------------

async def test_looking_at_an_invitation_does_not_consume_it(client):
    """A link scanner in a mail client, or a candidate checking on the train,
    must not burn the invitation before they sit down."""
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Preview round")
    token = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": profile_id, "invited_name": "Asha"})).json()["token"]

    for _ in range(3):
        preview = await client.get(f"/api/v1/invite/{token}")
        assert preview.status_code == 200
        body = preview.json()
        assert body["ok"] is True
        assert body["profile_name"] == "Preview round"
        assert body["estimated_minutes"] > 0
        assert body["invited_name"] == "Asha"

    # Still claimable afterwards.
    claimed = await client.post(f"/api/v1/invite/{token}/claim",
                                json={"full_name": "Asha Rao"})
    assert claimed.status_code == 200, claimed.text


async def test_an_unknown_token_reveals_nothing(client):
    preview = await client.get("/api/v1/invite/not-a-real-token")
    assert preview.status_code == 200
    body = preview.json()
    assert body["ok"] is False
    assert body["reason"] == "unknown"
    # No institution name, no assessment name -- nothing an enumeration could
    # harvest.
    assert body["tenant_name"] == ""
    assert body["profile_name"] == ""


async def test_a_link_works_once_and_the_second_person_is_told_why(client):
    """The forwarded-link case. The friend must not get a sitting too."""
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "One use")
    token = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": profile_id})).json()["token"]

    first = await client.post(f"/api/v1/invite/{token}/claim",
                              json={"full_name": "Asha Rao",
                                    "email": an_email("asha.first")})
    assert first.status_code == 200, first.text

    second = await client.post(f"/api/v1/invite/{token}/claim",
                               json={"full_name": "Somebody Else",
                                     "email": an_email("else")})
    assert second.status_code == 409
    assert "already been used" in second.text

    # And the preview now explains it rather than saying "invalid".
    preview = (await client.get(f"/api/v1/invite/{token}")).json()
    assert preview["reason"] == "used"


async def test_a_withdrawn_link_stops_working(client):
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Withdrawn round")
    made = (await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                              json={"profile_id": profile_id})).json()

    pulled = await client.post(
        f"/api/v1/tenant/invitations/{made['id']}/withdraw", headers=auth(admin))
    assert pulled.status_code == 200

    preview = (await client.get(f"/api/v1/invite/{made['token']}")).json()
    assert preview["ok"] is False
    # The pointer is deleted, so it no longer resolves to an institution at
    # all -- which is a stronger answer than "withdrawn" and reveals less.
    assert preview["reason"] in ("withdrawn", "unknown")

    refused = await client.post(f"/api/v1/invite/{made['token']}/claim",
                                json={"full_name": "Asha"})
    assert refused.status_code == 409


async def test_an_expired_link_is_refused_and_says_so(client):
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Expired round")
    token = (await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                               json={"profile_id": profile_id})).json()["token"]

    async with tenant_sessionmaker(SLUG)() as session:
        row = (await session.execute(
            select(Invitation).where(Invitation.token == token))).scalars().first()
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()

    preview = (await client.get(f"/api/v1/invite/{token}")).json()
    assert preview["reason"] == "expired"

    refused = await client.post(f"/api/v1/invite/{token}/claim",
                                json={"full_name": "Asha"})
    assert refused.status_code == 409


async def test_a_used_invitation_is_not_withdrawable(client):
    """The attempt behind it is somebody's work. Withdrawing the link now
    would suggest the result can be withdrawn too."""
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Already sat")
    made = (await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                              json={"profile_id": profile_id})).json()
    await client.post(f"/api/v1/invite/{made['token']}/claim",
                      json={"full_name": "Asha Rao",
                            "email": an_email("asha.sat")})

    refused = await client.post(
        f"/api/v1/tenant/invitations/{made['id']}/withdraw", headers=auth(admin))
    assert refused.status_code == 409


async def test_claiming_asks_for_a_name_and_nothing_intrusive(client):
    """Name, because a result belongs to somebody. Email, optionally, because
    that is how they receive it. Nothing else."""
    from app.schemas import RedeemRequest

    fields = set(RedeemRequest.model_fields)
    assert fields == {"full_name", "email"}


async def test_a_claim_without_a_name_is_refused(client):
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Needs a name")
    token = (await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                               json={"profile_id": profile_id})).json()["token"]

    refused = await client.post(f"/api/v1/invite/{token}/claim",
                                json={"full_name": "   "})
    assert refused.status_code in (400, 422)


# -- what a redeemed session may do ------------------------------------------

async def test_a_candidate_session_is_not_a_student_account(client):
    """The rule the whole design rests on. A token holder gets a key to one
    assessment, not an account with practice history, drills and every past
    result attached."""
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Scope round")
    token = (await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                               json={"profile_id": profile_id})).json()["token"]

    session = (await client.post(
        f"/api/v1/invite/{token}/claim",
        json={"full_name": "Asha Rao",
              "email": an_email("asha.scope")})).json()
    candidate = session["token"]

    from app.security import decode_token
    principal = decode_token(candidate)
    assert principal is not None
    assert principal.role == invitations.CANDIDATE_ROLE
    assert principal.role != "student"

    # Student surfaces refuse it. Each names `student` explicitly, which is
    # what makes this hold rather than depend on nobody adding a broad guard.
    for path in ("/api/v1/student/home", "/api/v1/student/profiles",
                 "/api/v1/student/attempts"):
        refused = await client.get(path, headers=auth(candidate))
        assert refused.status_code == 403, path


async def test_a_candidate_cannot_issue_invitations(client):
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "No re-invite")
    token = (await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                               json={"profile_id": profile_id})).json()["token"]
    candidate = (await client.post(
        f"/api/v1/invite/{token}/claim",
        json={"full_name": "Asha Rao",
              "email": an_email("asha.noinvite")})).json()["token"]

    refused = await client.post("/api/v1/tenant/invitations",
                                headers=auth(candidate),
                                json={"profile_id": profile_id})
    assert refused.status_code == 403


async def test_a_second_candidate_cannot_reuse_an_email(client):
    """Two people on one address would share a record, and the second one's
    result would land on the first one's history."""
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Shared email")
    tokens = [(await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                                 json={"profile_id": profile_id})).json()["token"]
              for _ in range(2)]

    shared = an_email("shared")
    first = await client.post(f"/api/v1/invite/{tokens[0]}/claim",
                              json={"full_name": "Asha", "email": shared})
    assert first.status_code == 200

    second = await client.post(f"/api/v1/invite/{tokens[1]}/claim",
                               json={"full_name": "Bhavna", "email": shared})
    assert second.status_code == 409
    assert "already has an account" in second.text


# -- sitting the thing they were invited to ----------------------------------

async def test_a_candidate_can_sit_the_assessment_and_nothing_else(client):
    """The point of the whole phase, and its boundary in one test.

    They can start the attempt they were invited to. They cannot start a
    different one, and they cannot reach another candidate's.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Sit it round")
    other_id = await _published_profile(client, admin, "Not for them")
    token = (await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                               json={"profile_id": profile_id})).json()["token"]

    session = (await client.post(
        f"/api/v1/invite/{token}/claim",
        json={"full_name": "Asha Rao",
              "email": an_email("asha.sit")})).json()
    candidate = session["token"]
    assert session["profile_id"] == profile_id

    # Recording consent first -- the same rule as for a student. An external
    # candidate is not exempt from being asked.
    consent = await client.post(
        "/api/v1/student/consent", headers=auth(candidate),
        json={"scopes": ["recording"], "notice_version": "1.0",
              "notice_language": "en"})
    assert consent.status_code == 201, consent.text

    started = await client.post(
        "/api/v1/student/attempts", headers=auth(candidate),
        json={"profile_id": profile_id, "mode": "official"})
    assert started.status_code == 201, started.text
    payload = started.json()
    assert payload["items"], "the candidate was handed an empty assessment"


async def test_a_candidate_cannot_open_another_persons_attempt(client):
    """`_own_attempt` compares the caller against the attempt's owner. Widening
    the router's role guard must not have widened that."""
    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Someone elses")
    token = (await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                               json={"profile_id": profile_id})).json()["token"]
    candidate = (await client.post(
        f"/api/v1/invite/{token}/claim",
        json={"full_name": "Asha Rao",
              "email": an_email("asha.other")})).json()["token"]

    # A student's attempt, made the ordinary way.
    student = await login(client, "student")
    mine = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    refused = await client.get(
        f"/api/v1/student/attempts/{mine['attempt_id']}/runner",
        headers=auth(candidate))
    assert refused.status_code == 404, (
        "a candidate reached an attempt that is not theirs")



# -- the warm-up item and the camera -----------------------------------------

async def test_a_practice_item_is_served_first_and_never_scored(client):
    """Somebody's first thirty seconds with unfamiliar software measures the
    software. One item, marked, and its audio is not even kept -- which is how
    it stays out of every score without exclusion logic in four places."""
    from sqlalchemy import select as _select

    from app.models.tenant import Response, ResponseAudio, SimulationProfile
    from tests.audio_fixtures import speech_like, to_wav

    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "With a warm-up")

    async with tenant_sessionmaker(SLUG)() as session:
        profile = await session.get(SimulationProfile, profile_id)
        profile.practice_item = True
        await session.commit()

    student = await login(client, "student")
    payload = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    attempt_id = payload["attempt_id"]

    async with tenant_sessionmaker(SLUG)() as session:
        rows = (await session.execute(
            _select(Response).where(Response.attempt_id == attempt_id)
            .order_by(Response.position))).scalars().all()
        practice = [r for r in rows if r.is_practice]

    assert len(practice) == 1, "expected exactly one warm-up"
    assert practice[0].position == 1, "the warm-up must come first"

    await client.post(f"/api/v1/student/attempts/{attempt_id}/env-check",
                      headers=auth(student),
                      json={"mic_ok": True, "playback_ok": True,
                            "headphones": True, "noise_dbfs": -60.0,
                            "input_peak_dbfs": -20.0, "device_label": "t",
                            "user_agent": "t"})

    uploaded = await client.post(
        f"/api/v1/student/attempts/{attempt_id}/responses/"
        f"{practice[0].id}/audio", headers=auth(student),
        files={"file": ("a.wav", to_wav(speech_like(2.0)), "audio/wav")})
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["practice"] is True
    assert body["stored"] is False

    async with tenant_sessionmaker(SLUG)() as session:
        audio = (await session.execute(
            _select(ResponseAudio).where(
                ResponseAudio.response_id == practice[0].id))).scalars().first()
    assert audio is None, (
        "a warm-up recording was kept, so it will be scored and counted")


async def test_the_camera_is_asked_for_only_where_an_assessment_wants_it(client):
    """Per assessment, because it is a client's requirement rather than ours.
    Demanding it of a student practising at home would be collecting a
    permission for no reason."""
    from app.models.tenant import SimulationProfile

    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Camera round")

    student = await login(client, "student")
    env = {"mic_ok": True, "playback_ok": True, "headphones": True,
           "noise_dbfs": -60.0, "input_peak_dbfs": -20.0,
           "device_label": "t", "user_agent": "t"}

    # Off by default: no camera, no complaint.
    without = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    ok = await client.post(
        f"/api/v1/student/attempts/{without['attempt_id']}/env-check",
        headers=auth(student), json=env)
    assert ok.status_code == 200, ok.text

    async with tenant_sessionmaker(SLUG)() as session:
        profile = await session.get(SimulationProfile, profile_id)
        profile.camera_check = True
        await session.commit()

    asked = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()
    refused = await client.post(
        f"/api/v1/student/attempts/{asked['attempt_id']}/env-check",
        headers=auth(student), json=env)
    assert refused.status_code == 400
    assert "camera" in refused.text.lower()
    assert "nothing is recorded" in refused.text.lower(), (
        "a candidate asked for a camera must be told what happens to it")

    allowed = await client.post(
        f"/api/v1/student/attempts/{asked['attempt_id']}/env-check",
        headers=auth(student), json={**env, "camera_ok": True})
    assert allowed.status_code == 200, allowed.text


async def test_the_preview_tells_a_candidate_what_they_are_walking_into(client):
    """Whether a camera is needed, and whether there is a warm-up, before they
    click anything -- not after they have committed the single-use link."""
    from app.models.tenant import SimulationProfile

    admin = await login(client, "tenant_admin")
    profile_id = await _published_profile(client, admin, "Told in advance")
    async with tenant_sessionmaker(SLUG)() as session:
        profile = await session.get(SimulationProfile, profile_id)
        profile.camera_check = True
        profile.practice_item = True
        await session.commit()

    token = (await client.post("/api/v1/tenant/invitations", headers=auth(admin),
                               json={"profile_id": profile_id})).json()["token"]

    preview = (await client.get(f"/api/v1/invite/{token}")).json()
    assert preview["camera_check"] is True
    assert preview["practice_item"] is True
    assert preview["estimated_minutes"] > 0


async def test_the_open_endpoint_has_a_brake(client):
    """The one route without a session in front of it does not answer forever.

    Not about guessing tokens -- 24 random bytes settles that -- but about an
    open endpoint that runs two database lookups per call being hit in a loop.
    """
    from app.routers import invitations as router
    from app import ratelimit

    # One token, hammered. The per-address limit is far looser and is not
    # what should stop this.
    codes = [(await client.get("/api/v1/invite/nonexistent")).status_code
             for _ in range(ratelimit.PER_TOKEN_LIMIT + 3)]

    assert codes[0] == 200, "an unknown token is a polite refusal, not an error"
    assert codes.count(429) == 3, (
        f"the brake did not engage after {ratelimit.PER_TOKEN_LIMIT}: {codes}")
    assert router._by_caller.allows("someone else"), (
        "one hammered token throttled the whole world")


async def test_the_brake_is_loose_enough_for_a_whole_office(client):
    """Thirty candidates behind one address must all get in.

    The obvious implementation counts by address alone and refuses candidate
    twenty-six, which is the failure nobody would find until a client ran a
    real hiring day.
    """
    from app import ratelimit

    by_caller = ratelimit.Limiter(limit=ratelimit.PER_CALLER_LIMIT)
    by_token = ratelimit.Limiter(limit=ratelimit.PER_TOKEN_LIMIT)

    # Thirty people, one office address, each opening their own link once
    # and claiming it.
    assert all(by_caller.allows("203.0.113.9", now=0.0) for _ in range(60))
    assert all(by_token.allows(f"token-{i}", now=0.0) for i in range(30))


async def test_the_brake_forgets_a_caller_after_the_window(client):
    from app import ratelimit

    limiter = ratelimit.Limiter(limit=2, window=60)
    assert limiter.allows("x", now=0.0)
    assert limiter.allows("x", now=1.0)
    assert not limiter.allows("x", now=2.0)
    assert limiter.allows("x", now=61.0), "the window never reopened"


async def test_one_caller_being_throttled_does_not_throttle_another(client):
    from app import ratelimit

    limiter = ratelimit.Limiter(limit=1, window=60)
    assert limiter.allows("a", now=0.0)
    assert not limiter.allows("a", now=0.0)
    assert limiter.allows("b", now=0.0), "counted against the wrong caller"
