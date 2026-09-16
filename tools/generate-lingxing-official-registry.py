"""Generate the metadata-only Lingxing operation registry from the official-doc audit."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/connectors/src"))

from zhixing_connectors.catalog import RESOURCE_CATALOG, can_project_to_core  # noqa: E402

SOURCE = "https://apidoc.lingxing.com/_sidebar.md"
VERSION = "lingxing-official-2026-09-10.2"
READ_STATUSES = {
    "read_candidate",
    "read_only_confirmed",
    "read_only_schema_pending",
}
WAVES = {
    "BasicData": "W0",
    "Product": "W1",
    "Logistics": "W1",
    "Sale": "W2",
    "MultiPlatform": "W2",
    "Warehouse": "W3",
    "FBA": "W3",
    "FBASug": "W3",
    "FBALimit": "W3",
    "Purchase": "W4",
    "newAd": "W5",
    "TargetManage": "W5",
    "Finance": "W6",
    "Statistics": "W6",
    "Service": "W7",
    "SourceData": "W8",
    "VC": "W8",
    "Tools": "W8",
}


def operation_id(method: str, path: str) -> str:
    digest = hashlib.sha256(f"{method}\0{path}".encode()).hexdigest()[:16]
    return f"lingxing_op_{digest}"


def wave(document_path: str) -> str:
    normalized = document_path.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    root = parts[1] if len(parts) > 1 and parts[0] == "docs" else parts[0]
    return WAVES.get(root, "W8")


def main() -> None:
    inventory_path = ROOT / "docs/development/lingxing-official-document-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    runtime: dict[tuple[str, str], list[object]] = {}
    for spec in RESOURCE_CATALOG:
        runtime.setdefault((spec.method, spec.path), []).append(spec)
    operations: list[dict[str, object]] = []
    for document in inventory["documents"]:
        if document["review_status"] not in READ_STATUSES:
            continue
        for operation in document["operations"]:
            key = (str(operation["method"]).strip().upper(), str(operation["path"]).strip())
            specs = runtime.get(key, [])
            projectable = bool(specs) and any(can_project_to_core(spec) for spec in specs)
            execution_status = (
                "runtime_projectable"
                if projectable
                else "runtime_raw_only"
                if specs
                else "metadata_only"
            )
            operations.append(
                {
                    "id": operation_id(*key),
                    "title": document["document_title"] or document["title"],
                    "document_path": document["path"],
                    "documentation_url": document["url"].replace("\\", "/"),
                    "method": key[0],
                    "path": key[1],
                    "wave": wave(document["path"]),
                    "review_status": document["review_status"],
                    "execution_status": execution_status,
                    "schema_status": "confirmed" if projectable else "schema_pending",
                    "resource_keys": sorted(spec.key for spec in specs),
                    "document_sha256": document["sha256"],
                }
            )
    operations.sort(key=lambda item: (item["wave"], item["document_path"], item["path"]))
    assert len(operations) == 470
    assert len({(item["method"], item["path"]) for item in operations}) == len(operations)
    payload = {
        "schema_version": 1,
        "registry_version": VERSION,
        "source": SOURCE,
        "operations": operations,
    }
    target = (
        ROOT
        / "packages/connectors/src/zhixing_connectors/lingxing_official_registry.json"
    )
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
