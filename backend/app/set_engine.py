"""Question Set Engine — auto-creates sets of 10, assigns them to students.

Flow:
  QUESTION BANK → question_number → QUESTION SETS (exactly 10) →
  ASSESSMENT PATTERN → random set selection → random question order →
  permanent student attempt assignment
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

# Collection names for each module
MODULE_COLLECTIONS = {
    "reading": "reading_passages",
    "listening": "listening_passages",
    "writing": "writing_prompts",
    "speaking": "task_items",
    "quiz": "quiz_items",
}

SET_SIZE = 10


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


async def auto_create_sets(module: str, db) -> list[dict]:
    """Check if enough questions exist to create new sets of 10.

    Called after every question creation. Groups unassigned questions into
    sets of exactly 10. Returns list of created sets.
    """
    from app.models.platform import QuestionSet

    prefix = MODULE_PREFIXES.get(module, module.upper()[:4])
    collection_name = MODULE_COLLECTIONS.get(module, "quiz_items")
    coll = db[collection_name]

    # Get all published questions in this module
    all_questions = await coll.find(
        {"status": "published"}
    ).to_list(None)

    if len(all_questions) < SET_SIZE:
        return []

    # Get IDs already in sets
    existing_sets = await QuestionSet.find(
        QuestionSet.module == module,
    ).to_list(None)
    assigned_ids = set()
    for s in existing_sets:
        assigned_ids.update(s.question_ids)

    # Filter to unassigned questions
    unassigned = [q for q in all_questions if str(q["_id"]) not in assigned_ids]

    created_sets = []
    while len(unassigned) >= SET_SIZE:
        batch = unassigned[:SET_SIZE]
        unassigned = unassigned[SET_SIZE:]

        question_ids = [str(q["_id"]) for q in batch]
        question_numbers = [q.get("question_number", "") for q in batch]

        # Determine set number
        existing_count = len(existing_sets) + len(created_sets)
        set_number = f"{prefix}SET-{existing_count + 1:03d}"

        new_set = QuestionSet(
            set_number=set_number,
            module=module,
            company=batch[0].get("company", ""),
            question_ids=question_ids,
            question_numbers=question_numbers,
            question_count=SET_SIZE,
            status="active",  # Auto-activate
            is_used=False,
            usage_count=0,
        )
        await new_set.create()
        existing_sets.append(new_set)
        created_sets.append({
            "set_id": str(new_set.id),
            "set_number": set_number,
            "module": module,
            "question_count": SET_SIZE,
            "status": "active",
        })
        log.info("Auto-created set %s for module %s with %d questions",
                 set_number, module, SET_SIZE)

    return created_sets


async def get_available_sets(module: str, company: str = "", db=None) -> list:
    """Get all active sets for a module, optionally filtered by company."""
    from app.models.platform import QuestionSet

    query = {
        "module": module,
        "status": "active",
    }
    if company:
        query["company"] = company

    sets = await QuestionSet.find(query).to_list(None)
    return sets


async def assign_sets_for_attempt(
    assessment_config: dict,
    company: str = "",
    db=None,
) -> dict:
    """Select random sets for a student attempt.

    Args:
        assessment_config: dict like {"reading": 10, "writing": 10, "listening": 10, "speaking": 10}
        company: company filter (empty for general)

    Returns:
        dict with assigned set IDs and question IDs per module
    """
    from app.models.platform import QuestionSet

    assigned_sets = {}
    assigned_questions = {}

    for module, required_count in assessment_config.items():
        if required_count <= 0:
            continue

        # Find active sets for this module
        query = {"module": module, "status": "active"}
        if company:
            query["company"] = company

        available_sets = await QuestionSet.find(query).to_list(None)

        # Filter sets that have enough questions
        valid_sets = [s for s in available_sets if len(s.question_ids) >= required_count]

        if not valid_sets:
            raise ValueError(
                f"Insufficient active {module} question sets available. "
                f"Need {required_count} questions, but no valid sets found."
            )

        # Level 1: Random set selection
        selected_set = random.choice(valid_sets)

        # Level 2: Random question order inside the set
        question_ids = list(selected_set.question_ids)
        random.shuffle(question_ids)

        # Take only the required number
        final_question_ids = question_ids[:required_count]

        # Update set usage
        selected_set.usage_count += 1
        selected_set.is_used = True
        selected_set.last_used_at = datetime.now(timezone.utc)
        await selected_set.save()

        assigned_sets[module] = str(selected_set.id)
        assigned_questions[module] = final_question_ids

    return {
        "assigned_sets": assigned_sets,
        "assigned_questions": assigned_questions,
    }


async def get_set_status_summary(db=None) -> dict:
    """Get summary of set availability per module for admin dashboard."""
    from app.models.platform import QuestionSet

    summary = {}
    for module in MODULE_PREFIXES:
        sets = await QuestionSet.find({"module": module}).to_list(None)
        active_sets = [s for s in sets if s.status == "active"]
        total_questions = sum(len(s.question_ids) for s in active_sets)

        summary[module] = {
            "total_sets": len(sets),
            "active_sets": len(active_sets),
            "questions_available": total_questions,
        }

    return summary
