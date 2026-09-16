"""Student surfaces.

Everything here is scoped to the caller: a student reads their own record and
nothing else. There is no student endpoint that takes another user's id.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace

from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app import formats, skills
from app import audit
from app import deadline as app_deadline
from app.deps import Principal, TenantModels, require_roles
from app.schemas import (AttemptOut, ConsentRequest, MasteryOut,
                         SkillModuleOut, SkillsOverview,
                         ProfileSectionOut, QuestOut, SimulationProfileOut,
                         StreakOut, StudentHome, UserOut)

router = APIRouter(prefix="/student", tags=["student"],
                   dependencies=[Depends(require_roles("student"))])

# Consent, on its own router.
consent_router = APIRouter(
    prefix="/student", tags=["student"],
    dependencies=[Depends(require_roles("student"))])

# Level thresholds. Deliberately generous and monotonic: Level is effort
# recognition and always moves up (GAM-03). Honesty lives in the Gap Meter.
_LEVEL_STEP = 500


def _level_for(xp: int) -> int:
    return 1 + xp // _LEVEL_STEP


def _to_user_out(user) -> UserOut:
    return UserOut(
        id=getattr(user, 'id', ''), email=getattr(user, 'email', ''),
        full_name=getattr(user, 'full_name', ''), role=getattr(user, 'role', 'student'),
        active=getattr(user, 'active', True),
        roll_number=getattr(user, 'roll_number', ''), branch=getattr(user, 'branch', ''),
        year_of_study=getattr(user, 'year_of_study', None),
        l1_language=getattr(user, 'l1_language', ''),
        created_at=getattr(user, 'created_at', None),
    )


def _profile_out(profile, sections) -> SimulationProfileOut:
    blueprint = formats.BY_CODE.get(getattr(profile, 'code', ''))
    budgets = formats.section_budgets(getattr(profile, 'code', ''))
    return SimulationProfileOut(
        id=getattr(profile, 'id', ''), code=getattr(profile, 'code', ''),
        name=getattr(profile, 'name', ''), style=getattr(profile, 'style', ''),
        company=getattr(profile, 'company', ''),
        description=getattr(profile, 'description', ''), status=getattr(profile, 'status', ''),
        estimated_minutes=getattr(profile, 'estimated_minutes', 0), is_baseline=getattr(profile, 'is_baseline', False),
        typical_minutes=(formats.typical_minutes(blueprint) if blueprint
                         else profile.estimated_minutes),
        sitting_limit_minutes=app_deadline.allowance_minutes(profile.estimated_minutes),
        # The scoring configuration, so it can be read back and edited.
        scoring_weights=dict(profile.scoring_weights or {}),
        pass_threshold=profile.pass_threshold,
        skill_thresholds=dict(profile.skill_thresholds or {}),
        target_role=profile.target_role, department=profile.department,
        difficulty_band=profile.difficulty_band,
        # From the blueprint where the profile came from one. A round an admin
        # authored by hand has none, and says nothing rather than something
        # generic and wrong.
        what_to_expect=list(blueprint.what_to_expect) if blueprint else [],
        not_included=blueprint.not_included if blueprint else "",
        provenance=blueprint.provenance if blueprint else "",
        sections=[
            ProfileSectionOut(
                id=s.id, position=s.position, title=s.title, task_type=s.task_type,
                instructions=s.instructions, item_count=s.item_count,
                prep_seconds=s.prep_seconds, response_seconds=s.response_seconds,
                prompt_plays_allowed=s.prompt_plays_allowed, allow_replay=s.allow_replay,
                budget_seconds=budgets.get(s.title, 0),
                weight=s.weight,
                # The filter, not the items it selects. A student seeing that
                # a section draws hard banking material is fine; seeing which
                # items it drew would not be.
                selection=dict(s.selection or {}),
            )
            for s in sections
        ],
    )


async def _none():
    """An awaitable ``None`` — for a gather() slot that has nothing to fetch."""
    return None


async def _sections_by_profile(models: SimpleNamespace,
                               profile_ids: list[str]) -> dict[str, list]:
    """Sections grouped by owning profile, each list ordered by position.

    There is no relationship loading to lean on any more; one query with an
    ``$in`` across every profile stands in for the eager load the join did.
    """
    if not profile_ids:
        return {}
    rows = await models.ProfileSection.find(
        In(models.ProfileSection.profile_id, profile_ids)).sort(
        models.ProfileSection.position).to_list()
    grouped: dict[str, list] = {}
    for s in rows:
        grouped.setdefault(s.profile_id, []).append(s)
    return grouped


@router.get("/home", response_model=StudentHome)
async def home(principal: Principal, models: TenantModels) -> StudentHome:
    user = await models.User.get(principal.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")

    # Everything below reads its own rows and none of it depends on any other
    # query's result, so it is fetched as one batch rather than one `await`
    # at a time. Sequentially, each round-trip pays the database's real
    # latency in turn — invisible against a local database, and additive
    # against a remote one, where this endpoint was measured taking the sum
    # of about a dozen round-trips instead of the cost of one.
    (
        consent, attempts, baseline_done, profiles, mastery, xp_rows,
        streak, quest, member,
    ) = await asyncio.gather(
        models.ConsentRecord.find(
            models.ConsentRecord.user_id == user.id,
            models.ConsentRecord.scope == "recording",
        ).sort("-at").first_or_none(),
        models.Attempt.find(
            models.Attempt.user_id == user.id,
        ).sort("-created_at").limit(10).to_list(),
        # Asked as its own question rather than read off the display list
        # above.
        #
        # This used to be `any(a.is_baseline and a.status == "scored" for a
        # in attempts)` over that ten-row slice, so it really answered "is
        # there a scored baseline among your ten most recent attempts". A
        # student who took the baseline and then practised eleven more times
        # was told they had never taken it -- on a screen that was
        # simultaneously listing their scored baseline results underneath.
        models.Attempt.find_one(
            models.Attempt.user_id == user.id,
            models.Attempt.is_baseline == True,
            models.Attempt.status == "scored",
        ),
        # Sections are fetched up front, grouped per profile: serialisation
        # needs the full shape, and there is no lazy load to fall back on
        # mid-response.
        models.SimulationProfile.find(
            models.SimulationProfile.status == "published").sort(
            "-is_baseline", "name").to_list(),
        models.SkillMastery.find(
            models.SkillMastery.user_id == user.id).sort(
            models.SkillMastery.mastery).to_list(),
        models.XPLedger.find(models.XPLedger.user_id == user.id).to_list(),
        models.StreakState.find_one(models.StreakState.user_id == user.id),
        models.Quest.find_one(
            models.Quest.user_id == user.id, models.Quest.kind == "daily",
            models.Quest.for_date == date.today()),
        models.CohortMember.find_one(models.CohortMember.user_id == user.id),
    )
    baseline_done = baseline_done is not None

    # This second batch depends on the first: sections need profile ids,
    # overall scores need attempt ids, and the cohort needs the membership
    # row — each one query, still parallel with the other two.
    sections_by_profile, overall_rows, cohort = await asyncio.gather(
        _sections_by_profile(models, [p.id for p in profiles]),
        models.ScoreRecord.find(
            models.ScoreRecord.dimension == "overall",
            models.ScoreRecord.is_shadow == False,
            In(models.ScoreRecord.attempt_id, [a.id for a in attempts] or [""]),
        ).to_list(),
        (models.Cohort.get(member.cohort_id) if member is not None
         else _none()),
    )
    profile_names = {p.id: p.name for p in profiles}
    overall = {r.attempt_id: r.score for r in overall_rows}
    total_xp = int(sum(r.awarded_xp for r in xp_rows))

    if cohort is not None and not cohort.active:
        cohort = None

    # Days to the real drive date, from the student's cohort. There is no
    # other countdown in the product (GAM-25).
    days_to_drive: int | None = None
    if cohort is not None and cohort.drive_start is not None:
        days_to_drive = (cohort.drive_start.date() - date.today()).days

    # The Gap Meter reads mastery only — never XP (GAM-23).
    gap_percent = round(100 * sum(m.mastery for m in mastery) / len(mastery), 1) if mastery else None

    # Load current plan for the student's tenant
    current_plan_data = None
    plan_expires = None
    tenant_slug = ""
    try:
        from app.models.platform import Plan, Tenant as TenantModel
        from app.db import control_db
        _db = control_db()
        tenant_doc = await _db.tenants.find_one({"_id": user.tenant_id}) if user.tenant_id else None
        if tenant_doc:
            tenant_slug = tenant_doc.get("slug", "")
            if tenant_doc.get("plan_id"):
                plan_doc = await _db.plans.find_one({"_id": tenant_doc["plan_id"]})
                if plan_doc:
                    current_plan_data = {
                        "id": str(plan_doc["_id"]),
                        "name": plan_doc.get("name", ""),
                        "features": plan_doc.get("features", []),
                        "max_questions": plan_doc.get("max_questions", 500),
                        "max_exams_per_day": plan_doc.get("max_exams_per_day", 10),
                        "has_proctoring": plan_doc.get("has_proctoring", True),
                    }
                    plan_expires = tenant_doc.get("plan_expires_at")
    except Exception:
        pass

    # Load active platform exam tests for student visibility (core tests only, not company-specific)
    exam_tests_list = []
    try:
        from app.models.platform import ExamTest
        from app.db import control_db as _control_db
        _cdb = _control_db()
        _tests = await ExamTest.find(
            ExamTest.is_active == True,
            ExamTest.company == "",
        ).to_list()
        exam_tests_list = [
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
                "is_baseline": t.is_baseline, "company": t.company,
                "total_questions": (t.reading_questions + t.listening_questions
                                     + t.writing_questions + t.speaking_questions),
                "total_parts": sum(1 for v in [t.reading_questions, t.listening_questions,
                   t.writing_questions, t.speaking_questions] if v > 0),
            }
            for t in _tests
        ]
    except Exception:
        pass

    return StudentHome(
        user=_to_user_out(user),
        consent_given=bool(consent and consent.granted),
        baseline_done=baseline_done,
        total_xp=int(total_xp),
        level=_level_for(int(total_xp)),
        gap_percent=gap_percent,
        current_plan=current_plan_data,
        plan_expires_at=str(plan_expires) if plan_expires else None,
        tenant_slug=tenant_slug,
        exam_tests=exam_tests_list,
        streak=StreakOut(
            current_streak=streak.current_streak if streak else 0,
            best_streak=streak.best_streak if streak else 0,
            freezes_available=streak.freezes_available if streak else 0,
            last_qualifying_day=streak.last_qualifying_day if streak else None,
        ),
        quest=QuestOut(
            id=quest.id, kind=quest.kind, title=quest.title,
            description=quest.description, target_skill=quest.target_skill,
            progress=quest.progress, target=quest.target, completed=quest.completed,
            bonus_xp=quest.bonus_xp, for_date=quest.for_date,
        ) if quest else None,
        days_to_drive=days_to_drive,
        assigned_profiles=[
            _profile_out(p, sections_by_profile.get(p.id, [])) for p in profiles],
        recent_attempts=[
            AttemptOut(
                id=a.id, profile_id=a.profile_id,
                profile_name=profile_names.get(a.profile_id, ""),
                attempt_number=a.attempt_number, status=a.status, mode=a.mode,
                is_baseline=a.is_baseline, overall_score=overall.get(a.id),
                started_at=a.started_at, submitted_at=a.submitted_at,
                scored_at=a.scored_at,
                proctor_strikes=getattr(a, "proctor_strikes", 0),
            )
            for a in attempts
        ],
        mastery=[
            MasteryOut(skill=m.skill, mastery=m.mastery, baseline=m.baseline,
                       last_change=m.last_change, observations=m.observations)
            for m in mastery
        ],
    )


@router.get("/skills", response_model=SkillsOverview)
async def skills_overview(principal: Principal,
                          models: TenantModels) -> SkillsOverview:
    """Reading, Writing, Listening and Speaking, and what each can really do.

    The headline is deliberately blunt. A student comparing this against a
    four-skill test should learn in one line that it measures one of them
    properly, rather than working it out from four cards.
    """
    modules = await skills.modules_for(models, principal.user_id)
    live = [m.label for m in modules if m.status == "live"]

    if len(live) == 4:
        headline = "All four skills are measured here."
    elif live:
        headline = (
            f"{' and '.join(live)} {'is' if len(live) == 1 else 'are'} fully "
            f"measured. The others are partly built or not started — each card "
            f"says which.")
    else:
        headline = "None of the four are fully measured yet."

    return SkillsOverview(
        headline=headline,
        modules=[SkillModuleOut(**vars(m)) for m in modules],
    )


@router.get("/profiles", response_model=list[SimulationProfileOut])
async def profiles(models: TenantModels) -> list[SimulationProfileOut]:
    rows = await models.SimulationProfile.find(
        models.SimulationProfile.status == "published").sort(
        "-is_baseline", "name").to_list()
    sections_by_profile = await _sections_by_profile(models, [p.id for p in rows])
    return [_profile_out(p, sections_by_profile.get(p.id, [])) for p in rows]


@consent_router.post("/consent", status_code=status.HTTP_201_CREATED)
async def give_consent(body: ConsentRequest, principal: Principal,
                       models: TenantModels, request: Request) -> dict:
    """Record consent before anything is recorded (STU-02).

    Append-only. Withdrawing later writes a new row with ``granted=False``, so
    what a student had agreed to on any past date stays answerable.
    """
    granted = set(body.scopes)
    # Scoring and the report are fully deterministic — there is no external AI
    # service. Scope names are kept stable so older consents stay readable.
    known = {"recording", "training_data", "outcome_sharing", "notifications",
             "ai_explanation"}
    unknown = granted - known
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Unknown consent scope(s): {', '.join(sorted(unknown))}")

    client_ip = request.client.host if request.client else ""
    for scope in sorted(known):
        await models.ConsentRecord(
            user_id=principal.user_id, scope=scope, granted=scope in granted,
            notice_version=body.notice_version, notice_language=body.notice_language,
            ip_address=client_ip,
        ).create()
    return {"recorded": sorted(known), "granted": sorted(granted),
            "at": datetime.now(timezone.utc)}


@router.get("/attempts", response_model=list[AttemptOut])
async def attempts(principal: Principal, models: TenantModels) -> list[AttemptOut]:
    rows = await models.Attempt.find(
        models.Attempt.user_id == principal.user_id,
    ).sort("-created_at").to_list()
    names = {p.id: p.name for p in await models.SimulationProfile.all().to_list()}
    attempt_ids = {a.id for a in rows}
    overall = {r.attempt_id: r.score for r in await models.ScoreRecord.find(
        models.ScoreRecord.dimension == "overall",
        models.ScoreRecord.is_shadow == False,
    ).to_list() if r.attempt_id in attempt_ids}
    return [
        AttemptOut(
            id=a.id, profile_id=a.profile_id, profile_name=names.get(a.profile_id, ""),
            attempt_number=a.attempt_number, status=a.status, mode=a.mode,
            is_baseline=a.is_baseline, overall_score=overall.get(a.id),
            started_at=a.started_at, submitted_at=a.submitted_at, scored_at=a.scored_at,
        )
        for a in rows
    ]


class SubscribeRequest(BaseModel):
    plan_id: str


@router.get("/exam-schedules")
async def student_exam_schedules(principal: Principal,
                                 models: TenantModels) -> list[dict]:
    """Scheduled exams for this student's institution, with window + attempts.

    A platform-scheduled exam is visible only while its window is live (or
    upcoming, so students can see what is coming) and only to students whose
    institution is targeted (or everyone, when the schedule targets all).
    """
    from app.models.platform import ScheduledExam, ExamTest
    from app.db import control_db
    from datetime import datetime, timezone

    db = control_db()
    now = datetime.now(timezone.utc)
    schedules = await ScheduledExam.find(
        ScheduledExam.is_active == True,
        ScheduledExam.ends_at >= now,
    ).sort("starts_at").to_list()

    tests = {t.id: t for t in await ExamTest.find_all().to_list()}
    out = []
    for s in schedules:
        # Institution audience check: empty tenant_ids = everyone (incl general)
        if s.tenant_ids and (not principal.tenant_id
                             or principal.tenant_id not in s.tenant_ids):
            continue
        test = tests.get(s.exam_test_id)
        # A deactivated exam test must not surface, even when scheduled:
        # its SimulationProfile is retired and students could not start it.
        if test is None or not test.is_active:
            continue
        taken = 0
        if s.profile_id:
            taken = await models.Attempt.find(
                models.Attempt.user_id == principal.user_id,
                models.Attempt.profile_id == s.profile_id,
                models.Attempt.created_at >= s.starts_at,
                models.Attempt.created_at <= s.ends_at,
            ).count()
        out.append({
            "id": s.id,
            "exam_test_id": s.exam_test_id,
            "profile_id": s.profile_id,
            "name": test.name,
            "description": test.description,
            "slug": test.slug,
            "duration_minutes": test.duration_minutes,
            "reading_questions": test.reading_questions,
            "listening_questions": test.listening_questions,
            "writing_questions": test.writing_questions,
            "speaking_questions": test.speaking_questions,
            "reading_seconds": test.reading_seconds,
            "listening_seconds": test.listening_seconds,
            "writing_seconds": test.writing_seconds,
            "speaking_seconds": test.speaking_seconds,
            "one_shot_audio": test.one_shot_audio,
            "is_baseline": test.is_baseline,
            "company": test.company,
            "total_questions": (test.reading_questions + test.listening_questions
                                 + test.writing_questions + test.speaking_questions),
            "total_parts": sum(1 for v in [test.reading_questions,
                                            test.listening_questions,
                                            test.writing_questions,
                                            test.speaking_questions] if v > 0),
            "starts_at": s.starts_at.isoformat(),
            "ends_at": s.ends_at.isoformat(),
            "max_attempts": s.max_attempts,
            "attempts_used": int(taken),
            "status": "ended" if now > s.ends_at else (
                "live" if now >= s.starts_at else "upcoming"),
        })
    return out


@router.get("/plans")
async def student_list_plans() -> list[dict]:
    """List active plans for students to browse."""
    from app.db import control_db
    db = control_db()
    rows = await db["plans"].find({"is_active": True}).sort("created_at", -1).to_list(100)
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


@router.post("/subscribe")
async def subscribe_to_plan(body: SubscribeRequest, principal: Principal) -> dict:
    """Subscribe to a plan (general users only)."""
    from app.db import control_db
    from app.models.platform import Tenant, Plan
    from datetime import datetime, timezone
    
    db = control_db()
    tenant_doc = await db.tenants.find_one({"_id": principal.tenant_id}) if principal.tenant_id else None
    
    if not tenant_doc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tenant associated with your account")
    
    # Only general users can subscribe via this endpoint
    if tenant_doc.get("slug") != "general":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Institutional users do not need to subscribe")
    
    # Verify the plan exists and is active
    plan_doc = await db.plans.find_one({"_id": body.plan_id})
    if not plan_doc or not plan_doc.get("is_active", True):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found or inactive")
    
    # For paid plans, check if payment gateway is configured
    if plan_doc.get("price_monthly", 0) > 0:
        payment_config = await db.payment_configs.find_one({"is_active": True})
        if not payment_config:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Payment is not yet configured. Please contact your administrator."
            )
    
    # Update the tenant's plan
    expires = None
    if plan_doc.get("price_monthly", 0) > 0:
        # Paid plan: expires in 30 days from now
        from datetime import timedelta
        expires = datetime.now(timezone.utc) + timedelta(days=30)
    await db.tenants.update_one(
        {"_id": tenant_doc["_id"]},
        {"$set": {
            "plan_id": body.plan_id,
            "plan_expires_at": expires,
        }}
    )

    await audit.record(principal, "plan.subscribed",
                       entity="Tenant", entity_id=tenant_doc["_id"],
                       before={"plan_id": str(tenant_doc.get("plan_id", ""))},
                       after={"plan_id": body.plan_id,
                              "plan_name": plan_doc.get("name", ""),
                              "expires_at": expires.isoformat() if expires else None})
    
    return {"ok": True, "plan": plan_doc.get("name", "")}


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@router.get("/leaderboard")
async def leaderboard(principal: Principal, scope: str = "institution",
                      limit: int = 50) -> dict:
    """Student rankings by best overall exam score.

    scope=institution ranks students of the caller's own institution;
    scope=global ranks students across every institution on the platform.
    Ranking is computed live from score_records (best overall, non-shadow)
    and attempts — nothing is stored, so it is always current.
    """
    from app.db import control_db
    db = control_db()

    q: dict = {"role": "student"}
    if scope == "institution":
        if not principal.tenant_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Institution ranking needs an institution account")
        q["tenant_id"] = principal.tenant_id
    users = await db.users.find(q).to_list()
    if not users:
        return {"rows": [], "updated_at": datetime.now(timezone.utc).isoformat()}

    uids = [u["_id"] for u in users]

    # Best overall score per student.
    best: dict = {}
    agg = db.score_records.aggregate([
        {"$match": {"user_id": {"$in": uids}, "dimension": "overall",
                    "is_shadow": {"$ne": True}}},
        {"$group": {"_id": "$user_id", "best": {"$max": "$score"}}},
    ])
    async for r in agg:
        best[r["_id"]] = r["best"]

    # Attempt counts + last scored date per student.
    counts: dict = {}
    last_at: dict = {}
    agg2 = db.attempts.aggregate([
        {"$match": {"user_id": {"$in": uids}}},
        {"$group": {"_id": "$user_id", "n": {"$sum": 1},
                    "last": {"$max": "$created_at"}}},
    ])
    async for r in agg2:
        counts[r["_id"]] = r["n"]
        last_at[r["_id"]] = r["last"]

    # Institution names (only needed for the global view).
    tenant_names: dict = {}
    if scope == "global":
        async for t in db.tenants.find({}):
            tenant_names[t["_id"]] = t.get("name", "")

    rows = []
    for u in users:
        uid = u["_id"]
        score = best.get(uid)
        if score is None:
            continue  # only students with a scored exam appear on the board
        rows.append({
            "user_id": uid,
            "full_name": u.get("full_name", ""),
            "email": u.get("email", ""),
            "roll_number": u.get("roll_number", ""),
            "institution": tenant_names.get(u.get("tenant_id")) if scope == "global"
                           else "",
            "best_score": round(float(score), 1),
            "attempts": counts.get(uid, 0),
            "last_attempt_at": last_at.get(uid),
            "is_me": uid == principal.user_id,
        })

    rows.sort(key=lambda r: (-r["best_score"], -r["attempts"],
                             r["full_name"].lower()))
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    me = next((r for r in rows if r["is_me"]), None)
    top = rows[:max(limit, 1)]
    if me and me["rank"] > len(top):
        top = top + [me]
    return {
        "rows": top,
        "total": len(rows),
        "me": {"rank": me["rank"], "best_score": me["best_score"]} if me else None,
        "scope": scope,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
