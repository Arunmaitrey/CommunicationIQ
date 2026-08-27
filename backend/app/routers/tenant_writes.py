"""Institution console â€” the write half.

Everything here runs against the caller's own schema and is audit-logged.
Three rules the endpoints enforce rather than trust the UI for:

* **Seats are a hard limit.** An import that would exceed the plan is refused
  in full rather than truncated â€” a half-imported cohort is worse than a
  clear "you need twelve more seats".
* **Nothing is silently overwritten.** An import row for an existing email
  updates profile fields and never a password, a role, or a history.
* **Trainers cannot reach this file.** Every route is tenant_admin only.
"""
from __future__ import annotations

import re
import secrets
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app import audit, formats
from app import deadline as app_deadline
from app import selection as app_selection
from app.db import ensure_tenant_models
from app.deps import Principal, TenantModels, require_roles
from app.importer import ImportPlan, parse
from app.models.platform import Tenant, TenantUserDirectory
from app.models.tenant import (Assignment, Attempt, Cohort, CohortMember,
                               ProfileSection, SimulationProfile, TaskItem,
                               User)
from app.schemas import (AssignmentOut, AssignmentRequest, CohortMembersRequest,
                         CohortOut, CohortRequest, CreateUserRequest,
                         ImportPreview, ImportProblemOut, ImportRequest,
                         ImportResult, ProfileRequest, ProfileSectionOut,
                         ProfileSectionRequest, ProfileStatusRequest,
                         SeatUsage, SimulationProfileOut, UpdateUserRequest,
                         UserOut)
from app.security import hash_password

router = APIRouter(prefix="/tenant", tags=["tenant-admin"],
                   dependencies=[Depends(require_roles("tenant_admin"))])

ALPHABET = string.ascii_letters + string.digits


async def link_to_directory(emails: list[str], tenant_id: str, slug: str) -> None:
    """Point sign-in at this institution for these emails, idempotently.

    Inserting blind looked fine until an email survived in the directory after
    its account was removed: the next import wrote every user, committed, then
    hit a unique-key violation here â€” a partial import, which is the one thing
    the endpoint promises cannot happen. So it inserts only what is missing,
    and repoints a row that names a different institution.
    """
    if not emails:
        return
    existing = {
        row.email: row for row in await TenantUserDirectory.find(
            TenantUserDirectory.email.in_(emails)).to_list()
    }
    for email in emails:
        row = existing.get(email)
        if row is None:
            await TenantUserDirectory(email=email, tenant_id=tenant_id,
                                       tenant_slug=slug).create()
        elif row.tenant_slug != slug:
            row.tenant_id = tenant_id
            row.tenant_slug = slug
            row.active = True
            await row.save()
        else:
            row.active = True
            await row.save()


