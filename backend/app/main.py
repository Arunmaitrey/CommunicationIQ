"""CommunicationIQ backend.

FastAPI backed by MongoDB, with one control-plane database and one database per
institution. The authenticated session resolves the tenant database; callers
never supply it.
"""
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (attempts, auth, game, invitations, listening,
                         platform_admin, platform_export,
                         reading, report, writing,
                         platform_writes, practice, student, tenant_admin,
                         tenant_writes, trainer, trainer_ops)

log = logging.getLogger(__name__)


async def _sync_exam_test_profiles():
    """Create a SimulationProfile + ProfileSections for every ExamTest that
    lacks one, so a test built in the question-bank admin is immediately
    sittable from the student side without a separate authoring step."""
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz
    from app.db import control_db as _cdb
    from app.models.platform import ExamTest as _ET

    db = _cdb()
    now = _dt.now(_tz.utc)
    task_types = {
        "reading": "reading_comprehension",
        "listening": "audio_comprehension",
        "writing": "writing_task",
        "speaking": "open_response",
    }
    tests = await _ET.find_all().to_list()
    for t in tests:
        existing = await db.simulation_profiles.find_one({"name": t.name})
        if existing:
            continue
        profile_id = str(_uuid.uuid4())
        sections = []
        pos = 1
        for module, count in [
            ("reading", t.reading_questions),
            ("listening", t.listening_questions),
            ("writing", t.writing_questions),
            ("speaking", t.speaking_questions),
        ]:
            if count <= 0:
                continue
            secs_key = f"{module}_seconds"
            resp_secs = getattr(t, secs_key, 300) // count if count else 30
            sections.append({
                "_id": str(_uuid.uuid4()), "profile_id": profile_id,
                "position": pos, "title": module.capitalize(),
                "task_type": task_types.get(module, "reading_comprehension"),
                "instructions": f"Complete the {module} section.",
                "item_count": count, "prep_seconds": 10,
                "response_seconds": resp_secs,
                "prompt_plays_allowed": 1 if module == "listening" else 0,
                "allow_replay": False, "weight": 1.0, "selection": {},
            })
            pos += 1
        await db.simulation_profiles.insert_one({
            "_id": profile_id, "name": t.name, "code": "",
            "style": "simulation", "company": t.company,
            "description": t.description, "status": "published",
            "estimated_minutes": t.duration_minutes,
            "is_baseline": t.is_baseline, "scoring_weights": {},
            "pass_threshold": 0.6, "skill_thresholds": {},
            "created_at": now, "updated_at": now,
        })
        if sections:
            await db.profile_sections.insert_many(sections)
        log.info("Created SimulationProfile for ExamTest: %s", t.name)


