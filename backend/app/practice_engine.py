"""Practice rotation over Question Sets.

A practice session is a set, not a random sample of the bank. The engine picks
the student's next unused set for that skill (set 1 first, then set 2, ...),
marks it as theirs, and never serves the same set to the same student again
until every other set for that skill has been completed — the loop restarts
only when the rotation is exhausted.

Questions inside a set are shuffled on every sitting (so the ten do not arrive
in the same order twice), but the served payload carries its position, so the
student always sees Q1..Q10 regardless of internal order.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

from app.models.platform import QuestionSet
from app.models.tenant import PracticeSitting

# Skill -> module key in question_sets (same names by design).
SKILL_MODULES = {
    "reading": "reading",
    "listening": "listening",
    "writing": "writing",
    "speaking": "speaking",
    "quiz": "quiz",
}


async def next_set_for_practice(user_id: str, skill: str,
                                company: str = "", db=None) -> dict | None:
    """Pick this student's next practice set for a skill.

    Rotation rule: sets already completed by this student (for this skill and
    scope) are skipped; among the rest, the lowest-numbered unused set is
    served — so a new student gets set 1, and after completing it, set 2. When
    every set has been completed, the rotation restarts (the sets are then
    re-shuffled by the caller anyway). A sitting left open from an earlier
    crash is resumed rather than replaced, so an abandoned set is never lost
    and never double-served.
    """
    if db is None:
        from app.db import control_db
        db = control_db()

    module = SKILL_MODULES.get(skill)
    if not module:
        return None

    # Resume an open sitting first — one open sitting per student+skill.
    open_sitting = await PracticeSitting.find_one(
        PracticeSitting.user_id == user_id,
        PracticeSitting.skill == skill,
        PracticeSitting.status == "open",
    )
    if open_sitting:
        s = await QuestionSet.get(open_sitting.set_id)
        if s is not None:
            return {
                "sitting_id": str(open_sitting.id),
                "set_id": str(s.id),
                "set_number": s.set_number,
                "question_ids": [str(x) for x in open_sitting.question_ids],
                "resumed": True,
            }
        # Set disappeared; close the stale sitting and re-rotate.
        open_sitting.status = "completed"
        open_sitting.completed_at = datetime.now(timezone.utc)
        await open_sitting.save()

    # Every live set for this skill+company, in creation order.
    query = {"module": module, "status": "active"}
    query["company"] = company or ""
    sets = await db.question_sets.find(query).sort("_id", 1).to_list(5000)
    if not sets:
        return None

    completed = await PracticeSitting.find(
        PracticeSitting.user_id == user_id,
        PracticeSitting.skill == skill,
        PracticeSitting.status == "completed",
    ).to_list(None)
    done_ids = {s.set_id for s in completed}

    # Sets not yet completed by this student, lowest number first.
    fresh = [s for s in sets if str(s["_id"]) not in done_ids]
    pool = fresh if fresh else sets  # rotation exhausted: start over
    chosen = pool[0] if fresh else random.choice(pool)

    question_ids = [str(q) for q in chosen.get("question_ids", [])]
    random.shuffle(question_ids)  # serve order differs every sitting

    sitting = PracticeSitting(
        user_id=user_id,
        skill=skill,
        set_id=str(chosen["_id"]),
        set_number=chosen.get("set_number", ""),
        question_ids=question_ids,
        status="open",
    )
    await sitting.create()
    return {
        "sitting_id": str(sitting.id),
        "set_id": str(chosen["_id"]),
        "set_number": chosen.get("set_number", ""),
        "question_ids": question_ids,
        "resumed": False,
    }


async def complete_sitting(sitting_id: str, user_id: str, score: float | None,
                           db=None) -> dict:
    """Mark a sitting completed — this is what keeps the rotation honest.

    A sitting only leaves the rotation when it is actually finished: the flag
    flips on submit, not on start, so an abandoned practice releases its set
    back and the student is not short-changed a set they never sat.
    """
    if db is None:
        from app.db import control_db
        db = control_db()

    sitting = await PracticeSitting.get(sitting_id)
    if sitting is None or sitting.user_id != user_id:
        return {"ok": False, "error": "Sitting not found"}
    if sitting.status == "completed":
        return {"ok": True, "already": True}
    sitting.status = "completed"
    sitting.score = score
    sitting.completed_at = datetime.now(timezone.utc)
    await sitting.save()
    return {"ok": True, "already": False}
