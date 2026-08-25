"""The narration recovery worker.

Two ways in, one body:
  * the in-process sweeper started in the app lifespan (settings-gated), which
    is the restart-safety net — a job left pending or half-processed by a crash
    is picked up on the next tick;
  * ``python -m app.narration`` for running it out of process, the same shape
    as ``python -m app.retention``.

The fast path is separate: the moment an attempt is scored, a BackgroundTask
calls kick() to generate immediately. The sweeper exists so that nothing is
*lost* if that fast path never ran or died mid-flight — durability does not
depend on the process that created the job staying alive.
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from app.config import settings
from app.models.platform import Tenant
from app.narration import service

log = logging.getLogger("narration.worker")


async def tick_tenant(slug: str, *, batch: int | None = None) -> dict[str, int]:
    batch = batch or settings.narration_worker_batch
    counts = {"claimed": 0, "ready": 0, "retry_pending": 0, "failed": 0}
    ids = await service.claim_due(slug, batch=batch)
    counts["claimed"] = len(ids)
    for narration_id in ids:
        outcome = await service.generate_one(slug, narration_id)
        if outcome in counts:
            counts[outcome] += 1
    return counts


async def tick_all(*, batch: int | None = None) -> dict[str, dict[str, int]]:
    slugs = [doc.slug for doc in await Tenant.find().to_list()]
    return {slug: await tick_tenant(slug, batch=batch) for slug in slugs}


async def kick(slug: str, narration_id: str) -> str:
    won = await service.claim_one(slug, narration_id)
    if not won:
        return "not_claimed"
    return await service.generate_one(slug, narration_id)


async def run_forever() -> None:
    interval = settings.narration_worker_interval_s
    log.info("narration sweeper started (interval=%ss)", interval)
    while True:
        try:
            await tick_all()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("narration sweeper tick failed")
        await asyncio.sleep(interval)


def _main() -> None:
    parser = argparse.ArgumentParser(description="Generate pending AI narrations.")
    parser.add_argument("--once", action="store_true",
                        help="run a single pass and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.once:
        print(asyncio.run(tick_all()))
    else:
        asyncio.run(run_forever())


if __name__ == "__main__":
    _main()
