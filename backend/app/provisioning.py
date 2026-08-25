"""Creating and destroying institution databases.

Provisioning is the only code allowed to name a real institution database.
Everything else speaks the ``tenant`` placeholder (here: asks for the bundle
bound to ``tenant_<slug>``) and Beanie routes it to the right database.
"""
from __future__ import annotations

import re

from app.db import (client, ensure_tenant_models, get_platform_bundle,
                    tenant_db, tenant_db_name)
from app.models.platform import TenantUserDirectory

SLUG = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def validate_slug(slug: str) -> str:
    """A slug becomes part of a database name, so it is validated, never escaped."""
    if not SLUG.match(slug):
        raise ValueError(
            f"invalid tenant slug {slug!r} — lowercase letters, digits and underscores only"
        )
    return slug


def tenant_schema_name(slug: str) -> str:
    """Kept for call-site compatibility; the database name is the schema name."""
    return tenant_db_name(slug)


async def create_tenant_schema(slug: str) -> str:
    """Create ``tenant_<slug>`` and bind its documents (collections + indexes)."""
    validate_slug(slug)
    # Touching the bundle creates the database's collections and indexes on
    # first use. The database itself is created implicitly by MongoDB on the
    # first write.
    await ensure_tenant_models(slug)
    return tenant_db_name(slug)


async def drop_tenant_schema(slug: str, *, purge_media: bool = True) -> int:
    """Remove an institution's database and its sign-in routing (offboarding)."""
    validate_slug(slug)
    name = tenant_db_name(slug)
    await client.drop_database(name)

    # Use the platform bundle to access the properly initialized Beanie models
    platform_bundle = await get_platform_bundle()
    await platform_bundle.TenantUserDirectory.find(
        platform_bundle.TenantUserDirectory.tenant_slug == slug
    ).delete()

    if not purge_media:
        return 0
    storage = None
    removed = 0
    try:
        from app.storage import get_storage, tenant_prefixes
        storage = get_storage()
        removed = sum(storage.purge_prefix(prefix) for prefix in tenant_prefixes(slug))
    except Exception:  # noqa: BLE001 — media purge is best-effort
        pass
    return removed


# Mongo is schemaless and collections/indexes are created by
# ``ensure_tenant_models``. These upgrade helpers therefore report "nothing to
# do" while keeping the names the platform expects.

async def upgrade_tenant_schema(slug: str) -> list[str]:
    validate_slug(slug)
    await ensure_tenant_models(slug)
    return []


async def upgrade_all_tenant_schemas() -> dict[str, list[str]]:
    """Bring every provisioned institution's indexes current."""
    platform = platform_sessionmaker()
    async with platform() as platform_bundle:
        slugs = [t.slug async for t in platform_bundle.Tenant.find_all()]
    return {slug: await upgrade_tenant_schema(slug) for slug in slugs}


async def tenant_schema_exists(slug: str) -> bool:
    validate_slug(slug)
    db = tenant_db(slug)
    names = await db.list_collection_names()
    return bool(names)


async def missing_columns(slug: str) -> list[str]:
    # Mongo documents are self-describing; there are no missing columns.
    return []


async def upgrade_everything() -> dict[str, list[str]]:
    return await upgrade_all_tenant_schemas()


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    for slug, columns in asyncio.run(upgrade_everything()).items():
        print(f"{slug}: {', '.join(columns) if columns else 'already current'}")
