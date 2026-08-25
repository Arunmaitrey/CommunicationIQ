"""Student-facing game surfaces.

Read-only by design. There is no endpoint here that accepts an XP amount, buys
a freeze, or ranks one student against a named other — those are the three
mechanics the BRD prohibits structurally, and the absence of the routes is how
the prohibition is kept (GAM-21, GAM-22, NFR-15).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from app.deps import Principal, TenantModels, require_roles
from app.gamification import engine
from app.schemas import (BadgeOut, GameState, LedgerEntry, QuestOut,
                         SeasonOut, SeasonWeek, StreakOut)

router = APIRouter(prefix="/student/game", tags=["game"],
                   dependencies=[Depends(require_roles("student"))])


@router.get("", response_model=GameState)
async def state(principal: Principal, models: TenantModels) -> GameState:
    config = await engine.config_for(principal.tenant_id)
    user_id = principal.user_id

    await engine.grant_monthly_freezes(models, config, user_id)
    quest = await engine.daily_quest(models, user_id)
    # Heals an account whose day was completed but never counted -- see
    # qualify_today. Costs one indexed read when the day is already on the
    # record, and means a student who hit the bug is not stuck at zero
    # forever waiting for a fix they cannot trigger themselves.
    await engine.qualify_today(models, config, user_id)
    season = await engine.season_for(models, user_id)
    streak = await engine.streak_state(models, user_id)

    xp = await engine.total_xp(models, user_id)

    mastery = await models.SkillMastery.find(
        models.SkillMastery.user_id == user_id).to_list()
    gap = (round(100 * sum(m.mastery for m in mastery) / len(mastery), 1)
           if mastery else None)
    gap_at_baseline = None
    with_baseline = [m for m in mastery if m.baseline is not None]
    if with_baseline:
        gap_at_baseline = round(
            100 * sum(m.baseline or 0 for m in with_baseline) / len(with_baseline), 1)

    earned = await models.EarnedBadge.find(
        models.EarnedBadge.user_id == user_id).to_list()
    definitions = {b.id: b for b in await models.Badge.all().to_list()}

    days_left = (season.ends_on - date.today()).days if season.ends_on else None

    return GameState(
        level=engine.level_for(xp),
        total_xp=xp,
        xp_into_level=engine.xp_into_level(xp),
        xp_per_level=engine.XP_PER_LEVEL,
        # Effort and mastery, reported side by side and never merged (GAM-03).
        gap_percent=gap,
        gap_at_baseline=gap_at_baseline,
        streak=StreakOut(
            current_streak=streak.current_streak, best_streak=streak.best_streak,
            freezes_available=streak.freezes_available,
            last_qualifying_day=streak.last_qualifying_day,
        ),
        quest=QuestOut(
            id=quest.id, kind=quest.kind, title=quest.title,
            description=quest.description, target_skill=quest.target_skill,
            progress=quest.progress, target=quest.target,
            completed=quest.completed, bonus_xp=quest.bonus_xp,
            for_date=quest.for_date,
        ),
        badges=[
            BadgeOut(
                code=definitions[e.badge_id].code,
                name=definitions[e.badge_id].name,
                description=definitions[e.badge_id].description,
                category=definitions[e.badge_id].category,
                earned_at=e.earned_at,
            )
            for e in earned if e.badge_id in definitions
        ],
        season=SeasonOut(
            starts_on=season.starts_on, ends_on=season.ends_on,
            drive_date=season.drive_date,
            days_remaining=days_left,
            # The distinction is load-bearing: one of these is a real date the
            # institution set, the other is a default we chose.
            is_real_drive_date=season.drive_date is not None,
            daily_minutes_target=season.daily_minutes_target,
            weeks=[SeasonWeek(**w) for w in (season.weekly_themes or [])],
            replans=len(season.replans or []),
        ),
    )


@router.get("/ledger", response_model=list[LedgerEntry])
async def ledger(principal: Principal, models: TenantModels,
                 limit: int = 50) -> list[LedgerEntry]:
    """Every XP award, and the arithmetic behind it.

    Shown to the student because an economy they cannot inspect is one they
    have to take on trust — including the rows where a cap reduced the award.
    """
    rows = await models.XPLedger.find(
        models.XPLedger.user_id == principal.user_id,
    ).sort("-at").limit(min(limit, 200)).to_list()
    return [
        LedgerEntry(
            activity=e.activity, base_xp=e.base_xp,
            difficulty_multiplier=e.difficulty_multiplier,
            weakness_multiplier=e.weakness_multiplier,
            awarded_xp=e.awarded_xp, cap_applied=e.cap_applied,
            target_skill=e.target_skill, at=e.at,
        )
        for e in rows
    ]


@router.get("/badges", response_model=list[BadgeOut])
async def badges(principal: Principal, models: TenantModels) -> list[BadgeOut]:
    """Every badge, earned or not — the unearned ones say what to aim at."""
    definitions = await engine.ensure_badges(models)

    earned = {e.badge_id: e for e in await models.EarnedBadge.find(
        models.EarnedBadge.user_id == principal.user_id).to_list()}

    return [
        BadgeOut(
            code=b.code, name=b.name, description=b.description,
            category=b.category,
            earned_at=earned[b.id].earned_at if b.id in earned else None,
        )
        for b in definitions.values()
    ]
