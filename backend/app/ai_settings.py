"""Admin-configurable AI narration settings.

The environment supplies defaults (app.config.Settings); a single
``platform_settings`` row keyed ``ai_narration`` overrides them, and the
platform console edits that row. Applying an override mutates the live
``settings`` object — the same object every provider reads and every test
monkeypatches — so a change takes effect without a restart in this process.
(Other worker processes pick it up on their next start; the row is the truth.)

Secrets never leave the API once stored: readers get ``{set, last4}``.
Writers send a real value to change a key, ``null`` to leave it unchanged,
and ``""`` to clear it.
"""
from __future__ import annotations

from typing import Any

from app.config import settings
from app.models.platform import PlatformSetting

KEY = "ai_narration"

FIELDS: dict[str, type] = {
    "narration_enabled": bool,
    "narration_provider": str,
    "narration_model": str,
    "anthropic_api_key": str,
    "anthropic_base_url": str,
    "nvidia_base_url": str,
    "nvidia_model": str,
    "nvidia_api_key": str,
    "oss_base_url": str,
    "oss_model": str,
    "oss_api_key": str,
    "oss_temperature": float,
}

SECRET_FIELDS = frozenset({"anthropic_api_key", "nvidia_api_key", "oss_api_key"})

PROVIDERS = ("anthropic", "nvidia", "opensource", "echo")


def _coerce(name: str, value: Any) -> Any:
    kind = FIELDS[name]
    if kind is bool:
        return bool(value)
    if kind is float:
        return float(value)
    return str(value)


def apply_overrides(overrides: dict[str, Any]) -> None:
    for name, value in overrides.items():
        if name in FIELDS and value is not None:
            setattr(settings, name, _coerce(name, value))


async def load_and_apply() -> dict[str, Any]:
    row = await PlatformSetting.find_one(PlatformSetting.key == KEY)
    overrides = dict(row.value or {}) if row else {}
    apply_overrides(overrides)
    return overrides


async def save(changes: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    clear: list[str] = []
    for name, value in changes.items():
        if name not in FIELDS or value is None:
            continue
        if value == "":
            clear.append(name)
        else:
            clean[name] = _coerce(name, value)

    if "narration_provider" in clean and clean["narration_provider"] not in PROVIDERS:
        raise ValueError(f"unknown provider {clean['narration_provider']!r}")

    row = await PlatformSetting.find_one(PlatformSetting.key == KEY)
    document = dict(row.value or {}) if row else {}
    document.update(clean)
    for name in clear:
        document.pop(name, None)

    if row is None:
        await PlatformSetting.insert(PlatformSetting(key=KEY, value=document))
    else:
        row.value = document
        await row.save()

    from app.config import Settings
    defaults = Settings()
    for name in clear:
        setattr(settings, name, getattr(defaults, name))
    apply_overrides(document)
    return document


def masked_view(overrides: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in FIELDS:
        effective = getattr(settings, name)
        if name in SECRET_FIELDS:
            value = str(effective or "")
            out[name] = {"set": bool(value), "last4": value[-4:] if value else ""}
        else:
            out[name] = effective
    out["overridden"] = sorted(k for k in overrides if k in FIELDS)
    out["providers"] = list(PROVIDERS)
    return out


async def ensure_table() -> None:
    return None
