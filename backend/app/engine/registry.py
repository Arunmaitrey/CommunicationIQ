"""Provider resolution, fallback and telemetry.

This is the only place that turns a capability name into a running
implementation. Consumers write::

    result = await providers.invoke(
        Capability.ASR, tenant_id,
        lambda impl: impl.transcribe(audio, hint_text=reference),
    )

and never import a provider package. Which implementation runs, what happens
when it times out, and whether a shadow copy runs alongside are all decided
from ProviderConfig rows — configuration, never a deployment (ENG-18).
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from app.db import Session, or_, platform_sessionmaker, select
from app.engine.contracts import CONTRACT_FOR, Capability, ProviderMeta
from app.engine.contracts.types import ProviderUnavailable
from app.models.platform import ProviderConfig, ProviderCall, ProviderRegistry

log = logging.getLogger(__name__)

T = TypeVar("T")

# Instances are cached per entrypoint: providers are expected to be stateless
# request-wise, and a Tier-1 provider holding a loaded model must not be
# rebuilt per call.
_instances: dict[str, Any] = {}


@dataclass(frozen=True)
class ResolvedProvider:
    row: ProviderRegistry
    impl: Any

    @property
    def meta(self) -> ProviderMeta:
        return ProviderMeta(
            provider_id=self.row.id,
            provider_key=self.row.provider_key,
            version=self.row.version,
            tier=self.row.tier,
        )


@dataclass(frozen=True)
class Resolution:
    capability: Capability
    primary: ResolvedProvider
    fallback: ResolvedProvider | None
    shadow: ResolvedProvider | None
    mode: str
    timeout_ms: int
    canary_percent: int = 0


def _load(row: ProviderRegistry) -> Any:
    """Import and instantiate a provider from its registry entrypoint."""
    if not row.entrypoint:
        raise ProviderUnavailable(
            f"provider {row.capability}/{row.provider_key} has no entrypoint registered"
        )
    if row.entrypoint in _instances:
        return _instances[row.entrypoint]

    module_path, _, attr = row.entrypoint.partition(":")
    if not attr:
        raise ProviderUnavailable(f"malformed entrypoint {row.entrypoint!r} (expected module:Class)")
    try:
        module = importlib.import_module(module_path)
        cls = getattr(module, attr)
    except (ImportError, AttributeError) as exc:
        raise ProviderUnavailable(
            f"cannot load {row.capability}/{row.provider_key} from {row.entrypoint}: {exc}"
        ) from exc

    impl = cls()

    # A provider claiming a capability must actually satisfy its contract.
    # Catching this at load time turns a mid-attempt AttributeError into a
    # startup-shaped failure with a name attached.
    contract = CONTRACT_FOR.get(Capability(row.capability))
    if contract is not None and not isinstance(impl, contract):
        raise ProviderUnavailable(
            f"{row.entrypoint} does not satisfy the {row.capability} contract"
        )

    _instances[row.entrypoint] = impl
    return impl


class Providers:
    """Capability resolution bound to one platform session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def _registry_row(self, provider_id: str | None) -> ProviderRegistry | None:
        if not provider_id:
            return None
        return await self.session.get(ProviderRegistry, provider_id)

    async def resolve(self, capability: Capability, tenant_id: str | None = None) -> Resolution:
        """Find the configuration that applies: tenant override first, then global."""
        # or_ rather than IN: `tenant_id IN ('abc', NULL)` is never true for a
        # NULL row, so an IN-list quietly hid every global default from every
        # tenant-scoped call — every capability read as unconfigured.
        scope = (or_(ProviderConfig.tenant_id == tenant_id,
                     ProviderConfig.tenant_id.is_(None))
                 if tenant_id else ProviderConfig.tenant_id.is_(None))
        stmt = (
            select(ProviderConfig)
            .where(ProviderConfig.capability == capability.value)
            .where(scope)
        )
        configs = (await self.session.execute(stmt)).scalars().all()
        if not configs:
            raise ProviderUnavailable(f"no provider configured for capability {capability.value}")
        # A tenant-specific row wins over the global default.
        config = next((c for c in configs if c.tenant_id == tenant_id and tenant_id), configs[0])

        primary_row = await self._registry_row(config.primary_provider_id)
        if primary_row is None or not primary_row.active:
            raise ProviderUnavailable(
                f"primary provider for {capability.value} is missing or inactive"
            )

        fallback_row = await self._registry_row(config.fallback_provider_id)
        shadow_row = await self._registry_row(config.shadow_provider_id)

        # Loading is where a tier difference actually bites, so it is handled
        # here rather than left to invoke().
        #
        # This used to read `primary=ResolvedProvider(row, _load(row))` inline.
        # _load raises ProviderUnavailable when the entrypoint will not import,
        # which happens *inside* resolve -- before any Resolution exists, so
        # invoke's fallback path could never run. The fallback therefore only
        # ever covered a provider that failed while *running*, never one that
        # was not installed, which is the main reason to configure one.
        #
        # The visible cost was total: on a deployment without torch the Tier-1
        # VAD would not import, the registered Tier-0 energy VAD was never
        # reached, and every response came back with no measures at all --
        # including the timing measures that need neither torch nor a
        # transcript.
        primary_impl = None
        primary_error: ProviderUnavailable | None = None
        try:
            primary_impl = _load(primary_row)
        except ProviderUnavailable as exc:
            primary_error = exc

        fallback = None
        if fallback_row is not None and fallback_row.active:
            try:
                fallback = ResolvedProvider(fallback_row, _load(fallback_row))
            except ProviderUnavailable as exc:
                log.warning("fallback %s/%s will not load: %s",
                            capability.value, fallback_row.provider_key, exc)

        if primary_impl is not None:
            primary = ResolvedProvider(primary_row, primary_impl)
        elif fallback is not None:
            # Promote, and leave the fallback slot empty: it is now the thing
            # doing the work, and pretending it can still fall back to itself
            # would hide a degraded deployment behind a healthy-looking shape.
            log.warning("primary %s/%s will not load (%s) - promoting fallback %s",
                        capability.value, primary_row.provider_key,
                        primary_error, fallback.row.provider_key)
            primary, fallback = fallback, None
        else:
            raise primary_error  # nothing can serve this capability

        # A shadow is diagnostic only and must never decide whether a student
        # gets a score.
        shadow = None
        if shadow_row is not None and shadow_row.active:
            try:
                shadow = ResolvedProvider(shadow_row, _load(shadow_row))
            except ProviderUnavailable as exc:
                log.warning("shadow %s/%s will not load: %s",
                            capability.value, shadow_row.provider_key, exc)

        return Resolution(
            capability=capability,
            primary=primary,
            fallback=fallback,
            shadow=shadow,
            mode=config.mode,
            timeout_ms=config.timeout_ms,
            canary_percent=config.canary_percent,
        )

    async def invoke(
        self,
        capability: Capability,
        tenant_id: str | None,
        call: Callable[[Any], Awaitable[T]],
    ) -> tuple[T, ProviderMeta]:
        """Run ``call`` against the configured provider, with fallback and telemetry.

        Returns the result and the identity of whichever implementation
        actually produced it — the caller stamps that onto the score.
        """
        res = await self.resolve(capability, tenant_id)

        chosen = res.primary
        # Canary: a slice of live traffic goes to the fallback slot so a
        # candidate is exercised for real before promotion (PLAT-10).
        if (res.mode == "canary" and res.fallback
                and random.randint(1, 100) <= res.canary_percent):
            chosen = res.fallback

        try:
            value = await self._timed(capability, chosen, tenant_id, call, res.timeout_ms)
        except Exception as exc:  # noqa: BLE001 — any failure is a fallback trigger
            # _timed already recorded the failure; without a fallback the
            # caller sees the original error unchanged.
            if res.fallback is None:
                raise
            log.warning("provider %s/%s failed (%s) — falling back to %s",
                        capability.value, chosen.row.provider_key, exc,
                        res.fallback.row.provider_key)
            value = await self._timed(capability, res.fallback, tenant_id, call,
                                      res.timeout_ms, used_fallback=True)
            chosen = res.fallback

        # Shadow evaluation runs detached: it must never delay or break the
        # student's result (PLAT-09). Its output is recorded, never shown.
        if res.mode == "shadow" and res.shadow is not None:
            asyncio.create_task(
                self._shadow(capability, res.shadow, tenant_id, call, res.timeout_ms)
            )

        return value, chosen.meta

    async def _timed(self, capability: Capability, provider: ResolvedProvider,
                     tenant_id: str | None, call: Callable[[Any], Awaitable[T]],
                     timeout_ms: int, used_fallback: bool = False) -> T:
        started = time.perf_counter()
        try:
            value = await asyncio.wait_for(call(provider.impl), timeout=timeout_ms / 1000)
        except Exception as exc:  # noqa: BLE001 — recorded then re-raised
            elapsed = int((time.perf_counter() - started) * 1000)
            await self._record(capability, provider, tenant_id, elapsed,
                               ok=False, error=str(exc)[:300], used_fallback=used_fallback)
            raise
        elapsed = int((time.perf_counter() - started) * 1000)
        await self._record(capability, provider, tenant_id, elapsed,
                           ok=True, used_fallback=used_fallback)
        return value

    async def _shadow(self, capability: Capability, provider: ResolvedProvider,
                      tenant_id: str | None, call: Callable[[Any], Awaitable[Any]],
                      timeout_ms: int) -> None:
        try:
            await self._timed(capability, provider, tenant_id, call, timeout_ms)
        except Exception as exc:  # noqa: BLE001
            log.info("shadow provider %s failed: %s", provider.row.provider_key, exc)

    async def _record(self, capability: Capability, provider: ResolvedProvider,
                      tenant_id: str | None, latency_ms: int, *, ok: bool,
                      error: str = "", used_fallback: bool = False) -> None:
        """Write one telemetry row in its own transaction (PLAT-13).

        Separate session on purpose: committing the caller's session here
        would publish half-finished work, and rolling back with it would lose
        exactly the records that explain a failure.
        """
        async with platform_sessionmaker()() as session:
            session.add(ProviderCall(
                capability=capability.value,
                provider_id=provider.row.id,
                provider_version=provider.row.version,
                tenant_id=tenant_id,
                latency_ms=latency_ms,
                ok=ok,
                error=error,
                used_fallback=used_fallback,
            ))
            await session.commit()


def clear_provider_cache() -> None:
    """Drop cached instances — used by tests and after a registry change."""
    _instances.clear()
