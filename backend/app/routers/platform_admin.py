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
    """List users for a specific tenant ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â super admin visibility."""
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
    from app.db import ensure_shared_models
    import uuid
    models = await ensure_shared_models()
    passage = models.ReadingPassage(
        id=passage_id, title=body.get("title", ""),
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
            explanation=q.get("explanation", ""), passage_id=passage_id,
            company=body.get("company", ""),
            seconds_allowed=q.get("seconds_allowed", 30),
            difficulty=q.get("difficulty", 0.0), status="published",
        )
        await qi.create()




async def _create_writing(body):
    from app.db import ensure_shared_models
    import uuid
    models = await ensure_shared_models()
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




async def _create_listening(body):
    from app.db import ensure_shared_models
    import uuid
    models = await ensure_shared_models()
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






async def _create_quiz(category, body):
    from app.db import ensure_shared_models
    import uuid
    models = await ensure_shared_models()
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


async def _create_speaking(body):
    from app.db import ensure_shared_models
    import uuid
    models = await ensure_shared_models()
    item_id = str(uuid.uuid4())
    ti = models.TaskItem(
        id=item_id, task_type=body.get("task_type", "open_response"),
        prompt_text=body.get("prompt_text", ""),
        company=body.get("company", ""),
        reference_text=body.get("reference_text", ""),
        prompt_audio_key=body.get("audio_key", ""),
        difficulty=body.get("difficulty", 0.3), status="published",
    )
    await ti.create()
    return item_id








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

    await audit_log.record_system("platform.export_db", entity="database")

    return HttpResponse(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="fluenzee-db-export.json"',
        },
    )


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
                             limit: int = 200) -> dict:
    """Question bank overview for the platform admin console."""
    from app.models.tenant import QuizItem, TaskItem, WritingPrompt, ListeningPassage, ReadingPassage

    quiz_filter = {"status": "published"}
    if category:
        quiz_filter["category"] = category
    if company:
        quiz_filter["company"] = company
    quiz_items = await QuizItem.find(quiz_filter).limit(limit).to_list()

    task_filter = {"status": "published"}
    if company:
        task_filter["company"] = company
    task_items = await TaskItem.find(task_filter).limit(limit).to_list()

    writing_filter = {"status": "published"}
    if company:
        writing_filter["company"] = company
    writing_prompts = await WritingPrompt.find(writing_filter).limit(limit).to_list()

    listening_filter = {"status": "published"}
    if company:
        listening_filter["company"] = company
    listening = await ListeningPassage.find(listening_filter).limit(limit).to_list()

    reading_filter = {"status": "published"}
    if company:
        reading_filter["company"] = company
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
    return {"id": item_id, "ok": True}


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
