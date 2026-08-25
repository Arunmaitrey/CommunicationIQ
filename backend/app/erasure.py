"""Deleting an attempt, and everything hanging off it.

Written because there was no way to do this. Six tables reference an attempt
or its responses, none of the foreign keys cascade, and the order matters --
delete the attempt first and Postgres refuses, delete the responses first and
it refuses again for a different table. Anyone doing it by hand discovers the
dependency graph one integrity error at a time, which is exactly how a
half-deleted attempt gets left behind.

That is not only a housekeeping problem. A student exercising their right to
erasure under the DPDP Act needs their recordings and scores gone, not gone
from the two tables somebody remembered. Same for a participant withdrawing
from the validation study. One function, one order, one place to update when a
table is added.

**Rows and files, together.** Deleting the rows and leaving the WAVs on disk
is the failure this project already made once at tenant offboarding: audio
unreachable through the product and entirely present on the filesystem. The
storage purge happens here, after the database transaction commits -- a rolled
back delete must not take the recordings with it.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select

from app.models.tenant import (Attempt, Drill, FeatureRecord, Response,
                               ResponseAudio, ScoreRecord)
from app.storage import get_storage


@dataclass(frozen=True)
class ErasureResult:
    attempts: int
    responses: int
    recordings: int


async def erase_attempts(session, attempt_ids: list[str], *,
                         tenant_slug: str,
                         purge_media: bool = True) -> ErasureResult:
    """Remove attempts, their responses, scores, features and recordings.

    Order is dependency order and is the whole point of the function. A drill
    created from a response is *unlinked* rather than deleted: the student
    chose to practise something, and that choice is theirs even once the
    recording behind it is gone.
    """
    if not attempt_ids:
        return ErasureResult(0, 0, 0)

    response_ids = list((await session.execute(
        select(Response.id).where(Response.attempt_id.in_(attempt_ids))
    )).scalars().all())

    if response_ids:
        # Practice a student started stays; only its pointer at the recording
        # goes, because the recording is about to.
        await session.execute(
            Drill.__table__.update()
            .where(Drill.origin_response_id.in_(response_ids))
            .values(origin_response_id=None))
        await session.execute(
            delete(FeatureRecord).where(FeatureRecord.response_id.in_(response_ids)))
        await session.execute(
            delete(ResponseAudio).where(ResponseAudio.response_id.in_(response_ids)))
        await session.execute(
            delete(ScoreRecord).where(ScoreRecord.response_id.in_(response_ids)))

    await session.execute(
        delete(ScoreRecord).where(ScoreRecord.attempt_id.in_(attempt_ids)))
    await session.execute(
        delete(Response).where(Response.attempt_id.in_(attempt_ids)))
    await session.execute(
        delete(Attempt).where(Attempt.id.in_(attempt_ids)))
    await session.commit()

    purged = 0
    if purge_media:
        # After the commit. A rolled back transaction must not have taken the
        # audio with it.
        storage = get_storage()
        for attempt_id in attempt_ids:
            purged += storage.purge_prefix(
                f"recordings/{tenant_slug}/{attempt_id}/")

    return ErasureResult(len(attempt_ids), len(response_ids), purged)
