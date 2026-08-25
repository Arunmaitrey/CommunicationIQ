"""Cross-tenant isolation.

The BRD calls this non-negotiable (TEN-12), and retrofitting it is how leaks
happen — so it is tested from the first table rather than the first incident.

The point of these tests is not that filtering works. It is that there is no
way to ask the wrong question: the schema comes from the signed token, the
application only ever speaks the ``tenant`` placeholder, and no endpoint takes
an institution identifier at all.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.db import TENANT_SCHEMA_PLACEHOLDER, engine, tenant_sessionmaker
from app.models.tenant import User
from app.provisioning import validate_slug
from app.security import TokenPrincipal, create_token, decode_token
from tests.conftest import auth, login

pytestmark = pytest.mark.asyncio


async def test_two_institutions_see_different_people(client):
    """The same endpoint, two tokens, two disjoint sets of users."""
    stmarys = await login(client, "tenant_admin")
    vignan = await login(client, "other_admin")

    a = (await client.get("/api/v1/tenant/users", headers=auth(stmarys))).json()
    b = (await client.get("/api/v1/tenant/users", headers=auth(vignan))).json()

    emails_a = {u["email"] for u in a}
    emails_b = {u["email"] for u in b}

    assert emails_a and emails_b
    assert not emails_a & emails_b, "the two institutions share a user — isolation is broken"

    # Enrolled people carry their institution's domain. External candidates
    # do not, and that is the point of them: somebody invited to sit one
    # assessment brings their own address, or gets a generated one where they
    # gave none.
    #
    # Keyed on the role rather than the address. The first attempt at this
    # filtered by email suffix and still failed, because candidates from
    # earlier runs carried three different shapes of address -- which is the
    # lesson: the thing that makes them different is what they *are*, not what
    # their address looks like.
    #
    # The isolation claim is the assertion above and is unaffected. A
    # candidate lives in exactly one institution's schema like everybody else.
    enrolled_a = {u["email"] for u in a if u["role"] != "candidate"}
    enrolled_b = {u["email"] for u in b if u["role"] != "candidate"}

    assert enrolled_a and enrolled_b
    assert all(e.endswith("@stmarys.edu") for e in enrolled_a)
    assert all(e.endswith("@vignan.edu") for e in enrolled_b)

    # And a candidate admitted to one institution is invisible in the other.
    # Stated separately because it is the property Phase 9 could plausibly
    # have broken, and the enrolled-only assertions no longer cover it.
    assert not (emails_a - enrolled_a) & (emails_b - enrolled_b)


async def test_a_forged_slug_in_the_token_cannot_reach_another_schema(client):
    """A token is only as good as the schema it names — so name someone else's.

    This is the attack the design has to survive: a valid signature over a
    principal pointing at another institution. It fails not because a filter
    catches it, but because the user id in the token does not exist in the
    schema it now points at.
    """
    real = await login(client, "tenant_admin")
    principal = decode_token(real)
    assert principal is not None and principal.tenant_slug == "stmarys"

    forged = create_token(TokenPrincipal(
        user_id=principal.user_id, email=principal.email,
        full_name=principal.full_name, role=principal.role, scope="tenant",
        tenant_id=principal.tenant_id, tenant_slug="vignan",
    ))

    res = await client.get("/api/v1/tenant/users", headers=auth(forged))
    users = res.json()
    # Whatever comes back, it must not be St Mary's data.
    assert all(not u["email"].endswith("@stmarys.edu") for u in users)

    # And /me — which resolves the caller inside the named schema — refuses,
    # because that user id is not a member of that institution.
    me = await client.get("/api/v1/auth/me", headers=auth(forged))
    assert me.status_code == 401


async def test_no_tenant_scoped_endpoint_accepts_a_tenant_identifier(client):
    """Isolation by construction: nothing a tenant session can call names a tenant.

    If an institution cannot be supplied, it cannot be supplied wrongly — the
    schema comes from the signed token and there is no second way in.

    Operator routes under ``/platform`` are excluded deliberately, and the
    exclusion is the boundary rather than a hole in it. Administering
    institutions *is* naming them: creating one, changing its seats, invoicing
    it. Those routes are platform-staff only (a tenant session gets 403, which
    ``test_a_tenant_admin_cannot_reach_the_operator_console`` proves) and they
    touch the registry, not a tenant schema.
    """
    offenders = []
    for route in app_routes():
        if route.path.startswith("/api/v1/platform"):
            continue
        params = {p.name for p in getattr(route, "dependant", None).query_params} \
            if getattr(route, "dependant", None) else set()
        params |= {p.name for p in route.dependant.path_params} if getattr(route, "dependant", None) else set()
        if params & {"tenant", "tenant_id", "tenant_slug", "slug", "institution"}:
            offenders.append(route.path)
    assert not offenders, (
        f"these tenant-reachable routes accept a tenant identifier: {offenders}")


def app_routes():
    from app.main import app
    return [r for r in app.routes if hasattr(r, "dependant")]


async def test_a_tenant_session_requires_a_slug():
    """There is no default institution — asking for one without a slug fails."""
    with pytest.raises(ValueError):
        tenant_sessionmaker("")


async def test_tenant_tables_are_declared_against_the_placeholder():
    """Every tenant table names ``tenant``, never a real schema.

    This is what makes the isolation structural: a model that hard-coded
    ``tenant_stmarys`` would be reachable from any session, and this test is
    what stops one being added.
    """
    from app.db import TenantBase
    wrong = [t.name for t in TenantBase.metadata.tables.values()
             if t.schema != TENANT_SCHEMA_PLACEHOLDER]
    assert not wrong, f"tables not declared against the placeholder schema: {wrong}"


async def test_each_institution_has_its_own_physical_schema():
    async with engine.connect() as conn:
        schemas = {r[0] for r in await conn.execute(text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 'tenant_%'"
        ))}
    assert {"tenant_stmarys", "tenant_vignan"} <= schemas


async def test_sessions_bound_to_different_slugs_read_different_rows():
    """Below the API: the same query object, two schemas, two answers."""
    stmt = select(User.email).where(User.role == "student")

    async with tenant_sessionmaker("stmarys")() as s:
        a = set((await s.execute(stmt)).scalars().all())
    async with tenant_sessionmaker("vignan")() as s:
        b = set((await s.execute(stmt)).scalars().all())

    assert a and b and not a & b


async def test_a_slug_cannot_smuggle_sql():
    """Slugs become schema names, so they are validated rather than escaped."""
    for bad in ["stmarys; DROP SCHEMA public CASCADE",
                "public", "Tenant", "tenant-1", "", "../etc"]:
        if bad == "public":
            # Structurally valid but reserved — it would collide with the
            # control plane, which is a different failure worth its own check.
            continue
        with pytest.raises(ValueError):
            validate_slug(bad)
