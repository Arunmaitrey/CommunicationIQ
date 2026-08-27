"""Calibrate the item bank from the responses collected so far (ENG-12).

Run with ``python -m app.calibrate`` (add ``--dry-run`` to see what would move,
``--tenant slug`` to do one institution).

Calibration is per institution on purpose. An item that is hard for a
particular college's intake is hard *there*, and pooling across institutions
would average away exactly the signal a placement cell needs. Splitting further
by L1 group — which the BRD asks for — needs more responses per cell than any
of them will have for a while, and doing it early would produce confident
nonsense.
"""
from __future__ import annotations

import argparse
import asyncio

from app.sqlbridge import select

from app import audit
from app.db import platform_sessionmaker, tenant_sessionmaker
from app.engine.psychometrics import irt
from app.engine.psychometrics.bkt import DEMONSTRATED_AT
from app.models.platform import Tenant
from app.models.tenant import (Attempt, QuizItem, Response, ScoreRecord,
                               TaskItem)


async def gather(slug: str) -> list[tuple[str, str, bool]]:
    """Every (student, item, got-it-right) triple this institution has.

    Speech items are binarised at the platform's own "placement ready" line,
    the same threshold the readiness bands and BKT use — so an item's
    difficulty means the same thing as the score it was derived from.
    """
    triples: list[tuple[str, str, bool]] = []

    async with tenant_sessionmaker(slug)() as session:
        # Quiz responses are already binary and are the cleanest signal.
        # (Join replaced with an attempt->user map; Mongo has no server-side
        # join and the bridge does not pretend otherwise.)
        attempts = {a.id: a.user_id for a in (await session.execute(
            select(Attempt))).scalars().all()}
        for attempt_id, item_id, correct in (await session.execute(
            select(Response.attempt_id, Response.quiz_item_id,
                   Response.is_correct)
            .where(Response.quiz_item_id.is_not(None),
                   Response.is_correct.is_not(None))
        )).all():
            user_id = attempts.get(attempt_id)
            if user_id is None:
                continue
            triples.append((user_id, item_id, bool(correct)))

        # Speech items: the accuracy score if there is one, otherwise the
        # response-level overall. Nothing is invented for a skipped item.
        responses = {r.id: r for r in (await session.execute(
            select(Response)
            .where(Response.item_id.is_not(None),
                   Response.skipped.is_(False))
        )).scalars().all()}
        rows = (await session.execute(
            select(ScoreRecord.response_id, ScoreRecord.dimension,
                   ScoreRecord.score)
            .where(ScoreRecord.is_shadow.is_(False),
                   ScoreRecord.dimension.in_(["accuracy", "pronunciation"]))
        )).all()

        best: dict[tuple[str, str], float] = {}
        for response_id, dimension, score in rows:
            response = responses.get(response_id)
            if response is None:
                continue
            user_id = attempts.get(response.attempt_id)
            if user_id is None or response.item_id is None:
                continue
            key = (user_id, response.item_id)
            # Accuracy is the more direct evidence of "did they do this item";
            # pronunciation only stands in where accuracy was not scored.
            if dimension == "accuracy" or key not in best:
                best[key] = score
        for (user_id, item_id), score in best.items():
            triples.append((user_id, item_id, score >= DEMONSTRATED_AT))

    return triples


async def calibrate_tenant(slug: str, *, dry_run: bool = False) -> dict:
    triples = await gather(slug)
    if not triples:
        return {"slug": slug, "responses": 0, "calibrated": 0, "skipped": 0}

    result = irt.calibrate(triples)

    updated = 0
    async with tenant_sessionmaker(slug)() as session:
        task_items = {i.id: i for i in (await session.execute(
            select(TaskItem))).scalars().all()}
        quiz_items = {i.id: i for i in (await session.execute(
            select(QuizItem))).scalars().all()}

        for item_id, params in result.items.items():
            if not params.calibrated:
                continue
            row = task_items.get(item_id) or quiz_items.get(item_id)
            if row is None:
                continue
            if not dry_run:
                row.difficulty = round(params.difficulty, 3)
                row.discrimination = round(params.discrimination, 3)
                row.calibrated = True
            updated += 1

        if not dry_run:
            await session.commit()

    if updated and not dry_run:
        await audit.record_system(
            "items.calibrated", entity="TaskItem",
            after={"slug": slug, "calibrated": updated,
                   "responses": len(triples), "converged": result.converged})

    return {
        "slug": slug,
        "responses": len(triples),
        "items_seen": len(result.items),
        "calibrated": updated,
        "skipped": len(result.items) - result.calibrated_count,
        "converged": result.converged,
        "iterations": result.iterations,
        # The reasons are the useful output when nothing calibrates: usually
        # "only nine responses", which is a content problem, not a bug.
        "reasons": sorted({p.reason for p in result.items.values() if p.reason}),
    }


async def main(slug: str | None, dry_run: bool) -> None:
    if slug:
        slugs = [slug]
    else:
        async with platform_sessionmaker()() as session:
            slugs = [t.slug for t in (await session.execute(
                select(Tenant))).scalars().all()]

    prefix = "would calibrate" if dry_run else "calibrated"
    for one in slugs:
        report = await calibrate_tenant(one, dry_run=dry_run)
        print(f"{one}: {report['responses']} responses across "
              f"{report.get('items_seen', 0)} items -> {prefix} {report['calibrated']}, "
              f"skipped {report.get('skipped', 0)}")
        for reason in report.get("reasons", []):
            print(f"    not calibrated: {reason}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate the item bank")
    parser.add_argument("--tenant", help="one institution slug")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.tenant, args.dry_run))
