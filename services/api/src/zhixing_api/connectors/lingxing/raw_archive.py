from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path


class RawArchive:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, payload: object) -> dict[str, object]:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        digest = hashlib.sha256(data).hexdigest()
        target = (self.root / digest[:2] / f"{digest}.json.gz").resolve()
        if self.root not in target.parents:
            raise ValueError("unsafe archive path")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        with gzip.open(tmp, "wb") as stream:
            stream.write(data)
        tmp.replace(target)
        return {
            "content_hash": digest,
            "storage_key": str(target.relative_to(self.root)),
            "bytes": len(data),
        }
