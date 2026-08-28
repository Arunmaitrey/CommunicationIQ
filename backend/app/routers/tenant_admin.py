"""Institution console â€” the tenant admin's own view of their institution.

Every query runs against the caller's own institution database. There is no
institution identifier in any signature here, because there is nowhere else
to look.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from beanie.operators import In, NE
from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import Principal, TenantModels, require_roles
from app.models.platform import Tenant
from app.models.tenant import (Attempt, CohortMember, ExamReview,
                               SimulationProfile, StudentFlag, User)
from app.readiness import HIGH_RISK, NEEDS_TRAINING, NOT_STARTED, READY, band
from app.schemas import (AttemptOut, CohortOut, CohortReadiness,
                         ProfileSectionOut, ReviewOut, SimulationProfileOut,
                         StudentSummary, TenantOverview, UserOut)

router = APIRouter(prefix="/tenant", tags=["tenant-admin"],
                   dependencies=[Depends(require_roles("tenant_admin"))])


@router.get("/overview", response_model=TenantOverview)
async def overview(principal: Principal, models: TenantModels) -> TenantOverview:
    tenant = await Tenant.get(principal.tenant_id or "")
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")

    role_docs = await models.User.get_motor_collection().aggregate([
        {"$match": {"active": True}},
        {"$group": {"_id": "$role", "n": {"$sum": 1}}},
    ]).to_list(None)
    counts = {d["_id"]: int(d["n"]) for d in role_docs}
    cohorts = await models.Cohort.find(models.Cohort.active == True).count()  # noqa: E712
    attempts = await models.Attempt.find_all().count()

    students = counts.get("student", 0)
    consented_ids = await models.ConsentRecord.get_motor_collection().distinct(
        "user_id", {"scope": "recording", "granted": True})
    consented = len(consented_ids)

    return TenantOverview(
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        seats_used=students + counts.get("tenant_admin", 0),
        seat_limit=tenant.seat_limit,
        students=students,
        cohorts=int(cohorts),
        attempts_total=int(attempts),
        consent_pending=max(students - int(consented), 0),
    )


@router.get("/users", response_model=list[UserOut])
async def users(models: TenantModels, role: str | None = None) -> list[UserOut]:
    query = (models.User.find(models.User.role == role) if role
             else models.User.find_all())
    rows = await query.sort("role", "full_name").to_list()
    return [
        UserOut(
            id=getattr(u, 'id', ''), email=getattr(u, 'email', ''), full_name=getattr(u, 'full_name', ''),
            role=getattr(u, 'role', 'student'), active=getattr(u, 'active', True),
            roll_number=getattr(u, 'roll_number', ''), branch=getattr(u, 'branch', ''),
            year_of_study=getattr(u, 'year_of_study', None),
            l1_language=getattr(u, 'l1_language', ''),
            created_at=getattr(u, 'created_at', None),
        )
        for u in rows
    ]


@router.get("/cohorts", response_model=list[CohortOut])
async def cohorts(models: TenantModels) -> list[CohortOut]:
    rows = await models.Cohort.find_all().sort("name").to_list()
    member_docs = await models.CohortMember.get_motor_collection().aggregate([
        {"$group": {"_id": "$cohort_id", "n": {"$sum": 1}}},
    ]).to_list(None)
    counts = {d["_id"]: int(d["n"]) for d in member_docs}
    return [
        CohortOut(
            id=c.id, name=c.name, branch=c.branch, year_of_study=c.year_of_study,
            section=c.section,
            drive_start=c.drive_start, drive_end=c.drive_end,
            member_count=counts.get(c.id, 0), active=c.active,
        )
        for c in rows
    ]


@router.get("/profiles", response_model=list[SimulationProfileOut])
async def profiles(models: TenantModels,
                   include_retired: bool = False) -> list[SimulationProfileOut]:
    """The assessment library.

    Retired assessments are excluded unless asked for, and the default is the
    important part.

    Retiring is how an assessment leaves circulation here, and it is a
    deliberate choice over deleting: attempts name their profile, and a result
    whose profile vanished cannot be read back. The consequence is that
    retired rows accumulate permanently, and this endpoint returned every one
    of them with its sections attached. On the demo estate that was 1466 rows
    and a 1.25 MB response, on a screen that also renders each of them as a
    card -- so the library an admin actually works in was 190 KB of
    assessments nobody can sit.

    That is not a seeding artefact. It is what any customer's library becomes
    after a few years of ordinary use.
    """
    query = (models.SimulationProfile.find_all() if include_retired else
             models.SimulationProfile.find(
                 NE(models.SimulationProfile.status, "retired")))
    rows = await query.sort("style", "name").to_list()
    # Sections are loaded here now: the console is a builder rather than a
    # list, and an admin cannot edit a section they were never sent.
    sections_by_profile: dict[str, list] = {}
    if rows:
        section_rows = await models.ProfileSection.find(In(
            models.ProfileSection.profile_id,
            [p.id for p in rows]),
        ).sort("position").to_list()
        for x in section_rows:
            sections_by_profile.setdefault(x.profile_id, []).append(x)
    return [
        SimulationProfileOut(
            id=p.id, code=p.code, name=p.name, style=p.style, company=p.company,
            description=p.description,
            status=p.status, estimated_minutes=p.estimated_minutes,
            is_baseline=p.is_baseline,
            # The scoring configuration, so it can be read back and edited.
            scoring_weights=dict(p.scoring_weights or {}),
            pass_threshold=p.pass_threshold,
            skill_thresholds=dict(p.skill_thresholds or {}),
            target_role=p.target_role, department=p.department,
            difficulty_band=p.difficulty_band,
            sections=[
                ProfileSectionOut(
                    id=x.id, position=x.position, title=x.title,
                    task_type=x.task_type, instructions=x.instructions,
                    item_count=x.item_count, prep_seconds=x.prep_seconds,
                    response_seconds=x.response_seconds,
                    prompt_plays_allowed=x.prompt_plays_allowed,
                    allow_replay=x.allow_replay,
                    weight=x.weight,
                )
                for x in sorted(sections_by_profile.get(p.id, []),
                                key=lambda x: x.position)
            ],
        )
        for p in rows
    ]


@router.get("/season")
async def season(models: TenantModels) -> list[dict]:
    """Each cohort's real placement window and what it implies (TEN-13)."""
    rows = await models.Cohort.find(
        models.Cohort.active == True).sort("name").to_list()  # noqa: E712
    out = []
    for c in rows:
        days = (c.drive_start.date() - date.today()).days if c.drive_start else None
        out.append({
            "cohort_id": c.id,
            "cohort_name": c.name,
            "drive_start": c.drive_start,
            "drive_end": c.drive_end,
            "days_to_drive": days,
            # No date set means a rolling 90-day season, never an invented deadline.
            "season_source": "drive_date" if c.drive_start else "rolling_90_day",
        })
    return out