def temporary_password() -> str:
    """A first password the student is forced to change.

    Random, not derived from anything about the person: a scheme like
    name+rollnumber is guessable for the whole cohort at once.
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(12))


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=getattr(u, 'id', ''), email=getattr(u, 'email', ''), full_name=getattr(u, 'full_name', ''),
        role=getattr(u, 'role', 'student'), active=getattr(u, 'active', True),
        roll_number=getattr(u, 'roll_number', ''), branch=getattr(u, 'branch', ''),
        year_of_study=getattr(u, 'year_of_study', None),
        l1_language=getattr(u, 'l1_language', ''), created_at=getattr(u, 'created_at', None),
    )


async def _seat_usage(models: TenantModels, tenant_id: str) -> SeatUsage:
    role_docs = await models.User.get_motor_collection().aggregate([
        {"$match": {"active": True}},
        {"$group": {"_id": "$role", "n": {"$sum": 1}}},
    ]).to_list(None)
    counts = {d["_id"]: int(d["n"]) for d in role_docs}
    tenant = await Tenant.get(tenant_id)
    limit = tenant.seat_limit if tenant else 0
    used = sum(counts.values())
    return SeatUsage(
        used=used, limit=limit,
        students=counts.get("student", 0),
        trainers=counts.get("trainer", 0),
        admins=counts.get("tenant_admin", 0),
        remaining=max(0, limit - used),
    )


@router.get("/seats", response_model=SeatUsage)
async def seats(principal: Principal, models: TenantModels) -> SeatUsage:
    return await _seat_usage(models, principal.tenant_id or "")


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------

async def _plan_for(models: TenantModels, csv_text: str) -> ImportPlan:
    plan = parse(csv_text)
    if plan.rows:
        emails = [r.email for r in plan.rows]
        users = await models.User.find(
            models.User.email.in_(emails)).to_list()
        plan.existing = {u.email for u in users}
    return plan


@router.post("/users/import/preview", response_model=ImportPreview)
async def preview_import(body: ImportRequest, principal: Principal,
                         models: TenantModels) -> ImportPreview:
    """Say exactly what would happen, before anything happens.

    Every problem at once, not the first one â€” an admin fixing a spreadsheet
    one error per upload will give up before row twenty.
    """
    plan = await _plan_for(models, body.csv_text)
    usage = await _seat_usage(models, principal.tenant_id or "")
    seats_after = usage.used + plan.creating

    return ImportPreview(
        ok=plan.ok and seats_after <= usage.limit,
        total=len(plan.rows),
        creating=plan.creating,
        updating=plan.updating,
        seats_after=seats_after,
        seat_limit=usage.limit,
        over_seat_limit=seats_after > usage.limit,
        problems=[ImportProblemOut(line=p.line, column=p.column, message=p.message)
                  for p in plan.problems[:50]],
        sample=[{"email": r.email, "full_name": r.full_name, "role": r.role,
                 "roll_number": r.roll_number, "branch": r.branch,
                 "cohort": r.cohort,
                 "action": "update" if r.email in plan.existing else "create"}
                for r in plan.rows[:10]],
    )


@router.post("/users/import", response_model=ImportResult)
async def commit_import(body: ImportRequest, principal: Principal,
                        models: TenantModels) -> ImportResult:
    plan = await _plan_for(models, body.csv_text)
    if not plan.ok:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{len(plan.problems)} problem(s) in the file â€” run the preview to see them")

    usage = await _seat_usage(models, principal.tenant_id or "")
    if usage.used + plan.creating > usage.limit:
        needed = usage.used + plan.creating - usage.limit
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This import needs {needed} more seat(s) than the plan allows. "
            f"Nothing was imported.")

    cohorts = {c.name.lower(): c for c in await models.Cohort.find_all().to_list()}
    created_cohorts: list[str] = []
    passwords: dict[str, str] = {}
    created = 0
    updated = 0

    for row in plan.rows:
        cohort = None
        if row.cohort:
            cohort = cohorts.get(row.cohort.lower())
            if cohort is None and body.create_missing_cohorts:
                cohort = Cohort(name=row.cohort, branch=row.branch,
                                year_of_study=row.year_of_study)
                await cohort.create()
                cohorts[row.cohort.lower()] = cohort
                created_cohorts.append(row.cohort)

        existing = await models.User.find_one(
            models.User.email == row.email)

        if existing is not None:
            existing.full_name = row.full_name or existing.full_name
            existing.roll_number = row.roll_number or existing.roll_number
            existing.branch = row.branch or existing.branch
            existing.year_of_study = row.year_of_study or existing.year_of_study
            existing.l1_language = row.l1_language or existing.l1_language
            user = existing
            updated += 1
        else:
            password = temporary_password()
            user = User(
                email=row.email, full_name=row.full_name, role=row.role,
                password_hash=hash_password(password), must_change_password=True,
                roll_number=row.roll_number, branch=row.branch,
                year_of_study=row.year_of_study, l1_language=row.l1_language,
            )
            await user.create()
            passwords[row.email] = password
            created += 1

        if cohort is not None:
            member = await models.CohortMember.find_one(
                models.CohortMember.cohort_id == cohort.id,
                models.CohortMember.user_id == user.id)
            if member is None:
                await CohortMember(cohort_id=cohort.id, user_id=user.id).create()

    await link_to_directory(list(passwords), principal.tenant_id or "",
                            principal.tenant_slug or "")

    await audit.record(principal, "users.imported", entity="User",
                       after={"created": created, "updated": updated,
                              "cohorts_created": created_cohorts})

    return ImportResult(created=created, updated=updated,
                        cohorts_created=created_cohorts,
                        temporary_passwords=passwords)


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------

@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: CreateUserRequest, principal: Principal,
                      models: TenantModels) -> UserOut:
    email = body.email.lower().strip()

    if await models.User.find_one(models.User.email == email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already in use")

    usage = await _seat_usage(models, principal.tenant_id or "")
    if usage.used >= usage.limit:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "No seats remaining on the current plan")

    password = temporary_password()
    user = User(email=email, full_name=body.full_name, role=body.role,
                password_hash=hash_password(password), must_change_password=True,
                roll_number=body.roll_number, branch=body.branch,
                year_of_study=body.year_of_study, l1_language=body.l1_language)
    await user.create()

    if body.cohort_id:
        await CohortMember(cohort_id=body.cohort_id, user_id=user.id).create()

    await link_to_directory([email], principal.tenant_id or "",
                            principal.tenant_slug or "")

    await audit.record(principal, "user.created", entity="User", entity_id=user.id,
                       after={"email": email, "role": body.role})

    out = _user_out(user)
    return out


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: str, body: UpdateUserRequest, principal: Principal,
                      models: TenantModels) -> UserOut:
    user = await models.User.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    before = {"active": user.active, "role": user.role, "full_name": user.full_name}

    if body.active is not None:
        if not body.active and user.id == principal.user_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "You cannot deactivate your own account")
        user.active = body.active
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.branch is not None:
        user.branch = body.branch
    if body.l1_language is not None:
        user.l1_language = body.l1_language
    if body.role is not None:
        if body.role not in {"student", "tenant_admin"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown role")
        if user.id == principal.user_id and body.role != "tenant_admin":
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "You cannot remove your own admin role")
        user.role = body.role

    await user.save()
    await audit.record(principal, "user.updated", entity="User", entity_id=user.id,
                       before=before,
                       after={"active": user.active, "role": user.role,
                              "full_name": user.full_name})
    return _user_out(user)


@router.post("/users/{user_id}/reset-password")
async def reset_password(user_id: str, principal: Principal,
                         models: TenantModels) -> dict:
    """Issue a new temporary password. Shown once, to the admin who asked."""
    user = await models.User.get(user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    password = temporary_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    await user.save()

    await audit.record(principal, "user.password_reset", entity="User",
                       entity_id=user.id)
    return {"email": user.email, "temporary_password": password}


# --------------------------------------------------------------------------
# Cohorts
# --------------------------------------------------------------------------

@router.post("/cohorts", response_model=CohortOut, status_code=status.HTTP_201_CREATED)
async def create_cohort(body: CohortRequest, principal: Principal,
                        models: TenantModels) -> CohortOut:
    cohort = Cohort(name=body.name, branch=body.branch,
                    year_of_study=body.year_of_study, section=body.section,
                    trainer_id=body.trainer_id, drive_start=body.drive_start,
                    drive_end=body.drive_end)
    await cohort.create()

    await audit.record(principal, "cohort.created", entity="Cohort",
                       entity_id=cohort.id, after={"name": cohort.name})
    return CohortOut(
        id=cohort.id, name=cohort.name, branch=cohort.branch,
        year_of_study=cohort.year_of_study, section=cohort.section,
        trainer_id=cohort.trainer_id, trainer_name="",
        drive_start=cohort.drive_start, drive_end=cohort.drive_end,
        member_count=0, active=cohort.active,
    )


@router.patch("/cohorts/{cohort_id}", response_model=CohortOut)
async def update_cohort(cohort_id: str, body: CohortRequest, principal: Principal,
                        models: TenantModels) -> CohortOut:
    """Change a cohort â€” including the drive date every countdown derives from.

    Moving the date re-plans the season, so it is audit-logged with both
    values: "why did my plan change last Tuesday" needs an answer.
    """
    cohort = await models.Cohort.get(cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cohort not found")

    before = {"name": cohort.name, "trainer_id": cohort.trainer_id,
              "drive_start": cohort.drive_start.isoformat() if cohort.drive_start else None}

    cohort.name = body.name or cohort.name
    cohort.branch = body.branch
    cohort.year_of_study = body.year_of_study
    cohort.section = body.section
    cohort.trainer_id = body.trainer_id
    cohort.drive_start = body.drive_start
    cohort.drive_end = body.drive_end
    await cohort.save()

    count = await models.CohortMember.find(
        models.CohortMember.cohort_id == cohort.id).count()
    trainer = await models.User.get(cohort.trainer_id) if cohort.trainer_id else None

    await audit.record(principal, "cohort.updated", entity="Cohort",
                       entity_id=cohort.id, before=before,
                       after={"name": cohort.name, "trainer_id": cohort.trainer_id,
                              "drive_start": cohort.drive_start.isoformat()
                              if cohort.drive_start else None})

    return CohortOut(
        id=cohort.id, name=cohort.name, branch=cohort.branch,
        year_of_study=cohort.year_of_study, section=cohort.section,
        trainer_id=cohort.trainer_id,
        trainer_name=trainer.full_name if trainer else "",
        drive_start=cohort.drive_start, drive_end=cohort.drive_end,
        member_count=int(count), active=cohort.active,
    )


@router.post("/cohorts/{cohort_id}/members")
async def update_members(cohort_id: str, body: CohortMembersRequest,
                         principal: Principal, models: TenantModels) -> dict:
    cohort = await models.Cohort.get(cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cohort not found")

    added = 0
    for user_id in body.add:
        exists = await models.CohortMember.find_one(
            models.CohortMember.cohort_id == cohort_id,
            models.CohortMember.user_id == user_id)
        if exists is None and await models.User.get(user_id) is not None:
            await CohortMember(cohort_id=cohort_id, user_id=user_id).create()
            added += 1

    removed = 0
    for user_id in body.remove:
        member = await models.CohortMember.find_one(
            models.CohortMember.cohort_id == cohort_id,
            models.CohortMember.user_id == user_id)
        if member is not None:
            await member.delete()
            removed += 1

    await audit.record(principal, "cohort.members_changed", entity="Cohort",
                       entity_id=cohort_id,
                       after={"added": added, "removed": removed})
    return {"added": added, "removed": removed}


# --------------------------------------------------------------------------
# Assignments
# --------------------------------------------------------------------------

@router.get("/assignments", response_model=list[AssignmentOut])
async def assignments(models: TenantModels) -> list[AssignmentOut]:
    rows = await models.Assignment.find_all().sort(
        "-created_at").to_list()

    cohorts = {c.id: c for c in await models.Cohort.find_all().to_list()}
    profiles = {p.id: p for p in await models.SimulationProfile.find_all().to_list()}

    member_counts = {doc["_id"]: doc["count"] async for doc in models.CohortMember.get_motor_collection().aggregate([
        {"$group": {"_id": "$cohort_id", "count": {"$sum": 1}}},
    ])}

    out: list[AssignmentOut] = []
    for a in rows:
        completed = await models.Attempt.find(
            models.Attempt.assignment_id == a.id,
            models.Attempt.status == "scored").count()
        cohort = cohorts.get(a.cohort_id)
        profile = profiles.get(a.profile_id)
        out.append(AssignmentOut(
            id=a.id, cohort_id=a.cohort_id,
            cohort_name=cohort.name if cohort else "",
            profile_id=a.profile_id,
            profile_name=profile.name if profile else "",
            mandatory=a.mandatory, opens_at=a.opens_at, due_at=a.due_at,
            max_attempts=a.max_attempts, completed=int(completed),
            total=member_counts.get(a.cohort_id, 0),
        ))
    return out


@router.post("/assignments", response_model=AssignmentOut,
             status_code=status.HTTP_201_CREATED)
async def create_assignment(body: AssignmentRequest, principal: Principal,
                            models: TenantModels) -> AssignmentOut:
    cohort = await models.Cohort.get(body.cohort_id)
    profile = await models.SimulationProfile.get(body.profile_id)
    if cohort is None or profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cohort or simulation not found")
    if profile.status != "published":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "A draft simulation cannot be assigned")
    if body.due_at and body.opens_at and body.due_at <= body.opens_at:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The deadline must be after the opening date")
    if body.due_at and body.due_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "That deadline is in the past")

    assignment = Assignment(
        cohort_id=body.cohort_id, profile_id=body.profile_id,
        assigned_by=principal.user_id, mandatory=body.mandatory,
        opens_at=body.opens_at, due_at=body.due_at, max_attempts=body.max_attempts)
    await assignment.create()

    count = await models.CohortMember.find(
        models.CohortMember.cohort_id == cohort.id).count()

    await audit.record(principal, "assignment.created", entity="Assignment",
                       entity_id=assignment.id,
                       after={"cohort": cohort.name, "profile": profile.name,
                              "due_at": body.due_at.isoformat() if body.due_at else None})

    return AssignmentOut(
        id=assignment.id, cohort_id=cohort.id, cohort_name=cohort.name,
        profile_id=profile.id, profile_name=profile.name,
        mandatory=assignment.mandatory, opens_at=assignment.opens_at,
        due_at=assignment.due_at, max_attempts=assignment.max_attempts,
        completed=0, total=int(count),
    )


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_200_OK)
async def delete_assignment(assignment_id: str, principal: Principal,
                            models: TenantModels) -> dict:
    assignment = await models.Assignment.get(assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assignment not found")

    taken = await models.Attempt.find(
        models.Attempt.assignment_id == assignment_id).count()
    if taken:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{taken} student(s) have already attempted this. It cannot be deleted.")

    await assignment.delete()
    await audit.record(principal, "assignment.deleted", entity="Assignment",
                       entity_id=assignment_id)
    return {"deleted": True}


# --------------------------------------------------------------------------
# Simulation profiles - the builder
# --------------------------------------------------------------------------
#
# Company rounds are the reason this exists. Every college chases a different
# set of recruiters, so the rounds a student should be practising cannot be
# decided centrally and shipped: the seeded five are a starting point that an
# admin is expected to edit, clone and add to.
#
# Two rules the endpoints enforce rather than trust the console for:
#
# * **A published profile has sections.** Publishing an empty profile hands
#   students a test with no questions, which fails silently at the far end as
#   an attempt containing nothing. Refused here.
# * **A profile with attempts against it is not edited in place.** Changing
#   the sections under a scored attempt makes that attempt a measurement of
#   something that no longer exists. Clone instead; the endpoint says so.
#


def _profile_payload(profile: SimulationProfile) -> SimulationProfileOut:
    blueprint = formats.BY_CODE.get(profile.code)
    budgets = formats.section_budgets(profile.code)
    return SimulationProfileOut(
        id=profile.id, code=profile.code, name=profile.name, style=profile.style,
        company=profile.company, description=profile.description,
        status=profile.status, estimated_minutes=profile.estimated_minutes,
        is_baseline=profile.is_baseline,
        typical_minutes=(formats.typical_minutes(blueprint) if blueprint
                         else profile.estimated_minutes),
        sitting_limit_minutes=app_deadline.allowance_minutes(profile.estimated_minutes),
        # The scoring configuration, so it can be read back and edited.
        scoring_weights=dict(profile.scoring_weights or {}),
        pass_threshold=profile.pass_threshold,
        skill_thresholds=dict(profile.skill_thresholds or {}),
        target_role=profile.target_role, department=profile.department,
        difficulty_band=profile.difficulty_band,
        what_to_expect=list(blueprint.what_to_expect) if blueprint else [],
        not_included=blueprint.not_included if blueprint else "",
        provenance=blueprint.provenance if blueprint else "",
        sections=[
            ProfileSectionOut(
                id=x.id, position=x.position, title=x.title, task_type=x.task_type,
                instructions=x.instructions, item_count=x.item_count,
                prep_seconds=x.prep_seconds, response_seconds=x.response_seconds,
                prompt_plays_allowed=x.prompt_plays_allowed,
                allow_replay=x.allow_replay,
                budget_seconds=budgets.get(x.title, 0),
                weight=x.weight,
                selection=dict(x.selection or {}),
            )
            for x in sorted(profile.sections, key=lambda x: x.position)
        ],
    )


async def _load_profile(models: TenantModels, profile_id: str) -> SimulationProfile:
    profile = await models.SimulationProfile.get(profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return profile


async def _attempt_count(models: TenantModels, profile_id: str) -> int:
    return await models.Attempt.find(
        models.Attempt.profile_id == profile_id).count()


def _unique_code(name: str, style: str, taken: set[str]) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", f"{style}_{name}".lower()).strip("_")[:50]
    code = stem or "profile"
    n = 2
    while code in taken:
        code = f"{stem[:46]}_{n}"
        n += 1
    return code


async def _apply_sections(models: TenantModels, profile: SimulationProfile,
                          sections: list[ProfileSectionRequest]) -> None:
    for existing in list(profile.sections):
        await existing.delete()
    profile.sections.clear()
    for position, section in enumerate(sections, start=1):
        profile.sections.append(ProfileSection(
            position=position, title=section.title, task_type=section.task_type,
            instructions=section.instructions, item_count=section.item_count,
            prep_seconds=section.prep_seconds,
            response_seconds=section.response_seconds,
            prompt_plays_allowed=section.prompt_plays_allowed,
            allow_replay=section.allow_replay,
            weight=section.weight,
            # Stored through `selection.to_dict` so an unconfigured section
            # stores {} rather than a dict of nulls -- which is what makes
            # "was this configured?" answerable later.
            selection=app_selection.to_dict(
                app_selection.from_dict(section.selection.model_dump())),
        ))


@router.post("/profiles", response_model=SimulationProfileOut,
             status_code=status.HTTP_201_CREATED)
async def create_profile(body: ProfileRequest, principal: Principal,
                         models: TenantModels) -> SimulationProfileOut:
    """Author a new round. Always created as a draft."""
    taken = {p.code for p in await models.SimulationProfile.find_all().to_list()}
    profile = SimulationProfile(
        code=_unique_code(body.name, body.style, taken),
        name=body.name, style=body.style,
        company=body.company if body.style == "company_round" else "",
        description=body.description, status="draft",
        estimated_minutes=body.estimated_minutes,
        # The scoring configuration a company round needs. Empty weights mean
        # "use the engine default", which keeps every existing profile
        # behaving exactly as before.
        scoring_weights=dict(body.scoring_weights or {}),
        pass_threshold=body.pass_threshold,
        skill_thresholds=dict(body.skill_thresholds or {}),
        target_role=body.target_role, department=body.department,
        difficulty_band=body.difficulty_band,
    )
    await profile.create()
    await _apply_sections(models, profile, body.sections)

    profile = await _load_profile(models, profile.id)
    await audit.record(principal, "profile.created", entity="SimulationProfile",
                       entity_id=profile.id,
                       after={"name": profile.name, "style": profile.style,
                              "company": profile.company})
    return _profile_payload(profile)


@router.post("/profiles/{profile_id}/clone", response_model=SimulationProfileOut,
             status_code=status.HTTP_201_CREATED)
async def clone_profile(profile_id: str, principal: Principal,
                        models: TenantModels) -> SimulationProfileOut:
    """Copy a profile, sections and all, as a fresh draft.

    The supported way to change a round that students have already taken.
    """
    source = await _load_profile(models, profile_id)
    taken = {p.code for p in await models.SimulationProfile.find_all().to_list()}
    copy = SimulationProfile(
        code=_unique_code(f"{source.name} copy", source.style, taken),
        name=f"{source.name} (copy)", style=source.style, company=source.company,
        description=source.description, status="draft",
        estimated_minutes=source.estimated_minutes,
        score_scale=dict(source.score_scale or {}),
        # Every configured value, not just the weights.
        #
        # This copied `scoring_weights` alone, so cloning a hiring round --
        # the supported way to edit one students have already taken -- dropped
        # its pass mark, its per-dimension floors and its classification. The
        # copy passed everybody, and looked like the original until somebody
        # read the report.
        scoring_weights=dict(source.scoring_weights or {}),
        pass_threshold=source.pass_threshold,
        skill_thresholds=dict(source.skill_thresholds or {}),
        target_role=source.target_role,
        department=source.department,
        difficulty_band=source.difficulty_band,
    )
    await copy.create()
    for section in sorted(source.sections, key=lambda x: x.position):
        copy.sections.append(ProfileSection(
            position=section.position, title=section.title,
            task_type=section.task_type, instructions=section.instructions,
            item_count=section.item_count, prep_seconds=section.prep_seconds,
            response_seconds=section.response_seconds,
            prompt_plays_allowed=section.prompt_plays_allowed,
            allow_replay=section.allow_replay,
            weight=section.weight,
            selection=dict(section.selection or {}),
        ))
    await copy.save()

    copy = await _load_profile(models, copy.id)
    await audit.record(principal, "profile.cloned", entity="SimulationProfile",
                       entity_id=copy.id, before={"from": source.id},
                       after={"name": copy.name})
    return _profile_payload(copy)


@router.put("/profiles/{profile_id}", response_model=SimulationProfileOut)
async def replace_profile(profile_id: str, body: ProfileRequest,
                          principal: Principal,
                          models: TenantModels) -> SimulationProfileOut:
    """Replace a profile's details and its whole section list.

    Refused once anything has been attempted against it. A scored attempt
    names the profile it was taken under; if the sections can change
    afterwards, that name stops meaning anything and every comparison built on
    it is quietly wrong.
    """
    profile = await _load_profile(models, profile_id)
    attempts = await _attempt_count(models, profile_id)
    if attempts:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{attempts} attempt(s) have been taken under this profile, so its "
            "sections cannot change. Clone it and edit the copy.",
        )

    before = {"name": profile.name, "sections": len(profile.sections)}
    profile.name = body.name
    profile.style = body.style
    profile.company = body.company if body.style == "company_round" else ""
    profile.description = body.description
    profile.estimated_minutes = body.estimated_minutes
    profile.scoring_weights = dict(body.scoring_weights or {})
    profile.pass_threshold = body.pass_threshold
    profile.skill_thresholds = dict(body.skill_thresholds or {})
    profile.target_role = body.target_role
    profile.department = body.department
    profile.difficulty_band = body.difficulty_band
    await _apply_sections(models, profile, body.sections)
    await profile.save()

    profile = await _load_profile(models, profile_id)
    await audit.record(principal, "profile.updated", entity="SimulationProfile",
                       entity_id=profile.id, before=before,
                       after={"name": profile.name,
                              "sections": len(profile.sections)})
    return _profile_payload(profile)


async def _sections_without_items(models: TenantModels,
                                  profile: SimulationProfile) -> list[str]:
    """Sections the runner could not fill, and why.

    ``_pick_items`` returns an empty list when the bank has nothing of a
    section's task type, and ``start_attempt`` skips such a section without
    comment. The result is a test quietly shorter than the one the admin
    designed -- and, because the composite is built from whatever was
    measured, a score built on a different basis than intended. Catching it at
    publish time is the only place it is cheap.

    Two ways a section comes up empty: a task type the item bank has never
    held (``mcq`` and ``audio_comprehension`` live in the quiz engine, not
    here), or one that simply has no published items yet.
    """
    from app.models.tenant import QuizItem, WritingPrompt
    from app.sections import (fill_from_passages, groups_by_passage,
                              prompt_kinds_for, source_of)

    # Ask the same question the runner asks: given this section, how many
    # items would it actually get?
    #
    # This branched on the response mode and looked everything non-spoken up
    # in the quiz bank. Dictation is typed and draws on the spoken sentence
    # bank, so the guard went looking for "dictation questions", found none,
    # and refused a section the runner would have filled perfectly well. The
    # selector had already been taught where each bank lives; the guard had
    # not, and two places encoding the same knowledge is how one of them ends
    # up stale.
    task_counts = {doc["_id"]: doc["count"] async for doc in models.TaskItem.get_motor_collection().aggregate([
        {"$match": {"status": "published"}},
        {"$group": {"_id": "$task_type", "count": {"$sum": 1}}},
    ])}
    quiz_counts = {doc["_id"]: doc["count"] async for doc in models.QuizItem.get_motor_collection().aggregate([
        {"$match": {"status": "published"}},
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
    ])}
    # Per kind, not one total. A reconstruction passage and an email brief
    # live in the same table and are not interchangeable, so counting them
    # together would pass a Passage Reconstruction section on the strength of
    # six email prompts the runner would never serve it.
    prompt_counts = {doc["_id"]: doc["count"] async for doc in models.WritingPrompt.get_motor_collection().aggregate([
        {"$match": {"status": "published"}},
        {"$group": {"_id": "$kind", "count": {"$sum": 1}}},
    ])}

    problems: list[str] = []
    for section in sorted(profile.sections, key=lambda x: x.position):
        kind, key = source_of(section.task_type)

        # A configured filter changes what "the bank" means for this section.
        #
        # Counting the whole bank would pass a section whose filter matches
        # nothing -- which is the same silent-truncation fault this guard was
        # built for, arriving through a new door. Counted per section rather
        # than once, because two sections of the same task type can filter
        # differently.
        try:
            pool_filter = app_selection.from_dict(section.selection)
        except (ValueError, TypeError) as exc:
            problems.append(f"{section.title!r} has an unusable filter: {exc}")
            continue

        unsupported = pool_filter.unsupported_for(kind)
        if unsupported:
            problems.append(
                f"{section.title!r} filters on {', '.join(unsupported)}, which "
                f"the {kind} bank does not carry")
            continue

        if kind == "task":
            items = await models.TaskItem.find(
                models.TaskItem.task_type == key,
                models.TaskItem.status == "published").to_list()
            available = len(app_selection.eligible(items, pool_filter, "task"))
            reachable = min(available, section.item_count)
            bank = (f"{key} items matching the filter" if pool_filter.configured
                    else f"{key} items")
        elif kind == "writing_prompt":
            allowed = prompt_kinds_for(key)
            available = sum(n for k, n in prompt_counts.items() if k in allowed)
            reachable = min(available, section.item_count)
            bank = f"{key} passages" if key else "writing prompts"
        else:
            available = quiz_counts.get(key, 0)
            bank = f"{key} questions"
            if groups_by_passage(key):
                # Comprehension comes a whole passage at a time, so the raw
                # count is not what the section will get.
                sizes = {doc["_id"]: doc["count"] async for doc in models.QuizItem.get_motor_collection().aggregate([
                    {"$match": {"category": key, "status": "published"}},
                    {"$group": {"_id": "$passage_id", "count": {"$sum": 1}}},
                ]) if doc["count"]}
                reachable = sum(sizes[p] for p
                                in fill_from_passages(sizes, section.item_count))
            else:
                reachable = min(available, section.item_count)

        if available == 0:
            problems.append(
                f"{section.title!r} needs {bank} and the bank has none")
        elif pool_filter.min_pool and available < pool_filter.min_pool:
            # A floor on variety, not on size. A bank the size of the section
            # serves the same test on every retake.
            problems.append(
                f"{section.title!r} asks for a pool of at least "
                f"{pool_filter.min_pool} but only {available} {bank} qualify, "
                f"so a retake would repeat most of it")
        elif reachable < section.item_count:
            problems.append(
                f"{section.title!r} asks for {section.item_count} but only "
                f"{reachable} can be served from {available} {bank}"
                # Only where it is true. The parenthetical fired for any quiz
                # category, so an admin who asked for twenty response-selection
                # items was told the bank of eight came grouped by passage --
                # which it does not, and which sends them looking for a
                # grouping problem instead of writing twelve more items.
                + (" (they come grouped by passage, so a section gets whole "
                   "passages or nothing)"
                   if kind == "quiz" and groups_by_passage(key) else ""))
    return problems


@router.post("/profiles/{profile_id}/status", response_model=SimulationProfileOut)
async def set_profile_status(profile_id: str, body: ProfileStatusRequest,
                             principal: Principal,
                             models: TenantModels) -> SimulationProfileOut:
    """Publish, retire, or send a profile back to draft."""
    profile = await _load_profile(models, profile_id)
    if body.status == "published":
        if not profile.sections:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "A profile with no sections cannot be published - a student "
                "would start it and be handed nothing to answer.",
            )
        empty = await _sections_without_items(models, profile)
        if empty:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "These sections have no items in the bank and would be "
                "dropped silently, giving students a shorter test than the "
                f"one you designed: {'; '.join(empty)}.",
            )

    before = profile.status
    profile.status = body.status
    await profile.save()

    await audit.record(principal, f"profile.{body.status}",
                       entity="SimulationProfile", entity_id=profile.id,
                       before={"status": before}, after={"status": body.status})
    return _profile_payload(await _load_profile(models, profile_id))
