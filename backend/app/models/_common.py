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
