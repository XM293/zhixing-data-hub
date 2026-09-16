from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


@dataclass(frozen=True)
class ArchivedPage:
    storage_key: str
    content_hash: str
    byte_count: int


class RawArchive:
    def __init__(self, root: Path, max_page_bytes: int = 64 * 1024 * 1024):
        self.root = root.resolve()
        self.max_page_bytes = max_page_bytes

    def _path(self, key: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{2}/[a-f0-9]{64}\.(json|bin)\.gz", key):
            raise ValueError("archive.path_invalid")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("archive.path_outside_root")
        return path

    def write(self, payload: dict[str, Any]) -> ArchivedPage:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"),
                         allow_nan=False).encode()
        return self._write_bytes(raw, "json")

    def write_bytes(self, raw: bytes) -> ArchivedPage:
        return self._write_bytes(raw, "bin")

    def _write_bytes(self, raw: bytes, extension: str) -> ArchivedPage:
        if len(raw) > self.max_page_bytes:
            raise ValueError("archive.page_too_large")
        digest = hashlib.sha256(raw).hexdigest()
        key = f"{digest[:2]}/{digest}.{extension}.gz"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        compressed = gzip.compress(raw, mtime=0)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(dir=path.parent, prefix=".raw-", suffix=".tmp",
                                    delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(compressed)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        return ArchivedPage(key, digest, len(compressed))

    def read(self, storage_key: str, content_hash: str) -> dict[str, Any]:
        raw = self.read_bytes(storage_key, content_hash)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("archive.schema_invalid")
        return payload

    def read_bytes(self, storage_key: str, content_hash: str) -> bytes:
        path = self._path(storage_key)
        if storage_key not in {f"{content_hash[:2]}/{content_hash}.{ext}.gz"
                               for ext in ("json", "bin")}:
            raise ValueError("archive.hash_path_mismatch")
        with gzip.open(path, "rb") as stream:
            raw = stream.read(self.max_page_bytes + 1)
        if len(raw) > self.max_page_bytes:
            raise ValueError("archive.page_too_large")
        if hashlib.sha256(raw).hexdigest() != content_hash:
            raise ValueError("archive.hash_mismatch")
        return raw
