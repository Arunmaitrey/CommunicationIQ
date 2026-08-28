"""Sign-in and session.

All data lives in the single CommunicationIQ database. Tenant isolation is by
``tenant_id`` on documents, not separate databases.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status

from app.db import control_db
from app.deps import Principal, ensure_tenant_models
from app.models.platform import PlatformUser, Tenant, TenantUserDirectory
from app.models.tenant import User
from app.schemas import (ChangePasswordRequest, LoginRequest, LoginResponse,
                          SessionUser, SignupRequest)
from app import audit
from app.security import (TokenPrincipal, create_token, hash_password,
                          verify_password)
from app.deps import Principal, require_roles
from app.routers.login_rate_limit import (
    is_blocked, record_failure, reset, LOGIN_RATE_LIMIT_MESSAGE,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_REJECT = "Incorrect email or password"


@router.post("/signup", response_model=LoginResponse)
async def signup(body: SignupRequest, request: Request) -> LoginResponse:
    """Student self-service registration.

    Validates the email domain against the institution's registered domain.
    Only emails matching the domain can sign up for that institution.
    """
    email = body.email.lower().strip()
    domain = email.split("@")[-1] if "@" in email else ""

    if not domain:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Invalid email address")

    # Find the tenant by domain
    tenant = await Tenant.find_one(Tenant.domain == domain)
    if tenant is None or tenant.status in {"suspended", "closed"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No institution found for this email domain. "
                            "Contact your institution admin to register.")

    tenant_models = await ensure_tenant_models(tenant.slug)

    # Check if email already exists in this tenant (use raw Motor to scope
    # the query by tenant_id, since the Beanie User model may not have the
    # field on all existing documents yet)
    from app.db import client as _client, CONTROL_DB_NAME as _DB
    _users_coll = _client[_DB]["users"]
    existing = await _users_coll.find_one({"email": email, "tenant_id": tenant.id})
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "An account with this email already exists")

    # Check directory
    dir_entry = await TenantUserDirectory.find(
        TenantUserDirectory.email == email).first_or_none()
    if dir_entry is not None and dir_entry.active:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "An account with this email already exists")

    # Create the user
    user = tenant_models.User(
        tenant_id=tenant.id, email=email, full_name=body.full_name, role="student",
        password_hash=hash_password(body.password),
        must_change_password=False,
    )
    await user.create()

    # Add to directory
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
            must_change_password=False,
            preferred_theme="campus",
        ),
    )


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest,
                          principal: Principal) -> dict:
    """Change the authenticated user's password."""
    if principal.scope == "platform":
        staff = await PlatformUser.get(principal.user_id)
        if staff is None or not verify_password(body.current_password, staff.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
        staff.password_hash = hash_password(body.new_password)
        staff.must_change_password = False
        await staff.save()
        await audit.record(principal, "auth.password_changed", entity="PlatformUser",
                           entity_id=staff.id)
    else:
        tenant = await Tenant.get(principal.tenant_id or "")
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")
        models = await ensure_tenant_models(tenant.slug)
        user = await models.User.get(principal.user_id)
        if user is None or not verify_password(body.current_password, user.password_hash):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
        user.password_hash = hash_password(body.new_password)
        user.must_change_password = False
        await user.save()
        await audit.record(principal, "auth.password_changed", entity="User",
                           entity_id=user.id, tenant_id=tenant.id)
    return {"ok": True}


@router.post("/preferences")
async def save_preferences(body: dict, principal: Principal) -> dict:
    """Save user preferences (theme, profile fields) to the DB."""
    if principal.scope == "platform":
        staff = await PlatformUser.get(principal.user_id)
        if staff is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        if "preferred_theme" in body:
            staff.preferred_theme = body["preferred_theme"]
        if "full_name" in body:
            staff.full_name = body["full_name"]
        await staff.save()
    else:
        tenant = await Tenant.get(principal.tenant_id or "")
        if tenant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Institution not found")
        models = await ensure_tenant_models(tenant.slug)
        user = await models.User.get(principal.user_id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        if "preferred_theme" in body:
            user.preferred_theme = body["preferred_theme"]
        if "full_name" in body:
            user.full_name = body["full_name"]
        if "roll_number" in body:
            user.roll_number = body["roll_number"]
        if "branch" in body:
            user.branch = body["branch"]
        if "year_of_study" in body:
            user.year_of_study = body["year_of_study"]
        if "l1_language" in body:
            user.l1_language = body["l1_language"]
        await user.save()
    return {"ok": True}


def _branding_fields(tenant) -> dict:
    if tenant is None:
        raw = {}
    elif isinstance(tenant, dict):
        raw = tenant.get("branding") or {}
    else:
        raw = (tenant.branding or {}) if getattr(tenant, 'branding', None) else {}
    return {
        "tenant_display_name": raw.get("display_name") or None,
        "tenant_logo_url": raw.get("logo_url") or None,
        "tenant_primary_color": raw.get("primary_color") or None,
    }


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    email = body.email.lower().strip()

    # Rate limiting: block IP after too many failed attempts
    client_ip = request.client.host if request else "unknown"
    remaining = is_blocked(client_ip)
    if remaining is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            LOGIN_RATE_LIMIT_MESSAGE,
        )

    # Use raw Motor for all lookups to avoid Beanie _id type mismatches
    from app.db import client, CONTROL_DB_NAME
    _db = client[CONTROL_DB_NAME]

    # Check platform staff first
    staff_doc = await _db["platform_users"].find_one({"email": email})
    if staff_doc is not None:
        if not staff_doc.get("active", True) or not verify_password(body.password, staff_doc.get("password_hash", "")):
            record_failure(client_ip)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, _REJECT)
        reset(client_ip)
        staff_id = str(staff_doc["_id"])
        principal = TokenPrincipal(
            user_id=staff_id, email=staff_doc.get("email", email),
            full_name=staff_doc.get("full_name", ""),
            role=staff_doc.get("role", "super_admin"), scope="platform",
        )
        await _db["platform_users"].update_one(
            {"_id": staff_doc["_id"]}, {"$set": {"last_login_at": datetime.now(timezone.utc).isoformat()}})
        await audit.record(principal, "auth.login", entity="PlatformUser", entity_id=staff_id)
        return LoginResponse(
            token=create_token(principal),
            user=SessionUser(
                id=staff_id, email=staff_doc.get("email", email),
                full_name=staff_doc.get("full_name", ""),
                role=staff_doc.get("role", "super_admin"), scope="platform",
            ),
        )

    # Institution user — route via tenant_user_directory
    _tud_coll = _db["tenant_user_directory"]
    _tud_raw = await _tud_coll.find_one({"email": email})
    if _tud_raw is None or not _tud_raw.get("active", True):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _REJECT)

    tenant_id = str(_tud_raw.get("tenant_id") or "")
    tenant_slug = str(_tud_raw.get("tenant_slug") or "")

    # Find tenant
    tenant_doc = await _db["tenants"].find_one({"_id": tenant_id})
    if tenant_doc is None or tenant_doc.get("status") in {"suspended", "closed"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "This institution's access is not currently active")

    # Find user scoped to this tenant
    user_doc = await _db["users"].find_one({"email": email, "tenant_id": tenant_id})
    if user_doc is None or not user_doc.get("active", True) or not verify_password(body.password, user_doc.get("password_hash", "")):
        record_failure(client_ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _REJECT)
    reset(client_ip)

    user_id = str(user_doc["_id"])
    await _db["users"].update_one(
        {"_id": user_doc["_id"]}, {"$set": {"last_login_at": datetime.now(timezone.utc).isoformat()}})

    principal = TokenPrincipal(
        user_id=user_id, email=user_doc.get("email", email),
        full_name=user_doc.get("full_name", ""),
        role=user_doc.get("role", "student"), scope="tenant",
        tenant_id=tenant_id, tenant_slug=tenant_slug,
    )
    await audit.record(principal, "auth.login", entity="User",
                       entity_id=user_id, tenant_id=tenant_id)

    branding = _branding_fields(tenant_doc)
    return LoginResponse(
        token=create_token(principal),
        user=SessionUser(
            id=user_id, email=user_doc.get("email", email),
            full_name=user_doc.get("full_name", ""),
            role=user_doc.get("role", "student"), scope="tenant",
            tenant_id=tenant_id, tenant_slug=tenant_slug,
            tenant_name=tenant_doc.get("name", ""),
            must_change_password=user_doc.get("must_change_password", False),
            preferred_theme=user_doc.get("preferred_theme", "campus"),
            **branding,
        ),
    )


