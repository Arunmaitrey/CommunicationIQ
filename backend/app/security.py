"""Password hashing and session tokens.

The one rule this file exists to enforce: **the tenant a request operates on
comes from the signed token and nowhere else.** No header, no query parameter,
no request body can name an institution. That is why ``TokenPrincipal`` carries
the slug and why the tenant session dependency reads it from there only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _pwd.verify(raw, hashed)
    except ValueError:
        return False


@dataclass(frozen=True)
class TokenPrincipal:
    """Who is calling, and — for institution users — from which schema."""

    user_id: str
    email: str
    full_name: str
    role: str
    # "platform" | "tenant"
    scope: str
    tenant_id: str | None = None
    tenant_slug: str | None = None

    @property
    def is_platform(self) -> bool:
        return self.scope == "platform"

    @property
    def label(self) -> str:
        return f"{self.full_name} <{self.email}>"


def create_token(principal: TokenPrincipal) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    claims = {
        "sub": principal.user_id,
        "email": principal.email,
        "name": principal.full_name,
        "role": principal.role,
        "scope": principal.scope,
        "tid": principal.tenant_id,
        "tslug": principal.tenant_slug,
        "exp": expires,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenPrincipal | None:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None

    scope = claims.get("scope")
    slug = claims.get("tslug")
    # A tenant-scoped token without a slug is not a degraded token, it is a
    # broken one — there is no default institution to fall back to.
    if scope == "tenant" and not slug:
        return None

    return TokenPrincipal(
        user_id=claims.get("sub", ""),
        email=claims.get("email", ""),
        full_name=claims.get("name", ""),
        role=claims.get("role", ""),
        scope=scope or "",
        tenant_id=claims.get("tid"),
        tenant_slug=slug,
    )
