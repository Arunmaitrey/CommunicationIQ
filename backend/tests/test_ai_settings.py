"""Operator-configurable AI narration settings, end to end.

The document is the truth, the whitelist is the boundary, and a secret that
went in never comes back out whole.
"""
from __future__ import annotations

import pytest
from sqlalchemy import delete

from app import ai_settings
from app.config import Settings, settings
from app.db import platform_sessionmaker
from app.models.platform import PlatformSetting
from app.narration.providers import NvidiaNarrator, get_narrator
from tests.conftest import auth, login

pytestmark = pytest.mark.asyncio


async def _wipe():
    async with platform_sessionmaker()() as s:
        await s.execute(delete(PlatformSetting)
                        .where(PlatformSetting.key == ai_settings.KEY))
        await s.commit()
    # And put the live settings back to environment defaults.
    defaults = Settings()
    for name in ai_settings.FIELDS:
        setattr(settings, name, getattr(defaults, name))


@pytest.fixture(autouse=True)
async def clean():
    await ai_settings.ensure_table()
    await _wipe()
    yield
    await _wipe()


async def test_save_applies_to_live_settings_and_selects_the_provider():
    await ai_settings.save({"narration_provider": "nvidia",
                            "nvidia_model": "meta/llama-3.1-70b-instruct",
                            "nvidia_api_key": "nvapi-test-1234"})
    assert settings.narration_provider == "nvidia"
    assert settings.nvidia_model == "meta/llama-3.1-70b-instruct"
    narrator = get_narrator()
    assert isinstance(narrator, NvidiaNarrator)
    assert narrator.model_version == "meta/llama-3.1-70b-instruct"


async def test_secrets_are_masked_and_persist_across_a_reload():
    await ai_settings.save({"nvidia_api_key": "nvapi-secret-abcd"})
    view = ai_settings.masked_view(await ai_settings.load_and_apply())
    assert view["nvidia_api_key"] == {"set": True, "last4": "abcd"}
    assert "nvapi-secret" not in str(view)
    # A fresh load (a new process starting) re-applies the stored key.
    settings.nvidia_api_key = ""
    await ai_settings.load_and_apply()
    assert settings.nvidia_api_key == "nvapi-secret-abcd"


async def test_null_leaves_and_empty_clears_back_to_default():
    await ai_settings.save({"nvidia_model": "custom/model"})
    await ai_settings.save({"nvidia_model": None})          # leave as is
    assert settings.nvidia_model == "custom/model"
    await ai_settings.save({"nvidia_model": ""})            # clear
    assert settings.nvidia_model == Settings().nvidia_model


async def test_unknown_fields_and_providers_are_refused():
    document = await ai_settings.save({"database_url": "postgres://evil",
                                       "nvidia_model": "ok/model"})
    assert "database_url" not in document
    with pytest.raises(ValueError):
        await ai_settings.save({"narration_provider": "skynet"})


async def test_console_endpoints_gate_and_mask(client):
    su = await login(client, "platform")
    r = await client.get("/api/v1/platform/narration/settings", headers=auth(su))
    assert r.status_code == 200
    body = r.json()
    assert body["providers"] == list(ai_settings.PROVIDERS)
    assert body["nvidia_api_key"] == {"set": False, "last4": ""}

    r = await client.put("/api/v1/platform/narration/settings", headers=auth(su),
                         json={"narration_provider": "nvidia",
                               "nvidia_api_key": "nvapi-live-9876"})
    assert r.status_code == 200
    assert r.json()["nvidia_api_key"] == {"set": True, "last4": "9876"}
    assert r.json()["narration_provider"] == "nvidia"

    # A student token gets nowhere near it.
    student = await login(client, "student")
    r = await client.get("/api/v1/platform/narration/settings",
                         headers=auth(student))
    assert r.status_code == 403


async def test_nvidia_without_a_key_is_a_terminal_config_error():
    from app.narration.contract import NarratorError
    settings.nvidia_api_key = ""
    narrator = NvidiaNarrator()
    with pytest.raises(NarratorError) as err:
        await narrator.narrate(None, timeout_s=1.0)  # type: ignore[arg-type]
    assert err.value.category == "config"