@router.get("/reviews", response_model=list[ReviewOut])
async def tenant_reviews(principal: Principal, models: TenantModels,
                         limit: int = 50) -> list[ReviewOut]:
    """All reviews for this tenant, most recent first."""
    from app.db import control_db
    db = control_db()
    tenant_id = principal.tenant_id or ""
    query = {"tenant_id": tenant_id} if tenant_id else {}
    raw = await db.exam_reviews.find(query).sort("created_at", -1).limit(limit).to_list()
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
        ReviewOut(
            id=str(r.get("_id", "")),
            attempt_id=r.get("attempt_id", ""),
            user_id=r.get("user_id", ""),
            user_name=users.get(r.get("user_id", ""), {}).get("full_name", ""),
            user_email=users.get(r.get("user_id", ""), {}).get("email", ""),
            profile_name=profiles.get(r.get("profile_id", ""), {}).get("name", ""),
            rating=r.get("rating", 0),
            difficulty=r.get("difficulty", "just_right"),
            comment=r.get("comment", ""),
            created_at=r.get("created_at", ""),
        )
        for r in raw
    ]


def _ensure_aware(dt) -> datetime:
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _latest_overall(models, user_ids) -> dict[str, float]:
    if not user_ids:
        return {}
    attempts = await models.Attempt.find(
        In(models.Attempt.user_id, user_ids)).to_list()
    overall_by_attempt = {}
    if attempts:
        rows = await models.ScoreRecord.find(
            In(models.ScoreRecord.attempt_id, [a.id for a in attempts]),
            models.ScoreRecord.dimension == "overall",
            models.ScoreRecord.is_shadow == False,
        ).to_list()
        overall_by_attempt = {r.attempt_id: r.score for r in rows}

    latest: dict[str, float] = {}
    for attempt in sorted(attempts, key=lambda a: a.scored_at
                          or datetime.min.replace(tzinfo=timezone.utc),
                          reverse=True):
        if attempt.user_id in latest:
            continue
        score = overall_by_attempt.get(attempt.id)
        if score is not None:
            latest[attempt.user_id] = score
    return latest


