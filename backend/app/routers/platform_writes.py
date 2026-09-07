"""Operator console — the write half.

Switching a provider, onboarding an institution, and changing the game economy
all live here. Every one of them is audit-logged with the before and after,
because "who changed the ASR provider on the morning of the drive" is a
question somebody will eventually ask.

Two things this file will not do:

* **Reach student data.** Creating an institution provisions its schema and
  its first admin; nothing here reads an attempt, a recording or a score.
* **Configure a prohibited mechanic.** The economy endpoint has no field for a
  streak price or a public leaderboard, and it enforces floors so a tenant
  cannot configure its way past a student protection (GAM-21…25).
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

from fastapi import (APIRouter, Depends, File, HTTPException, UploadFile,
                     status)

from app import audit
from app.db import ensure_tenant_models
from app.deps import Principal, require_platform
from app.engine.contracts import Capability
from app.engine.registry import clear_provider_cache
from app.models.platform import (GamificationConfig,
                                 TENANT_TYPES, TENANT_TYPE_KEYS,
                                 ProviderConfig, ProviderRegistry,
                                 Tenant, TenantUserDirectory, ExamTest,
                                 ScheduledExam)
from app.provisioning import create_tenant_schema, validate_slug
from app.routers.tenant_writes import temporary_password
from app.schemas import (CapabilityConfigRequest, GamificationConfigOut,
                         GamificationConfigRequest,
                         LogoByUrlRequest,
                         ProviderOut, ProviderRegisterRequest,
                         ProviderUpdateRequest,
                         TenantBranding, TenantCreateRequest, TenantOut,
                         TenantProfile, TenantTypeOut, TenantUpdateRequest,
                         ContactMessageRequest, ContactMessageReplyRequest,
                         ExamTestRequest, ScheduledExamRequest, ScheduledExamOut)
from app.security import hash_password
from app.storage import get_storage

router = APIRouter(prefix="/platform", tags=["platform"],
                   dependencies=[Depends(require_platform())])

# Floors that protect students. A tenant can tune the economy; it cannot tune
# these away, which is the difference between a setting and a guardrail.
MIN_FREE_FREEZES = 1
MAX_ENGAGEMENT_NOTIFICATIONS = 3
MAX_QUIZ_CAP_PERCENT = 60


# --------------------------------------------------------------------------
# AI narration configuration
# --------------------------------------------------------------------------

@router.put("/narration/settings",
            dependencies=[Depends(require_platform("super_admin"))])
async def update_narration_settings(body: dict) -> dict:
    """Save AI-narration configuration and apply it live.

    super_admin only: the document holds provider API keys. Field contract:
    a value changes the setting, null leaves it unchanged, "" clears it back
    to the environment default. Unknown fields are ignored (the whitelist in
    app.ai_settings is the boundary). Secrets are stored whole and returned
    masked -- the console never sees a key again after saving it.
    """
    from app import ai_settings
    try:
        overrides = await ai_settings.save(body or {})
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return ai_settings.masked_view(overrides)


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------

@router.put("/capabilities/{capability}")
async def configure_capability(capability: str, body: CapabilityConfigRequest,
                               principal: Principal) -> dict:
    """Point a capability at a different implementation. No deploy (ENG-18)."""
    try:
        cap = Capability(capability)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"Unknown capability {capability}") from exc

    async def resolve(provider_id: str | None, label: str) -> str | None:
        if not provider_id:
            return None
        row = await ProviderRegistry.get(provider_id)
        if row is None or row.capability != cap.value:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"{label} is not a provider for {cap.value}")
        if not row.active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"{row.name} is registered but not active")
        return row.id

    primary = await resolve(body.primary_provider_id, "primary")
    if primary is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A primary provider is required")
    fallback = await resolve(body.fallback_provider_id, "fallback")
    shadow = await resolve(body.shadow_provider_id, "shadow")

    if body.mode not in {"live", "shadow", "canary"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown mode")
    if body.mode == "shadow" and shadow is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Shadow mode needs a shadow provider to compare against")
    if body.mode == "canary" and (fallback is None or not 1 <= body.canary_percent <= 99):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Canary mode needs a second provider and a split between 1 and 99")

    existing = await ProviderConfig.find_one(
        ProviderConfig.capability == cap.value,
        ProviderConfig.tenant_id == body.tenant_id) if body.tenant_id else await ProviderConfig.find_one(
        ProviderConfig.capability == cap.value,
        ProviderConfig.tenant_id == None)

    before = {}
    if existing is None:
        existing = ProviderConfig(capability=cap.value, tenant_id=body.tenant_id,
                                  primary_provider_id=primary)
        await existing.create()
    else:
        before = {"primary": existing.primary_provider_id,
                  "fallback": existing.fallback_provider_id,
                  "mode": existing.mode, "timeout_ms": existing.timeout_ms}

    existing.primary_provider_id = primary
    existing.fallback_provider_id = fallback
    existing.shadow_provider_id = shadow
    existing.mode = body.mode
    existing.canary_percent = body.canary_percent
    existing.timeout_ms = max(500, min(body.timeout_ms, 120000))
    existing.updated_at = datetime.now(timezone.utc)
    await existing.save()

    # Instances are cached per entrypoint; a swap has to invalidate that or
    # the console would report a change the engine has not made.
    clear_provider_cache()

    await audit.record(principal, "capability.configured", entity="ProviderConfig",
                       entity_id=existing.id, before=before,
                       after={"capability": cap.value, "primary": primary,
                              "fallback": fallback, "mode": body.mode},
                       tenant_id=body.tenant_id)
    return {"capability": cap.value, "mode": body.mode, "applied": True}


def _provider_out(row: ProviderRegistry) -> ProviderOut:
    return ProviderOut(
        id=row.id, capability=row.capability, provider_key=row.provider_key,
        name=row.name, tier=row.tier, version=row.version,
        entrypoint=row.entrypoint, active=row.active,
        role="", mode="", calls_24h=0, error_rate=0.0, p50_latency_ms=0,
    )


def _importable(entrypoint: str) -> str:
    """Check an entrypoint resolves, and say why if it does not.

    Storing an unimportable path is the difference between a provider that
    fails now, in a form, and one that fails later inside a student's attempt
    with the fallback quietly carrying the load.
    """
    if ":" not in entrypoint:
        return "Expected module:attribute, e.g. app.engine.providers.tier1.pronunciation:Wav2VecGOP"
    module_name, _, attribute = entrypoint.partition(":")
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 — any import failure is the answer
        return f"{module_name} could not be imported: {exc}"
    if not hasattr(module, attribute):
        return f"{module_name} has no attribute {attribute!r}"
    return ""


@router.post("/providers", response_model=ProviderOut,
             status_code=status.HTTP_201_CREATED)
async def register_provider(body: ProviderRegisterRequest, principal: Principal) -> ProviderOut:
    """Add an implementation to the registry."""
    known = {c.value for c in Capability}
    if body.capability not in known:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown capability {body.capability!r}. Known: "
            f"{', '.join(sorted(known))}")

    clash = await ProviderRegistry.find_one(
        ProviderRegistry.capability == body.capability,
        ProviderRegistry.provider_key == body.provider_key,
        ProviderRegistry.version == body.version)
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{body.provider_key} {body.version} is already registered for "
            f"{body.capability}. Bump the version to add another.")

    problem = _importable(body.entrypoint)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)

    row = ProviderRegistry(
        capability=body.capability, provider_key=body.provider_key,
        name=body.name, tier=body.tier, version=body.version,
        entrypoint=body.entrypoint, active=body.active,
        config_schema=body.config or {},
    )
    await row.create()
    clear_provider_cache()

    await audit.record(principal, "provider.registered", entity="ProviderRegistry",
                       entity_id=row.id,
                       after={"capability": row.capability, "key": row.provider_key,
                              "version": row.version})
    return _provider_out(row)


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: str, body: ProviderUpdateRequest,
                          principal: Principal) -> ProviderOut:
    row = await ProviderRegistry.get(provider_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")

    before = {"name": row.name, "tier": row.tier, "version": row.version,
              "entrypoint": row.entrypoint, "active": row.active}

    if body.entrypoint is not None:
        problem = _importable(body.entrypoint)
        if problem:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)
        row.entrypoint = body.entrypoint
    if body.name is not None:
        row.name = body.name
    if body.tier is not None:
        row.tier = body.tier
    if body.version is not None:
        row.version = body.version
    if body.active is not None:
        row.active = body.active
    if body.config is not None:
        row.config_schema = body.config

    await row.save()
    clear_provider_cache()
    await audit.record(principal, "provider.updated", entity="ProviderRegistry",
                       entity_id=row.id, before=before,
                       after={"name": row.name, "tier": row.tier,
                              "version": row.version, "entrypoint": row.entrypoint,
                              "active": row.active})
    return _provider_out(row)


@router.post("/providers/{provider_id}/active")
async def set_provider_active(provider_id: str, active: bool, principal: Principal) -> dict:
    row = await ProviderRegistry.get(provider_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider not found")

    if not active:
        serving = await ProviderConfig.find(
            ProviderConfig.primary_provider_id == provider_id).count()
        if serving:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This provider is currently primary for a capability. "
                "Point that capability elsewhere first.")

    before = {"active": row.active}
    row.active = active
    await row.save()
    clear_provider_cache()

    await audit.record(principal, "provider.active_changed", entity="ProviderRegistry",
                       entity_id=provider_id, before=before, after={"active": active})
    return {"id": provider_id, "active": active}


# --------------------------------------------------------------------------
# Institutions
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Tenants
# --------------------------------------------------------------------------

# Logos are small and the list of what a browser will render inline is short.
# Anything outside it is refused rather than stored and served back, because
# "upload a logo" is the cheapest route into stored-XSS there is -- an SVG is
# a script container, and a mislabelled HTML file served from our own origin
# would run with our cookies.
LOGO_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
MAX_LOGO_BYTES = 2 * 1024 * 1024

# The first bytes of each format we accept. Checked instead of trusting the
# declared content type, which the client chooses.
LOGO_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _sniff_image(data: bytes) -> str | None:
    for magic, kind in LOGO_MAGIC:
        if data.startswith(magic):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _profile_of(tenant: Tenant) -> TenantProfile:
    """Stored blob to typed profile, tolerating anything already in there.

    A blob written by an older release can be missing keys or carry ones we
    have since dropped; both are survivable and neither should 500 a list of
    tenants. Unknown keys are ignored, absent ones take their default.
    """
    raw = dict(tenant.profile or {})
    known = set(TenantProfile.model_fields)
    return TenantProfile(**{k: v for k, v in raw.items()
                            if k in known and v is not None})


def _branding_of(tenant: Tenant) -> TenantBranding:
    raw = tenant.branding or {}
    return TenantBranding(
        display_name=str(raw.get("display_name", "") or ""),
        logo_url=str(raw.get("logo_url", "") or ""),
        primary_color=str(raw.get("primary_color", "") or ""),
        default_theme=str(raw.get("default_theme", "") or ""),
        support_email=str(raw.get("support_email", "") or ""),
    )


async def _tenant_out(tenant: Tenant, *, seats_used: int | None = None
                      ) -> TenantOut:
    if seats_used is None:
        seats_used = 0
        try:
            models = await ensure_tenant_models(tenant.slug)
            seats_used = await models.User.find(
                models.User.active == True).count()
        except Exception:  # noqa: BLE001 — a schema that is gone must not 500 the list
            seats_used = 0

    labels = dict(TENANT_TYPES)
    return TenantOut(
        id=tenant.id, name=tenant.name, slug=tenant.slug,
        domain=tenant.domain,
        tenant_type=tenant.tenant_type,
        tenant_type_label=labels.get(tenant.tenant_type, tenant.tenant_type),
        status=tenant.status,
        seat_limit=tenant.seat_limit, seats_used=seats_used,
        region=tenant.region, branding=_branding_of(tenant),
        profile=_profile_of(tenant),
        created_at=tenant.created_at,
    )


@router.get("/tenant-types", response_model=list[TenantTypeOut])
async def tenant_types() -> list[TenantTypeOut]:
    """The taxonomy, served rather than duplicated in the console."""
    return [TenantTypeOut(key=k, label=v) for k, v in TENANT_TYPES]


@router.post("/tenants/{tenant_id}/logo", response_model=TenantOut)
async def upload_logo(tenant_id: str, principal: Principal,
                      file: UploadFile = File(...)) -> TenantOut:
    """Store a logo uploaded from the operator's machine."""
    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty upload")
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "A logo must be 2 MB or smaller")

    # Sniffed, not declared. The browser's content type is a hint from the
    # client and an SVG or HTML file wearing an image/png label would be
    # served straight back from our own origin.
    kind = _sniff_image(data)
    if kind is None or kind not in LOGO_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "PNG, JPEG, WebP or GIF only — the file does not look like any of "
            "those. SVG is not accepted because it can carry script.")

    key = f"branding/{tenant.slug}/logo.{LOGO_TYPES[kind]}"
    get_storage().put(key, data, kind)

    branding = dict(tenant.branding or {})
    branding["logo_url"] = f"/platform/assets/{key}"
    tenant.branding = branding
    await tenant.save()

    await audit.record(principal, "tenant.logo_uploaded", entity="Tenant",
                       entity_id=tenant.id, tenant_id=tenant.id,
                       after={"bytes": len(data), "type": kind})
    return await _tenant_out(tenant)


