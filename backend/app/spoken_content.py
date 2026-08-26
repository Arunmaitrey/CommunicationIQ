"""Content relevance for spoken task types the frozen pipeline does not cover.

Conversation Question and Passage Question ask the candidate to say, out loud,
what they understood. If the answer is wrong, the delivery scores are beside
the point -- so *whether the answer was right* is the measurement, and the
other four dimensions are context for it.

The pipeline already knows how to make that measurement. It gates it on a set
of three task types::

    if transcript.text and task_type in {"story_retell", "open_response",
                                         "short_answer"}:

which was written when those were the only unscripted speaking tasks that
existed. Adding two names to that set would be a one-line change to
``app/engine/pipeline.py`` -- and ``app/engine/pipeline.py`` is on
``SCORING_PATH``. Editing it moves the engine hash, which retires the current
baseline and invalidates any study frozen against it. The freeze is doing
exactly what it was built to do: it is refusing to let the scoring engine
change quietly while a study depends on it.

(The baseline has since been re-cut as ``validation-baseline-v4``, for
changes that were genuinely engine changes and were made deliberately, with
the reasons written into the baseline's own note. That is the freeze working
as intended too -- it does not forbid changing the engine, it forbids
changing it silently. This module still belongs above the path: moving it
down would put content scoring for these two task types inside the hash for
no gain.)

So the same provider, with the same rubric, is invoked from here instead --
above the frozen path, after the engine has produced a transcript. Nothing
about how content is measured changes; only where the call is made from. When
a new baseline is next cut, moving these two names into the pipeline's own set
and deleting this module is the right cleanup.

Run once, at submit, before the attempt is finalised. Not in the background
task beside the engine: submit waits for the engine's own pending work and
would happily finalise an attempt while a background content call was still in
flight, and a dimension that lands after the overall is computed is a
dimension nobody sees.
"""
from __future__ import annotations

import logging

from app.db import select

from app.engine.contracts.types import Capability, ProviderUnavailable
from app.engine.pipeline import SCALE_MAX, SCALE_MIN, band_label
from app.models.tenant import (FeatureRecord, ProfileSection, Response,
                               ScoreRecord, TaskItem)

log = logging.getLogger(__name__)

# Task types whose content the pipeline's gate does not reach.
SCORED_HERE = frozenset({"conversation_question", "passage_question"})


async def score_pending(tenant, providers, tenant_id: str | None,
                        attempt_id: str) -> int:
    """Add a content score to every answer of these types that lacks one.

    Idempotent, and returns how many it added so a caller can assert on it.
    An answer with no transcript gets nothing rather than a zero: the engine
    could not hear it, which is a fact about the recording and not about
    whether the candidate understood. ``_unscored_reasons`` in the attempts
    router notices the missing dimension and says so.
    """
    rows = list((await tenant.execute(
        select(Response, ProfileSection.task_type)
        .join(ProfileSection, ProfileSection.id == Response.section_id)
        .where(Response.attempt_id == attempt_id,
               ProfileSection.task_type.in_(sorted(SCORED_HERE)))
    )).all())
    if not rows:
        return 0

    added = 0
    for response, task_type in rows:
        if response.skipped:
            continue

        already = (await tenant.execute(
            select(ScoreRecord.id).where(ScoreRecord.response_id == response.id,
                                         ScoreRecord.dimension == "content")
        )).scalars().first()
        if already is not None:
            continue

        feature = (await tenant.execute(
            select(FeatureRecord).where(FeatureRecord.response_id == response.id)
        )).scalars().first()
        transcript = (feature.transcript if feature else "") or ""
        if not transcript.strip():
            continue

        item = (await tenant.get(TaskItem, response.item_id)
                if response.item_id else None)
        rubric = dict(item.rubric or {}) if item else {}
        if not [p for p in (rubric.get("key_points") or []) if str(p).strip()]:
            # Nothing written down to mark against. Guessing at what a good
            # answer contains is the one thing the content measure promises
            # not to do.
            log.warning("no rubric for %s on response %s", task_type, response.id)
            continue

        try:
            relevance, meta = await providers.invoke(
                Capability.CONTENT_RELEVANCE, tenant_id,
                lambda impl: impl.score(transcript, rubric=rubric,
                                        task_type=task_type),
            )
        except ProviderUnavailable as exc:
            log.warning("no content-relevance provider: %s", exc)
            return added
        if relevance.confidence <= 0:
            continue

        tenant.add(ScoreRecord(
            attempt_id=response.attempt_id, response_id=response.id,
            dimension="content", score=round(relevance.score, 1),
            scale_min=SCALE_MIN, scale_max=SCALE_MAX,
            band=band_label(relevance.score), confidence=relevance.confidence,
            provider_id=getattr(meta, "provider_id", "") or "",
            provider_key=getattr(meta, "provider_key", "") or "content_relevance",
            provider_version=getattr(meta, "version", "") or "0.1.0",
        ))
        added += 1

    if added:
        await tenant.commit()
    return added