@router.get("/me", response_model=SessionUser)
async def me(principal: Principal) -> SessionUser:
    from app.db import client, CONTROL_DB_NAME
    _db = client[CONTROL_DB_NAME]

    if principal.is_platform:
        staff = await _db["platform_users"].find_one({"_id": principal.user_id})
        if staff is None or not staff.get("active", True):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
        return SessionUser(
            id=str(staff["_id"]), email=staff.get("email", ""),
            full_name=staff.get("full_name", ""),
            role=staff.get("role", "super_admin"), scope="platform",
        )

    if not principal.tenant_slug:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    tenant_doc = await _db["tenants"].find_one({"_id": principal.tenant_id})
    if tenant_doc is None or tenant_doc.get("status") in {"suspended", "closed"}:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    user_doc = await _db["users"].find_one({"_id": principal.user_id, "tenant_id": principal.tenant_id})
    if user_doc is None or not user_doc.get("active", True):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    return SessionUser(
        id=str(user_doc["_id"]), email=user_doc.get("email", ""),
        full_name=user_doc.get("full_name", ""),
        role=user_doc.get("role", "student"), scope="tenant",
        tenant_id=tenant_doc.get("_id", ""), tenant_slug=tenant_doc.get("slug", ""),
        tenant_name=tenant_doc.get("name", ""),
        **_branding_fields(tenant_doc),
        must_change_password=user_doc.get("must_change_password", False),
        preferred_theme=user_doc.get("preferred_theme", "campus"),
    )