@router.get("/cohorts/{cohort_id}/readiness", response_model=CohortReadiness)
async def cohort_readiness(cohort_id: str, principal: Principal,
                           models: TenantModels) -> CohortReadiness:
    cohort = await models.Cohort.get(cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cohort not found")

    members = await models.CohortMember.find(
        models.CohortMember.cohort_id == cohort_id).to_list()
    member_ids = [m.user_id for m in members]
    latest = await _latest_overall(models, member_ids)

    bands = [band(latest.get(uid)) for uid in member_ids]
    scores = [s for s in latest.values()]

    return CohortReadiness(
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        total=len(member_ids),
        assessed=len(latest),
        placement_ready=bands.count(READY),
        needs_training=bands.count(NEEDS_TRAINING),
        high_risk=bands.count(HIGH_RISK),
        not_started=bands.count(NOT_STARTED),
        average_overall=round(sum(scores) / len(scores), 1) if scores else None,
        days_to_drive=((cohort.drive_start.date() - date.today()).days
                       if cohort.drive_start else None),
    )


@router.get("/cohorts/{cohort_id}/students", response_model=list[StudentSummary])
async def cohort_students(cohort_id: str, principal: Principal,
                          models: TenantModels) -> list[StudentSummary]:
    """Students in a specific cohort with scores and readiness."""
    from app.db import control_db
    db = control_db()

    cohort = await models.Cohort.get(cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cohort not found")

    # Get member user_ids
    member_docs = await db.cohort_members.find({"cohort_id": cohort_id}).to_list()
    member_ids = [m["user_id"] for m in member_docs if m.get("user_id")]
    if not member_ids:
        return []

    # Get users
    users_docs = await db.users.find({"_id": {"$in": member_ids}, "role": "student"}).to_list()
    if not users_docs:
        return []

    user_ids = [u["_id"] for u in users_docs]

    # Get latest overall score per user
    latest = {}
    score_docs = await db.score_records.find({
        "user_id": {"$in": user_ids}, "dimension": "overall", "is_shadow": {"$ne": True}
    }).sort("created_at", -1).to_list()
    for s in score_docs:
        uid = s.get("user_id")
        if uid and uid not in latest:
            latest[uid] = s.get("score")

    # Get attempt counts and last attempt date
    attempt_count = {}
    last_attempt = {}
    attempt_docs = await db.attempts.find({"user_id": {"$in": user_ids}}).to_list()
    for a in attempt_docs:
        uid = a.get("user_id")
        if uid:
            attempt_count[uid] = attempt_count.get(uid, 0) + 1
            scored = a.get("scored_at")
            if scored:
                if uid not in last_attempt or scored > last_attempt[uid]:
                    last_attempt[uid] = scored

    # Get flagged users
    flagged_docs = await db.student_flags.find({"user_id": {"$in": user_ids}}).to_list()
    flagged = {f.get("user_id") for f in flagged_docs}

    now = datetime.now(timezone.utc)
    results = []
    for u in users_docs:
        uid = u["_id"]
        last = last_attempt.get(uid)
        last_dt = _ensure_aware(last) if last else None
        results.append(StudentSummary(
            user=UserOut(
                id=uid, full_name=u.get("full_name", ""), email=u.get("email", ""),
                role=u.get("role", "student"), active=True,
                roll_number=u.get("roll_number", ""), branch=u.get("branch", ""),
                created_at=u.get("created_at", now)
            ),
            attempts=attempt_count.get(uid, 0),
            last_attempt_at=last,
            overall_score=latest.get(uid),
            readiness=band(latest.get(uid)),
            days_since_activity=(now - last_dt).days if last_dt else None,
            flagged=uid in flagged,
        ))
    return results


@router.get("/students/{user_id}/attempts", response_model=list[AttemptOut])
async def student_attempts(user_id: str, principal: Principal,
                           models: TenantModels) -> list[AttemptOut]:
    user = await models.User.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")

    rows = await models.Attempt.find(
        models.Attempt.user_id == user_id).sort(
        -models.Attempt.created_at).to_list()

    profiles = await models.SimulationProfile.find(
        In(models.SimulationProfile.id,
           [r.profile_id for r in rows] or [""])).to_list()
    names = {p.id: p.name for p in profiles}

    return [AttemptOut(
        id=r.id, profile_id=r.profile_id,
        profile_name=names.get(r.profile_id, ""),
        attempt_number=r.attempt_number, status=r.status, mode=r.mode,
        is_baseline=r.is_baseline, overall_score=None,
        started_at=r.started_at, submitted_at=r.submitted_at,
        scored_at=r.scored_at,
        ip_address=getattr(r, "ip_address", ""),
    ) for r in rows]


@router.get("/results", response_model=list[AttemptOut])
async def tenant_results(principal: Principal, models: TenantModels) -> list[AttemptOut]:
    """All completed attempts for this tenant."""
    attempts = await models.Attempt.find(
        models.Attempt.tenant_id == principal.tenant_id,
        models.Attempt.status == "submitted"
    ).sort(-models.Attempt.scored_at).to_list()
    profiles = await models.SimulationProfile.find(
        In(models.SimulationProfile.id, [r.profile_id for r in attempts] or [""])).to_list()
    names = {p.id: p.name for p in profiles}
    return [AttemptOut(
        id=r.id, profile_id=r.profile_id, profile_name=names.get(r.profile_id, ""),
        attempt_number=r.attempt_number, status=r.status, mode=r.mode,
        is_baseline=r.is_baseline, overall_score=None,
        started_at=r.started_at, submitted_at=r.submitted_at,
        scored_at=r.scored_at, ip_address=getattr(r, "ip_address", ""),
    ) for r in attempts]


@router.get("/readiness", response_model=list[StudentSummary])
async def tenant_readiness_overview(principal: Principal, models: TenantModels) -> list[StudentSummary]:
    """Readiness overview for all students in tenant."""
    from app.db import control_db
    from app.readiness import band
    from app.models.tenant import User
    db = control_db()
    
    # Get student user_ids for this tenant
    users_docs = await db.users.find({"tenant_id": principal.tenant_id, "role": "student"}).to_list()
    user_ids = [u["_id"] for u in users_docs]
    if not user_ids:
        return []
    
    # Get latest overall score per user
    latest = {}
    score_docs = await db.score_records.find({
        "user_id": {"$in": user_ids}, "dimension": "overall", "is_shadow": {"$ne": True}
    }).sort("created_at", -1).to_list()
    for s in score_docs:
        uid = s.get("user_id")
        if uid and uid not in latest:
            latest[uid] = s.get("score")
    
    # Get last attempt date per user and attempt count
    last_attempt = {}
    attempt_count = {}
    attempt_docs = await db.attempts.find({"user_id": {"$in": user_ids}}).to_list()
    for a in attempt_docs:
        uid = a.get("user_id")
        if uid:
            attempt_count[uid] = attempt_count.get(uid, 0) + 1
            scored = a.get("scored_at")
            if scored:
                if uid not in last_attempt or scored > last_attempt[uid]:
                    last_attempt[uid] = scored
    
    # Get flagged users
    flagged = set()
    flag_docs = await db.student_flags.find({"user_id": {"$in": user_ids}}).to_list()
    for f in flag_docs:
        flagged.add(f.get("user_id"))

    now = datetime.now(timezone.utc)
    results = []
    for u in users_docs:
        uid = u["_id"]
        last = last_attempt.get(uid)
        last_dt = _ensure_aware(last) if last else None
        results.append(StudentSummary(
            user=UserOut(
                id=uid, full_name=u.get("full_name", ""), email=u.get("email", ""),
                role=u.get("role", "student"), active=True,
                roll_number=u.get("roll_number", ""), branch=u.get("branch", ""),
                year_of_study=u.get("year_of_study"), l1_language=u.get("l1_language", ""),
                created_at=u.get("created_at", now)
            ),
            attempts=attempt_count.get(uid, 0),
            last_attempt_at=last,
            overall_score=latest.get(uid),
            readiness=band(latest.get(uid)),
            days_since_activity=(now - last_dt).days if last_dt else None,
            flagged=uid in flagged,
        ))
    return results


@router.get("/export-results")
async def export_results_csv(principal: Principal, models: TenantModels):
    """Export all student results as CSV for the tenant admin."""
    import csv
    import io
    from fastapi.responses import Response as HttpResponse
    from app.db import control_db
    db = control_db()

    users_docs = await db.users.find({
        "tenant_id": principal.tenant_id, "role": "student"
    }).to_list()
    user_ids = [u["_id"] for u in users_docs]
    user_map = {u["_id"]: u for u in users_docs}

    latest = {}
    score_docs = await db.score_records.find({
        "user_id": {"$in": user_ids}, "dimension": "overall", "is_shadow": {"$ne": True}
    }).sort("created_at", -1).to_list()
    for s in score_docs:
        uid = s.get("user_id")
        if uid and uid not in latest:
            latest[uid] = s.get("score")

    attempt_count = {}
    attempt_docs = await db.attempts.find({"user_id": {"$in": user_ids}}).to_list()
    for a in attempt_docs:
        uid = a.get("user_id")
        if uid:
            attempt_count[uid] = attempt_count.get(uid, 0) + 1

    member_docs = await db.cohort_members.find({"user_id": {"$in": user_ids}}).to_list()
    user_cohorts: dict[str, list[str]] = {}
    for m in member_docs:
        uid, cid = m.get("user_id"), m.get("cohort_id")
        if uid and cid:
            user_cohorts.setdefault(uid, []).append(cid)
    cohort_ids = list({cid for cids in user_cohorts.values() for cid in cids})
    cohort_names: dict[str, str] = {}
    if cohort_ids:
        cohorts_db = await db.cohorts.find({"_id": {"$in": cohort_ids}}).to_list()
        cohort_names = {c["_id"]: c.get("name", "") for c in cohorts_db}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Email", "Roll Number", "Branch",
                     "Cohort", "Total Attempts", "Best Score", "Readiness"])
    for uid in user_ids:
        u = user_map.get(uid, {})
        sc = latest.get(uid)
        cohort_list = user_cohorts.get(uid, [])
        cohort_str = ", ".join(cohort_names.get(c, c) for c in cohort_list) if cohort_list else "---"
        writer.writerow([
            u.get("full_name", ""), u.get("email", ""),
            u.get("roll_number", ""), u.get("branch", ""),
            cohort_str, attempt_count.get(uid, 0),
            sc if sc is not None else "---", band(sc),
        ])
    content = output.getvalue().encode("utf-8")
    return HttpResponse(
        content=content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="student-results.csv"'},
    )
