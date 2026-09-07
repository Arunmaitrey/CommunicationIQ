"""Shared field types for the Beanie document models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BeforeValidator


def _coerce_created_at(v: Any) -> Any:
    """Treat a stored null the same as a genuinely missing field.

    ``Field(default_factory=...)`` only fires when the key is absent from the
    document entirely -- it does nothing when the key is present with value
    ``None``, which is exactly how most of the content bank was written
    (confirmed: 5291/5291 quiz_items, and the large majority of task_items,
    reading_passages, listening_passages and writing_prompts all store
    ``created_at: null``). A non-Optional ``datetime`` field rejects that
    outright, so fetching almost any question -- which every attempt-start
    does -- raised a ValidationError with no handler above it, which is why
    the browser saw a bare connection failure (reported as a CORS block)
    instead of a clean error.
    """
    if v is None:
        return datetime.now(timezone.utc)
    return v


CreatedAt = Annotated[datetime, BeforeValidator(_coerce_created_at)]


def _coerce_str(v: Any) -> Any:
    """Accept anything id-like and store it as its string form.

    Real documents in the shared database were written by more than one code
    path over time; some let Mongo default `_id` to an ObjectId instead of
    this app's string-UUID convention (confirmed on `cohort_members`,
    `users`, `score_records`). Beanie validates every fetched document
    against the typed model, so without this, reading one of those rows
    raises instead of just working.
    """
    if isinstance(v, (str, int, float)):
        return v
    try:
        return str(v)
    except Exception:
        return v


StrId = Annotated[str, BeforeValidator(_coerce_str)]


async def get_tolerant(document_cls, id_value: str):
    """``Document.get()``, but also tries the id as a Mongo ObjectId.

    ``StrId`` lets a document with a real ObjectId ``_id`` be *read* without
    Beanie's validator rejecting it -- but ``Document.get(id_value)`` builds
    its filter from the plain string, which never matches a document whose
    ``_id`` is actually stored as BSON ObjectId. Some ExamTest rows (the
    company-round ones seeded outside this app's own uuid4 path) are exactly
    that: ``ExamTest.get("<24-hex-chars>")`` returns None even though the
    document exists, so every route built on it 404s or 400s. This retries
    the same lookup with the string parsed as an ObjectId when the first
    attempt comes up empty and the string is even shaped like one.
    """
    found = await document_cls.get(id_value)
    if found is not None:
        return found
    from bson import ObjectId
    from bson.errors import InvalidId
    try:
        oid = ObjectId(id_value)
    except (InvalidId, TypeError):
        return None
    return await document_cls.find_one({"_id": oid})


def _coerce_revision_id(v: Any) -> Any:
    """Accept int, str, or None for Beanie's revision_id field."""
    if v is None:
        return v
    if isinstance(v, int):
        return str(v)
    return v


def patch_beanie_revision_id() -> None:
    """Make Document.revision_id tolerate int values stored in MongoDB.

    Beanie's Document base class declares revision_id as Optional[UUID], but
    some insert paths store plain 0. This patch replaces the field
    annotation so parsing succeeds for both.
    """
    from beanie import Document as _Doc
    from pydantic import Field as _Field

    _annotation = Annotated[str | None, BeforeValidator(_coerce_revision_id)]
    _Doc.model_fields["revision_id"] = _Field(default=None, alias="revision_id",
                                              annotation=_annotation)


patch_beanie_revision_id()
