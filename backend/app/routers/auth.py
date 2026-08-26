"""Sign-in and session.

Two populations sign in here: platform staff (control plane) and institution
users (students, trainers, tenant admins). The email decides which, and the
issued token carries the answer. A caller never states which institution they
belong to — the directory does, once, at sign-in.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.db import control_db
from app.deps import Principal, ensure_tenant_models
from app.models.platform import PlatformUser, Tenant, TenantUserDirectory
from app.models.tenant import User
from app.schemas import (ChangePasswordRequest, LoginRequest, LoginResponse,
                          SessionUser)
from app import audit
from app.security import (TokenPrincipal, create_token, hash_password,
                          verify_password)

router = APIRouter(prefix="/auth", tags=["auth"])

_REJECT = "Incorrect email or password"


def _branding_fields(tenant) -> dict:
    raw = (tenant.branding or {}) if tenant is not None else {}
    return {
        "tenant_display_name": raw.get("display_name") or None,
        "tenant_logo_url": raw.get("logo_url") or None,
        "tenant_primary_color": raw.get("primary_color") or None,
    }


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    email = body.email.lower().strip()

    staff = await PlatformUser.find(PlatformUser.email == email).first_or_none()

    if staff is not None:
        if not staff.active or not verify_password(body.password, staff.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, _REJECT)
        staff.last_login_at = datetime.now(timezone.utc)
        await staff.save()
        principal = TokenPrincipal(
            user_id=staff.id, email=staff.email, full_name=staff.full_name,
            role=staff.role, scope="platform",
        )
        await audit.record(principal, "auth.login", entity="PlatformUser",
                           entity_id=staff.id)
        return LoginResponse(
            token=create_token(principal),
            user=SessionUser(
                id=staff.id, email=staff.email, full_name=staff.full_name,
                role=staff.role, scope="platform",
            ),
        )

    entry = await TenantUserDirectory.find(TenantUserDirectory.email == email).first_or_none()
    if entry is None or not entry.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _REJECT)

    tenant = await Tenant.get(entry.tenant_id)
    if tenant is None or tenant.status in {"suspended", "closed"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "This institution's access is not currently active")

    tenant_models = await ensure_tenant_models(tenant.slug)
    user = await tenant_models.User.find(tenant_models.User.email == email).first_or_none()
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _REJECT)
    user.last_login_at = datetime.now(timezone.utc)
    await user.save()

    principal = TokenPrincipal(
        user_id=user.id, email=user.email, full_name=user.full_name,
        role=user.role, scope="tenant",
        tenant_id=tenant.id, tenant_slug=tenant.slug,
    )
    await audit.record(principal, "auth.login", entity="User",
                       entity_id=user.id, tenant_id=tenant.id)
    return LoginResponse(
        token=create_token(principal),
        user=SessionUser(
            id=user.id, email=user.email, full_name=user.full_name,
            role=user.role, scope="tenant",
            tenant_id=tenant.id, tenant_slug=tenant.slug, tenant_name=tenant.name,
            **_branding_fields(tenant),
            must_change_password=user.must_change_password,
            ui_language=user.ui_language, preferred_theme=user.preferred_theme,
        ),
    )


@router.get("/me", response_model=SessionUser)
async def me(principal: Principal) -> SessionUser:
    """Restore a session from its token — what the frontend calls on every
    page load to decide whether a stored token still means something.

    Re-reads the account rather than trusting the token's claims: a role
    change, a rename, or a tenant's branding update should show up on the
    next refresh without forcing a fresh sign-in, and an account or
    institution deactivated after the token was issued should not be
    trusted just because the signature still checks out.
    """
    if principal.is_platform:
        staff = await PlatformUser.get(principal.user_id)
        if staff is None or not staff.active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
        return SessionUser(
            id=staff.id, email=staff.email, full_name=staff.full_name,
            role=staff.role, scope="platform",
        )

    if not principal.tenant_slug:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    tenant = await Tenant.get(principal.tenant_id)
    if tenant is None or tenant.status in {"suspended", "closed"}:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    tenant_models = await ensure_tenant_models(tenant.slug)
    user = await tenant_models.User.get(principal.user_id)
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    return SessionUser(
        id=user.id, email=user.email, full_name=user.full_name,
        role=user.role, scope="tenant",
        tenant_id=tenant.id, tenant_slug=tenant.slug, tenant_name=tenant.name,
        **_branding_fields(tenant),
        must_change_password=user.must_change_password,
        ui_language=user.ui_language, preferred_theme=user.preferred_theme,
    )
