"""Test fixtures.

These run against the seeded demo estate on the local database. That is a
deliberate choice for M0: the isolation guarantees under test are properties of
real PostgreSQL schemas and real ``schema_translate_map`` routing, and a
sqlite-backed test would prove none of it.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

from app.config import settings

# The suite runs the smallest Whisper. It transcribes the speech fixtures
# exactly as the default model does, and it is roughly four times faster —
# these tests are checking that the pipeline carries a transcript around
# correctly, not how good the model is. Set before anything triggers a load,
# because the model is a process-wide singleton.
settings.whisper_model = "tiny.en"

from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.storage import get_storage, tenant_prefixes

DEMO_PASSWORD = "Password123!"

ACCOUNTS = {
    "student": "aarav.reddy1@stmarys.edu",
    "trainer": "trainer1@stmarys.edu",
    "tenant_admin": "admin@stmarys.edu",
    "platform": "admin@saashx.ai",
    # The second institution — what makes the isolation tests mean anything.
    "other_admin": "admin@vignan.edu",
}


@pytest.fixture(scope="session", autouse=True)
def _clean_recordings_afterwards():
    """Remove the audio the suite wrote.

    The attempt tests upload real WAVs to real storage, which is the point —
    a mocked filesystem would not exercise the ingest path. Left alone they
    accumulate tens of megabytes per run on a developer's machine, so the
    suite takes its own rubbish out.
    """
    yield
    storage = get_storage()
    for slug in ("stmarys", "vignan"):
        for prefix in tenant_prefixes(slug):
            try:
                storage.purge_prefix(prefix)
            except (ValueError, OSError):
                pass


@pytest.fixture(scope="session", autouse=True)
def _retire_profiles_the_suite_created():
    """Take the suite's own assessments out of the estate afterwards.

    The profile helpers create a published profile per test and never removed
    it, so a few hundred accumulated in the demo tenant: the student's
    assessment list became unusable locally, and -- worse -- a test that
    asserted something about "every published profile" was really asserting
    something about whatever the previous run had left behind. One such test
    failed on a row a deliberate fault-injection run had published.

    Retiring stopped the bleeding without draining the wound: retired rows
    still pile up, and after enough runs the table is almost entirely rubbish
    a person browsing the database has to read past. So one that nothing
    points at is now deleted outright, and only one an attempt, invitation or
    assignment names is kept and retired -- a result whose profile vanished
    cannot be read back at all.

    The rule about what is safe to delete lives in ``app/estate.py`` rather
    than here, so the suite and the maintenance pass cannot disagree about it.
    Two copies of that rule would drift, and the direction it drifts in is
    somebody's data.
    """
    yield

    import asyncio

    from sqlalchemy import select

    from app.db import platform_sessionmaker, tenant_sessionmaker
    from app.models.platform import Tenant
    from app.models.tenant import SimulationProfile

    async def tidy() -> None:
        from app import estate

        for result in await estate.tidy_everywhere():
            if result.deleted or result.retired:
                print(result)

        async with platform_sessionmaker()() as session:
            slugs = list((await session.execute(
                select(Tenant.slug))).scalars().all())
        for slug in slugs:
            async with tenant_sessionmaker(slug)() as session:
                # Candidates the invitation tests admitted, and the
                # invitations that admitted them. Same reasoning as the
                # profiles above: a suite that leaves accounts behind makes
                # the next run's "this email already exists" a fact about the
                # last run rather than about the endpoint.
                #
                # Keyed on the address the tests mint, which nothing real
                # uses. Deactivated rather than deleted -- attempts point at
                # these users, and a result whose candidate vanished cannot
                # be read back.
                from app.models.tenant import Invitation, User

                # Only the ones the suite let in.
                #
                # This used to deactivate every active candidate and withdraw
                # every pending invitation, in every tenant, keyed on nothing
                # but role and status. That is correct for a throwaway
                # database and catastrophic for any other: a real candidate
                # halfway through a hiring round is also "a candidate", and a
                # live invitation nobody has opened yet is also "pending". The
                # suite would have locked out every one of them.
                #
                # It bit during a manual walkthrough of the invitation journey
                # -- three times -- which is how it was found, and which is
                # also the mildest possible version of the consequence.
                #
                # A candidate is the suite's if the invitation that admitted
                # them points at a test profile. Same marker `app/estate.py`
                # uses, imported rather than restated.
                from app.estate import TEST_COMPANIES
                from app.models.tenant import SimulationProfile

                ours = select(SimulationProfile.id).where(
                    SimulationProfile.company.in_(TEST_COMPANIES))

                mine = select(Invitation.candidate_id).where(
                    Invitation.profile_id.in_(ours),
                    Invitation.candidate_id.is_not(None))

                candidates = (await session.execute(
                    select(User).where(User.role == "candidate",
                                       User.active.is_(True),
                                       User.id.in_(mine))
                )).scalars().all()
                for candidate in candidates:
                    candidate.active = False
                    candidate.email = f"retired.{candidate.id[:8]}@candidate.test"

                stale = (await session.execute(
                    select(Invitation).where(
                        Invitation.status == "pending",
                        Invitation.profile_id.in_(ours)))).scalars().all()
                for invitation in stale:
                    invitation.status = "withdrawn"

                await session.commit()

    try:
        asyncio.run(tidy())
    except Exception:  # noqa: BLE001 — tidying must never fail a green run
        pass


@pytest_asyncio.fixture(autouse=True)
async def _dispose_pool():
    """Return pooled connections at the end of each test.

    The engine is a module-level singleton and pytest-asyncio gives each test
    its own event loop. A connection pooled under a finished loop cannot be
    reused under the next one — disposing here keeps the singleton without
    pinning every test to a shared loop.
    """
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def login(client: httpx.AsyncClient, who: str) -> str:
    res = await client.post("/api/v1/auth/login",
                            json={"email": ACCOUNTS[who], "password": DEMO_PASSWORD})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
