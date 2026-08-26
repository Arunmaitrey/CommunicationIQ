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
from app.deps import ensure_tenant_models
from app.models.platform import PlatformUser, Tenant, TenantUserDirectory
from app.models.tenant import User
from app.schemas import (ChangePasswordRequest, LoginRequest, LoginResponse,
                          SessionUser)
from app import audit
from app.security import (TokenPrincipal, create_token, hash_password,
                          verify_password)
from app.routers.login_rate_limit import (
    is_blocked, record_failure, reset, LOGIN_RATE_LIMIT_MESSAGE,
)

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
async def login(body: LoginRequest, request=None) -> LoginResponse:
    email = body.email.lower().strip()

    # Rate limiting: block IP after too many failed attempts
    client_ip = request.client.host if request else "unknown"
    remaining = is_blocked(client_ip)
    if remaining is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            LOGIN_RATE_LIMIT_MESSAGE,
        )

    staff = await PlatformUser.find(PlatformUser.email == email).first_or_none()

    if staff is not None:
        if not staff.active or not verify_password(body.password, staff.password_hash):
            record_failure(client_ip)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, _REJECT)
        reset(client_ip)
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
        record_failure(client_ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _REJECT)
    reset(client_ip)
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
