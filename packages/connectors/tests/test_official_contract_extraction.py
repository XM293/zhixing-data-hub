import json
from pathlib import Path

import jsonschema
from zhixing_connectors.official_contract_extraction import extract_contract
from zhixing_connectors.official_contracts import (
    OFFICIAL_CONTRACT_VERSION,
    contract_summary,
    official_contract,
    official_contracts,
)

ROOT = Path(__file__).resolve().parents[3]


DOCUMENT = """# 查询合成库存

## 接口信息
| API Path | 请求协议 | 请求方式 | 令牌桶容量 |
| :-- | :-- | :-- | :-- |
| `/erp/sc/data/synthetic` | HTTPS | POST | 5 |

## 请求参数
| 参数名 | 说明 | 必填 | 类型 | 示例 |
| :-- | :-- | :-- | :-- | :-- |
|sid|店铺id|是|[int]|109|
|event_date|报表日期，格式 Y-m-d|是|[string]|2026-01-01|
|offset|分页偏移量|否|[int]|0|
|length|分页长度|否|[int]|1000|

## 返回结果
| 参数名 | 说明 | 必填 | 类型 | 示例 |
| :-- | :-- | :-- | :-- | :-- |
|code|状态码|是|[int]|0|
|data|响应数据|是|[array]||
|data>>sku|SKU|是|[string]|SKU-EXAMPLE|
|data>>quantity|库存数量|是|[number]|1|
"""


def test_extracts_only_structural_official_contract_metadata():
    result = extract_contract(DOCUMENT, method="POST", path="/erp/sc/data/synthetic")
    assert result["rate_capacity"] == 5
    assert result["required_fields"] == ["event_date", "sid"]
    assert result["scope_fields"] == ["sid"]
    assert result["pagination_mode"] == "offset_length"
    assert result["window_fields"] == ["event_date"]
    assert result["window_format"] == "date"
    assert result["rows_path"] == ["data"]
    assert result["total_path"] == []
    assert result["extraction_status"] == "confirmed"
    assert result["request_fields"][0] == {
        "path": ["sid"], "name": "sid", "required": True, "type": "int",
        "description": "店铺id"}
    assert "example" not in str(result).lower()


def test_changed_path_or_missing_schema_stays_non_executable():
    changed = extract_contract(DOCUMENT, method="POST", path="/different")
    assert changed["extraction_status"] == "document_changed"
    missing = extract_contract(
        "# empty\n| `/empty` | HTTPS | POST | 1 |", method="POST", path="/empty")
    assert missing["extraction_status"] == "schema_pending"


def test_nested_collection_wins_over_mislabeled_outer_data_wrapper():
    document = DOCUMENT.replace(
        "|data>>sku|SKU|是|[string]|SKU-EXAMPLE|",
        "|data>>records|[array]|是|unknown||\n"
        "|data>>records>>sku|SKU|是|[string]|SKU-EXAMPLE|\n"
        "|data>>total|总数|是|[int]|1|",
    )
    result = extract_contract(document, method="POST", path="/erp/sc/data/synthetic")
    assert result["rows_path"] == ["data", "records"]
    assert result["total_path"] == ["data", "total"]


def test_extracts_documented_window_and_retention_limits():
    document = DOCUMENT.replace(
        "|event_date|报表日期，格式 Y-m-d|是|[string]|2026-01-01|",
        "|start_date|开始日期，最大跨度31天|是|[string]|2026-01-01|\n"
        "|end_date|结束日期，只能查询最近60天|是|[string]|2026-01-02|",
    )
    result = extract_contract(document, method="POST", path="/erp/sc/data/synthetic")
    assert result["max_window_days"] == 31
    assert result["retention_days"] == 60


def test_required_window_ignores_optional_comparison_range():
    document = DOCUMENT.replace(
        "|event_date|报表日期，格式 Y-m-d|是|[string]|2026-01-01|",
        "|period>>startDate|开始日期，最大跨度31天|是|[string]|2026-01-01|\n"
        "|period>>endDate|结束日期|是|[string]|2026-01-02|\n"
        "|comparison>>comparisonStartDate|对比开始日期|否|[string]|2025-01-01|\n"
        "|comparison>>comparisonEndDate|对比结束日期|否|[string]|2025-01-02|",
    )
    result = extract_contract(document, method="POST", path="/erp/sc/data/synthetic")
    assert result["window_fields"] == ["startDate", "endDate"]


def test_extracts_official_after_before_date_windows_and_hyphenated_time_format():
    document = """
## 接口信息
| 接口路径 | 名称 | 请求方式 | 限流 |
| /readonly | synthetic | POST | 1 |
## 请求参数
| 参数名 | 说明 | 必填 | 类型 |
| sid | 店铺ID | 是 | long |
| shipment_date_after | 快照开始时间，格式：Y-m-d hh-mm-ss，区间支持7天 | 是 | string |
| shipment_date_before | 快照结束时间，格式：Y-m-d hh-mm-ss，区间支持7天 | 是 | string |
## 返回结果
| 参数名 | 说明 | 必填 | 类型 |
| data>>list | 列表 | 否 | array |
| data>>list>>id | ID | 否 | string |
"""
    result = extract_contract(document, method="POST", path="/readonly")
    assert result["window_fields"] == ["shipment_date_after", "shipment_date_before"]
    assert result["window_format"] == "datetime"
    assert result["max_window_days"] == 7


def test_generated_official_contracts_are_complete_versioned_and_example_free():
    payload = json.loads((ROOT /
        "packages/connectors/src/zhixing_connectors/lingxing_official_contracts.json"
    ).read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts/data/lingxing-official-contract.schema.json")
                        .read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
    assert payload["contract_version"] == OFFICIAL_CONTRACT_VERSION
    assert len(official_contracts()) == 470
    assert all(item.extraction_status == "confirmed" for item in official_contracts())
    assert all(item.document_sha256 == item.retrieved_sha256 for item in official_contracts())
    assert all("example" not in field for operation in payload["operations"]
               for field in operation)
    first = official_contracts()[0]
    assert official_contract(first.id) == first
    assert official_contract(first.runtime_key) == first
    assert contract_summary()["official_contracts"] == 470


def test_verified_live_response_containers_are_part_of_the_versioned_contract():
    replenishment = official_contract("lingxing_op_1f62b5154c5436d8")
    walmart_payment = official_contract("lingxing_op_d82ef06c6be39f88")
    assert replenishment is not None and replenishment.rows_path == ("data", "list")
    assert walmart_payment is not None and walmart_payment.rows_path == ("data",)
