"""Operational visibility for narration jobs — counts, health, cost.

Answers the questions operations actually asks: how many are pending, ready,
failed; why are they failing; what is it costing. Aggregated across tenants,
and it reads only the job table — never any content, transcript or prompt, so
the metrics themselves carry no student data.
"""
from __future__ import annotations

from collections import Counter

from app.db import ensure_tenant_models, platform_sessionmaker, select
from app.models.platform import Tenant


async def _tenant_metrics(slug: str) -> dict:
    # This is an operational-metrics read over a job table, not a scoring or
    # student-data path — a plain fetch-then-aggregate-in-Python is simple
    # and correct here, rather than teaching the query shim a MongoDB
    # aggregation pipeline it has exactly one caller for.
    models = await ensure_tenant_models(slug)
    rows = await models.AttemptNarration.find_all().to_list()

    by_status = Counter(r.status for r in rows)
    failures = Counter((r.last_error_category or "unknown")
                       for r in rows if r.status == "failed")

    ready_rows = [r for r in rows if r.status == "ready"]
    input_tokens = sum(r.input_tokens or 0 for r in ready_rows)
    output_tokens = sum(r.output_tokens or 0 for r in ready_rows)
    avg_latency = (sum(r.provider_latency_ms or 0 for r in ready_rows) / len(ready_rows)
                   if ready_rows else 0)
    avg_attempts = (sum(r.attempt_count or 0 for r in ready_rows) / len(ready_rows)
                    if ready_rows else 0)

    ready = by_status.get("ready", 0)
    failed = by_status.get("failed", 0)
    total_terminal = ready + failed
    return {
        "by_status": dict(by_status),
        "failures": dict(failures),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "avg_latency_ms": round(float(avg_latency), 1),
        "avg_attempts": round(float(avg_attempts), 2),
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
