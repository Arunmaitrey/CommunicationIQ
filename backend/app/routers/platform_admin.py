"""Operator console — the control plane.

Platform staff never read student data from here. What they see is the shape
of the business (tenants, plans, seats) and the shape of the system
(capabilities, providers, latency, audit). Institution databases are not
reachable through any endpoint in this file.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from beanie.operators import GTE
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response as HttpResponse

from app.deps import require_platform
from app.engine.contracts import CONTRACT_FOR, Capability
from app.models.platform import (AuditLog, GamificationConfig, Plan,
                                 ProviderCall, ProviderConfig,
                                 ProviderRegistry, Tenant)
from app.routers.platform_writes import _tenant_out
from app.schemas import (AuditOut, CapabilityOut, GamificationConfigOut,
                         PlanOut, PlatformOverview, ProviderOut, TenantOut)
from app.storage import get_storage

router = APIRouter(prefix="/platform", tags=["platform"],
                   dependencies=[Depends(require_platform())])

# Branding assets hang off the same prefix but carry no platform-admin
# dependency: a tenant logo is shown to students and on the sign-in page,
# and a logo only an operator can load is not a logo.
asset_router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("/overview", response_model=PlatformOverview)
async def overview() -> PlatformOverview:
    tenants = await Tenant.find_all().to_list()
    plans = await Plan.find_all().count()
    providers = await ProviderRegistry.find_all().count()
    configured_docs = await ProviderConfig.get_motor_collection().distinct(
        "capability")
    configured = len(configured_docs)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    audit = await AuditLog.find(GTE(AuditLog.at, week_ago)).count()

    return PlatformOverview(
        tenants_total=len(tenants),
        tenants_active=sum(1 for t in tenants if t.status in {"active", "trial"}),
        seats_sold=sum(t.seat_limit for t in tenants),
        plans=int(plans),
        providers_registered=int(providers),
        capabilities_configured=int(configured),
        capabilities_total=len(Capability),
        audit_events_7d=int(audit),
    )


@router.get("/tenants", response_model=list[TenantOut])
async def tenants() -> list[TenantOut]:
    rows = await Tenant.find_all().sort("name").to_list()
    # One serialiser for the console, shared with the write endpoints, so a
    # tenant does not describe itself differently depending on which call
    # fetched it.
    return [await _tenant_out(t) for t in rows]


@router.get("/plans", response_model=list[PlanOut])
async def plans() -> list[PlanOut]:
    rows = await Plan.find_all().sort([("code", 1), ("version", -1)]).to_list()
    return [
        PlanOut(
            id=p.id, code=p.code, name=p.name, version=p.version,
            billing_model=p.billing_model, currency=p.currency,
            price_per_seat=p.price_per_seat, price_flat=p.price_flat,
            attempt_allowance=p.attempt_allowance, active=p.active,
        )
        for p in rows
    ]


@router.get("/capabilities", response_model=list[CapabilityOut])
async def capabilities() -> list[CapabilityOut]:
    """Every pluggable capability, its contract, and what currently serves it.

    Capabilities with no configured provider are listed too — an unconfigured
    capability is a fact worth seeing, not a row to hide.
    """
    registry = await ProviderRegistry.find_all().sort(
        "capability", "tier").to_list()
    configs = {c.capability: c for c in await ProviderConfig.find(
        ProviderConfig.tenant_id == None).to_list()}  # noqa: E711

    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    stat_docs = await ProviderCall.get_motor_collection().aggregate([
        {"$match": {"at": {"$gte": day_ago}}},
        {"$group": {
            "_id": "$provider_id",
            "calls": {"$sum": 1},
            "errors": {"$sum": {"$cond": [{"$eq": ["$ok", False]}, 1, 0]}},
            "latency": {"$avg": "$latency_ms"},
        }},
    ]).to_list(None)
    stats = {d["_id"]: (d["calls"], d["errors"], d["latency"])
             for d in stat_docs}

    by_capability: dict[str, list[ProviderRegistry]] = {}
    for row in registry:
        by_capability.setdefault(row.capability, []).append(row)

    out: list[CapabilityOut] = []
    for cap in Capability:
        config = configs.get(cap.value)
        contract = CONTRACT_FOR.get(cap)
        rows = by_capability.get(cap.value, [])

        def role_of(row_id: str) -> str:
            if config is None:
                return "unassigned"
            if row_id == config.primary_provider_id:
                return "primary"
            if row_id == config.fallback_provider_id:
                return "fallback"
            if row_id == config.shadow_provider_id:
                return "shadow"
            return "unassigned"

        names = {r.id: r.name for r in rows}
        providers = []
        for r in rows:
            calls, errors, latency = stats.get(r.id, (0, 0, 0))
            providers.append(ProviderOut(
                id=r.id, capability=r.capability, provider_key=r.provider_key,
                name=r.name, tier=r.tier, version=r.version, entrypoint=r.entrypoint,
                active=r.active, role=role_of(r.id),
                mode=config.mode if config else "",
                calls_24h=int(calls),
                error_rate=round(errors / calls, 3) if calls else 0.0,
                p50_latency_ms=int(latency or 0),
            ))

        out.append(CapabilityOut(
            capability=cap.value,
            contract_version=getattr(contract, "contract_version", "—"),
            configured=config is not None,
            mode=config.mode if config else "",
            primary=names.get(config.primary_provider_id, "") if config else "",
            fallback=names.get(config.fallback_provider_id or "", "") if config else "",
            shadow=names.get(config.shadow_provider_id or "", "") if config else "",
            timeout_ms=config.timeout_ms if config else 0,
            providers=providers,
        ))
    return out


@router.get("/audit", response_model=list[AuditOut])
async def audit(limit: int = 100) -> list[AuditOut]:
    rows = await AuditLog.find_all().sort("-at").limit(min(limit, 500)).to_list()
    return [
        AuditOut(
            id=a.id, actor_type=a.actor_type, actor_label=a.actor_label,
            tenant_id=a.tenant_id, action=a.action, entity=a.entity,
            entity_id=a.entity_id, at=a.at,
        )
        for a in rows
    ]


@router.get("/narration/settings")
async def narration_settings() -> dict:
    """The AI-narration configuration, secrets masked to set/last4."""
    from app import ai_settings
    overrides = await ai_settings.load_and_apply()
    return ai_settings.masked_view(overrides)


@router.get("/narration/metrics")
async def narration_metrics() -> dict:
    """Operational health of the AI narrator — counts, failures, cost.

    Platform staff only (the router dependency). Reads the job table across
    tenants; carries no student content. Answers pending/processing/ready/
    failed, why things fail, latency, token usage and success rate.
    """
    from app.narration import metrics
    return await metrics.collect()


@router.get("/gamification", response_model=GamificationConfigOut)
async def gamification(tenant_id: str | None = None) -> GamificationConfigOut:
    """The game economy (PLAT-17). Tenant row if present, otherwise the global default."""
    row = None
    if tenant_id:
        row = await GamificationConfig.find_one(
            GamificationConfig.tenant_id == tenant_id)
    if row is None:
        row = await GamificationConfig.find_one(
            GamificationConfig.tenant_id == None)  # noqa: E711
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No gamification configuration")

    return GamificationConfigOut(
        tenant_id=row.tenant_id, xp_table=row.xp_table,
        difficulty_multipliers=row.difficulty_multipliers,
        weakness_multiplier=row.weakness_multiplier,
        free_freezes_per_month=row.free_freezes_per_month,
        quiz_xp_cap_percent=row.quiz_xp_cap_percent,
        leagues_enabled=row.leagues_enabled,
        max_engagement_notifications_per_day=row.max_engagement_notifications_per_day,
    )


# --------------------------------------------------------------------------
# Branding assets
# --------------------------------------------------------------------------

_ASSET_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "gif": "image/gif"}

# Matches exactly what the upload endpoint writes and nothing else. Serving
# arbitrary storage keys from an authenticated route would turn this into a
# reader for every recording on disk.
_ASSET_KEY = re.compile(r"^branding/[a-z][a-z0-9_]{1,40}/logo\.(png|jpg|jpeg|webp|gif)$")


@asset_router.get("/assets/{key:path}")
async def branding_asset(key: str) -> HttpResponse:
    """Serve a tenant logo.

    Deliberately outside the platform-admin dependency: this is on the sign-in
    page and in every student's sidebar, so requiring a platform token would
    mean it never renders for the people it is for. The narrow key pattern is
    what keeps that safe -- nothing but a logo can be addressed.
    """
    if not _ASSET_KEY.match(key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    storage = get_storage()
    if not storage.exists(key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    try:
        data = storage.get(key)
    except (ValueError, OSError) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc

    return HttpResponse(
        content=data,
        media_type=_ASSET_TYPES.get(key.rsplit(".", 1)[-1], "application/octet-stream"),
        headers={
            "Cache-Control": "public, max-age=300",
            # A logo is an image and is only ever an image. Says so, so a
            # browser cannot be talked into treating it as anything else.
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