@router.post("/tenants/{tenant_id}/logo-url", response_model=TenantOut)
async def set_logo_url(tenant_id: str, body: LogoByUrlRequest,
                       principal: Principal) -> TenantOut:
    """Point at a logo the customer already hosts.

    Stored as a reference, not fetched. Fetching a URL supplied by an operator
    would make the server issue requests to wherever it points, which is the
    shape of an SSRF -- and a logo that lives on the customer's own CDN is
    better served from there anyway.
    """
    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    url = body.url.strip()
    if not url.startswith("https://"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The logo URL must be https — a plain-HTTP image is blocked as "
            "mixed content on every page that would show it.")

    branding = dict(tenant.branding or {})
    branding["logo_url"] = url
    tenant.branding = branding
    await tenant.save()

    await audit.record(principal, "tenant.logo_linked", entity="Tenant",
                       entity_id=tenant.id, tenant_id=tenant.id,
                       after={"logo_url": url})
    return await _tenant_out(tenant)


@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(body: TenantCreateRequest, principal: Principal) -> TenantOut:
    """Onboard an institution: registry row, schema, and its first admin."""
    slug = body.slug.lower().strip()
    try:
        validate_slug(slug)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if await Tenant.find_one(Tenant.slug == slug) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That slug is already taken")

    if body.tenant_type not in TENANT_TYPE_KEYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unknown tenant type {body.tenant_type!r}")

    domain = body.domain.lower().strip() if body.domain else ""
    if domain:
        existing = await Tenant.find_one(Tenant.domain == domain)
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Domain {domain} is already registered")

    tenant = Tenant(name=body.name, slug=slug, domain=domain,
                    status=body.status,
                    tenant_type=body.tenant_type,
                    seat_limit=body.seat_limit,
                    branding=body.branding.model_dump() if body.branding else {},
                    profile=body.profile.model_dump() if body.profile else {})
    if body.region:
        tenant.region = body.region
    await tenant.create()

    await create_tenant_schema(slug)

    password = body.admin_password.strip() if body.admin_password and body.admin_password.strip() else temporary_password()
    models = await ensure_tenant_models(slug)
    await models.User(email=body.admin_email.lower(), full_name=body.admin_name,
                      role="tenant_admin", password_hash=hash_password(password),
                      must_change_password=True).create()

    await TenantUserDirectory(email=body.admin_email.lower(),
                              tenant_id=tenant.id, tenant_slug=slug).create()

    await audit.record(principal, "tenant.created", entity="Tenant",
                       entity_id=tenant.id, tenant_id=tenant.id,
                       after={"name": tenant.name, "slug": slug,
                              "domain": domain,
                              "seat_limit": body.seat_limit})

    out = await _tenant_out(tenant, seats_used=1)
    out.temp_password = password
    out.admin_email = body.admin_email.lower()
    return out


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
async def update_tenant(tenant_id: str, body: TenantUpdateRequest,
                        principal: Principal) -> TenantOut:
    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    before = {"name": tenant.name, "status": tenant.status,
              "tenant_type": tenant.tenant_type,
              "seat_limit": tenant.seat_limit}

    if body.name is not None:
        tenant.name = body.name.strip()
    if body.tenant_type is not None:
        if body.tenant_type not in TENANT_TYPE_KEYS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Unknown tenant type {body.tenant_type!r}")
        tenant.tenant_type = body.tenant_type
    if body.region is not None:
        tenant.region = body.region.strip()
    if body.branding is not None:
        # Merged, not replaced: the logo lives in the same blob and is set by
        # its own endpoints, so a branding save from the form must not wipe it.
        merged = dict(tenant.branding or {})
        for key, value in body.branding.model_dump().items():
            if key == "logo_url" and not value:
                continue
            merged[key] = value
        tenant.branding = merged
    if body.profile is not None:
        # Replaced whole, not merged. The console sends the entire form, and
        # merging would make clearing a field impossible -- an address line
        # deleted in the UI would quietly come back.
        tenant.profile = body.profile.model_dump()
    if body.status is not None:
        if body.status not in {"trial", "active", "suspended", "offboarding", "closed"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown status")
        tenant.status = body.status
    if body.seat_limit is not None:
        # Cutting seats below the people already in the schema would silently
        # lock students out mid-season. Refused, with the number they need.
        models = await ensure_tenant_models(tenant.slug)
        in_use = await models.User.find(
            models.User.active == True).count()
        if body.seat_limit < in_use:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{in_use} accounts are active — the seat limit cannot go below that.")
        tenant.seat_limit = body.seat_limit
    if body.season_start is not None:
        tenant.season_start = body.season_start
    if body.season_end is not None:
        tenant.season_end = body.season_end

    await tenant.save()
    await audit.record(principal, "tenant.updated", entity="Tenant",
                       entity_id=tenant.id, tenant_id=tenant.id, before=before,
                       after={"status": tenant.status,
                              "seat_limit": tenant.seat_limit})

    return await _tenant_out(tenant)





# --------------------------------------------------------------------------
# The game economy
# --------------------------------------------------------------------------

@router.put("/gamification", response_model=GamificationConfigOut)
async def update_gamification(body: GamificationConfigRequest, principal: Principal) -> GamificationConfigOut:
    """Tune the economy without a deploy (PLAT-17), within the floors.

    The floors are the point. An operator can make XP stingier or leagues go
    away; they cannot remove a student's free streak freezes, and they cannot
    raise the notification cap past three a day. Those are protections, not
    preferences, so the endpoint refuses rather than clamping silently — an
    operator who asked for something they cannot have should be told.
    """
    if body.free_freezes_per_month < MIN_FREE_FREEZES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Free streak freezes cannot go below {MIN_FREE_FREEZES} a month. "
            f"Freezes are never purchasable, so this is the student's only protection.")
    if body.max_engagement_notifications_per_day > MAX_ENGAGEMENT_NOTIFICATIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Engagement notifications are capped at {MAX_ENGAGEMENT_NOTIFICATIONS} a day.")
    if not 0 < body.quiz_xp_cap_percent <= MAX_QUIZ_CAP_PERCENT:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"The quiz XP cap must be between 1 and {MAX_QUIZ_CAP_PERCENT} percent, "
            f"or quizzes could stand in for speaking practice.")
    if body.weakness_multiplier < 1.0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "The weakness multiplier cannot be below 1.0 — training a diagnosed gap "
            "must never be worth less than repeating a strength.")

    row = await GamificationConfig.find_one(
        GamificationConfig.tenant_id == body.tenant_id) if body.tenant_id else await GamificationConfig.find_one(
        GamificationConfig.tenant_id == None)

    if row is None:
        row = GamificationConfig(tenant_id=body.tenant_id)
        await row.create()

    before = {"xp_table": row.xp_table, "quiz_cap": row.quiz_xp_cap_percent,
              "freezes": row.free_freezes_per_month}

    row.xp_table = body.xp_table or row.xp_table
    row.difficulty_multipliers = body.difficulty_multipliers or row.difficulty_multipliers
    row.weakness_multiplier = body.weakness_multiplier
    row.free_freezes_per_month = body.free_freezes_per_month
    row.quiz_xp_cap_percent = body.quiz_xp_cap_percent
    row.leagues_enabled = body.leagues_enabled
    row.max_engagement_notifications_per_day = body.max_engagement_notifications_per_day
    row.updated_at = datetime.now(timezone.utc)
    await row.save()

    await audit.record(principal, "gamification.configured",
                       entity="GamificationConfig", entity_id=row.id,
                       before=before, tenant_id=body.tenant_id,
                       after={"quiz_cap": row.quiz_xp_cap_percent,
                              "freezes": row.free_freezes_per_month,
                              "leagues": row.leagues_enabled})

    return GamificationConfigOut(
        tenant_id=row.tenant_id, xp_table=row.xp_table,
        difficulty_multipliers=row.difficulty_multipliers,
        weakness_multiplier=row.weakness_multiplier,
        free_freezes_per_month=row.free_freezes_per_month,
        quiz_xp_cap_percent=row.quiz_xp_cap_percent,
        leagues_enabled=row.leagues_enabled,
        max_engagement_notifications_per_day=row.max_engagement_notifications_per_day,
    )


