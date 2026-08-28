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
                                 TENANT_TYPES,
                                 ProviderConfig, ProviderRegistry,
                                 Tenant, TenantUserDirectory)
from app.provisioning import create_tenant_schema, validate_slug
from app.routers.tenant_writes import temporary_password
from app.schemas import (CapabilityConfigRequest, GamificationConfigOut,
                         GamificationConfigRequest,
                         LogoByUrlRequest,
                         ProviderOut, ProviderRegisterRequest,
                         ProviderUpdateRequest,
                         TenantBranding, TenantCreateRequest, TenantOut,
                         TenantProfile, TenantTypeOut, TenantUpdateRequest)
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
    branding["logo_url"] = f"/api/v1/platform/assets/{key}"
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

    password = temporary_password()
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
