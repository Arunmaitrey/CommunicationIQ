"""The bulk report export — the one deliberate door through the tenant wall.

Everything here is about the rules the door ships with, not the CSV
formatting. The wall itself (platform staff cannot read student data) is
proved by test_tenant_isolation.py; these tests prove the exception is
exactly as wide as designed: one role, one tenant per call, logged, and
carrying nothing that executes on the operator's machine.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from tests.conftest import auth, login

pytestmark = pytest.mark.asyncio


async def _tenant_id(client: httpx.AsyncClient, token: str, slug: str) -> str:
    res = await client.get("/api/v1/platform/tenants", headers=auth(token))
    assert res.status_code == 200, res.text
    return next(t["id"] for t in res.json() if t["slug"] == slug)


async def _export(client: httpx.AsyncClient, token: str,
                  tenant_id: str) -> zipfile.ZipFile:
    res = await client.get(f"/api/v1/platform/tenants/{tenant_id}/export.zip",
                           headers=auth(token))
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("application/zip")
    return zipfile.ZipFile(io.BytesIO(res.content))


async def test_only_the_super_admin_can_export(client: httpx.AsyncClient):
    """Every other role gets a refusal — including the tenant's own admin.

    The tenant admin case matters most: they can see their students inside
    the product, so a 403 here looks almost wrong. But this endpoint hangs
    off the platform prefix and resolves any tenant by id; letting a tenant
    role through it would mean trusting the handler body, forever, to check
    that the id names their own institution. The guard on the router makes
    that class of bug unrepresentable.
    """
    platform = await login(client, "platform")
    tenant_id = await _tenant_id(client, platform, "stmarys")
    url = f"/api/v1/platform/tenants/{tenant_id}/export.zip"

    for who in ("student", "trainer", "tenant_admin", "other_admin"):
        res = await client.get(url, headers=auth(await login(client, who)))
        assert res.status_code == 403, f"{who}: {res.status_code}"

    assert (await client.get(url)).status_code == 401


async def test_other_platform_staff_are_refused_too(client: httpx.AsyncClient):
    """finance, support, content, data_ml: platform scope is not enough.

    This endpoint is the first ever to use require_platform's narrowing arm,
    which means that arm had shipped without a single test executing it. No
    such staff account is seeded, so the tokens are minted directly — the
    guard reads the token, not the database, and that is precisely what is
    under test.
    """
    from app.security import TokenPrincipal, create_token

    platform = await login(client, "platform")
    tenant_id = await _tenant_id(client, platform, "stmarys")
    url = f"/api/v1/platform/tenants/{tenant_id}/export.zip"

    for role in ("finance", "support", "content", "data_ml"):
        token = create_token(TokenPrincipal(
            user_id="00000000-0000-0000-0000-000000000000",
            email=f"{role}@saashx.ai", full_name=f"Suite {role}",
            role=role, scope="platform"))
        res = await client.get(url, headers=auth(token))
        assert res.status_code == 403, f"{role}: {res.status_code}"


async def test_an_unknown_tenant_is_a_404(client: httpx.AsyncClient):
    platform = await login(client, "platform")
    res = await client.get("/api/v1/platform/tenants/no-such-tenant/export.zip",
                           headers=auth(platform))
    assert res.status_code == 404


async def test_the_export_holds_one_tenant_and_only_that_tenant(
        client: httpx.AsyncClient):
    """The ZIP for vignan must not contain a single stmarys address.

    This is the isolation guarantee restated for the one endpoint that is
    allowed inside a schema. The slug the handler opens comes from the
    control-plane registry row, so crossing tenants would need the registry
    itself to be wrong — but a test that assumes the implementation is the
    implementation proves nothing, so: export both, check the water line.
    """
    platform = await login(client, "platform")

    seen: dict[str, str] = {}
    for slug in ("stmarys", "vignan"):
        zf = await _export(client, platform,
                           await _tenant_id(client, platform, slug))
        assert set(zf.namelist()) == {"README.txt", "students.csv",
                                      "attempts.csv", "report_measures.csv",
                                      "skill_mastery.csv"}
        seen[slug] = "".join(zf.read(name).decode("utf-8")
                             for name in zf.namelist() if name.endswith(".csv"))

    assert "@stmarys.edu" in seen["stmarys"]
    assert "@vignan.edu" not in seen["stmarys"]
    assert "@stmarys.edu" not in seen["vignan"]


async def test_the_export_carries_real_scores_with_their_caveats(
        client: httpx.AsyncClient):
    """A scored attempt's overall number appears, and so does the warning.

    The README's calibration caveat is part of the contract, not decoration:
    this file will be forwarded to people who never saw the product's
    "not validated" badges, and the export is the last place the caveat can
    travel with the numbers.
    """
    platform = await login(client, "platform")
    zf = await _export(client, platform,
                       await _tenant_id(client, platform, "stmarys"))

    attempts = list(csv.DictReader(io.StringIO(zf.read("attempts.csv").decode())))
    scored = [a for a in attempts if a["status"] == "scored"]
    assert scored, "the demo estate seeds scored attempts"
    # At least one carries an overall. Not all: an attempt scored on a
    # server without speech models legitimately has none (an overall needs
    # three measures), and this suite runs on exactly such a server.
    assert any(a["overall_score"] for a in scored)

    measures = list(csv.DictReader(
        io.StringIO(zf.read("report_measures.csv").decode())))
    assert any(m["dimension"] == "overall" for m in measures)
    # Provenance travels with every number (ENG-21).
    assert all(m["provider_key"] for m in measures)

    readme = zf.read("README.txt").decode()
    assert "UNCALIBRATED" in readme
    assert "No audio" in readme
    # Programmatic consumers are warned about the defusal apostrophe.
    assert "apostrophe" in readme


async def test_candidates_are_in_the_export_and_their_names_cannot_execute(
        client: httpx.AsyncClient):
    """An invited candidate's report is exported, disarmed.

    Two findings from review, one fixture. First: candidates are User rows
    with role "candidate", and sitting an assessment is the entire reason
    they exist — the first version filtered on role == "student" and dropped
    them silently from a file that reads as complete. Second: the formula
    defusal was only ever unit-tested; nothing proved the endpoint actually
    routes institution-typed text through it. So: one candidate whose name
    is a spreadsheet payload, created directly in the schema (the invitation
    flow is tested elsewhere; this is about the export), asserted present
    and inert, then removed.
    """
    from app.db import tenant_sessionmaker
    from app.models.tenant import Attempt, ScoreRecord, SimulationProfile, User

    payload = '=HYPERLINK("http://evil.example","Suite Candidate")'
    email = "suite.export.candidate@stmarys.edu"
    maker = tenant_sessionmaker("stmarys")

    async with maker() as ts:
        from sqlalchemy import select
        profile_id = (await ts.execute(
            select(SimulationProfile.id).limit(1))).scalar_one()
        user = User(email=email, full_name=payload, password_hash="",
                    role="candidate", active=False)
        ts.add(user)
        await ts.flush()
        attempt = Attempt(user_id=user.id, profile_id=profile_id,
                          status="scored", mode="official")
        ts.add(attempt)
        await ts.flush()
        ts.add(ScoreRecord(attempt_id=attempt.id, response_id=None,
                           dimension="overall", score=55.0, band="Competent",
                           confidence=0.5, provider_key="suite",
                           provider_version="0"))
        await ts.commit()
        user_id, attempt_id = user.id, attempt.id

    try:
        platform = await login(client, "platform")
        zf = await _export(client, platform,
                           await _tenant_id(client, platform, "stmarys"))

        people = list(csv.DictReader(io.StringIO(zf.read("students.csv").decode())))
        row = next(p for p in people if p["email"] == email)
        assert row["role"] == "candidate"
        # Present, and defused: the payload survives for a human reader but
        # cannot open as a formula.
        assert row["full_name"] == "'" + payload

        attempts = list(csv.DictReader(io.StringIO(zf.read("attempts.csv").decode())))
        mine = next(a for a in attempts if a["student_email"] == email)
        assert mine["overall_score"] == "55.0"

        measures = list(csv.DictReader(
            io.StringIO(zf.read("report_measures.csv").decode())))
        assert any(m["student_email"] == email for m in measures)
    finally:
        async with maker() as ts:
            from sqlalchemy import delete
            await ts.execute(delete(ScoreRecord)
                             .where(ScoreRecord.attempt_id == attempt_id))
            await ts.execute(delete(Attempt).where(Attempt.id == attempt_id))
            await ts.execute(delete(User).where(User.id == user_id))
            await ts.commit()


async def test_the_export_is_audit_logged(client: httpx.AsyncClient):
    """A row newer than the request exists, naming the actor and tenant.

    The first version of this test looked for *any* matching row — which the
    persistent demo estate always has after the first ever run, so deleting
    the audit call entirely would have kept it green. The assertion is now
    anchored to a timestamp taken before the export.
    """
    platform = await login(client, "platform")
    tenant_id = await _tenant_id(client, platform, "vignan")

    before = datetime.now(timezone.utc) - timedelta(seconds=2)
    res = await client.get(f"/api/v1/platform/tenants/{tenant_id}/export.zip",
                           headers=auth(platform))
    assert res.status_code == 200

    audit_rows = (await client.get("/api/v1/platform/audit?limit=10",
                                   headers=auth(platform))).json()
    fresh = [r for r in audit_rows
             if r["action"] == "tenant.reports_exported"
             and r["entity_id"] == tenant_id
             and datetime.fromisoformat(r["at"].replace("Z", "+00:00")) >= before]
    assert fresh, "no audit row newer than this export"
    assert fresh[0]["actor_type"] == "platform_user"


async def test_every_status_exports_and_a_missing_schema_refuses_cleanly(
        client: httpx.AsyncClient):
    """A closed tenant still exports; a schema-less registry row answers 409.

    drop_tenant_schema's own contract says offboarding completes "the
    contracted data export first" — this endpoint is that export, so status
    must never block it. And a row whose schema is already gone (offboarded,
    or half-provisioned) is a state the registry permits, so it must answer
    with a reason rather than a stack trace.
    """
    from app.db import platform_sessionmaker
    from app.models.platform import Tenant
    from app.provisioning import create_tenant_schema, drop_tenant_schema

    platform = await login(client, "platform")

    held = Tenant(name="Suite Export Hold", slug="suite_export_hold",
                  status="closed")
    ghost = Tenant(name="Suite Export Ghost", slug="suite_export_ghost",
                   status="offboarding")
    async with platform_sessionmaker()() as session:
        session.add_all([held, ghost])
        await session.commit()
        held_id, ghost_id = held.id, ghost.id
    await create_tenant_schema("suite_export_hold")
    # suite_export_ghost deliberately gets no schema.

    try:
        zf = await _export(client, platform, held_id)
        people = list(csv.DictReader(io.StringIO(zf.read("students.csv").decode())))
        assert people == []  # header only — an empty estate is not an error

        res = await client.get(
            f"/api/v1/platform/tenants/{ghost_id}/export.zip",
            headers=auth(platform))
        assert res.status_code == 409
        assert "schema" in res.json()["detail"]
    finally:
        await drop_tenant_schema("suite_export_hold", purge_media=False)
        async with platform_sessionmaker()() as session:
            from sqlalchemy import delete
            await session.execute(
                delete(Tenant).where(Tenant.id.in_((held_id, ghost_id))))
            await session.commit()


async def test_schema_drift_is_not_disguised_as_a_missing_schema(
        client: httpx.AsyncClient):
    """A stale schema (missing a column) must not export as 409 "not found".

    The two failures share an exception type — ProgrammingError — and the
    first version of the handler caught both, so a schema that missed a
    column migration would tell the operator "the schema does not exist" and
    send them to re-provision a tenant that is already there, burying the
    drift. They are told apart by SQLSTATE: 42P01 (undefined_table, also a
    whole missing schema) is the clean 409; 42703 (undefined_column) is
    drift and must surface, not masquerade.

    Proven by inflicting the drift: a throwaway tenant loses a column the
    export reads, and the response is anything but the 409 reserved for a
    genuinely absent schema. The companion case — 42P01 really does 409 — is
    test_every_status_exports_and_a_missing_schema_refuses_cleanly above.
    """
    from sqlalchemy import delete, text
    from app.db import platform_sessionmaker, tenant_sessionmaker
    from app.models.platform import Tenant
    from app.provisioning import (create_tenant_schema, drop_tenant_schema,
                                  tenant_schema_name)

    drifted = Tenant(name="Suite Export Drift", slug="suite_export_drift",
                     status="active")
    async with platform_sessionmaker()() as session:
        session.add(drifted)
        await session.commit()
        drifted_id = drifted.id
    await create_tenant_schema("suite_export_drift")

    schema = tenant_schema_name("suite_export_drift")
    async with tenant_sessionmaker("suite_export_drift")() as ts:
        # branch is read into students.csv; removing it is exactly the drift
        # a skipped migration produces.
        await ts.execute(text(f'ALTER TABLE "{schema}".users DROP COLUMN branch'))
        await ts.commit()

    try:
        platform = await login(client, "platform")
        # The point of the fix: drift is re-raised, not dressed up as a 409.
        # The test client propagates an unhandled app exception (in production
        # Starlette's ServerErrorMiddleware turns the same error into a logged
        # 500) — so a raised ProgrammingError here IS the "surfaces as a real
        # fault" behaviour, and the absence of a 409 is the whole fix.
        from sqlalchemy.exc import ProgrammingError
        with pytest.raises(ProgrammingError) as caught:
            await client.get(
                f"/api/v1/platform/tenants/{drifted_id}/export.zip",
                headers=auth(platform))
        assert getattr(caught.value.orig, "sqlstate", None) == "42703"
    finally:
        await drop_tenant_schema("suite_export_drift", purge_media=False)
        async with platform_sessionmaker()() as session:
            await session.execute(
                delete(Tenant).where(Tenant.id == drifted_id))
            await session.commit()


def test_spreadsheet_formulas_are_disarmed():
    """The defusal itself, at unit level — the wiring is proved above."""
    from app.routers.platform_export import _disarm

    assert _disarm('=HYPERLINK("http://x","go")') == '\'=HYPERLINK("http://x","go")'
    assert _disarm("@SUM(A1)") == "'@SUM(A1)"
    assert _disarm("+1+2") == "'+1+2"
    assert _disarm("-2+3") == "'-2+3"
    assert _disarm("\t=cmd()") == "'\t=cmd()"
    # Untouched: ordinary text, and numbers — a negative score is data.
    assert _disarm("Aarav Reddy") == "Aarav Reddy"
    assert _disarm(-3.5) == -3.5
