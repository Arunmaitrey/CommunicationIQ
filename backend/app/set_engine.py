"""Question Set Engine — admin-built sets of 10, served in rotation.

Flow:
  QUESTION BANK → question_number → QUESTION SETS (exactly 10 questions) →
  ASSESSMENT PATTERN → random set selection → random question order →
  permanent student attempt assignment

Every module's set holds QUESTION ids — reading and listening sets hold quiz
item ids (their questions carry the parent passage via ``passage_id``), writing
holds prompt ids, speaking holds task item ids, quiz holds grammar/vocabulary
item ids. That keeps the promise "one set = ten questions" true for every
skill instead of silently meaning ten passages whose question counts vary.
"""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Module prefix mapping
MODULE_PREFIXES = {
    "reading": "READ",
    "listening": "LISTEN",
    "writing": "WRITE",
    "speaking": "SPEAK",
    "quiz": "GRAM",
}

# Collection names for each module. Reading and listening questions live in
# quiz_items (linked to their passage by passage_id) — the same place the
# practice and exam flows read them from, so a set, the practice page and the
# exam can never disagree about what a question is.
MODULE_COLLECTIONS = {
    "reading": "quiz_items",
    "listening": "quiz_items",
    "writing": "writing_prompts",
    "speaking": "task_items",
    "quiz": "quiz_items",
}

# The category a quiz item must carry to belong to a module. None means the
# collection itself is already module-specific (writing prompts, task items).
MODULE_CATEGORY: dict[str, object] = {
    "reading": "reading_comprehension",
    "listening": "audio_comprehension",
    "quiz": {"$in": ["grammar", "vocabulary"]},
    "writing": None,
    "speaking": None,
}

SET_SIZE = 10


def _category_query(module: str) -> dict:
    """The category clause narrowing quiz_items to this module's bank."""
    cat = MODULE_CATEGORY.get(module)
    return {} if cat is None else {"category": cat}


def _next_set_number(prefix: str, company: str, all_sets: list) -> str:
    """Return the next unused ``<PREFIX>-SET-NNN`` for this module.

    The sequence is module-wide, not per company: ``READ-SET-006`` must name
    exactly one set, otherwise the Question Bank's company filter shows a wall
    of repeated labels. Derived from every set ever created so archived ones
    keep their numbers unique too.
    """
    taken = {s.set_number for s in all_sets}
    n = 1
    while f"{prefix}-SET-{n:03d}" in taken:
        n += 1
    return f"{prefix}-SET-{n:03d}"


async def generate_question_number(module: str, db) -> str:
    """Generate the next sequential question number for a module.

    Examples: READ-000001, WRITE-000001, LISTEN-000001, SPEAK-000001
    Uses a counter document in platform_settings to avoid duplicates.
    """
    prefix = MODULE_PREFIXES.get(module, module.upper()[:4])
    settings_coll = db["platform_settings"]
    counter_key = f"question_counter_{module}"

    # Atomically increment the counter
    result = await settings_coll.find_one_and_update(
        {"key": counter_key},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=True,
    )
    next_num = result.get("value", 1) if result else 1
    return f"{prefix}-{next_num:06d}"


async def create_empty_set(module: str, company: str = "", db=None) -> dict:
    """Create one empty draft set for this module and company.

    Sets are built by hand: the admin creates the shell, then picks the ten
    questions from the bank in the Question Bank UI. Nothing is auto-filled —
    an empty draft is the honest starting state, and it cannot go live until
    it really holds ten questions (see ``activate_set``).
    """
    from app.models.platform import QuestionSet

    if db is None:
        from app.db import control_db
        db = control_db()

    if module not in MODULE_COLLECTIONS:
        return {"created": 0, "error": f"Unknown module '{module}'"}

    prefix = MODULE_PREFIXES.get(module, module.upper()[:4])
    all_sets = await QuestionSet.find(QuestionSet.module == module).to_list(None)
    new_set = QuestionSet(
        set_number=_next_set_number(prefix, company, all_sets),
        module=module,
        company=company,
        question_ids=[],
        question_numbers=[],
        question_count=0,
        status="draft",
    )
    await new_set.create()
    log.info("Created empty set %s for %s (company=%s)",
             new_set.set_number, module, company or "general")
    return {
        "created": 1,
        "set_id": str(new_set.id),
        "set_number": new_set.set_number,
        "module": module,
        "company": company,
        "question_count": 0,
        "status": new_set.status,
    }


