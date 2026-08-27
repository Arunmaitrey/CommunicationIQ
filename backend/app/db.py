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
    from app.sqlbridge import register_model
    for doc in CONTROL_DOCUMENTS:
        register_model(doc)
    _client_inited = True


# ---------------------------------------------------------------------------
# Tenant document bundles (lazy per-slug init)
# ---------------------------------------------------------------------------

_tenant_bundles: dict[str, SimpleNamespace] = {}
_tenant_locks: dict[str, asyncio.Lock] = {}


def _make_tenant_subclasses(slug: str, base_docs: list) -> list:
    """Create per-tenant Document subclasses."""
    # Beanie fields are descriptors that may not work on type()-created
    # subclasses. Add a __getattr__ fallback that reads from the internal
    # state dict so that access like user.year_of_study returns the actual
    # value instead of an ExpressionField descriptor object.
    _orig_getattr = getattr(type(base_docs[0]), '__getattr__', None) if base_docs else None

    def _safe_getattr(self, item):
        # 1. Try normal attribute resolution first
        try:
            val = object.__getattribute__(self, item)
        except AttributeError:
            val = None
        # 2. If it looks like a Beanie ExpressionField or descriptor, fall back
        #    to Pydantic's stored field values
        if val is not None and type(val).__name__ in ('ExpressionField', 'IndexField'):
            # Pydantic v2 stores field values in __dict__
            d = object.__getattribute__(self, '__dict__')
            if item in d:
                return d[item]
        return val

    subclasses = []
    for cls in base_docs:
        orig_name = cls.__name__
        ns = {
            "__qualname__": f"{orig_name}_{slug}",
            "__module__": cls.__module__,
            "__getattr__": _safe_getattr,
        }
        sub = type(orig_name, (cls,), ns)
        sub.Settings = type("Settings", (), {"name": cls.Settings.name})
        subclasses.append(sub)
    return subclasses


