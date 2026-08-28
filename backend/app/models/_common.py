"""Shared field types for the Beanie document models."""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator


def _coerce_str(v: Any) -> Any:
    """Accept anything id-like and store it as its string form."""
    if isinstance(v, (str, int, float)):
        return v
    try:
        return str(v)
    except Exception:
        return v


StrId = Annotated[str, BeforeValidator(_coerce_str)]


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
    older documents and some insert paths store plain 0.  This patch replaces
    the field annotation so parsing succeeds for both.
    """
    from beanie import Document as _Doc
    from pydantic import Field as _Field

    _annotation = Annotated[str | None, BeforeValidator(_coerce_revision_id)]
    _Doc.model_fields["revision_id"] = _Field(default=None, alias="revision_id",
                                              annotation=_annotation)


patch_beanie_revision_id()
