"""Trainer tooling that writes: at-risk flags, and the momentum view.

Split from the read-only trainer router because the rule that matters here is
different. Nothing in this file is visible to a student and nothing in it
sends them anything: a flag is a note to staff (TRN-03), and the momentum
view produces a *suggestion to the trainer* rather than an automatic message
to the person it is about (TRN-06). Making that a file boundary makes it hard
to get wrong later.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status
from beanie.operators import In

from app import audit
from app.deps import Principal, TenantModels, require_roles
from app.routers.trainer import _latest_overall, _visible_cohorts
from app.schemas import FlagOut, FlagRequest, MomentumRow

router = APIRouter(prefix="/trainer", tags=["trainer"],
                   dependencies=[Depends(require_roles("trainer", "tenant_admin"))])

# A student who has gone quiet this long, with a drive this close, is worth a
# trainer's attention. Both halves matter: silence in week one of a ninety-day
# season is not the same fact as silence three weeks out.
DARK_DAYS = 5
DRIVE_WINDOW_DAYS = 45


async def _students_in_scope(models: SimpleNamespace,
                             principal: Principal) -> list[str]:
    cohorts = [c.id for c in await _visible_cohorts(models, principal)]
    members = await models.CohortMember.find(
        In(models.CohortMember.cohort_id, cohorts or [""])).to_list()
    return [m.user_id for m in members]


@router.get("/flags", response_model=list[FlagOut])
async def flags(principal: Principal, models: TenantModels,
                include_resolved: bool = False) -> list[FlagOut]:
    member_ids = await _students_in_scope(models, principal)

    conditions = [In(models.StudentFlag.user_id, member_ids or [""])]
    if not include_resolved:
        conditions.append(models.StudentFlag.resolved == False)
    rows = await models.StudentFlag.find(*conditions).sort(
        -models.StudentFlag.created_at).to_list()

    names = {u.id: u.full_name for u in await models.User.all().to_list()}
    return [
        FlagOut(
            id=f.id, user_id=f.user_id, student_name=names.get(f.user_id, ""),
            reason=f.reason, note=f.note, auto_suggested=f.auto_suggested,
            resolved=f.resolved, raised_by_name=names.get(f.raised_by, "system"),
            created_at=f.created_at,
        )
        for f in rows
    ]


@router.post("/flags", response_model=FlagOut, status_code=status.HTTP_201_CREATED)
async def raise_flag(body: FlagRequest, principal: Principal,
                     models: TenantModels) -> FlagOut:
    if body.user_id not in await _students_in_scope(models, principal):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not in your cohorts")

    student = await models.User.get(body.user_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Student not found")

    flag = models.StudentFlag(user_id=body.user_id, raised_by=principal.user_id,
                              reason=body.reason, note=body.note)
    await flag.create()

    await audit.record(principal, "student.flagged", entity="StudentFlag",
                       entity_id=flag.id, after={"reason": body.reason})

    raiser = await models.User.get(principal.user_id)
    return FlagOut(
        id=flag.id, user_id=flag.user_id, student_name=student.full_name,
        reason=flag.reason, note=flag.note, auto_suggested=False, resolved=False,
        raised_by_name=raiser.full_name if raiser else "",
        created_at=flag.created_at,
    )


@router.post("/flags/{flag_id}/resolve")
async def resolve_flag(flag_id: str, principal: Principal,
                       models: TenantModels) -> dict:
    flag = await models.StudentFlag.get(flag_id)
    if flag is None or flag.user_id not in await _students_in_scope(models, principal):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Flag not found")

    flag.resolved = True
    flag.resolved_at = datetime.now(timezone.utc)
    await flag.save()
    await audit.record(principal, "student.flag_resolved", entity="StudentFlag",
                       entity_id=flag_id)
    return {"resolved": True}


@router.get("/momentum", response_model=list[MomentumRow])
async def momentum(principal: Principal,
                   models: TenantModels) -> list[MomentumRow]:
    """Who is practising, and who has gone dark with a drive approaching."""
    cohorts = await _visible_cohorts(models, principal)
    cohort_names = {c.id: c.name for c in cohorts}
    drive_dates = {c.id: c.drive_start for c in cohorts}

    members = await models.CohortMember.find(
        In(models.CohortMember.cohort_id,
           [c.id for c in cohorts] or [""])).to_list()
    cohort_of = {m.user_id: m.cohort_id for m in members}
    user_ids = list(cohort_of)

    users = {u.id: u for u in await models.User.find(
        In(models.User.id, user_ids or [""]),
        models.User.role == "student").to_list()}

    coll = models.Attempt.get_motor_collection()
    activity_docs = await coll.aggregate([
        {"$match": {"user_id": {"$in": user_ids or [""]}}},
        {"$group": {"_id": "$user_id", "count": {"$sum": 1},
                    "last": {"$max": "$created_at"}}},
    ]).to_list(None)
    activity = {doc["_id"]: (doc["count"], doc["last"]) for doc in activity_docs}

    streaks = {s.user_id: s.current_streak for s in await models.StreakState.all().to_list()}
    latest = await _latest_overall(models, user_ids)
    flagged = {f.user_id for f in await models.StudentFlag.find(
        models.StudentFlag.resolved == False).to_list()}

    now = datetime.now(timezone.utc)
    today = date.today()
    rows: list[MomentumRow] = []

    for user_id, user in users.items():
        cohort_id = cohort_of.get(user_id, "")
        drive = drive_dates.get(cohort_id)
        days_to_drive = (drive.date() - today).days if drive else None

        count, last = activity.get(user_id, (0, None))
        dark_days = (now - last).days if last else None
        approaching = days_to_drive is not None and days_to_drive < DRIVE_WINDOW_DAYS

        suggest = False
        suggestion = ""
        if user_id not in flagged and approaching:
            if last is None:
                suggest = True
                suggestion = (f"Has never attempted a simulation, with "
                              f"{days_to_drive} days to the drive.")
            elif dark_days is not None and dark_days >= DARK_DAYS:
                suggest = True
                suggestion = (f"No practice for {dark_days} days, with "
                              f"{days_to_drive} days to the drive.")

        rows.append(MomentumRow(
            user_id=user_id, full_name=user.full_name,
            cohort_name=cohort_names.get(cohort_id, ""),
            days_since_activity=dark_days, attempts=count,
            current_streak=streaks.get(user_id, 0),
            days_to_drive=days_to_drive, overall_score=latest.get(user_id),
            suggest_flag=suggest, suggestion=suggestion,
            flagged=user_id in flagged,
        ))

    # The ones needing attention first — that is the whole point of the screen.
    rows.sort(key=lambda r: (not r.suggest_flag, -(r.days_since_activity or 999)))
    return rows
