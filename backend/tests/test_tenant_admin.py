"""The institution console: import, seats, cohorts, assignments, flags.

The tests that matter here are the refusals. Anyone can write an import that
works on a clean file; the question is what happens to the file a placement
officer actually has.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

from app.db import platform_sessionmaker, tenant_sessionmaker
from app.models.platform import TenantUserDirectory
from app.importer import parse
from app.models.tenant import Cohort, CohortMember, User
from tests.conftest import auth, login

pytestmark = pytest.mark.asyncio

SLUG = "stmarys"

GOOD_CSV = """Name,Email ID,Roll No,Branch,Year,Mother Tongue,Cohort
Ramya Krishnan,ramya.k@stmarys.edu,20B81A9001,CSE,4,tamil,CSE-A Final Year
Imran Sheikh,imran.s@stmarys.edu,20B81A9002,CSE,4,hindi,CSE-A Final Year
"""


# -- the parser ------------------------------------------------------------

def test_unfamiliar_column_names_are_understood():
    """A sheet exported from a college ERP does not say 'full_name'."""
    plan = parse(GOOD_CSV)
    assert plan.ok, plan.problems
    assert len(plan.rows) == 2
    assert plan.rows[0].full_name == "Ramya Krishnan"
    assert plan.rows[0].roll_number == "20B81A9001"
    assert plan.rows[0].l1_language == "tamil"
    assert plan.rows[0].cohort == "CSE-A Final Year"


def test_a_byte_order_mark_does_not_hide_the_email_column():
    """Excel on Windows adds one, and it turns 'email' into '\\ufeffemail'."""
    plan = parse("﻿" + GOOD_CSV)
    assert plan.ok, plan.problems


def test_blank_rows_in_the_middle_are_not_errors():
    plan = parse(GOOD_CSV.replace("Imran", "\n\nImran"))
    assert plan.ok, plan.problems


def test_every_problem_is_reported_not_just_the_first():
    """An admin fixing one error per upload gives up before row twenty."""
    bad = """Name,Email
