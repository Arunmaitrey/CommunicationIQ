"""Control-plane models — ``CommunicationIQ`` database only.

Tenant registry, plans and subscriptions, platform staff, the Provider
Registry, model versions, gamification economy config, feature flags and the
immutable audit log. Also the question bank's own control surface: exam
tests, question sets, exam scheduling, SMTP/payment/email-template config and
inbound contact messages. No student, attempt, recording or score data
appears here.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from beanie import Document, Indexed
from pydantic import Field

from app.models._common import CreatedAt, StrId


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Tenancy, plans, billing
# --------------------------------------------------------------------------

class BillingPlan(Document):
    """Versioned pricing template used only by the GST invoicing flow
    (PLAT-03, BILL-04) -- a separate collection from the customer-facing
    ``Plan`` below. The two were briefly the same class pointed at the same
    "plans" collection with incompatible field shapes; this is the half that
    was never wired to real data (tracked separately, left as-is)."""

    id: StrId = Field(default_factory=_uuid)
    code: str = Field(default="", index=True)
    name: str
    version: int = 1
    # per_seat | flat | usage | pilot
    billing_model: str = "per_seat"
    currency: str = "INR"
    price_per_seat: float = 0
    price_flat: float = 0
    # Attempts a student gets per simulation profile before re-purchase (STU-09).
    attempt_allowance: int = 3
    features: dict = Field(default_factory=dict)
    active: bool = True
    created_at: CreatedAt = Field(default_factory=_now)

    class Settings:
        name = "billing_plans"


class Plan(Document):
    """Subscription plan that controls feature access and limits -- the one
    the platform-admin plans UI and student subscription flow actually read
    and write."""
    id: StrId = Field(default_factory=_uuid, alias="_id")
    name: str = ""
    slug: str = Field(default="", unique=True, index=True)
    description: str = ""
    price_monthly: float = 0.0
    price_yearly: float = 0.0
    seat_limit: int = 50
    features: list[str] = Field(default_factory=list)
    max_questions: int = 500
    max_exams_per_day: int = 10
    has_proctoring: bool = True
    has_analytics: bool = True
    has_custom_branding: bool = False
    has_api_access: bool = False
    is_active: bool = True
    is_default: bool = False
    created_at: CreatedAt = Field(default_factory=_now)

    class Settings:
        name = "plans"


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
    # Email domain for self-service student signup (e.g. "stmarys.edu") —
    # empty for a tenant that only admits students by admin-created account
    # or invitation. "" rather than unique-indexed: two tenants sharing one
    # domain is a real, if rare, case (a group of colleges under one mail
    # system), and signup already falls back to "no institution found" for
    # an empty domain, so there is nothing to enforce uniqueness against yet.
    domain: str = ""
    tenant_type: str = "engineering_college"
    # active | trial | suspended | offboarding | closed
    status: str = "trial"
    plan_id: str | None = None
    seat_limit: int = 100
    region: str = "ap-south-1 (Mumbai)"
    branding: dict = Field(default_factory=dict)
    profile: dict = Field(default_factory=dict)
    season_start: datetime | None = None
    season_end: datetime | None = None
    settings: dict = Field(default_factory=dict)
    created_at: CreatedAt = Field(default_factory=_now)

    class Settings:
        name = "tenants"


class Subscription(Document):
    __tablename__ = "subscriptions"

    id: StrId = Field(default_factory=_uuid)
    tenant_id: str = Field(default="", index=True)
    plan_id: str
    status: str = "trialing"
    seats: int = 0
    negotiated_price: float | None = None
    started_at: datetime = Field(default_factory=_now)
    trial_ends_at: datetime | None = None
    renews_at: datetime | None = None

    class Settings:
        name = "subscriptions"


class Invoice(Document):
    """GST-compliant invoice record (BILL-04)."""

    id: StrId = Field(default_factory=_uuid)
    tenant_id: str = Field(default="", index=True)
    number: str = Field(unique=True, index=True)
    period_start: datetime
    period_end: datetime
    subtotal: float = 0
    gst_rate: float = 18.0
    gst_amount: float = 0
    total: float = 0
    currency: str = "INR"
    status: str = "draft"
    issued_at: datetime | None = None
    created_at: CreatedAt = Field(default_factory=_now)

    class Settings:
        name = "invoices"


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
    last_login_at: datetime | None = None
    created_at: CreatedAt = Field(default_factory=_now)

    class Settings:
        name = "platform_users"


class InvitationDirectory(Document):
    """Redemption lookup: token -> which institution to open a session against."""

    id: StrId = Field(default_factory=_uuid)
    token: str = Field(unique=True, index=True)
    tenant_id: str = Field(default="", index=True)
    tenant_slug: str = Field(default="", index=True)
    created_at: CreatedAt = Field(default_factory=_now)

    class Settings:
        name = "invitation_directory"


class TenantUserDirectory(Document):
    """Sign-in lookup: email -> which institution to open a session against."""

    id: StrId = Field(default_factory=_uuid)
    email: str = Field(unique=True, index=True)
    tenant_id: str = Field(default="", index=True)
    tenant_slug: str = Field(default="", index=True)
    active: bool = True
    created_at: CreatedAt = Field(default_factory=_now)

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
    created_at: CreatedAt = Field(default_factory=_now)

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
    created_at: CreatedAt = Field(default_factory=_now)

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


# --------------------------------------------------------------------------
# Question bank, exam tests and scheduling, operator communication
# --------------------------------------------------------------------------

class SmtpConfig(Document):
    """SMTP settings for sending emails."""
    id: StrId = Field(default_factory=_uuid, alias="_id")
    tenant_id: str | None = None
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""
    from_name: str = "CommunicationIQ"
    use_tls: bool = True
    use_ssl: bool = False
    is_active: bool = True
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "smtp_configs"


class PaymentConfig(Document):
    """Payment gateway credentials."""
    id: StrId = Field(default_factory=_uuid, alias="_id")
    gateway: str = ""
    test_mode: bool = True
    stripe_publishable: str = ""
    stripe_secret: str = ""
    stripe_webhook_secret: str = ""
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    currency: str = "INR"
    is_active: bool = False
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "payment_configs"


class EmailTemplate(Document):
    """Reusable email templates."""
    id: StrId = Field(default_factory=_uuid, alias="_id")
    key: str = Field(default="", unique=True, index=True)
    name: str = ""
    subject: str = ""
    body_html: str = ""
    body_text: str = ""
    category: str = "transactional"
    is_active: bool = True
    created_at: CreatedAt = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "email_templates"


class ContactMessage(Document):
    """Messages from users to platform super admins (contact form submissions)."""
    id: StrId = Field(default_factory=_uuid, alias="_id")
    from_user_id: str = ""
    from_email: str = ""
    from_name: str = ""
    from_role: str = ""  # student, tenant_admin, or empty
    from_tenant_id: str | None = None
    subject: str = ""
    body: str = ""
    status: str = "open"  # open, read, resolved
    priority: str = "normal"  # low, normal, high, urgent
    replies: list[dict] = Field(default_factory=list)  # [{from: "admin", text: "...", at: "..."}]
    created_at: CreatedAt = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "contact_messages"


class ExamTest(Document):
    """Custom test configurations created by super admin."""
    id: StrId = Field(default_factory=_uuid, alias="_id")
    name: str = ""
    description: str = ""
    slug: str = Field(default="", index=True)
    duration_minutes: int = 30
    # Weightage per section
    reading_questions: int = 10
    listening_questions: int = 10
    writing_questions: int = 10
    speaking_questions: int = 0
    # Timing per section in seconds
    reading_seconds: int = 600
    listening_seconds: int = 600
    writing_seconds: int = 600
    speaking_seconds: int = 0
    # Restrictions
    allow_pause: bool = False
    show_timer: bool = True
    one_shot_audio: bool = True
    is_active: bool = True
    is_baseline: bool = False
    company: str = ""  # empty = general (no company)
    # Question IDs organized by section
    question_ids: dict = Field(default_factory=dict)  # {reading: [...], listening: [...], writing: [...]}
    created_at: CreatedAt = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "exam_tests"


class QuestionSet(Document):
    """A set of exactly 10 questions from the same module."""
    id: StrId = Field(default_factory=_uuid, alias="_id")
    set_number: str = Field(default="", index=True)  # e.g. "READSET-001", "WRITESET-003"
    module: str = Field(default="", index=True)  # reading, writing, listening, speaking, quiz
    company: str = Field(default="", index=True)  # empty = general
    question_ids: list[str] = Field(default_factory=list)  # exactly 10 question IDs
    question_numbers: list[str] = Field(default_factory=list)  # human-readable numbers
    question_count: int = 10
    status: str = Field(default="draft", index=True)  # draft, active, inactive, archived
    is_used: bool = False
    usage_count: int = 0
    last_used_at: datetime | None = None
    created_at: CreatedAt = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "question_sets"


class ScheduledExam(Document):
    """An ExamTest opened to one or more institutions for a fixed window
    (Phase 4 of the exam-scheduling feature). Referenced by the merged
    feat/exam-section PR's routers but never actually defined there -- the
    import would have raised ImportError at startup. Field shape below is
    reconstructed from every read/write site in platform_admin.py and
    platform_writes.py (create/update/list/delete), not guessed."""
    id: StrId = Field(default_factory=_uuid, alias="_id")
    exam_test_id: str = Field(default="", index=True)
    profile_id: str = ""
    name: str = ""
    tenant_ids: list[str] = Field(default_factory=list)  # empty = all institutions + general
    starts_at: datetime
    ends_at: datetime
    max_attempts: int = 1
    is_active: bool = True
    created_by: str = ""
    created_at: CreatedAt = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "scheduled_exams"


CONTROL_DOCUMENTS = [
    BillingPlan, Plan, Tenant, Subscription, Invoice, PlatformUser,
    InvitationDirectory, TenantUserDirectory, ProviderRegistry, ProviderConfig,
    ModelVersion, ProviderCall, GamificationConfig, FeatureFlag, AuditLog,
    PlatformSetting, SmtpConfig, PaymentConfig, EmailTemplate, ContactMessage,
    ExamTest, QuestionSet, ScheduledExam,
]
