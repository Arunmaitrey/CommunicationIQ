"""Shared field types for the Beanie document models."""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator


def _coerce_str(v: Any) -> Any:
    """Accept anything id-like and store it as its string form.

    Documents inserted outside Beanie (seed scripts, manual mongo shell
    fixes) carry an ObjectId ``_id``. With ``id`` declared as plain ``str``,
    every read of such a row died in validation -- "Input should be a valid
    string" -- which is how sign-in started returning 500 for anyone whose
    directory row predated the ODM. Coercing at the field boundary makes old
    rows readable and keeps new ones unchanged.
    """
    if isinstance(v, (str, int, float)):
        return v
    return str(v)


StrId = Annotated[str, BeforeValidator(_coerce_str)]
