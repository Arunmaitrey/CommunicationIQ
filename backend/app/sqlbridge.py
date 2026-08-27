"""A tiny SQL-shaped query builder that runs over Beanie/MongoDB.

Why this exists: several routers and services were written against the
SQLAlchemy expression API (``select(Model).where(...)``) from the PostgreSQL
days. Real SQLAlchemy refuses to build those statements for Beanie document
classes — ``select(FakeClass)`` raises ``ArgumentError`` before the statement
ever reaches ``db.Session.execute`` — and Beanie's ``ExpressionField`` does not
implement ``.in_() / .is_() / .desc() / .asc()``, so even the argument lists
crash. The result was a family of 500s on exactly the endpoints that matter:
starting an attempt, submitting, scoring, listing tenant users.

This module gives those call sites a real implementation instead of leaving
them pointing at an ORM that is not installed against this database:

* ``select(...)``      -> a builder translated by ``db.Session.execute``
* ``func.count/sum/avg/min/max/coalesce`` aggregates (single-table)
* ``delete(M)`` / ``update(M).values(...)``
* ``or_(a, b, ...)``

It also patches Beanie's ``ExpressionField`` with the missing helper methods so
existing expressions like ``Response.id.in_(ids)`` or
``ScoreRecord.created_at.desc()`` construct cleanly.

Only the shapes actually used in this codebase are supported, on purpose: a
small honest bridge beats a half-faithful ORM.
"""
from __future__ import annotations

from typing import Any

from beanie.odm.fields import ExpressionField


# ---------------------------------------------------------------------------
# ExpressionField helpers — these did not exist and crashed on touch.
# ---------------------------------------------------------------------------

class _Sort:
    __slots__ = ("field", "direction")

    def __init__(self, field: ExpressionField, direction: int):
        self.field = str(field)
        self.direction = direction


def _in(self: ExpressionField, values: Any):
    from beanie.operators import In
    return In(str(self), list(values))


def _not_in(self: ExpressionField, values: Any):
    from beanie.operators import NotIn
    return NotIn(str(self), list(values))


def _is(self: ExpressionField, value: Any):
    if value is None:
        return {str(self): None}
    from beanie.operators import Eq
    return Eq(str(self), value)


def _is_not(self: ExpressionField, value: Any):
    if value is None:
        return {str(self): {"$ne": None}}
    from beanie.operators import Ne
    return Ne(str(self), value)


def _desc(self: ExpressionField) -> _Sort:
    return _Sort(self, -1)


def _asc(self: ExpressionField) -> _Sort:
    return _Sort(self, 1)


def _contains(self: ExpressionField, value: str):
    return {str(self): {"$regex": _regex_escape(value)}}


def _startswith(self: ExpressionField, value: str):
    return {str(self): {"$regex": "^" + _regex_escape(value)}}


def _regex_escape(text: str) -> str:
    import re
    return re.escape(text)


for _name, _fn in (("in_", _in), ("not_in", _not_in), ("is_", _is),
                   ("is_not", _is_not), ("desc", _desc), ("asc", _asc),
                   ("contains", _contains), ("startswith", _startswith)):
    setattr(ExpressionField, _name, _fn)


# ---------------------------------------------------------------------------
# Field -> owning-document registry
# ---------------------------------------------------------------------------

# ``Model.field`` only exists after init_beanie() attaches ExpressionField
# instances to each document class, one fresh object per class+field. Those
# instances are our handle back to the class, so column-only selects such as
# ``select(Tenant.slug)`` can find what they belong to at execution time.
_FIELD_OWNER: dict[int, type] = {}


def register_model(cls: type) -> None:
    """Remember which document class each of its ExpressionFields belongs to."""
    for name, info in getattr(cls, "model_fields", {}).items():
        field = getattr(cls, name, None)
        if isinstance(field, ExpressionField):
            _FIELD_OWNER[id(field)] = cls


def owner_of(column: Any) -> type | None:
    return _FIELD_OWNER.get(id(column))


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

