"""CommunicationIQ backend.

FastAPI backed by MongoDB, with one control-plane database and one database per
institution. The authenticated session resolves the tenant database; callers
never supply it.
"""
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (attempts, auth, game, invitations, listening,
                          notifications, platform_admin, platform_export,
                          reading, report, writing,
                          platform_writes, practice, student, tenant_admin,
                          tenant_writes)

log = logging.getLogger(__name__)





async def _sync_exam_test_profiles():
    """Create SimulationProfiles + ProfileSections for every ExamTest that lacks
    one, and keep each existing profile's published status in step with the
    ExamTest's `is_active` flag.

    The profile is the student-facing object (the tests page lists published
    SimulationProfiles), so this routine is what makes an ExamTest visible or
    hidden on the student side *without a restart*: toggling `is_active` in the
    platform console and re-running this sync retires or re-publishes the linked
    profile immediately.
    """
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz
    from app.db import control_db as _cdb
    from app.models.platform import ExamTest as _ET

    db = _cdb()
    now = _dt.now(_tz.utc)
    task_types = {
        'reading': 'reading_comprehension',
        'listening': 'audio_comprehension',
        'writing': 'writing_task',
        'speaking': 'open_response',
        'quiz': 'grammar',
    }
    # Map exam test names to the style codes the student simulate page uses
    # to group tests into families (diagnostic, vendor, professional, etc.).
    _style_map = {
        'baseline': 'diagnostic',
        'professional': 'professional',
        'svar': 'svar_style',
        'speechx': 'speechx_style',
        'versant': 'versant_style',
    }
    tests = await _ET.find_all().to_list()
    for t in tests:
        existing = await db.simulation_profiles.find_one({'name': t.name})
        if existing:
            # Keep the student-facing profile in step with the ExamTest:
            # inactive test -> retire profile (hidden); active test -> publish it.
            want = 'published' if t.is_active else 'retired'
            updates: dict = {}
            if existing.get('status') != want:
                updates['status'] = want
            # Fix style if wrong
            want_style = 'simulation'
            for kw, sty in _style_map.items():
                if kw in t.name.lower():
                    want_style = sty
                    break
            if existing.get('style') != want_style:
                updates['style'] = want_style
            if updates:
                updates['updated_at'] = now
                await db.simulation_profiles.update_one(
                    {'_id': existing['_id']},
                    {'$set': updates})
                log.info("ExamTest %s -> SimulationProfile %s", t.name, updates)
            continue
        profile_id = str(_uuid.uuid4())
        sections = []
        pos = 1
        for module, count in [
            ('reading', t.reading_questions),
            ('listening', t.listening_questions),
            ('writing', t.writing_questions),
            ('speaking', t.speaking_questions),
            ('quiz', getattr(t, 'quiz_questions', 0)),
        ]:
            if count <= 0:
                continue
            secs_key = f'{module}_seconds'
            resp_secs = getattr(t, secs_key, 300) // count if count else 30
            sections.append({
                '_id': str(_uuid.uuid4()), 'profile_id': profile_id,
                'position': pos, 'title': 'Grammar & Vocabulary' if module == 'quiz' else module.capitalize(),
                'task_type': task_types.get(module, 'reading_comprehension'),
                'instructions': f'Complete the {"grammar and vocabulary" if module == "quiz" else module} section.',
                'item_count': count, 'prep_seconds': 10,
                'response_seconds': resp_secs,
                'prompt_plays_allowed': 1 if module == 'listening' else 0,
                'allow_replay': False, 'weight': 1.0, 'selection': {},
            })
            pos += 1
        # Determine style from test name
        want_style = 'simulation'
        for kw, sty in _style_map.items():
            if kw in t.name.lower():
                want_style = sty
                break
        await db.simulation_profiles.insert_one({
            '_id': profile_id, 'name': t.name, 'code': '',
            'style': want_style, 'company': t.company,
            'description': t.description, 'status': 'published',
            'estimated_minutes': t.duration_minutes,
            'is_baseline': t.is_baseline, 'scoring_weights': {},
            'pass_threshold': 0.6, 'skill_thresholds': {},
            'created_at': now, 'updated_at': now,
        })
        if sections:
            await db.profile_sections.insert_many(sections)
        log.info("Created SimulationProfile for ExamTest: %s", t.name)


