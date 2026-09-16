"""Listening practice: hear a passage, then answer questions about it.

The order is the whole design. Questions are withheld until the audio has
been played, because a student who can read the questions first knows what to
listen for, and that measures scanning rather than comprehension. Real rounds
do not show you the questions in advance and neither does this.

The correct answers never leave the server before an attempt is submitted --
the same rule the quiz engine follows, for the same reason.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import Principal, TenantModels, require_roles
from app.engine.pipeline import SCALE_MAX, SCALE_MIN, band_label
from app.gamification import engine as game
from app.schemas import (ListeningAnswer, ListeningPassageOut,
                         ListeningQuestionOut, ListeningResult,
                         ListeningResultItem, ListeningStart, ListeningSubmission)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/student/listening", tags=["listening"],
                   dependencies=[Depends(require_roles("student"))])


def _score(correct: int, total: int) -> float:
    """Proportion correct, on the product's internal 0-100 scale.

    The same scale as every other measure here, so a Listening score can sit
    beside a Speaking one without a silent change of units. Not calibrated
    against human judgement -- nothing in this product is yet -- but it is at
    least the same uncalibrated scale.
    """
    if total <= 0:
        return SCALE_MIN
    return round(SCALE_MIN + (SCALE_MAX - SCALE_MIN) * (correct / total), 1)

@router.get("/set/next")
async def next_listening_set(principal: Principal, models: TenantModels) -> dict:
    """This student's next listening practice set, in rotation.

    A listening set holds exactly ten audio-comprehension questions, each
    carrying its parent passage (with its audio) inline. Questions are
    shuffled inside the set; the served payload keeps Q1..Q10 positions.
    """
    from app.practice_engine import next_set_for_practice
    chosen = await next_set_for_practice(principal.user_id, "listening")
    if chosen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No listening sets are active yet")

    from app.db import control_db
    db = control_db()
    qids = [str(x) for x in chosen["question_ids"]]
    docs = await db.quiz_items.find({"_id": {"$in": qids}}).to_list(20)
    by_id = {str(d["_id"]): d for d in docs}

    passage_ids = list({d.get("passage_id") for d in docs if d.get("passage_id")})
    pdocs = await db.listening_passages.find(
        {"_id": {"$in": [str(x) for x in passage_ids]}}).to_list(50)
    passages_by_id = {str(d["_id"]): d for d in pdocs}

    questions = []
    for qid in qids:
        d = by_id.get(qid)
        if d is None:
            continue
        pid = str(d.get("passage_id") or "")
        p = passages_by_id.get(pid) or {}
        questions.append({
            "position": len(questions) + 1,
            "id": qid,
            "question_number": d.get("question_number", ""),
            "stem": d.get("stem", ""),
            "options": list(d.get("options") or []),
            "passage": {
                "id": pid,
                "title": p.get("title", ""),
                "kind": p.get("kind", "short_talk"),
                "transcript": p.get("transcript", ""),
                "audio_key": p.get("audio_key", ""),
                "plays_allowed": p.get("plays_allowed", 1),
                "approx_seconds": p.get("approx_seconds", 45),
            } if p else None,
        })

    return {
        "sitting_id": chosen["sitting_id"],
        "set_id": chosen["set_id"],
        "set_number": chosen["set_number"],
        "resumed": chosen["resumed"],
        "questions": questions,
    }


@router.post("/set/complete")
async def complete_listening_set(body: dict, principal: Principal,
                                 models: TenantModels) -> dict:
    """Close the sitting: the set leaves the rotation only now."""
    from app.practice_engine import complete_sitting
    result = await complete_sitting(
        body.get("sitting_id", ""), principal.user_id,
        score=body.get("score"))
    if not result.get("ok"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, result.get("error", "Sitting not found"))
    return result


@router.get("/random", response_model=ListeningStart)
async def random_passage(principal: Principal, models: TenantModels,
                          company: str = "") -> ListeningStart:
    """Serve the student's next unanswered question from their listening set.

    Same rotation as reading: the engine picks the student's first unfinished
    listening set; this endpoint hands out its questions one at a time
    (skipping ones already answered), and the set leaves the rotation once all
    ten are answered. Questions come only from the set — listening practice is
    listening, never another skill's bank and never another company's.
    """
    from app.practice_engine import next_set_for_practice, complete_sitting
    from app.db import control_db

    db = control_db()

    for _attempt in range(4):  # at most: finish one full set, then serve next
        chosen = await next_set_for_practice(principal.user_id, "listening")
        if chosen is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "No listening sets are active yet")
        sitting_id = chosen["sitting_id"]
        set_qids = [str(x) for x in chosen["question_ids"]]

        attempted_rows = await models.ListeningAttempt.find(
            models.ListeningAttempt.user_id == principal.user_id).to_list()
        answered_items: set[str] = set()
        for a in attempted_rows:
            answered_items.update(str(x) for x in (a.item_ids or []))
        remaining = [q for q in set_qids if q not in answered_items]

        if not remaining:
            await complete_sitting(sitting_id, principal.user_id,
                                   score=None, db=db)
            continue

        total = len(set_qids)
        attempt = models.ListeningAttempt(user_id=principal.user_id,
                                          passage_id=remaining[0], total=total)
        attempt.item_ids = remaining
        await attempt.create()

        # ListeningStart keeps its shape; the audio shown is the first
        # remaining question's parent passage.
        first = await db.quiz_items.find_one({"_id": remaining[0]})
        pid = str((first or {}).get("passage_id") or "")
        passage = await db.listening_passages.find_one({"_id": pid}) if pid else None
        if first is None or not passage:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "No listening passages available")

        return ListeningStart(
            attempt_id=attempt.id, passage_id=pid, title=passage.get("title", ""),
            kind=passage.get("kind", "short_talk"),
            transcript=passage.get("transcript", ""),
            accent=passage.get("accent", "indian"),
            plays_allowed=int(passage.get("plays_allowed") or 1),
            question_count=total,
            audio_key=passage.get("audio_key", ""),
        )

    raise HTTPException(status.HTTP_404_NOT_FOUND, "No listening passages available")


@router.get("/passages", response_model=list[ListeningPassageOut])
async def passages(principal: Principal,
                   models: TenantModels,
                   company: str = "",
                   limit: int = 10) -> list[ListeningPassageOut]:
    """Everything available, with how the student has done on each.

    Includes passages already attempted: re-listening to something you scored
    badly on is the point, not a loophole.
    """
    # Practice shows general passages by default.
    # "General" and empty company both count as general (non-company) content.
    # Company-specific passages are only shown when company param is provided.
    query = models.ListeningPassage.find(models.ListeningPassage.status == "published")
    if company:
        query = query.find(models.ListeningPassage.company == company)
    else:
        # No company specified — only show general passages
        query = query.find(
            models.ListeningPassage.company.in_(["", "general"])
        )
    import random as _rand
    all_rows = await query.to_list()
    _rand.shuffle(all_rows)
    rows = all_rows[:max(1, min(limit, 50))]

    coll = models.QuizItem.get_motor_collection()
    counts = {doc["_id"]: doc["count"] for doc in await coll.aggregate([
        {"$match": {"category": "audio_comprehension", "status": "published"}},
        {"$group": {"_id": "$passage_id", "count": {"$sum": 1}}},
    ]).to_list(None)}

    coll = models.ListeningAttempt.get_motor_collection()
    best = {doc["_id"]: doc["max"] for doc in await coll.aggregate([
        {"$match": {"user_id": principal.user_id, "score": {"$ne": None}}},
        {"$group": {"_id": "$passage_id", "max": {"$max": "$score"}}},
    ]).to_list(None)}

    return [
        ListeningPassageOut(
            id=p.id, title=p.title, kind=p.kind,
            approx_seconds=p.approx_seconds, plays_allowed=p.plays_allowed,
            question_count=int(counts.get(p.id, 0)),
            best_score=best.get(p.id),
            # No transcript here. It is the answer sheet.
            has_recording=bool(p.audio_key),
        )
        for p in rows
    ]


@router.post("/passages/{passage_id}/start", response_model=ListeningStart)
async def start(passage_id: str, principal: Principal,
                models: TenantModels) -> ListeningStart:
    """Open an attempt and hand over the words to be spoken -- not the questions.

    The transcript goes to the client because there is no recording yet and
    the browser speaks it. That is a real weakness of doing it this way: a
    determined student can read it out of the network tab instead of
    listening. It is disclosed rather than pretended away, and it is why this
    is practice rather than assessment. A recorded passage would close it.
    """
    # Subscription check for general users
    from app.subscription import require_subscription
    await require_subscription(principal)

    passage = await models.ListeningPassage.get(passage_id)
    if passage is None or passage.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such passage")

    total = int(await models.QuizItem.find(
        models.QuizItem.passage_id == passage_id,
        models.QuizItem.category == "audio_comprehension",
        models.QuizItem.status == "published"
    ).count())
    if total == 0:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "That passage has no questions written for it yet")

    attempt = models.ListeningAttempt(user_id=principal.user_id,
                                      passage_id=passage_id, total=total)
    await attempt.create()

    return ListeningStart(
        attempt_id=attempt.id, passage_id=passage.id, title=passage.title,
        kind=passage.kind, transcript=passage.transcript, accent=passage.accent,
        plays_allowed=passage.plays_allowed, question_count=total,
        audio_key=passage.audio_key,
    )


@router.get("/attempts/{attempt_id}/questions",
            response_model=list[ListeningQuestionOut])
async def questions(attempt_id: str, principal: Principal,
                    models: TenantModels) -> list[ListeningQuestionOut]:
    """The questions, once the passage has been heard.

    Correct answers are not included. They arrive with the result.
    """
    attempt = await models.ListeningAttempt.get(attempt_id)
    if attempt is None or attempt.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attempt")
    if attempt.completed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That attempt is finished")

    # Only return questions that are in this attempt's set (item_ids).
    # If item_ids is empty (legacy attempt), return all passage questions.
    if attempt.item_ids:
        rows = await models.QuizItem.find(
            models.QuizItem.id.in_(attempt.item_ids),
            models.QuizItem.passage_id == attempt.passage_id,
            models.QuizItem.category == "audio_comprehension",
            models.QuizItem.status == "published"
        ).to_list()
    else:
        rows = await models.QuizItem.find(
            models.QuizItem.passage_id == attempt.passage_id,
            models.QuizItem.category == "audio_comprehension",
            models.QuizItem.status == "published"
        ).to_list()

    import random as _rand
    _rand.shuffle(rows)

    return [ListeningQuestionOut(id=q.id, stem=q.stem, options=list(q.options))
            for q in rows]


@router.post("/attempts/{attempt_id}/submit", response_model=ListeningResult)
async def submit(attempt_id: str, body: ListeningSubmission,
                 principal: Principal, models: TenantModels) -> ListeningResult:
    """Mark the answers, record the score, and move the daily loop."""
    attempt = await models.ListeningAttempt.get(attempt_id)
    if attempt is None or attempt.user_id != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attempt")
    if attempt.completed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Already submitted")

    rows = {q.id: q for q in await models.QuizItem.find(
        models.QuizItem.passage_id == attempt.passage_id,
        models.QuizItem.category == "audio_comprehension",
        models.QuizItem.status == "published").to_list()}

    chosen = {a.item_id: a.selected_index for a in body.answers}
    results: list[ListeningResultItem] = []
    correct = 0
    for item_id, item in rows.items():
        picked = chosen.get(item_id)
        is_right = picked == item.correct_index
        correct += int(is_right)
        results.append(ListeningResultItem(
            item_id=item_id, stem=item.stem, options=list(item.options),
            selected_index=picked, correct_index=item.correct_index,
            is_correct=is_right, explanation=item.explanation,
        ))

    total = len(rows)
    score = _score(correct, total)

    attempt.correct = correct
    attempt.total = total
    attempt.score = score
    attempt.plays_used = max(1, int(body.plays_used or 1))
    attempt.completed_at = datetime.now(timezone.utc)

    # Deliberately not a ScoreRecord. That table hangs off a speaking attempt
    # by a non-nullable foreign key, and manufacturing an empty Attempt row to
    # carry a listening score would put a fake speaking attempt into every
    # report that counts them. The ListeningAttempt row is the record; mastery
    # below is how this reaches the rest of the product.

    # This is a direct measurement of listening, unlike the repeat-accuracy
    # signal the skill has been fed until now.
    await attempt.save()
    await _update_listening_mastery(models, principal.user_id, score)

    passage = await models.ListeningPassage.get(attempt.passage_id)

    award_xp, day_counted, streak_now = await _reward(
        models, principal, attempt.id, correct, total)

    return ListeningResult(
        attempt_id=attempt.id,
        title=passage.title if passage else "",
        correct=correct, total=total, score=score,
        band=band_label(score),
        transcript=passage.transcript if passage else "",
        items=results,
        xp_awarded=award_xp,
        day_counted_now=day_counted,
        streak_current=streak_now,
    )


async def _update_listening_mastery(models, user_id: str, score: float) -> None:
    """Move the listening mastery from a real comprehension result.

    Kept out of the frozen scoring pipeline on purpose: that pipeline is
    hashed for the validation study and this is a new measure that has never
    been part of it. The arithmetic is a plain exponential update rather than
    the BKT the speech dimensions use, because BKT parameters for listening
    comprehension have not been fitted to anything.
    """
    row = await models.SkillMastery.find_one(
        models.SkillMastery.user_id == user_id,
        models.SkillMastery.skill == "listening")

    observed = max(0.0, min(1.0, (score - SCALE_MIN) / (SCALE_MAX - SCALE_MIN)))
    if row is None:
        await models.SkillMastery(user_id=user_id, skill="listening",
                                  mastery=round(observed, 4),
                                  baseline=round(observed, 4),
                                  confidence=0.3, observations=1,
                                  last_change=0.0).create()
        return

    prior = float(row.mastery)
    # Weighted toward the record rather than the newest sitting: one bad
    # morning should move a mastery estimate, not replace it.
    posterior = 0.7 * prior + 0.3 * observed
    row.last_change = round(posterior - prior, 4)
    row.mastery = round(posterior, 4)
    row.observations = int(row.observations or 0) + 1
    row.confidence = min(0.9, float(row.confidence or 0.3) + 0.05)
    await row.save()


async def _reward(models, principal, attempt_id: str,
                  correct: int, total: int) -> tuple[int, bool, int]:
    """XP, quest and streak. Never costs a student their result if it fails."""
    try:
        config = await game.config_for(principal.tenant_id)
        award = await game.award(
            models, config, principal.user_id, "quiz_completed",
            ref_type="listening", ref_id=attempt_id, target_skill="listening",
            difficulty=("above_ability" if correct < total * 0.5
                        else "at_ability" if correct < total * 0.85
                        else "below_ability"),
        )
        await game.advance_quest(models, config, principal.user_id,
                                 amount=float(total), skill="listening")
        before = await game.streak_state(models, principal.user_id)
        counted_before = before.last_qualifying_day
        await game.qualify_today(models, config, principal.user_id)
        after = await game.streak_state(models, principal.user_id)
        return (award.awarded_xp,
                after.last_qualifying_day != counted_before,
                after.current_streak)
    except Exception as exc:  # noqa: BLE001
        log.warning("listening reward hook failed for %s: %s", attempt_id, exc)
        return 0, False, 0