class Select:
    """``select(entity_or_field, ...)`` — one entity, optionally projected."""

    def __init__(self, *entities: Any):
        self.entity: type | None = None
        self.columns: list[ExpressionField] = []
        for e in entities:
            if isinstance(e, ExpressionField):
                self.columns.append(e)
            elif isinstance(e, _Func):
                self.func = e
            elif self.entity is None and hasattr(e, "Settings"):
                self.entity = e
            else:
                raise TypeError(
                    f"select() cannot handle {e!r}; one document class and/or "
                    "its fields only")
        self._where: list[Any] = []
        self._sort: list[_Sort] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._from_model: type | None = None

    # -- builders ----------------------------------------------------------
    def where(self, *conditions: Any) -> "Select":
        self._where.extend(c for c in conditions if c is not None)
        return self

    def order_by(self, *cols: Any) -> "Select":
        for c in cols:
            if isinstance(c, _Sort):
                self._sort.append(c)
            elif isinstance(c, ExpressionField):
                self._sort.append(_Sort(c, 1))
        return self

    def limit(self, n: int) -> "Select":
        self._limit = int(n)
        return self

    def offset(self, n: int) -> "Select":
        self._offset = int(n)
        return self

    def select_from(self, model: type) -> "Select":
        """For aggregate selects: which table the count runs over."""
        self._from_model = model
        return self

    @property
    def is_count(self) -> bool:
        return getattr(self, "func", None) is not None \
            and self.func.fn == "count"


class _Func:
    __slots__ = ("fn", "arg", "args")

    def __init__(self, fn: str, *args: Any):
        self.fn = fn
        self.arg = args[0] if args else None
        self.args = args


class _FuncNamespace:
    """``func.count()``, ``func.sum(x)``, ``func.coalesce(a, b, ...)``."""

    def count(self) -> _Func:
        return _Func("count")

    def sum(self, col: Any) -> _Func:
        return _Func("sum", col)

    def avg(self, col: Any) -> _Func:
        return _Func("avg", col)

    def min(self, col: Any) -> _Func:
        return _Func("min", col)

    def max(self, col: Any) -> _Func:
        return _Func("max", col)

    def coalesce(self, *args: Any) -> _Func:
        return _Func("coalesce", *args)


func = _FuncNamespace()


class Delete:
    def __init__(self, model: type):
        self.model = model
        self._where: list[Any] = []

    def where(self, *conditions: Any) -> "Delete":
        self._where.extend(c for c in conditions if c is not None)
        return self


class Update:
    def __init__(self, model: type):
        self.model = model
        self._where: list[Any] = []
        self.values_map: dict[str, Any] = {}

    def where(self, *conditions: Any) -> "Update":
        self._where.extend(c for c in conditions if c is not None)
        return self

    def values(self, **kw: Any) -> "Update":
        self.values_map.update(kw)
        return self


class Or:
    """``or_(cond, ...)`` -> Beanie ``$or``."""

    def __init__(self, *conditions: Any):
        self.conditions = [c for c in conditions if c is not None]


def or_(*conditions: Any) -> Or:
    return Or(*conditions)


def select(*entities: Any) -> Select:
    return Select(*entities)


def delete(model: type) -> Delete:
    return Delete(model)


def update(model: type) -> Update:
    return Update(model)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_condition(cond: Any) -> Any:
    """Make any condition safe to hand to Beanie's find().

    Three jobs:

    * Turn every condition into a plain-dict Mongo filter.
    * Field names arrive as ``ExpressionField`` instances — a ``str``
      *subclass* whose ``__eq__`` is overridden to build query operators, so
      ``key == "id"`` is truthy for every field. Everything must go through
      ``str()`` before any comparison.
    * The primary key is stored as ``_id`` while every query here writes
      ``id``, and ``or_(...)`` groups become ``{"$or": [...]}``.
    """
    def _remap(items) -> dict:
        out: dict = {}
        for key, value in items:
            name = key if type(key) is str else str(key)
            out["_id" if name == "id" else name] = value
        return out

    if isinstance(cond, Or):
        return {"$or": [normalize_condition(c) for c in cond.conditions]}
    if isinstance(cond, dict):
        return _remap(cond.items())
    # Beanie comparison operators expose their filter as a mapping; some
    # versions via a `.query` property, all via `.items()`.
    if hasattr(cond, "query") and isinstance(cond.query, dict):
        return _remap(cond.query.items())
    if hasattr(cond, "items"):
        return _remap(cond.items())
    raise TypeError(f"unsupported condition type: {type(cond).__name__}")


def normalize_conditions(conditions: list[Any]) -> list[dict]:
    return [normalize_condition(c) for c in conditions]
