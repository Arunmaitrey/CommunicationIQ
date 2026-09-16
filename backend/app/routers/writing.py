"""Writing practice: a real task, and five measures of the answer.

The scoring lives in ``app.writing``; this exposes it and keeps the text.

Submissions are stored in full. A writing score with no writing behind it
cannot be checked by a admin, appealed by a student, or re-marked when the
scorer improves -- and this scorer is a first version that will improve. The
measures are stored exactly as produced, alongside the version that produced
them, so a later re-mark can be compared against what the student was told at
the time.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status

from app import writing as scorer
from app.deps import Principal, TenantModels, require_roles
from app import audit
from app.gamification import engine as game
from app.models.tenant import SkillMastery, WritingPrompt, WritingSubmissionRow
from app.schemas import (WritingMeasureOut, WritingPromptOut, WritingResult,
                         WritingSubmission)

log = logging.getLogger(__name__)

SCORER_VERSION = "0.1.0"

router = APIRouter(prefix="/student/writing", tags=["writing"],
                   dependencies=[Depends(require_roles("student"))])


def _label(point) -> str:
    """The student-facing half of a rubric point, without its cues."""
    return str(point.get("point", "")) if isinstance(point, dict) else str(point)


async def _best_scores(models, user_id: str) -> dict[str, float]:
    coll = models.WritingSubmissionRow.get_motor_collection()
    cursor = coll.aggregate([
        {"$match": {"user_id": user_id, "overall": {"$ne": None}}},
        {"$group": {"_id": "$prompt_id", "max": {"$max": "$overall"}}},
    ])
    return {doc["_id"]: doc["max"] async for doc in cursor}

@router.get("/set/next")
async def next_writing_set(principal: Principal, models: TenantModels) -> dict:
    """This student's next writing practice set, in rotation.

    Writing sets hold writing prompts only — emails, reports, summaries. The
    rotation serves the first set the student has not completed, and questions
    are shuffled inside the set with their Q1..Q10 positions kept.
    """
    from app.practice_engine import next_set_for_practice
    chosen = await next_set_for_practice(principal.user_id, "writing")
    if chosen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No writing sets are active yet")

    from app.db import control_db
    db = control_db()
    prompt_ids = [str(x) for x in chosen["question_ids"]]
    docs = await db.writing_prompts.find({"_id": {"$in": prompt_ids}}).to_list(100)
    by_id = {str(d["_id"]): d for d in docs}

    prompts_out = []
    for pid in prompt_ids:
        d = by_id.get(pid)
        if d is None:
            continue
        prompts_out.append({
            "position": len(prompts_out) + 1,
            "prompt_id": pid,
            "question_number": d.get("question_number", ""),
            "title": d.get("title", ""),
            "kind": d.get("kind", "email"),
            "prompt": d.get("prompt", ""),
            "scenario": d.get("scenario", ""),
            "key_points": list(d.get("key_points") or []),
            "min_words": d.get("min_words", 120),
            "suggested_minutes": d.get("suggested_minutes", 20),
        })

    return {
        "sitting_id": chosen["sitting_id"],
        "set_id": chosen["set_id"],
        "set_number": chosen["set_number"],
        "resumed": chosen["resumed"],
        "prompts": prompts_out,
    }


@router.post("/set/complete")
async def complete_writing_set(body: dict, principal: Principal,
                               models: TenantModels) -> dict:
    """Close the sitting: the set leaves the rotation only now."""
    from app.practice_engine import complete_sitting
    result = await complete_sitting(
        body.get("sitting_id", ""), principal.user_id,
        score=body.get("score"))
    if not result.get("ok"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, result.get("error", "Sitting not found"))
    return result


@router.get("/prompts", response_model=list[WritingPromptOut])
async def prompts(principal: Principal,
                  models: TenantModels,
                  company: str = "",
                  limit: int = 10) -> list[WritingPromptOut]:
    # Practice shows general prompts by default.
    # "General" and empty company both count as general (non-company) content.
    # Company-specific prompts are only shown when company param is provided.
    query = models.WritingPrompt.find(models.WritingPrompt.status == "published")
    if company:
        all_rows = []
        for p in await query.to_list():
            if p.company and p.company.lower() == company.lower():
                all_rows.append(p)
    else:
        all_rows = [
            p for p in await query.to_list()
            if not getattr(p, 'company', '') or p.company.lower() in ('', 'general')
        ]
    import random as _rand
    _rand.shuffle(all_rows)

    # Exclude prompts already submitted by this user
    attempted = await models.WritingSubmissionRow.find(
        models.WritingSubmissionRow.user_id == principal.user_id
    ).to_list()
    attempted_ids = {a.prompt_id for a in attempted}
    if attempted_ids:
        all_rows = [p for p in all_rows if p.id not in attempted_ids]

    rows = all_rows[:max(1, min(limit, 10))]

    best = await _best_scores(models, principal.user_id)

    return [
        WritingPromptOut(
            id=p.id, title=p.title, kind=p.kind, company=getattr(p, 'company', ''), scenario=p.scenario,
            prompt=p.prompt, min_words=p.min_words,
            suggested_minutes=p.suggested_minutes,
            key_points=[_label(point) for point in (p.key_points or [])],
            best_score=best.get(p.id),
        )
        for p in rows
    ]


@router.post("/prompts/{prompt_id}/submit", response_model=WritingResult)
async def submit(prompt_id: str, body: WritingSubmission,
                 principal: Principal, models: TenantModels) -> WritingResult:
    # Subscription check for general users
    from app.subscription import require_subscription
    await require_subscription(principal)

    prompt = await models.WritingPrompt.get(prompt_id)
    if prompt is None or prompt.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such prompt")

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing was written")

    result = await scorer.score_essay(
        text, key_points=list(prompt.key_points or []),
        min_words=int(prompt.min_words or 0))

    row = models.WritingSubmissionRow(
        user_id=principal.user_id, prompt_id=prompt_id, text=text,
        word_count=result.word_count,
        minutes_spent=max(0, int(body.minutes_spent or 0)),
        overall=result.overall,
        measures={m.name: {"score": m.score, "confidence": m.confidence,
                           "basis": m.basis} for m in result.measures},
        scorer_version=SCORER_VERSION,
    )
    await row.create()

    if result.overall is not None:
        await _update_writing_mastery(models, principal.user_id, result.overall)

    xp, day_counted, streak_now = (0, False, 0)
    if result.overall is not None:
        xp, day_counted, streak_now = await _reward(
            models, principal, row.id, result.overall)

    await audit.record(principal, "writing.submitted",
                       entity="WritingPrompt", entity_id=prompt_id,
                       after={"submission_id": row.id,
                              "word_count": result.word_count,
                              "overall": result.overall,
                              "xp_awarded": xp})

    return WritingResult(
        submission_id=row.id, title=prompt.title,
        word_count=result.word_count, overall=result.overall,
        too_short=result.too_short, notes=list(result.notes),
        measures=[WritingMeasureOut(**asdict(m)) for m in result.measures],
        text=text,
        xp_awarded=xp, day_counted_now=day_counted, streak_current=streak_now,
    )


@router.get("/submissions", response_model=list[WritingResult])
async def submissions(principal: Principal,
                     models: TenantModels) -> list[WritingResult]:
    """Everything this student has written, newest first."""
    rows = await models.WritingSubmissionRow.find(
        models.WritingSubmissionRow.user_id == principal.user_id).sort(
        -models.WritingSubmissionRow.submitted_at).limit(20).to_list()

    titles = {p.id: p.title async for p in models.WritingPrompt.find_all()}

    return [
        WritingResult(
            submission_id=r.id, title=titles.get(r.prompt_id, ""),
            word_count=r.word_count, overall=r.overall,
            too_short=False, notes=[],
            measures=[
                WritingMeasureOut(name=name, score=float(v.get("score", 0)),
                                  confidence=float(v.get("confidence", 0)),
                                  basis=str(v.get("basis", "")), detail={})
                for name, v in (r.measures or {}).items()
            ],
            text=r.text,
        )
        for r in rows
    ]


async def _update_writing_mastery(models, user_id: str, overall: float) -> None:
    """Writing feeds the `grammar` mastery track for now."""
    row = await models.SkillMastery.find_one(
        models.SkillMastery.user_id == user_id,
        models.SkillMastery.skill == "grammar")

    observed = max(0.0, min(1.0, (overall - scorer.SCALE_MIN)
                            / (scorer.SCALE_MAX - scorer.SCALE_MIN)))
    if row is None:
        await models.SkillMastery(user_id=user_id, skill="grammar",
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


async def _reward(models, principal, submission_id: str,
                 overall: float) -> tuple[int, bool, int]:
    try:
        config = await game.config_for(principal.tenant_id)
        award = await game.award(
            models, config, principal.user_id, "drill_completed",
            ref_type="writing", ref_id=submission_id, target_skill="grammar",
            difficulty="at_ability",
        )
        await game.advance_quest(models, config, principal.user_id,
                                 amount=5.0, skill="grammar")
        before = await game.streak_state(models, principal.user_id)
        counted_before = before.last_qualifying_day
        await game.qualify_today(models, config, principal.user_id)
        after = await game.streak_state(models, principal.user_id)
        return (award.awarded_xp,
                after.last_qualifying_day != counted_before,
                after.current_streak)
    except Exception as exc:  # noqa: BLE001
        log.warning("writing reward hook failed for %s: %s", submission_id, exc)
        return 0, False, 0
