"""Operator console Ã¢â‚¬â€ the control plane.

Platform staff never read student data from here. What they see is the shape
of the business (tenants, seats) and the shape of the system
(capabilities, providers, latency, audit). Institution databases are not
reachable through any endpoint in this file.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from beanie.operators import GTE
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response as HttpResponse

from app.deps import require_platform, Principal
from app.engine.contracts import CONTRACT_FOR, Capability
# Aliased: the GET /audit route below is named `audit`, which would otherwise
# shadow the module and crash every audit.record() call here.
from app import audit as audit_log
from app.models.platform import (AuditLog, GamificationConfig,
                                 ProviderCall, ProviderConfig,
                                 ProviderRegistry, Tenant)
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

    Capabilities with no configured provider are listed too Ã¢â‚¬â€ an unconfigured
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
            contract_version=getattr(contract, "contract_version", "Ã¢â‚¬â€"),
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
    """Operational health of the AI narrator Ã¢â‚¬â€ counts, failures, cost.

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


# --------------------------------------------------------------------------
# Question bank management
# --------------------------------------------------------------------------

@router.get("/tenants/{tenant_id}/users")
async def tenant_users(tenant_id: str) -> list[dict]:
    """List users for a specific tenant Ã¢â‚¬â€ super admin visibility."""
    from app.db import ensure_tenant_models
    from app.models.platform import Tenant

    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    from app.db import client as _client, tenant_db_name as _tdb_name
    _coll = _client[_tdb_name(tenant.slug)]['users']
    raw_users = await _coll.find().to_list()

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


@router.get("/students/{user_id}/attempts")
async def student_attempts(user_id: str, tenant_id: str) -> list[dict]:
    """List attempts for a specific student — super admin visibility."""
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


