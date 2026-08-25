"""MongoDB data layer — Beanie ODM over Motor, database-per-tenant.

Two kinds of documents:

* Control-plane documents (``app.models.platform``) live in one database,
  ``CommunicationIQ`` (taken from the URI). Registered once at startup.
* Per-institution documents (``app.models.tenant``) live in a database named
  ``tenant_<slug>`` each.
"""
from __future__ import annotations

import asyncio
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
    return client[CONTROL_DB_NAME]


def tenant_db_name(slug: str) -> str:
    return f"{settings.tenant_schema_prefix}{slug}"


def tenant_db(slug: str) -> AsyncIOMotorDatabase:
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
#
# Beanie 2.0 stores the DB reference on the class object itself.  When we
# call init_beanie(db_A, [User, Attempt, ...]) and then later
# init_beanie(db_B, [User, Attempt, ...]) the second call overwrites the
# first's binding.  We fix this by creating per-tenant subclasses that each
# carry their own _database reference.
# ---------------------------------------------------------------------------

_tenant_bundles: dict[str, SimpleNamespace] = {}
_tenant_locks: dict[str, asyncio.Lock] = {}


def _make_tenant_subclasses(slug: str, base_docs: list) -> list:
    """Create per-tenant Document subclasses.

    Each subclass is created via ``type()`` *without* putting ``Settings``
    in the namespace (which would trigger a Pydantic field-detection error),
    then we patch ``Settings`` as a plain class attribute after creation.
    """
    subclasses = []
    for cls in base_docs:
        orig_name = cls.__name__
        sub = type(
            orig_name,
            (cls,),
            {
                "__qualname__": f"{orig_name}_{slug}",
                "__module__": cls.__module__,
            },
        )
        # Patch Settings after class creation — Pydantic won't re-inspect.
        sub.Settings = type("Settings", (), {"name": cls.Settings.name})
        subclasses.append(sub)
    return subclasses


