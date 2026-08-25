"""What the suite is allowed to delete after itself.

The rule has one dangerous edge and this file exists for that edge: a profile
an attempt points at must survive, because a result names its profile and one
whose profile vanished cannot be read back at all. Somebody opening a result
from last term would get an error instead of their score.

The other direction matters too, just less: a profile nothing points at that
is merely retired is rubbish accumulating in a table forever, and after enough
runs a person browsing the database has to read past nineteen hundred rows to
find anything real.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app import estate
from app.db import tenant_sessionmaker
from app.models.tenant import (Attempt, ProfileSection, SimulationProfile)
from tests.test_game_and_practice import SLUG, auth, login

pytestmark = pytest.mark.asyncio


async def _a_test_profile(client, admin, name: str) -> str:
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": name, "style": "company_round", "company": "Testco",
              "description": "x", "estimated_minutes": 10,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 1, "prep_seconds": 0,
                            "response_seconds": 20,
                            "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})
    return created["id"]


async def test_a_profile_nobody_sat_is_deleted_along_with_its_sections(client):
    admin = await login(client, "tenant_admin")
    profile_id = await _a_test_profile(client, admin, "Estate - untouched")

    await estate.tidy(SLUG)

    async with tenant_sessionmaker(SLUG)() as session:
        gone = await session.get(SimulationProfile, profile_id)
        orphans = (await session.execute(
            select(ProfileSection).where(
                ProfileSection.profile_id == profile_id))).scalars().all()

    assert gone is None, "an unreferenced test profile survived the tidy"
    assert not orphans, (
        "the profile went and its sections did not -- which is a foreign key "
        "violation waiting for the next person to add a constraint")


async def test_a_profile_somebody_sat_survives_and_is_retired(client):
    """The edge this file exists for.

    Deleting this one would take the attempt with it, and with the attempt the
    result a person can still open. Retired means invisible to somebody
    choosing what to sit, and still there for somebody reading what they did.
    """
    admin = await login(client, "tenant_admin")
    profile_id = await _a_test_profile(client, admin, "Estate - sat")

    student = await login(client, "student")
    attempt = (await client.post(
        "/api/v1/student/attempts", headers=auth(student),
        json={"profile_id": profile_id, "mode": "practice"})).json()

    result = await estate.tidy(SLUG)

    async with tenant_sessionmaker(SLUG)() as session:
        row = await session.get(SimulationProfile, profile_id)
        kept = await session.get(Attempt, attempt["attempt_id"])

    assert row is not None, (
        "a profile with an attempt against it was deleted -- the result can "
        "no longer be read back")
    assert row.status == "retired"
    assert kept is not None
    assert result.kept >= 1


async def test_nothing_a_person_authored_is_ever_touched(client):
    """The rule is keyed on a company name no real assessment carries.

    Stated as a test because the last rule in this codebase that inferred
    ownership from a code pattern retired two dozen of somebody's own
    profiles, and the fix for that is only as good as the thing that stops it
    coming back.
    """
    admin = await login(client, "tenant_admin")
    mine = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": "A real hiring round", "style": "company_round",
              "company": "Actual Employer Ltd", "description": "x",
              "estimated_minutes": 10,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 1, "prep_seconds": 0,
                            "response_seconds": 20,
                            "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    await client.post(f"/api/v1/tenant/profiles/{mine['id']}/status",
                      headers=auth(admin), json={"status": "published"})

    await estate.tidy(SLUG)

    async with tenant_sessionmaker(SLUG)() as session:
        row = await session.get(SimulationProfile, mine["id"])

    assert row is not None and row.status == "published", (
        "the tidy reached an assessment a person authored")

    # Leave the estate as it was found.
    async with tenant_sessionmaker(SLUG)() as session:
        row = await session.get(SimulationProfile, mine["id"])
        row.status = "retired"
        await session.commit()


async def test_every_table_that_names_a_profile_is_checked(client):
    """A new foreign key nobody added to the check is how this becomes a bug.

    The tidy looks at attempts, invitations and assignments. If a fifth table
    starts pointing at profiles and this list is not updated, the tidy deletes
    rows out from under it -- so the list is compared against the model
    metadata rather than trusted to stay complete.
    """
    from app.db import TenantBase

    names = {
        table.name
        for table in TenantBase.metadata.tables.values()
        for column in table.columns
        for fk in column.foreign_keys
        if fk.column.table.name == "simulation_profiles"
    }
    # `profile_sections` is deleted with the profile rather than protecting
    # it, which is why it is excluded here rather than missing.
    guarding = names - {"profile_sections"}

    assert guarding == {"attempts", "invitations", "assignments"}, (
        f"a table now names a profile and app/estate.py does not know: "
        f"{guarding}")
