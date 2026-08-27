"""Reading practice: read a passage, then answer without it in front of you.

Two measures, kept apart on purpose.

**Comprehension** is the questions. **Rate** is how long the passage was on
screen, in words per minute. Blending them into one number would hide the
thing a student most needs to know: fast with poor comprehension is skimming,
slow with good comprehension is a different problem with a different fix, and
a single figure makes those two look identical.

The passage is withdrawn before the questions appear. Leaving it up would
make this a search task -- find the sentence containing the keyword -- which
is a real skill but not the one being claimed, and it would make the rate
measure meaningless because nobody would need to finish reading.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import Principal, TenantModels, require_roles
from app.engine.pipeline import SCALE_MAX, SCALE_MIN, band_label
from app.gamification import engine as game
from app.schemas import (ReadingPassageOut, ReadingQuestionOut, ReadingResult,
                         ReadingResultItem, ReadingStart, ReadingSubmission)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/student/reading", tags=["reading"],
                   dependencies=[Depends(require_roles("student"))])

# Rate bands for the comment beside the number. Adult reading of workplace
# prose sits around 200-250 wpm; below 120 is slow enough to cost a candidate
# real time in a paper, and above 400 with good comprehension is genuinely
# fast rather than skimming -- which is why the comment always pairs the rate
# with the score rather than judging speed alone.
SLOW_WPM = 120
FAST_WPM = 400
# Below this, the passage cannot have been read. Recorded, not scored.
IMPLAUSIBLE_WPM = 700


def _score(correct: int, total: int) -> float:
    if total <= 0:
        return SCALE_MIN
    return round(SCALE_MIN + (SCALE_MAX - SCALE_MIN) * (correct / total), 1)


def _rate_note(wpm: int | None, correct: int, total: int) -> str:
    """What the two numbers mean together. Never speed on its own."""
    if wpm is None:
        return ("Reading rate was not measured for this attempt.")
    share = correct / total if total else 0.0

    if wpm >= IMPLAUSIBLE_WPM:
        return (f"{wpm} words per minute is faster than the passage can be "
                f"read, so the rate is recorded but not treated as a "
                f"measurement. Your comprehension score stands on its own.")
    if wpm > FAST_WPM and share < 0.6:
        return (f"{wpm} words per minute with {correct} of {total} correct is "
                f"skimming. The speed is real; it is costing you the content.")
    if wpm > FAST_WPM:
        return (f"{wpm} words per minute with {correct} of {total} correct is "
                f"genuinely fast reading, not skimming.")
    if wpm < SLOW_WPM and share >= 0.8:
        return (f"{wpm} words per minute is slow, but you took it in â€” "
                f"{correct} of {total}. In a timed paper the speed is what "
                f"would cost you, not the understanding.")
    if wpm < SLOW_WPM:
        return (f"{wpm} words per minute is slow for workplace prose, and the "
                f"comprehension has not been bought by the extra time.")
    return (f"{wpm} words per minute is a normal working pace for this kind of "
            f"text.")


@router.get("/passages", response_model=list[ReadingPassageOut])
async def passages(principal: Principal,
                   models: TenantModels) -> list[ReadingPassageOut]:
    rows = await models.ReadingPassage.find(
        models.ReadingPassage.status == "published").sort(
        models.ReadingPassage.difficulty).to_list()

    coll = models.QuizItem.get_motor_collection()
    counts = {doc["_id"]: doc["count"] for doc in await coll.aggregate([
        {"$match": {"category": "reading_comprehension", "status": "published"}},
        {"$group": {"_id": "$passage_id", "count": {"$sum": 1}}},
    ]).to_list(None)}

    coll = models.ReadingAttempt.get_motor_collection()
    best = {doc["_id"]: doc["max"] for doc in await coll.aggregate([
        {"$match": {"user_id": principal.user_id, "score": {"$ne": None}}},
        {"$group": {"_id": "$passage_id", "max": {"$max": "$score"}}},
    ]).to_list(None)}

    return [
        ReadingPassageOut(
            id=p.id, title=p.title, kind=p.kind, word_count=p.word_count,
            question_count=int(counts.get(p.id, 0)),
            best_score=best.get(p.id),
            # The body is not here. It is the thing being timed.
        )
        for p in rows if counts.get(p.id, 0) > 0
    ]


@router.post("/passages/{passage_id}/start", response_model=ReadingStart)
async def start(passage_id: str, principal: Principal,
                models: TenantModels) -> ReadingStart:
    """Open an attempt and release the passage. The clock starts on the client.

    Timed client-side because the measurement is "how long was this on your
    screen", and a server timestamp would include network latency and the
    student's own delay in pressing the button. The trade is that the number
    is reported by the client and could be faked; it is a practice measure,
    not an invigilated one, and an implausible rate is flagged rather than
    trusted.
    """
    passage = await models.ReadingPassage.get(passage_id)
    if passage is None or passage.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such passage")

    total = int(await models.QuizItem.find(
        models.QuizItem.passage_id == passage_id,
        models.QuizItem.category == "reading_comprehension",
        models.QuizItem.status == "published"
    ).count())
    if total == 0:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That passage has no questions written for it yet")

    attempt = models.ReadingAttempt(user_id=principal.user_id,
                                    passage_id=passage_id, total=total)
    await attempt.create()

    return ReadingStart(
        attempt_id=attempt.id, passage_id=passage.id, title=passage.title,
        kind=passage.kind, body=passage.body, word_count=passage.word_count,
        question_count=total,
    )


@router.get("/attempts/{attempt_id}/questions",
            response_model=list[ReadingQuestionOut])
async def questions(attempt_id: str, principal: Principal,
                    models: TenantModels) -> list[ReadingQuestionOut]:
    attempt = await models.ReadingAttempt.get(attempt_id)
    if attempt is None or attempt.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attempt")
    if attempt.completed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That attempt is finished")

    rows = await models.QuizItem.find(
        models.QuizItem.passage_id == attempt.passage_id,
        models.QuizItem.category == "reading_comprehension",
        models.QuizItem.status == "published"
    ).sort(models.QuizItem.id).to_list()
    random.shuffle(rows)
    return [ReadingQuestionOut(id=q.id, stem=q.stem, options=list(q.options))
            for q in rows]


@router.post("/attempts/{attempt_id}/submit", response_model=ReadingResult)
async def submit(attempt_id: str, body: ReadingSubmission,
                 principal: Principal, models: TenantModels) -> ReadingResult:
    attempt = await models.ReadingAttempt.get(attempt_id)
    if attempt is None or attempt.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attempt")
    if attempt.completed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already submitted")

    passage = await models.ReadingPassage.get(attempt.passage_id)
    rows = {q.id: q for q in await models.QuizItem.find(
        models.QuizItem.passage_id == attempt.passage_id,
        models.QuizItem.category == "reading_comprehension",
        models.QuizItem.status == "published").to_list()}

    chosen = {a.item_id: a.selected_index for a in body.answers}
    results: list[ReadingResultItem] = []
    correct = 0
    for item_id, item in rows.items():
        picked = chosen.get(item_id)
        is_right = picked == item.correct_index
        correct += int(is_right)
        results.append(ReadingResultItem(
            item_id=item_id, stem=item.stem, options=list(item.options),
            selected_index=picked, correct_index=item.correct_index,
            is_correct=is_right, explanation=item.explanation,
        ))

    total = len(rows)
    score = _score(correct, total)

    read_ms = max(0, int(body.read_ms or 0))
    words = passage.word_count if passage else 0
    wpm: int | None = None
    if read_ms > 0 and words > 0:
        wpm = int(round(words / (read_ms / 60_000)))

    attempt.read_ms = read_ms
    attempt.words_per_minute = wpm
    attempt.correct = correct
    attempt.total = total
    attempt.score = score
    attempt.completed_at = datetime.now(timezone.utc)

    await _update_reading_mastery(models, principal.user_id, score)
    await attempt.save()

    xp, day_counted, streak_now = await _reward(
        models, principal, attempt.id, correct, total)

    return ReadingResult(
        attempt_id=attempt.id, title=passage.title if passage else "",
        correct=correct, total=total, score=score, band=band_label(score),
        words_per_minute=wpm, word_count=words,
        rate_note=_rate_note(wpm, correct, total),
        # Released now so a student can check an answer against the text.
        body=passage.body if passage else "",
        items=results, xp_awarded=xp,
        day_counted_now=day_counted, streak_current=streak_now,
    )


async def _update_reading_mastery(models, user_id: str, score: float) -> None:
    """Reading comprehension feeds the `vocabulary` skill for now.

    There is no `reading` skill in the mastery vocabulary, and adding one is a
    psychometrics change rather than a content one: the BKT parameters are
    fitted per skill and there is nothing to fit this against yet. Vocabulary
    is the closest existing home and the skills card says where the number
    came from, which is the same disclosure rule Listening follows.
    """
    row = await models.SkillMastery.find_one(
        models.SkillMastery.user_id == user_id,
        models.SkillMastery.skill == "vocabulary")

    observed = max(0.0, min(1.0, (score - SCALE_MIN) / (SCALE_MAX - SCALE_MIN)))
    if row is None:
        await models.SkillMastery(user_id=user_id, skill="vocabulary",
                                  mastery=round(observed, 4),
                                  baseline=round(observed, 4),
                                  confidence=0.3, observations=1,
                                  last_change=0.0).create()
        return
    prior = float(row.mastery)
    posterior = 0.8 * prior + 0.2 * observed
    row.last_change = round(posterior - prior, 4)
    row.mastery = round(posterior, 4)
    row.observations = int(row.observations or 0) + 1
    row.confidence = min(0.9, float(row.confidence or 0.3) + 0.04)
    await row.save()


async def _reward(models, principal, attempt_id: str,
                  correct: int, total: int) -> tuple[int, bool, int]:
    try:
        config = await game.config_for(principal.tenant_id)
        award = await game.award(
            models, config, principal.user_id, "quiz_completed",
            ref_type="reading", ref_id=attempt_id, target_skill="vocabulary",
            difficulty=("above_ability" if correct < total * 0.5
                        else "at_ability" if correct < total * 0.85
                        else "below_ability"),
        )
        await game.advance_quest(models, config, principal.user_id,
                                 amount=float(total), skill="vocabulary")
        before = await game.streak_state(models, principal.user_id)
        counted_before = before.last_qualifying_day
        await game.qualify_today(models, config, principal.user_id)
        after = await game.streak_state(models, principal.user_id)
        return (award.awarded_xp,
                after.last_qualifying_day != counted_before,
                after.current_streak)
    except Exception as exc:  # noqa: BLE001
        log.warning("reading reward hook failed for %s: %s", attempt_id, exc)
        return 0, False, 0
