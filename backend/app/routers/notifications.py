"""In-app notification feed for every role.

Nothing is hand-written per event: the feed is *computed* from collections that
already exist (attempts, scheduled exams, contact messages, exam reviews), so
it cannot drift out of sync with the data and requires no manual step anywhere.
Read state is the only thing stored explicitly (``notification_reads``), keyed
by ``user_id + notification key`` so a mark-read survives reloads and devices.

Content by role:

* **student** — exam results that just landed, plus scheduled exams opening or
  closing for their institution.
* **tenant_admin** — reviews their students left recently.
* **super_admin** — open contact messages in the inbox.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from app.db import control_db
from app.deps import Principal

router = APIRouter(prefix="/notifications", tags=["notifications"])

_DAY = timedelta(days=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("")
async def notification_feed(principal: Principal) -> dict:
    """Return the caller's notifications with read flags and unread count."""
    db = control_db()
    items: list[dict] = []

    if principal.role == "student":
        items = await _student_items(db, principal)
    elif principal.role == "tenant_admin":
        items = await _tenant_admin_items(db, principal)
    elif principal.is_platform and principal.role == "super_admin":
        items = await _platform_items(db)

    read_keys = set()
    read_docs = await db.notification_reads.find(
        {"user_id": principal.user_id}).to_list()
    for rd in read_docs:
        read_keys.add(rd.get("key", ""))

    for it in items:
        it["read"] = it["key"] in read_keys
    return {"items": items,
            "unread": sum(1 for it in items if not it["read"])}


@router.patch("")
async def mark_read(body: dict, principal: Principal) -> dict:
    """Mark specific notification keys as read for this user."""
    keys = [k for k in (body.get("keys") or []) if isinstance(k, str)]
    if not keys:
        return {"ok": True}
    db = control_db()
    now = _now()
    for k in keys:
        await db.notification_reads.update_one(
            {"user_id": principal.user_id, "key": k},
            {"$setOnInsert": {"user_id": principal.user_id, "key": k,
                              "read_at": now}},
            upsert=True)
    return {"ok": True, "marked": len(keys)}


@router.post("/read-all")
async def mark_all_read(principal: Principal) -> dict:
    """Mark every currently-visible notification as read."""
    db = control_db()
    if principal.role == "student":
        items = await _student_items(db, principal)
    elif principal.role == "tenant_admin":
        items = await _tenant_admin_items(db, principal)
    elif principal.is_platform and principal.role == "super_admin":
        items = await _platform_items(db)
    else:
        items = []
    now = _now()
    for it in items:
        await db.notification_reads.update_one(
            {"user_id": principal.user_id, "key": it["key"]},
            {"$setOnInsert": {"user_id": principal.user_id, "key": it["key"],
                              "read_at": now}},
            upsert=True)
    return {"ok": True, "marked": len(items)}


# ---------------------------------------------------------------------------
# Role feeds — each helper only reads collections that exist for that role.
# ---------------------------------------------------------------------------

