"""Generate reviewed parameter strategies for dependent Lingxing read resources."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/connectors/src"))

from zhixing_connectors.official_contracts import OFFICIAL_CONTRACT_VERSION  # noqa: E402

VERSION = "lingxing-parameter-policy-2026-09-13.5"
TARGET = ROOT / "packages/connectors/src/zhixing_connectors/lingxing_parameter_policies.json"
WORKLIST = ROOT / "contracts/data/lingxing-official-rollout-worklist.json"

DEPENDENCIES: dict[str, list[str]] = {
    "amazonOrderId": ["amazonOrderId"], "asin": ["asin"],
    "categoryUniqueId": ["categoryUniqueId"], "currencyCode": ["currencyCode"],
    "inboundPlanId": ["inboundPlanId"], "invoice_id": ["invoice_id"],
    "marketplaceId": ["marketplaceId"], "msku": ["msku"], "orderId": ["orderId"],
    "report_document_id": ["report_document_id"],
    "sellerSku": ["sellerSku", "msku"],
    "sku": ["msku", "sellerSku"],
    "skus": ["sellerSku", "msku"],
    "shipment_id": ["shipment_id", "shipmentId"],
    "shipmentId": ["shipmentId", "shipment_id"],
}
CALENDAR = {"month": "month", "settleMonth": "month",
            "pullDate": "day", "site_date": "day"}
MANUAL = {"mids": "country_id_scope_required",
          "productType": "product_type_values_required",
          "region": "approved_store_region_mapping_required"}

GENERIC_ENUMS: dict[str, tuple[list[str], str]] = {
    "sortField": (["startTime"], "ordering"),
    "sortType": (["asc"], "ordering"),
    "isParent": (["0", "1"], "exhaustive"),
    "searchField": (["1", "2", "4", "5", "6", "7", "8", "9"], "exhaustive"),
    "orderField": (["campaignId"], "ordering"),
    "orderType": (["asc"], "ordering"),
    "new_report": (["1"], "documented_latest"),
    "timeType": (["1"], "documented_default"),
    "storage_type": (
        ["Standard", "Oversize", "Apparel", "Footwear", "ExtraLarge"], "exhaustive"),
    "sug_type": (["1", "2", "3"], "exhaustive"),
    "currency_type": ([str(value) for value in range(1, 17)], "exhaustive"),
    "version": ([""], "documented_empty"),
    "asinType": (["msku", "asin", "parentAsin", "sku", "spu"], "exhaustive"),
    "search_date_field": (["posted_date_locale"], "complete_time_axis"),
    "summary_type": (["asin", "parent_asin", "msku"], "exhaustive"),
    "summary_field": (["asin", "parent_asin", "msku", "sku"], "exhaustive"),
    "sort_field": (["volume"], "ordering"),
    "sort_type": (["desc"], "ordering"),
    "queryType": (["2"], "most_granular"),
    "view": (["sourcing", "manufacturing"], "exhaustive"),
    "summaryField": (["1", "2", "3", "4", "5", "6", "11"], "exhaustive"),
    "result_type": (["1", "2", "3"], "exhaustive"),
    "date_unit": (["1", "2", "3", "4"], "exhaustive"),
    "asin_type": (["1", "2"], "exhaustive"),
    "time_search_type": (["1", "2"], "exhaustive"),
    "date_type": (["1", "2", "3"], "exhaustive"),
    "shipmentType": (["1", "2", "3"], "exhaustive"),
    "show_status": (["1"], "all_statuses"),
}

RESOURCE_ENUMS: dict[tuple[str, str], tuple[list[str], str]] = {
    ("official_a2fa77b89b3172af", "group_type"):
        (["hourly", "weekly"], "exhaustive"),
    ("official_271a3c2c8d3dfc09", "sponsored_type"): (["ALL"], "all_data"),
    ("official_271a3c2c8d3dfc09", "target_type"): (["ALL"], "all_data"),
    ("official_2eeb6e5205deb764", "target_type"):
        (["keyword", "target"], "exhaustive"),
    ("official_8e2e3f4a4ed9dbde", "target_type"):
        (["keyword", "target"], "exhaustive"),
    ("official_91609b93ec2b7dfc", "log_source"): (["all"], "all_data"),
    ("official_91609b93ec2b7dfc", "sponsored_type"):
        (["sp", "sb", "sd"], "exhaustive"),
    ("official_91609b93ec2b7dfc", "operate_type"): ([
        "campaigns", "adGroups", "productAds", "keywords", "negativeKeywords",
        "targets", "negativeTargets", "profiles",
    ], "exhaustive"),
    ("official_9a24daac7382a112", "ads_type"): (["ALL"], "all_data"),
    ("official_9a24daac7382a112", "targeting_type"): (["ALL"], "all_data"),
    ("official_a08f8cfbd51f8aa5", "sponsored_type"): (["ALL"], "all_data"),
    ("official_a08f8cfbd51f8aa5", "target_type"): (["keyword"], "only_value"),
    ("official_576da4fe8614f636", "dimensionType"):
        (["1", "2", "3", "4", "5"], "exhaustive"),
    ("official_e538c1149d341c8a", "dimensionType"):
        (["1", "2", "3", "4"], "exhaustive"),
    ("official_281e1d2a31717fc9", "dateType"): (["1", "2"], "exhaustive"),
    ("official_5b70e6c18c973e74", "dateType"): (["1", "2"], "exhaustive"),
    ("official_e6d150b0783457b2", "dateType"): (["1", "2"], "exhaustive"),
    ("official_0e56fdfae7c28e18", "dateType"): (["0", "1"], "exhaustive"),
    ("official_41831dde4af8b73a", "data_type"): (["1", "2"], "exhaustive"),
    ("official_8e9e5f51f4aa10e1", "data_type"):
        (["1", "2", "3", "4", "5", "6"], "exhaustive"),
    ("official_4673bfc9f9133624", "search_field_time"):
        (["update_time"], "complete_time_axis"),
    ("official_4a4c7818d7c2b40f", "search_field_time"):
        (["last_updated_date"], "complete_time_axis"),
}

PAIRED_FIELDS: dict[tuple[str, str], dict[str, list[str]]] = {
    ("official_11bb1741d5441737", "summary_field"): {
        "parent_asin": ["parentAsin"], "asin": ["asin"], "msku": ["msku"],
        "sku": ["sellerSku"], "spu": ["spu"],
    },
    ("official_814603b5d7e61e0d", "search_field"): {
        "asin": ["asin"], "parent_asin": ["parentAsin"], "msku": ["msku"],
    },
}
PAIRED_VALUE_FIELDS = {"summary_field_value", "search_value"}


def _rule(resource_key: str, field: str) -> dict[str, object]:
    if field in DEPENDENCIES:
        return {"field": field, "strategy": "dependency",
                "value_types": DEPENDENCIES[field]}
    if field in CALENDAR:
        return {"field": field, "strategy": "calendar", "unit": CALENDAR[field]}
    if field in MANUAL:
        return {"field": field, "strategy": "manual", "reason": MANUAL[field]}
    if (resource_key, field) in PAIRED_FIELDS:
        return {"field": field, "strategy": "paired_dependency",
                "value_field": ("summary_field_value" if field == "summary_field"
                                else "search_value"),
                "dimensions": PAIRED_FIELDS[(resource_key, field)]}
    enum = RESOURCE_ENUMS.get((resource_key, field)) or GENERIC_ENUMS.get(field)
    if enum is not None:
        values, purpose = enum
        return {"field": field, "strategy": "enum", "values": values,
                "purpose": purpose, "allow_empty": purpose == "documented_empty"}
    if field in PAIRED_VALUE_FIELDS:
        return {"field": field, "strategy": "provided_by_pair"}
    raise ValueError(f"unreviewed parameter policy: {resource_key}:{field}")


def build() -> dict[str, object]:
    worklist = json.loads(WORKLIST.read_text(encoding="utf-8"))
    assert worklist["official_contract_version"] == OFFICIAL_CONTRACT_VERSION
    resources = []
    for item in worklist["items"]:
        fields = list(item.get("required_configuration") or [])
        if not fields:
            continue
        rules = [_rule(str(item["resource_key"]), str(field)) for field in fields]
        resources.append({
            "resource_key": item["resource_key"], "operation_id": item["operation_id"],
            "wave": item["wave"], "status": (
                "manual_required" if any(rule["strategy"] == "manual" for rule in rules)
                else "ready_for_bounded_fanout"),
            "combination": ("source_tuple" if sum(
                rule["strategy"] == "dependency" for rule in rules) > 1 else "bounded_product"),
            "max_partitions_per_batch": 64, "rules": rules,
        })
    return {"schema_version": 1, "policy_version": VERSION,
            "official_contract_version": OFFICIAL_CONTRACT_VERSION,
            "source": "https://apidoc.lingxing.com/", "resources": resources}


def main() -> None:
    payload = build()
    assert len(payload["resources"]) == 78
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    counts: dict[str, int] = {}
    for resource in payload["resources"]:
        status = str(resource["status"])
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps({"status": "passed", "resources": len(payload["resources"]),
                      "states": counts, "policy_version": VERSION}))


if __name__ == "__main__":
    main()