async def ensure_tenant_models(slug: str) -> SimpleNamespace:
    """Return a namespace of Beanie Document classes bound to ``tenant_<slug>``."""
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
        from app.sqlbridge import register_model
        for doc in tenant_docs:
            register_model(doc)
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
        self.models = models  # Public accessor for tenant-bound Beanie classes
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

    async def refresh(self, obj: Any) -> None:
        """Re-fetch an object from the database."""
        if hasattr(obj, 'id') and hasattr(obj, '__class__') and hasattr(obj.__class__, 'get'):
            refreshed = await obj.__class__.get(obj.id)
            if refreshed is not None:
                for key in list(vars(refreshed).keys()):
                    if not key.startswith('_'):
                        setattr(obj, key, getattr(refreshed, key))

    async def get(self, model: type, pk: Any):
        return await model.get(pk)

    async def execute(self, stmt):
        # The app.sqlbridge builders are the supported path: real SQLAlchemy
        # cannot even construct select(Model) for a Beanie document class, so
        # anything that reaches here built by sqlalchemy is legacy.
        from app.sqlbridge import Delete as BridgeDelete, Select as BridgeSelect, \
            Update as BridgeUpdate

        if isinstance(stmt, BridgeSelect):
            return await self._exec_bridge_select(stmt)
        if isinstance(stmt, BridgeDelete):
            return await self._exec_bridge_delete(stmt)
        if isinstance(stmt, BridgeUpdate):
            return await self._exec_bridge_update(stmt)

        from sqlalchemy.sql.selectable import Select
        from sqlalchemy.sql.dml import Delete, Update

        if isinstance(stmt, Delete):
            return await self._exec_delete(stmt)
        if isinstance(stmt, Update):
            return await self._exec_update(stmt)
        if isinstance(stmt, Select):
            return await self._exec_select(stmt)
        raise TypeError(f"Unsupported statement type: {type(stmt)}")

    async def _exec_bridge_select(self, stmt):
        from app.sqlbridge import normalize_conditions, owner_of

        model = stmt.entity or getattr(stmt, "_from_model", None)
        if model is None and stmt.columns:
            # Column-only select: the ExpressionField instance knows its class.
            model = owner_of(stmt.columns[0])
        if stmt.is_count:
            target = stmt._from_model or stmt.entity
            if target is None:
                raise TypeError("count() needs select_from(Model) or an entity")
            filters = normalize_conditions(stmt._where)
            total = await (target.find(*filters).count() if filters
                           else target.find().count())
            return _ScalarResult(total)

        if model is None:
            raise TypeError("select() needs a document class")

        query = model.find(*normalize_conditions(stmt._where))
        if stmt._sort:
            query = query.sort(
                *[("_id" if s.field == "id" else s.field, s.direction)
                  for s in stmt._sort])
        if stmt._limit is not None:
            query = query.limit(stmt._limit)
        if stmt._offset is not None:
            query = query.skip(stmt._offset)
        docs = await query.to_list()

        if not stmt.columns:
            return _Result(docs)
        names = [str(c) for c in stmt.columns]
        rows = [_Row(names, tuple(getattr(d, n, None) for n in names))
                for d in docs]
        return _Result(rows, unwrap_single=len(names) == 1)

    async def _exec_bridge_delete(self, stmt):
        from app.sqlbridge import normalize_conditions

        filters = normalize_conditions(stmt._where)
        if filters:
            await stmt.model.find(*filters).delete()
        else:
            await stmt.model.find_all().delete()
        return None

    async def _exec_bridge_update(self, stmt):
        from app.sqlbridge import normalize_conditions

        filters = normalize_conditions(stmt._where)
        docs = await stmt.model.find(*filters).to_list() if filters \
            else await stmt.model.find_all().to_list()
        for doc in docs:
            for k, v in stmt.values_map.items():
                setattr(doc, "_id" if k == "id" else k, v)
            await doc.save()
        return len(docs)

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
                filter_args = self._extract_where(stmt.whereclause)
                if filter_args:
                    count = await model.find(*filter_args).count()
                else:
                    count = await model.find().count()
                return _ScalarResult(count)

        if select_cols:
            first = select_cols[0]
            if hasattr(first, 'class_'):
                model = self._resolve(first.class_) or first.class_
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
                # Direct Beanie Document class
                if hasattr(fc, 'Settings') and hasattr(fc.Settings, 'name'):
                    m = self._resolve(fc)
                    if m:
                        return m
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
        # Direct Beanie Document class passed (e.g. select_from(Attempt))
        if hasattr(table_or_model, 'Settings') and hasattr(table_or_model.Settings, 'name'):
            ns = self._models
            for attr in dir(ns):
                obj = getattr(ns, attr)
                if obj is table_or_model:
                    return obj
            # Fall back to matching by Settings.name
            table_name = table_or_model.Settings.name
            for attr in dir(ns):
                obj = getattr(ns, attr)
                if hasattr(obj, 'Settings') and hasattr(obj.Settings, 'name'):
                    if obj.Settings.name == table_name:
                        return obj
            return None

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
        # Beanie stores the primary key as '_id', not 'id'
        if col_name == 'id':
            col_name = '_id'
        value = right.value if hasattr(right, 'value') else right

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


class _Row(tuple):
    """A projected row: unpacks like a tuple, reads like an object."""

    def __new__(cls, names: list[str], values: tuple):
        self = super().__new__(cls, values)
        object.__setattr__(self, "_names", names)
        return self

    def __getattr__(self, name: str):
        try:
            return self[self._names.index(name)]
        except (ValueError, IndexError):
            raise AttributeError(name)


class _Result:
    def __init__(self, data: list, unwrap_single: bool = False):
        self._data = data
        # True for projected column selects, where each row is a tuple and
        # scalars() must hand back the first element of each.
        self._unwrap = unwrap_single
    def scalars(self):
        if self._unwrap:
            return _Result([r[0] if isinstance(r, tuple) else r
                            for r in self._data])
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
    def scalar_one(self):
        row = self.one()
        return row[0] if isinstance(row, tuple) else row
    def scalar_one_or_none(self):
        row = self.first()
        if row is None:
            return None
        return row[0] if isinstance(row, tuple) else row
    def scalar(self):
        row = self.first()
        if row is None:
            return None
        return row[0] if isinstance(row, tuple) else row
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
    def scalar_one(self):
        return self._value
    def scalar_one_or_none(self):
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
