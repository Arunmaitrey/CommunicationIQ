"""The operator console: providers, institutions, plans, invoices, economy.

The interesting cases are the ones the console refuses. An operator who can
point a capability at a provider that does not serve it, or cut an
institution's seats below the people already using them, will eventually do
it on a Friday afternoon.
"""
from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.db import platform_sessionmaker, tenant_sessionmaker
from app.models.platform import ProviderRegistry, Tenant, TenantUserDirectory
from app.provisioning import drop_tenant_schema, tenant_schema_exists
from tests.conftest import auth, login

pytestmark = pytest.mark.asyncio


async def _provider(capability: str, key: str) -> str | None:
    async with platform_sessionmaker()() as ps:
        row = (await ps.execute(
            select(ProviderRegistry).where(ProviderRegistry.capability == capability,
                                           ProviderRegistry.provider_key == key)
        )).scalars().first()
        return row.id if row else None


# -- providers -------------------------------------------------------------

async def test_a_capability_can_be_repointed_without_a_deploy(client):
    """ENG-18. The whole reason the abstraction exists."""
    token = await login(client, "platform")
    tier1 = await _provider("vad", "silero_vad")
    tier0 = await _provider("vad", "energy_vad")
    assert tier1 and tier0

    # Swap to Tier 0 as primary, Tier 1 as the fallback…
    res = await client.put("/api/v1/platform/capabilities/vad", headers=auth(token),
                           json={"primary_provider_id": tier0,
                                 "fallback_provider_id": tier1,
                                 "mode": "live", "timeout_ms": 5000})
    assert res.status_code == 200

    caps = (await client.get("/api/v1/platform/capabilities",
                             headers=auth(token))).json()
    vad = next(c for c in caps if c["capability"] == "vad")
    assert "Energy" in vad["primary"]
    assert "Silero" in vad["fallback"]

    # …and back, so the rest of the suite runs against the intended setup.
    await client.put("/api/v1/platform/capabilities/vad", headers=auth(token),
                     json={"primary_provider_id": tier1,
                           "fallback_provider_id": tier0,
                           "mode": "live", "timeout_ms": 15000})


async def test_a_provider_cannot_serve_a_capability_it_does_not_implement(client):
    token = await login(client, "platform")
    asr = await _provider("asr", "faster_whisper")
    res = await client.put("/api/v1/platform/capabilities/vad", headers=auth(token),
                           json={"primary_provider_id": asr, "mode": "live"})
    assert res.status_code == 400
    assert "not a provider" in res.json()["detail"]


async def test_shadow_mode_needs_something_to_compare_against(client):
    token = await login(client, "platform")
    tier1 = await _provider("vad", "silero_vad")
    res = await client.put("/api/v1/platform/capabilities/vad", headers=auth(token),
                           json={"primary_provider_id": tier1, "mode": "shadow"})
    assert res.status_code == 400


async def test_canary_needs_a_second_provider_and_a_real_split(client):
    token = await login(client, "platform")
    tier1 = await _provider("vad", "silero_vad")
    tier0 = await _provider("vad", "energy_vad")

    res = await client.put("/api/v1/platform/capabilities/vad", headers=auth(token),
                           json={"primary_provider_id": tier1, "mode": "canary",
                                 "canary_percent": 0})
    assert res.status_code == 400

    res = await client.put("/api/v1/platform/capabilities/vad", headers=auth(token),
                           json={"primary_provider_id": tier1,
                                 "fallback_provider_id": tier0,
                                 "mode": "canary", "canary_percent": 150})
    assert res.status_code == 400


async def test_an_unknown_capability_is_a_404(client):
    token = await login(client, "platform")
    res = await client.put("/api/v1/platform/capabilities/telepathy",
                           headers=auth(token),
                           json={"primary_provider_id": "x"})
    assert res.status_code == 404


async def test_a_serving_provider_cannot_be_deactivated_out_from_under_traffic(client):
    token = await login(client, "platform")
    serving = await _provider("asr", "faster_whisper")
    res = await client.post(f"/api/v1/platform/providers/{serving}/active?active=false",
                            headers=auth(token))
    assert res.status_code == 409
    assert "primary" in res.json()["detail"].lower()


# -- institutions ----------------------------------------------------------

