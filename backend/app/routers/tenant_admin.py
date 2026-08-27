"""Institution console â€” the tenant admin's own view of their institution.

Every query runs against the caller's own institution database. There is no
institution identifier in any signature here, because there is nowhere else
to look.
"""
from __future__ import annotations

from datetime import date

from beanie.operators import In, NE
from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import Principal, TenantModels, require_roles
from app.models.platform import Tenant
from app.schemas import (CohortOut, ProfileSectionOut, SimulationProfileOut,
                         TenantOverview, UserOut)

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
    trainer_rows = await models.User.find(models.User.role == "trainer").to_list()
    trainers = {u.id: u.full_name for u in trainer_rows}
    return [
        CohortOut(
            id=c.id, name=c.name, branch=c.branch, year_of_study=c.year_of_study,
            section=c.section, trainer_id=c.trainer_id,
            trainer_name=trainers.get(c.trainer_id or "", ""),
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