async def _student_items(db, principal: Principal) -> list[dict]:
    """Recent scored exam results + scheduled exams for the student."""
    now = _now()
    items: list[dict] = []
    uid = principal.user_id

    # 1. Results that landed in the last 14 days.
    attempt_docs = await db.attempts.find({
        "user_id": uid, "status": "scored",
        "scored_at": {"$gte": now - 14 * _DAY},
    }).sort("scored_at", -1).limit(8).to_list()
    if attempt_docs:
        pids = list({a.get("profile_id", "") for a in attempt_docs if a.get("profile_id")})
        names = {}
        if pids:
            async for p in db.simulation_profiles.find({"_id": {"$in": pids}}):
                names[p["_id"]] = p.get("name", "Exam")
        overall = {}
        attempt_ids = [a["_id"] for a in attempt_docs]
        sr = db.score_records.aggregate([
            {"$match": {"attempt_id": {"$in": attempt_ids},
                        "dimension": "overall", "is_shadow": {"$ne": True}}},
            {"$group": {"_id": "$attempt_id",
                        "score": {"$max": "$score"}}},
        ])
        async for r in sr:
            overall[r["_id"]] = r["score"]
        for a in attempt_docs:
            aid = a["_id"]
            items.append({
                "key": f"result:{aid}",
                "type": "exam_result",
                "title": "Result ready",
                "message": f"{names.get(a.get('profile_id', ''), 'Your exam')} — "
                           + (f"score {overall[aid]:g}" if overall.get(aid) is not None
                              else "see your report"),
                "timestamp": (a.get("scored_at") or now).isoformat(),
                "action_url": f"/results/{aid}",
            })

    # 2. Scheduled exams for this student's institution: live now, opening
    #    within 3 days, or closing within 1 day. Audience: schedules whose
    #    tenant list contains this student's institution, or that target
    #    everyone (empty / missing tenant_ids = general users too).
    if principal.tenant_id:
        audience = [{"tenant_ids": {"$in": [principal.tenant_id]}},
                    {"tenant_ids": {"$size": 0}}]
    else:
        audience = [{"tenant_ids": {"$size": 0}},
                    {"tenant_ids": {"$exists": False}}]
    sched_q: dict = {"is_active": True, "$or": audience,
                     "ends_at": {"$gte": now - _DAY}}
    scheds = await db.exam_schedules.find(sched_q).sort(
        "starts_at", 1).limit(6).to_list()
    if scheds:
        test_ids = list({s.get("exam_test_id", "") for s in scheds if s.get("exam_test_id")})
        tnames = {}
        if test_ids:
            async for t in db.exam_tests.find({"_id": {"$in": test_ids}}):
                tnames[t["_id"]] = t.get("name", "Scheduled exam")
        for s in scheds:
            start = s.get("starts_at")
            end = s.get("ends_at")
            opens_soon = start and start - now <= 3 * _DAY and start > now
            closing = end and end - now <= _DAY and end >= now
            if not (opens_soon or closing) and not (start and start <= now <= end):
                continue
            tname = tnames.get(s.get("exam_test_id", ""), s.get("name", "Scheduled exam"))
            items.append({
                "key": f"schedule:{s['_id']}",
                "type": "reminder",
                "title": "Scheduled exam" if closing or (start and start <= now) else "Exam opening soon",
                "message": f"{tname} for your institution" + (
                    " closes soon" if closing else " is live now — take it while the window is open"
                    if (start and start <= now) else f" opens {start.strftime('%d %b %H:%M')}"),
                "timestamp": (start or end or now).isoformat(),
                "action_url": "/tests",
            })

    return items


async def _tenant_admin_items(db, principal: Principal) -> list[dict]:
    """Reviews students left recently, so admins see feedback without digging."""
    now = _now()
    uids = []
    async for u in db.users.find({"tenant_id": principal.tenant_id,
                                  "role": "student"}):
        uids.append(u["_id"])
    if not uids:
        return []
    names = {}
    async for u in db.users.find({"_id": {"$in": uids}}):
        names[u["_id"]] = u.get("full_name", "A student")
    items = []
    rev_docs = await db.exam_reviews.find({
        "user_id": {"$in": uids},
        "created_at": {"$gte": now - 7 * _DAY},
    }).sort("created_at", -1).limit(10).to_list()
    for r in rev_docs:
        items.append({
            "key": f"review:{r['_id']}",
            "type": "exam_result",
            "title": "New review",
            "message": f"{names.get(r.get('user_id', ''), 'A student')} rated "
                       f"{r.get('rating', '—')}/5 · {r.get('comment') or 'no comment'}",
            "timestamp": (r.get("created_at") or now).isoformat(),
            "action_url": "/tenant/reviews",
        })
    return items


async def _platform_items(db, principal: Principal) -> list[dict]:
    """Open contact messages waiting in the super-admin inbox."""
    now = _now()
    items = []
    msgs = await db.contact_messages.find(
        {"status": {"$in": ["open", "new"]}}).sort(
        "created_at", -1).limit(10).to_list()
    for m in msgs:
        items.append({
            "key": f"contact:{m['_id']}",
            "type": "info",
            "title": "New contact message",
            "message": f"{m.get('from_name') or m.get('from_email', 'Someone')} — "
                       f"{m.get('subject', '')}",
            "timestamp": (m.get("created_at") or now).isoformat(),
            "action_url": "/platform/messages",
        })
    return items
