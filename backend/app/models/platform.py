"""Control-plane models — ``CommunicationIQ`` database only.

Tenant registry, platform staff, the Provider Registry, model versions,
gamification economy config, feature flags and the immutable audit log.
No student, attempt, recording or score data appears here.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from beanie import Document, Indexed
from pydantic import Field

from app.models._common import StrId


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Tenancy
# --------------------------------------------------------------------------

TENANT_TYPES: tuple[tuple[str, str], ...] = (
    ("engineering_college", "Engineering college"),
    ("degree_college", "Degree / arts & science college"),
    ("university", "University"),
    ("school", "School"),
    ("polytechnic", "Polytechnic / diploma institute"),
    ("training_institute", "Training institute"),
    ("coaching_centre", "Coaching centre"),
    ("corporate", "Corporate / enterprise L&D"),
    ("bpo", "BPO / contact centre"),
    ("staffing", "Staffing & recruitment firm"),
    ("government", "Government / skilling mission"),
    ("ngo", "NGO / foundation"),
    ("partner", "Channel partner / reseller"),
    ("internal", "Internal / demo"),
    ("other", "Other"),
)

TENANT_TYPE_KEYS = frozenset(key for key, _ in TENANT_TYPES)


class Tenant(Document):
    """A customer. Routing record for its database (PLAT-01/02)."""

    id: StrId = Field(default_factory=_uuid)
    name: str
    slug: str = Field(unique=True, index=True)
    domain: str = Field(default="", index=True)
    tenant_type: str = "engineering_college"
    # active | trial | suspended | offboarding | closed
    status: str = "trial"
    seat_limit: int = 100
    region: str = "ap-south-1 (Mumbai)"
    branding: dict = Field(default_factory=dict)
    profile: dict = Field(default_factory=dict)
    season_start: datetime | None = None
    season_end: datetime | None = None
    settings: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "tenants"





# --------------------------------------------------------------------------
# Platform staff
# --------------------------------------------------------------------------

class PlatformUser(Document):
    """Internal staff account (PLAT-16)."""

    id: StrId = Field(default_factory=_uuid)
    email: str = Field(unique=True, index=True)
    full_name: str
    password_hash: str
    role: str = "support"
    mfa_enabled: bool = False
    active: bool = True
    ui_language: str = "en"
    preferred_theme: str = ""
    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "platform_users"


class InvitationDirectory(Document):
    """Redemption lookup: token -> which institution to open a session against."""

    id: StrId = Field(default_factory=_uuid)
    token: str = Field(unique=True, index=True)
    tenant_id: str = Field(default="", index=True)
    tenant_slug: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "invitation_directory"


class TenantUserDirectory(Document):
    """Sign-in lookup: email -> which institution to open a session against."""

    id: StrId = Field(default_factory=_uuid)
    email: str = Field(unique=True, index=True)
    tenant_id: str = Field(default="", index=True)
    tenant_slug: str = Field(default="", index=True)
    active: bool = True
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "tenant_user_directory"


# --------------------------------------------------------------------------
# Provider abstraction (ENG-16..21, PLAT-07…10, PLAT-13)
# --------------------------------------------------------------------------

class ProviderRegistry(Document):
    """One registered implementation of one capability."""

    id: StrId = Field(default_factory=_uuid)
    capability: str = Field(default="", index=True)
    provider_key: str
    name: str
    tier: int = 0
    version: str = "0.1.0"
    entrypoint: str = ""
    config_schema: dict = Field(default_factory=dict)
    active: bool = True
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "provider_registry"


class ProviderConfig(Document):
    """Which provider serves a capability, for whom, and what happens on failure."""

    id: StrId = Field(default_factory=_uuid)
    capability: str = Field(default="", index=True)
    tenant_id: str | None = Field(default=None, index=True)
    primary_provider_id: str
    fallback_provider_id: str | None = None
    mode: str = "live"
    shadow_provider_id: str | None = None
    canary_percent: int = 0
    timeout_ms: int = 8000
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "provider_configs"


class ModelVersion(Document):
    """A promotable version of a model behind a provider."""

    id: StrId = Field(default_factory=_uuid)
    provider_id: str = Field(default="", index=True)
    version: str
    notes: str = ""
    eval_metrics: dict = Field(default_factory=dict)
    promoted_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "model_versions"


class ProviderCall(Document):
    """Per-call telemetry feeding the provider performance dashboard (PLAT-13)."""

    id: StrId = Field(default_factory=_uuid)
    capability: str = Field(default="", index=True)
    provider_id: str = Field(default="", index=True)
    provider_version: str = ""
    tenant_id: str | None = Field(default=None, index=True)
    latency_ms: int = 0
    ok: bool = True
    error: str = ""
    used_fallback: bool = False
    cost_paise: int = 0
    at: datetime = Field(default_factory=_now, indexed=True)

    class Settings:
        name = "provider_calls"


# --------------------------------------------------------------------------
# Configuration, flags, audit
# --------------------------------------------------------------------------

class GamificationConfig(Document):
    """The game economy, tunable without a deploy (PLAT-17)."""

    id: StrId = Field(default_factory=_uuid)
    tenant_id: str | None = Field(default=None, index=True, unique=True)
    xp_table: dict = Field(default_factory=dict)
    difficulty_multipliers: dict = Field(default_factory=dict)
    weakness_multiplier: float = 1.5
    streak_rules: dict = Field(default_factory=dict)
    free_freezes_per_month: int = 2
    quiz_xp_cap_percent: int = 40
    leagues_enabled: bool = True
    max_engagement_notifications_per_day: int = 1
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "gamification_configs"


class FeatureFlag(Document):
    id: StrId = Field(default_factory=_uuid)
    key: str = Field(default="", index=True)
    tenant_id: str | None = Field(default=None, index=True)
    enabled: bool = False
    description: str = ""

    class Settings:
        name = "feature_flags"


class AuditLog(Document):
    """Append-only record of admin and score-affecting actions (PLAT-14, NFR-11)."""

    id: StrId = Field(default_factory=_uuid)
    actor_type: str = "system"
    actor_id: str = ""
    actor_label: str = ""
    tenant_id: str | None = Field(default=None, index=True)
    action: str = Field(default="", index=True)
    entity: str = ""
    entity_id: str = ""
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    at: datetime = Field(default_factory=_now, indexed=True)

    class Settings:
        name = "audit_log"


class PlatformSetting(Document):
    """Operator-editable configuration, one JSON document per key."""

    id: StrId = Field(default_factory=_uuid)
    key: str = Field(unique=True, index=True)
    value: dict = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "platform_settings"


CONTROL_DOCUMENTS = [
    Tenant, PlatformUser, InvitationDirectory,
    TenantUserDirectory, ProviderRegistry, ProviderConfig, ModelVersion,
    ProviderCall, GamificationConfig, FeatureFlag, AuditLog, PlatformSetting,
]
