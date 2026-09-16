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
    from app.set_engine import generate_question_number
    import uuid
    models = await ensure_shared_models()
    company = body.get("company", "")
    title = body.get("title", "")
    body_text = body.get("body", "")
    if not body_text or not body_text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reading passage requires body text")
    existing = await models.ReadingPassage.find_one(
        models.ReadingPassage.title == title,
        models.ReadingPassage.company == company,
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate reading passage (same title/company)")
    qn = await generate_question_number("reading", control_db())
    passage = models.ReadingPassage(
        id=passage_id, question_number=qn, title=title,
        kind=body.get("kind", "article"), body=body_text,
        company=company,
        word_count=len(body_text.split()),
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
            company=company,
            seconds_allowed=q.get("seconds_allowed", 30),
            difficulty=q.get("difficulty", 0.0), status="published",
        )
        await qi.create()



async def _create_writing(body):
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number
    import uuid
    models = await ensure_shared_models()
    company = body.get("company", "")
    title = body.get("title", "")
    prompt_text = body.get("prompt", "")
    if not prompt_text or not prompt_text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Writing prompt requires prompt text")
    existing = await models.WritingPrompt.find_one(
        models.WritingPrompt.title == title,
        models.WritingPrompt.company == company,
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate writing prompt (same title/company)")
    prompt_id = str(uuid.uuid4())
    qn = await generate_question_number("writing", control_db())
    prompt = models.WritingPrompt(
        id=prompt_id, question_number=qn, title=title,
        kind=body.get("kind", "essay"), prompt=prompt_text,
        company=company,
        scenario=body.get("scenario", ""),
        key_points=body.get("key_points", []),
        min_words=body.get("min_words", 150),
        suggested_minutes=body.get("suggested_minutes", 20),
        difficulty=body.get("difficulty", 0.0), status="published",
    )
    await prompt.create()
    return prompt_id




async def _create_listening(body):
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number
    import uuid
    models = await ensure_shared_models()
    company = body.get("company", "")
    title = body.get("title", "")
    transcript = body.get("transcript", "")
    if not transcript or not transcript.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Listening passage requires transcript")
    existing = await models.ListeningPassage.find_one(
        models.ListeningPassage.title == title,
        models.ListeningPassage.company == company,
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate listening passage (same title/company)")
    passage_id = str(uuid.uuid4())
    qn = await generate_question_number("listening", control_db())
    passage = models.ListeningPassage(
        id=passage_id, question_number=qn, title=title,
        kind=body.get("kind", "short_talk"),
        transcript=transcript,
        company=company,
        audio_key=body.get("audio_key", ""),
        accent=body.get("accent", "indian"),
        plays_allowed=body.get("plays_allowed", 1),
        approx_seconds=body.get("approx_seconds", 45),
        difficulty=body.get("difficulty", 0.0), status="published",
    )
    await passage.create()
    for q in body.get("questions", []):
        qn_q = await generate_question_number("listening", control_db())
        qi = models.QuizItem(
            id=str(uuid.uuid4()), question_number=qn_q, category="audio_comprehension",
            stem=q.get("stem", ""), options=q.get("options", []),
            correct_index=q.get("correct_index", 0),
            explanation=q.get("explanation", ""), passage_id=passage_id,
            company=company,
            seconds_allowed=q.get("seconds_allowed", 30),
            difficulty=q.get("difficulty", 0.0), status="published",
        )
        await qi.create()
    return passage_id






async def _create_quiz(category, body):
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number
    import uuid
    models = await ensure_shared_models()
    item_id = str(uuid.uuid4())
    company = body.get("company", "")
    stem = body.get("stem", "")
    if not stem or not stem.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Question stem is required")
    options = body.get("options", [])
    if not options or len(options) < 2:
        options = ["Option A", "Option B", "Option C", "Option D"]
    correct_index = body.get("correct_index", 0)
    if not isinstance(correct_index, int) or correct_index < 0 or correct_index >= len(options):
        correct_index = 0
    existing = await models.QuizItem.find_one(
        models.QuizItem.stem == stem,
        models.QuizItem.category == category,
        models.QuizItem.company == company,
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate question (same stem/category/company)")
    module = "reading" if category == "reading_comprehension" else "quiz"
    qn = await generate_question_number(module, control_db())
    qi = models.QuizItem(
        id=item_id, question_number=qn, category=category, stem=stem,
        options=options, correct_index=correct_index,
        explanation=body.get("explanation", ""), company=company,
        difficulty=body.get("difficulty", 0.3),
        seconds_allowed=30, status="published",
    )
    await qi.create()
    return item_id


async def _create_speaking(body):
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number
    import uuid
    models = await ensure_shared_models()
    item_id = str(uuid.uuid4())
    company = body.get("company", "")
    prompt_text = body.get("prompt_text", "")
    if not prompt_text or not prompt_text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Speaking task requires prompt text")
    existing = await models.TaskItem.find_one(
        models.TaskItem.prompt_text == prompt_text,
        models.TaskItem.company == company,
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate speaking item (same prompt/company)")
    qn = await generate_question_number("speaking", control_db())
    ti = models.TaskItem(
        id=item_id, question_number=qn, task_type=body.get("task_type", "open_response"),
        prompt_text=prompt_text,
        company=company,
        reference_text=body.get("reference_text", ""),
        prompt_audio_key=body.get("audio_key", ""),
        difficulty=body.get("difficulty", 0.3), status="published",
    )
    await ti.create()
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
# Question bank item listing — paginated, per category (+ optional company).
# This is the endpoint the Question Bank console lists questions from.
# --------------------------------------------------------------------------

_QUESTION_CATEGORY_MODEL = {
    "reading": "ReadingPassage",
    "writing": "WritingPrompt",
    "listening": "ListeningPassage",
    "speaking": "TaskItem",
    "grammar": "QuizItem",
    "vocabulary": "QuizItem",
}


@router.get("/questions/items")
async def list_question_items(tenant_id: str, category: str = "reading",
                              page: int = 1, page_size: int = 10,
                              company: str = "") -> dict:
    """Return actual question items for a category (paginated).

    If *company* is supplied, results are filtered to items tagged with that
    company name. The total count also reflects the filter so pagination
    stays correct. tenant_id is accepted for API compatibility — the question
    bank is shared across institutions, so it does not change the result.
    """
    from app.models.tenant import (QuizItem, TaskItem, WritingPrompt,
                                   ListeningPassage, ReadingPassage)

    model_map = {
        "reading": ReadingPassage, "writing": WritingPrompt,
        "listening": ListeningPassage, "speaking": TaskItem,
        "grammar": QuizItem, "vocabulary": QuizItem,
    }
    model = model_map.get(category)
    if model is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unknown category {category!r}")

    base = [model.status == "published"]
    if company:
        base.append(model.company == company)
    q = model.find(*base)
    total = await q.count()
    skip = max(0, (page - 1) * page_size)
    docs = await q.sort("-created_at").skip(skip).limit(page_size).to_list()

    items = []
    for d in docs:
        out = {
            "id": str(d.id),
            "category": category,
            "company": getattr(d, "company", "") or "",
            "status": getattr(d, "status", "published"),
            "created_at": (getattr(d, "created_at", None).isoformat()
                           if getattr(d, "created_at", None) else None),
        }
        if category == "speaking":
            out["title"] = getattr(d, "title", "")
            out["task_type"] = getattr(d, "task_type", "")
            out["prompt"] = getattr(d, "prompt", "")
            out["answer"] = getattr(d, "answer", "") or getattr(d, "reference", "")
            out["seconds_allowed"] = getattr(d, "seconds_allowed", None)
        elif category in ("grammar", "vocabulary"):
            out["stem"] = getattr(d, "stem", "")
            out["options"] = getattr(d, "options", [])
            out["correct_index"] = getattr(d, "correct_index", 0)
            out["explanation"] = getattr(d, "explanation", "")
            out["question_number"] = getattr(d, "question_number", "")
        elif category == "writing":
            out["title"] = getattr(d, "title", "")
            out["prompt"] = getattr(d, "prompt", "") or getattr(d, "body", "")
            out["kind"] = getattr(d, "kind", "")
        elif category == "listening":
            out["title"] = getattr(d, "title", "")
            out["transcript"] = getattr(d, "transcript", "")
            out["audio_key"] = getattr(d, "audio_key", "")
            # Comprehension questions attach to the passage via passage_id.
            n = await QuizItem.find(QuizItem.passage_id == str(d.id)).count()
            out["question_count"] = n
        elif category == "reading":
            out["title"] = getattr(d, "title", "")
            out["body"] = getattr(d, "body", "")
            n = await QuizItem.find(QuizItem.passage_id == str(d.id)).count()
            out["question_count"] = n
        items.append(out)

    return {"items": items, "total": total, "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size)}


# --------------------------------------------------------------------------
# Module-specific question bank endpoints for the Exam Test Question Bank UI.
# These return questions grouped by module so the admin can browse and assign.
# --------------------------------------------------------------------------

@router.get("/reading/passages")
async def platform_reading_passages(company: str = "", limit: int = 5000) -> list:
    """Reading comprehension questions (quiz_items with reading categories)
    plus reading passages."""
    from app.models.tenant import QuizItem, ReadingPassage
    items = []
    # Reading comprehension quiz items
    qf: dict = {"status": "published", "category": {"$in": ["reading_comprehension", "grammar", "vocabulary"]}}
    if company:
        qf["company"] = company
    for q in await QuizItem.find(qf).limit(limit).to_list():
        items.append({
            "id": str(q.id), "title": q.stem, "category": q.category,
            "company": getattr(q, "company", "") or "",
            "options": getattr(q, "options", []),
            "correct_index": getattr(q, "correct_index", 0),
            "explanation": getattr(q, "explanation", ""),
            "question_number": getattr(q, "question_number", ""),
        })
    # Reading passages
    rf: dict = {"status": "published"}
    if company:
        rf["company"] = company
    for p in await ReadingPassage.find(rf).limit(limit).to_list():
        items.append({
            "id": str(p.id), "title": p.title, "category": "reading_passage",
            "company": getattr(p, "company", "") or "",
            "body": getattr(p, "body", ""),
        })
    return items


@router.get("/listening/passages")
async def platform_listening_passages(company: str = "", limit: int = 5000) -> list:
    """Listening passages and audio comprehension quiz items."""
    from app.models.tenant import ListeningPassage, QuizItem
    items = []
    lf: dict = {"status": "published"}
    if company:
        lf["company"] = company
    for p in await ListeningPassage.find(lf).limit(limit).to_list():
        n = await QuizItem.find(QuizItem.passage_id == str(p.id)).count()
        items.append({
            "id": str(p.id), "title": p.title, "category": "listening_passage",
            "company": getattr(p, "company", "") or "",
            "transcript": getattr(p, "transcript", ""),
            "audio_key": getattr(p, "audio_key", ""),
            "question_count": n,
        })
    # Audio comprehension quiz items (standalone)
    qf: dict = {"status": "published", "category": "audio_comprehension"}
    if company:
        qf["company"] = company
    for q in await QuizItem.find(qf).limit(limit).to_list():
        items.append({
            "id": str(q.id), "title": q.stem, "category": "audio_comprehension",
            "company": getattr(q, "company", "") or "",
            "options": getattr(q, "options", []),
            "correct_index": getattr(q, "correct_index", 0),
            "explanation": getattr(q, "explanation", ""),
            "passage_id": getattr(q, "passage_id", ""),
        })
    return items


@router.get("/writing/prompts")
async def platform_writing_prompts(company: str = "", limit: int = 5000) -> list:
    """Writing prompts (essay, email, etc.)."""
    from app.models.tenant import WritingPrompt
    items = []
    wf: dict = {"status": "published"}
    if company:
        wf["company"] = company
    for p in await WritingPrompt.find(wf).limit(limit).to_list():
        items.append({
            "id": str(p.id), "title": p.title, "category": p.kind or "essay",
            "company": getattr(p, "company", "") or "",
            "prompt": getattr(p, "prompt", ""),
            "kind": getattr(p, "kind", ""),
        })
    return items


@router.get("/speaking/tasks")
async def platform_speaking_tasks(company: str = "", limit: int = 5000) -> list:
    """Speaking tasks (read_aloud, listen_and_repeat, open_response, etc.)."""
    from app.models.tenant import TaskItem
    items = []
    tf = {"status": "published"}
    if company:
        tf["company"] = company
    for t in await TaskItem.find(tf).limit(limit).to_list():
        items.append({
            "id": str(t.id), "title": t.prompt_text, "category": t.task_type,
            "company": getattr(t, "company", "") or "",
            "task_type": getattr(t, "task_type", ""),
            "prompt_text": getattr(t, "prompt_text", ""),
            "reference_text": getattr(t, "reference_text", ""),
            "difficulty": getattr(t, "difficulty", 0),
        })
    return items


@router.get("/questions/company-counts")
async def question_company_counts(tenant_id: str = "") -> dict:
    """Per-company question counts per category, via MongoDB aggregation.

    Fast on large banks: the counting happens in MongoDB, not Python.
    Returns {"<company>": {"<category>": count, ...}, ...} with "" meaning
    the general (untagged) pool.
    """
    from app.db import control_db
    db = control_db()

    category_collection = {
        "reading": "reading_passages", "writing": "writing_prompts",
        "listening": "listening_passages", "speaking": "task_items",
        "grammar": "quiz_items", "vocabulary": "quiz_items",
    }
    out: dict[str, dict[str, int]] = {}
    for cat, coll in category_collection.items():
        pipeline = [
            {"$match": {"status": "published"}},
            {"$group": {"_id": {"$ifNull": ["$company", ""]},
                        "count": {"$sum": 1}}},
        ]
        for row in await db[coll].aggregate(pipeline).to_list(500):
            c = row["_id"] or ""
            out.setdefault(c, {})[cat] = out.get(c, {}).get(cat, 0) + row["count"]
    return out


# --------------------------------------------------------------------------
# Question creation endpoints
# --------------------------------------------------------------------------

@router.post("/questions/quiz")
async def create_quiz_item(body: dict) -> dict:
    item_id = await _create_quiz(body.get("category", "reading_comprehension"), body)
    await audit_log.record_system("platform.create_question", entity="quiz_item")
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
    from app.db import ensure_shared_models, control_db
    from app.set_engine import generate_question_number
    import uuid

    models = await ensure_shared_models()
    items = body.get("items", [])
    category = body.get("category", "quiz")
    company = body.get("company", "")
    db = control_db()

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
                # Validate MCQ options
                if not options or len(options) < 2:
                    options = ["Option A", "Option B", "Option C", "Option D"]
                if not isinstance(correct_index, int) or correct_index < 0 or correct_index >= len(options):
                    correct_index = 0
                item_id = str(uuid.uuid4())
                qn = await generate_question_number("quiz", db)
                cat = category if category in ("grammar", "vocabulary") else "grammar"
                existing = await models.QuizItem.find_one(
                    models.QuizItem.stem == stem,
                    models.QuizItem.category == cat,
                    models.QuizItem.company == company,
                )
                if existing:
                    errors.append({"index": i, "error": "Duplicate question (same stem/category/company)"})
                    continue
                qi = models.QuizItem(
                    id=item_id, question_number=qn,
                    category=cat,
                    stem=stem,
                    options=options,
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
                body_text = item.get("body", item.get("passage", ""))
                if not body_text or not body_text.strip():
                    errors.append({"index": i, "error": "Reading passage requires body text"})
                    continue
                passage_id = str(uuid.uuid4())
                qn = await generate_question_number("reading", db)
                existing = await models.ReadingPassage.find_one(
                    models.ReadingPassage.title == stem[:100],
                    models.ReadingPassage.company == company,
                )
                if existing:
                    errors.append({"index": i, "error": "Duplicate reading passage (same title/company)"})
                    continue
                passage = models.ReadingPassage(
                    id=passage_id, question_number=qn,
                    title=stem[:100],
                    kind=item.get("kind", "article"),
                    body=body_text,
                    company=company,
                    word_count=len(body_text.split()),
                    difficulty=difficulty,
                    status="published",
                )
                await passage.create()

                for q in item.get("questions", []):
                    qn_q = await generate_question_number("reading", db)
                    qi = models.QuizItem(
                        id=str(uuid.uuid4()), question_number=qn_q,
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
                transcript = item.get("transcript", "")
                if not transcript or not transcript.strip():
                    errors.append({"index": i, "error": "Listening passage requires transcript"})
                    continue
                passage_id = str(uuid.uuid4())
                qn = await generate_question_number("listening", db)
                existing = await models.ListeningPassage.find_one(
                    models.ListeningPassage.title == stem[:100],
                    models.ListeningPassage.company == company,
                )
                if existing:
                    errors.append({"index": i, "error": "Duplicate listening passage (same title/company)"})
                    continue
                passage = models.ListeningPassage(
                    id=passage_id, question_number=qn,
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
                    qn_q = await generate_question_number("listening", db)
                    qi = models.QuizItem(
                        id=str(uuid.uuid4()), question_number=qn_q,
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
                prompt_text = item.get("prompt", stem)
                if not prompt_text or not prompt_text.strip():
                    errors.append({"index": i, "error": "Writing prompt requires prompt text"})
                    continue
                prompt_id = str(uuid.uuid4())
                qn = await generate_question_number("writing", db)
                existing = await models.WritingPrompt.find_one(
                    models.WritingPrompt.title == stem[:100],
                    models.WritingPrompt.company == company,
                )
                if existing:
                    errors.append({"index": i, "error": "Duplicate writing prompt (same title/company)"})
                    continue
                prompt = models.WritingPrompt(
                    id=prompt_id, question_number=qn,
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
                if not stem or not stem.strip():
                    errors.append({"index": i, "error": "Speaking task requires prompt text"})
                    continue
                item_id = str(uuid.uuid4())
                qn = await generate_question_number("speaking", db)
                existing = await models.TaskItem.find_one(
                    models.TaskItem.prompt_text == stem,
                    models.TaskItem.company == company,
                )
                if existing:
                    errors.append({"index": i, "error": "Duplicate speaking item (same prompt/company)"})
                    continue
                ti = models.TaskItem(
                    id=item_id, question_number=qn,
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
    return {"id": item_id, "ok": True}


@router.post("/questions/reading")
async def create_reading_passage(body: dict) -> dict:
    import uuid
    passage_id = str(uuid.uuid4())
    await _create_reading(passage_id, body)
    await audit_log.record_system("platform.create_question", entity="reading_passage")
    return {"passage_id": passage_id, "ok": True}


@router.post("/questions/writing")
async def create_writing_prompt(body: dict) -> dict:
    prompt_id = await _create_writing(body)
    await audit_log.record_system("platform.create_question", entity="writing_prompt")
    return {"prompt_id": prompt_id, "ok": True}


@router.post("/questions/listening")
async def create_listening_passage(body: dict) -> dict:
    passage_id = await _create_listening(body)
    await audit_log.record_system("platform.create_question", entity="listening_passage")
    return {"passage_id": passage_id, "ok": True}


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

# ---------------------------------------------------------------------------
# Company Papers — one paper = 10 reading + 10 writing + 10 listening + 10
# speaking sets, all from that company's own bank. Built by hand, like sets.
# ---------------------------------------------------------------------------


@router.get("/company-papers")
async def list_company_papers(company: str = "") -> list[dict]:
    """All company papers with their section sets resolved."""
    from app.models.tenant import CompanyPaper
    query = {"status": {"$in": ["active", "draft"]}}
    if company:
        query["company"] = company
    papers = await CompanyPaper.find(query).to_list(500)
    out = []
    for p in papers:
        out.append({
            "id": str(p.id), "name": p.name, "company": p.company,
            "description": p.description, "status": p.status,
            "is_used": p.is_used, "usage_count": p.usage_count,
            "sets": {
                "reading": p.reading_set_id, "writing": p.writing_set_id,
                "listening": p.listening_set_id, "speaking": p.speaking_set_id,
                "quiz": p.quiz_set_id,
            },
        })
    return out


@router.post("/company-papers", status_code=status.HTTP_201_CREATED)
async def create_company_paper(body: dict) -> dict:
    """Create one empty company paper draft for a company.

    The four section slots start empty; the admin fills each by picking one of
    that company's own active sets per skill. The paper cannot go live until
    reading, writing, listening and speaking are all filled (40 = 4×10).
    """
    from app.models.tenant import CompanyPaper
    company = (body.get("company") or "").strip()
    name = (body.get("name") or "").strip()
    if not company:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "company is required")
    if not name:
        name = f"{company} Communication Round"
    existing = await CompanyPaper.find_one(
        CompanyPaper.name == name, CompanyPaper.status != "archived")
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"A paper named '{name}' already exists")
    paper = CompanyPaper(name=name, company=company,
                         description=(body.get("description") or "").strip())
    await paper.create()
    await audit_log.record_system(
        "platform.company_paper_created", entity="CompanyPaper",
        entity_id=str(paper.id), after={"name": name, "company": company})
    return {"id": str(paper.id), "name": name, "company": company,
            "status": paper.status}


@router.get("/company-papers/available-sets")
async def paper_available_sets(company: str = "", module: str = "") -> list[dict]:
    """Active sets of one module+company that a paper slot can take.

    A slot may take any active set of that company for that skill, including
    sets already used by another paper — a paper references a set; several
    papers can share one set without any question leaking across companies.
    """
    from app.models.platform import QuestionSet
    if not company or module not in ("reading", "writing", "listening", "speaking", "quiz"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "company and valid module required")
    sets = await QuestionSet.find(
        QuestionSet.module == module,
        QuestionSet.company == company,
        QuestionSet.status == "active",
    ).to_list(500)
    return [{"id": str(s.id), "set_number": s.set_number,
             "question_count": s.question_count} for s in sets]


@router.patch("/company-papers/{paper_id}")
async def update_company_paper(paper_id: str, body: dict) -> dict:
    """Fill section slots, rename, or change status (with the 4-section gate)."""
    from app.models.tenant import CompanyPaper
    from app.models.platform import QuestionSet
    paper = await CompanyPaper.get(paper_id)
    if paper is None or paper.status == "archived":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper not found")

    if "name" in body:
        paper.name = (body["name"] or "").strip()
    if "description" in body:
        paper.description = (body["description"] or "").strip()

    slot_map = {"reading": "reading_set_id", "writing": "writing_set_id",
                "listening": "listening_set_id", "speaking": "speaking_set_id",
                "quiz": "quiz_set_id"}
    for key, field in slot_map.items():
        if key in body:
            set_id = (body[key] or "").strip()
            if set_id:
                s = await QuestionSet.get(set_id)
                if s is None or s.status != "active" or s.module != key:
                    raise HTTPException(status.HTTP_409_CONFLICT,
                                        f"Set for '{key}' must be an active {key} set")
                if (s.company or "") != paper.company:
                    raise HTTPException(status.HTTP_409_CONFLICT,
                                        f"Set for '{key}' belongs to "
                                        f"'{s.company or 'general'}', not {paper.company}")
                setattr(paper, field, set_id)
            else:
                setattr(paper, field, "")

    if "status" in body:
        wanted = body["status"]
        if wanted == "active":
            missing = [k for k in ("reading", "writing", "listening", "speaking")
                       if not getattr(paper, slot_map[k])]
            if missing:
                raise HTTPException(status.HTTP_409_CONFLICT,
                                    "Cannot activate: still missing " + ", ".join(missing))
        paper.status = wanted

    paper.updated_at = datetime.now(timezone.utc)
    await paper.save()
    await audit_log.record_system(
        "platform.company_paper_updated", entity="CompanyPaper",
        entity_id=paper_id, after={"status": paper.status})
    return {"ok": True, "status": paper.status}


@router.delete("/company-papers/{paper_id}")
async def delete_company_paper(paper_id: str) -> dict:
    """Archive a paper (papers are history once used — never hard-deleted)."""
    from app.models.tenant import CompanyPaper
    paper = await CompanyPaper.get(paper_id)
    if paper is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper not found")
    paper.status = "archived"
    paper.updated_at = datetime.now(timezone.utc)
    await paper.save()
    await audit_log.record_system(
        "platform.company_paper_archived", entity="CompanyPaper", entity_id=paper_id)
    return {"ok": True}


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
    from app.models.platform import QuestionSet
    model_map = {
        "quiz": QuizItem, "task": TaskItem, "writing": WritingPrompt,
        "listening": ListeningPassage, "reading": ReadingPassage,
    }
    model = model_map.get(collection)
    if not model:
        raise HTTPException(400, f"Unknown collection: {collection}")
    doc = await model.get(item_id)
    if not doc:
        raise HTTPException(404, f"{collection} item not found")
    # Check if question is used in any active question sets
    active_sets = await QuestionSet.find(
        QuestionSet.status.in_(["active", "draft"]),
        QuestionSet.question_ids == item_id,
    ).to_list()
    if active_sets:
        set_ids = [s.id for s in active_sets]
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Cannot delete: question is used in {len(active_sets)} active/draft set(s) ({', '.join(set_ids[:3])}). Remove it from sets first.")
    await doc.delete()
    await audit_log.record_system("platform.delete_question", entity=f"{collection}:{item_id}")
    return {"ok": True}


@router.post("/questions/audio")
async def upload_audio(file: "UploadFile") -> dict:
    """Upload an audio file (WAV, M4A, MP3) for listening passages or prompts."""
    import uuid
    ext = os.path.splitext(file.filename or "audio.wav")[1] or ".wav"
    ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}
    if ext.lower() not in ALLOWED_AUDIO_EXTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Audio must be one of: {', '.join(ALLOWED_AUDIO_EXTS)}")
    content = await file.read()
    # Reject non-audio files (SVG, HTML, executables)
    if content[:5].lower() in (b"<svg ", b"<html", b"<!DOC"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only audio files are allowed")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio must be under 25 MB")
    key = f"audio/{uuid.uuid4().hex}{ext}"
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "audio")
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, key.replace("audio/", ""))
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
    """List all custom exam tests with set counts per module."""
    from app.models.platform import ExamTest, QuestionSet
    tests = await ExamTest.find(ExamTest.is_active == True).to_list()
    print(f"DEBUG list_exam_tests: found {len(tests)} active tests")
    for t in tests:
        if not t.company:
            print(f"  {t.id} - {t.name} - is_active: {t.is_active}")
    tests.sort(key=lambda t: t.created_at or t.updated_at or "", reverse=True)
    # Batch-fetch set counts per company
    all_sets = await QuestionSet.find({"status": "active"}).to_list(5000)
    company_mod_counts: dict[str, dict[str, int]] = {}
    for s in all_sets:
        key = s.company or ""
        if key not in company_mod_counts:
            company_mod_counts[key] = {}
        mod = s.module
        company_mod_counts[key][mod] = company_mod_counts[key].get(mod, 0) + 1
    return [
        {
            "id": t.id, "name": t.name, "description": t.description,
            "slug": t.slug, "duration_minutes": t.duration_minutes,
            "reading_questions": t.reading_questions,
            "listening_questions": t.listening_questions,
            "writing_questions": t.writing_questions,
            "speaking_questions": t.speaking_questions,
            "quiz_questions": t.quiz_questions,
            "reading_seconds": t.reading_seconds,
            "listening_seconds": t.listening_seconds,
            "writing_seconds": t.writing_seconds,
            "speaking_seconds": t.speaking_seconds,
            "quiz_seconds": t.quiz_seconds,
            "allow_pause": t.allow_pause, "show_timer": t.show_timer,
            "one_shot_audio": t.one_shot_audio,
            "is_active": t.is_active, "is_baseline": t.is_baseline,
            "company": t.company, "question_ids": t.question_ids,
            "sets_by_module": company_mod_counts.get(t.company or "", {}),
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

# The sets API is the /sets family below. A second /question-sets family used to
# live here (list + stats) with a third set of writes in platform_writes; all
# three wrote the same QuestionSet rows, so the same set could be created,
# listed and archived through two different vocabularies. Consolidated onto
# /sets, which is what the console actually calls.


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
async def list_sets(module: str = "", status: str = "", company: str | None = None,
                    include_archived: bool = False) -> list[dict]:
    """List question sets with optional filters.

    Archived sets are excluded unless asked for. The bank accumulates a lot of
    them (every rebuild supersedes the previous generation), and the Question
    Bank shows this list as one button per set, so carrying the dead ones would
    bury the sets an admin can actually assign.
    """
    from app.models.platform import QuestionSet, ExamTest
    print(f"DEBUG list_sets: company={repr(company)}")
    query = {}
    if module:
        query["module"] = module
    if status:
        query["status"] = status
    elif not include_archived:
        query["status"] = {"$in": ["active", "draft"]}
    # Handle company filter: "general" or empty/None means general (no company)
    if company and company not in ("general", ""):
        query["company"] = company
    elif company in ("general", "") or company is None:
        # If explicitly "general", empty string, or None -> filter to general
        # Only apply filter if it was explicitly provided
        # We need to check if the parameter was actually passed
        # For now, treat None as "all companies" and "general"/"" as general
        if company in ("general", ""):
            query["company"] = "general"
            print(f"DEBUG: Setting company=general")
    print(f"DEBUG: Final query: {query}")
    raw = await QuestionSet.find(query).to_list(5000)
    # Company first, then number: with one numbering sequence per company, a
    # flat sort by set_number would interleave READ-SET-001 of every company
    # into a run of repeated labels.
    sets = sorted(raw, key=lambda s: (s.company or "", s.set_number or ""))

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


from app.set_engine import (create_empty_set, set_candidates,
                            add_question_to_set, remove_question_from_set,
                            activate_set)


@router.post("/sets", status_code=status.HTTP_201_CREATED)
async def create_set(body: dict) -> dict:
    """Create one empty draft set for a module (+ optional company).

    Sets are built by hand: the shell is created here, then the admin adds the
    ten questions one at a time through /sets/{id}/questions. Nothing is
    auto-filled from the bank.
    """
    module = (body.get("module") or "").strip()
    company = (body.get("company") or "").strip()
    result = await create_empty_set(module, company)
    if result.get("created") == 0:
        await audit_log.record_system(
            "platform.set_create_failed", entity=f"set:{module}",
            after={"company": company, "reason": result.get("error", "")})
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("error") or "Could not create a set")
    await audit_log.record_system(
        "platform.set_created", entity="QuestionSet",
        entity_id=result.get("set_id", ""),
        after={"set_number": result.get("set_number"), "module": module,
               "company": company})
    return result


@router.get("/sets/{set_id}/candidates")
async def set_candidate_questions(set_id: str, search: str = "",
                                  limit: int = 30) -> dict:
    """Questions the admin may still add to this draft set.

    Scope follows the set (same module collection, same company, published) and
    excludes questions already sitting in another live set, so the picker can
    never offer something the engine would refuse.
    """
    result = await set_candidates(set_id, search=search, limit=limit)
    if result.get("error"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, result["error"])
    return result


@router.get("/sets/{set_id}/questions")
async def get_set_questions_by_id(set_id: str) -> list:
    """Return resolved questions for a specific set (by set ID)."""
    from app.db import control_db
    from bson import ObjectId
    db = control_db()
    s_doc = None
    try:
        s_doc = await db.question_sets.find_one({"_id": ObjectId(set_id)})
    except Exception:
        pass
    if not s_doc:
        s_doc = await db.question_sets.find_one({"_id": set_id})
    if not s_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set not found")
    MODULE_COLL = {
        "reading": "reading_passages",
        "listening": "listening_passages",
        "writing": "writing_prompts",
        "speaking": "task_items",
        "quiz": "quiz_items",
    }
    COMP_COLL = {"reading": "quiz_items", "listening": "quiz_items"}
    mod = s_doc.get("module", "")
    qids = s_doc.get("question_ids", []) or []
    coll_name = MODULE_COLL.get(mod)
    comp_name = COMP_COLL.get(mod)
    questions = []
    for qid in qids[:20]:
        doc = None
        if coll_name:
            doc = await db[coll_name].find_one({"_id": str(qid)})
        if not doc and comp_name:
            doc = await db[comp_name].find_one({"_id": str(qid)})
        if doc:
            questions.append({
                "id": str(doc["_id"]),
                "title": doc.get("title") or doc.get("stem") or doc.get("prompt_text") or doc.get("prompt") or "",
                "category": doc.get("category") or doc.get("task_type") or mod,
                "options": doc.get("options", []),
                "correct_index": doc.get("correct_index", 0),
                "explanation": doc.get("explanation", ""),
                "audio_key": doc.get("audio_key") or doc.get("prompt_audio_key") or "",
                "body": doc.get("body") or doc.get("transcript") or "",
            })
    return questions


@router.post("/sets/{set_id}/questions")
async def set_add_question(set_id: str, body: dict) -> dict:
    """Add one question to a draft set (manual set building)."""
    question_id = (body.get("question_id") or "").strip()
    if not question_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "question_id is required")
    result = await add_question_to_set(set_id, question_id)
    if not result.get("ok"):
        raise HTTPException(status.HTTP_409_CONFLICT, result.get("error") or "Could not add the question")
    await audit_log.record_system(
        "platform.set_question_added", entity="QuestionSet", entity_id=set_id,
        after={"question_id": question_id, "count": result.get("question_count")})
    return result


@router.delete("/sets/{set_id}/questions/{question_id}")
async def set_remove_question(set_id: str, question_id: str) -> dict:
    """Remove one question from a draft set."""
    result = await remove_question_from_set(set_id, question_id)
    if not result.get("ok"):
        raise HTTPException(status.HTTP_409_CONFLICT, result.get("error") or "Could not remove the question")
    await audit_log.record_system(
        "platform.set_question_removed", entity="QuestionSet", entity_id=set_id,
        after={"question_id": question_id, "count": result.get("question_count")})
    return result


@router.post("/sets/{set_id}/activate")
async def set_activate(set_id: str) -> dict:
    """Activate a draft set — refused until it holds exactly 10 questions."""
    result = await activate_set(set_id)
    if not result.get("ok"):
        raise HTTPException(status.HTTP_409_CONFLICT, result.get("error") or "Could not activate the set")
    await audit_log.record_system(
        "platform.set_activated", entity="QuestionSet", entity_id=set_id,
        after={"set_number": result.get("set_number")})
    return result


@router.post("/sets/{set_id}/deactivate")
async def set_deactivate(set_id: str) -> dict:
    """Revert an active set back to draft."""
    from app.models.platform import QuestionSet
    s = await QuestionSet.get(set_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set not found")
    if s.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Set is not active")
    s.status = "draft"
    s.updated_at = datetime.now(timezone.utc)
    await s.save()
    await audit_log.record_system(
        "platform.set_deactivated", entity="QuestionSet", entity_id=set_id)
    return {"ok": True, "set_number": s.set_number, "status": s.status}


@router.delete("/sets/{set_id}")
async def delete_set(set_id: str) -> dict:
    """Delete a set (only drafts can be deleted)."""
    from app.models.platform import QuestionSet
    s = await QuestionSet.get(set_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set not found")
    if s.status == "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Cannot delete an active set. Deactivate it first.")
    await s.delete()
    await audit_log.record_system(
        "platform.set_deleted", entity="QuestionSet", entity_id=set_id)
    return {"ok": True}


# --------------------------------------------------------------------------
# Question CRUD (edit / delete individual questions)
# --------------------------------------------------------------------------

@router.patch("/questions/{category}/{question_id}")
async def update_question(category: str, question_id: str, body: dict) -> dict:
    """Update an individual question by category and ID."""
    from app.db import ensure_shared_models, control_db
    models = await ensure_shared_models()
    db = control_db()

    category_map = {
        "quiz": ("quiz_items", models.QuizItem),
        "reading": ("reading_passages", models.ReadingPassage),
        "listening": ("listening_passages", models.ListeningPassage),
        "writing": ("writing_prompts", models.WritingPrompt),
        "speaking": ("task_items", models.TaskItem),
    }

    if category not in category_map:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown category: {category}")

    coll_name, model_cls = category_map[category]
    doc = await db[coll_name].find_one({"_id": question_id})
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")

    # Apply updates
    updates = {}
    allowed_fields = {
        "quiz": ["stem", "options", "correct_index", "explanation", "difficulty", "category"],
        "reading": ["title", "body", "kind", "difficulty"],
        "listening": ["title", "transcript", "audio_key", "accent", "kind", "difficulty"],
        "writing": ["title", "prompt", "kind", "scenario", "min_words", "suggested_minutes", "difficulty"],
        "speaking": ["prompt_text", "reference_text", "task_type", "prompt_audio_key", "difficulty"],
    }

    for field in allowed_fields.get(category, []):
        if field in body:
            updates[field] = body[field]

    if not updates:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No valid fields to update")

    await db[coll_name].update_one({"_id": question_id}, {"$set": updates})
    await audit_log.record_system(
        f"platform.update_question_{category}", entity=coll_name, entity_id=question_id)
    return {"ok": True, "updated_fields": list(updates.keys())}


@router.delete("/questions/{category}/{question_id}")
async def delete_question(category: str, question_id: str) -> dict:
    """Delete an individual question by category and ID.

    Refuses to delete if the question is referenced by any active/draft set.
    """
    from app.db import ensure_shared_models, control_db
    from app.models.platform import QuestionSet
    models = await ensure_shared_models()
    db = control_db()

    category_map = {
        "quiz": "quiz_items",
        "reading": "reading_passages",
        "listening": "listening_passages",
        "writing": "writing_prompts",
        "speaking": "task_items",
    }

    if category not in category_map:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown category: {category}")

    coll_name = category_map[category]
    doc = await db[coll_name].find_one({"_id": question_id})
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")

    # Check if referenced by any active/draft sets
    active_sets = await QuestionSet.find(
        {"status": {"$in": ["active", "draft"]}, "question_ids": question_id}
    ).to_list(None)
    if active_sets:
        set_nums = [s.set_number for s in active_sets[:5]]
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot delete: question is in {len(active_sets)} set(s) "
            f"({', '.join(set_nums)}{'...' if len(active_sets) > 5 else ''}). "
            f"Remove it from sets first."
        )

    await db[coll_name].delete_one({"_id": question_id})
    await audit_log.record_system(
        f"platform.delete_question_{category}", entity=coll_name, entity_id=question_id)
    return {"ok": True}


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


@router.post("/sets/archive-empty")
async def archive_empty_sets() -> dict:
    """Archive all active sets where all question_numbers are empty strings."""
    from app.db import control_db
    db = control_db()
    # Find all active sets
    all_sets = await db.question_sets.find({"status": "active"}).to_list(10000)
    # Identify ghosts: every question_number is empty string
    ghost_ids = []
    for s in all_sets:
        nums = s.get("question_numbers") or []
        if all(n == "" for n in nums):
            ghost_ids.append(s["_id"])
    if ghost_ids:
        result = await db.question_sets.update_many(
            {"_id": {"$in": ghost_ids}},
            {"$set": {"status": "archived"}}
        )
        return {"archived": result.modified_count, "remaining": len(all_sets) - result.modified_count}
    return {"archived": 0, "remaining": len(all_sets)}


@router.post("/sets/rebuild-broken")
async def rebuild_broken_sets() -> dict:
    """Archive sets with missing questions and rebuild from actual question banks.

    One scheme everywhere: a reading/listening set holds QUIZ-ITEM ids (the
    questions, which cite their passage), writing holds prompt ids, speaking
    holds task-item ids. The bank for reading is quiz_items with category
    reading_comprehension — never the passages themselves, whose per-passage
    question counts would break the "one set = ten questions" promise.
    """
    from app.db import control_db
    from app.models.platform import QuestionSet, ExamTest
    import random
    db = control_db()

    MODULE_COLLECTIONS = {
        "reading": "quiz_items",
        "listening": "quiz_items",
        "writing": "writing_prompts",
        "speaking": "task_items",
        "quiz": "quiz_items",
    }
    MODULE_CATEGORY = {
        "reading": "reading_comprehension",
        "listening": "audio_comprehension",
        "quiz": {"$in": ["grammar", "vocabulary"]},
    }

    # 1. Find all active sets and check which have broken question_ids
    all_sets = await QuestionSet.find({"status": "active"}).to_list(10000)
    broken_ids = []
    for s in all_sets:
        coll_name = MODULE_COLLECTIONS.get(s.module)
        if not coll_name or not s.question_ids:
            if not s.question_ids:
                broken_ids.append(s.id)
            continue
        # Check if question_ids exist in the collection
        found = await db[coll_name].count_documents(
            {"_id": {"$in": s.question_ids}}
        )
        if found < len(s.question_ids):
            broken_ids.append(s.id)

    # 2. Archive broken sets
    if broken_ids:
        await QuestionSet.find({"_id": {"$in": broken_ids}}).update(
            {"$set": {"status": "archived"}}
        )

    # 3. Rebuild sets per module: group actual questions into sets of 10
    exam_tests = await ExamTest.find({}).to_list(100)
    companies_with_tests = set()
    for t in exam_tests:
        if t.company:
            companies_with_tests.add(t.company)

    created = {}
    for module, coll_name in MODULE_COLLECTIONS.items():
        # Get all questions (both general and company-specific)
        # Reading and listening draw from quiz_items, so the category clause
        # is what keeps a reading set reading (and a listening set listening).
        base_query: dict = {"status": "published"}
        cat = MODULE_CATEGORY.get(module)
        if isinstance(cat, str):
            base_query["category"] = cat
        elif isinstance(cat, dict):
            # {"$in": [...]} → {"category": {"$in": [...]}}
            base_query["category"] = cat
        all_questions = await db[coll_name].find(base_query).to_list(20000)
        if not all_questions:
            all_questions = await db[coll_name].find(
                {**base_query, "status": {"$in": ["published", "draft"]}}
            ).to_list(20000)

        # Group by company, normalising the general tags to ""
        by_company: dict[str, list] = {}
        for q in all_questions:
            co = (q.get("company") or "").strip()
            if co.lower() in ("general", "all"):
                co = ""
            by_company.setdefault(co, []).append(q)

        for company, questions in by_company.items():
            if len(questions) < 10:
                continue  # Need at least 10 for one set

            # Check how many active sets already exist for this module+company
            existing = await QuestionSet.find({
                "module": module, "company": company, "status": "active"
            }).to_list(100)
            existing_count = len(existing)

            # Calculate how many sets we need
            needed = len(questions) // 10
            if existing_count >= needed:
                continue  # Already have enough sets

            # Create new sets from remaining questions, using the shared
            # _next_set_number for consistent, gap-free numbering.
            from app.set_engine import _next_set_number, MODULE_PREFIXES
            prefix = MODULE_PREFIXES.get(module, module.upper()[:4])
            all_module_sets = await QuestionSet.find(
                QuestionSet.module == module
            ).to_list(None)

            questions_to_use = questions[existing_count * 10:]
            for i in range(0, len(questions_to_use), 10):
                batch = questions_to_use[i:i+10]
                if len(batch) < 10:
                    break  # Skip incomplete sets
                set_number = _next_set_number(prefix, company, all_module_sets)
                # Add the new set to all_module_sets so the next call picks the
                # next number instead of reusing the same one.
                class _Placeholder:
                    pass
                ph = _Placeholder()
                ph.set_number = set_number
                all_module_sets.append(ph)
                q_ids = [str(q["_id"]) for q in batch]
                q_nums = [q.get("question_number", "") or str(q.get("_id", "")) for q in batch]
                new_set = QuestionSet(
                    set_number=set_number,
                    module=module,
                    company=company,
                    question_ids=q_ids,
                    question_numbers=[str(n) for n in q_nums],
                    question_count=10,
                    status="active",
                )
                await new_set.insert()
                created.setdefault(module, 0)

            created[module] = created.get(module, 0) + (len(questions_to_use) // 10)

    return {
        "archived_broken": len(broken_ids),
        "created": created,
    }


# Literal paths are declared before the parameterised one below: FastAPI matches
# in registration order, so "/sets/{set_id}" registered first would swallow
# "/sets/summary" and answer "Set not found" for both summary routes.
@router.get("/sets/{set_id}")
async def get_set(set_id: str) -> dict:
    """One set and the questions inside it, with full content and answer key.

    The Question Bank expands a category to its sets, and a set to the ten
    questions it holds — each with its stem, options, the correct answer and
    the explanation, plus the parent passage (or transcript/audio for
    listening) so a superadmin can review the whole question as the student
    will see it. Read-only: nothing here scores.
    """
    from app.db import control_db
    from app.models.platform import QuestionSet
    from app.set_engine import MODULE_COLLECTIONS, MODULE_CATEGORY

    s = await QuestionSet.get(set_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Set not found")

    coll_name = MODULE_COLLECTIONS.get(s.module)
    if coll_name is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Set has unknown module '{s.module}'")

    db = control_db()
    docs = await db[coll_name].find(
        {"_id": {"$in": [str(q) for q in s.question_ids]}}
    ).to_list(None)
    by_id = {str(d["_id"]): d for d in docs}

    # Reading and listening questions hang off parent passages — fetch them
    # once so every question can carry its passage inline.
    pdocs_by_id: dict[str, dict] = {}
    if s.module in ("reading", "listening"):
        pids = list({str(d.get("passage_id")) for d in docs if d.get("passage_id")})
        pcoll = ("reading_passages" if s.module == "reading"
                 else "listening_passages")
        for p in await db[pcoll].find({"_id": {"$in": pids}}).to_list(200):
            pdocs_by_id[str(p["_id"])] = p

    questions = []
    missing = 0
    for qid in s.question_ids:
        d = by_id.get(str(qid))
        if d is None:
            # A set can outlive a question that was archived or deleted. The
            # slot is reported rather than skipped, so the count on screen stays
            # honest instead of quietly showing nine questions.
            missing += 1
            questions.append({"id": str(qid), "label": "", "missing": True})
            continue
        questions.append({
            "id": str(d["_id"]),
            "question_number": d.get("question_number", ""),
            "label": (d.get("stem") or d.get("title")
                      or d.get("prompt_text") or d.get("prompt") or ""),
            "kind": (d.get("category") or d.get("kind")
                     or d.get("task_type") or ""),
            "company": d.get("company", ""),
            "difficulty": float(d.get("difficulty") or 0),
            "status": d.get("status", ""),
            "stem": d.get("stem", ""),
            "options": list(d.get("options") or []),
            "correct_index": d.get("correct_index"),
            "explanation": d.get("explanation", ""),
            "body": (d.get("body") or d.get("transcript")
                     or d.get("scenario") or d.get("reference_text") or ""),
            # Where the audio lives, for the rows the UI can play (listening,
            # speaking): a pre-rendered key, not a URL, same as the bank list.
            "audio_key": d.get("audio_key") or d.get("prompt_audio_key") or "",
            # The parent passage (reading/listening): full text, title and the
            # audio key, so the superadmin sees the question in its context.
            "passage": ({
                "id": pid,
                "title": p.get("title", ""),
                "kind": p.get("kind", ""),
                "body": p.get("body", ""),
                "transcript": p.get("transcript", ""),
                "audio_key": p.get("audio_key", ""),
            } if (pid := str(d.get("passage_id") or "")) and (p := pdocs_by_id.get(pid)) else None),
        })

    return {
        "id": str(s.id),
        "set_number": s.set_number,
        "module": s.module,
        "company": s.company,
        "status": s.status,
        "question_count": s.question_count,
        "usage_count": s.usage_count,
        "is_used": s.is_used,
        "last_used_at": s.last_used_at.isoformat() if s.last_used_at else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "missing_count": missing,
        "questions": questions,
    }


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
            "quiz": getattr(test, 'quiz_questions', 0),
        }
    else:
        config = {"reading": 10, "writing": 10, "listening": 10, "speaking": 0, "quiz": 0}

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
    from app.set_engine import generate_question_number
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
    section_module_map = {
        "reading": "reading", "reading_comprehension": "reading",
        "listening": "listening", "audio_comprehension": "listening",
        "writing": "writing", "essay": "writing", "email": "writing",
        "speaking": "speaking", "grammar": "quiz", "vocabulary": "quiz",
    }

    for section in sections:
        section_name = section.get("name", "reading").lower().strip()
        module = section_module_map.get(section_name, "reading")
        questions = section.get("questions", [])
        for q in questions:
            diff_str = q.get("difficulty", "medium")
            difficulty_val = {"easy": 0.3, "medium": 0.5, "hard": 0.8, "medium_hard": 0.65}.get(diff_str, 0.5)
            correct_map = {"A": 0, "B": 1, "C": 2, "D": 3}
            correct_index = correct_map.get(q.get("correct_answer", "A"), 0)
            stem = q.get("question", "")
            if not stem:
                continue
            existing = await QuizItem.find_one(
                QuizItem.stem == stem,
                QuizItem.company == company_name,
            )
            if existing:
                continue
            qn = await generate_question_number(module, db)
            qi = QuizItem(
                id=str(uuid.uuid4()), question_number=qn, category="reading_comprehension",
                stem=stem, options=q.get("options", []),
                correct_index=correct_index, explanation=q.get("explanation", ""),
                company=company_name, difficulty=difficulty_val, seconds_allowed=30,
                status="published",
            )
            await qi.create()
            total += 1

    await audit_log.record_system("platform.bulk_import_questions", entity="quiz_item",
                                   after={"company": company_name, "count": total})
    return {"ok": True, "imported": total, "company": company_name}