async def _sync_company_visibility(company_name: str, is_active: bool):
    """Flip student-facing objects for one company in step with its activation.

    A company round is shown to students through published SimulationProfiles
    whose `company` matches, and through ExamTests tagged with that company
    (which own the weightage/timing). Deactivating a company therefore retires
    those profiles and deactivates those tests; reactivating reverses it — so
    the Companies console controls student visibility live, without a restart.
    """
    from datetime import datetime as _dt, timezone as _tz
    from app.db import control_db as _cdb

    db = _cdb()
    now = _dt.now(_tz.utc)
    want_profile = 'published' if is_active else 'retired'
    await db.simulation_profiles.update_many(
        {'company': company_name},
        {'$set': {'status': want_profile, 'updated_at': now}})
    await db.exam_tests.update_many(
        {'company': company_name},
        {'$set': {'is_active': is_active, 'updated_at': now}})
    # A reactivated company with no published SimulationProfile yet: make sure
    # its ExamTests still have profiles (create + publish, matching is_active).
    if is_active:
        try:
            await _sync_exam_test_profiles()
        except Exception:  # noqa: BLE001 — never block a company toggle on this
            log.exception("profile sync after company activation failed")
    log.info("Company %s -> active=%s (student-facing profiles/tests synced)",
             company_name, is_active)


async def _seed_exam_tests():
    """Ensure the five core exam tests exist.

    Baseline Diagnostic, Professional English, SVAR-style, SpeechX-style,
    and Versant-style Speaking Test. Updates existing ones if values differ.
    """
    from app.models.platform import ExamTest
    from datetime import datetime as _dt, timezone as _tz

    now = _dt.now(_tz.utc)
    defaults = [
        {
            "name": "Baseline Diagnostic",
            "description": "Short diagnostic taken once, before any training is assigned. About 10 minutes.",
            "duration_minutes": 15,
            "reading_questions": 10, "listening_questions": 10,
            "writing_questions": 10, "speaking_questions": 5,
            "quiz_questions": 10,
            "reading_seconds": 300, "listening_seconds": 300,
            "writing_seconds": 300, "speaking_seconds": 150,
            "quiz_seconds": 300,
            "is_baseline": True, "is_active": True, "company": "",
        },
        {
            "name": "Professional English",
            "description": "Ten parts across all four skills plus grammar on workplace material. About 60 minutes.",
            "duration_minutes": 60,
            "reading_questions": 12, "listening_questions": 12,
            "writing_questions": 12, "speaking_questions": 12,
            "quiz_questions": 12,
            "reading_seconds": 720, "listening_seconds": 720,
            "writing_seconds": 720, "speaking_seconds": 720,
            "quiz_seconds": 360,
            "is_active": True, "company": "",
        },
        {
            "name": "SVAR-style Communication Assessment (4-section)",
            "description": "Five-section assessment: reading, listening, speaking, writing, grammar and comprehension.",
            "duration_minutes": 61,
            "reading_questions": 15, "listening_questions": 15,
            "writing_questions": 15, "speaking_questions": 22,
            "quiz_questions": 20,
            "reading_seconds": 900, "listening_seconds": 900,
            "writing_seconds": 900, "speaking_seconds": 1320,
            "quiz_seconds": 600,
            "one_shot_audio": True, "is_active": True, "company": "",
        },
        {
            "name": "SpeechX-style Communication Assessment (Mercer | Mettl)",
            "description": "SpeechX communication assessment: reading, listening, speaking, writing, grammar and comprehension.",
            "duration_minutes": 60,
            "reading_questions": 15, "listening_questions": 15,
            "writing_questions": 15, "speaking_questions": 22,
            "quiz_questions": 20,
            "reading_seconds": 900, "listening_seconds": 900,
            "writing_seconds": 900, "speaking_seconds": 1320,
            "quiz_seconds": 600,
            "one_shot_audio": True, "is_active": True, "company": "",
        },
        {
            "name": "Versant-style Speaking Test",
            "description": "Six-part spoken test: read on cue, repeat, short answers, sentence builds, story retelling, open questions.",
            "duration_minutes": 22,
            "reading_questions": 0, "listening_questions": 10,
            "writing_questions": 0, "speaking_questions": 20,
            "quiz_questions": 0,
            "reading_seconds": 0, "listening_seconds": 600,
            "writing_seconds": 0, "speaking_seconds": 720,
            "quiz_seconds": 0,
            "one_shot_audio": True, "is_active": True, "company": "",
        },
    ]
    existing = await ExamTest.find_all().to_list()
    existing_map = {t.name: t for t in existing}
    created = 0
    updated = 0
    for d in defaults:
        if d["name"] in existing_map:
            # Update existing tests that may be missing quiz_questions
            t = existing_map[d["name"]]
            changed = False
            for key in ("quiz_questions", "quiz_seconds", "duration_minutes",
                        "reading_questions", "listening_questions",
                        "writing_questions", "speaking_questions",
                        "reading_seconds", "listening_seconds",
                        "writing_seconds", "speaking_seconds"):
                if key in d and getattr(t, key, None) != d[key]:
                    setattr(t, key, d[key])
                    changed = True
            if t.description != d.get("description", t.description):
                t.description = d["description"]
                changed = True
            if changed:
                await t.save()
                updated += 1
            continue
        import re as _re
        d["slug"] = _re.sub(r"[^a-z0-9]+", "-", d["name"].lower()).strip("-")
        t = ExamTest(**d)
        await t.create()
        created += 1
    if created or updated:
        log.info("Seeded %d missing, updated %d existing exam tests", created, updated)
        await _sync_exam_test_profiles()


