"""Subscription enforcement for general users.

General users (slug == "general") must have an active plan to access
practice and exam features. Institutional users bypass this check.
Free plan allows only 1 attempt total; after that the user must upgrade.
"""
from __future__ import annotations

from fastapi import HTTPException, status

from app.db import control_db
from app.deps import Principal


async def check_subscription(principal: Principal) -> bool:
    """Check if a general user has an active subscription. Returns True if allowed."""
    db = control_db()
    tenant_doc = await db.tenants.find_one({"_id": principal.tenant_id}) if principal.tenant_id else None

    if not tenant_doc:
        return True  # No tenant = institutional user = bypass

    # General users (slug == "general") need a plan
    if tenant_doc.get("slug") != "general":
        return True  # Institutional users bypass check

    # Check if plan is assigned
    plan_id = tenant_doc.get("plan_id")
    if not plan_id:
        return False  # No plan = blocked

    # Check if plan is active
    plan_doc = await db.plans.find_one({"_id": plan_id})
    if not plan_doc:
        return False

    if not plan_doc.get("is_active", True):
        return False

    # Free plan single-use enforcement
    if plan_doc.get("slug") == "free-trial":
        # Count attempts for this user, scoped by tenant
        attempts_count = await db.get_collection("attempts").count_documents(
            {"user_id": principal.user_id, "tenant_id": principal.tenant_id}
        )
        max_free = plan_doc.get("max_exams_per_day", 1)
        if attempts_count >= max_free:
            return False  # Free plan exhausted, must upgrade

    return True


async def require_subscription(principal: Principal) -> None:
    """Raise HTTP 403 if general user has no active subscription."""
    allowed = await check_subscription(principal)
    if not allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your free plan has been used. Please upgrade your plan at /plans to continue."
        )
