"""Operational visibility for narration jobs — counts, health, cost.

Answers the questions operations actually asks: how many are pending, ready,
failed; why are they failing; what is it costing. Aggregated across tenants,
and it reads only the job table — never any content, transcript or prompt, so
the metrics themselves carry no student data.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.db import platform_sessionmaker, tenant_sessionmaker
from app.models.platform import Tenant
from app.models.tenant import AttemptNarration


async def _tenant_metrics(slug: str) -> dict:
    async with tenant_sessionmaker(slug)() as s:
        status_rows = (await s.execute(
            select(AttemptNarration.status, func.count())
            .group_by(AttemptNarration.status))).all()
        by_status = {status: n for status, n in status_rows}

        error_rows = (await s.execute(
            select(AttemptNarration.last_error_category, func.count())
            .where(AttemptNarration.status == "failed")
            .group_by(AttemptNarration.last_error_category))).all()
        failures = {cat or "unknown": n for cat, n in error_rows}

        # Cost/latency over ready rows only.
        agg = (await s.execute(
            select(func.coalesce(func.sum(AttemptNarration.input_tokens), 0),
                   func.coalesce(func.sum(AttemptNarration.output_tokens), 0),
                   func.coalesce(func.avg(AttemptNarration.provider_latency_ms), 0),
                   func.coalesce(func.avg(AttemptNarration.attempt_count), 0))
            .where(AttemptNarration.status == "ready"))).first()

    ready = by_status.get("ready", 0)
    failed = by_status.get("failed", 0)
    total_terminal = ready + failed
    return {
        "by_status": by_status,
        "failures": failures,
        "input_tokens": int(agg[0]),
        "output_tokens": int(agg[1]),
        "avg_latency_ms": round(float(agg[2]), 1),
        "avg_attempts": round(float(agg[3]), 2),
        "success_rate": round(ready / total_terminal, 3) if total_terminal else None,
    }


async def collect() -> dict:
    """Estate-wide narration metrics, per tenant and rolled up."""
    async with platform_sessionmaker()() as s:
        slugs = list((await s.execute(select(Tenant.slug))).scalars().all())

    per_tenant = {slug: await _tenant_metrics(slug) for slug in slugs}
    roll = {"pending": 0, "processing": 0, "retry_pending": 0,
            "ready": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0}
    for m in per_tenant.values():
        for k, v in m["by_status"].items():
            roll[k] = roll.get(k, 0) + v
        roll["input_tokens"] += m["input_tokens"]
        roll["output_tokens"] += m["output_tokens"]
    return {"totals": roll, "tenants": per_tenant}
