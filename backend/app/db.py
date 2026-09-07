"""MongoDB data layer — Beanie ODM over Motor, single shared database.

Everything — control-plane documents (``app.models.platform``) and
per-institution documents (``app.models.tenant``) alike — lives in one
database, ``CommunicationIQ`` (taken from the URI). Registered once at
startup. Tenant isolation is by the ``tenant_id`` field on each document,
applied at query time by callers (see ``app.deps``), not by a database
boundary — there used to be a separate ``tenant_<slug>`` database per
institution; that's gone, because the real data was never actually stored
that way (confirmed against the live cluster), only the code assumed it.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import Document, init_beanie

from app.config import settings


client = AsyncIOMotorClient(
    settings.mongo_uri, uuidRepresentation="standard",
    serverSelectionTimeoutMS=15000,
    # This Python build's default SSL context ships with no CA certs loaded
    # (a known python.org-framework-build gap on macOS), which makes Atlas's
    # TLS handshake fail with "unable to get local issuer certificate" even
    # though the connection itself is fine. Pointing at certifi's bundle
    # sidesteps the system trust store entirely.
    tlsCAFile=certifi.where())

CONTROL_DB_NAME = settings.control_db_name


def control_db() -> AsyncIOMotorDatabase:
    return client[CONTROL_DB_NAME]


# ---------------------------------------------------------------------------
# Beanie init — one database, one registration, at startup.
# ---------------------------------------------------------------------------

_client_inited = False
_tenant_bundle: SimpleNamespace | None = None


async def init_mongo() -> None:
    """Ping and register every document model against the one database.

    Idempotent. Runs once at process startup; every request after that reads
    the already-registered classes rather than re-initialising anything.
    """
    global _client_inited
    if _client_inited:
        return
    await client.admin.command("ping")
    from app.models.platform import CONTROL_DOCUMENTS
    from app.models.tenant import TENANT_DOCUMENTS, SHARED_DOCUMENTS
    await init_beanie(
        database=control_db(),
        document_models=list(CONTROL_DOCUMENTS) + list(TENANT_DOCUMENTS) + list(SHARED_DOCUMENTS))
    _client_inited = True
    _stamp_platform_owners()
    _stamp_tenant_owners()


# ---------------------------------------------------------------------------
# Tenant document bundle
#
# There is no more per-tenant database binding to create — every tenant's
# documents live in the same collections, distinguished by tenant_id. This
# just hands back the plain, already-registered Document classes, kept as a
# SimpleNamespace so every existing `models.User`/`models.QuizItem` call site
# across the routers keeps working unchanged.
# ---------------------------------------------------------------------------


async def ensure_tenant_models(slug: str) -> SimpleNamespace:
    """Return the tenant + shared-content Document classes.

    ``slug`` is accepted (every caller still passes one) but no longer
    changes what comes back — there is one set of classes now, not one per
    institution. Callers still must filter their own queries by
    ``tenant_id``; that boundary moved from the database to the query.
    """
    await init_mongo()
    return _get_tenant_bundle()


def _get_tenant_bundle() -> SimpleNamespace:
    global _tenant_bundle
    if _tenant_bundle is None:
        from app.models.tenant import TENANT_DOCUMENTS, SHARED_DOCUMENTS
        classes = list(TENANT_DOCUMENTS) + list(SHARED_DOCUMENTS)
        _tenant_bundle = SimpleNamespace(**{cls.__name__: cls for cls in classes})
    return _tenant_bundle


def get_tenant_models(slug: str) -> SimpleNamespace:
    """Synchronous accessor — only valid after ``ensure_tenant_models`` ran
    at least once for any tenant (it always has, by request time)."""
    return _get_tenant_bundle()


# ---------------------------------------------------------------------------
# Platform models accessor
# ---------------------------------------------------------------------------

async def ensure_platform_models() -> SimpleNamespace:
    from app.models.platform import CONTROL_DOCUMENTS
    return SimpleNamespace(**{cls.__name__: cls for cls in CONTROL_DOCUMENTS})


async def ensure_shared_models() -> SimpleNamespace:
    """The shared-content classes only (QuizItem, ReadingPassage, ...), for
    callers that have no tenant slug to hand ``ensure_tenant_models`` — the
    question-bank admin routes, which write shared content directly rather
    than through a tenant-scoped session."""
    from app.models.tenant import SHARED_DOCUMENTS
    return SimpleNamespace(**{cls.__name__: cls for cls in SHARED_DOCUMENTS})


# ---------------------------------------------------------------------------
# Query-builder shim — select()/delete()/update()/func/or_/selectinload for
# service modules that still write session.execute(select(Model)...).
#
# The previous version of this bridge built *real* sqlalchemy.Select/Delete
# statements and translated them after the fact. That never worked:
# sqlalchemy.select() rejects a Beanie Document at construction time (it is
# not an ORM-mapped class), so every select(SomeDocument) in the app raised
# ArgumentError before Session.execute ever ran — including inside
# Providers.resolve(), which every scored dimension goes through. This shim
# never touches SQLAlchemy; it builds Beanie queries directly.
# ---------------------------------------------------------------------------

from beanie.odm.fields import ExpressionField as _EF
from beanie.operators import Eq as _Eq, NE as _NE, In as _In, NotIn as _NotIn, Or as _Or

or_ = _Or


def _ef_in_(self, values):
    return _In(self, list(values))


def _ef_not_in(self, values):
    return _NotIn(self, list(values))


def _ef_is_(self, value):
    return _Eq(self, value)


def _ef_is_not(self, value):
    return _NE(self, value)


def _ef_desc(self):
    # Beanie's own -field / +field sort-direction operators (__neg__/__pos__)
    # already exist; .desc()/.asc() just spell them the way this codebase's
    # call sites do.
    return self.__neg__()


def _ef_asc(self):
    return self.__pos__()


_EF.in_ = _ef_in_
_EF.not_in = _ef_not_in
_EF.is_ = _ef_is_
_EF.is_not = _ef_is_not
_EF.desc = _ef_desc
_EF.asc = _ef_asc


_platform_owners_stamped = False


def _stamp_platform_owners() -> None:
    """``Model.field`` is only ever the field's *name* (Beanie's
    ExpressionField is a plain str subclass) — it carries no reference back
    to ``Model``. A whole-row ``select(Model)`` doesn't need one, but a
    partial ``select(Model.field)`` does, to know what to query.

    Unlike the tenant side, Beanie only sets these class attributes once
    ``init_beanie`` has actually run for a class — so this runs from
    ``init_mongo``, after registration, not at import time.
    """
    global _platform_owners_stamped
    if _platform_owners_stamped:
        return
    from app.models.platform import CONTROL_DOCUMENTS
    for model in CONTROL_DOCUMENTS:
        for name in model.model_fields:
            field = getattr(model, name, None)
            if isinstance(field, _EF):
                field.owner_model = model
    _platform_owners_stamped = True


_tenant_owners_stamped = False


def _stamp_tenant_owners() -> None:
    """Same idea as ``_stamp_platform_owners``, for the tenant + shared-content
    side — now a single `init_beanie` call like the platform side, so this
    also only needs to run once per process."""
    global _tenant_owners_stamped
    if _tenant_owners_stamped:
        return
    from app.models.tenant import TENANT_DOCUMENTS, SHARED_DOCUMENTS
    for model in list(TENANT_DOCUMENTS) + list(SHARED_DOCUMENTS):
        for name in model.model_fields:
            field = getattr(model, name, None)
            if isinstance(field, _EF):
                field.owner_model = model
    _tenant_owners_stamped = True


class _Count:
    """Marker produced by func.count(); resolved via .select_from(Model)."""


class _Func:
    @staticmethod
    def count(*_a) -> _Count:
        return _Count()


func = _Func()


def selectinload(*_a, **_kw):
    """Eager-load hint from the SQLAlchemy relationship world. Meaningless
    for Beanie: embedded fields already ride along on the document, and
    nothing here models a lazy-loaded relationship. .options() drops it."""
    return None


class _Stmt:
    SELECT, DELETE, UPDATE = "select", "delete", "update"

    def __init__(self, kind: str, entities: tuple):
        self.kind = kind
        self.entities = entities
        self.conditions: list = []
        self.order: list = []
        self.limit_val: int | None = None
        self.offset_val: int | None = None
        self.values_: dict = {}
        self.from_model = None

    def where(self, *conditions) -> _Stmt:
        self.conditions.extend(conditions)
        return self

    def order_by(self, *keys) -> _Stmt:
        self.order.extend(keys)
        return self

    def limit(self, n) -> _Stmt:
        self.limit_val = n
        return self

    def offset(self, n) -> _Stmt:
        self.offset_val = n
        return self

    def values(self, **kwargs) -> _Stmt:
        self.values_.update(kwargs)
        return self

    def select_from(self, model) -> _Stmt:
        self.from_model = model
        return self

    def options(self, *_a, **_kw) -> _Stmt:
        return self


def select(*entities) -> _Stmt:
    return _Stmt(_Stmt.SELECT, entities)


def delete(entity) -> _Stmt:
    return _Stmt(_Stmt.DELETE, (entity,))


def update(entity) -> _Stmt:
    return _Stmt(_Stmt.UPDATE, (entity,))


# ---------------------------------------------------------------------------
# Session bridge — for service modules that still use
# session.execute(select(...)) / session.add(obj) / session.commit()
# ---------------------------------------------------------------------------

class Session:
    """Beanie-backed session that speaks the SQLAlchemy async-session API."""

    def __init__(self, models: SimpleNamespace):
        self._models = models
        self._new: list = []
        # SQLAlchemy's session auto-tracks anything it fetched: mutate an
        # object session.get() handed you, call commit(), and it persists —
        # no session.add() needed, because the session already knows about
        # it. This codebase was written against exactly that idiom (see
        # attempts.py's env_check: fetch, mutate attempt.env_check in place,
        # commit — never add()). Beanie has no equivalent auto-tracking, so
        # get() below records what it hands out, and flush() saves it,
        # otherwise every such mutation is silently discarded.
        self._tracked: list = []

    async def __aenter__(self) -> Session:
        return self

    async def __aexit__(self, *a) -> None:
        pass

    def add(self, obj: Any) -> None:
        self._new.append(obj)

    def add_all(self, objs: list) -> None:
        self._new.extend(objs)

    def track(self, obj: Any) -> None:
        """Mark an already-fetched row as dirty-tracked.

        ``get()`` does this automatically; a row that came back from
        ``execute(select(...))`` does not (see ``_run`` -- it is a plain
        ``to_list()``, no tracking). A caller that mutates such a row and
        expects the next ``commit()`` to save it needs this, or the change
        is silently lost -- the same failure mode ``get()``'s tracking
        exists to prevent, just for a row fetched the other way.
        """
        self._tracked.append(obj)

    async def flush(self) -> None:
        for obj in self._new:
            if not getattr(obj, 'id', None):
                import uuid
                obj.id = str(uuid.uuid4())
            await obj.insert()
        self._new.clear()
        for obj in self._tracked:
            await obj.save()
        self._tracked.clear()

    async def commit(self) -> None:
        await self.flush()

    async def rollback(self) -> None:
        self._new.clear()
        self._tracked.clear()

    async def get(self, model: type, pk: Any):
        obj = await self._resolve(model).get(pk)
        if obj is not None:
            self._tracked.append(obj)
        return obj

    async def refresh(self, obj: Any) -> None:
        """Reload `obj`'s fields in place from the database, mirroring
        SQLAlchemy's session.refresh() -- the caller keeps the same object
        identity, but its attributes now match what another write (e.g. a
        different session.get() of the same row, mutated and saved
        elsewhere in this same request) actually persisted.
        """
        fresh = await self._resolve(type(obj)).get(obj.id)
        if fresh is not None:
            for field in type(fresh).model_fields:
                setattr(obj, field, getattr(fresh, field))

    async def execute(self, stmt: _Stmt):
        if stmt.kind == _Stmt.DELETE:
            return await self._exec_delete(stmt)
        if stmt.kind == _Stmt.UPDATE:
            return await self._exec_update(stmt)
        return await self._exec_select(stmt)

    async def _exec_delete(self, stmt: _Stmt) -> None:
        model = self._resolve(stmt.entities[0])
        await model.find(*stmt.conditions).delete()

    async def _exec_update(self, stmt: _Stmt) -> None:
        model = self._resolve(stmt.entities[0])
        docs = await model.find(*stmt.conditions).to_list()
        for doc in docs:
            for k, v in stmt.values_.items():
                setattr(doc, k, v)
            await doc.save()

    async def _exec_select(self, stmt: _Stmt):
        entities = stmt.entities

        if len(entities) == 1 and isinstance(entities[0], _Count):
            model = self._resolve(stmt.from_model)
            if model is None:
                raise TypeError("func.count() needs .select_from(Model)")
            n = await model.find(*stmt.conditions).count()
            return _ScalarResult(n)

        first = entities[0]
        if isinstance(first, type):
            model = self._resolve(first)
            docs = await self._run(model, stmt)
            return _Result(docs)

        owner = getattr(first, 'owner_model', None)
        if owner is None:
            raise TypeError(
                f"select({first!r}) — its owning model was never stamped by "
                "_stamp_owners(); is it a field on a model in CONTROL_DOCUMENTS "
                "or TENANT_DOCUMENTS?")
        model = self._resolve(owner)
        docs = await self._run(model, stmt)
        if len(entities) == 1:
            return _Result([getattr(d, str(first)) for d in docs])
        return _Result([tuple(getattr(d, str(f)) for f in entities) for d in docs])

    async def _run(self, model, stmt: _Stmt) -> list:
        query = model.find(*stmt.conditions)
        if stmt.order:
            query = query.sort(*stmt.order)
        if stmt.limit_val is not None:
            query = query.limit(stmt.limit_val)
        if stmt.offset_val is not None:
            query = query.skip(stmt.offset_val)
        return await query.to_list()

    def _resolve(self, model):
        """The class a caller imports (``from app.models.tenant import
        Attempt``) is never itself bound to a database — each tenant gets its
        own subclass, built and registered by ``ensure_tenant_models``. This
        finds that bound subclass; for platform models, where the base class
        *is* the bound one, it is its own answer."""
        if model is None:
            return None
        return getattr(self._models, model.__name__, model)


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
    def scalar_one(self):
        return self.one()
    def scalar_one_or_none(self):
        return self.one_or_none()
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