Valid Person,valid@stmarys.edu
No Email Person,not-an-email
,blank.name@stmarys.edu
Duplicate,valid@stmarys.edu
"""
    plan = parse(bad)
    assert not plan.ok
    assert len(plan.problems) >= 3
    lines = {p.line for p in plan.problems}
    assert {3, 4, 5} <= lines


def test_a_file_with_no_email_column_says_so_clearly():
    plan = parse("Name,Roll\nSomebody,123\n")
    assert not plan.ok
    assert any("email" in p.message.lower() for p in plan.problems)


def test_an_empty_file_is_rejected():
    assert not parse("").ok
    assert not parse("Name,Email\n").ok


def test_a_bad_year_or_role_is_caught():
    plan = parse("Name,Email,Year\nA Person,a@x.edu,9\n")
    assert any(p.column == "year_of_study" for p in plan.problems)

    plan = parse("Name,Email,Role\nA Person,a@x.edu,principal\n")
    assert any(p.column == "role" for p in plan.problems)


# -- the endpoint ----------------------------------------------------------

async def _cleanup(emails: list[str]) -> None:
    """Remove imported accounts, including their sign-in routing."""
    async with tenant_sessionmaker(SLUG)() as session:
        users = list((await session.execute(
            select(User).where(User.email.in_(emails)))).scalars().all())
        for user in users:
            await session.execute(delete(CohortMember).where(
                CohortMember.user_id == user.id))
            await session.delete(user)
        await session.commit()

    async with platform_sessionmaker()() as ps:
        await ps.execute(delete(TenantUserDirectory).where(
            TenantUserDirectory.email.in_(emails)))
        await ps.commit()


async def test_preview_changes_nothing_and_says_what_it_would_do(client):
    token = await login(client, "tenant_admin")
    before = len((await client.get("/api/v1/tenant/users", headers=auth(token))).json())

    res = await client.post("/api/v1/tenant/users/import/preview",
                            json={"csv_text": GOOD_CSV}, headers=auth(token))
    assert res.status_code == 200
    preview = res.json()
    assert preview["ok"] is True
    assert preview["creating"] == 2
    assert preview["updating"] == 0
    assert preview["sample"][0]["action"] == "create"

    after = len((await client.get("/api/v1/tenant/users", headers=auth(token))).json())
    assert after == before, "preview must not write anything"


async def test_an_import_creates_people_and_returns_their_first_password(client):
    token = await login(client, "tenant_admin")
    try:
        res = await client.post("/api/v1/tenant/users/import",
                                json={"csv_text": GOOD_CSV}, headers=auth(token))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["created"] == 2
        assert set(body["temporary_passwords"]) == {"ramya.k@stmarys.edu",
                                                    "imran.s@stmarys.edu"}

        # And they can actually sign in with it, then are made to change it.
        email = "ramya.k@stmarys.edu"
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": body["temporary_passwords"][email]})
        assert login_res.status_code == 200
        assert login_res.json()["user"]["must_change_password"] is True
    finally:
        await _cleanup(["ramya.k@stmarys.edu", "imran.s@stmarys.edu"])


async def test_re_importing_updates_a_profile_and_never_a_password(client):
    token = await login(client, "tenant_admin")
    try:
        first = await client.post("/api/v1/tenant/users/import",
                                  json={"csv_text": GOOD_CSV}, headers=auth(token))
        password = first.json()["temporary_passwords"]["ramya.k@stmarys.edu"]

        changed = GOOD_CSV.replace("Ramya Krishnan", "Ramya Krishnan Iyer")
        second = await client.post("/api/v1/tenant/users/import",
                                   json={"csv_text": changed}, headers=auth(token))
        assert second.json()["updated"] == 2
        assert second.json()["created"] == 0
        assert second.json()["temporary_passwords"] == {}

        # The original password still works — a re-import must not lock anyone out.
        again = await client.post("/api/v1/auth/login",
                                  json={"email": "ramya.k@stmarys.edu",
                                        "password": password})
        assert again.status_code == 200

        users = (await client.get("/api/v1/tenant/users", headers=auth(token))).json()
        renamed = next(u for u in users if u["email"] == "ramya.k@stmarys.edu")
        assert renamed["full_name"] == "Ramya Krishnan Iyer"
    finally:
        await _cleanup(["ramya.k@stmarys.edu", "imran.s@stmarys.edu"])


async def test_a_file_with_problems_imports_nothing_at_all(client):
    """All or nothing. A half-imported cohort leaves an admin guessing."""
    token = await login(client, "tenant_admin")
    bad = GOOD_CSV + "Broken Row,not-an-email,,,,,\n"
    res = await client.post("/api/v1/tenant/users/import",
                            json={"csv_text": bad}, headers=auth(token))
    assert res.status_code == 400

    users = (await client.get("/api/v1/tenant/users", headers=auth(token))).json()
    assert not any(u["email"] == "ramya.k@stmarys.edu" for u in users)


async def test_an_import_over_the_seat_limit_is_refused_in_full(client):
    token = await login(client, "tenant_admin")
    seats = (await client.get("/api/v1/tenant/seats", headers=auth(token))).json()

    rows = "\n".join(f"Person {i},bulk{i}@stmarys.edu"
                     for i in range(seats["remaining"] + 5))
    csv_text = "Name,Email\n" + rows + "\n"

    preview = (await client.post("/api/v1/tenant/users/import/preview",
                                 json={"csv_text": csv_text},
                                 headers=auth(token))).json()
    assert preview["over_seat_limit"] is True
    assert preview["ok"] is False

    res = await client.post("/api/v1/tenant/users/import",
                            json={"csv_text": csv_text}, headers=auth(token))
    assert res.status_code == 409
    assert "seat" in res.json()["detail"].lower()

    users = (await client.get("/api/v1/tenant/users", headers=auth(token))).json()
    assert not any(u["email"].startswith("bulk") for u in users)


async def test_an_import_creates_the_cohort_it_names(client):
    token = await login(client, "tenant_admin")
    csv_text = "Name,Email,Cohort\nNew Student,newcohort@stmarys.edu,MBA Final Year\n"
    try:
        res = await client.post("/api/v1/tenant/users/import",
                                json={"csv_text": csv_text}, headers=auth(token))
        assert "MBA Final Year" in res.json()["cohorts_created"]

        cohorts = (await client.get("/api/v1/tenant/cohorts", headers=auth(token))).json()
        created = next(c for c in cohorts if c["name"] == "MBA Final Year")
        assert created["member_count"] == 1
    finally:
        await _cleanup(["newcohort@stmarys.edu"])
        async with tenant_sessionmaker(SLUG)() as session:
            await session.execute(delete(Cohort).where(Cohort.name == "MBA Final Year"))
            await session.commit()


# -- seats and accounts ----------------------------------------------------

async def test_an_admin_cannot_lock_themselves_out(client):
    token = await login(client, "tenant_admin")
    me = (await client.get("/api/v1/auth/me", headers=auth(token))).json()

    deactivate = await client.patch(f"/api/v1/tenant/users/{me['id']}",
                                    json={"active": False}, headers=auth(token))
    assert deactivate.status_code == 400

    demote = await client.patch(f"/api/v1/tenant/users/{me['id']}",
                                json={"role": "student"}, headers=auth(token))
    assert demote.status_code == 400


async def test_a_trainer_cannot_reach_the_admin_console(client):
    token = await login(client, "trainer")
    for method, path, body in [
        ("post", "/api/v1/tenant/users/import", {"csv_text": GOOD_CSV}),
        ("post", "/api/v1/tenant/cohorts", {"name": "Sneaky"}),
        ("get", "/api/v1/tenant/seats", None),
    ]:
        call = getattr(client, method)
        res = await (call(path, json=body, headers=auth(token)) if body
                     else call(path, headers=auth(token)))
        assert res.status_code == 403, path


# -- cohorts and assignments -----------------------------------------------

async def test_moving_the_drive_date_is_recorded(client):
    token = await login(client, "tenant_admin")
    cohorts = (await client.get("/api/v1/tenant/cohorts", headers=auth(token))).json()
    cohort = cohorts[0]
    new_date = (datetime.now(timezone.utc) + timedelta(days=70))

    res = await client.patch(f"/api/v1/tenant/cohorts/{cohort['id']}", headers=auth(token),
                             json={"name": cohort["name"], "branch": cohort["branch"],
                                   "section": cohort["section"],
                                   "trainer_id": cohort["trainer_id"],
                                   "drive_start": new_date.isoformat()})
    assert res.status_code == 200

    platform = await login(client, "platform")
    events = (await client.get("/api/v1/platform/audit", headers=auth(platform))).json()
    assert any(e["action"] == "cohort.updated" for e in events)


async def test_a_deadline_in_the_past_is_refused(client):
    token = await login(client, "tenant_admin")
    cohorts = (await client.get("/api/v1/tenant/cohorts", headers=auth(token))).json()
    profiles = (await client.get("/api/v1/tenant/profiles", headers=auth(token))).json()
    published = next(p for p in profiles if p["status"] == "published")

    res = await client.post("/api/v1/tenant/assignments", headers=auth(token), json={
        "cohort_id": cohorts[0]["id"], "profile_id": published["id"],
        "due_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
    assert res.status_code == 400


async def test_a_draft_simulation_cannot_be_assigned(client):
    """A draft is unfinished content; assigning one hands students a test the
    institution has not signed off.

    The draft is created here rather than looked for. It used to be whichever
    profile happened to be seeded unpublished, and when that profile was
    finished and published the test quietly became a skip -- the assertion
    stopped running and the suite still reported green. A test that depends on
    demo data tests the demo data.
    """
    token = await login(client, "tenant_admin")
    cohorts = (await client.get("/api/v1/tenant/cohorts", headers=auth(token))).json()

    created = await client.post(
        "/api/v1/tenant/profiles", headers=auth(token),
        json={"name": "Draft under test", "style": "company_round",
              "company": "Testco", "description": "Created by this test.",
              "estimated_minutes": 5,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "instructions": "", "item_count": 2,
                            "prep_seconds": 5, "response_seconds": 20,
                            "prompt_plays_allowed": 0, "allow_replay": False}]})
    assert created.status_code == 201, created.text
    draft = created.json()
    assert draft["status"] == "draft", "a new profile must not arrive published"

    res = await client.post("/api/v1/tenant/assignments", headers=auth(token),
                            json={"cohort_id": cohorts[0]["id"],
                                  "profile_id": draft["id"]})
    assert res.status_code == 400


async def test_an_assignment_can_be_created_and_withdrawn_before_anyone_starts(client):
    token = await login(client, "tenant_admin")
    cohorts = (await client.get("/api/v1/tenant/cohorts", headers=auth(token))).json()
    profiles = (await client.get("/api/v1/tenant/profiles", headers=auth(token))).json()
    published = next(p for p in profiles if p["status"] == "published")

    created = await client.post("/api/v1/tenant/assignments", headers=auth(token), json={
        "cohort_id": cohorts[0]["id"], "profile_id": published["id"],
        "due_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()})
    assert created.status_code == 201
    assignment = created.json()
    assert assignment["total"] > 0

    listed = (await client.get("/api/v1/tenant/assignments", headers=auth(token))).json()
    assert any(a["id"] == assignment["id"] for a in listed)

    deleted = await client.delete(f"/api/v1/tenant/assignments/{assignment['id']}",
                                  headers=auth(token))
    assert deleted.status_code == 200


# -- trainer flags and momentum --------------------------------------------

async def test_a_trainer_flags_a_student_and_resolves_it(client):
    token = await login(client, "trainer")
    cohorts = (await client.get("/api/v1/trainer/cohorts", headers=auth(token))).json()
    students = (await client.get(
        f"/api/v1/trainer/cohorts/{cohorts[0]['id']}/students",
        headers=auth(token))).json()

    raised = await client.post("/api/v1/trainer/flags", headers=auth(token), json={
        "user_id": students[0]["user"]["id"], "reason": "at_risk",
        "note": "Missed two sessions."})
    assert raised.status_code == 201
    flag = raised.json()
    assert flag["student_name"] == students[0]["user"]["full_name"]

    open_flags = (await client.get("/api/v1/trainer/flags", headers=auth(token))).json()
    assert any(f["id"] == flag["id"] for f in open_flags)

    resolved = await client.post(f"/api/v1/trainer/flags/{flag['id']}/resolve",
                                 headers=auth(token))
    assert resolved.status_code == 200

    still_open = (await client.get("/api/v1/trainer/flags", headers=auth(token))).json()
    assert not any(f["id"] == flag["id"] for f in still_open)


async def test_a_trainer_cannot_flag_a_student_outside_their_cohorts(client):
    trainer = await login(client, "trainer")
    admin = await login(client, "tenant_admin")

    mine = {c["id"] for c in
            (await client.get("/api/v1/trainer/cohorts", headers=auth(trainer))).json()}
    every = (await client.get("/api/v1/tenant/cohorts", headers=auth(admin))).json()
    other = next(c for c in every if c["id"] not in mine)

    async with tenant_sessionmaker(SLUG)() as session:
        outsider = (await session.execute(
            select(CohortMember.user_id).where(CohortMember.cohort_id == other["id"])
        )).scalars().first()

    res = await client.post("/api/v1/trainer/flags", headers=auth(trainer),
                            json={"user_id": outsider, "reason": "at_risk"})
    assert res.status_code == 404


async def test_momentum_suggests_rather_than_messages(client):
    """TRN-06: the output is a note to the trainer. Nothing reaches the student."""
    token = await login(client, "trainer")
    rows = (await client.get("/api/v1/trainer/momentum", headers=auth(token))).json()
    assert rows

    for row in rows:
        assert set(row) >= {"suggest_flag", "suggestion", "days_since_activity"}
        if row["suggest_flag"]:
            assert row["suggestion"], "a suggestion must say why"
            assert "days" in row["suggestion"]

    # Sorted so the people needing attention are at the top.
    flags = [r["suggest_flag"] for r in rows]
    assert flags == sorted(flags, reverse=True)

    # And no notification was produced by looking.
    from app.models.tenant import NotificationLog
    async with tenant_sessionmaker(SLUG)() as session:
        sent = (await session.execute(select(NotificationLog))).scalars().all()
    assert not sent


@pytest.mark.asyncio
async def test_the_library_leaves_out_retired_assessments_by_default(client):
    """Retiring is permanent, so the library must not grow forever.

    An assessment leaves circulation by being retired rather than deleted,
    because attempts name their profile and a result whose profile vanished
    cannot be read back. The rows therefore accumulate for the life of the
    tenant -- 1466 of them on the demo estate, returned with their sections
    attached in a 1.25 MB response, and rendered as 1466 cards on the screen
    an admin actually works in.

    Not a seeding artefact: it is what any customer's library becomes.
    """
    from sqlalchemy import select

    from app.db import tenant_sessionmaker
    from app.models.tenant import SimulationProfile

    admin = await login(client, "tenant_admin")
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "Library visibility", "style": "company_round",
              "company": "Testco", "description": "x", "estimated_minutes": 10,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 1, "prep_seconds": 0,
                            "response_seconds": 20,
                            "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()

    visible = (await client.get("/api/v1/tenant/profiles",
                                headers=auth(admin))).json()
    assert any(p["id"] == created["id"] for p in visible), (
        "a live assessment is missing from the library")

    async with tenant_sessionmaker("stmarys")() as session:
        row = await session.get(SimulationProfile, created["id"])
        row.status = "retired"
        await session.commit()

    after = (await client.get("/api/v1/tenant/profiles",
                              headers=auth(admin))).json()
    assert not any(p["id"] == created["id"] for p in after), (
        "a retired assessment is still in the default library")

    # Hidden, not lost. An admin who asks can still see it -- otherwise this
    # is deletion with extra steps, and the row exists precisely so somebody
    # can look at what a past result was scored against.
    shown = (await client.get(
        "/api/v1/tenant/profiles?include_retired=true",
        headers=auth(admin))).json()
    assert any(p["id"] == created["id"] for p in shown), (
        "asking for retired assessments did not return them")


@pytest.mark.asyncio
async def test_hiding_retired_assessments_actually_shrinks_the_response(client):
    """The point was the payload, not the tidiness.

    Asserted as a ratio rather than a byte count, so it keeps meaning
    something as the estate changes.
    """
    admin = await login(client, "tenant_admin")

    lean = (await client.get("/api/v1/tenant/profiles",
                             headers=auth(admin))).json()
    full = (await client.get("/api/v1/tenant/profiles?include_retired=true",
                             headers=auth(admin))).json()

    assert len(lean) < len(full), (
        "the default library is no smaller than the full one -- either the "
        "filter is not applied or the estate has no retired rows to prove it "
        "with")
