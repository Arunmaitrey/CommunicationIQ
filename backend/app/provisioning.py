"""Institution management — all data lives in the single CommunicationIQ DB.

Tenant isolation is by ``tenant_id`` field on documents, not separate databases.
"""
from __future__ import annotations

import re

from app.db import (control_db, ensure_tenant_models, get_platform_bundle)
from app.models.platform import TenantUserDirectory

SLUG = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def validate_slug(slug: str) -> str:
    if not SLUG.match(slug):
        raise ValueError(
            f"invalid tenant slug {slug!r} — lowercase letters, digits and underscores only"
        )
    return slug


def tenant_schema_name(slug: str) -> str:
    return slug


async def create_tenant_schema(slug: str) -> str:
    """Ensure tenant models exist — no-op now since all data is in one DB."""
    validate_slug(slug)
    await ensure_tenant_models(slug)
    return slug


async def drop_tenant_schema(slug: str, *, purge_media: bool = True) -> int:
    """Remove an institution's data by deleting tenant_id-matching documents."""
    validate_slug(slug)
    from app.models.platform import Tenant
    from app.models.tenant import (User, Cohort, CohortMember, Invitation,
                                    SimulationProfile, ProfileSection, Assignment,
                                    Attempt, Response, ResponseAudio)

    # Find the tenant to get its id
    tenant = await Tenant.find_one(Tenant.slug == slug)
    if tenant is None:
        return 0

    tenant_id = str(tenant.id)
    db = control_db()

    # Delete tenant_id-marked documents from shared collections
    for coll_name in ["users", "cohorts", "simulation_profiles", "profile_sections",
                       "attempts", "responses", "response_audio", "assignments",
                       "invitations"]:
        await db[coll_name].delete_many({"tenant_id": tenant_id})

    # Delete from TenantUserDirectory
    platform_bundle = await get_platform_bundle()
    await platform_bundle.TenantUserDirectory.find(
        {"tenant_slug": slug}
    ).delete()

    # Delete the tenant record itself
    await tenant.delete()

    if not purge_media:
        return 0
    storage = None
    removed = 0
    try:
        from app.storage import get_storage, tenant_prefixes
        storage = get_storage()
        removed = sum(storage.purge_prefix(prefix) for prefix in tenant_prefixes(slug))
    except Exception:
        pass
    return removed


async def upgrade_tenant_schema(slug: str) -> list[str]:
    validate_slug(slug)
    await ensure_tenant_models(slug)
    return []


async def upgrade_all_tenant_schemas() -> dict[str, list[str]]:
    platform = platform_sessionmaker()
    async with platform() as platform_bundle:
        slugs = [t.slug async for t in platform_bundle.Tenant.find_all()]
    return {slug: await upgrade_tenant_schema(slug) for slug in slugs}


async def tenant_schema_exists(slug: str) -> bool:
    validate_slug(slug)
    from app.models.platform import Tenant
    return await Tenant.find_one(Tenant.slug == slug) is not None


async def missing_columns(slug: str) -> list[str]:
    return []


async def upgrade_everything() -> dict[str, list[str]]:
    return await upgrade_all_tenant_schemas()


if __name__ == "__main__":
    import asyncio
    for slug, columns in asyncio.run(upgrade_everything()).items():
        print(f"{slug}: {', '.join(columns) if columns else 'already current'}")
