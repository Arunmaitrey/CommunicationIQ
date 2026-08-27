"""Deleting recordings when their time is up.

Run with ``python -m app.retention`` (add ``--dry-run`` to see what would go).

This exists in M1 rather than "later" because retention is not a feature you
add to a store of student voice recordings after the fact — DPDP treats voice
as adjacent to biometric data, and the honest version of "kept for 30 days" is
a job that actually deletes on day 31.

What it deletes is the audio. The FeatureRecord — transcript, timings, pause
structure — survives, so a student's diagnosis and their progress history stay
intact after their voice is gone. That split is the whole reason the two are
separate tables.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from app.sqlbridge import select

from app.db import platform_sessionmaker, tenant_sessionmaker
from app.models.platform import AuditLog, Tenant
from app.models.tenant import ResponseAudio
from app.storage import get_storage


async def sweep_tenant(slug: str, *, dry_run: bool = False) -> tuple[int, int]:
    """Delete expired recordings for one institution.

    Returns (deleted, bytes_freed).
    """
    storage = get_storage()
    now = datetime.now(timezone.utc)
    deleted = 0
    freed = 0

    async with tenant_sessionmaker(slug)() as session:
        expired = list((await session.execute(
            select(ResponseAudio)
            .where(ResponseAudio.delete_after.is_not(None),
                   ResponseAudio.delete_after <= now,
                   ResponseAudio.deleted_at.is_(None))
        )).scalars().all())

        for row in expired:
            if dry_run:
                deleted += 1
                freed += row.bytes
                continue
            try:
                storage.delete(row.storage_key)
            except (ValueError, OSError):
                # A missing or unreadable object is still expired. Marking the
                # row is what makes the deletion true from the platform's
                # point of view, and leaving it unmarked would retry forever.
                pass
            row.deleted_at = now
            # The key is cleared so nothing can be read back through it, but
            # the row stays: "this recording existed and was deleted on this
            # date" is exactly what a deletion request needs to be able to
            # answer later.
            row.storage_key = ""
            deleted += 1
            freed += row.bytes

        if not dry_run:
            await session.commit()

    return deleted, freed


async def sweep_all(*, dry_run: bool = False) -> dict[str, tuple[int, int]]:
    async with platform_sessionmaker()() as session:
        tenants = list((await session.execute(select(Tenant))).scalars().all())

    results: dict[str, tuple[int, int]] = {}
    for tenant in tenants:
        results[tenant.slug] = await sweep_tenant(tenant.slug, dry_run=dry_run)

    if not dry_run:
        total = sum(count for count, _ in results.values())
        if total:
            async with platform_sessionmaker()() as session:
                session.add(AuditLog(
                    actor_type="system", actor_label="retention-sweeper",
                    action="recordings.expired_deleted", entity="ResponseAudio",
                    after={slug: {"deleted": c, "bytes": b}
                           for slug, (c, b) in results.items() if c},
                ))
                await session.commit()

    return results


async def _main(dry_run: bool) -> None:
    results = await sweep_all(dry_run=dry_run)
    prefix = "would delete" if dry_run else "deleted"
    for slug, (count, freed) in results.items():
        print(f"  {slug}: {prefix} {count} recordings ({freed / 1024:.0f} KB)")
    total = sum(c for c, _ in results.values())
    print(f"{prefix}: {total} recordings across {len(results)} institutions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete expired recordings")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be deleted, change nothing")
    args = parser.parse_args()
    asyncio.run(_main(args.dry_run))