async def lifespan(_app: FastAPI):
    """Load the speech model before the first student needs it.

    In a thread, and without blocking startup: a cold load is a couple of
    seconds from cache and a couple of minutes on a machine that has never
    downloaded the weights. Neither should delay the health check, and
    neither should stop the API serving ΓÇö a host where the model will not
    load falls back to heuristic providers and says so in the provider console.
    """
    # Connect to MongoDB and register the control-plane documents. Tenant
    # databases are bound lazily on first use, so nothing here names a real
    # institution schema.
    try:
        from app.db import init_store

        await init_store()
    except Exception:  # noqa: BLE001 — never block startup on this
        log.exception("MongoDB init failed")

    # Former AI-settings / narration overrides were removed with the
    # narration module; reports are deterministic and need no LLM pass.

    engine = _engine_status()
    if not engine["speech_models_available"]:
        log.warning(
            "Speech models unavailable (%s). Pronunciation, accuracy, grammar "
            "and content will report as unscored; timing measures still work.",
            ", ".join(engine["missing"]))
    else:
        log.info("Speech engine available (ASR + pronunciation scoring)")

    # Seed default exam tests if the collection is empty
    try:
        await _seed_exam_tests()
    except Exception:
        log.exception("Exam test seeding failed")



    # No content seeding at startup: tests, companies and plans are created by
    # the platform admin and persist in the database.

    yield

    # (Question-generation scheduler removed with the Groq module.)


app = FastAPI(
    lifespan=lifespan,
    title="CommunicationIQ API",
    version="0.1.0",
    description=(
        "Communication assessment and training for placement readiness. "
        "Every score carries the deterministic engine and version that "
        "produced it."
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
app.include_router(listening.router, prefix=API)
app.include_router(reading.router, prefix=API)
app.include_router(writing.router, prefix=API)
app.include_router(game.router, prefix=API)
app.include_router(practice.router, prefix=API)
app.include_router(tenant_admin.router, prefix=API)
app.include_router(tenant_writes.router, prefix=API)
app.include_router(platform_admin.router, prefix=API)
app.include_router(platform_admin.asset_router, prefix=API)
app.include_router(platform_writes.router, prefix=API)
app.include_router(platform_export.router, prefix=API)
app.include_router(invitations.router, prefix=API)
app.include_router(notifications.router, prefix=API)
app.include_router(report.router, prefix=API)
# Unauthenticated. A candidate arrives holding a token and nothing else, so
# this is the one router with no session behind it -- see its module docstring
# for the three rules that make that safe.
app.include_router(invitations.public, prefix=API)


def _engine_status() -> dict:
    """Which speech capabilities this instance can actually run.

    Reported rather than assumed. The ML provider imports sit inside their
    providers, so an instance without them starts perfectly and then scores
    nothing but timing -- a difference invisible from the outside and easy to
    mistake for the model simply disagreeing with you. Anyone looking at a
    deployment should be able to see which one they have.

    One engine, one status: there is no tier split any more. The deps are
    open-source (faster-whisper + wav2vec2 via torch) and either installed
    or not.
    """
    missing: list[str] = []
    for name in ("torch", "torchaudio", "transformers", "faster_whisper"):
        try:
            __import__(name)
        except Exception:  # noqa: BLE001 — absent or broken, same conclusion
            missing.append(name)

    if not missing:
        return {"speech_models_available": True, "missing": []}
    return {
        "speech_models_available": False,
        "missing": missing,
        "effect": ("Pronunciation, accuracy, grammar and content report as "
                   "unscored. Timing measures still work. Install "
                   "requirements.txt to enable them."),
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
@app.get("/health", tags=["ops"])
async def healthz() -> dict:
    """Liveness, plus what is actually running here.

    The commit is reported because working out which build was live took
    behavioural fingerprinting -- probing for an endpoint that only exists in
    a later commit, and diffing a user-visible string against the source. That
    works, but it is archaeology, and it gets harder every release.
    """
    return {"status": "ok", "service": "communicationiq-api",
            "commit": BUILD_COMMIT or "unknown",
            "engine": _engine_status()}


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
    engine = _engine_status()
    full = engine["speech_models_available"]
    return {
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
