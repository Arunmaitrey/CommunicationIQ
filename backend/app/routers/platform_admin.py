"""Operator console ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â the control plane.

Platform staff never read student data from here. What they see is the shape
of the business (tenants, seats) and the shape of the system
(capabilities, providers, latency, audit). Institution databases are not
reachable through any endpoint in this file.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from beanie.operators import GTE
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response as HttpResponse

from app.deps import require_platform, Principal
from app.engine.contracts import CONTRACT_FOR, Capability
# Aliased: the GET /audit route below is named `audit`, which would otherwise
# shadow the module and crash every audit.record() call here.
from app import audit as audit_log
from app.models.platform import (AuditLog, GamificationConfig,
                                 ProviderCall, ProviderConfig,
                                 ProviderRegistry, Tenant, ScheduledExam)
from app.routers.platform_writes import _tenant_out
from app.schemas import (AuditOut, CapabilityOut, GamificationConfigOut,
                         PlatformOverview, ProviderOut, TenantOut)
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



@router.get("/capabilities", response_model=list[CapabilityOut])
async def capabilities() -> list[CapabilityOut]:
    """Every pluggable capability, its contract, and what currently serves it.

    Capabilities with no configured provider are listed too ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â an unconfigured
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
            contract_version=getattr(contract, "contract_version", "ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â"),
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
async def audit_log_view(limit: int = 100) -> list[AuditOut]:
    rows = await AuditLog.find_all().sort("-at").limit(min(limit, 500)).to_list()
    return [
        AuditOut(
            id=a.id, actor_type=a.actor_type, actor_label=a.actor_label,
            tenant_id=a.tenant_id, action=a.action, entity=a.entity,
            entity_id=a.entity_id, ip_address=getattr(a, 'ip_address', ''), at=a.at,
        )
        for a in rows
    ]


# ---------------------------------------------------------------------------
# Plans, SMTP, Payment, Email Templates — read endpoints
# ---------------------------------------------------------------------------

@router.get("/plans")
async def list_plans() -> list[dict]:
    from app.db import control_db
    db = control_db()
    rows = await db["plans"].find().sort("created_at", -1).to_list(100)
    return [
        {
            "id": str(r["_id"]), "name": r.get("name", ""), "slug": r.get("slug", ""),
            "description": r.get("description", ""),
            "price_monthly": r.get("price_monthly", 0), "price_yearly": r.get("price_yearly", 0),
            "seat_limit": r.get("seat_limit", 50), "features": r.get("features", []),
            "max_questions": r.get("max_questions", 500), "max_exams_per_day": r.get("max_exams_per_day", 10),
            "has_proctoring": r.get("has_proctoring", True), "has_analytics": r.get("has_analytics", True),
            "has_custom_branding": r.get("has_custom_branding", False), "has_api_access": r.get("has_api_access", False),
            "is_active": r.get("is_active", True), "is_default": r.get("is_default", False),
        }
        for r in rows
    ]


@router.get("/smtp")
async def get_smtp(tenant_id: str | None = None) -> dict | None:
    from app.db import control_db
    db = control_db()
    doc = await db["smtp_configs"].find_one({"tenant_id": tenant_id})
    if not doc:
        return None
    return {
        "id": str(doc["_id"]), "host": doc.get("host", ""), "port": doc.get("port", 587),
        "username": doc.get("username", ""), "from_email": doc.get("from_email", ""),
        "from_name": doc.get("from_name", "CommunicationIQ"),
        "use_tls": doc.get("use_tls", True), "use_ssl": doc.get("use_ssl", False),
        "is_active": doc.get("is_active", True), "tenant_id": doc.get("tenant_id"),
        "password": "***" if doc.get("password") else "",  # masked
    }


@router.get("/payment")
async def get_payment_config(gateway: str = "stripe") -> dict | None:
    from app.db import control_db
    db = control_db()
    doc = await db["payment_configs"].find_one({"gateway": gateway})
    if not doc:
        return None
    return {
        "id": str(doc["_id"]), "gateway": doc.get("gateway", ""),
        "test_mode": doc.get("test_mode", True),
        "stripe_publishable": doc.get("stripe_publishable", ""),
        "stripe_secret": "***" if doc.get("stripe_secret") else "",
        "stripe_webhook_secret": "***" if doc.get("stripe_webhook_secret") else "",
        "razorpay_key_id": doc.get("razorpay_key_id", ""),
        "razorpay_key_secret": "***" if doc.get("razorpay_key_secret") else "",
        "currency": doc.get("currency", "INR"),
        "is_active": doc.get("is_active", False),
    }


@router.get("/email-templates")
async def list_email_templates() -> list[dict]:
    from app.db import control_db
    db = control_db()
    rows = await db["email_templates"].find().sort("created_at", -1).to_list(100)
    return [
        {
            "id": str(r["_id"]), "key": r.get("key", ""), "name": r.get("name", ""),
            "subject": r.get("subject", ""), "body_html": r.get("body_html", ""),
            "body_text": r.get("body_text", ""),
            "category": r.get("category", "transactional"),
            "is_active": r.get("is_active", True),
        }
        for r in rows
    ]


@router.get("/narration/settings")
async def narration_settings() -> dict:
    """The AI-narration configuration, secrets masked to set/last4."""
    from app import ai_settings
    overrides = await ai_settings.load_and_apply()
    return ai_settings.masked_view(overrides)


