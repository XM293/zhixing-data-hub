"""Fetch public Lingxing docs and persist structural read-contract metadata only."""

from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/connectors/src"))

from zhixing_connectors.official_contract_extraction import extract_contract  # noqa: E402
from zhixing_connectors.official_registry import (  # noqa: E402
    OfficialOperation,
    official_operations,
)

SOURCE = "https://apidoc.lingxing.com/_sidebar.md"
VERSION = "lingxing-contract-2026-09-11.7"
TARGET = ROOT / "packages/connectors/src/zhixing_connectors/lingxing_official_contracts.json"

# The official response tables below describe enough structure to prove the row
# container, but the generic extractor cannot distinguish it without a live shape.
# Each correction was confirmed against a value-free candidate response shape and
# remains guarded by the pinned official document hash plus the field assertions.
VERIFIED_ROWS_PATHS: dict[str, tuple[str, ...]] = {
    "lingxing_op_1f62b5154c5436d8": ("data", "list"),
    "lingxing_op_d82ef06c6be39f88": ("data",),
}


def _apply_verified_rows_path(
    operation: OfficialOperation,
    extracted: dict[str, object],
) -> None:
    override = VERIFIED_ROWS_PATHS.get(operation.id)
    if override is None:
        return
    if extracted.get("extraction_status") != "confirmed":
        raise RuntimeError("lingxing.rows_path_override_contract_unconfirmed")
    response_fields = extracted.get("response_fields")
    if not isinstance(response_fields, list):
        raise RuntimeError("lingxing.rows_path_override_fields_missing")
    paths = {
        tuple(str(part) for part in field.get("path", [])): str(field.get("type", "")).lower()
        for field in response_fields
        if isinstance(field, dict)
    }
    if operation.id == "lingxing_op_1f62b5154c5436d8":
        # The table omits the list container row, but documents its child fields.
        if not any(path[:2] == override and len(path) > 2 for path in paths):
            raise RuntimeError("lingxing.rows_path_override_structure_changed")
    elif not any(token in paths.get(override, "") for token in ("array", "list")):
        raise RuntimeError("lingxing.rows_path_override_structure_changed")
    extracted["rows_path"] = list(override)


def _fetch(operation: OfficialOperation) -> dict[str, object]:
    url = operation.documentation_url
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "apidoc.lingxing.com":
        raise RuntimeError("lingxing.contract_host_blocked")
    expected_hash = operation.document_sha256
    content = b""
    for attempt in range(3):
        try:
            with httpx.Client(timeout=30, follow_redirects=False, trust_env=False,
                              headers={"User-Agent": "zhixing-contract-audit/1"}) as client:
                response = client.get(url)
                response.raise_for_status()
                content = response.content
                break
        except httpx.HTTPError:
            if attempt == 2:
                break
    retrieved_hash = hashlib.sha256(content).hexdigest()
    text = content.decode("utf-8", errors="replace")
    extracted = extract_contract(text, method=operation.method, path=operation.path)
    if not content:
        extracted["extraction_status"] = "schema_pending"
    elif retrieved_hash != expected_hash:
        extracted["extraction_status"] = "document_changed"
    _apply_verified_rows_path(operation, extracted)
    return {
        "id": operation.id,
        "method": operation.method,
        "path": operation.path,
        "wave": operation.wave,
        "documentation_url": url,
        "document_sha256": expected_hash,
        "retrieved_sha256": retrieved_hash,
        **extracted,
    }


def main() -> None:
    operations = official_operations()
    with ThreadPoolExecutor(max_workers=8) as pool:
        contracts = list(pool.map(_fetch, operations))
    contracts.sort(key=lambda item: (str(item["path"]), str(item["method"])))
    payload = {"schema_version": 1, "contract_version": VERSION,
               "source": SOURCE, "operations": contracts}
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    for item in contracts:
        status = str(item["extraction_status"])
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps({"operations": len(contracts), "statuses": counts}, sort_keys=True))


if __name__ == "__main__":
    main()
