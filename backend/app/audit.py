"""Writing to the audit log.

One helper, used by every write path that changes something a person could
later be asked to account for. It writes its own document on purpose: an audit
row must survive whatever transaction it describes.
"""
from __future__ import annotations

from app.models.platform import AuditLog
from app.security import TokenPrincipal


async def record(principal: TokenPrincipal, action: str, *, entity: str = "",
                 entity_id: str = "", before: dict | None = None,
                 after: dict | None = None, tenant_id: str | None = None) -> None:
    await AuditLog(
        actor_type="platform_user" if principal.is_platform else "tenant_user",
        actor_id=principal.user_id,
        actor_label=principal.label,
        tenant_id=tenant_id or principal.tenant_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        before=before or {},
        after=after or {},
    ).create()


async def record_system(action: str, *, entity: str = "", entity_id: str = "",
                        after: dict | None = None,
                        tenant_id: str | None = None) -> None:
    """For things nobody triggered — sweepers, schedulers, auto-suggestions."""
    await AuditLog(
        actor_type="system", actor_label="system", tenant_id=tenant_id,
        action=action, entity=entity, entity_id=entity_id, after=after or {},
    ).create()