async def set_candidates(set_id: str, search: str = "", limit: int = 30,
                         db=None) -> dict:
    """Questions an admin may still add to this draft set.

    Same module collection, same company scope as the set (an empty company on
    the set means the general bank), published, and not already taken by another
    live set — a question sitting in two sets would be served twice to students,
    so exclusivity is enforced here rather than hoped for in the UI.
    """
    from app.models.platform import QuestionSet

    if db is None:
        from app.db import control_db
        db = control_db()

    s = await QuestionSet.get(set_id)
    if s is None:
        return {"error": "Set not found"}
    coll_name = MODULE_COLLECTIONS.get(s.module)
    if coll_name is None:
        return {"error": f"Set has unknown module '{s.module}'"}

    live = await QuestionSet.find(
        QuestionSet.status.in_(["active", "draft"])).to_list(None)
    taken: set[str] = set()
    for other in live:
        if str(other.id) != str(s.id):
            taken.update(str(q) for q in other.question_ids)

    query: dict = {"status": "published", "_id": {"$nin": list(taken)}}
    query.update(_category_query(s.module))
    if s.company:
        query["company"] = s.company
    else:
        query["company"] = {"$in": ["", "general", "General", "GENERAL", None]}

    find = db[coll_name].find(query)
    if search:
        find = db[coll_name].find(
            {**query,
             "$or": [{"stem": {"$regex": search, "$options": "i"}},
                     {"title": {"$regex": search, "$options": "i"}},
                     {"prompt_text": {"$regex": search, "$options": "i"}},
                     {"prompt": {"$regex": search, "$options": "i"}},
                     {"question_number": {"$regex": search, "$options": "i"}}]})
    docs = await find.limit(max(1, min(limit, 100))).to_list(limit)
    out = [{
        "id": str(d["_id"]),
        "question_number": d.get("question_number", ""),
        "label": (d.get("stem") or d.get("title") or d.get("prompt_text")
                  or d.get("prompt") or ""),
        "kind": (d.get("category") or d.get("kind") or d.get("task_type") or ""),
        "difficulty": float(d.get("difficulty") or 0),
    } for d in docs]
    return {"candidates": out, "count": len(out)}


async def add_question_to_set(set_id: str, question_id: str, db=None) -> dict:
    """Add one question to a draft set, enforcing every rule a set lives by.

    Ten is the ceiling (the unit assessments assign), the set must still be a
    draft, the question must belong to the set's module collection and company,
    and no question may sit in two live sets. The response says which rule
    failed so the UI can show a real message.
    """
    from app.models.platform import QuestionSet

    if db is None:
        from app.db import control_db
        db = control_db()

    s = await QuestionSet.get(set_id)
    if s is None:
        return {"ok": False, "error": "Set not found"}
    if s.status != "draft":
        return {"ok": False, "error": "Only draft sets can be edited"}
    if len(s.question_ids) >= SET_SIZE:
        return {"ok": False, "error": f"This set already holds {SET_SIZE} questions"}

    coll_name = MODULE_COLLECTIONS.get(s.module)
    if coll_name is None:
        return {"ok": False, "error": f"Set has unknown module '{s.module}'"}
    q = await db[coll_name].find_one({"_id": str(question_id)})
    if q is None:
        return {"ok": False, "error": "Question not found in this module's bank"}
    if q.get("status") != "published":
        return {"ok": False, "error": "Question is not published"}
    # The question must be the right kind for this module: a grammar MCQ in a
    # reading set would put grammar practice under the reading tab.
    cat_query = _category_query(s.module)
    if "category" in cat_query and q.get("category") != cat_query["category"]:
        return {"ok": False,
                "error": (f"Question category '{q.get('category')}' does not "
                          f"belong in a {s.module} set")}
    if "$in" in cat_query and q.get("category") not in cat_query["$in"]["$in"]:
        return {"ok": False,
                "error": (f"Question category '{q.get('category')}' does not "
                          f"belong in a {s.module} set")}
    q_company = q.get("company") or ""
    if q_company.lower() in ("general", "all"):
        q_company = ""
    if q_company != (s.company or ""):
        want = s.company or "the general bank"
        return {"ok": False,
                "error": f"Question belongs to '{q_company or 'general'}', not {want}"}

    taken_by = None
    live = await QuestionSet.find(
        QuestionSet.status.in_(["active", "draft"])).to_list(None)
    for other in live:
        if str(other.id) != str(s.id) and str(question_id) in [
                str(x) for x in other.question_ids]:
            taken_by = other.set_number
            break
    if taken_by:
        return {"ok": False, "error": f"Already in set {taken_by}"}
    if str(question_id) in [str(x) for x in s.question_ids]:
        return {"ok": False, "error": "Already in this set"}

    s.question_ids.append(str(question_id))
    s.question_numbers.append(q.get("question_number", ""))
    s.question_count = len(s.question_ids)
    s.updated_at = datetime.now(timezone.utc)
    await s.save()
    return {"ok": True, "question_count": s.question_count,
            "set_number": s.set_number}


async def remove_question_from_set(set_id: str, question_id: str,
                                   db=None) -> dict:
    """Take one question back out of a draft set."""
    from app.models.platform import QuestionSet

    if db is None:
        from app.db import control_db
        db = control_db()

    s = await QuestionSet.get(set_id)
    if s is None:
        return {"ok": False, "error": "Set not found"}
    if s.status != "draft":
        return {"ok": False, "error": "Only draft sets can be edited"}
    ids = [str(x) for x in s.question_ids]
    if str(question_id) not in ids:
        return {"ok": False, "error": "Question is not in this set"}
    idx = ids.index(str(question_id))
    s.question_ids.pop(idx)
    if idx < len(s.question_numbers):
        s.question_numbers.pop(idx)
    s.question_count = len(s.question_ids)
    s.updated_at = datetime.now(timezone.utc)
    await s.save()
    return {"ok": True, "question_count": s.question_count}