async def ensure_tenant_models(slug: str) -> SimpleNamespace:
    """Return a namespace of Beanie Document classes bound to ``tenant_<slug>``.

    The bundle is created and its documents registered with Beanie on first
    use, then cached.  Each tenant gets distinct document subclasses so that
    multiple tenants coexist without init_beanie clobbering DB bindings.
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
        tenant_docs = _make_tenant_subclasses(slug, list(TENANT_DOCUMENTS))
        await init_beanie(database=db, document_models=tenant_docs)
        bundle = SimpleNamespace(**{cls.__name__: cls for cls in tenant_docs})
        _tenant_bundles[slug] = bundle
        return bundle


def get_tenant_models(slug: str) -> SimpleNamespace:
    """Synchronous accessor — only valid after ``ensure_tenant_models`` ran."""
    return _tenant_bundles[slug]


# ---------------------------------------------------------------------------
# Platform models accessor
# ---------------------------------------------------------------------------

async def ensure_platform_models() -> SimpleNamespace:
    from app.models.platform import CONTROL_DOCUMENTS
    return SimpleNamespace(**{cls.__name__: cls for cls in CONTROL_DOCUMENTS})


# ---------------------------------------------------------------------------
# Session bridge — for service modules that still use
# session.execute(select(...)) / session.add(obj) / session.commit()
# ---------------------------------------------------------------------------

class Session:
    """Beanie-backed session that speaks the SQLAlchemy async-session API."""

    def __init__(self, models: SimpleNamespace):
        self._models = models
        self._new: list = []

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *a) -> None:
        pass

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

    async def execute(self, stmt):
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
        from sqlalchemy import func as sa_func

        select_cols = list(stmt.selected_columns)
        if select_cols and isinstance(select_cols[0], sa_func.Function):
            model = self._resolve_model_from_select(stmt)
            if model:
                count = await model.find().count()
                return _ScalarResult(count)

        if select_cols:
            first = select_cols[0]
            if hasattr(first, 'class_'):
                model = first.class_
                result = await self._find_with_clauses(model, stmt)
                return _Result(result)
            if hasattr(first, 'table'):
                model = self._resolve(first.table)
                if model:
                    result = await self._find_with_clauses(model, stmt)
                    col_names = [c.name if hasattr(c, 'name') else c.key
                                 for c in select_cols if hasattr(c, 'name') or hasattr(c, 'key')]
                    if col_names:
                        result = [type('_Row', (), dict(zip(col_names, row)))()
                                  for row in
                                  [[getattr(r, cn, None) for cn in col_names] for r in result]]
                    return _Result(result)

        model = self._resolve_model_from_select(stmt)
        if model:
            result = await self._find_with_clauses(model, stmt)
            return _Result(result)
        return _Result([])

    def _resolve_model_from_select(self, stmt):
        for desc in stmt.column_descriptions:
            if 'entity' in desc and desc['entity'] is not None:
                return desc['entity']
        if hasattr(stmt, 'froms') and stmt.froms:
            for fc in stmt.froms:
                if hasattr(fc, 'name'):
                    m = self._resolve(fc)
                    if m:
                        return m
        if hasattr(stmt, 'from_table') and stmt.from_table:
            return self._resolve(stmt.from_table)
        return None

    async def _find_with_clauses(self, model, stmt):
        query = model.find()

        if stmt.whereclause is not None:
            filters = self._extract_where(stmt.whereclause)
            if filters:
                query = model.find(*filters)

        if stmt.order_by_clause:
            sort_list = []
            for elem in stmt.order_by_clause:
                col = elem.element if hasattr(elem, 'element') else elem
                direction = 1 if not getattr(elem, 'descending', lambda: False)() else -1
                col_name = getattr(col, 'name', None) or str(col)
                sort_list.append((col_name, direction))
            query = query.sort(sort_list)

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

    def _resolve(self, table_or_model):
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
        from sqlalchemy.sql.elements import BooleanClauseList
        if whereclause is None:
            return []
        if isinstance(whereclause, BooleanClauseList):
            return [f for elem in whereclause.clauses
                    if (f := self._extract_one(elem)) is not None]
        f = self._extract_one(whereclause)
        return [f] if f is not None else []

    def _extract_one(self, clause):
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
        col_name = getattr(left, 'name', None) or getattr(left, 'key', None)
        if col_name is None:
            return None
        value = right.value if hasattr(right, 'value') else right

        from sqlalchemy import operators as sa_ops
        from beanie.operators import Eq, Ne, Gt, Gte, Lt, Lte, In, NotIn, RegEx

        op_map = {sa_ops.eq: Eq, sa_ops.ne: Ne, sa_ops.gt: Gt, sa_ops.ge: Gte,
                  sa_ops.lt: Lt, sa_ops.le: Lte}
        if op in op_map:
            return {col_name: op_map[op](value)}
        if op == sa_ops.in_op:
            return {col_name: In(value)}
        if op == sa_ops.not_in_op:
            return {col_name: NotIn(value)}
        if op in (sa_ops.like_op, sa_ops.ilike_op):
            pattern = value.replace('%', '.*').replace('_', '.')
            return {col_name: RegEx(f"(?i){pattern}") if op == sa_ops.ilike_op else RegEx(pattern)}
        if op == sa_ops.is_:
            return {col_name: None} if value is None else {col_name: Eq(value)}
        if op == sa_ops.is_not:
            return {col_name: {"$ne": None}} if value is None else {col_name: {"$ne": value}}
        return None


class _Result:
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
        return None if not self._data else self.one()
    def __iter__(self):
        return iter(self._data)
    def __len__(self):
        return len(self._data)
    def __bool__(self):
        return bool(self._data)


class _ScalarResult:
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

def platform_sessionmaker():
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


async def get_platform_session():
    async with platform_sessionmaker()() as session:
        yield session


async def get_tenant_session(slug: str):
    async with tenant_sessionmaker(slug)() as session:
        yield session


async def get_platform_bundle() -> SimpleNamespace:
    await init_mongo()
    return await ensure_platform_models()


# ---------------------------------------------------------------------------
# Compatibility aliases
# ---------------------------------------------------------------------------

init_store = init_mongo
ensure_indexes = lambda *a, **kw: None
PlatformBase = type('PlatformBase', (), {})
TenantBase = type('TenantBase', (), {})
close_client = lambda: None
