"""Authentication and role boundaries.

Each console is tested against the three roles that must not reach it, not
just the one that must. A guard that admits everybody passes a happy-path
test.
"""
from __future__ import annotations

import pytest

from app.security import decode_token
from tests.conftest import ACCOUNTS, DEMO_PASSWORD, auth, login

pytestmark = pytest.mark.asyncio


async def test_sign_in_issues_a_scoped_token(client):
    token = await login(client, "student")
    principal = decode_token(token)
    assert principal is not None
    assert principal.scope == "tenant"
    assert principal.role == "student"
    assert principal.tenant_slug == "stmarys"


async def test_platform_staff_get_a_token_with_no_institution(client):
    principal = decode_token(await login(client, "platform"))
    assert principal is not None
    assert principal.scope == "platform"
    assert principal.tenant_slug is None


async def test_a_wrong_password_and_an_unknown_email_look_identical(client):
    wrong = await client.post("/api/v1/auth/login",
                              json={"email": ACCOUNTS["student"], "password": "nope"})
    unknown = await client.post("/api/v1/auth/login",
                                json={"email": "nobody@nowhere.edu", "password": DEMO_PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    # Same message, or the response tells an attacker which emails are real.
    assert wrong.json()["detail"] == unknown.json()["detail"]


async def test_no_token_is_rejected(client):
    for path in ["/api/v1/student/home", "/api/v1/trainer/cohorts",
                 "/api/v1/tenant/overview", "/api/v1/platform/overview"]:
        assert (await client.get(path)).status_code == 401


async def test_a_garbage_token_is_rejected(client):
    res = await client.get("/api/v1/student/home",
                           headers={"Authorization": "Bearer not.a.real.token"})
    assert res.status_code == 401


@pytest.mark.parametrize("path,allowed", [
    ("/api/v1/student/home", "student"),
    ("/api/v1/trainer/cohorts", "trainer"),
    ("/api/v1/tenant/overview", "tenant_admin"),
    ("/api/v1/platform/overview", "platform"),
])
async def test_each_console_admits_only_its_own_role(client, path, allowed):
    for who in ["student", "trainer", "tenant_admin", "platform"]:
        token = await login(client, who)
        res = await client.get(path, headers=auth(token))
        if who == allowed:
            assert res.status_code == 200, f"{who} should reach {path}: {res.text}"
        elif path == "/api/v1/trainer/cohorts" and who == "tenant_admin":
            # A tenant admin sees the whole institution, including every
            # cohort — this is the one deliberate widening, and it narrows
            # rather than widens for trainers.
            assert res.status_code == 200
        else:
            assert res.status_code == 403, f"{who} must not reach {path}"


async def test_a_trainer_sees_only_their_own_cohorts(client):
    trainer = await login(client, "trainer")
    admin = await login(client, "tenant_admin")

    theirs = (await client.get("/api/v1/trainer/cohorts", headers=auth(trainer))).json()
    all_cohorts = (await client.get("/api/v1/tenant/cohorts", headers=auth(admin))).json()

    assert theirs, "the seeded trainer should have cohorts"
    assert len(theirs) < len(all_cohorts), "a trainer should not see every cohort"


async def test_a_trainer_cannot_open_a_cohort_they_do_not_own(client):
    trainer = await login(client, "trainer")
    admin = await login(client, "tenant_admin")

    theirs = {c["id"] for c in
              (await client.get("/api/v1/trainer/cohorts", headers=auth(trainer))).json()}
    every = {c["id"] for c in
             (await client.get("/api/v1/tenant/cohorts", headers=auth(admin))).json()}
    other = next(iter(every - theirs))

    res = await client.get(f"/api/v1/trainer/cohorts/{other}/readiness", headers=auth(trainer))
    # 404 rather than 403: confirming a cohort exists is itself a disclosure.
    assert res.status_code == 404


async def test_a_student_reads_only_their_own_record(client):
    """There is no student endpoint that takes another user's id."""
    from app.routers import student
    for route in student.router.routes:
        path = getattr(route, "path", "")
        assert "{user_id}" not in path, f"{path} lets a student name someone else"