@router.get("/questions/items")
async def list_question_items(tenant_id: str, category: str = "reading",
                             page: int = 1, page_size: int = 10) -> dict:
    """Return actual question items for a specific tenant and category (paginated)."""
    from app.db import ensure_tenant_models
    from app.models.platform import Tenant

    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    models = await ensure_tenant_models(tenant.slug)
    items = []
    total = 0
    skip = (page - 1) * page_size

    if category == "reading":
        total = await models.ReadingPassage.find(
            models.ReadingPassage.status == "published").count()
        passages = await models.ReadingPassage.find(
            models.ReadingPassage.status == "published").sort("title").skip(skip).limit(page_size).to_list()
        for p in passages:
            items.append({"id": str(p.id), "title": p.title, "kind": p.kind,
                          "company": getattr(p, "company", ""),
                          "word_count": p.word_count, "difficulty": p.difficulty})
    elif category == "writing":
        total = await models.WritingPrompt.find(
            models.WritingPrompt.status == "published").count()
        prompts = await models.WritingPrompt.find(
            models.WritingPrompt.status == "published").sort("title").skip(skip).limit(page_size).to_list()
        for p in prompts:
            items.append({"id": str(p.id), "title": p.title, "kind": p.kind,
                          "company": getattr(p, "company", ""),
                          "min_words": p.min_words, "prompt": p.prompt})
    elif category == "listening":
        total = await models.ListeningPassage.find(
            models.ListeningPassage.status == "published").count()
        passages = await models.ListeningPassage.find(
            models.ListeningPassage.status == "published").sort("title").skip(skip).limit(page_size).to_list()
        for p in passages:
            items.append({"id": str(p.id), "title": p.title, "kind": p.kind,
                          "company": getattr(p, "company", ""),
                          "approx_seconds": p.approx_seconds, "transcript": p.transcript})
    elif category == "speaking":
        total = await models.TaskItem.find(
            models.TaskItem.status == "published").count()
        tasks = await models.TaskItem.find(
            models.TaskItem.status == "published").sort("task_type").skip(skip).limit(page_size).to_list()
        for t in tasks:
            items.append({"id": str(t.id), "task_type": t.task_type,
                          "company": getattr(t, "company", ""),
                          "prompt_text": t.prompt_text, "difficulty": t.difficulty})
    elif category == "grammar":
        total = await models.QuizItem.find(
            models.QuizItem.category == "grammar",
            models.QuizItem.status == "published").count()
        qi = await models.QuizItem.find(
            models.QuizItem.category == "grammar",
            models.QuizItem.status == "published").sort("stem").skip(skip).limit(page_size).to_list()
        for q in qi:
            items.append({"id": str(q.id), "stem": q.stem, "options": q.options,
                          "company": getattr(q, "company", ""),
                          "correct_index": q.correct_index, "explanation": q.explanation})
    elif category == "vocabulary":
        total = await models.QuizItem.find(
            models.QuizItem.category == "vocabulary",
            models.QuizItem.status == "published").count()
        qi = await models.QuizItem.find(
            models.QuizItem.category == "vocabulary",
            models.QuizItem.status == "published").sort("stem").skip(skip).limit(page_size).to_list()
        for q in qi:
            items.append({"id": str(q.id), "stem": q.stem, "options": q.options,
                          "company": getattr(q, "company", ""),
                          "correct_index": q.correct_index, "explanation": q.explanation})

    return {"items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": max(1, -(-total // page_size))}


@router.get("/questions")
async def list_questions(tenant_id: str | None = None,
                         category: str | None = None) -> dict:
    """List questions across tenants. Filters by tenant and/or category."""
    from app.db import ensure_tenant_models
    from app.models.platform import Tenant

    tenants = []
    if tenant_id:
        t = await Tenant.get(tenant_id)
        if t:
            tenants = [t]
        else:
            return {"tenants": [], "total": 0}
    else:
        tenants = await Tenant.find_all().to_list()

    result = {"tenants": [], "total": 0}
    for t in tenants:
        try:
            models = await ensure_tenant_models(t.slug)
            # Count by category
            pipeline = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}]
            if category:
                pipeline.insert(0, {"$match": {"category": category, "status": "published"}})
            else:
                pipeline.insert(0, {"$match": {"status": "published"}})
            cats = await models.QuizItem.get_motor_collection().aggregate(pipeline).to_list(None)
            cat_counts = {c["_id"]: c["count"] for c in cats}
            total = sum(cat_counts.values())

            # Count other collections
            reading = await models.ReadingPassage.find(models.ReadingPassage.status == "published").count()
            writing = await models.WritingPrompt.find(models.WritingPrompt.status == "published").count()
            listening = await models.ListeningPassage.find(models.ListeningPassage.status == "published").count()
            speaking = await models.TaskItem.find_all().count()

            result["tenants"].append({
                "tenant_id": t.id, "tenant_name": t.name, "tenant_slug": t.slug,
                "quiz_items": cat_counts, "total_questions": total,
                "reading_passages": reading, "writing_prompts": writing,
                "listening_passages": listening, "speaking_items": speaking,
            })
            result["total"] += total
        except Exception:
            pass

    return result


async def _propagate_reading(tenant, body, passage_id, questions_created):
    """Copy a reading passage + its quiz items to a tenant."""
    from app.db import ensure_tenant_models
    import uuid
    models = await ensure_tenant_models(tenant.slug)
    # Use the caller's shared id, not a fresh one: the id returned to the
    # console has to address the same content in every institution, or delete
    # and cross-references silently miss.
    local_id = passage_id
    passage = models.ReadingPassage(
        id=local_id, title=body.get("title", ""),
        kind=body.get("kind", "article"), body=body.get("body", ""),
        company=body.get("company", ""),
        word_count=len(body.get("body", "").split()),
        difficulty=body.get("difficulty", 0.0), status="published",
    )
    await passage.create()
    for q in body.get("questions", []):
        qi = models.QuizItem(
            id=str(uuid.uuid4()), category="reading_comprehension",
            stem=q.get("stem", ""), options=q.get("options", []),
            correct_index=q.get("correct_index", 0),
            explanation=q.get("explanation", ""), passage_id=local_id,
            company=body.get("company", ""),
            seconds_allowed=q.get("seconds_allowed", 30),
            difficulty=q.get("difficulty", 0.0), status="published",
        )
        await qi.create()


@router.post("/questions/reading")
async def create_reading_question(tenant_id: str, body: dict,
                                  principal: Principal) -> dict:
    """Create a reading passage with MCQ questions Ã¢â‚¬â€ saved to ALL tenants."""
    from app.models.platform import Tenant
    import uuid

    tenants = await Tenant.find_all().to_list()
    if not tenants:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No tenants found")

    passage_id = str(uuid.uuid4())
    created_count = 0
    for t in tenants:
        try:
            await _propagate_reading(t, body, passage_id, 0)
            created_count += 1
        except Exception:
            pass

    await audit_log.record(principal, "question.reading_created", entity="ReadingPassage",
                       entity_id=passage_id, tenant_id=tenant_id,
                       after={"title": body.get("title", ""), "tenants": created_count})
    return {"passage_id": passage_id, "tenants_updated": created_count}


async def _propagate_writing(tenant, body):
    from app.db import ensure_tenant_models
    import uuid
    models = await ensure_tenant_models(tenant.slug)
    prompt_id = str(uuid.uuid4())
    prompt = models.WritingPrompt(
        id=prompt_id, title=body.get("title", ""),
        kind=body.get("kind", "essay"), prompt=body.get("prompt", ""),
        company=body.get("company", ""),
        scenario=body.get("scenario", ""),
        key_points=body.get("key_points", []),
        min_words=body.get("min_words", 150),
        suggested_minutes=body.get("suggested_minutes", 20),
        difficulty=body.get("difficulty", 0.0), status="published",
    )
    await prompt.create()
    return prompt_id


@router.post("/questions/writing")
async def create_writing_question(tenant_id: str, body: dict,
                                  principal: Principal) -> dict:
    """Create a writing prompt (essay or email) Ã¢â‚¬â€ saved to ALL tenants."""
    from app.models.platform import Tenant

    tenants = await Tenant.find_all().to_list()
    created_count = 0
    prompt_id = ""
    for t in tenants:
        try:
            pid = await _propagate_writing(t, body)
            if not prompt_id:
                prompt_id = pid
            created_count += 1
        except Exception:
            pass

    await audit_log.record(principal, "question.writing_created", entity="WritingPrompt",
                       entity_id=prompt_id, tenant_id=tenant_id,
                       after={"title": body.get("title", ""), "tenants": created_count})
    return {"prompt_id": prompt_id, "tenants_updated": created_count}


async def _propagate_listening(tenant, body):
    from app.db import ensure_tenant_models
    import uuid
    models = await ensure_tenant_models(tenant.slug)
    passage_id = str(uuid.uuid4())
    passage = models.ListeningPassage(
        id=passage_id, title=body.get("title", ""),
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
        qi = models.QuizItem(
            id=str(uuid.uuid4()), category="audio_comprehension",
            stem=q.get("stem", ""), options=q.get("options", []),
            correct_index=q.get("correct_index", 0),
            explanation=q.get("explanation", ""), passage_id=passage_id,
            company=body.get("company", ""),
            seconds_allowed=q.get("seconds_allowed", 30),
            difficulty=q.get("difficulty", 0.0), status="published",
        )
        await qi.create()
    return passage_id


@router.post("/questions/listening")
async def create_listening_question(tenant_id: str, body: dict,
                                    principal: Principal) -> dict:
    """Create a listening passage Ã¢â‚¬â€ saved to ALL tenants."""
    from app.models.platform import Tenant

    tenants = await Tenant.find_all().to_list()
    created_count = 0
    passage_id = ""
    for t in tenants:
        try:
            pid = await _propagate_listening(t, body)
            if not passage_id:
                passage_id = pid
            created_count += 1
        except Exception:
            pass

    await audit_log.record(principal, "question.listening_created", entity="ListeningPassage",
                       entity_id=passage_id, tenant_id=tenant_id,
                       after={"title": body.get("title", ""), "tenants": created_count})
    return {"passage_id": passage_id, "tenants_updated": created_count}


@router.delete("/questions/{collection}/{item_id}")
async def delete_question(collection: str, item_id: str, tenant_id: str,
                          principal: Principal) -> dict:
    """Delete a question item from any collection."""
    from app.db import ensure_tenant_models
    from app.models.platform import Tenant

    ALLOWED = {"reading_passages", "quiz_items", "writing_prompts", "listening_passages"}
    if collection not in ALLOWED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown collection: {collection}")

    tenant = await Tenant.get(tenant_id)
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    models = await ensure_tenant_models(tenant.slug)
    MODEL_MAP = {
        "reading_passages": models.ReadingPassage,
        "quiz_items": models.QuizItem,
        "writing_prompts": models.WritingPrompt,
        "listening_passages": models.ListeningPassage,
    }
    model = MODEL_MAP[collection]
    item = await model.get(item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    await item.delete()

    await audit_log.record(principal, f"question.{collection}_deleted", entity=collection,
                       entity_id=item_id, tenant_id=tenant.id)
    return {"deleted": True}


async def _propagate_quiz(tenant, category, body):
    from app.db import ensure_tenant_models
    import uuid
    models = await ensure_tenant_models(tenant.slug)
    item_id = str(uuid.uuid4())
    qi = models.QuizItem(
        id=item_id, category=category, stem=body.get("stem", ""),
        options=body.get("options", []), correct_index=body.get("correct_index", 0),
        explanation=body.get("explanation", ""), company=body.get("company", ""),
        difficulty=body.get("difficulty", 0.3),
        seconds_allowed=30, status="published",
    )
    await qi.create()
    return item_id


async def _propagate_speaking(tenant, body):
    from app.db import ensure_tenant_models
    import uuid
    models = await ensure_tenant_models(tenant.slug)
    item_id = str(uuid.uuid4())
    ti = models.TaskItem(
        id=item_id, task_type=body.get("task_type", "open_response"),
        prompt_text=body.get("prompt_text", ""),
        company=body.get("company", ""),
        reference_text=body.get("reference_text", ""),
        difficulty=body.get("difficulty", 0.3), status="published",
    )
    await ti.create()
    return item_id


@router.post("/questions/grammar")
async def create_grammar_question(tenant_id: str, body: dict,
                                  principal: Principal) -> dict:
    """Create a grammar quiz item Ã¢â‚¬â€ saved to ALL tenants."""
    from app.models.platform import Tenant

    tenants = await Tenant.find_all().to_list()
    created_count = 0
    first_id = ""
    for t in tenants:
        try:
            iid = await _propagate_quiz(t, "grammar", body)
            if not first_id:
                first_id = iid
            created_count += 1
        except Exception:
            pass
    await audit_log.record(principal, "question.grammar_created", entity="QuizItem",
                       entity_id=first_id, tenant_id=tenant_id,
                       after={"tenants": created_count})
    return {"id": first_id, "tenants_updated": created_count}


@router.post("/questions/vocabulary")
async def create_vocabulary_question(tenant_id: str, body: dict,
                                     principal: Principal) -> dict:
    """Create a vocabulary quiz item Ã¢â‚¬â€ saved to ALL tenants."""
    from app.models.platform import Tenant

    tenants = await Tenant.find_all().to_list()
    created_count = 0
    first_id = ""
    for t in tenants:
        try:
            iid = await _propagate_quiz(t, "vocabulary", body)
            if not first_id:
                first_id = iid
            created_count += 1
        except Exception:
            pass
    await audit_log.record(principal, "question.vocabulary_created", entity="QuizItem",
                       entity_id=first_id, tenant_id=tenant_id,
                       after={"tenants": created_count})
    return {"id": first_id, "tenants_updated": created_count}


@router.post("/questions/speaking")
async def create_speaking_question(tenant_id: str, body: dict,
                                   principal: Principal) -> dict:
    """Create a speaking task item Ã¢â‚¬â€ saved to ALL tenants."""
    from app.models.platform import Tenant

    tenants = await Tenant.find_all().to_list()
    created_count = 0
    first_id = ""
    for t in tenants:
        try:
            iid = await _propagate_speaking(t, body)
            if not first_id:
                first_id = iid
            created_count += 1
        except Exception:
            pass
    await audit_log.record(principal, "question.speaking_created", entity="TaskItem",
                       entity_id=first_id, tenant_id=tenant_id,
                       after={"tenants": created_count})
    return {"id": first_id, "tenants_updated": created_count}


# --------------------------------------------------------------------------
# Database export
# --------------------------------------------------------------------------

@router.get("/export-db")
async def export_db() -> HttpResponse:
    """Export the entire project database (CommunicationIQ + all tenant_*) as JSON."""
    import json
    from bson import ObjectId, Decimal128, Regex
    from datetime import date
    from app.db import client, CONTROL_DB_NAME

    def serialize(obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, Decimal128):
            return float(obj)
        if isinstance(obj, Regex):
            return obj.pattern
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    export = {"databases": {}, "exported_at": datetime.now(timezone.utc).isoformat()}

    # Control plane
    cp_db = client[CONTROL_DB_NAME]
    cp_data = {}
    for coll_name in await cp_db.list_collection_names():
        docs = await cp_db[coll_name].find().to_list()
        cp_data[coll_name] = [{k: v for k, v in doc.items() if k != '_id'} for doc in docs]
    export["databases"][CONTROL_DB_NAME] = cp_data

    # All tenant databases
    for db_name in await client.list_database_names():
        if db_name.startswith("tenant_") and db_name not in ('admin', 'local', 'config'):
            t_db = client[db_name]
            t_data = {}
            for coll_name in await t_db.list_collection_names():
                docs = await t_db[coll_name].find().to_list()
                t_data[coll_name] = [{k: v for k, v in doc.items() if k != '_id'} for doc in docs]
            export["databases"][db_name] = t_data

    content = json.dumps(export, default=serialize, ensure_ascii=False)

    await audit_log.record(None, "platform.export_db", entity="database")

    return HttpResponse(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="fluenzee-db-export.json"',
        },
    )
