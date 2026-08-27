"""Operational visibility for narration jobs — counts, health, cost.

Answers the questions operations actually asks: how many are pending, ready,
failed; why are they failing; what is it costing. Aggregated across tenants,
and it reads only the job table — never any content, transcript or prompt, so
the metrics themselves carry no student data.
"""
from __future__ import annotations

from collections import Counter

from app.sqlbridge import select

from app.db import ensure_tenant_models, platform_sessionmaker
from app.models.platform import Tenant


async def _tenant_metrics(slug: str) -> dict:
    models = await ensure_tenant_models(slug)
    jobs = await models.AttemptNarration.find_all().to_list()

    by_status = Counter(j.status for j in jobs)
    failures = Counter(
        (j.last_error_category or "unknown")
        for j in jobs if j.status == "failed")

    # Cost/latency over ready rows only. coalesce(x, 0) becomes a plain
    # default for an empty set.
    ready = [j for j in jobs if j.status == "ready"]
    input_tokens = sum(j.input_tokens or 0 for j in ready)
    output_tokens = sum(j.output_tokens or 0 for j in ready)
    avg_latency = (sum(j.provider_latency_ms or 0 for j in ready) / len(ready)
                   if ready else 0.0)
    avg_attempts = (sum(j.attempt_count or 0 for j in ready) / len(ready)
                    if ready else 0.0)

    ready_n = by_status.get("ready", 0)
    failed_n = by_status.get("failed", 0)
    total_terminal = ready_n + failed_n
    return {
        "by_status": dict(by_status),
        "failures": dict(failures),
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "avg_latency_ms": round(float(avg_latency), 1),
        "avg_attempts": round(float(avg_attempts), 2),
        "success_rate": round(ready_n / total_terminal, 3) if total_terminal else None,
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
