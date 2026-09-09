"""Ensure every simulation profile this product ships with actually exists.

Most of the company-round profiles (ADP, Deloitte, Virtusa, LTIMindtree,
IBM, and everything with a `*-CR` code) were never created by any script in
this codebase -- they only ever existed as rows someone inserted directly
into a database at some point. SVAR and SpeechX were the same story until
2026-09-07. `formats.py`'s blueprints don't cover this set either: their
codes don't match what's actually stored (`company_round_tcs` in code vs
`TCS-CR` in the database), so a resync against `formats.py` can't recreate
them.

The fixtures here (`seed_data/simulation_profiles.json` and
`profile_sections.json`) are a straight export of every profile and section
that exists in the working database as of 2026-09-09 -- the actual, current
truth, not a re-derivation from code that would risk missing whatever isn't
written down anywhere else. Running this script against any database
(a fresh one, a redeployed environment, a teammate's local Mongo) creates
whichever of these are missing there, so a test format someone built and
never wrote a seed script for still shows up after a migration.

Safe to re-run: it only creates profiles/sections that are missing by id,
and never touches or overwrites one that already exists -- so it will never
clobber a live edit made in the target environment, and running it twice
does nothing the second time.

    python -m app.seed_profiles
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "seed_data"


async def main() -> None:
    from app.db import init_mongo
    from app.models.tenant import ProfileSection, SimulationProfile

    await init_mongo()

    profiles = json.loads((DATA_DIR / "simulation_profiles.json").read_text())
    sections = json.loads((DATA_DIR / "profile_sections.json").read_text())

    existing_profile_ids = {p.id for p in await SimulationProfile.find_all().to_list()}
    existing_section_ids = {s.id for s in await ProfileSection.find_all().to_list()}

    created_profiles = 0
    for row in profiles:
        row = dict(row)
        row["id"] = row.pop("_id")
        if row["id"] in existing_profile_ids:
            continue
        await SimulationProfile(**row).insert()
        created_profiles += 1

    created_sections = 0
    for row in sections:
        row = dict(row)
        row["id"] = row.pop("_id")
        if row["id"] in existing_section_ids:
            continue
        await ProfileSection(**row).insert()
        created_sections += 1

    print(f"profiles: {created_profiles} created, "
          f"{len(profiles) - created_profiles} already present")
    print(f"sections: {created_sections} created, "
          f"{len(sections) - created_sections} already present")


if __name__ == "__main__":
    asyncio.run(main())
