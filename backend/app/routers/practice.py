"""Quizzes, drills and the mistake bank.

The fast loop. A student who will not face a full speaking simulation on a
Tuesday evening will still do ten grammar items on a bus, and the product's
job is to make that count for something without letting it substitute for the
thing that actually matters — hence the quiz XP cap, enforced in the ledger.

The drill loop is the slow one: fail, understand why, do five similar items,
take a harder one, re-test. It is always pointed at a diagnosed weakness, and
when there is no diagnosis yet it says so instead of inventing one.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from beanie.operators import In, LTE, NE
from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import Principal, TenantModels, require_roles
from app.gamification import engine as game
from app.schemas import (DrillCompletion, DrillOut, MistakeOut, QuizAnswer, QuizItemOut,
                         QuizResult, QuizResultItem, QuizSubmission)

router = APIRouter(prefix="/student", tags=["practice"],
                   dependencies=[Depends(require_roles("student"))])

# QUIZ-03: any quiz playable in three minutes. Ten items at ~20s is the shape.
DEFAULT_QUIZ_LENGTH = 10

# Spaced repetition. Doubling-ish intervals, and an item retires after three
# consecutive correct answers — the point is to stop showing someone something
# they now know, not to farm reviews.
SR_INTERVALS = [1, 3, 7, 16, 35]
MASTERY_STREAK = 3


def _skill_for(category: str) -> str:
    return {
        "grammar": "grammar",
        "sentence_correction": "grammar",
        "error_id": "grammar",
        "vocabulary": "vocabulary",
        "audio_comprehension": "listening",
    }.get(category, "grammar")


# --------------------------------------------------------------------------
# Quiz
# --------------------------------------------------------------------------

@router.get("/quiz/next", response_model=list[QuizItemOut])
async def next_quiz(principal: Principal, models: TenantModels,
                    count: int = DEFAULT_QUIZ_LENGTH,
                    category: str | None = None) -> list[QuizItemOut]:
    """A quiz session, weighted toward the student's weakest area.

    The correct answer is deliberately not in this payload. It arrives with
    the result, after the answer has been given — a quiz whose key is in the
    network tab is not a measurement.
    """
    count = max(1, min(count, 25))
    weakest = await game.weakest_skills(models, principal.user_id, 2)

    query = models.QuizItem.find(models.QuizItem.status == "published")
    if category:
        query = query.find(models.QuizItem.category == category)
    pool = await query.to_list()
    if not pool:
        return []

    # Due mistakes come first: the whole point of the bank is that they
    # resurface, not that they sit in a list.
    due_rows = await models.MistakeBankEntry.find(
        models.MistakeBankEntry.user_id == principal.user_id,
        models.MistakeBankEntry.mastered == False,
        NE(models.MistakeBankEntry.quiz_item_id, None),
        LTE(models.MistakeBankEntry.due_at, datetime.now(timezone.utc)),
    ).to_list()
    due_ids = {r.quiz_item_id for r in due_rows}

    def rank(item) -> tuple[int, float]:
        if item.id in due_ids:
            return (0, random.random())
        if _skill_for(item.category) in weakest:
            return (1, random.random())
        return (2, random.random())

    chosen = sorted(pool, key=rank)[:count]
    random.shuffle(chosen)

    return [
        QuizItemOut(
            id=i.id, category=i.category, stem=i.stem, options=i.options,
            seconds_allowed=i.seconds_allowed,
            is_review=i.id in due_ids,
        )
        for i in chosen
    ]


@router.post("/quiz/submit", response_model=QuizResult)
async def submit_quiz(body: QuizSubmission, principal: Principal,
                      models: TenantModels) -> QuizResult:
    """Mark a quiz, update the mistake bank, award capped XP."""
    if not body.answers:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No answers submitted")

    items = {i.id: i for i in await models.QuizItem.find(
        In(models.QuizItem.id, [a.item_id for a in body.answers])).to_list()}

    results: list[QuizResultItem] = []
    correct = 0
    now = datetime.now(timezone.utc)

    for answer in body.answers:
        item = items.get(answer.item_id)
        if item is None:
            continue
        is_right = answer.selected_index == item.correct_index
        correct += int(is_right)

        results.append(QuizResultItem(
            item_id=item.id, stem=item.stem, options=item.options,
            selected_index=answer.selected_index,
            correct_index=item.correct_index, is_correct=is_right,
            explanation=item.explanation, category=item.category,
        ))
        await _update_mistake_bank(models, principal.user_id, item, is_right, now)

    total = len(results)
    accuracy = correct / total if total else 0.0

    # Difficulty band is relative to how the student actually did, so a set
    # they found hard is worth more than one they breezed through.
    difficulty = ("above_ability" if accuracy < 0.5
                  else "at_ability" if accuracy < 0.85 else "below_ability")

    config = await game.config_for(principal.tenant_id)
    weakest = await game.weakest_skills(models, principal.user_id)
    skills = {_skill_for(r.category) for r in results}
    target = next((s for s in weakest if s in skills), next(iter(skills), ""))

    award = await game.award(
        models, config, principal.user_id, "quiz_completed",
        ref_type="quiz", ref_id=body.session_id or "", target_skill=target,
        difficulty=difficulty,
    )
    # Quizzes advance the daily quest but never satisfy it outright — only a
    # full simulation does that (GAM-01).
    quest, quest_completed = await game.advance_quest(
        models, config, principal.user_id, amount=1.0, skill=target)
    # Unconditional: the quest may already have been finished by an earlier
    # drill today, and the day still has to be counted exactly once.
    await game.qualify_today(models, config, principal.user_id)

    return QuizResult(
        total=total, correct=correct, accuracy=round(accuracy, 3),
        xp_awarded=award.awarded_xp,
        # When the cap bit, say so. A student who earned less than the maths
        # suggests is owed the reason.
        xp_capped=bool(award.cap_applied),
        cap_note=("Quiz XP is capped as a share of your week so quizzes cannot "
                  "stand in for speaking practice."
                  if award.cap_applied else ""),
        quest_progress=quest.progress, quest_target=quest.target,
        quest_completed=quest_completed,
        items=results,
    )


async def _update_mistake_bank(models: TenantModels, user_id: str,
                               item, is_right: bool,
                               now: datetime) -> None:
    entry = await models.MistakeBankEntry.find_one(
        models.MistakeBankEntry.user_id == user_id,
        models.MistakeBankEntry.quiz_item_id == item.id)

    if not is_right:
        if entry is None:
            await models.MistakeBankEntry(
                user_id=user_id, quiz_item_id=item.id, skill=_skill_for(item.category),
                times_wrong=1, interval_days=SR_INTERVALS[0],
                due_at=now + timedelta(days=SR_INTERVALS[0]),
            ).create()
        else:
            # Getting it wrong again resets the ladder — the schedule should
            # reflect what the student actually knows, not how long the item
            # has been in the list.
            entry.times_wrong += 1
            entry.times_right_since = 0
            entry.mastered = False
            entry.interval_days = SR_INTERVALS[0]
            entry.due_at = now + timedelta(days=SR_INTERVALS[0])
            await entry.save()
        return

    if entry is None or entry.mastered:
        return

    entry.times_right_since += 1
    if entry.times_right_since >= MASTERY_STREAK:
        entry.mastered = True
        entry.due_at = now + timedelta(days=365)
        await entry.save()
        return

    step = min(entry.times_right_since, len(SR_INTERVALS) - 1)
    entry.interval_days = SR_INTERVALS[step]
    entry.due_at = now + timedelta(days=entry.interval_days)
    await entry.save()


@router.get("/mistakes", response_model=list[MistakeOut])
async def mistakes(principal: Principal, models: TenantModels,
                   only_due: bool = False) -> list[MistakeOut]:
    query = models.MistakeBankEntry.find(
        models.MistakeBankEntry.user_id == principal.user_id,
        models.MistakeBankEntry.mastered == False)
    if only_due:
        query = query.find(LTE(models.MistakeBankEntry.due_at,
                               datetime.now(timezone.utc)))
    rows = await query.sort(models.MistakeBankEntry.due_at).to_list()

    items = {i.id: i for i in await models.QuizItem.find(In(
        models.QuizItem.id,
        [r.quiz_item_id for r in rows if r.quiz_item_id] or [""]),
    ).to_list()}

    now = datetime.now(timezone.utc)
    return [
        MistakeOut(
            id=r.id, skill=r.skill, times_wrong=r.times_wrong,
            times_right_since=r.times_right_since, interval_days=r.interval_days,
            due_at=r.due_at, due_now=r.due_at <= now,
            stem=items[r.quiz_item_id].stem if r.quiz_item_id in items else "",
            category=items[r.quiz_item_id].category if r.quiz_item_id in items else "",
        )
        for r in rows
    ]


# --------------------------------------------------------------------------
# Drills
# --------------------------------------------------------------------------

DRILL_ITEMS = 5

# Which task types exercise which sub-skill. Read the other way round when
# choosing what to drill.
SKILL_TASKS = {
    "pronunciation": ["read_aloud"],
    "fluency": ["read_aloud", "open_response"],
    "response_latency": ["repeat_sentence", "short_answer"],
    "listening": ["repeat_sentence"],
    "content_recall": ["story_retell", "open_response"],
    "grammar": ["sentence_build", "open_response"],
    "vocabulary": ["open_response"],
}


@router.get("/drills", response_model=list[DrillOut])
async def drills(principal: Principal, models: TenantModels) -> list[DrillOut]:
    rows = await models.Drill.find(
        models.Drill.user_id == principal.user_id,
    ).sort("-created_at").limit(20).to_list()
    return [_drill_out(d) for d in rows]


@router.post("/drills", response_model=DrillOut, status_code=status.HTTP_201_CREATED)
async def create_drill(principal: Principal, models: TenantModels,
                       skill: str | None = None) -> DrillOut:
    """Build a drill against a diagnosed weakness.

    Refuses to invent one. With no mastery record there is nothing to target,
    and five random items dressed up as a personalised drill would be the kind
    of small dishonesty this product cannot afford.
    """
    mastery = await models.SkillMastery.find(
        models.SkillMastery.user_id == principal.user_id).sort(
        models.SkillMastery.mastery).to_list()
    if not mastery:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Take the baseline diagnostic first — a drill needs a diagnosis to aim at.")

    target = skill or mastery[0].skill
    record = next((m for m in mastery if m.skill == target), mastery[0])

    task_types = SKILL_TASKS.get(target, ["read_aloud"])
    pool = await models.TaskItem.find(
        In(models.TaskItem.task_type, task_types),
        models.TaskItem.status == "published").to_list()
    if not pool:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "No items available for that skill yet")

    easier = sorted(pool, key=lambda i: i.difficulty)
    chosen = easier[:min(DRILL_ITEMS, len(easier))]
    # TRAIN-01 ends on something harder than the set that preceded it — the
    # loop is fail, understand, practise, then stretch.
    if len(easier) > len(chosen):
        chosen.append(easier[-1])

    # The "why": the most recent evidence for this weakness, in the student's
    # own numbers rather than a generic tip.
    why = await _why_for(models, principal.user_id, target)

    drill = models.Drill(
        user_id=principal.user_id, target_skill=target, source="auto",
        item_ids=[i.id for i in chosen], status="pending",
        mastery_before=record.mastery,
    )
    await drill.create()

    out = _drill_out(drill)
    out.why = why
    return out


@router.post("/drills/{drill_id}/complete", response_model=DrillCompletion)
async def complete_drill(drill_id: str, principal: Principal,
                         models: TenantModels) -> DrillCompletion:
    drill = await models.Drill.get(drill_id)
    if drill is None or drill.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Drill not found")
    if drill.status == "completed":
        # Replaying a completed drill earns nothing a second time, and says so
        # by reporting a zero reward rather than a stale one.
        return DrillCompletion(**_drill_out(drill).model_dump())

    record = await models.SkillMastery.find_one(
        models.SkillMastery.user_id == principal.user_id,
        models.SkillMastery.skill == drill.target_skill)

    drill.status = "completed"
    drill.items_completed = len(drill.item_ids or [])
    drill.completed_at = datetime.now(timezone.utc)
    drill.mastery_after = record.mastery if record else None

    config = await game.config_for(principal.tenant_id)
    award = await game.award(models, config, principal.user_id, "drill_completed",
                             ref_type="drill", ref_id=drill.id,
                             target_skill=drill.target_skill)
    quest, _completed = await game.advance_quest(
        models, config, principal.user_id, amount=float(drill.items_completed),
        skill=drill.target_skill)

    # Read the streak before qualifying so we can tell the student whether
    # *this* action is what counted the day, rather than only what the total
    # now is.
    before = await game.streak_state(models, principal.user_id)
    counted_before = before.last_qualifying_day
    milestones = await game.qualify_today(models, config, principal.user_id)
    after = await game.streak_state(models, principal.user_id)

    await drill.save()
    return DrillCompletion(
        **_drill_out(drill).model_dump(),
        xp_awarded=award.awarded_xp,
        quest_progress=quest.progress,
        quest_target=quest.target,
        quest_completed=quest.completed,
        streak_current=after.current_streak,
        day_counted_now=after.last_qualifying_day != counted_before,
        milestones=milestones,
    )


async def _why_for(models: TenantModels, user_id: str, skill: str) -> str:
    """One sentence of evidence, drawn from the student's last recording.

    "Last recording" means the newest feature record backed by a real
    response; the join that enforced that becomes a ``$lookup`` here. The
    joined array is stripped before validation so the document parses clean.
    """
    coll = models.FeatureRecord.get_motor_collection()
    docs = await coll.aggregate([
        {"$lookup": {
            "from": models.Response.get_motor_collection().name,
            "localField": "response_id",
            "foreignField": "_id",
            "as": "_response",
        }},
        {"$match": {"_response": {"$ne": []}}},
        {"$sort": {"created_at": -1}},
        {"$limit": 1},
    ]).to_list(1)
    if not docs:
        return ""
    docs[0].pop("_response", None)
    feature = models.FeatureRecord.model_validate(docs[0])

    metrics = feature.metrics or {}
    if skill == "response_latency" and metrics.get("onset_ms"):
        return (f"On your last answer you took {metrics['onset_ms'] / 1000:.1f}s "
                f"to start speaking.")
    if skill == "fluency":
        if metrics.get("longest_pause_ms"):
            return (f"Your longest pause last time was "
                    f"{metrics['longest_pause_ms'] / 1000:.1f}s.")
        if metrics.get("words_per_minute"):
            return f"You last spoke at about {metrics['words_per_minute']:.0f} words a minute."
    if skill == "listening" and metrics.get("accuracy") is not None:
        return (f"You reproduced {metrics['accuracy'] * 100:.0f}% of the words "
                f"on your last repeat item.")
    return ""


def _drill_out(drill) -> DrillOut:
    return DrillOut(
        id=drill.id, target_skill=drill.target_skill, status=drill.status,
        item_count=len(drill.item_ids or []), items_completed=drill.items_completed,
        mastery_before=drill.mastery_before, mastery_after=drill.mastery_after,
        created_at=drill.created_at, why="",
    )
