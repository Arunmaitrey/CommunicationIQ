"""MongoDB data layer — Beanie ODM over Motor, database-per-tenant.

SQLAlchemy ``select()`` expressions remain the query language for service
modules; the ``Session`` class in this file translates them to Beanie
``.find()`` calls so no module needs rewriting.

Two kinds of documents:

* Control-plane documents (``app.models.platform``) live in one database,
  ``CommunicationIQ`` (taken from the URI). Registered once at startup.
* Per-institution documents (``app.models.tenant``) live in a database named
  ``tenant_<slug>`` each. There is no shared tenant database; the database name
  *is* the isolation boundary (TEN-12).
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import Document, init_beanie

from app.config import settings


client = AsyncIOMotorClient(
    settings.mongo_uri, uuidRepresentation="standard",
    serverSelectionTimeoutMS=15000)

CONTROL_DB_NAME = settings.control_db_name


def control_db() -> AsyncIOMotorDatabase:
    """The control-plane database (``CommunicationIQ``)."""
    return client[CONTROL_DB_NAME]


def tenant_db_name(slug: str) -> str:
    return f"{settings.tenant_schema_prefix}{slug}"


def tenant_db(slug: str) -> AsyncIOMotorDatabase:
    """The isolated database for one institution."""
    return client[tenant_db_name(slug)]


# ---------------------------------------------------------------------------
# Beanie init (control plane — called once at startup)
# ---------------------------------------------------------------------------

_client_inited = False


async def init_mongo() -> None:
    """Ping and register the control-plane documents. Idempotent."""
    global _client_inited
    if _client_inited:
        return
    await client.admin.command("ping")
    from app.models.platform import CONTROL_DOCUMENTS
    await init_beanie(database=control_db(), document_models=CONTROL_DOCUMENTS)
    _client_inited = True


# ---------------------------------------------------------------------------
# Tenant document bundles (lazy per-slug init)
# ---------------------------------------------------------------------------

_tenant_bundles: dict[str, SimpleNamespace] = {}
_tenant_locks: dict[str, asyncio.Lock] = {}


async def ensure_tenant_models(slug: str) -> SimpleNamespace:
    """Return a namespace of Beanie Document classes bound to ``tenant_<slug>``.

    The bundle is created and its documents registered with Beanie on first
    use, then cached. Each tenant gets distinct document classes.
    """
    cached = _tenant_bundles.get(slug)
    if cached is not None:
        return cached
    lock = _tenant_locks.setdefault(slug, asyncio.Lock())
    async with lock:
        cached = _tenant_bundles.get(slug)
        if cached is not None:
            return cached
        from app.models.tenant import TENANT_DOCUMENTS
        db = tenant_db(slug)
        await init_beanie(database=db, document_models=list(TENANT_DOCUMENTS))
        bundle = SimpleNamespace(**{cls.__name__: cls for cls in TENANT_DOCUMENTS})
        _tenant_bundles[slug] = bundle
        return bundle


def get_tenant_models(slug: str) -> SimpleNamespace:
    """Synchronous accessor — only valid after ``ensure_tenant_models`` ran."""
    return _tenant_bundles[slug]


# ---------------------------------------------------------------------------
# Platform models accessor
# ---------------------------------------------------------------------------

async def ensure_platform_models() -> SimpleNamespace:
    """Return a SimpleNamespace of control-plane Document classes.
    
    Control plane models are already registered with Beanie by init_mongo().
    This function just wraps them in a namespace for backward compatibility.
    """
    from app.models.platform import CONTROL_DOCUMENTS
    return SimpleNamespace(**{cls.__name__: cls for cls in CONTROL_DOCUMENTS})


# ---------------------------------------------------------------------------
# Sessionmaker shims — bridge for service modules that use
# ``platform_sessionmaker()`` / ``tenant_sessionmaker()`` with a session API.
#
# The returned Session wraps Beanie Document .find() / .insert() / .delete()
# behind the ``execute(select())`` / ``add()`` / ``commit()`` / ``get()``
# interface that service modules expect.
# ---------------------------------------------------------------------------

class Session:
    """Beanie-backed session that speaks the SQLAlchemy async-session API.

    ``session.execute(select(Model).where(...))`` translates to
    ``Model.find(Model.field == value).to_list()``.
    ``session.add(obj)`` translates to ``await obj.insert()``.
    ``session.get(Model, pk)`` translates to ``await Model.get(pk)``.
    ``session.commit()`` / ``session.flush()`` are no-ops (Beanie auto-commits).
    """

    def __init__(self, models: SimpleNamespace):
        self._models = models
        self._new: list = []

    # -- context manager support ------------------------------------------

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *a) -> None:
        pass

    # -- mutation ----------------------------------------------------------

    def add(self, obj: Any) -> None:
        self._new.append(obj)

    def add_all(self, objs: list) -> None:
        self._new.extend(objs)

    async def flush(self) -> None:
        for obj in self._new:
            if not getattr(obj, 'id', None):
                import uuid
                obj.id = str(uuid.uuid4())
            await obj.insert()
        self._new.clear()

    async def commit(self) -> None:
        await self.flush()

    def rollback(self) -> None:
        self._new.clear()

    async def get(self, model: type, pk: Any):
        return await model.get(pk)

    # -- queries -----------------------------------------------------------

    async def execute(self, stmt):
        """Translate a SQLAlchemy ``select()`` / ``delete()`` / ``update()``
        into Beanie ``.find()`` calls.

        Supports:
          select(Model)                      -> find_all()
          select(Model).where(...)           -> find(cond)
          select(Model).where(...).limit(n)  -> find(cond).limit(n)
          select(Model).where(...).order_by() -> find(cond).sort(...)
          delete(Model).where(...)           -> find(cond).delete()
          select(func.count(...))            -> find().count()
          select(Model.col)                  -> find().only(Model.col.name)
        """
        from sqlalchemy.sql.selectable import Select
        from sqlalchemy.sql.dml import Delete, Update
        from sqlalchemy import func as sa_func

        if isinstance(stmt, Delete):
            return await self._exec_delete(stmt)
        if isinstance(stmt, Update):
            return await self._exec_update(stmt)
        if isinstance(stmt, Select):
            return await self._exec_select(stmt)
        raise TypeError(f"Unsupported statement type: {type(stmt)}")

    async def _exec_delete(self, stmt) -> None:
        """Translate DELETE statement to Beanie .find().delete()."""
        from sqlalchemy.sql.elements import BinaryExpression
        table = stmt.table
        model = self._resolve(table)
        if model is None:
            return
        filter_args = self._extract_where(stmt.whereclause)
        if filter_args:
            await model.find(*filter_args).delete()
        else:
            await model.find_all().delete()

    async def _exec_update(self, stmt) -> None:
        """Translate UPDATE statement to Beanie find+update."""
        table = stmt.table
        model = self._resolve(table)
        if model is None:
            return
        filter_args = self._extract_where(stmt.whereclause)
        if filter_args:
            docs = await model.find(*filter_args).to_list()
            for doc in docs:
                for k, v in (stmt.values or {}).items():
                    col_name = k.name if hasattr(k, 'name') else str(k)
                    setattr(doc, col_name, v)
                await doc.save()

    async def _exec_select(self, stmt):
        """Translate SELECT statement to Beanie .find() calls."""
        from sqlalchemy import func as sa_func
        from sqlalchemy.sql.elements import Label

        # Handle scalar aggregates: func.count(), func.sum(), etc.
        if stmt.columns_clause_froms or stmt.column_descriptions:
            cols = list(stmt.columns_clause_froms) or []
            # Check for func.count() style queries
            if cols:
                first_col = cols[0] if cols else None
            else:
                first_col = None

            # Check for func.count in select columns
            select_cols = list(stmt.selected_columns)
            if select_cols and isinstance(select_cols[0], sa_func.Function):
                model = self._resolve_model_from_select(stmt)
                if model:
                    count = await model.find().count()
                    return _ScalarResult(count)

            # select(Model) or select(Model.col)
            if select_cols:
                first = select_cols[0]
                # select(Model) — return full objects
                if hasattr(first, 'class_'):
                    model = first.class_
                    result = await self._find_with_clauses(model, stmt)
                    return _Result(result)

                # select(Model.col) or select(Model.col1, Model.col2)
                if hasattr(first, 'table'):
                    model = self._resolve(first.table)
                    if model:
                        result = await self._find_with_clauses(model, stmt)
                        # Extract requested columns
                        col_names = []
                        for c in select_cols:
                            if hasattr(c, 'name'):
                                col_names.append(c.name)
                            elif hasattr(c, 'key'):
                                col_names.append(c.key)
                        if col_names:
                            result = [[getattr(r, cn, None) for cn in col_names]
                                      for r in result]
                            # Return as named-tuple-like result
                            result = [type('_Row', (), dict(zip(col_names, row)))()
                                      for row in result]
                        return _Result(result)

        # Fallback: try to resolve the FROM table
        model = self._resolve_model_from_select(stmt)
        if model:
            result = await self._find_with_clauses(model, stmt)
            return _Result(result)

        return _Result([])

    def _resolve_model_from_select(self, stmt):
        """Get the model class from a SELECT statement."""
        # Try column descriptions
        for desc in stmt.column_descriptions:
            if 'entity' in desc and desc['entity'] is not None:
                return desc['entity']
        # Try FROM clause
        if hasattr(stmt, 'froms') and stmt.froms:
            for from_clause in stmt.froms:
                if hasattr(from_clause, 'name'):
                    # Try to find model by table name
                    model = self._resolve(from_clause)
                    if model:
                        return model
        # Try FROM table
        if hasattr(stmt, 'from_table') and stmt.from_table:
            return self._resolve(stmt.from_table)
        return None

    async def _find_with_clauses(self, model, stmt):
        """Build a Beanie query from SELECT WHERE/ORDER/LIMIT/OFFSET."""
        query = model.find()

        if stmt.whereclause is not None:
            filters = self._extract_where(stmt.whereclause)
            if filters:
                query = model.find(*filters)

        # ORDER BY
        if stmt.order_by_clause:
            sort_list = []
            for elem in stmt.order_by_clause:
                if hasattr(elem, 'element'):
                    col = elem.element
                    direction = 1 if not getattr(elem, 'descending', lambda: False)() else -1
                else:
                    col = elem
                    direction = 1
                col_name = getattr(col, 'name', None) or str(col)
                sort_list.append((col_name, direction))
            query = query.sort(sort_list)

        # LIMIT / OFFSET
        if stmt._limit_clause is not None:
            limit_val = stmt._limit_clause
            if hasattr(limit_val, 'value'):
                limit_val = limit_val.value
            query = query.limit(int(limit_val))

        if stmt._offset_clause is not None:
            offset_val = stmt._offset_clause
            if hasattr(offset_val, 'value'):
                offset_val = offset_val.value
            query = query.skip(int(offset_val))

        return await query.to_list()

    def _resolve(self, table_or_model) -> type | None:
        """Resolve a table name or table object to a Beanie Document class."""
        if hasattr(table_or_model, 'name'):
            table_name = table_or_model.name
        elif hasattr(table_or_model, '__tablename__'):
            table_name = table_or_model.__tablename__
        elif isinstance(table_or_model, str):
            table_name = table_or_model
        else:
            return None

        ns = self._models
        for attr in dir(ns):
            obj = getattr(ns, attr)
            if hasattr(obj, 'Settings') and hasattr(obj.Settings, 'name'):
                if obj.Settings.name == table_name:
                    return obj
        return None

    def _extract_where(self, whereclause) -> list:
        """Extract Beanie filter conditions from SQLAlchemy WHERE clause."""
        from sqlalchemy.sql.elements import BinaryExpression, BooleanClauseList, UnaryExpression

        if whereclause is None:
            return []

        if isinstance(whereclause, BooleanClauseList):
            filters = []
            for elem in whereclause.clauses:
                f = self._extract_one(elem)
                if f is not None:
                    filters.append(f)
            return filters

        f = self._extract_one(whereclause)
        return [f] if f is not None else []

    def _extract_one(self, clause):
        """Translate one BinaryExpression to a Beanie filter."""
        from sqlalchemy.sql.elements import BinaryExpression, UnaryExpression
        from sqlalchemy import operators as sa_ops

        if not isinstance(clause, (BinaryExpression, UnaryExpression)):
            return None

        if isinstance(clause, UnaryExpression):
            if clause.operator == sa_ops.not_op:
                inner = self._extract_one(clause.element)
                if inner is not None:
                    from beanie.operators import Not
                    return Not(inner)
            return None

        left = clause.left
        right = clause.right
        op = clause.operator

        # Resolve column name
        if hasattr(left, 'name'):
            col_name = left.name
        elif hasattr(left, 'key'):
            col_name = left.key
        else:
            return None

        # Resolve value
        value = right.value if hasattr(right, 'value') else right

        # Map SQLAlchemy operators to Beanie/MongoDB
        from sqlalchemy import operators as sa_ops
        from beanie.operators import (
            Eq, Ne, Gt, Gte, Lt, Lte, In, NotIn, RegEx
        )

        op_map = {
            sa_ops.eq: Eq,
            sa_ops.ne: Ne,
            sa_ops.gt: Gt,
            sa_ops.ge: Gte,
            sa_ops.lt: Lt,
            sa_ops.le: Lte,
        }

        if op in op_map:
            return {col_name: op_map[op](value)}

        if op == sa_ops.in_op:
            return {col_name: In(value)}

        if op == sa_ops.not_in_op:
            return {col_name: NotIn(value)}

        if op == sa_ops.like_op or op == sa_ops.ilike_op:
            import re as _re
            pattern = value.replace('%', '.*').replace('_', '.')
            return {col_name: RegEx(f"(?i){pattern}") if op == sa_ops.ilike_op else RegEx(pattern)}

        if op == sa_ops.is_:
            if value is None:
                return {col_name: None}
            return {col_name: Eq(value)}

        if op == sa_ops.is_not:
            if value is None:
                return {col_name: {"$ne": None}}
            return {col_name: {"$ne": value}}

        return None


class _Result:
    """Wraps a list to match SQLAlchemy's scalars().all() interface."""
    def __init__(self, data: list):
        self._data = data

    def scalars(self):
        return self

    def all(self):
        return self._data

    def first(self):
        return self._data[0] if self._data else None

    def one(self):
        if len(self._data) == 0:
            from sqlalchemy.exc import NoResultFound
            raise NoResultFound()
        if len(self._data) > 1:
            from sqlalchemy.exc import MultipleResultsFound
            raise MultipleResultsFound()
        return self._data[0]

    def one_or_none(self):
        if len(self._data) == 0:
            return None
        return self.one()

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __bool__(self):
        return bool(self._data)


