"""Can one person turn an identifier into somebody else's data.

Not a security audit. A boundary check over the objects this product actually
holds -- invitation, candidate, attempt, result, assessment, cohort -- asking
one question of each: if I change the id, do I get somebody else's?

Three boundaries, and they are enforced by different machinery, which is why
each needs its own test rather than one sweeping assertion:

* **Between institutions** is structural. Every tenant table is declared
  against the ``tenant`` placeholder and the schema comes from the signed
  token, so another institution's row is not forbidden -- it is not present.
  These tests confirm the property holds for the routes added most recently,
  where a mistake would be new.
* **Between people inside one institution** is a filter, and filters are what
  get forgotten. `_own_attempt`, `_one_of_mine` and the invitation lookup each
  do this work, and each is checked here against a real second person rather
  than against a made-up id.
* **Between roles** is `require_roles`, checked at the router.

The three routes added in the last two passes get particular attention:
``GET /student/attempts/resume``, ``GET /tenant/invitations/{id}/result`` and
``GET /trainer/attempts/{id}/result``. All three are new ways to turn an
identifier into a report.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import tenant_sessionmaker
from app.models.tenant import Attempt, Cohort, CohortMember, User
from tests.test_game_and_practice import SLUG, auth, login

pytestmark = pytest.mark.asyncio

OTHER = "vignan"


async def _published(client, admin, name: str) -> str:
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": name, "style": "company_round", "company": "Testco",
              "description": "x", "estimated_minutes": 6,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 1, "prep_seconds": 0,
                            "response_seconds": 20, "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})
    return created["id"]


async def _sat_candidate(client, name: str):
    """A candidate who has finished. Returns (token, invitation, attempt_id)."""
    admin = await login(client, "tenant_admin")
    profile_id = await _published(client, admin, f"Boundary - {name}")
    invitation = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": profile_id, "invited_name": name,
              "invited_email": "", "reference": "", "valid_days": 7})).json()
    claimed = (await client.post(f"/api/v1/invite/{invitation['token']}/claim",
                                 json={"full_name": name, "email": ""})).json()
    token = claimed["token"]
    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})
    attempt = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": profile_id, "mode": "official"})).json()
    await client.post(f"/api/v1/student/attempts/{attempt['attempt_id']}/submit",
                      headers=auth(token), json={})
    return token, invitation, attempt["attempt_id"]


# -- candidate to candidate -----------------------------------------------

async def test_a_candidate_cannot_read_another_candidates_result(client):
    """The one that would matter most: two people in one hiring round."""
    first_token, _, first_attempt = await _sat_candidate(client, "Boundary A")
    second_token, _, second_attempt = await _sat_candidate(client, "Boundary B")

    assert first_attempt != second_attempt

    crossed = await client.get(
        f"/api/v1/student/attempts/{second_attempt}/result",
        headers=auth(first_token))
    assert crossed.status_code == 404, (
        f"a candidate read another candidate's report ({crossed.status_code})")

    own = await client.get(f"/api/v1/student/attempts/{first_attempt}/result",
                           headers=auth(first_token))
    assert own.status_code == 200, "and their own report must still open"


async def test_resume_cannot_be_pointed_at_somebody_else(client):
    """`resume` takes no identifier at all, which is the reason it is safe.

    Asserted rather than assumed: the obvious next change to this endpoint is
    a `?candidate_id=` parameter for an admin view, and that is the change
    that would break it.
    """
    from app.main import app

    route = next(r for r in app.routes
                 if getattr(r, "path", "") == "/api/v1/student/attempts/resume")
    params = {p.name for p in route.dependant.path_params}
    params |= {p.name for p in route.dependant.query_params}
    assert not params, (
        f"resume now accepts {params}; it answers from the caller's own token "
        f"and must not take an identifier from them")


async def test_a_candidate_cannot_reach_the_admin_or_trainer_report_routes(client):
    token, invitation, attempt_id = await _sat_candidate(client, "Boundary C")

    for path in (f"/api/v1/tenant/invitations/{invitation['id']}/result",
                 f"/api/v1/trainer/attempts/{attempt_id}/result"):
        res = await client.get(path, headers=auth(token))
        assert res.status_code in (403, 404), (
            f"a candidate reached {path} with {res.status_code}")


# -- student to student ----------------------------------------------------

async def test_a_student_cannot_read_another_students_result(client):
    student = await login(client, "student")
    me = (await client.get("/api/v1/auth/me", headers=auth(student))).json()["id"]

    async with tenant_sessionmaker(SLUG)() as session:
        theirs = (await session.execute(
            select(Attempt.id).where(Attempt.user_id != me).limit(1)
        )).scalars().first()

    assert theirs is not None, (
        "the estate holds no attempt belonging to somebody else, so this "
        "boundary cannot be tested -- which is worse than it failing")

    res = await client.get(f"/api/v1/student/attempts/{theirs}/result",
                           headers=auth(student))
    assert res.status_code == 404, (
        f"a student read another person's report ({res.status_code})")

    # 404 rather than 403 on purpose: confirming an attempt exists is itself
    # a disclosure, so "not yours" and "not a thing" must look identical.
    assert "not found" in res.text.lower()


# -- trainer boundaries ----------------------------------------------------

async def test_a_trainer_cannot_read_a_student_outside_their_cohorts(client):
    """The new trainer report route, against a real out-of-cohort student."""
    trainer = await login(client, "trainer")

    cohorts = (await client.get("/api/v1/trainer/cohorts",
                                headers=auth(trainer))).json()
    mine = {c["id"] for c in cohorts}

    async with tenant_sessionmaker(SLUG)() as session:
        members = set((await session.execute(
            select(CohortMember.user_id)
            .where(CohortMember.cohort_id.in_(mine or [""])))).scalars().all())
        outsider = (await session.execute(
            select(Attempt).where(Attempt.user_id.not_in(members or [""]))
            .limit(1))).scalars().first()

    assert outsider is not None, "the estate has no out-of-cohort attempt to try"

    res = await client.get(f"/api/v1/trainer/attempts/{outsider.id}/result",
                           headers=auth(trainer))
    assert res.status_code == 404, (
        f"a trainer read a report for somebody outside their cohorts "
        f"({res.status_code})")

    listed = await client.get(
        f"/api/v1/trainer/students/{outsider.user_id}/attempts",
        headers=auth(trainer))
    assert listed.status_code == 404


async def test_a_trainer_can_read_their_own_cohort_student(client):
    """The guard must not have closed the door it was built to open."""
    trainer = await login(client, "trainer")
    cohorts = (await client.get("/api/v1/trainer/cohorts",
                                headers=auth(trainer))).json()
    assert cohorts, "this trainer has no cohorts to test with"

    students = (await client.get(
        f"/api/v1/trainer/cohorts/{cohorts[0]['id']}/students",
        headers=auth(trainer))).json()
    with_attempts = [s for s in students if s["attempts"]]
    assert with_attempts, "no student in this cohort has sat anything"

    user_id = with_attempts[0]["user"]["id"]
    listed = await client.get(f"/api/v1/trainer/students/{user_id}/attempts",
                              headers=auth(trainer))
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert rows, "a student with attempts listed none"

    scored = [a for a in rows if a["scored_at"]]
    if scored:
        report = await client.get(
            f"/api/v1/trainer/attempts/{scored[0]['id']}/result",
            headers=auth(trainer))
        assert report.status_code == 200, report.text


async def test_a_trainer_cannot_read_another_cohorts_student_list(client):
    trainer = await login(client, "trainer")
    mine = {c["id"] for c in (await client.get(
        "/api/v1/trainer/cohorts", headers=auth(trainer))).json()}

    async with tenant_sessionmaker(SLUG)() as session:
        other = (await session.execute(
            select(Cohort.id).where(Cohort.id.not_in(mine or [""]))
            .limit(1))).scalars().first()

    if other is None:
        pytest.skip("only one cohort in the estate")

    res = await client.get(f"/api/v1/trainer/cohorts/{other}/students",
                           headers=auth(trainer))
    assert res.status_code == 404


# -- across institutions ---------------------------------------------------

async def test_another_institution_cannot_read_an_invitation_result(client):
    _, invitation, _ = await _sat_candidate(client, "Boundary Cross")

    other = await login(client, "other_admin")
    res = await client.get(
        f"/api/v1/tenant/invitations/{invitation['id']}/result",
        headers=auth(other))
    assert res.status_code == 404, (
        f"another institution read this invitation's result "
        f"({res.status_code})")


async def test_another_institutions_trainer_cannot_read_this_attempt(client):
    """Structural, but the trainer report route is new and worth proving."""
    _, _, attempt_id = await _sat_candidate(client, "Boundary Cross Trainer")

    async with tenant_sessionmaker(OTHER)() as session:
        trainer = (await session.execute(
            select(User).where(User.role == "trainer",
                               User.active.is_(True)).limit(1))).scalars().first()

    if trainer is None:
        pytest.skip("the other institution has no trainer seeded")

    res = await client.post("/api/v1/auth/login",
                            json={"email": trainer.email,
                                  "password": "Password123!"})
    if res.status_code != 200:
        pytest.skip("cannot sign in as the other institution's trainer")

    crossed = await client.get(f"/api/v1/trainer/attempts/{attempt_id}/result",
                               headers=auth(res.json()["token"]))
    assert crossed.status_code == 404, (
        f"another institution's trainer read this attempt ({crossed.status_code})")


async def test_another_institution_cannot_read_this_assessment(client):
    admin = await login(client, "tenant_admin")
    profile_id = await _published(client, admin, "Boundary profile")

    other = await login(client, "other_admin")
    listed = (await client.get("/api/v1/tenant/profiles",
                               headers=auth(other))).json()
    assert not any(p["id"] == profile_id for p in listed), (
        "an assessment from another institution appeared in this library")

    # And with retired included, which is the wider query.
    everything = (await client.get(
        "/api/v1/tenant/profiles?include_retired=true",
        headers=auth(other))).json()
    assert not any(p["id"] == profile_id for p in everything)


async def test_another_institution_cannot_see_this_invitation_at_all(client):
    _, invitation, _ = await _sat_candidate(client, "Boundary Listing")

    other = await login(client, "other_admin")
    listed = (await client.get("/api/v1/tenant/invitations",
                               headers=auth(other))).json()
    assert not any(row["id"] == invitation["id"] for row in listed)


# -- what the trainer report says when there is nothing to say -------------

async def test_an_unfinished_attempt_is_listed_but_has_no_report(client):
    """A trainer must be able to tell "not finished" from "scored zero".

    The cohort table shows one number per student. Opening it and finding an
    attempt in progress has to read as in progress -- a report full of dashes,
    or worse a zero, would describe the student wrongly to the person coaching
    them.
    """
    trainer = await login(client, "trainer")
    cohorts = (await client.get("/api/v1/trainer/cohorts",
                                headers=auth(trainer))).json()
    students = (await client.get(
        f"/api/v1/trainer/cohorts/{cohorts[0]['id']}/students",
        headers=auth(trainer))).json()
    subject = students[0]["user"]

    # Start something as that student and leave it unfinished.
    signed = await client.post("/api/v1/auth/login",
                               json={"email": subject["email"],
                                     "password": "Password123!"})
    token = signed.json()["token"]
    await client.post("/api/v1/student/consent", headers=auth(token),
                      json={"scopes": ["recording"]})
    profiles = (await client.get("/api/v1/student/profiles",
                                 headers=auth(token))).json()
    started = (await client.post(
        "/api/v1/student/attempts", headers=auth(token),
        json={"profile_id": profiles[0]["id"], "mode": "practice"})).json()

    listed = (await client.get(
        f"/api/v1/trainer/students/{subject['id']}/attempts",
        headers=auth(trainer))).json()

    row = next((a for a in listed if a["id"] == started["attempt_id"]), None)
    assert row is not None, "an in-progress attempt is missing from the list"
    assert row["scored_at"] is None
    assert row["status"] != "scored", (
        "an attempt nobody has finished is being reported as scored")


async def test_the_trainer_report_carries_the_same_caveats_as_the_students(client):
    """One set of numbers, one set of warnings.

    A coaching view with the hedging removed would be a different claim about
    the same measurements, and a trainer repeating it to a student would be
    repeating something the product did not say.
    """
    trainer = await login(client, "trainer")
    cohorts = (await client.get("/api/v1/trainer/cohorts",
                                headers=auth(trainer))).json()
    students = (await client.get(
        f"/api/v1/trainer/cohorts/{cohorts[0]['id']}/students",
        headers=auth(trainer))).json()

    for summary in students:
        listed = (await client.get(
            f"/api/v1/trainer/students/{summary['user']['id']}/attempts",
            headers=auth(trainer))).json()
        scored = [a for a in listed if a["scored_at"]]
        if not scored:
            continue

        coach = (await client.get(
            f"/api/v1/trainer/attempts/{scored[0]['id']}/result",
            headers=auth(trainer))).json()

        assert "calibrated" in coach and "calibration_note" in coach
        assert coach["calibrated"] is False, (
            "the engine reports itself calibrated without a study")
        assert coach["calibration_note"], (
            "the coaching report drops the note saying the weights are "
            "unvalidated")
        return

    pytest.skip("no scored attempt in the trainer's cohorts")
