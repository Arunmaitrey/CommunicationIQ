"""Dev-only: force the researched blueprints onto their canonical profiles.

The normal resync skips any profile that
already has attempts, to protect score comparability -- the right rule in
production. In development the demo estate has test attempts on some of these
profiles, which would otherwise leave them stranded on stale blueprints. This
tool force-applies the *current* blueprint to the canonical profiles
regardless of attempts, so a developer can verify the new structures.

Scope is deliberately narrow: only the named canonical codes, only their
section list / pacing / style / description. It never touches any other
profile. Never run against production.

    python -m app.reseed_formats
"""
from __future__ import annotations

import asyncio
import os

from sqlalchemy import delete, select, update

from app import formats
from app.db import platform_sessionmaker, tenant_sessionmaker
from app.models.platform import Tenant
from app.models.tenant import (AttemptNarration, FeatureRecord, Invitation,
                               ProfileSection, Response, ResponseAudio,
                               ScoreRecord, SectionResult, SimulationProfile)
from app.models.tenant import Attempt

CANONICAL = (
    # The SVAR-style profile is included since its Section A/C structure was
    # re-derived from the reference walkthrough (2026-08-23); the normal
    # resync leaves a profile with attempts alone, which on a dev estate
    # means the old structure would stay seeded forever.
    "svar_full_simulation",
    "company_round_tcs",
    "company_round_infosys",
    "company_round_wipro",
    "company_round_cognizant",
    "speechx_style_full",
    "versant_style_speaking_listening",
)


async def _apply(slug: str) -> list[str]:
    changed: list[str] = []
    async with tenant_sessionmaker(slug)() as s:
        profiles = {p.code: p for p in (await s.execute(
            select(SimulationProfile))).scalars().all()}
        for code in CANONICAL:
            blueprint = formats.BY_CODE[code]
            profile = profiles.get(code)
            if profile is None:
                continue
            # Already on the blueprint (structure and wording): nothing to
            # force, so do not delete this profile's attempts for nothing.
            rows = (await s.execute(select(ProfileSection).where(
                ProfileSection.profile_id == profile.id)
                .order_by(ProfileSection.position))).scalars().all()
            current = [(x.title, x.task_type, x.item_count, x.prep_seconds,
                        x.response_seconds, x.prompt_plays_allowed,
                        x.instructions, dict(x.selection or {})) for x in rows]
            wanted = [(b.title, b.task_type, b.item_count, b.prep_seconds,
                       b.response_seconds, b.prompt_plays_allowed,
                       b.instructions, dict(b.selection or {})) for b in blueprint.sections]
            if (current == wanted and profile.name == blueprint.name
                    and profile.description == blueprint.description
                    and profile.estimated_minutes == blueprint.estimated_minutes):
                continue
            # Purge this profile's (dev test) attempts first: their responses
            # foreign-key the sections, so the sections cannot be replaced
            # while they exist. Cascade order, children before parents.
            attempt_ids = list((await s.execute(select(Attempt.id).where(
                Attempt.profile_id == profile.id))).scalars().all())
            if attempt_ids:
                resp_ids = list((await s.execute(select(Response.id).where(
                    Response.attempt_id.in_(attempt_ids)))).scalars().all())
                if resp_ids:
                    await s.execute(delete(FeatureRecord).where(
                        FeatureRecord.response_id.in_(resp_ids)))
                    await s.execute(delete(ResponseAudio).where(
                        ResponseAudio.response_id.in_(resp_ids)))
                await s.execute(delete(ScoreRecord).where(
                    ScoreRecord.attempt_id.in_(attempt_ids)))
                await s.execute(delete(Response).where(
                    Response.attempt_id.in_(attempt_ids)))
                await s.execute(delete(SectionResult).where(
                    SectionResult.attempt_id.in_(attempt_ids)))
                await s.execute(delete(AttemptNarration).where(
                    AttemptNarration.attempt_id.in_(attempt_ids)))
                await s.execute(update(Invitation).where(
                    Invitation.attempt_id.in_(attempt_ids)).values(attempt_id=None))
                await s.execute(delete(Attempt).where(
                    Attempt.id.in_(attempt_ids)))

            existing = (await s.execute(select(ProfileSection).where(
                ProfileSection.profile_id == profile.id))).scalars().all()
            for row in existing:
                await s.delete(row)
            for position, section in enumerate(blueprint.sections, start=1):
                s.add(ProfileSection(
                    profile_id=profile.id, position=position,
                    title=section.title, task_type=section.task_type,
                    item_count=section.item_count,
                    prep_seconds=section.prep_seconds,
                    response_seconds=section.response_seconds,
                    prompt_plays_allowed=section.prompt_plays_allowed,
                    instructions=section.instructions,
                    selection=section.selection,
                ))
            profile.name = blueprint.name
            profile.style = blueprint.style
            profile.description = blueprint.description
            profile.estimated_minutes = blueprint.estimated_minutes
            changed.append(code)
        await s.commit()
    return changed


async def main() -> None:
    # Hard guard: this tool deletes attempts on the canonical profiles,
    # which is only ever acceptable on a development estate. It refuses to run
    # unless the operator states, in the environment, that this is one.
    if os.environ.get("ALLOW_DEV_RESEED") != "1":
        raise SystemExit(
            "reseed_formats is DEV-ONLY: it deletes attempts on the "
            "canonical format profiles. If this is a development estate, run "
            "it as ALLOW_DEV_RESEED=1 python -m app.reseed_formats. "
            "Never run it against production.")
    async with platform_sessionmaker()() as ps:
        slugs = [t.slug for t in (await ps.execute(select(Tenant))).scalars().all()]
    for slug in slugs:
        changed = await _apply(slug)
        print(f"{slug}: force-reseeded {len(changed)} profiles -> {changed}")


if __name__ == "__main__":
    asyncio.run(main())
