"""Freeze the reviewed read-only decisions for executable official Lingxing contracts."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "lingxing-readonly-review-2026-09-11.4"
REVIEWED_CONTRACT_VERSION = "lingxing-contract-2026-09-11.7"
TARGET = (ROOT / "packages/connectors/src/zhixing_connectors/"
          "lingxing_official_readonly_allowlist.json")
BLOCKED_MUTATIONS = {
    "lingxing_op_72d2c55bdbc031ea": {
        "title": "WFS货件暂存",
        "path": "/basicOpen/multiplatform/cargo/storage",
        "reason": "official_title_declares_state_mutation",
    },
}
NEWAD_STORE_READS = frozenset({
    "lingxing_op_0c965b63c13509a7",
    "lingxing_op_1accf3fcfe303635",
    "lingxing_op_20ea9894c69263c4",
    "lingxing_op_26ca516f5ff2a508",
    "lingxing_op_271a3c2c8d3dfc09",
    "lingxing_op_273db2b48715beeb",
    "lingxing_op_2eeb6e5205deb764",
    "lingxing_op_3e3dd5c5f9a138ab",
    "lingxing_op_3e68495907ab0f72",
    "lingxing_op_44834e4a61d753cc",
    "lingxing_op_4b4259f3b53730f1",
    "lingxing_op_4f933f3d1fafaf71",
    "lingxing_op_4fa8b7280fe6ed17",
    "lingxing_op_530e7e686bbbff69",
    "lingxing_op_5c513243a6ecc9ae",
    "lingxing_op_5f2db44c8763ca79",
    "lingxing_op_603aa36f9430fd19",
    "lingxing_op_6b4e9d491796a0d4",
    "lingxing_op_77fe5590f8dab444",
    "lingxing_op_783ea35a9813c6bd",
    "lingxing_op_7854052822535a7c",
    "lingxing_op_8c35228f62ce213b",
    "lingxing_op_8e2e3f4a4ed9dbde",
    "lingxing_op_91609b93ec2b7dfc",
    "lingxing_op_93d0f274a58cc6d7",
    "lingxing_op_9a24daac7382a112",
    "lingxing_op_a08f8cfbd51f8aa5",
    "lingxing_op_a2d36233dedf90df",
    "lingxing_op_a91d36406f4978f7",
    "lingxing_op_a9617a31fe8f385c",
    "lingxing_op_ac6873a70cf30793",
    "lingxing_op_b1c85bbb349b0890",
    "lingxing_op_b1d18ba8971795ce",
    "lingxing_op_b608c2acde25181b",
    "lingxing_op_c43d719e1f198828",
    "lingxing_op_c52ecc90a9549079",
    "lingxing_op_c8205312b9aed0b4",
    "lingxing_op_c8b269e402d67633",
    "lingxing_op_cd5c65a106df79f9",
    "lingxing_op_f0920d3940b0d970",
})


def main() -> None:
    contracts_path = (ROOT / "packages/connectors/src/zhixing_connectors/"
                      "lingxing_official_contracts.json")
    contracts_payload = json.loads(contracts_path.read_text(encoding="utf-8"))
    assert contracts_payload["contract_version"] == REVIEWED_CONTRACT_VERSION
    previous = json.loads(TARGET.read_text(encoding="utf-8"))
    reviewed = {str(item["operation_id"]): item for item in previous["entries"]}
    registry_path = (ROOT / "packages/connectors/src/zhixing_connectors/"
                     "lingxing_official_registry.json")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    operations = {str(item["id"]): item for item in registry["operations"]}
    explicit_runtime_reads = {
        str(item["id"])
        for item in registry["operations"]
        if item["execution_status"] != "metadata_only"
    }
    assert len(explicit_runtime_reads) == 36
    reviewed_ids = set(reviewed) | set(NEWAD_STORE_READS) | explicit_runtime_reads
    candidates = [contract for contract in contracts_payload["operations"]
                  if str(contract["id"]) in reviewed_ids]
    assert len(candidates) == 317
    entries: list[dict[str, object]] = []
    for contract in sorted(candidates, key=lambda item: str(item["id"])):
        contract_id = str(contract["id"])
        operation = operations[contract_id]
        prior = reviewed.get(contract_id)
        if prior is not None:
            assert prior["method"] == contract["method"]
            assert prior["path"] == contract["path"]
            assert prior["document_sha256"] == contract["document_sha256"]
        else:
            assert contract_id in NEWAD_STORE_READS or contract_id in explicit_runtime_reads
            if contract_id in NEWAD_STORE_READS:
                assert contract["method"] == "POST" and str(contract["path"]).startswith(
                    "/pb/openapi/newad/")
                assert contract["extraction_status"] == "confirmed"
                assert contract["rows_path"] == ["data"]
                fields = {str(item["name"]): item for item in contract["request_fields"]}
                assert fields["sid"]["required"] is True
                if "profile_id" in fields and fields["profile_id"]["required"] is True:
                    description = str(fields["profile_id"]["description"]).replace(" ", "")
                    assert "sid跟profile_id其中一个必填" in description
            else:
                assert operation["execution_status"] != "metadata_only"
        blocked = BLOCKED_MUTATIONS.get(contract_id)
        if blocked is not None:
            assert operation["title"] == blocked["title"]
            assert contract["path"] == blocked["path"]
        entries.append({
            "operation_id": contract_id,
            "method": contract["method"],
            "path": contract["path"],
            "document_sha256": contract["document_sha256"],
            "decision": "blocked_mutation" if blocked else "read_only",
            "reason": (blocked["reason"] if blocked else
                       "official_newad_store_read_contract_reviewed"
                       if contract_id in NEWAD_STORE_READS else
                       "explicit_runtime_read_contract_reviewed"
                       if contract_id in explicit_runtime_reads else
                       "official_read_contract_reviewed"),
        })
    assert sum(item["decision"] == "read_only" for item in entries) == 316
    payload = {
        "schema_version": 1,
        "allowlist_version": VERSION,
        "official_contract_version": REVIEWED_CONTRACT_VERSION,
        "source": "https://apidoc.lingxing.com/",
        "entries": entries,
    }
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"status": "passed", "reviewed": len(entries),
                      "read_only": 316, "blocked_mutation": 1,
                      "allowlist_version": VERSION}))


if __name__ == "__main__":
    main()
