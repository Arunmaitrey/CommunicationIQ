"""Onboarding and offboarding institutions.

There's no per-institution database to create or drop anymore — every tenant
shares the same collections, distinguished by ``tenant_id``. What this module
still does: validate a new slug, and — for offboarding — actually erase one
institution's documents (a bulk delete across every tenant-scoped collection)
rather than the single `drop_database` call that used to do the whole job.
"""
from __future__ import annotations

import re

from app.db import ensure_tenant_models, get_platform_bundle
from app.models.platform import TenantUserDirectory

SLUG = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def validate_slug(slug: str) -> str:
    """Still validated even though it no longer becomes a database name —
    the slug remains part of sign-in routing and audit trails."""
    if not SLUG.match(slug):
        raise ValueError(
            f"invalid tenant slug {slug!r} — lowercase letters, digits and underscores only"
        )
    return slug


def tenant_schema_name(slug: str) -> str:
    """Kept for call-site compatibility. There's no separate schema/database
    per tenant anymore; this just echoes the slug back."""
    return slug


async def create_tenant_schema(slug: str) -> str:
    """Nothing to create — the shared collections already exist. Kept so
    existing callers (onboarding a new institution) don't need to change."""
    validate_slug(slug)
    await ensure_tenant_models(slug)
    return slug


async def drop_tenant_schema(slug: str, *, purge_media: bool = True) -> int:
    """Erase an institution's data (offboarding): every document across the
    tenant-scoped collections whose ``tenant_id`` matches, plus its sign-in
    routing. Content collections (QuizItem, ReadingPassage, ...) are shared
    across institutions and are never touched here."""
    validate_slug(slug)
    from app.models.platform import Tenant
    from app.models.tenant import TENANT_DOCUMENTS

    platform_bundle = await get_platform_bundle()
    tenant = await platform_bundle.Tenant.find_one(Tenant.slug == slug)
    if tenant is None:
        return 0

    models = await ensure_tenant_models(slug)
    for cls in TENANT_DOCUMENTS:
        model = getattr(models, cls.__name__)
        await model.find(model.tenant_id == tenant.id).delete()

    await platform_bundle.TenantUserDirectory.find(
        {"tenant_slug": slug}
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
    platform_bundle = await get_platform_bundle()
    slugs = [t.slug async for t in platform_bundle.Tenant.find_all()]
    return {slug: await upgrade_tenant_schema(slug) for slug in slugs}


async def tenant_schema_exists(slug: str) -> bool:
    """Whether this institution is registered — there's no separate database
    to check for anymore, so this checks the ``Tenant`` registry instead."""
    validate_slug(slug)
    platform_bundle = await get_platform_bundle()
    tenant = await platform_bundle.Tenant.find_one({"slug": slug})
    return tenant is not None


async def missing_columns(slug: str) -> list[str]:
    # Mongo documents are self-describing; there are no missing columns.
    return []


async def upgrade_everything() -> dict[str, list[str]]:
    return await upgrade_all_tenant_schemas()


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    for slug, columns in asyncio.run(upgrade_everything()).items():
        print(f"{slug}: {', '.join(columns) if columns else 'already current'}")
