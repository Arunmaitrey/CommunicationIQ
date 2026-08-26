"""Clearing up after the test suite.

The profile helpers create a published assessment per test. They always did,
and for a long time nothing removed them: nearly nineteen hundred accumulated
in the demo tenant, which made the student's assessment list unusable locally
and -- worse -- meant a test asserting something about "every published
profile" was really asserting something about whatever the previous run had
left behind. One such test failed on a row a deliberate fault-injection run
had published.

That was fixed by retiring them, which stopped the bleeding without draining
the wound: retired rows still pile up, and after enough runs the table is
almost entirely rubbish that a person browsing the database has to read past.

So there are two cases, and telling them apart is the whole job here.

* A test profile **nothing points at** can go. Nobody sat it, nobody was
  invited to it, no cohort was assigned it. Deleting it loses nothing.
* A test profile **something points at** must stay, retired. Attempts, and the
  results a person can still open, name their profile -- and a result whose
  profile vanished cannot be read back at all.

Lives in ``app`` rather than ``tests`` so the fixture and the one-off
maintenance pass are the same code. Two copies of a rule about what is safe to
delete is exactly the shape of thing that drifts, and the direction it drifts
in is somebody's data.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.db import delete, func, platform_sessionmaker, select, tenant_sessionmaker
from app.models.platform import Tenant
from app.models.tenant import (Assignment, Attempt, Invitation, ProfileSection,
                               SimulationProfile)

# The company name the test helpers stamp on everything they create.
#
# Nothing seeded and nothing a person would author uses either of these, so
# this cannot reach a real assessment -- which matters, because the last rule
# in this codebase that inferred ownership from a code pattern retired two
# dozen of somebody's own profiles.
TEST_COMPANIES = ("T", "Testco")


@dataclass
class Tidied:
    slug: str
    deleted: int
    retired: int
    kept: int

    def __str__(self) -> str:
        return (f"{self.slug}: deleted {self.deleted}, retired {self.retired}, "
                f"{self.kept} still referenced")


async def tidy(slug: str) -> Tidied:
    """Remove what can go, retire what cannot, for one institution."""
    async with tenant_sessionmaker(slug)() as session:
        rows = list((await session.execute(
            select(SimulationProfile).where(
                SimulationProfile.company.in_(TEST_COMPANIES))
        )).scalars().all())

        if not rows:
            return Tidied(slug, 0, 0, 0)

        ids = [r.id for r in rows]

        # Everything that names a profile. Missing one of these turns a tidy
        # into a foreign key violation at best, and at worst -- if a future
        # table is added with ON DELETE CASCADE -- into silent data loss.
        referenced: set[str] = set()
        for model in (Attempt, Invitation, Assignment):
            referenced |= set((await session.execute(
                select(model.profile_id).where(model.profile_id.in_(ids))
            )).scalars().all())

        removable = [r.id for r in rows if r.id not in referenced]
        retired = 0
        for row in rows:
            if row.id in referenced and row.status != "retired":
                row.status = "retired"
                retired += 1

        if removable:
            # Sections first: they carry the foreign key, and nothing else
            # points at a section.
            await session.execute(delete(ProfileSection).where(
                ProfileSection.profile_id.in_(removable)))
            await session.execute(delete(SimulationProfile).where(
                SimulationProfile.id.in_(removable)))

        await session.commit()
        return Tidied(slug, len(removable), retired, len(referenced))


async def tidy_everywhere() -> list[Tidied]:
    async with platform_sessionmaker()() as session:
        slugs = list((await session.execute(select(Tenant.slug))).scalars().all())
    return [await tidy(slug) for slug in slugs]


async def count_test_profiles(slug: str) -> int:
    async with tenant_sessionmaker(slug)() as session:
        return (await session.execute(
            select(func.count()).select_from(SimulationProfile).where(
                SimulationProfile.company.in_(TEST_COMPANIES)))).scalar() or 0


if __name__ == "__main__":  # pragma: no cover - a maintenance entry point
    import asyncio

    for result in asyncio.run(tidy_everywhere()):
        print(result)