async def _sync_company_visibility(name: str, active: bool) -> None:
    """Publish or retire every SimulationProfile and ExamTest carrying one
    company's name, so toggling a company in the admin console takes effect
    for students immediately rather than needing a backend restart.

    Referenced from three spots in platform_admin.py's company CRUD
    (create/update/delete) but never defined anywhere in the merged
    feat/exam-section PR -- each call site already wraps it in a bare
    try/except, so the gap was silent: creating, renaming or deactivating a
    company always "worked", it just never actually changed whether that
    company's content was reachable by a student.
    """
    from datetime import datetime as _dt, timezone as _tz
    from app.db import control_db as _cdb

    db = _cdb()
    now = _dt.now(_tz.utc)
    await db.simulation_profiles.update_many(
        {"company": name},
        {"$set": {"status": "published" if active else "retired",
                  "updated_at": now}})
    await db.exam_tests.update_many(
        {"company": name},
        {"$set": {"is_active": active, "updated_at": now}})


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load the speech model before the first student needs it.

    In a thread, and without blocking startup: a cold load is a couple of
    seconds from cache and a couple of minutes on a machine that has never
    downloaded the weights. Neither should delay the health check, and
    neither should stop the API serving — a host where the model will not
    load falls back to Tier 0 and says so in the provider console.
    """
    # Connect to MongoDB and register the control-plane documents. Tenant
    # databases are bound lazily on first use, so nothing here names a real
    # institution schema.
    try:
        from app.db import init_store

        await init_store()
    except Exception:  # noqa: BLE001 — never block startup on this
        log.exception("MongoDB init failed")

    # Operator-configured AI settings: create the table on an estate that
    # predates it, then fold any stored overrides onto the live settings so
    # the configured provider/model/keys are in force before the first
    # narration job runs. Failure falls back to environment defaults.
    try:
        from app import ai_settings
        await ai_settings.ensure_table()
        applied = await ai_settings.load_and_apply()
        if applied:
            log.info("AI narration overrides applied: %s",
                     ", ".join(sorted(applied)))
    except Exception:  # noqa: BLE001 — env defaults still work
        log.exception("AI settings load failed; using environment defaults")

    engine = _engine_tier()
    if engine["tier"] == 0:
        log.warning(
            "TIER 0 ONLY - speech models unavailable (%s). Pronunciation, "
            "accuracy, grammar and content will report as unscored.",
            ", ".join(engine["missing"]))
    else:
        log.info("Tier 1 speech engine available")

    if settings.whisper_warm_on_startup:
        from app.engine.providers.tier1 import model, pronunciation

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, model.warm)
        loop.run_in_executor(None, pronunciation.warm)

    # The narration recovery sweeper. The fast path is a BackgroundTask fired
    # when an attempt is scored; this loop is the durability net, so a job left
    # pending or half-processed by a restart is picked up rather than lost.
    narration_task = None
    if settings.narration_enabled and settings.narration_worker_enabled:
        from app.narration.worker import run_forever
        narration_task = asyncio.create_task(run_forever())

    # Every ExamTest built in the question-bank admin needs a matching
    # SimulationProfile before a student can sit it — this creates any that
    # are missing. Never blocks startup: a sync failure here just means that
    # test isn't sittable yet, not that the API is down.
    try:
        await _sync_exam_test_profiles()
    except Exception:  # noqa: BLE001
        log.exception("Failed to sync exam test profiles")

    # AI question generation scheduler — off unless an operator has actually
    # configured a key, so an unconfigured deployment does nothing here.
    if settings.auto_question_generation and settings.groq_api_key:
        from app.question_generator import start_scheduler
        start_scheduler()
        log.info("AI question generation scheduler started")

    yield

    if narration_task is not None:
        narration_task.cancel()
        try:
            await narration_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass


app = FastAPI(
    lifespan=lifespan,
    title="CommunicationIQ API",
    version="0.1.0",
    description=(
        "Communication assessment and training for placement readiness. "
        "Every AI capability sits behind a versioned provider contract; every "
        "score carries the provider and version that produced it."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(student.router, prefix=API)
app.include_router(student.consent_router, prefix=API)
app.include_router(attempts.router, prefix=API)
app.include_router(report.router, prefix=API)
app.include_router(listening.router, prefix=API)
app.include_router(reading.router, prefix=API)
app.include_router(writing.router, prefix=API)
app.include_router(game.router, prefix=API)
app.include_router(practice.router, prefix=API)
app.include_router(trainer.router, prefix=API)
app.include_router(trainer_ops.router, prefix=API)
app.include_router(tenant_admin.router, prefix=API)
app.include_router(tenant_writes.router, prefix=API)
app.include_router(platform_admin.router, prefix=API)
app.include_router(platform_admin.asset_router, prefix=API)
app.include_router(platform_writes.router, prefix=API)
app.include_router(platform_export.router, prefix=API)
app.include_router(invitations.router, prefix=API)
# Unauthenticated. A candidate arrives holding a token and nothing else, so
# this is the one router with no session behind it -- see its module docstring
# for the three rules that make that safe.
app.include_router(invitations.public, prefix=API)


def _engine_tier() -> dict:
    """Which scoring tier this instance can actually run.

    Reported rather than assumed. The Tier-1 imports sit inside their
    providers, so an instance without them starts perfectly and then scores
    nothing but timing -- a difference invisible from the outside and easy to
    mistake for the model simply disagreeing with you. Anyone looking at a
    deployment should be able to see which one they have.
    """
    missing: list[str] = []
    for name in ("faster_whisper", "torch", "torchaudio", "transformers"):
        try:
            __import__(name)
        except Exception:  # noqa: BLE001 — absent or broken, same conclusion
            missing.append(name)

    if not missing:
        return {"tier": 1, "speech_models": "available"}
    return {
        "tier": 0,
        "speech_models": "unavailable",
        "missing": missing,
        "effect": ("Pronunciation, accuracy, grammar and content report as "
                   "unscored. Timing measures still work. Install "
                   "requirements-engine.txt to enable them."),
    }


def _build_commit() -> str:
    """Which commit this process is running, if it can tell.

    Render injects RENDER_GIT_COMMIT into every service; a local checkout has
    a .git directory instead. Either way this is read once at import and never
    guessed -- an endpoint that reports a version it is not sure about is
    worse than one that admits it does not know.
    """
    import os
    import subprocess

    commit = os.environ.get("RENDER_GIT_COMMIT", "").strip()
    if commit:
        return commit[:12]
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=str(Path(__file__).resolve().parent.parent))
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001 - no git, no repo, no matter
        return ""


BUILD_COMMIT = _build_commit()


@app.get("/healthz", tags=["ops"])
async def healthz() -> dict:
    """Liveness, plus what is actually running here.

    The commit is reported because working out which build was live took
    behavioural fingerprinting -- probing for an endpoint that only exists in
    a later commit, and diffing a user-visible string against the source. That
    works, but it is archaeology, and it gets harder every release.
    """
    return {"status": "ok", "service": "communicationiq-api",
            "commit": BUILD_COMMIT or "unknown",
            "engine": _engine_tier()}


@app.get(API + "/meta/capability", tags=["ops"])
async def capability() -> dict:
    """What this deployment can actually measure, for the client to say so.

    /healthz reports the same thing for operators. This exists because the
    people who most need to know are candidates: a student who spends twenty
    minutes on a simulation deserves to be told beforehand that this server
    cannot score pronunciation, rather than discovering it on a results page
    with four blanks on it. Unauthenticated, because it describes the server
    and nothing about anyone using it.
    """
    engine = _engine_tier()
    full = engine["tier"] >= 1
    return {
        "tier": engine["tier"],
        "full_scoring": full,
        "measures": (["pronunciation", "accuracy", "grammar", "content",
                      "fluency", "latency", "disfluency"] if full
                     else ["fluency", "latency"]),
        # Said plainly, and only when it is true.
        "note": "" if full else (
            "This server measures timing and fluency only. Pronunciation, "
            "accuracy, grammar and content need speech-recognition models that "
            "are not installed here, so they will show as not measured — and "
            "there will be no overall score, which needs at least three "
            "measures. Your practice still counts."),
    }