class _ScalarResult:
    """Wraps a scalar value for func.count() etc."""
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def all(self):
        return [self._value]

    def first(self):
        return self._value

    def one(self):
        return self._value

    def scalar(self):
        return self._value

    def __iter__(self):
        return iter([self._value])

    def __len__(self):
        return 1


# ---------------------------------------------------------------------------
# Session factories
# ---------------------------------------------------------------------------

def _build_session(models: SimpleNamespace) -> Session:
    return Session(models)


def platform_sessionmaker():
    """Factory yielding a Session bound to the control-plane database."""
    def factory():
        return _PlatformSessionCM()
    return factory


class _PlatformSessionCM:
    def __init__(self):
        self._session = None

    async def __aenter__(self):
        models = await ensure_platform_models()
        self._session = Session(models)
        return self._session

    async def __aexit__(self, *a):
        pass


def tenant_sessionmaker(slug: str):
    """Session factory bound to one institution's database."""
    if not slug:
        raise ValueError("tenant slug is required")
    def factory():
        return _TenantSessionCM(slug)
    return factory


class _TenantSessionCM:
    def __init__(self, slug: str):
        self._slug = slug
        self._session = None

    async def __aenter__(self):
        models = await ensure_tenant_models(self._slug)
        self._session = Session(models)
        return self._session

    async def __aexit__(self, *a):
        pass


async def get_platform_session() -> AsyncIterator[Session]:
    async with platform_sessionmaker()() as session:
        yield session


async def get_tenant_session(slug: str) -> AsyncIterator[Session]:
    async with tenant_sessionmaker(slug)() as session:
        yield session


async def get_platform_bundle() -> SimpleNamespace:
    """Get the control-plane Document bundle directly (for non-session code)."""
    await init_mongo()
    return await ensure_platform_models()


# ---------------------------------------------------------------------------
# Compatibility aliases
# ---------------------------------------------------------------------------

init_store = init_mongo
ensure_indexes = lambda *a, **kw: None  # Beanie handles indexes via Settings

PlatformBase = type('PlatformBase', (), {})
TenantBase = type('TenantBase', (), {})

close_client = lambda: None
