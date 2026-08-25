"""Local working storage under ``MEDIA_ROOT`` (the repo's ``tmp/`` by default).

Keys look like ``recordings/<tenant>/<attempt>/<response>.webm``. They are
validated before touching the filesystem: a key may not be absolute, may not
climb out of the media root, and may not contain a drive letter. A storage key
originates from our own code today, but the moment one is echoed back from a
client this check is the only thing between us and an arbitrary file write.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

from app.config import settings
from app.storage.base import StoredObject

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class LocalTempStorage:
    """Filesystem implementation of the ``storage`` capability."""

    contract_version = "1.0"
    provider_key = "local_tmp"
    version = "0.1.0"

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.media_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # -- key handling ------------------------------------------------------

    def _resolve(self, key: str) -> Path:
        if not key or not _SAFE_KEY.match(key) or ".." in key.split("/"):
            raise ValueError(f"unsafe storage key: {key!r}")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"storage key escapes the media root: {key!r}")
        return path

    # -- contract ----------------------------------------------------------

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredObject:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return StoredObject(key=key, bytes=len(data), content_type=content_type)

    def get(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def open(self, key: str) -> BinaryIO:
        return self._resolve(key).open("rb")

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> bool:
        path = self._resolve(key)
        if not path.exists():
            return False
        path.unlink()
        return True

    def size(self, key: str) -> int:
        return self._resolve(key).stat().st_size

    def purge_prefix(self, prefix: str) -> int:
        """Remove everything under a prefix — used when an institution leaves.

        The prefix goes through the same validation as a key: a caller that
        could pass ".." here would be able to empty the media root.
        """
        root = self._resolve(prefix.rstrip("/"))
        if not root.exists():
            return 0
        removed = 0
        if root.is_file():
            root.unlink()
            return 1
        for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_file():
                path.unlink()
                removed += 1
            elif path.is_dir():
                path.rmdir()
        root.rmdir()
        return removed
