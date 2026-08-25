"""What the test suite is allowed to touch when it tidies up after itself.

The cleanup in ``conftest.py`` used to deactivate every active candidate and
withdraw every pending invitation, in every tenant, keyed on nothing but role
and status.

On a throwaway database that is fine. On any other it is destructive in the
worst way available to this product: a real candidate halfway through a hiring
round is also "a candidate", and an invitation an employer sent this morning
that nobody has opened yet is also "pending". Running the suite would lock out
every one of them, silently, as a side effect of a green run.

It was found during a manual walkthrough of the invitation journey, where it
deactivated the candidate three times -- which is the mildest possible version
of that consequence and the only reason anybody noticed.

These tests pin the scope. They deliberately do not test the fixture itself,
which only runs at session teardown; they test the rule the fixture uses, so
the rule cannot quietly widen.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import tenant_sessionmaker
from app.estate import TEST_COMPANIES
from app.models.tenant import Invitation, SimulationProfile, User
from tests.test_game_and_practice import SLUG, auth, login

pytestmark = pytest.mark.asyncio


async def _profile(client, admin, name: str, company: str) -> str:
    created = (await client.post(
        "/api/v1/tenant/profiles", headers=auth(admin),
        json={"name": name, "style": "company_round", "company": company,
              "description": "x", "estimated_minutes": 6,
              "sections": [{"title": "Read Aloud", "task_type": "read_aloud",
                            "item_count": 1, "prep_seconds": 0,
                            "response_seconds": 20,
                            "prompt_plays_allowed": 0,
                            "allow_replay": False}]})).json()
    await client.post(f"/api/v1/tenant/profiles/{created['id']}/status",
                      headers=auth(admin), json={"status": "published"})
    return created["id"]


async def _candidates_the_suite_owns() -> set[str]:
    """The rule conftest applies, expressed once so a test can check it."""
    async with tenant_sessionmaker(SLUG)() as session:
        ours = select(SimulationProfile.id).where(
            SimulationProfile.company.in_(TEST_COMPANIES))
        mine = select(Invitation.candidate_id).where(
            Invitation.profile_id.in_(ours),
            Invitation.candidate_id.is_not(None))
        return set((await session.execute(
            select(User.id).where(User.role == "candidate",
                                  User.id.in_(mine)))).scalars().all())


async def test_a_real_customers_candidate_is_not_the_suites_to_touch(client):
    """The whole hazard, in one assertion.

    A candidate admitted through an invitation to an assessment a person
    authored belongs to that customer. The suite must not be able to see them.
    """
    admin = await login(client, "tenant_admin")

    theirs = await _profile(client, admin, "Real hiring round",
                            "Actual Employer Ltd")
    invitation = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": theirs, "invited_name": "Real Candidate",
              "invited_email": "", "reference": "", "valid_days": 7})).json()
    claimed = (await client.post(
        f"/api/v1/invite/{invitation['token']}/claim",
        json={"full_name": "Real Candidate", "email": ""})).json()

    owned = await _candidates_the_suite_owns()
    assert claimed["candidate_id"] not in owned, (
        "the suite's cleanup considers a real customer's candidate disposable")

    # Leave the estate as found.
    async with tenant_sessionmaker(SLUG)() as session:
        row = await session.get(SimulationProfile, theirs)
        row.status = "retired"
        await session.commit()


async def test_the_suites_own_candidate_is_still_cleaned_up(client):
    """The scope must not have narrowed to nothing.

    A guard that protects everything protects the accumulation this cleanup
    exists to prevent.
    """
    admin = await login(client, "tenant_admin")

    mine = await _profile(client, admin, "Suite round", "Testco")
    invitation = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": mine, "invited_name": "Suite Candidate",
              "invited_email": "", "reference": "", "valid_days": 7})).json()
    claimed = (await client.post(
        f"/api/v1/invite/{invitation['token']}/claim",
        json={"full_name": "Suite Candidate", "email": ""})).json()

    owned = await _candidates_the_suite_owns()
    assert claimed["candidate_id"] in owned, (
        "the suite no longer recognises its own candidates, so they will "
        "accumulate in the estate forever")


async def test_a_live_invitation_to_a_real_assessment_is_not_withdrawn(client):
    """Same rule, for the invitation nobody has opened yet.

    An employer sends thirty links on Monday morning. The suite runs. Every
    one of those links was withdrawn.
    """
    admin = await login(client, "tenant_admin")

    theirs = await _profile(client, admin, "Real round pending",
                            "Actual Employer Ltd")
    invitation = (await client.post(
        "/api/v1/tenant/invitations", headers=auth(admin),
        json={"profile_id": theirs, "invited_name": "Not Yet Opened",
              "invited_email": "", "reference": "", "valid_days": 7})).json()

    async with tenant_sessionmaker(SLUG)() as session:
        ours = select(SimulationProfile.id).where(
            SimulationProfile.company.in_(TEST_COMPANIES))
        doomed = set((await session.execute(
            select(Invitation.id).where(
                Invitation.status == "pending",
                Invitation.profile_id.in_(ours)))).scalars().all())

    assert invitation["id"] not in doomed, (
        "a live invitation to a real assessment is in the suite's sweep")

    async with tenant_sessionmaker(SLUG)() as session:
        row = await session.get(SimulationProfile, theirs)
        row.status = "retired"
        await session.commit()


async def test_the_marker_is_shared_rather_than_restated():
    """`conftest` and `app/estate.py` must agree on what a test row is.

    Two copies of "which company names mean this is disposable" is how one of
    them ends up wider than the other, and the wider one wins.
    """
    from pathlib import Path

    text = (Path(__file__).resolve().parent / "conftest.py").read_text(
        encoding="utf-8")
    assert "from app.estate import TEST_COMPANIES" in text, (
        "conftest defines its own idea of a test profile instead of sharing "
        "the one in app/estate.py")
