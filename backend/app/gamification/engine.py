"""The game, such as it is.

Duolingo's craft, inverted purpose: the season ends on drive day and the app
celebrates a student leaving. Everything here is built so that the mechanics
which would make it dishonest are absent rather than disabled.

Four properties are structural, not policy:

* **XP is computed here and nowhere else.** No endpoint accepts an amount. The
  ledger is append-only; nothing in the codebase updates or deletes a row.
* **Effort and mastery never mix.** Level comes from the ledger and always
  rises. The gap meter comes from SkillMastery and is allowed to stall.
* **Quizzes cannot replace speaking.** Quiz XP is capped as a share of the
  week, and when the cap bites the ledger records that it did.

The engine functions take the per-tenant Beanie document *bundle* (a
``types.SimpleNamespace`` whose attributes are the document classes bound to
that institution's database) instead of a SQLAlchemy session.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.platform import GamificationConfig
from app.models.tenant import (Badge, Cohort, CohortMember, EarnedBadge,
                               EngagementEvent, Quest, SeasonPlan, SkillMastery,
                               StreakState, XPLedger)

log = logging.getLogger(__name__)

XP_PER_LEVEL = 500

SKILLS = ["pronunciation", "fluency", "response_latency", "listening",
          "grammar", "vocabulary", "content_recall"]

SKILL_LABEL = {
    "pronunciation": "Pronunciation Habits",
    "fluency": "Fluency",
    "response_latency": "Response Speed",
    "listening": "Listening Accuracy",
    "grammar": "Grammar Under Pressure",
    "vocabulary": "Vocabulary",
    "content_recall": "Retell Craft",
}

QUEST_TEMPLATES = {
    "response_latency": ("Start faster", "Answer five items without stalling. "
                                         "Aim to begin inside 1.2 seconds of the tone."),
    "fluency": ("Even out your pace", "Five items at a steady rate, without a "
                                      "long pause in the middle."),
    "listening": ("Catch every word", "Five Repeat Sentence items, aiming to "
                                      "reproduce each one in full."),
    "pronunciation": ("Sharpen your delivery", "Five Read Aloud items, "
                                                 "concentrating on clear word endings."),
    "grammar": ("Tighten your sentences", "Five items with attention to tense "
                                          "and agreement."),
    "vocabulary": ("Reach for the right word", "Five items using precise wording."),
    "content_recall": ("Cover the key points", "Five items where you say the "
                                                 "whole idea, not part of it."),
}

STREAK_MILESTONES = [7, 14, 30, 60, 90]

BADGES = [
    ("first_recording", "First Recording", "courage",
     "You pressed record. That is the hardest part."),
    ("first_open_response", "Spoke Freely", "courage",
     "Completed an Open Response with no script to lean on."),
    ("first_boss_mock", "Full Length", "courage",
     "Completed a full-length simulation start to finish."),
    ("chapter_cleared", "Chapter Cleared", "mastery",
     "Reached mastery in a sub-skill — demonstrated, not just practised."),
    ("latency_under_second", "Quick Off the Mark", "mastery",
     "Averaged under a second to start speaking across a whole attempt."),
    ("personal_best", "Personal Best", "mastery",
     "Beat your own best score on this simulation."),
    ("gap_halved", "Halfway There", "mastery",
     "Closed half the gap you started with."),
    ("streak_7", "Seven Days", "consistency", "A week of daily practice."),
    ("streak_14", "Two Weeks", "consistency", "Fourteen days running."),
    ("streak_30", "Thirty Days", "consistency", "A month of showing up."),
    ("streak_60", "Sixty Days", "consistency", "Two months of it."),
    ("streak_90", "Ninety Days", "consistency", "A full season."),
]

CHAPTER_MASTERY = 0.8


@dataclass
class Award:
    activity: str
    awarded_xp: int
    base_xp: int
    difficulty_multiplier: float
    weakness_multiplier: float
    cap_applied: str
    target_skill: str


def level_for(total_xp: int) -> int:
    return 1 + max(0, total_xp) // XP_PER_LEVEL


def xp_into_level(total_xp: int) -> int:
    return max(0, total_xp) % XP_PER_LEVEL


async def config_for(tenant_id: str | None) -> GamificationConfig:
    """The economy for this institution, falling back to the global default."""
    try:
        if tenant_id:
            row = await GamificationConfig.find_one(
                GamificationConfig.tenant_id == tenant_id)
            if row is not None:
                return row
        row = await GamificationConfig.find_one(GamificationConfig.tenant_id == None)
        if row is not None:
            return row
    except Exception:
        pass
    # A tenant with no economy configured still has to be able to practise.
    return GamificationConfig(
        xp_table={"attempt_completed": 120, "drill_completed": 60,
                  "quiz_completed": 25, "quest_completed": 80,
                  "streak_milestone": 150},
        difficulty_multipliers={"below_ability": 0.6, "at_ability": 1.0,
                                "above_ability": 1.4},
        weakness_multiplier=1.5, free_freezes_per_month=2,
        quiz_xp_cap_percent=40, leagues_enabled=True,
        max_engagement_notifications_per_day=1,
    )


async def total_xp(models: SimpleNamespace, user_id: str) -> int:
    rows = await models.XPLedger.find(models.XPLedger.user_id == user_id).to_list()
    return int(sum(r.awarded_xp for r in rows))


async def weakest_skills(models: SimpleNamespace, user_id: str, count: int = 3) -> list[str]:
    rows = await models.SkillMastery.find(
        models.SkillMastery.user_id == user_id).sort(
        models.SkillMastery.mastery).to_list()
    return [r.skill for r in rows[:count]]


# --------------------------------------------------------------------------
# XP
# --------------------------------------------------------------------------

async def _week_start() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


async def _apply_quiz_cap(models: SimpleNamespace, config: GamificationConfig,
                          user_id: str, amount: int) -> tuple[int, str]:
    cap_percent = int(config.quiz_xp_cap_percent or 100)
    if cap_percent >= 100:
        return amount, ""

    week_start = await _week_start()
    since = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
    rows = await models.XPLedger.find(
        models.XPLedger.user_id == user_id,
        models.XPLedger.at >= since).to_list()
    quiz_total = sum(x.awarded_xp for x in rows if x.activity == "quiz_completed")
    speaking_total = sum(x.awarded_xp for x in rows if x.activity != "quiz_completed")

    floor = int(config.xp_table.get("quiz_completed", 0))
    share = cap_percent / 100.0
    from_speaking = int(share / (1 - share) * speaking_total)

    allowance = max(floor, from_speaking) - quiz_total
    if amount <= max(0, allowance):
        return amount, ""

    return max(0, allowance), f"quiz_weekly_{cap_percent}pct"


async def award(models: SimpleNamespace, config: GamificationConfig, user_id: str,
                activity: str, *, ref_type: str = "", ref_id: str = "",
                target_skill: str = "", difficulty: str = "at_ability",
                weakness: bool | None = None) -> Award:
    """Write one XP row. The only way XP is ever created."""
    base = int(config.xp_table.get(activity, 0))
    difficulty_multiplier = float(config.difficulty_multipliers.get(difficulty, 1.0))

    if weakness is None and target_skill:
        weakness = target_skill in await weakest_skills(models, user_id)
    weakness_multiplier = float(config.weakness_multiplier) if weakness else 1.0

    amount = int(round(base * difficulty_multiplier * weakness_multiplier))
    cap_applied = ""

    if activity == "quiz_completed" and amount > 0:
        amount, cap_applied = await _apply_quiz_cap(models, config, user_id, amount)

    await models.XPLedger(
        user_id=user_id, activity=activity, ref_type=ref_type, ref_id=ref_id,
        base_xp=base, difficulty_multiplier=difficulty_multiplier,
        weakness_multiplier=weakness_multiplier, awarded_xp=amount,
        cap_applied=cap_applied, target_skill=target_skill,
    ).create()
    await models.EngagementEvent(
        user_id=user_id, event=activity,
        payload={"xp": amount, "skill": target_skill, "cap": cap_applied},
        weakness_targeted=bool(weakness),
    ).create()
    return Award(activity=activity, awarded_xp=amount, base_xp=base,
                 difficulty_multiplier=difficulty_multiplier,
                 weakness_multiplier=weakness_multiplier,
                 cap_applied=cap_applied, target_skill=target_skill)


# --------------------------------------------------------------------------
# Streaks
# --------------------------------------------------------------------------

async def streak_state(models: SimpleNamespace, user_id: str) -> StreakState:
    row = await models.StreakState.find_one(models.StreakState.user_id == user_id)
    if row is None:
        row = models.StreakState(user_id=user_id)
        await row.create()
    return row


async def touch_streak(models: SimpleNamespace, config: GamificationConfig,
                       user_id: str, today: date | None = None) -> tuple[StreakState, list[int]]:
    today = today or date.today()
    state = await streak_state(models, user_id)
    milestones: list[int] = []

    if state.last_qualifying_day == today:
        return state, milestones

    if state.last_qualifying_day is None:
        state.current_streak = 1
    else:
        gap = (today - state.last_qualifying_day).days
        if gap == 1:
            state.current_streak += 1
        elif gap > 1:
            missed = gap - 1
            usable = min(missed, state.freezes_available)
            if usable == missed:
                state.freezes_available -= usable
                state.freezes_used_this_month += usable
                state.freeze_history = (state.freeze_history or []) + [
                    {"applied_on": today.isoformat(), "days": usable}]
                state.current_streak += 1
            else:
                state.current_streak = 1

    state.last_qualifying_day = today
    state.best_streak = max(state.best_streak, state.current_streak)
    state.updated_at = datetime.now(timezone.utc)

    if state.current_streak in STREAK_MILESTONES:
        milestones.append(state.current_streak)
        state.freezes_available += 1

    await state.save()
    return state, milestones


async def qualify_today(models: SimpleNamespace, config: GamificationConfig,
                        user_id: str, today: date | None = None) -> list[int]:
    quest = await daily_quest(models, user_id, today)
    if not quest.completed:
        return []

    _state, milestones = await touch_streak(models, config, user_id, today)
    for milestone in milestones:
        await award(models, config, user_id, "streak_milestone",
                    ref_type="streak", ref_id=str(milestone))
        await grant(models, user_id, f"streak_{milestone}")
    return milestones


async def grant_monthly_freezes(models: SimpleNamespace, config: GamificationConfig,
                                user_id: str) -> None:
    state = await streak_state(models, user_id)
    free = int(config.free_freezes_per_month or 0)
    if state.freezes_used_this_month and date.today().day == 1:
        state.freezes_used_this_month = 0
        state.freezes_available = max(state.freezes_available, free)
        await state.save()


# --------------------------------------------------------------------------
# Quests
# --------------------------------------------------------------------------

async def daily_quest(models: SimpleNamespace, user_id: str,
                      for_date: date | None = None) -> Quest:
    for_date = for_date or date.today()

    existing = await models.Quest.find_one(
        models.Quest.user_id == user_id, models.Quest.kind == "daily",
        models.Quest.for_date == for_date)
    if existing is not None:
        return existing

    weakest = await weakest_skills(models, user_id, 1)
    if weakest:
        skill = weakest[0]
        title, description = QUEST_TEMPLATES.get(
            skill, ("Practise " + skill.replace("_", " "), "Five targeted items."))
    else:
        skill = ""
        title = "Take your baseline"
        description = ("One short diagnostic sets your starting point. Everything "
                      "after it is measured against today.")

    quest = models.Quest(
        user_id=user_id, kind="daily", for_date=for_date, title=title,
        description=description, target_skill=skill,
        objective={"items": 5, "skill": skill} if skill else {"baseline": True},
        progress=0.0, target=5.0 if skill else 1.0, bonus_xp=80,
    )
    await quest.create()
    return quest


async def advance_quest(models: SimpleNamespace, config: GamificationConfig,
                        user_id: str, *, amount: float = 1.0,
                        skill: str = "", satisfies: bool = False) -> tuple[Quest, bool]:
    quest = await daily_quest(models, user_id)
    if quest.completed:
        return quest, False

    if satisfies:
        quest.progress = quest.target
    elif not quest.target_skill or quest.target_skill == skill:
        quest.progress = min(quest.target, quest.progress + amount)

    just_completed = quest.progress >= quest.target
    if just_completed:
        quest.completed = True
        quest.completed_at = datetime.now(timezone.utc)
        await award(models, config, user_id, "quest_completed",
                    ref_type="quest", ref_id=quest.id,
                    target_skill=quest.target_skill, weakness=True)
    await quest.save()
    return quest, just_completed


# --------------------------------------------------------------------------
# Badges
# --------------------------------------------------------------------------

async def ensure_badges(models: SimpleNamespace) -> dict[str, Badge]:
    existing = {b.code: b async for b in models.Badge.all()}
    for code, name, category, description in BADGES:
        if code not in existing:
            badge = models.Badge(code=code, name=name, category=category,
                                 description=description, criteria={"code": code},
                                 criteria_version=1)
            try:
                await badge.create()
                existing[code] = badge
            except Exception:
                # Duplicate or corrupt record — find by code and continue
                found = await models.Badge.find_one(models.Badge.code == code)
                if found:
                    existing[code] = found
    return existing


async def grant(models: SimpleNamespace, user_id: str, code: str) -> bool:
    """Award a badge once. Returns True if this was the first time."""
    badges = await ensure_badges(models)
    badge = badges.get(code)
    if badge is None:
        return False

    already = await models.EarnedBadge.find_one(
        models.EarnedBadge.user_id == user_id,
        models.EarnedBadge.badge_id == badge.id)
    if already is not None:
        return False

    await models.EarnedBadge(user_id=user_id, badge_id=badge.id,
                             criteria_version=badge.criteria_version).create()
    return True


# --------------------------------------------------------------------------
# Season
# --------------------------------------------------------------------------

ROLLING_SEASON_DAYS = 90


async def season_for(models: SimpleNamespace, user_id: str) -> SeasonPlan:
    member = await models.CohortMember.find_one(
        models.CohortMember.user_id == user_id)
    cohort = None
    if member is not None:
        cohort = await models.Cohort.get(member.cohort_id)
    if cohort is not None and not cohort.active:
        cohort = None

    drive = cohort.drive_start if cohort else None
    starts = date.today()
    ends = drive.date() if drive else starts + timedelta(days=ROLLING_SEASON_DAYS)
    if ends <= starts:
        ends = starts + timedelta(days=7)

    existing = await models.SeasonPlan.find_one(
        models.SeasonPlan.user_id == user_id,
        models.SeasonPlan.active == True)

    weeks = max(1, (ends - starts).days // 7)
    focus = await weakest_skills(models, user_id, 4) or SKILLS[:4]
    themes = [
        {"week": i + 1,
         "theme": SKILL_LABEL.get(focus[i % len(focus)], focus[i % len(focus)]),
         "target_skill": focus[i % len(focus)],
         "minutes_target": 25 * 7}
        for i in range(min(weeks, 16))
    ]

    if existing is None:
        plan = models.SeasonPlan(
            user_id=user_id, cohort_id=cohort.id if cohort else None,
            drive_date=drive, starts_on=starts, ends_on=ends,
            weekly_themes=themes, daily_minutes_target=25,
        )
        try:
            await plan.create()
        except Exception:
            # Race condition or corrupt data — find existing
            existing = await models.SeasonPlan.find_one(
                models.SeasonPlan.user_id == user_id)
            if existing:
                return existing
        return plan

    if existing.ends_on != ends or existing.drive_date != drive:
        existing.replans = (existing.replans or []) + [{
            "at": datetime.now(timezone.utc).isoformat(),
            "from": existing.ends_on.isoformat(), "to": ends.isoformat(),
        }]
        existing.drive_date = drive
        existing.ends_on = ends
        existing.weekly_themes = themes
        await existing.save()
    return existing


# --------------------------------------------------------------------------
# The hook the rest of the app calls
# --------------------------------------------------------------------------

async def on_attempt_scored(models: SimpleNamespace, config: GamificationConfig,
                            user_id: str, attempt_id: str, *,
                            dimensions: dict[str, float],
                            is_full_simulation: bool,
                            previous_best: float | None,
                            overall: float | None,
                            task_types: set[str]) -> dict:
    """Everything the game does when an attempt finishes."""
    weakest = await weakest_skills(models, user_id)
    target = weakest[0] if weakest else ""

    attempt_award = await award(
        models, config, user_id, "attempt_completed",
        ref_type="attempt", ref_id=attempt_id, target_skill=target,
        difficulty="at_ability", weakness=bool(target),
    )

    quest, quest_completed = await advance_quest(
        models, config, user_id, satisfies=is_full_simulation, skill=target)

    milestones = await qualify_today(models, config, user_id)

    earned: list[str] = []

    ledger = await models.XPLedger.find(
        models.XPLedger.user_id == user_id,
        models.XPLedger.activity == "attempt_completed").to_list()
    attempts_before = len(ledger)
    if attempts_before <= 1 and await grant(models, user_id, "first_recording"):
        earned.append("first_recording")

    if "open_response" in task_types and await grant(models, user_id, "first_open_response"):
        earned.append("first_open_response")
    if is_full_simulation and await grant(models, user_id, "first_boss_mock"):
        earned.append("first_boss_mock")

    if (overall is not None and previous_best is not None and overall > previous_best
            and await grant(models, user_id, "personal_best")):
        earned.append("personal_best")

    latency = dimensions.get("latency")
    if latency is not None and latency >= 75 and await grant(models, user_id,
                                                             "latency_under_second"):
        earned.append("latency_under_second")

    mastered = await models.SkillMastery.find(
        models.SkillMastery.user_id == user_id,
        models.SkillMastery.mastery >= CHAPTER_MASTERY).to_list()
    if mastered and await grant(models, user_id, "chapter_cleared"):
        earned.append("chapter_cleared")

    await season_for(models, user_id)

    return {
        "xp_awarded": attempt_award.awarded_xp,
        "quest_completed": quest_completed,
        "quest_title": quest.title,
        "streak_milestones": milestones,
        "badges_earned": earned,
    }