@router.get("/narration/metrics")
async def narration_metrics() -> dict:
    """Operational health of the AI narrator ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â counts, failures, cost.

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
_AUDIO_KEY = re.compile(r"^audio/[a-f0-9]{64}\.(wav|m4a|mp3)$")


# --------------------------------------------------------------------------
# Question bank management
# --------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/users")
async def tenant_users(tenant_id: str) -> list[dict]:
    """List users for a specific tenant — super admin visibility."""
    from app.db import ensure_tenant_models
    from app.models.platform import Tenant

    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    from app.db import client as _client, CONTROL_DB_NAME as _cdb
    _coll = _client[_cdb]["users"]
    raw_users = await _coll.find({"tenant_id": tenant_id}).to_list()

    def _iso(value):
        if value is None:
            return None
        # Rows written outside Beanie sometimes carry a plain string here.
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    return [
        {"id": str(u.get('_id', '')), "full_name": u.get('full_name', ''),
         "email": u.get('email', ''), "role": u.get('role', 'student'),
         "active": u.get('active', True),
         "branch": u.get('branch', ''), "year_of_study": u.get('year_of_study'),
         "roll_number": u.get('roll_number', ''),
         "last_login_at": _iso(u.get('last_login_at'))}
        for u in raw_users
    ]


@router.get("/external-users")
async def list_external_users() -> list[dict]:
    """List all external (general) users — super admin visibility."""
    from app.models.platform import Tenant
    
    # Find the general tenant
    general_tenant = await Tenant.find_one(Tenant.slug == "general")
    if not general_tenant:
        return []
    
    from app.db import client as _client, CONTROL_DB_NAME as _cdb
    _coll = _client[_cdb]["users"]
    raw_users = await _coll.find({"tenant_id": general_tenant.id}).to_list()
    
    # Get subscription info
    _db = _client[_cdb]
    plan_doc = await _db.plans.find_one({"_id": general_tenant.plan_id}) if general_tenant.plan_id else None
    
    def _iso(value):
        if value is None:
            return None
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    
    return [
        {"id": str(u.get('_id', '')), "full_name": u.get('full_name', ''),
         "email": u.get('email', ''), "role": u.get('role', 'student'),
         "active": u.get('active', True),
         "subscription": plan_doc.get("name", "Free Trial") if plan_doc else "Free Trial",
         "last_login_at": _iso(u.get('last_login_at'))}
        for u in raw_users
    ]


@router.get("/students/{user_id}/attempts")
async def student_attempts(user_id: str, tenant_id: str) -> list[dict]:
    """List attempts for a specific student â€” super admin visibility."""
    from app.db import ensure_tenant_models
    from app.models.platform import Tenant

    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    models = await ensure_tenant_models(tenant.slug)
    rows = await models.Attempt.find(
        models.Attempt.user_id == user_id).sort(-models.Attempt.created_at).to_list()

    profile_ids = list({r.profile_id for r in rows} or {""})
    profiles = await models.SimulationProfile.find(
        models.SimulationProfile.id.in_(profile_ids)).to_list()
    names = {p.id: p.name for p in profiles}

    def _iso(value):
        if value is None:
            return None
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    return [
        {"id": str(r.id), "profile_id": r.profile_id,
         "profile_name": names.get(r.profile_id, ""),
         "attempt_number": r.attempt_number, "status": r.status, "mode": r.mode,
         "is_baseline": r.is_baseline, "started_at": _iso(r.started_at),
         "submitted_at": _iso(r.submitted_at), "scored_at": _iso(r.scored_at),
         "ip_address": getattr(r, "ip_address", "")}
        for r in rows
    ]








async def _create_reading(passage_id, body):
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number, auto_create_sets
    import uuid
    models = await ensure_shared_models()
    qn = await generate_question_number("reading", control_db())
    passage = models.ReadingPassage(
        id=passage_id, question_number=qn, title=body.get("title", ""),
        kind=body.get("kind", "article"), body=body.get("body", ""),
        company=body.get("company", ""),
        word_count=len(body.get("body", "").split()),
        difficulty=body.get("difficulty", 0.0), status="published",
    )
    await passage.create()
    for q in body.get("questions", []):
        qn_q = await generate_question_number("reading", control_db())
        qi = models.QuizItem(
            id=str(uuid.uuid4()), question_number=qn_q, category="reading_comprehension",
            stem=q.get("stem", ""), options=q.get("options", []),
            correct_index=q.get("correct_index", 0),
            explanation=q.get("explanation", ""), passage_id=passage_id,
            company=body.get("company", ""),
            seconds_allowed=q.get("seconds_allowed", 30),
            difficulty=q.get("difficulty", 0.0), status="published",
        )
        await qi.create()
    await auto_create_sets("reading", control_db())




async def _create_writing(body):
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number, auto_create_sets
    import uuid
    models = await ensure_shared_models()
    prompt_id = str(uuid.uuid4())
    qn = await generate_question_number("writing", control_db())
    prompt = models.WritingPrompt(
        id=prompt_id, question_number=qn, title=body.get("title", ""),
        kind=body.get("kind", "essay"), prompt=body.get("prompt", ""),
        company=body.get("company", ""),
        scenario=body.get("scenario", ""),
        key_points=body.get("key_points", []),
        min_words=body.get("min_words", 150),
        suggested_minutes=body.get("suggested_minutes", 20),
        difficulty=body.get("difficulty", 0.0), status="published",
    )
    await prompt.create()
    await auto_create_sets("writing", control_db())
    return prompt_id




async def _create_listening(body):
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number, auto_create_sets
    import uuid
    models = await ensure_shared_models()
    passage_id = str(uuid.uuid4())
    qn = await generate_question_number("listening", control_db())
    passage = models.ListeningPassage(
        id=passage_id, question_number=qn, title=body.get("title", ""),
        kind=body.get("kind", "short_talk"),
        transcript=body.get("transcript", ""),
        company=body.get("company", ""),
        audio_key=body.get("audio_key", ""),
        accent=body.get("accent", "indian"),
        plays_allowed=body.get("plays_allowed", 1),
        approx_seconds=body.get("approx_seconds", 45),
        difficulty=body.get("difficulty", 0.0), status="published",
    )
    await passage.create()
    for q in body.get("questions", []):
        qn_q = await generate_question_number("reading", control_db())
        qi = models.QuizItem(
            id=str(uuid.uuid4()), question_number=qn_q, category="audio_comprehension",
            stem=q.get("stem", ""), options=q.get("options", []),
            correct_index=q.get("correct_index", 0),
            explanation=q.get("explanation", ""), passage_id=passage_id,
            company=body.get("company", ""),
            seconds_allowed=q.get("seconds_allowed", 30),
            difficulty=q.get("difficulty", 0.0), status="published",
        )
        await qi.create()
    await auto_create_sets("listening", control_db())
    return passage_id






async def _create_quiz(category, body):
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number, auto_create_sets
    import uuid
    models = await ensure_shared_models()
    item_id = str(uuid.uuid4())
    # Determine module from category
    module = "reading" if category == "reading_comprehension" else "quiz"
    qn = await generate_question_number(module, control_db())
    qi = models.QuizItem(
        id=item_id, question_number=qn, category=category, stem=body.get("stem", ""),
        options=body.get("options", []), correct_index=body.get("correct_index", 0),
        explanation=body.get("explanation", ""), company=body.get("company", ""),
        difficulty=body.get("difficulty", 0.3),
        seconds_allowed=30, status="published",
    )
    await qi.create()
    # Auto-create sets if enough questions
    await auto_create_sets(module, control_db())
    return item_id


async def _create_speaking(body):
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number, auto_create_sets
    import uuid
    models = await ensure_shared_models()
    item_id = str(uuid.uuid4())
    qn = await generate_question_number("speaking", control_db())
    ti = models.TaskItem(
        id=item_id, question_number=qn, task_type=body.get("task_type", "open_response"),
        prompt_text=body.get("prompt_text", ""),
        company=body.get("company", ""),
        reference_text=body.get("reference_text", ""),
        prompt_audio_key=body.get("audio_key", ""),
        difficulty=body.get("difficulty", 0.3), status="published",
    )
    await ti.create()
    await auto_create_sets("speaking", control_db())
    return item_id








# --------------------------------------------------------------------------
# Reviews
# --------------------------------------------------------------------------

@router.get("/reviews")
async def platform_reviews(limit: int = 100) -> list[dict]:
    """All reviews across all tenants, for superadmin visibility."""
    from app.db import control_db
    db = control_db()
    raw = await db.exam_reviews.find().sort("created_at", -1).limit(limit).to_list()
    if not raw:
        return []
    user_ids = list({r.get("user_id", "") for r in raw if r.get("user_id")})
    profile_ids = list({r.get("profile_id", "") for r in raw if r.get("profile_id")})
    users = {}
    if user_ids:
        async for u in db.users.find({"_id": {"$in": user_ids}}):
            users[u["_id"]] = u
    profiles = {}
    if profile_ids:
        async for p in db.simulation_profiles.find({"_id": {"$in": profile_ids}}):
            profiles[p["_id"]] = p
    return [
        {
            "id": str(r.get("_id", "")),
            "attempt_id": r.get("attempt_id", ""),
            "user_id": r.get("user_id", ""),
            "user_name": users.get(r.get("user_id", ""), {}).get("full_name", ""),
            "user_email": users.get(r.get("user_id", ""), {}).get("email", ""),
            "tenant_id": r.get("tenant_id", ""),
            "profile_name": profiles.get(r.get("profile_id", ""), {}).get("name", ""),
            "rating": r.get("rating", 0),
            "difficulty": r.get("difficulty", "just_right"),
            "comment": r.get("comment", ""),
            "created_at": r.get("created_at", ""),
        }
        for r in raw
    ]


@router.get("/questions")
async def platform_questions(category: str = "", company: str = "",
                             include_company: bool = False,
                             limit: int = 200) -> dict:
    """Question bank overview for the platform admin console.

    When no company is specified and include_company=False, returns only general
    (no-company) questions.  Pass include_company=True to get everything.
    """
    from app.models.tenant import QuizItem, TaskItem, WritingPrompt, ListeningPassage, ReadingPassage

    def _build_filter(base: dict, company_val: str) -> dict:
        f = {**base}
        if company_val:
            f["company"] = company_val
        elif not include_company:
            # Default: only general questions (company is empty or missing)
            f["company"] = {"$in": ["", None]}
        return f

    quiz_filter = _build_filter({"status": "published"}, company)
    quiz_items = await QuizItem.find(quiz_filter).limit(limit).to_list()

    task_filter = _build_filter({"status": "published"}, company)
    task_items = await TaskItem.find(task_filter).limit(limit).to_list()

    writing_filter = _build_filter({"status": "published"}, company)
    writing_prompts = await WritingPrompt.find(writing_filter).limit(limit).to_list()

    listening_filter = _build_filter({"status": "published"}, company)
    listening = await ListeningPassage.find(listening_filter).limit(limit).to_list()

    reading_filter = _build_filter({"status": "published"}, company)
    reading = await ReadingPassage.find(reading_filter).limit(limit).to_list()

    def _item_out(item, kind):
        return {
            "id": item.id,
            "kind": kind,
            "title": getattr(item, "stem", None) or getattr(item, "prompt_text", None)
                     or getattr(item, "title", None) or getattr(item, "prompt", "")[:80],
            "category": getattr(item, "category", "") or getattr(item, "task_type", "")
                        or getattr(item, "kind", ""),
            "company": getattr(item, "company", ""),
            "difficulty": getattr(item, "difficulty", 0),
            "status": getattr(item, "status", "published"),
            "audio_key": getattr(item, "audio_key", "")
                         or getattr(item, "prompt_audio_key", ""),
        }

    return {
        "quiz_items": [_item_out(i, "quiz") for i in quiz_items],
        "task_items": [_item_out(i, "task") for i in task_items],
        "writing_prompts": [_item_out(i, "writing") for i in writing_prompts],
        "listening_passages": [_item_out(i, "listening") for i in listening],
        "reading_passages": [_item_out(i, "reading") for i in reading],
        "counts": {
            "quiz_items": len(quiz_items),
            "task_items": len(task_items),
            "writing_prompts": len(writing_prompts),
            "listening_passages": len(listening),
            "reading_passages": len(reading),
        },
    }


# --------------------------------------------------------------------------
# Question creation endpoints
# --------------------------------------------------------------------------

@router.post("/questions/quiz")
async def create_quiz_item(body: dict) -> dict:
    item_id = await _create_quiz(body.get("category", "reading_comprehension"), body)
    await audit_log.record_system("platform.create_question", entity="quiz_item")
    # Auto-create sets if we have 10+ questions in this module
    try:
        from app.db import control_db
        from app.set_engine import auto_create_sets
        await auto_create_sets("quiz", control_db())
    except Exception:
        pass
    return {"id": item_id, "ok": True}


@router.post("/questions/bulk")
async def bulk_upload_questions(body: dict) -> dict:
    """Bulk upload questions from JSON payload.

    Accepts a JSON object with:
    - items: list of question objects
    - category: "quiz" | "reading" | "listening" | "writing" | "speaking"
    - company: company name (optional, empty for general)

    Each question object should have:
    - stem/question: the question text
    - options: list of answer options (for MCQ)
    - correct_index: index of correct answer (for MCQ)
    - explanation: explanation for the answer
    - difficulty: 0.0-1.0 (optional, default 0.3)
    """
    from app.db import ensure_shared_models
    import uuid

    models = await ensure_shared_models()
    items = body.get("items", [])
    category = body.get("category", "quiz")
    company = body.get("company", "")

    created = 0
    errors = []

    for i, item in enumerate(items):
        try:
            stem = item.get("stem") or item.get("question", "")
            options = item.get("options", [])
            correct_index = item.get("correct_index", 0)
            explanation = item.get("explanation", "")
            difficulty = item.get("difficulty", 0.3)

            if not stem:
                errors.append({"index": i, "error": "Missing stem/question"})
                continue

            if category == "quiz" or category == "grammar" or category == "vocabulary":
                item_id = str(uuid.uuid4())
                qi = models.QuizItem(
                    id=item_id,
                    category=category if category in ("grammar", "vocabulary") else "grammar",
                    stem=stem,
                    options=options if len(options) >= 2 else ["Option A", "Option B", "Option C", "Option D"],
                    correct_index=correct_index,
                    explanation=explanation,
                    company=company,
                    difficulty=difficulty,
                    seconds_allowed=30,
                    status="published",
                )
                await qi.create()
                created += 1

            elif category == "reading":
                # Create reading passage with questions
                passage_id = str(uuid.uuid4())
                body_text = item.get("body", item.get("passage", ""))
                passage = models.ReadingPassage(
                    id=passage_id,
                    title=stem[:100],
                    kind=item.get("kind", "article"),
                    body=body_text,
                    company=company,
                    word_count=len(body_text.split()),
                    difficulty=difficulty,
                    status="published",
                )
                await passage.create()

                # Create associated questions
                for q in item.get("questions", []):
                    qi = models.QuizItem(
                        id=str(uuid.uuid4()),
                        category="reading_comprehension",
                        stem=q.get("stem", ""),
                        options=q.get("options", []),
                        correct_index=q.get("correct_index", 0),
                        explanation=q.get("explanation", ""),
                        passage_id=passage_id,
                        company=company,
                        difficulty=q.get("difficulty", difficulty),
                        status="published",
                    )
                    await qi.create()
                created += 1

            elif category == "listening":
                passage_id = str(uuid.uuid4())
                passage = models.ListeningPassage(
                    id=passage_id,
                    title=stem[:100],
                    kind=item.get("kind", "short_talk"),
                    transcript=item.get("transcript", ""),
                    company=company,
                    audio_key=item.get("audio_key", ""),
                    accent=item.get("accent", "indian"),
                    plays_allowed=item.get("plays_allowed", 1),
                    approx_seconds=item.get("approx_seconds", 45),
                    difficulty=difficulty,
                    status="published",
                )
                await passage.create()

                for q in item.get("questions", []):
                    qi = models.QuizItem(
                        id=str(uuid.uuid4()),
                        category="audio_comprehension",
                        stem=q.get("stem", ""),
                        options=q.get("options", []),
                        correct_index=q.get("correct_index", 0),
                        explanation=q.get("explanation", ""),
                        passage_id=passage_id,
                        company=company,
                        difficulty=q.get("difficulty", difficulty),
                        status="published",
                    )
                    await qi.create()
                created += 1

            elif category == "writing":
                prompt_id = str(uuid.uuid4())
                prompt = models.WritingPrompt(
                    id=prompt_id,
                    title=stem[:100],
                    kind=item.get("kind", "essay"),
                    prompt=item.get("prompt", stem),
                    company=company,
                    scenario=item.get("scenario", ""),
                    key_points=item.get("key_points", []),
                    min_words=item.get("min_words", 150),
                    suggested_minutes=item.get("suggested_minutes", 20),
                    difficulty=difficulty,
                    status="published",
                )
                await prompt.create()
                created += 1

            elif category == "speaking":
                item_id = str(uuid.uuid4())
                ti = models.TaskItem(
                    id=item_id,
                    task_type=item.get("task_type", "open_response"),
                    prompt_text=stem,
                    company=company,
                    reference_text=item.get("reference_text", ""),
                    prompt_audio_key=item.get("audio_key", ""),
                    difficulty=difficulty,
                    status="published",
                )
                await ti.create()
                created += 1

            else:
                errors.append({"index": i, "error": f"Unknown category: {category}"})

        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    await audit_log.record_system(
        "platform.bulk_upload",
        entity=f"{category}:{company or 'general'}",
    )

    return {
        "ok": True,
        "created": created,
        "errors": errors,
        "total": len(items),
    }


@router.post("/questions/speaking")
async def create_speaking_item(body: dict) -> dict:
    item_id = await _create_speaking(body)
    await audit_log.record_system("platform.create_question", entity="task_item")
    try:
        from app.db import control_db
        from app.set_engine import auto_create_sets
        await auto_create_sets("speaking", control_db())
    except Exception:
        pass
    return {"id": item_id, "ok": True}


@router.post("/questions/reading")
async def create_reading_passage(body: dict) -> dict:
    import uuid
    passage_id = str(uuid.uuid4())
    await _create_reading(passage_id, body)
    await audit_log.record_system("platform.create_question", entity="reading_passage")
    try:
        from app.db import control_db
        from app.set_engine import auto_create_sets
        await auto_create_sets("reading", control_db())
    except Exception:
        pass
    return {"passage_id": passage_id, "ok": True}


@router.post("/questions/writing")
async def create_writing_prompt(body: dict) -> dict:
    prompt_id = await _create_writing(body)
    await audit_log.record_system("platform.create_question", entity="writing_prompt")
    try:
        from app.db import control_db
        from app.set_engine import auto_create_sets
        await auto_create_sets("writing", control_db())
    except Exception:
        pass
    return {"prompt_id": prompt_id, "ok": True}


@router.post("/questions/listening")
async def create_listening_passage(body: dict) -> dict:
    passage_id = await _create_listening(body)
    await audit_log.record_system("platform.create_question", entity="listening_passage")
    try:
        from app.db import control_db
        from app.set_engine import auto_create_sets
        await auto_create_sets("listening", control_db())
    except Exception:
        pass
    return {"passage_id": passage_id, "ok": True}


@router.post("/questions/generate")
async def generate_questions() -> dict:
    """Manually trigger AI question generation via Groq API."""
    from app.question_generator import run_daily_generation
    result = await run_daily_generation()
    return {"generated": result, "ok": True}


# ---------------------------------------------------------------------------
# Bulk import: file upload → validate → preview → confirm
# ---------------------------------------------------------------------------

import json as _json
import uuid as _uuid
from fastapi.responses import StreamingResponse as _SR
from app.question_importer import (
    parse_upload, get_template, ImportPlan, _normalise_header,
    CATEGORY_ALIASES,
)


@router.post("/questions/import/preview")
async def import_preview(
    file: UploadFile,
    category: str = "",
    company: str = "",
) -> dict:
    """Parse uploaded file and return validation results (no DB writes)."""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit
        raise HTTPException(413, "File too large (max 10 MB)")

    plan = parse_upload(file.filename or "upload.csv", content)

    # Override category if provided
    if category:
        cat = CATEGORY_ALIASES.get(category.lower(), category)
        for row in plan.rows:
            row.category = cat

    # Build preview (first 10 rows)
    previews = []
    for r in plan.rows[:10]:
        raw = r.raw
        previews.append({
            "category": r.category,
            "stem": raw.get("stem") or raw.get("prompt_text") or raw.get("prompt") or raw.get("body", ""),
            "options": [raw.get(f"option_{c}", "") for c in "abcd" if raw.get(f"option_{c}")],
            "difficulty": raw.get("difficulty", ""),
            "company": raw.get("company", "") or company,
        })

    return {
        "ok": True,
        "total": plan.total,
        "valid": plan.valid,
        "warnings": plan.warnings,
        "errors": plan.errors,
        "duplicates": plan.duplicates,
        "detected_category": plan.rows[0].category if plan.rows else category,
        "problems": [{"row": p.row, "field": p.field, "message": p.message, "severity": p.severity} for p in plan.problems],
        "preview": previews,
    }


@router.post("/questions/import/confirm")
async def import_confirm(
    file: UploadFile,
    category: str = "",
    company: str = "",
) -> dict:
    """Parse file again, validate, and insert into DB."""
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10 MB)")

    plan = parse_upload(file.filename or "upload.csv", content)
    if category:
        cat = CATEGORY_ALIASES.get(category.lower(), category)
        for row in plan.rows:
            row.category = cat

    # Only insert rows without errors
    error_rows = {p.row for p in plan.problems if p.severity == "error"}
    to_insert = [r for r in plan.rows if r.row_num not in error_rows]

    if not to_insert:
        return {"ok": False, "created": 0, "errors": len(error_rows), "message": "All rows have errors"}

    from app.db import ensure_shared_models
    models = await ensure_shared_models()
    created = 0
    cats = {}

    for r in to_insert:
        raw = r.raw
        cat = r.category
        try:
            if cat == "quiz":
                item_id = str(_uuid.uuid4())
                opts = [raw.get(f"option_{c}", "") for c in "abcd" if raw.get(f"option_{c}")]
                correct_letter = (raw.get("correct_answer") or "A").upper().strip()
                correct_idx = {"A": 0, "B": 1, "C": 2, "D": 3}.get(correct_letter, 0)
                diff = _parse_difficulty(raw.get("difficulty", "0.3"))
                qi = models.QuizItem(
                    id=item_id, category=raw.get("category") or raw.get("module") or "general",
                    stem=raw.get("stem", ""), options=opts,
                    correct_index=correct_idx, explanation=raw.get("explanation", ""),
                    company=raw.get("company", "") or company,
                    difficulty=diff, seconds_allowed=30, status="published",
                )
                await qi.create()
                created += 1
                cats["quiz"] = cats.get("quiz", 0) + 1

            elif cat == "reading":
                pid = str(_uuid.uuid4())
                await _create_reading(pid, {
                    "title": raw.get("title", ""),
                    "kind": raw.get("kind", "article"),
                    "body": raw.get("body", ""),
                    "company": raw.get("company", "") or company,
                    "difficulty": _parse_difficulty(raw.get("difficulty", "0.3")),
                })
                created += 1
                cats["reading"] = cats.get("reading", 0) + 1

            elif cat == "listening":
                pid = str(_uuid.uuid4())
                await _create_listening({
                    "title": raw.get("title", ""),
                    "kind": raw.get("kind", "short_talk"),
                    "transcript": raw.get("transcript", ""),
                    "company": raw.get("company", "") or company,
                    "audio_key": raw.get("audio_key", ""),
                    "accent": raw.get("accent", "indian"),
                    "plays_allowed": int(raw.get("plays_allowed", 1) or 1),
                    "approx_seconds": int(raw.get("approx_seconds", 45) or 45),
                    "difficulty": _parse_difficulty(raw.get("difficulty", "0.3")),
                })
                created += 1
                cats["listening"] = cats.get("listening", 0) + 1

            elif cat == "writing":
                kp = raw.get("key_points", "")
                if isinstance(kp, str):
                    kp = [k.strip() for k in kp.split(",") if k.strip()]
                await _create_writing({
                    "title": raw.get("title", ""),
                    "kind": raw.get("kind", "essay"),
                    "prompt": raw.get("prompt") or raw.get("stem", ""),
                    "company": raw.get("company", "") or company,
                    "scenario": raw.get("scenario", ""),
                    "key_points": kp,
                    "min_words": int(raw.get("min_words", 150) or 150),
                    "suggested_minutes": int(raw.get("suggested_minutes", 20) or 20),
                    "difficulty": _parse_difficulty(raw.get("difficulty", "0.3")),
                })
                created += 1
                cats["writing"] = cats.get("writing", 0) + 1

            elif cat == "speaking":
                await _create_speaking({
                    "task_type": raw.get("task_type", "open_response"),
                    "prompt_text": raw.get("prompt_text") or raw.get("stem", ""),
                    "company": raw.get("company", "") or company,
                    "reference_text": raw.get("reference_text", ""),
                    "audio_key": raw.get("audio_key", ""),
                    "difficulty": _parse_difficulty(raw.get("difficulty", "0.3")),
                })
                created += 1
                cats["speaking"] = cats.get("speaking", 0) + 1

        except Exception as exc:
            pass  # skip individual row errors silently

    await audit_log.record_system(
        "platform.import_questions",
        entity=f"{category or 'mixed'}:{company or 'general'}",
    )

    # Auto-create sets for any module that got new questions
    try:
        from app.db import control_db
        from app.set_engine import auto_create_sets
        for mod in cats:
            if mod in ("reading", "writing", "listening", "speaking", "quiz"):
                await auto_create_sets(mod, control_db())
    except Exception:
        pass

    return {
        "ok": True,
        "created": created,
        "errors": len(error_rows),
        "total": plan.total,
        "by_category": cats,
    }


def _parse_difficulty(val: str | float | int) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).lower().strip()
    mapping = {"easy": 0.2, "beginner": 0.2, "medium": 0.5, "intermediate": 0.5, "hard": 0.8, "advanced": 0.8}
    if s in mapping:
        return mapping[s]
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.5


@router.get("/questions/import/template/{category}")
async def import_template(category: str) -> HttpResponse:
    """Download a CSV template for bulk question import."""
    csv_text = get_template(category)
    return HttpResponse(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{category}_template.csv"'},
    )


# ── Company management ────────────────────────────────────────────────────

@router.get("/companies")
async def list_companies() -> list[dict]:
    """List all companies with question counts."""
    from app.models.tenant import Company, QuizItem, ReadingPassage, WritingPrompt, ListeningPassage, TaskItem
    companies = await Company.find_all().sort(Company.name).to_list()
    result = []
    for c in companies:
        quiz_count = await QuizItem.find(QuizItem.company == c.name).count()
        reading_count = await ReadingPassage.find(ReadingPassage.company == c.name).count()
        writing_count = await WritingPrompt.find(WritingPrompt.company == c.name).count()
        listening_count = await ListeningPassage.find(ListeningPassage.company == c.name).count()
        speaking_count = await TaskItem.find(TaskItem.company == c.name).count()
        result.append({
            "id": c.id, "name": c.name, "slug": c.slug,
            "color": c.color, "description": c.description,
            "is_active": c.is_active, "created_at": str(c.created_at),
            "question_counts": {
                "quiz": quiz_count, "reading": reading_count,
                "writing": writing_count, "listening": listening_count,
                "speaking": speaking_count,
                "total": quiz_count + reading_count + writing_count + listening_count + speaking_count,
            },
        })
    return result


@router.post("/companies")
async def create_company(body: dict) -> dict:
    """Create a new company."""
    from app.models.tenant import Company
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Company name is required")
    existing = await Company.find(Company.name == name).first()
    if existing:
        raise HTTPException(409, f"Company '{name}' already exists")
    slug = body.get("slug") or name.lower().replace(" ", "-")
    company = Company(
        name=name, slug=slug,
        color=body.get("color", "#6366f1"),
        description=body.get("description", ""),
    )
    await company.create()
    # A freshly created company should be reachable from the student side right
    # away: publish any profiles/tests already carrying its name.
    try:
        from app.main import _sync_company_visibility
        await _sync_company_visibility(name, True)
    except Exception:  # noqa: BLE001 — never block creation on the sync
        pass
    await audit_log.record_system("platform.create_company", entity=name)
    return {"id": company.id, "name": company.name, "ok": True}


@router.patch("/companies/{company_id}")
async def update_company(company_id: str, body: dict) -> dict:
    """Update a company's details.

    Renaming retires the old name's student-facing objects (so nothing keeps
    the previous name visible) and syncs the new name; toggling is_active
    publishes/retires profiles + tests live.
    """
    from datetime import datetime as _dt, timezone as _tz
    from app.models.tenant import Company
    from app.db import control_db
    company = await Company.get(company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    old_name = company.name
    if "name" in body:
        company.name = body["name"]
    if "slug" in body:
        company.slug = body["slug"]
    if "color" in body:
        company.color = body["color"]
    if "description" in body:
        company.description = body["description"]
    if "is_active" in body:
        company.is_active = bool(body["is_active"])
    await company.save()
    # Keep student-facing objects in step with the change (no orphans):
    #   * rename -> retire whatever still carried the old name
    #   * activation -> publish profiles/tests under the (new) name
    if "name" in body and body["name"] != old_name:
        try:
            db = control_db()
            await db.simulation_profiles.update_many(
                {"company": old_name},
                {"$set": {"status": "retired", "updated_at": _dt.now(_tz.utc)}})
            await db.exam_tests.update_many(
                {"company": old_name},
                {"$set": {"is_active": False, "updated_at": _dt.now(_tz.utc)}})
        except Exception:  # noqa: BLE001
            pass
    try:
        from app.main import _sync_company_visibility
        await _sync_company_visibility(company.name, company.is_active)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True}


@router.delete("/companies/{company_id}")
async def delete_company(company_id: str) -> dict:
    """Soft-delete a company (set is_active=false)."""
    from app.models.tenant import Company
    company = await Company.get(company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    company.is_active = False
    await company.save()
    # Retire the company's student-facing profiles + tests so deactivation is
    # visible immediately (no backend restart needed).
    try:
        from app.main import _sync_company_visibility
        await _sync_company_visibility(company.name, False)
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True}


@router.delete("/questions/{collection}/{item_id}")
async def delete_question(collection: str, item_id: str) -> dict:
    from app.models.tenant import QuizItem, TaskItem, WritingPrompt, ListeningPassage, ReadingPassage
    model_map = {
        "quiz": QuizItem, "task": TaskItem, "writing": WritingPrompt,
        "listening": ListeningPassage, "reading": ReadingPassage,
    }
    model = model_map.get(collection)
    if not model:
        raise HTTPException(400, f"Unknown collection: {collection}")
    doc = await model.get(item_id)
    if doc:
        await doc.delete()
    await audit_log.record_system("platform.delete_question", entity=f"{collection}:{item_id}")
    return {"ok": True}


@router.post("/questions/audio")
async def upload_audio(file: "UploadFile") -> dict:
    """Upload an audio file (WAV, M4A, MP3) for listening passages or prompts."""
    import uuid
    ext = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    key = f"audio/{uuid.uuid4().hex}{ext}"
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "audio")
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, key.replace("audio/", ""))
    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)
    await audit_log.record_system("platform.upload_audio", entity=key)
    return {"key": key, "size": len(content), "ok": True}


# --------------------------------------------------------------------------
# Contact Messages
# --------------------------------------------------------------------------

@router.get("/messages")
async def list_contact_messages(status: str = "") -> list[dict]:
    """List contact messages (super admin inbox)."""
    from app.models.platform import ContactMessage
    query = {}
    if status:
        query["status"] = status
    msgs = await ContactMessage.find(query).to_list()
    msgs.sort(key=lambda m: m.created_at or m.updated_at or "", reverse=True)
    return [
        {
            "id": m.id, "from_user_id": m.from_user_id,
            "from_email": m.from_email, "from_name": m.from_name,
            "from_role": m.from_role, "from_tenant_id": m.from_tenant_id,
            "subject": m.subject, "body": m.body,
            "status": m.status, "priority": m.priority,
            "replies": m.replies,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None,
        }
        for m in msgs
    ]


# --------------------------------------------------------------------------
# Exam Tests
# --------------------------------------------------------------------------

@router.get("/exam-tests")
async def list_exam_tests() -> list[dict]:
    """List all custom exam tests."""
    from app.models.platform import ExamTest
    tests = await ExamTest.find_all().to_list()
    tests.sort(key=lambda t: t.created_at or t.updated_at or "", reverse=True)
    return [
        {
            "id": t.id, "name": t.name, "description": t.description,
            "slug": t.slug, "duration_minutes": t.duration_minutes,
            "reading_questions": t.reading_questions,
            "listening_questions": t.listening_questions,
            "writing_questions": t.writing_questions,
            "speaking_questions": t.speaking_questions,
            "reading_seconds": t.reading_seconds,
            "listening_seconds": t.listening_seconds,
            "writing_seconds": t.writing_seconds,
            "speaking_seconds": t.speaking_seconds,
            "allow_pause": t.allow_pause, "show_timer": t.show_timer,
            "one_shot_audio": t.one_shot_audio,
            "is_active": t.is_active, "is_baseline": t.is_baseline,
            "company": t.company, "question_ids": t.question_ids,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tests
    ]


# --------------------------------------------------------------------------
# Exam Schedules
# --------------------------------------------------------------------------

@router.get("/exam-schedules")
async def list_exam_schedules() -> list[dict]:
    """List all scheduled exams with resolved test + institution names and
    live results (attempts started, students who started, average score)."""
    from app.models.platform import ExamTest as ET
    from app.db import control_db as _cdb
    schedules = await ScheduledExam.find_all().sort("-starts_at").to_list()
    tests = {t.id: t for t in await ET.find_all().to_list()}
    tenants = {t.id: t for t in await Tenant.find_all().to_list()}
    db = _cdb()
    now = datetime.now(timezone.utc)

    # One aggregation per schedule — small lists, never a scan per row.
    def _attempt_stats(profile_id: str, starts_at, ends_at) -> dict:
        if not profile_id:
            return {"started": 0, "students": 0, "average_score": None}
        match = {"profile_id": profile_id,
                 "status": {"$nin": ["created"]},
                 "created_at": {"$gte": starts_at, "$lte": ends_at}}
        started = db.attempts.count_documents(match)
        students = len(db.attempts.distinct("user_id", match))
        avg = db.attempts.aggregate([
            {"$match": match},
            {"$lookup": {"from": "score_records",
                          "localField": "_id", "foreignField": "attempt_id",
                          "as": "scores"}},
            {"$unwind": {"path": "$scores", "preserveNullAndEmptyArrays": False}},
            {"$match": {"scores.dimension": "overall",
                          "scores.is_shadow": False}},
            {"$group": {"_id": None, "avg": {"$avg": "$scores.score"}}},
        ]).to_list(1)
        avg_score = round(float(avg[0]["avg"]), 1) if avg and avg[0].get("avg") is not None else None
        return {"started": int(started), "students": int(students),
                "average_score": avg_score}

    out = []
    for s in schedules:
        test = tests.get(s.exam_test_id)
        if s.tenant_ids:
            inst = [
                {"id": tid, "name": tenants.get(tid).name if tenants.get(tid) else tid}
                for tid in s.tenant_ids
            ]
        else:
            inst = [{"id": "", "name": "All institutions + general"}]
        status = ("ended" if now > s.ends_at
                  else "live" if now >= s.starts_at
                  else "upcoming")
        if not s.is_active:
            status = "cancelled" if status in ("upcoming", "live") else "ended"
        out.append({
            "id": s.id,
            "exam_test_id": s.exam_test_id,
            "profile_id": s.profile_id,
            "name": s.name,
            "test": {
                "name": test.name if test else "",
                "description": test.description if test else "",
                "duration_minutes": test.duration_minutes if test else 0,
                "reading_questions": test.reading_questions if test else 0,
                "listening_questions": test.listening_questions if test else 0,
                "writing_questions": test.writing_questions if test else 0,
                "speaking_questions": test.speaking_questions if test else 0,
                "reading_seconds": test.reading_seconds if test else 0,
                "listening_seconds": test.listening_seconds if test else 0,
                "writing_seconds": test.writing_seconds if test else 0,
                "speaking_seconds": test.speaking_seconds if test else 0,
                "is_baseline": test.is_baseline if test else False,
            } if test else None,
            "institutions": inst,
            "starts_at": s.starts_at.isoformat(),
            "ends_at": s.ends_at.isoformat(),
            "max_attempts": s.max_attempts,
            "is_active": s.is_active,
            "status": status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "results": _attempt_stats(s.profile_id, s.starts_at, s.ends_at),
        })
    return out


# --------------------------------------------------------------------------
# Question Sets
# --------------------------------------------------------------------------

@router.get("/question-sets")
async def list_question_sets(module: str = "") -> list[dict]:
    """List all question sets, optionally filtered by module."""
    from app.models.platform import QuestionSet
    query = {}
    if module:
        query["module"] = module
    sets = await QuestionSet.find(query).sort("created_at", -1).to_list()
    return [
        {
            "id": s.id, "set_number": s.set_number, "module": s.module,
            "question_ids": s.question_ids, "question_count": s.question_count,
            "status": s.status, "usage_count": s.usage_count,
            "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in sets
    ]


@router.get("/question-sets/stats")
async def question_set_stats() -> dict:
    """Get question set availability per module."""
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
    stats = {}
    for module, coll_name in coll_map.items():
        total = await db[coll_name].count_documents({})
        active_sets = await QuestionSet.find(
            QuestionSet.module == module, QuestionSet.status == "active"
        ).count()
        draft_sets = await QuestionSet.find(
            QuestionSet.module == module, QuestionSet.status == "draft"
        ).count()
        stats[module] = {
            "total_questions": total,
            "active_sets": active_sets,
            "draft_sets": draft_sets,
            "questions_available": total,
        }
    return stats


# --------------------------------------------------------------------------
# Prompt audio bank — browse & preview the pre-rendered TTS clips
# --------------------------------------------------------------------------

_PROMPT_AUDIO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "prompt_audio")


@router.get("/prompt-audio")
async def list_prompt_audio() -> dict:
    """List all pre-rendered prompt audio files with metadata."""
    files = []
    if os.path.isdir(_PROMPT_AUDIO_DIR):
        for name in sorted(os.listdir(_PROMPT_AUDIO_DIR)):
            path = os.path.join(_PROMPT_AUDIO_DIR, name)
            if os.path.isfile(path):
                ext = os.path.splitext(name)[1].lower()
                size = os.path.getsize(path)
                files.append({"name": name, "ext": ext, "size": size})
    return {"files": files, "count": len(files)}


# Served on asset_router (no auth) so the browser <audio> element can play it.


_PROMPT_AUDIO_SAFE = re.compile(r"^[a-f0-9\-]+\.(wav|m4a|mp3)$")


@asset_router.get("/assets/{key:path}")
async def serve_prompt_audio(key: str) -> HttpResponse:
    """Serve a pre-rendered prompt audio file for playback.

    Falls through to the branding/audio handler below if the key doesn't match
    the prompt-audio pattern.
    """
    if _PROMPT_AUDIO_SAFE.match(key):
        path = os.path.join(_PROMPT_AUDIO_DIR, key)
        if os.path.isfile(path):
            ext = os.path.splitext(key)[1].lower()
            media = {".m4a": "audio/mp4", ".wav": "audio/wav", ".mp3": "audio/mpeg"}.get(ext, "application/octet-stream")
            with open(path, "rb") as f:
                data = f.read()
            return HttpResponse(content=data, media_type=media,
                                headers={"Cache-Control": "public, max-age=600",
                                         "X-Content-Type-Options": "nosniff"})

    # Not a prompt audio file — try branding assets and uploaded audio below.
    if _ASSET_KEY.match(key):
        storage = get_storage()
        if not storage.exists(key):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        try:
            data = storage.get(key)
        except (ValueError, OSError) as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
        ext = key.rsplit(".", 1)[-1]
        media = _ASSET_TYPES.get(ext, "application/octet-stream")
        return HttpResponse(
            content=data, media_type=media,
            headers={"Cache-Control": "public, max-age=300",
                     "X-Content-Type-Options": "nosniff",
                     "Content-Disposition": "inline"},
        )

    if _AUDIO_KEY.match(key):
        audio_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "audio")
        fname = key.replace("audio/", "")
        path = os.path.join(audio_dir, fname)
        if not os.path.isfile(path):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        ext = os.path.splitext(fname)[1].lower()
        media = {".wav": "audio/wav", ".m4a": "audio/mp4", ".mp3": "audio/mpeg"}.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            data = f.read()
        return HttpResponse(content=data, media_type=media,
                            headers={"Cache-Control": "public, max-age=600",
                                     "X-Content-Type-Options": "nosniff"})

    raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


# ---------------------------------------------------------------------------
# Question Sets — management endpoints
# ---------------------------------------------------------------------------


@router.get("/sets")
async def list_sets(module: str = "", status: str = "", company: str = "") -> list[dict]:
    """List question sets with optional filters."""
    from app.models.platform import QuestionSet, ExamTest
    query = {}
    if module:
        query["module"] = module
    if status:
        query["status"] = status
    if company:
        query["company"] = company
    raw = await QuestionSet.find(query).to_list(5000)
    sets = sorted(raw, key=lambda s: s.set_number or "")

    # Find which exam tests use each module+company combo
    all_tests = await ExamTest.find({}).to_list(500)
    test_map = {}
    for t in all_tests:
        key = (t.company or "")
        if key not in test_map:
            test_map[key] = []
        test_map[key].append({"name": t.name, "slug": t.slug})

    return [
        {
            "id": str(s.id), "set_number": s.set_number, "module": s.module,
            "company": s.company, "question_count": s.question_count,
            "question_numbers": s.question_numbers,
            "status": s.status, "is_used": s.is_used,
            "usage_count": s.usage_count,
            "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "linked_tests": test_map.get(s.company or "", []),
        }
        for s in sets
    ]


@router.get("/sets/summary")
async def sets_summary() -> dict:
    """Summary of set availability per module."""
    from app.set_engine import get_set_status_summary
    return await get_set_status_summary()


@router.get("/sets/summary-by-company")
async def sets_summary_by_company() -> dict:
    """Per-company summary of set availability per module."""
    from app.db import control_db
    db = control_db()
    pipeline = [
        {"$group": {"_id": {"company": "$company", "module": "$module"},
                    "sets": {"$sum": 1}, "questions": {"$sum": "$question_count"}}},
    ]
    result = await db.question_sets.aggregate(pipeline).to_list(5000)
    out: dict[str, dict] = {}
    for r in result:
        c = r["_id"].get("company") or ""
        m = r["_id"].get("module") or ""
        if c not in out:
            out[c] = {}
        out[c][m] = {"active_sets": r["sets"], "questions_available": r["questions"]}
    return out


@router.post("/sets/generate")
async def generate_sets(module: str, company: str = "") -> dict:
    """Manually trigger set generation for a module."""
    from app.db import control_db
    from app.set_engine import auto_create_sets
    created = await auto_create_sets(module, control_db())
    await audit_log.record_system("platform.generate_sets", entity="question_set", after={"module": module, "created": len(created)})
    return {"created": len(created), "sets": created}


@router.patch("/sets/{set_id}")
async def update_set(set_id: str, body: dict) -> dict:
    """Update a set's status."""
    from app.models.platform import QuestionSet
    s = await QuestionSet.get(set_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set not found")
    if "status" in body:
        s.status = body["status"]
    s.updated_at = datetime.now(timezone.utc)
    await s.save()
    return {"ok": True, "status": s.status}


@router.delete("/sets/{set_id}")
async def delete_set(set_id: str) -> dict:
    """Delete a draft set only."""
    from app.models.platform import QuestionSet
    s = await QuestionSet.get(set_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set not found")
    if s.status == "active" and s.usage_count > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete a set that has been used. Archive it instead.")
    await s.delete()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Assessment assignment — for student attempt start
# ---------------------------------------------------------------------------


@router.post("/assign")
async def assign_for_attempt(body: dict) -> dict:
    """Assign random sets for a student attempt.

    Body: {"assessment_id": "...", "company": ""}
    Returns: {"assigned_sets": {...}, "assigned_questions": {...}}
    """
    from app.db import control_db
    from app.set_engine import assign_sets_for_attempt
    from app.models.platform import ExamTest

    assessment_id = body.get("assessment_id", "")
    company = body.get("company", "")

    if assessment_id:
        test = await ExamTest.get(assessment_id)
        if not test:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")
        config = {
            "reading": test.reading_questions,
            "writing": test.writing_questions,
            "listening": test.listening_questions,
            "speaking": test.speaking_questions,
        }
    else:
        config = {"reading": 10, "writing": 10, "listening": 10, "speaking": 0}

    try:
        result = await assign_sets_for_attempt(config, company, control_db())
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    return result


# ---------------------------------------------------------------------------
# Bulk import company questions
# ---------------------------------------------------------------------------


@router.post("/questions/bulk-import")
async def bulk_import_company_questions(body: dict) -> dict:
    """Bulk import company questions from JSON.

    Body: {"company": "ADP", "sections": [{"name": "...", "questions": [{"question": "...", "options": [...], "correct_answer": "B", "explanation": "..."}]}]}
    """
    from app.db import control_db
    from app.models.platform import Company
    from app.set_engine import generate_question_number, auto_create_sets
    import uuid

    company_name = body.get("company", "")
    sections = body.get("sections", [])

    if not company_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "company is required")

    # Ensure company exists
    existing = await Company.find_one(Company.name == company_name)
    if not existing:
        await Company(name=company_name, description=f"{company_name} Assessment", is_active=True).create()

    db = control_db()
    total = 0

    for section in sections:
        questions = section.get("questions", [])
        for q in questions:
            diff_str = q.get("difficulty", "medium")
            difficulty_val = {"easy": 0.3, "medium": 0.5, "hard": 0.8, "medium_hard": 0.65}.get(diff_str, 0.5)
            correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
            correct_index = correct_map.get(q.get("correct_answer", "A"), 0)
            qn = await generate_question_number("reading", db)
            qi = QuizItem(
                id=str(uuid.uuid4()), question_number=qn, category="reading_comprehension",
                stem=q.get("question", ""), options=q.get("options", []),
                correct_index=correct_index, explanation=q.get("explanation", ""),
                company=company_name, difficulty=difficulty_val, seconds_allowed=30,
                status="published",
            )
            await qi.create()
            total += 1

    await auto_create_sets("reading", db)
    await audit_log.record_system("platform.bulk_import_questions", entity="quiz_item",
                                   after={"company": company_name, "count": total})
    return {"ok": True, "imported": total, "company": company_name}
