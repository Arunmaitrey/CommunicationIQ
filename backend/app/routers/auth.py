"""Sign-in and session.

Two populations sign in here: platform staff (control plane) and institution
users (students, trainers, tenant admins). The email decides which, and the
issued token carries the answer. A caller never states which institution they
belong to — the directory does, once, at sign-in.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from app.db import control_db
from app.deps import Principal, ensure_tenant_models
from app.models.platform import PlatformUser, Tenant, TenantUserDirectory
from app.models.tenant import User
from app.routers.login_rate_limit import (LOGIN_RATE_LIMIT_MESSAGE, is_blocked,
                                          record_failure, reset)
from app.schemas import (ChangePasswordRequest, LoginRequest, LoginResponse,
                          PreferencesRequest, SessionUser, SignupRequest,
                          UpdateProfileRequest)
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


def _tenant_session_user(user, tenant) -> SessionUser:
    """Shared by every endpoint that hands a tenant user's session back
    after re-reading or mutating it (``/me``, ``/profile``, ``/preferences``)."""
    return SessionUser(
        id=user.id, email=user.email, full_name=user.full_name,
        role=user.role, scope="tenant",
        tenant_id=tenant.id, tenant_slug=tenant.slug, tenant_name=tenant.name,
        **_branding_fields(tenant),
        must_change_password=user.must_change_password,
        ui_language=user.ui_language, preferred_theme=user.preferred_theme,
        onboarding_completed=user.onboarding_completed,
    )


async def _load_self_tenant(principal: Principal):
    """Re-reads the caller's own tenant + User row, or 401s. Shared by every
    self-service endpoint below that is not valid for platform staff."""
    if not principal.tenant_slug:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    tenant = await Tenant.get(principal.tenant_id)
    if tenant is None or tenant.status in {"suspended", "closed"}:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    tenant_models = await ensure_tenant_models(tenant.slug)
    user = await tenant_models.User.get(principal.user_id)
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return user, tenant


@router.post("/signup", response_model=LoginResponse)
async def signup(body: SignupRequest) -> LoginResponse:
    """Student self-service registration.

    Validates the email domain against the institution's registered domain
    (Tenant.domain) — only emails matching it can sign up for that tenant.
    A tenant with no domain set (the default) accepts no self-service
    signups; its students are created by an admin or an invitation instead.
    """
    email = body.email.lower().strip()
    domain = email.split("@")[-1] if "@" in email else ""
    if not domain:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid email address")

    tenant = await Tenant.find_one(Tenant.domain == domain)
    if tenant is None or tenant.status in {"suspended", "closed"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No institution found for this email domain. Contact your "
            "institution admin to register.")

    dir_entry = await TenantUserDirectory.find(
        TenantUserDirectory.email == email).first_or_none()
    if dir_entry is not None and dir_entry.active:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "An account with this email already exists")

    tenant_models = await ensure_tenant_models(tenant.slug)
    existing = await tenant_models.User.find_one(tenant_models.User.email == email)
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "An account with this email already exists")

    user = tenant_models.User(
        email=email, full_name=body.full_name, role="student",
        password_hash=hash_password(body.password),
    )
    await user.create()

    if dir_entry is None:
        await TenantUserDirectory(email=email, tenant_id=tenant.id,
                                  tenant_slug=tenant.slug).create()
    else:
        dir_entry.tenant_id = tenant.id
        dir_entry.tenant_slug = tenant.slug
        dir_entry.active = True
        await dir_entry.save()

    principal = TokenPrincipal(
        user_id=user.id, email=user.email, full_name=user.full_name,
        role="student", scope="tenant",
        tenant_id=tenant.id, tenant_slug=tenant.slug,
    )
    await audit.record(principal, "auth.signup", entity="User",
                       entity_id=user.id, tenant_id=tenant.id)

    return LoginResponse(
        token=create_token(principal),
        user=SessionUser(
            id=user.id, email=user.email, full_name=user.full_name,
            role="student", scope="tenant",
            tenant_id=tenant.id, tenant_slug=tenant.slug, tenant_name=tenant.name,
            **_branding_fields(tenant),
            must_change_password=False, ui_language="en", preferred_theme="",
        ),
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    email = body.email.lower().strip()

    # Cheap in-process guard against credential stuffing from one IP. Not a
    # substitute for a real edge rate limiter — see login_rate_limit.py.
    client_ip = request.client.host if request.client else "unknown"
    remaining = is_blocked(client_ip)
    if remaining is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, LOGIN_RATE_LIMIT_MESSAGE)

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
            onboarding_completed=user.onboarding_completed,
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

    user, tenant = await _load_self_tenant(principal)
    return _tenant_session_user(user, tenant)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(body: ChangePasswordRequest, principal: Principal) -> None:
    """Self-service password change.

    For a tenant user this also clears ``must_change_password`` -- that flag
    is set whenever an admin issues a reset (see ``tenant_writes.reset_password``)
    and, until this endpoint existed, nothing ever cleared it again.
    """
    if principal.is_platform:
        staff = await PlatformUser.get(principal.user_id)
        if staff is None or not staff.active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
        if not verify_password(body.current_password, staff.password_hash):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
        staff.password_hash = hash_password(body.new_password)
        await staff.save()
        await audit.record(principal, "auth.password_changed",
                           entity="PlatformUser", entity_id=staff.id)
        return

    user, _tenant = await _load_self_tenant(principal)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    await user.save()
    await audit.record(principal, "auth.password_changed", entity="User",
                       entity_id=user.id, tenant_id=principal.tenant_id)


@router.patch("/profile", response_model=SessionUser)
async def update_profile(body: UpdateProfileRequest, principal: Principal) -> SessionUser:
    """Update the caller's own name and, for a tenant user, feedback
    language -- the self-service counterpart to
    ``tenant_writes.update_user``, which only an admin may call and never on
    themselves for these fields."""
    if principal.is_platform:
        staff = await PlatformUser.get(principal.user_id)
        if staff is None or not staff.active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
        if body.full_name is not None:
            staff.full_name = body.full_name
            await staff.save()
        return SessionUser(
            id=staff.id, email=staff.email, full_name=staff.full_name,
            role=staff.role, scope="platform",
        )

    user, tenant = await _load_self_tenant(principal)
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.l1_language is not None:
        user.l1_language = body.l1_language
    await user.save()
    return _tenant_session_user(user, tenant)


@router.put("/preferences", response_model=SessionUser)
async def update_preferences(body: PreferencesRequest, principal: Principal) -> SessionUser:
    """Persist appearance/locale on the account so they follow the user
    rather than the browser. Platform staff have no such fields on their
    model, so this is a no-op there rather than an error -- the frontend
    keeps their picks in localStorage only."""
    if principal.is_platform:
        staff = await PlatformUser.get(principal.user_id)
        if staff is None or not staff.active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
        return SessionUser(
            id=staff.id, email=staff.email, full_name=staff.full_name,
            role=staff.role, scope="platform",
        )

    user, tenant = await _load_self_tenant(principal)
    if body.ui_language is not None:
        user.ui_language = body.ui_language
    if body.preferred_theme is not None:
        user.preferred_theme = body.preferred_theme
    await user.save()
    return _tenant_session_user(user, tenant)


@router.post("/onboarding/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_onboarding(principal: Principal) -> None:
    """Mark the first-time product tour/welcome as done for this account.

    Tenant users only — platform staff and candidates never see the
    onboarding UI that calls this (candidates have no ``User`` document at
    all). Idempotent: calling it again is harmless.
    """
    if principal.is_platform or not principal.tenant_slug:
        return
    tenant_models = await ensure_tenant_models(principal.tenant_slug)
    user = await tenant_models.User.get(principal.user_id)
    if user is None:
        return
    user.onboarding_completed = True
    await user.save()
