"""Storage contract.

Audio is referenced by *key*, never by path. Consumers ask the storage
provider for bytes or a stream and never learn where the file physically
lives, which is the whole reason today's ``tmp/`` folder can become object
storage later without touching assessment, reporting or the API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol, runtime_checkable


@dataclass(frozen=True)
class StoredObject:
    key: str
    bytes: int
    content_type: str


@runtime_checkable
class StorageProvider(Protocol):
    """Capability: ``storage``."""

    contract_version = "1.0"
    provider_key: str
    version: str

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredObject:
        ...

    def get(self, key: str) -> bytes:
        ...

    def open(self, key: str) -> BinaryIO:
        ...

    def exists(self, key: str) -> bool:
        ...

    def delete(self, key: str) -> bool:
        ...

    def size(self, key: str) -> int:
        ...

    def purge_prefix(self, prefix: str) -> int:
        """Delete every object under a prefix; returns how many went.

        Exists because offboarding an institution (PLAT-01) has to remove its
        recordings, not just its database schema. A provider that cannot
        enumerate a prefix cannot honour a deletion request.
        """
        ...