# ---------------------------------------------------------------------------
# Subscription Plans
# ---------------------------------------------------------------------------

@router.post("/plans")
async def create_plan(body: dict, principal: Principal) -> dict:
    from app.db import control_db
    db = control_db()
    import uuid
    plan_id = str(uuid.uuid4())
    doc = {
        "_id": plan_id,
        "name": body.get("name", ""),
        "slug": body.get("slug", ""),
        "description": body.get("description", ""),
        "price_monthly": body.get("price_monthly", 0),
        "price_yearly": body.get("price_yearly", 0),
        "seat_limit": body.get("seat_limit", 50),
        "features": body.get("features", []),
        "max_questions": body.get("max_questions", 500),
        "max_exams_per_day": body.get("max_exams_per_day", 10),
        "has_proctoring": body.get("has_proctoring", True),
        "has_analytics": body.get("has_analytics", True),
        "has_custom_branding": body.get("has_custom_branding", False),
        "has_api_access": body.get("has_api_access", False),
        "is_active": body.get("is_active", True),
        "is_default": body.get("is_default", False),
    }
    await db["plans"].insert_one(doc)
    await audit.record(principal, "plan.created", entity="Plan", entity_id=plan_id)
    return {"id": plan_id, "ok": True}


@router.patch("/plans/{plan_id}")
async def update_plan(plan_id: str, body: dict, principal: Principal) -> dict:
    from app.db import control_db
    db = control_db()
    updates = {k: v for k, v in body.items() if k not in ("_id", "id")}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db["plans"].update_one({"_id": plan_id}, {"$set": updates})
    await audit.record(principal, "plan.updated", entity="Plan", entity_id=plan_id)
    return {"ok": True}


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str, principal: Principal) -> dict:
    from app.db import control_db
    db = control_db()
    await db["plans"].delete_one({"_id": plan_id})
    await audit.record(principal, "plan.deleted", entity="Plan", entity_id=plan_id)
    return {"ok": True}


