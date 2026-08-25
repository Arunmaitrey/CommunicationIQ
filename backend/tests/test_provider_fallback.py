"""A provider that will not import must fall back, not take the score with it.

The bug these cover was invisible on any developer machine, because every
provider imports there. It only appeared on a deployment missing the Tier-1
speech packages -- which is exactly where the fallback was supposed to earn
its keep.

``Providers.resolve`` built the Resolution with ``_load(primary_row)`` inline.
``_load`` raises ProviderUnavailable when the entrypoint will not import, so
the failure happened *inside* resolve, before any Resolution existed, and
``invoke``'s fallback path could never be reached. The configured fallback
therefore only ever covered a provider that broke while *running* -- never one
that was not installed.

Downstream, the pipeline caught that ProviderUnavailable from the VAD call and
returned ``skipped=True``, which claims the student did not answer. A skipped
response carries no dimensions and no explanation, so eight good recordings
came back as an empty result with nothing to say about why.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import platform_sessionmaker
from app.engine.contracts.types import Capability
from app.engine.registry import ProviderUnavailable, Providers, _instances
from app.models.platform import ProviderConfig, ProviderRegistry, Tenant

pytestmark = pytest.mark.asyncio

# A real, importable Tier-0 provider and an entrypoint that cannot exist.
GOOD = "app.engine.providers.tier0.vad:EnergyVAD"
MISSING_MODULE = "app.engine.providers.tier1.definitely_not_here:Nope"
MISSING_CLASS = "app.engine.providers.tier0.vad:NoSuchClass"


async def _configure(session, *, primary: str, fallback: str | None):
    """A VAD config pointing at the given entrypoints, cleaned up by the caller."""
    # provider_configs.tenant_id is a real foreign key, so the override has to
    # hang off a tenant that exists. Any of them will do -- the rows never
    # outlive the transaction.
    tenant_id = (await session.execute(select(Tenant.id))).scalars().first()
    assert tenant_id, "seed the demo estate before running these"

    rows = []
    primary_row = ProviderRegistry(
        capability="vad", provider_key="test_primary", name="test primary",
        tier=1, version="0.0.0", entrypoint=primary, active=True)
    rows.append(primary_row)

    fallback_row = None
    if fallback is not None:
        fallback_row = ProviderRegistry(
            capability="vad", provider_key="test_fallback", name="test fallback",
            tier=0, version="0.0.0", entrypoint=fallback, active=True)
        rows.append(fallback_row)

    for row in rows:
        session.add(row)
    await session.flush()

    config = ProviderConfig(
        capability="vad", tenant_id=tenant_id,
        primary_provider_id=primary_row.id,
        fallback_provider_id=fallback_row.id if fallback_row else None,
        mode="primary", timeout_ms=5_000, canary_percent=0)
    session.add(config)
    await session.flush()
    return config, rows, tenant_id


async def _resolve_with(primary: str, fallback: str | None):
    """Resolve a throwaway VAD config, then roll it back."""
    _instances.clear()   # never let a cached import mask a load failure
    async with platform_sessionmaker()() as session:
        _config, _rows, tenant_id = await _configure(
            session, primary=primary, fallback=fallback)
        try:
            return await Providers(session).resolve(Capability.VAD, tenant_id)
        finally:
            await session.rollback()


async def test_a_primary_that_will_not_import_promotes_the_fallback():
    """The regression: a missing package must not defeat a working fallback."""
    resolution = await _resolve_with(MISSING_MODULE, GOOD)

    assert resolution.primary.row.provider_key == "test_fallback"
    assert resolution.primary.impl is not None
    # The slot is emptied rather than left pointing at itself: a degraded
    # deployment must not present the same shape as a healthy one.
    assert resolution.fallback is None


async def test_a_missing_class_is_treated_the_same_as_a_missing_module():
    """An entrypoint whose module imports but whose class is gone."""
    resolution = await _resolve_with(MISSING_CLASS, GOOD)
    assert resolution.primary.row.provider_key == "test_fallback"


async def test_a_working_primary_is_never_displaced():
    """The healthy path is untouched -- this must not silently prefer Tier 0."""
    resolution = await _resolve_with(GOOD, GOOD)
    assert resolution.primary.row.provider_key == "test_primary"
    assert resolution.fallback is not None


async def test_no_usable_provider_still_raises():
    """Degrading gracefully is not the same as pretending it worked."""
    with pytest.raises(ProviderUnavailable):
        await _resolve_with(MISSING_MODULE, MISSING_MODULE)

    with pytest.raises(ProviderUnavailable):
        await _resolve_with(MISSING_MODULE, None)


async def test_a_broken_fallback_does_not_break_a_working_primary():
    """A fallback that will not load is a warning, not an outage."""
    resolution = await _resolve_with(GOOD, MISSING_MODULE)
    assert resolution.primary.row.provider_key == "test_primary"
    assert resolution.fallback is None


# -- Telling the candidate before, not after --------------------------------

async def test_capability_is_public_and_honest_about_a_degraded_server(client):
    """A student must be able to learn what this server can measure.

    Unauthenticated on purpose: it describes the deployment, not the person
    asking. The note is empty on a full install so the UI has nothing to show,
    and populated only when something really is missing -- a permanent banner
    that is usually wrong would be ignored by the time it mattered.
    """
    import app.main as main

    body = (await client.get("/api/v1/meta/capability")).json()
    assert body["tier"] == 1 and body["full_scoring"] is True
    assert body["note"] == ""
    assert "pronunciation" in body["measures"]

    original = main._engine_tier
    main._engine_tier = lambda: {"tier": 0, "speech_models": "unavailable",
                                 "missing": ["torch"]}
    try:
        degraded = (await client.get("/api/v1/meta/capability")).json()
    finally:
        main._engine_tier = original

    assert degraded["full_scoring"] is False
    assert degraded["measures"] == ["fluency", "latency"]
    assert degraded["note"], "a degraded server must say so"
    # No promise the product cannot keep: audio does not survive a restart on
    # a deployment without a disk.
    assert "saved" not in degraded["note"].lower()


async def test_no_unscored_reason_promises_the_recording_survives():
    """The free plan has no disk, so 'we kept it, we'll score it later' is false."""
    from app.engine.pipeline import NO_TRANSCRIPT, NO_VAD
    from app.routers.attempts import _unscored_reasons
    from types import SimpleNamespace

    rows = [SimpleNamespace(task_type="read_aloud", skipped=False)]
    reasons = list(_unscored_reasons(rows, {}).values()) + [NO_TRANSCRIPT, NO_VAD]
    for reason in reasons:
        assert "saved" not in reason.lower(), reason
        assert "filled in once" not in reason.lower(), reason


async def test_healthz_reports_which_commit_is_running(client):
    """Verifying a deployment should not require archaeology.

    Working out which build was live in production meant probing for an
    endpoint that only exists in a later commit and diffing a user-visible
    string against the source. That works once; it gets harder every release.
    """
    body = (await client.get("/healthz")).json()
    assert body["status"] == "ok"
    assert body["commit"], "healthz must say what it is running"
    # Either a real short SHA or an honest "unknown" -- never a guess.
    assert body["commit"] == "unknown" or (
        len(body["commit"]) == 12 and all(c in "0123456789abcdef"
                                          for c in body["commit"]))
