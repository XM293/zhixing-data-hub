from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def wire_value(value: object) -> str:
    # The official browser tool uses JSON.stringify, which preserves nested insertion order.
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return "null"
    return str(value)


def canonicalize(params: Mapping[str, object]) -> str:
    return "&".join(f"{key}={wire_value(params[key])}" for key in sorted(params)
                     if params[key] != "")


def build_signature(params: Mapping[str, object], app_id: str) -> str:
    if not app_id or len(app_id.encode("utf-8")) not in {16, 24, 32}:
        raise ValueError("lingxing app_id must be a valid AES key length")
    digest = hashlib.md5(canonicalize(params).encode("utf-8")).hexdigest().upper().encode("ascii")
    pad = 16 - len(digest) % 16
    encryptor = Cipher(algorithms.AES(app_id.encode("utf-8")), modes.ECB()).encryptor()
    encrypted = encryptor.update(digest + bytes([pad]) * pad) + encryptor.finalize()
    # Return the wire value unescaped. httpx performs URL encoding exactly once.
    return base64.b64encode(encrypted).decode("ascii")