@router.post("/plans/{plan_id}/assign/{tenant_id}")
async def assign_plan(plan_id: str, tenant_id: str, principal: Principal) -> dict:
    from app.db import control_db
    db = control_db()
    await db["tenants"].update_one({"_id": tenant_id}, {"$set": {"plan_id": plan_id}})
    await audit.record(principal, "plan.assigned", entity="Tenant", entity_id=tenant_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# SMTP Configuration
# ---------------------------------------------------------------------------

@router.post("/smtp")
async def save_smtp(body: dict, principal: Principal) -> dict:
    from app.db import control_db
    db = control_db()
    tenant_id = body.get("tenant_id")  # null = platform default
    existing = await db["smtp_configs"].find_one({"tenant_id": tenant_id})
    doc = {
        "host": body.get("host", ""),
        "port": body.get("port", 587),
        "username": body.get("username", ""),
        "password": body.get("password", ""),
        "from_email": body.get("from_email", ""),
        "from_name": body.get("from_name", "CommunicationIQ"),
        "use_tls": body.get("use_tls", True),
        "use_ssl": body.get("use_ssl", False),
        "is_active": body.get("is_active", True),
        "tenant_id": tenant_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        await db["smtp_configs"].update_one({"_id": existing["_id"]}, {"$set": doc})
    else:
        import uuid
        doc["_id"] = str(uuid.uuid4())
        await db["smtp_configs"].insert_one(doc)
    await audit.record(principal, "smtp.configured", entity="SmtpConfig")
    return {"ok": True}


@router.post("/smtp/test")
async def test_smtp(body: dict, principal: Principal) -> dict:
    """Send a test email to verify SMTP configuration."""
    from app.email_sender import send_email
    to = body.get("to_email", "")
    if not to:
        return {"ok": False, "message": "No test email address provided"}
    ok = await send_email(
        to_email=to,
        subject="CommunicationIQ — SMTP Test",
        body_html="<h2>SMTP configured successfully!</h2><p>Your email system is working.</p>",
        body_text="SMTP configured successfully! Your email system is working.",
        tenant_id=body.get("tenant_id"),
    )
    return {"ok": ok, "message": "Test email sent" if ok else "Failed to send — check SMTP settings"}


# ---------------------------------------------------------------------------
# Payment Gateway Configuration
# ---------------------------------------------------------------------------

@router.post("/payment")
async def save_payment_config(body: dict, principal: Principal) -> dict:
    from app.db import control_db
    db = control_db()
    gateway = body.get("gateway", "stripe")
    existing = await db["payment_configs"].find_one({"gateway": gateway})
    doc = {
        "gateway": gateway,
        "test_mode": body.get("test_mode", True),
        "stripe_publishable": body.get("stripe_publishable", ""),
        "stripe_secret": body.get("stripe_secret", ""),
        "stripe_webhook_secret": body.get("stripe_webhook_secret", ""),
        "razorpay_key_id": body.get("razorpay_key_id", ""),
        "razorpay_key_secret": body.get("razorpay_key_secret", ""),
        "currency": body.get("currency", "INR"),
        "is_active": body.get("is_active", False),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        await db["payment_configs"].update_one({"_id": existing["_id"]}, {"$set": doc})
    else:
        import uuid
        doc["_id"] = str(uuid.uuid4())
        await db["payment_configs"].insert_one(doc)
    await audit.record(principal, "payment.configured", entity="PaymentConfig")
    return {"ok": True}


# --------------------------------------------------------------------------
# Contact Messages
# --------------------------------------------------------------------------

@router.post("/messages")
async def submit_contact_message(body: ContactMessageRequest,
                                 principal: Principal) -> dict:
    """Submit a contact message from any user to super admins."""
    from app.models.platform import ContactMessage
    msg = ContactMessage(
        from_user_id=principal.user_id,
        from_email=principal.email,
        from_name=principal.full_name or "",
        from_role=principal.role,
        from_tenant_id=getattr(principal, "tenant_id", None),
        subject=body.subject,
        body=body.body,
        priority=body.priority,
    )
    await msg.create()
    await audit.record(principal, "contact.submitted", entity="ContactMessage",
                       entity_id=msg.id)
    return {"id": msg.id, "ok": True}


@router.patch("/messages/{message_id}")
async def update_contact_message(message_id: str, body: dict,
                                 principal: Principal) -> dict:
    """Update message status (super admin)."""
    from app.models.platform import ContactMessage
    msg = await ContactMessage.get(message_id)
    if not msg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    if "status" in body:
        msg.status = body["status"]
    if "priority" in body:
        msg.priority = body["priority"]
    msg.updated_at = datetime.now(timezone.utc)
    await msg.save()
    await audit.record(principal, "contact.updated", entity="ContactMessage",
                       entity_id=message_id, after={"status": msg.status})
    return {"ok": True}


@router.post("/messages/{message_id}/reply")
async def reply_to_message(message_id: str, body: ContactMessageReplyRequest,
                           principal: Principal) -> dict:
    """Reply to a contact message (super admin)."""
    from app.models.platform import ContactMessage
    msg = await ContactMessage.get(message_id)
    if not msg:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    msg.replies.append({
        "from": principal.full_name or "Admin",
        "text": body.text,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    msg.updated_at = datetime.now(timezone.utc)
    await msg.save()
    await audit.record(principal, "contact.replied", entity="ContactMessage",
                       entity_id=message_id)
    return {"ok": True}


# --------------------------------------------------------------------------
# Exam Tests (Custom tests created by super admin)
# --------------------------------------------------------------------------

@router.post("/exam-tests", status_code=status.HTTP_201_CREATED)
async def create_exam_test(body: ExamTestRequest, principal: Principal) -> dict:
    """Create a new custom exam test."""
    from app.models.platform import ExamTest
    import re as _re
    slug = _re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")
    test = ExamTest(
        name=body.name, description=body.description, slug=slug,
        duration_minutes=body.duration_minutes,
        reading_questions=body.reading_questions,
        listening_questions=body.listening_questions,
        writing_questions=body.writing_questions,
        speaking_questions=body.speaking_questions,
        reading_seconds=body.reading_seconds,
        listening_seconds=body.listening_seconds,
        writing_seconds=body.writing_seconds,
        speaking_seconds=body.speaking_seconds,
        allow_pause=body.allow_pause, show_timer=body.show_timer,
        one_shot_audio=body.one_shot_audio, is_active=body.is_active,
        is_baseline=body.is_baseline, company=body.company,
        question_ids=body.question_ids,
    )
    await test.create()
    await audit.record(principal, "exam_test.created", entity="ExamTest",
                       entity_id=test.id, after={"name": test.name})
    # Auto-sync SimulationProfile for this exam test
    try:
        from app.main import _sync_exam_test_profiles
        await _sync_exam_test_profiles()
    except Exception:
        pass
    return {"id": test.id, "ok": True}


@router.patch("/exam-tests/{test_id}")
async def update_exam_test(test_id: str, body: ExamTestRequest,
                           principal: Principal) -> dict:
    """Update an exam test."""
    from app.models.platform import ExamTest
    test = await ExamTest.get(test_id)
    if not test:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test not found")
    for field in ["name", "description", "duration_minutes",
                  "reading_questions", "listening_questions",
                  "writing_questions", "speaking_questions",
                  "reading_seconds", "listening_seconds",
                  "writing_seconds", "speaking_seconds",
                  "allow_pause", "show_timer", "one_shot_audio",
                  "is_active", "is_baseline", "company", "question_ids"]:
        if hasattr(body, field):
            setattr(test, field, getattr(body, field))
    test.updated_at = datetime.now(timezone.utc)
    await test.save()
    await audit.record(principal, "exam_test.updated", entity="ExamTest",
                       entity_id=test_id)
    # Auto-sync SimulationProfile for this exam test
    try:
        from app.main import _sync_exam_test_profiles
        await _sync_exam_test_profiles()
    except Exception:
        pass
    return {"ok": True}


@router.delete("/exam-tests/{test_id}")
async def delete_exam_test(test_id: str, principal: Principal) -> dict:
    """Delete an exam test and retire its student-facing SimulationProfile so
    it stops appearing for students (no orphaned published profile)."""
    from datetime import datetime as _dt, timezone as _tz
    from app.models.platform import ExamTest
    from app.db import control_db
    test = await ExamTest.get(test_id)
    if test is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Test not found")
    await ExamTest.delete(ExamTest.id == test_id)
    try:
        db = control_db()
        await db.simulation_profiles.update_many(
            {"name": test.name},
            {"$set": {"status": "retired",
                      "updated_at": _dt.now(_tz.utc)}})
    except Exception:  # noqa: BLE001
        pass
    await audit.record(principal, "exam_test.deleted", entity="ExamTest",
                       entity_id=test_id)
    return {"ok": True}


# --------------------------------------------------------------------------
# Question Sets (exactly 10 questions per set)
# --------------------------------------------------------------------------

@router.post("/question-sets/generate", status_code=status.HTTP_201_CREATED)
async def generate_question_sets(module: str, principal: Principal, count: int = 1) -> dict:
    """Auto-generate question sets from the question bank for a module.
    Each set contains exactly 10 questions from the same module.
    """
    import re as _re
    from app.models.platform import QuestionSet
    from app.db import control_db

    if module not in ("reading", "writing", "listening", "speaking", "quiz"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid module")

    db = control_db()
    # Map module to collection
    coll_map = {
        "reading": "reading_passages",
        "listening": "listening_passages",
        "writing": "writing_prompts",
        "speaking": "task_items",
        "quiz": "quiz_items",
    }
    coll_name = coll_map[module]
    coll = db[coll_name]

    # Count existing questions
    total = await coll.count_documents({})
    needed = count * 10
    if total < needed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Need {needed} {module} questions but only {total} exist")

    # Count existing sets to determine numbering
    existing_count = await QuestionSet.find(QuestionSet.module == module).count()

    created_sets = []
    for i in range(count):
        set_num = existing_count + i + 1
        prefix = module[:4].upper()
        set_number = f"{prefix}-SET-{set_num:03d}"

        # Find questions not already in an active set for this module
        active_sets = await QuestionSet.find(
            QuestionSet.module == module,
            QuestionSet.status.in_(["active", "draft"]),
        ).to_list()
        used_ids = set()
        for s in active_sets:
            used_ids.update(s.question_ids)

        # Get eligible questions
        query = {"_id": {"$nin": list(used_ids)}} if used_ids else {}
        cursor = coll.find(query).limit(10)
        questions = await cursor.to_list()

        if len(questions) < 10:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Not enough unused {module} questions for set {set_num}")

        q_ids = [str(q["_id"]) for q in questions]

        qs = QuestionSet(
            set_number=set_number,
            module=module,
            question_ids=q_ids,
            question_count=10,
            status="draft",
        )
        await qs.create()
        created_sets.append({"id": qs.id, "set_number": set_number, "module": module})

    await audit.record(principal, "question_sets.generated", entity="QuestionSet",
                       after={"module": module, "count": len(created_sets)})
    return {"created": len(created_sets), "sets": created_sets, "ok": True}


@router.patch("/question-sets/{set_id}")
async def update_question_set(set_id: str, body: dict, principal: Principal) -> dict:
    """Update a question set (status, etc.)."""
    from app.models.platform import QuestionSet
    qs = await QuestionSet.get(set_id)
    if not qs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set not found")
    if "status" in body:
        qs.status = body["status"]
    qs.updated_at = datetime.now(timezone.utc)
    await qs.save()
    await audit.record(principal, "question_set.updated", entity="QuestionSet",
                       entity_id=set_id, after={"status": qs.status})
    return {"ok": True}


@router.delete("/question-sets/{set_id}")
async def delete_question_set(set_id: str, principal: Principal) -> dict:
    """Delete a question set (only if draft)."""
    from app.models.platform import QuestionSet
    qs = await QuestionSet.get(set_id)
    if not qs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set not found")
    if qs.status not in ("draft", "inactive"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can only delete draft/inactive sets")
    await QuestionSet.delete(QuestionSet.id == set_id)
    await audit.record(principal, "question_set.deleted", entity="QuestionSet", entity_id=set_id)
    return {"ok": True}


@router.post("/question-sets/auto-create")
async def auto_create_sets(principal: Principal) -> dict:
    """Auto-create sets for all modules where we have enough questions (10+)."""
    from app.models.platform import QuestionSet
    from app.db import control_db

    db = control_db()
    coll_map = {
        "reading": "reading_passages",
        "listening": "listening_passages",
        "writing": "writing_prompts",
        "speaking": "task_items",
        "quiz": "quiz_items",
    }
    results = {}
    for module, coll_name in coll_map.items():
        coll = db[coll_name]
        total = await coll.count_documents({})
        # Count existing sets for this module
        existing = await QuestionSet.find(QuestionSet.module == module).count()
        # How many sets of 10 can we make from unused questions?
        active_sets = await QuestionSet.find(
            QuestionSet.module == module,
            QuestionSet.status.in_(["active", "draft"]),
        ).to_list()
        used_ids = set()
        for s in active_sets:
            used_ids.update(s.question_ids)
        available = total - len(used_ids)
        can_create = available // 10
        sets_to_create = min(can_create, 50)  # cap at 50 per call

        if sets_to_create <= 0:
            results[module] = {"total_questions": total, "existing_sets": existing, "created": 0}
            continue

        prefix = module[:4].upper()
        created = []
        for i in range(sets_to_create):
            set_num = existing + i + 1
            set_number = f"{prefix}-SET-{set_num:03d}"

            query = {"_id": {"$nin": list(used_ids)}} if used_ids else {}
            questions = await coll.find(query).limit(10).to_list()
            if len(questions) < 10:
                break
            q_ids = [str(q["_id"]) for q in questions]
            used_ids.update(q_ids)

            qs = QuestionSet(
                set_number=set_number, module=module,
                question_ids=q_ids, question_count=10, status="active",
            )
            await qs.create()
            created.append(set_number)

        results[module] = {"total_questions": total, "existing_sets": existing, "created": len(created), "sets": created}

    await audit.record(principal, "question_sets.auto_created", entity="QuestionSet",
                       after=results)
    return {"results": results, "ok": True}


# --------------------------------------------------------------------------
# Exam Schedules — platform-scheduled sittings for institutions
# --------------------------------------------------------------------------

async def _resolve_profile_id_for_test(exam_test: ExamTest) -> str:
    """Return the published SimulationProfile id that backs an ExamTest.

    ExamTests are turned into SimulationProfiles (with ProfileSections) so
    they can be sat through the normal attempt engine — `_sync_exam_test_profiles`
    does that at startup and after every exam-test create/update. A schedule
    needs to know which profile its students will actually start, so we look
    it up by name and fall back to a re-sync if it has not been created yet.
    """
    from app.models.tenant import SimulationProfile
    profile = await SimulationProfile.find_one(
        SimulationProfile.name == exam_test.name,
        SimulationProfile.status == "published",
    )
    if profile is None:
        try:
            from app.main import _sync_exam_test_profiles
            await _sync_exam_test_profiles()
        except Exception:
            pass
        profile = await SimulationProfile.find_one(
            SimulationProfile.name == exam_test.name,
            SimulationProfile.status == "published",
        )
    return profile.id if profile else ""


@router.post("/exam-schedules", status_code=status.HTTP_201_CREATED)
async def create_exam_schedule(body: ScheduledExamRequest,
                               principal: Principal) -> dict:
    """Schedule an ExamTest for one or more institutions within a window."""
    test = await ExamTest.get(body.exam_test_id)
    if not test:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exam test not found")
    if not test.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "An inactive exam test cannot be scheduled")
    if body.ends_at <= body.starts_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The schedule must end after it starts")
    if body.ends_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "That window is already in the past")

    # Validate institution ids if any were supplied
    if body.tenant_ids:
        existing = {t.id for t in await Tenant.find(
            Tenant.id.in_(body.tenant_ids)).to_list()}
        missing = [t for t in body.tenant_ids if t not in existing]
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Unknown institution(s): {', '.join(missing)}")

    profile_id = await _resolve_profile_id_for_test(test)
    schedule = ScheduledExam(
        exam_test_id=test.id,
        profile_id=profile_id,
        name=test.name,
        tenant_ids=body.tenant_ids,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        max_attempts=body.max_attempts,
        is_active=body.is_active,
        created_by=principal.user_id,
    )
    await schedule.create()
    await audit.record(principal, "exam_schedule.created", entity="ScheduledExam",
                       entity_id=schedule.id,
                       after={"exam_test": test.name,
                              "window": f"{body.starts_at.isoformat()} → {body.ends_at.isoformat()}",
                              "tenant_ids": body.tenant_ids})
    return {"id": schedule.id, "ok": True}


@router.patch("/exam-schedules/{schedule_id}")
async def update_exam_schedule(schedule_id: str, body: ScheduledExamRequest,
                               principal: Principal) -> dict:
    """Update a schedule — window, audience, attempt cap or activation."""
    schedule = await ScheduledExam.get(schedule_id)
    if not schedule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    test = await ExamTest.get(body.exam_test_id)
    if not test:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exam test not found")
    if not test.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "An inactive exam test cannot be scheduled")
    if body.ends_at <= body.starts_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The schedule must end after it starts")
    if body.tenant_ids:
        existing = {t.id for t in await Tenant.find(
            Tenant.id.in_(body.tenant_ids)).to_list()}
        missing = [t for t in body.tenant_ids if t not in existing]
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Unknown institution(s): {', '.join(missing)}")

    schedule.exam_test_id = test.id
    schedule.name = test.name
    schedule.profile_id = await _resolve_profile_id_for_test(test)
    schedule.tenant_ids = body.tenant_ids
    schedule.starts_at = body.starts_at
    schedule.ends_at = body.ends_at
    schedule.max_attempts = body.max_attempts
    schedule.is_active = body.is_active
    schedule.updated_at = datetime.now(timezone.utc)
    await schedule.save()
    await audit.record(principal, "exam_schedule.updated", entity="ScheduledExam",
                       entity_id=schedule.id)
    return {"ok": True}


@router.delete("/exam-schedules/{schedule_id}")
async def delete_exam_schedule(schedule_id: str, principal: Principal) -> dict:
    """Delete a schedule. Attempts already started are untouched."""
    schedule = await ScheduledExam.get(schedule_id)
    if not schedule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    await schedule.delete()
    await audit.record(principal, "exam_schedule.deleted", entity="ScheduledExam",
                       entity_id=schedule_id)
    return {"ok": True}
