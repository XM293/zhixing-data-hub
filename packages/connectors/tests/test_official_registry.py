import json
from pathlib import Path

import jsonschema
from zhixing_connectors.catalog import (
    OFFICIAL_RAW_SPECS,
    OFFICIAL_READONLY_ALLOWLIST_VERSION,
    RESOURCE_CATALOG,
    resource_spec,
)
from zhixing_connectors.official_registry import (
    OFFICIAL_REGISTRY_VERSION,
    official_operation,
    official_operations,
    registry_summary,
)

ROOT = Path(__file__).resolve().parents[3]


def test_official_registry_covers_every_reviewed_read_operation_and_matches_contract():
    payload = {
        "schema_version": 1,
        "registry_version": OFFICIAL_REGISTRY_VERSION,
        "source": "https://apidoc.lingxing.com/_sidebar.md",
        "operations": [item.as_dict() for item in official_operations()],
    }
    schema = json.loads(
        (ROOT / "contracts/data/lingxing-official-operation-registry.schema.json").read_text()
    )
    jsonschema.validate(payload, schema)
    assert len(payload["operations"]) == 470
    assert len({(item["method"], item["path"]) for item in payload["operations"]}) == 470
    assert all(item["review_status"].startswith("read_") for item in payload["operations"])


def test_only_runtime_catalog_operations_are_executable():
    operations = official_operations()
    expected_paths = {(spec.method, spec.path) for spec in RESOURCE_CATALOG}
    executable = {
        (item.method, item.path)
        for item in operations
        if item.execution_status != "metadata_only"
    }
    assert executable == expected_paths
    assert all(item.schema_status == "schema_pending"
               for item in operations if item.execution_status == "metadata_only")
    assert official_operation(operations[0].id) == operations[0]
    assert official_operation("lingxing_op_0000000000000000") is None


def test_registry_summary_separates_metadata_from_runtime_resources():
    summary = registry_summary()
    assert summary["official_read_operations"] == 470
    assert summary["runtime_operations"] == 36
    assert summary["runtime_resources"] == len(RESOURCE_CATALOG) == 39
    assert summary["metadata_only_operations"] == 434
    assert summary["runtime_raw_only_operations"] == 1
    assert summary["runtime_projectable_operations"] == 35
    assert sum(summary["waves"].values()) == 470


def test_dynamic_runtime_catalog_is_bound_to_explicit_readonly_review():
    assert OFFICIAL_READONLY_ALLOWLIST_VERSION == "lingxing-readonly-review-2026-09-11.4"
    assert len(OFFICIAL_RAW_SPECS) == 265
    assert resource_spec("official_72d2c55bdbc031ea") is None
    # Reviewed string arrays are safe only where the source dependency policy
    # creates one immutable value per request; object arrays remain blocked.
    assert resource_spec("official_04957300fd9047e6") is not None
    assert resource_spec("official_bdf5a2637e0fc969") is None
    assert all(item.method in {"GET", "POST"} and item.path for item in OFFICIAL_RAW_SPECS)


def test_explicit_runtime_catalog_is_also_recorded_in_the_readonly_ledger():
    allowlist = json.loads((
        ROOT / "packages/connectors/src/zhixing_connectors/"
        "lingxing_official_readonly_allowlist.json"
    ).read_text(encoding="utf-8"))
    reviewed = {
        (item["method"], item["path"]): item["decision"]
        for item in allowlist["entries"]
    }
    registry_paths = {(item.method, item.path) for item in official_operations()}
    expected = {
        (item.method, item.path)
        for item in RESOURCE_CATALOG
        if (item.method, item.path) in registry_paths
    }
    assert len(expected) == 36
    assert all(reviewed.get(identity) == "read_only" for identity in expected)


def test_newad_amazon_resources_use_the_approved_store_sid_branch():
    newad = [item for item in OFFICIAL_RAW_SPECS
             if item.path.startswith("/pb/openapi/newad/")]
    assert len(newad) == 40
    assert all(item.scope_kind == "store" and item.scope_parameter == "sid"
               and item.scope_parameter_mode == "scalar" for item in newad)
    assert all("sid" in item.required_parameters
               and "profile_id" not in item.required_parameters for item in newad)
    assert all(dict(item.headers) == {"X-API-VERSION": "2"} for item in newad)
    dated = [item for item in newad if "report_date" in item.required_parameters]
    assert dated
    assert all(item.window_fields == ("report_date",)
               and item.window_format == "date"
               and item.schedule_strategy == "source_window" for item in dated)
