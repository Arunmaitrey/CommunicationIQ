"""Storage access point and key conventions."""
from __future__ import annotations

from functools import lru_cache

from app.storage.base import StorageProvider, StoredObject
from app.storage.local import LocalTempStorage

__all__ = [
    "StorageProvider",
    "StoredObject",
    "get_storage",
    "recording_key",
    "prompt_key",
    "export_key",
    "tenant_prefixes",
]


@lru_cache(maxsize=1)
def get_storage() -> StorageProvider:
    """The active storage provider.

    One implementation today. When object storage arrives it is selected here
    from ProviderConfig, and nothing that stores or reads audio changes.
    """
    return LocalTempStorage()


def recording_key(tenant_slug: str, attempt_id: str, response_id: str, ext: str = "webm") -> str:
    return f"recordings/{tenant_slug}/{attempt_id}/{response_id}.{ext}"


def prompt_key(item_id: str, ext: str = "mp3") -> str:
    return f"prompts/{item_id}.{ext}"


def export_key(tenant_slug: str, name: str) -> str:
    return f"exports/{tenant_slug}/{name}"


def tenant_prefixes(tenant_slug: str) -> list[str]:
    """Every place one institution's files live."""
    return [f"recordings/{tenant_slug}", f"exports/{tenant_slug}"]
