"""The durable narration job: create, claim, generate, validate, persist, retry.

The row IS the job (app.models.tenant.AttemptNarration). This module never
touches a ScoreRecord and never runs inside a scoring transaction — it reads a
finished AttemptResult and writes only its own row.

Concurrency safety in MongoDB uses atomic update operations instead of
SELECT ... FOR UPDATE SKIP LOCKED.
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import ensure_tenant_models
from app.models.tenant import Attempt, ConsentRecord, User
from app.narration import evidence as evidence_mod
from app.narration import validate as validate_mod
from app.narration.contract import NarratorError, RETRYABLE
from app.narration.providers import get_narrator

log = logging.getLogger("narration")

CLAIMABLE = ("pending", "retry_pending")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _tenant_docs(slug: str):
    """Get tenant-specific document classes for the given slug."""
    return await ensure_tenant_models(slug)


async def ai_consent_granted(slug: str, user_id: str) -> bool:
    """The student's latest ai_explanation decision. Absent = not granted."""
    docs = await _tenant_docs(slug)
    row = await docs.ConsentRecord.find(
        docs.ConsentRecord.user_id == user_id,
        docs.ConsentRecord.scope == "ai_explanation"
    ).sort(-docs.ConsentRecord.at).first_or_none()
    return bool(row and row.granted)


async def ensure_row(slug: str, attempt: Attempt) -> AttemptNarration | None:
    """Create the pending job for a scored attempt, once.

    Idempotent by the unique attempt_id: a second call returns the existing
    row. Returns None when narration is disabled or the student has not
    consented.
    """
    if not settings.narration_enabled:
        return None
    if attempt.status != "scored":
        return None

    docs = await _tenant_docs(slug)
    existing = await docs.AttemptNarration.find(
        docs.AttemptNarration.attempt_id == attempt.id
    ).first_or_none()
    if existing is not None:
        return existing

    user = await docs.User.get(attempt.user_id)
    if user is None or not await ai_consent_granted(slug, user.id):
        return None

    row = docs.AttemptNarration(
        attempt_id=attempt.id, status="pending", attempt_count=0,
        prompt_version=settings.narration_prompt_version,
        model_version=settings.narration_model,
        provider_key=settings.narration_provider,
    )
    await row.insert()
    return row


async def claim_due(slug: str, *, batch: int) -> list[str]:
    """Atomically claim up to `batch` due jobs; return their ids."""
    docs = await _tenant_docs(slug)
    now = _now()
    lease = now + timedelta(seconds=settings.narration_lease_seconds)
    claimed: list[str] = []

    filter_query = {
        "$or": [
            {"status": "pending"},
            {"status": "retry_pending", "next_retry_at": {"$lte": now}},
            {"status": "processing", "lease_until": {"$lte": now}},
        ]
    }

    candidates = await docs.AttemptNarration.find(filter_query).sort(+docs.AttemptNarration.created_at).limit(batch).to_list()

    for row in candidates:
        result = await docs.AttemptNarration.find_one(
            docs.AttemptNarration.id == row.id,
            docs.AttemptNarration.status == row.status
        ).update(
            {
                "$set": {
                    "status": "processing",
                    "lease_until": lease,
                    "next_retry_at": None,
                    "attempt_count": docs.AttemptNarration.attempt_count + 1,
                }
            }
        )
        if result.modified_count > 0:
            claimed.append(row.id)

    return claimed


async def claim_one(slug: str, narration_id: str) -> bool:
    """Atomically claim one specific job by id. Returns True if this call won it."""
    docs = await _tenant_docs(slug)
    now = _now()
    lease = now + timedelta(seconds=settings.narration_lease_seconds)

    row = await docs.AttemptNarration.find_one(docs.AttemptNarration.id == narration_id)
    if row is None:
        return False

    if row.status not in ("pending", "retry_pending", "processing"):
        return False
    if row.status == "retry_pending" and row.next_retry_at and row.next_retry_at > now:
        return False
    if row.status == "processing" and row.lease_until and row.lease_until > now:
        return False

    result = await docs.AttemptNarration.find_one(docs.AttemptNarration.id == narration_id).update(
        {
            "$set": {
                "status": "processing",
                "lease_until": lease,
                "next_retry_at": None,
                "attempt_count": docs.AttemptNarration.attempt_count + 1,
            }
        }
    )
    return result.modified_count > 0


def _backoff_seconds(attempt_count: int) -> float:
    """Exponential backoff with full jitter, capped."""
    base = settings.narration_backoff_base_s * (2 ** max(0, attempt_count - 1))
    capped = min(base, settings.narration_backoff_cap_s)
    return random.uniform(capped / 2, capped)


async def generate_one(slug: str, narration_id: str) -> str:
    """Generate one claimed job to a terminal-or-retry state. Returns status."""
    docs = await _tenant_docs(slug)
    row = await docs.AttemptNarration.find_one(docs.AttemptNarration.id == narration_id)
    if row is None or row.status != "processing":
        return "skipped"

    try:
        attempt = await docs.Attempt.get(row.attempt_id)
        if attempt is None:
            raise NarratorError("no_evidence", "attempt vanished")

        from app.routers.attempts import _result
        result = await _result(attempt)
        user = await docs.User.get(attempt.user_id)
        l1 = (user.l1_language if user else "") or ""

        ev = evidence_mod.build(result, l1_language=l1)
        provider = get_narrator(row.provider_key)
        draft = await provider.narrate(ev, timeout_s=settings.narration_timeout_s)
        clean = validate_mod.check(draft, ev)

    except NarratorError as err:
        return await _record_failure(row, err)
    except Exception as err:
        return await _record_failure(row, NarratorError("transient", type(err).__name__))

    row.status = "ready"
    row.headline = clean.headline
    row.summary = clean.summary
    row.primary_focus = clean.primary_focus
    row.practice_action = clean.practice_action
    row.caveats = clean.caveats
    row.model_version = clean.model_version or row.model_version
    row.provider_latency_ms = clean.latency_ms
    row.input_tokens = clean.input_tokens
    row.output_tokens = clean.output_tokens
    row.last_error_category = ""
    row.last_error_detail = ""
    row.next_retry_at = None
    row.lease_until = None
    row.generated_at = _now()
    await row.save()
    log.info("narration ready id=%s attempts=%s latency_ms=%s tokens=%s/%s",
             row.id, row.attempt_count, row.provider_latency_ms,
             row.input_tokens, row.output_tokens)
    return "ready"


async def _record_failure(row, err: NarratorError) -> str:
    row.last_error_category = err.category
    row.last_error_detail = err.detail
    row.lease_until = None
    retryable = err.category in RETRYABLE
    if retryable and row.attempt_count < settings.narration_max_attempts:
        row.status = "retry_pending"
        row.next_retry_at = _now() + timedelta(seconds=_backoff_seconds(row.attempt_count))
        outcome = "retry_pending"
    else:
        row.status = "failed"
        row.next_retry_at = None
        outcome = "failed"
    await row.save()
    log.warning("narration %s id=%s category=%s attempts=%s detail=%s",
                outcome, row.id, err.category, row.attempt_count, err.detail)
    return outcome