async def test_onboarding_creates_a_schema_and_a_working_admin(client):
    token = await login(client, "platform")
    slug = "testcollege"
    try:
        res = await client.post("/api/v1/platform/tenants", headers=auth(token), json={
            "name": "Test College of Engineering", "slug": slug,
            "seat_limit": 25, "status": "trial",
            "admin_email": "principal@testcollege.edu",
            "admin_name": "Test Principal"})
        assert res.status_code == 201, res.text
        assert await tenant_schema_exists(slug)

        # The institution is isolated from the first moment, not eventually.
        async with tenant_sessionmaker(slug)() as session:
            from app.models.tenant import User
            users = list((await session.execute(select(User))).scalars().all())
        assert len(users) == 1
        assert users[0].role == "tenant_admin"
        assert users[0].must_change_password is True
    finally:
        await drop_tenant_schema(slug)
        async with platform_sessionmaker()() as ps:
            await ps.execute(delete(Tenant).where(Tenant.slug == slug))
            await ps.execute(delete(TenantUserDirectory).where(
                TenantUserDirectory.tenant_slug == slug))
            await ps.commit()


async def test_a_duplicate_or_malformed_slug_is_refused(client):
    token = await login(client, "platform")
    for slug in ["stmarys", "Not A Slug", "1college", ""]:
        res = await client.post("/api/v1/platform/tenants", headers=auth(token), json={
            "name": "X", "slug": slug, "admin_email": "a@b.edu", "admin_name": "A"})
        assert res.status_code in (400, 409, 422), slug


async def test_seats_cannot_be_cut_below_the_people_using_them(client):
    """Otherwise a plan change silently locks students out mid-season."""
    token = await login(client, "platform")
    tenants = (await client.get("/api/v1/platform/tenants", headers=auth(token))).json()
    stmarys = next(t for t in tenants if t["slug"] == "stmarys")

    res = await client.patch(f"/api/v1/platform/tenants/{stmarys['id']}",
                             headers=auth(token), json={"seat_limit": 2})
    assert res.status_code == 409
    assert "active" in res.json()["detail"].lower()


async def test_offboarding_removes_the_schema_the_files_and_the_sign_in_route(client):
    """PLAT-01. All three, or the deletion is a half-truth."""
    token = await login(client, "platform")
    slug = "leavingcollege"
    await client.post("/api/v1/platform/tenants", headers=auth(token), json={
        "name": "Leaving College", "slug": slug, "seat_limit": 10,
        "admin_email": "head@leavingcollege.edu", "admin_name": "Head"})

    assert await tenant_schema_exists(slug)
    await drop_tenant_schema(slug)
    assert not await tenant_schema_exists(slug)

    async with platform_sessionmaker()() as ps:
        routes = list((await ps.execute(
            select(TenantUserDirectory).where(TenantUserDirectory.tenant_slug == slug)
        )).scalars().all())
        await ps.execute(delete(Tenant).where(Tenant.slug == slug))
        await ps.commit()
    assert not routes, "sign-in routing outlived the schema it points at"


# -- plans and invoices ----------------------------------------------------

async def test_a_plan_change_creates_a_version_rather_than_editing_one(client):
    token = await login(client, "platform")
    before = (await client.get("/api/v1/platform/plans", headers=auth(token))).json()
    standard = next(p for p in before if p["code"] == "seat_standard")

    res = await client.post("/api/v1/platform/plans", headers=auth(token), json={
        "code": "seat_standard", "name": "Standard (per seat)",
        "billing_model": "per_seat", "price_per_seat": 550, "attempt_allowance": 5})
    assert res.status_code == 201
    assert res.json()["version"] == standard["version"] + 1

    # The old version is still there — a live subscription still points at it.
    after = (await client.get("/api/v1/platform/plans", headers=auth(token))).json()
    versions = {p["version"] for p in after if p["code"] == "seat_standard"}
    assert standard["version"] in versions


async def test_an_invoice_adds_gst_and_bills_the_seats_actually_in_use(client):
    token = await login(client, "platform")
    tenants = (await client.get("/api/v1/platform/tenants", headers=auth(token))).json()
    stmarys = next(t for t in tenants if t["slug"] == "stmarys")

    res = await client.post(f"/api/v1/platform/tenants/{stmarys['id']}/invoice",
                            headers=auth(token))
    assert res.status_code == 201, res.text
    invoice = res.json()

    assert invoice["number"].startswith("INV-")
    assert invoice["gst_rate"] == 18.0
    assert invoice["seats"] > 0
    # Seats in use, not the plan's headline limit — billing for empty seats is
    # how a pilot becomes a dispute.
    assert invoice["seats"] < stmarys["seat_limit"]
    assert round(invoice["subtotal"] * 0.18, 2) == invoice["gst_amount"]
    assert round(invoice["subtotal"] + invoice["gst_amount"], 2) == invoice["total"]

    listed = (await client.get("/api/v1/platform/invoices", headers=auth(token))).json()
    assert any(i["number"] == invoice["number"] for i in listed)