async def activate_set(set_id: str, db=None) -> dict:
    """Make a draft set live — but only once it genuinely holds ten questions.

    A half-full set would hand a student fewer questions than the pattern
    promises, so ten is a hard gate, not a warning.
    """
    from app.models.platform import QuestionSet

    if db is None:
        from app.db import control_db
        db = control_db()

    s = await QuestionSet.get(set_id)
    if s is None:
        return {"ok": False, "error": "Set not found"}
    if s.status == "active":
        return {"ok": False, "error": "Set is already active"}
    if len(s.question_ids) != SET_SIZE:
        return {"ok": False,
                "error": (f"A set needs exactly {SET_SIZE} questions; "
                          f"this one has {len(s.question_ids)}.")}
    # Re-resolve at activation time: a question deleted while the draft sat
    # open would otherwise go live as a hole.
    coll_name = MODULE_COLLECTIONS.get(s.module)
    docs = await db[coll_name].find(
        {"_id": {"$in": [str(x) for x in s.question_ids]}}
    ).to_list(None)
    if len(docs) != SET_SIZE:
        return {"ok": False,
                "error": (f"{SET_SIZE - len(docs)} question(s) in this set no longer "
                          f"exist in the bank — remove them first.")}
    # Validate question content quality
    issues = []
    for d in docs:
        qid = str(d.get("_id", ""))
        if s.module == "quiz":
            stem = d.get("stem", "")
            options = d.get("options", [])
            ci = d.get("correct_index", 0)
            if not stem:
                issues.append(f"Question {qid[:8]}: empty stem")
            if len(options) < 2:
                issues.append(f"Question {qid[:8]}: needs at least 2 options (has {len(options)})")
            if not isinstance(ci, int) or ci < 0 or ci >= len(options):
                issues.append(f"Question {qid[:8]}: correct_index {ci} out of range for {len(options)} options")
        elif s.module == "reading":
            if not d.get("body", "").strip():
                issues.append(f"Passage {qid[:8]}: empty body text")
        elif s.module == "listening":
            if not d.get("transcript", "").strip():
                issues.append(f"Passage {qid[:8]}: empty transcript")
        elif s.module == "speaking":
            if not d.get("prompt_text", "").strip():
                issues.append(f"Task {qid[:8]}: empty prompt text")
        elif s.module == "writing":
            if not d.get("prompt", "").strip():
                issues.append(f"Prompt {qid[:8]}: empty prompt text")
    if issues:
        return {"ok": False,
                "error": f"Cannot activate — {len(issues)} question(s) have issues: " +
                         "; ".join(issues[:5]) + ("..." if len(issues) > 5 else "")}
    s.status = "active"
    s.question_count = SET_SIZE
    s.updated_at = datetime.now(timezone.utc)
    await s.save()
    log.info("Activated set %s (%s) with %d questions",
             s.set_number, s.module, SET_SIZE)
    return {"ok": True, "set_number": s.set_number, "status": s.status}


async def get_available_sets(module: str, company: str = "", db=None) -> list:
    """Get active sets for a module, filtered by company.

    When company is empty, returns only general (company="") sets so
    company-specific sets don't leak to other companies' students.
    """
    from app.models.platform import QuestionSet

    query = {
        "module": module,
        "status": "active",
    }
    if company:
        query["company"] = company
    else:
        # No company context — return only general sets
        query["company"] = ""

    sets = await QuestionSet.find(query).to_list(None)
    return sets


async def get_set_status_summary(db=None) -> dict:
    """Per-module set availability: active, drafts, and served question depth.

    Drives the Question Bank's set-coverage cards. "Questions per set" is
    always exactly ten for an active set — that is the promise — so the
    interesting number is how many active sets each module can serve.
    """
    from app.models.platform import QuestionSet

    if db is None:
        from app.db import control_db
        db = control_db()

    rows = await db.question_sets.find({}).to_list(20000)
    summary: dict[str, dict] = {}
    for r in rows:
        m = r.get("module") or ""
        s = summary.setdefault(m, {"module": m, "active": 0, "draft": 0,
                                   "archived": 0, "questions": 0})
        status = r.get("status") or ""
        if status in s:
            s[status] += 1
        if status == "active":
            s["questions"] += int(r.get("question_count") or 0)
    return {"modules": list(summary.values())}


async def assign_sets_for_attempt(
    assessment_config: dict,
    company: str = "",
    db=None,
) -> dict:
    """Select random sets for a student attempt."""
    raise NotImplementedError("Superseded by practice_engine rotation")