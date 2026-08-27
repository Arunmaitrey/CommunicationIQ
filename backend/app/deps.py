"""Request dependencies: who is calling, and which database they may touch."""
from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.db import Session, ensure_tenant_models, ensure_platform_models, tenant_db_name
from app.models.platform import Tenant
from app.security import TokenPrincipal, decode_token

_bearer = HTTPBearer(auto_error=False)


async def _principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenPrincipal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    principal = decode_token(creds.credentials)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return principal


Principal = Annotated[TokenPrincipal, Depends(_principal)]


async def tenant_models(principal: Principal) -> AsyncIterator[SimpleNamespace]:
    """The Beanie document bundle bound to the caller's own institution.

    The slug comes from the verified token, never from the caller, so
    cross-tenant access is structurally impossible (TEN-12).
    """
    if principal.scope != "tenant" or not principal.tenant_slug:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This endpoint requires an institution session",
        )
    yield await ensure_tenant_models(principal.tenant_slug)


TenantModels = Annotated[SimpleNamespace, Depends(tenant_models)]


async def tenant_session(principal: Principal) -> AsyncIterator[Session]:
    """The same institution's document bundle, wrapped so routers written
    against the SQLAlchemy async-session API (``session.execute(select(...))``,
    ``session.get(Model, id)``) can use it unchanged. ``TenantModels`` above
    is the same bundle for routers that call Beanie directly instead.
    """
    if principal.scope != "tenant" or not principal.tenant_slug:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This endpoint requires an institution session",
        )
    yield Session(await ensure_tenant_models(principal.tenant_slug))


TenantSession = Annotated[Session, Depends(tenant_session)]


async def platform_session() -> AsyncIterator[Session]:
    """The control-plane bundle, wrapped the same way as ``tenant_session``."""
    yield Session(await ensure_platform_models())


PlatformSession = Annotated[Session, Depends(platform_session)]


async def tenant_models_for(tenant: Tenant) -> SimpleNamespace:
    """The tenant document bundle for platform code that already holds a Tenant.

    The only sanctioned way for a platform-scope endpoint to enter an
    institution database. Requiring the registry row (not a slug) keeps TEN-12
    structural on this side of the wall too.
    """
    if not isinstance(tenant, Tenant):
        raise TypeError(
            "tenant_models_for requires the control-plane Tenant row itself, "
            "not an id or slug")
    return await ensure_tenant_models(tenant.slug)


def require_platform(*roles: str):
    """Platform staff only, optionally narrowed to specific staff roles."""

    async def _guard(principal: Principal) -> TokenPrincipal:
        if not principal.is_platform:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform staff only")
        if roles and principal.role not in roles and principal.role != "super_admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal

    return _guard


def require_roles(*roles: str):
    """Institution users in one of the given roles."""

    async def _guard(principal: Principal) -> TokenPrincipal:
        if principal.scope != "tenant":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Institution session required")
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return principal

    return _guard


def registry_tenant_sessionmaker(tenant):
    """Shim for provisioning.py — returns ensure_tenant_models coroutine."""
    from app.db import ensure_tenant_models as _etm
    return _etm(tenant.slug)