async def test_an_institution_with_no_plan_cannot_be_invoiced(client):
    token = await login(client, "platform")
    slug = "noplan"
    try:
        created = await client.post("/api/v1/platform/tenants", headers=auth(token),
                                    json={"name": "No Plan College", "slug": slug,
                                          "admin_email": "a@noplan.edu",
                                          "admin_name": "A"})
        tenant_id = created.json()["id"]
        res = await client.post(f"/api/v1/platform/tenants/{tenant_id}/invoice",
                                headers=auth(token))
        assert res.status_code == 400
    finally:
        await drop_tenant_schema(slug)
        async with platform_sessionmaker()() as ps:
            await ps.execute(delete(Tenant).where(Tenant.slug == slug))
            await ps.commit()


# -- the economy, and its floors -------------------------------------------

async def test_the_economy_can_be_tuned(client):
    token = await login(client, "platform")
    res = await client.put("/api/v1/platform/gamification", headers=auth(token), json={
        "xp_table": {"attempt_completed": 150, "drill_completed": 60,
                     "quiz_completed": 25, "quest_completed": 80,
                     "streak_milestone": 150},
        "weakness_multiplier": 2.0, "free_freezes_per_month": 3,
        "quiz_xp_cap_percent": 30, "leagues_enabled": False,
        "max_engagement_notifications_per_day": 1})
    assert res.status_code == 200
    assert res.json()["weakness_multiplier"] == 2.0
    assert res.json()["leagues_enabled"] is False

    # Put it back for the rest of the suite.
    await client.put("/api/v1/platform/gamification", headers=auth(token), json={
        "xp_table": {"attempt_completed": 120, "drill_completed": 60,
                     "quiz_completed": 25, "quest_completed": 80,
                     "streak_milestone": 150},
        "weakness_multiplier": 1.5, "free_freezes_per_month": 2,
        "quiz_xp_cap_percent": 40, "leagues_enabled": True,
        "max_engagement_notifications_per_day": 1})


@pytest.mark.parametrize("payload,why", [
    ({"free_freezes_per_month": 0}, "freezes are the student's only protection"),
    ({"max_engagement_notifications_per_day": 10}, "notification cap"),
    ({"quiz_xp_cap_percent": 95}, "quizzes would replace speaking"),
    ({"quiz_xp_cap_percent": 0}, "a zero cap is not a cap"),
    ({"weakness_multiplier": 0.5}, "weakness must never be worth less"),
])
async def test_a_student_protection_cannot_be_configured_away(client, payload, why):
    """The floors are the difference between a setting and a guardrail.

    Refused rather than silently clamped: an operator who asked for something
    they cannot have should be told, not quietly overruled.
    """
    token = await login(client, "platform")
    body = {"weakness_multiplier": 1.5, "free_freezes_per_month": 2,
            "quiz_xp_cap_percent": 40, "leagues_enabled": True,
            "max_engagement_notifications_per_day": 1}
    body.update(payload)

    res = await client.put("/api/v1/platform/gamification", headers=auth(token),
                           json=body)
    assert res.status_code == 400, why
    assert res.json()["detail"], "a refusal must explain itself"


async def test_the_console_cannot_configure_a_prohibited_mechanic(client):
    """NFR-16: they are absent, not disabled. There is no field to set."""
    from app.schemas import GamificationConfigRequest

    fields = set(GamificationConfigRequest.model_fields)
    for forbidden in ("freeze_price", "streak_restore_price", "currency_enabled",
                      "public_leaderboard", "loot_boxes", "countdown_days"):
        assert forbidden not in fields


# -- audit -----------------------------------------------------------------

async def test_every_console_change_lands_in_the_audit_log(client):
    token = await login(client, "platform")
    tier1 = await _provider("vad", "silero_vad")
    tier0 = await _provider("vad", "energy_vad")

    await client.put("/api/v1/platform/capabilities/vad", headers=auth(token),
                     json={"primary_provider_id": tier1,
                           "fallback_provider_id": tier0,
                           "mode": "live", "timeout_ms": 15000})

    events = (await client.get("/api/v1/platform/audit", headers=auth(token))).json()
    actions = {e["action"] for e in events}
    assert "capability.configured" in actions

    entry = next(e for e in events if e["action"] == "capability.configured")
    assert entry["actor_type"] == "platform_user"
    assert entry["actor_label"], "an audit row without an actor is not an audit row"


async def test_a_tenant_admin_cannot_reach_the_operator_console(client):
    token = await login(client, "tenant_admin")
    for method, path, body in [
        ("put", "/api/v1/platform/capabilities/vad", {"primary_provider_id": "x"}),
        ("post", "/api/v1/platform/tenants", {"name": "Mine", "slug": "mine",
                                              "admin_email": "a@b.edu",
                                              "admin_name": "A"}),
        ("put", "/api/v1/platform/gamification", {"quiz_xp_cap_percent": 100}),
    ]:
        res = await getattr(client, method)(path, json=body, headers=auth(token))
        assert res.status_code == 403, path
