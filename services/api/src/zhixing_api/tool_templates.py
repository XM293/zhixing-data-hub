"""Explicitly selected tool definitions; no demo data or permission grants."""

from zhixing_api.ingestion.metrics import OrderSummary
from zhixing_api.tool_schemas import QueryAuthoritativeOrdersInput


def reviewed_tool_template(key: str) -> dict[str, object]:
    if key != "query_authoritative_orders":
        raise ValueError("unknown reviewed tool template")
    return {
        "tool_key": key, "display_name": "权威订单汇总",
        "description": "当前授权集团/法人/项目/店铺的权威订单记录数、分币种订单金额与血缘。"
                       "业务日期闭开区间；包含全部状态，不是付款 GMV 或收入。"
                       "必须保留返回的质量标志，不将空结果解释为全量同步完成。",
        "risk_level": "R0", "permission_key": "metric.query.execute",
        "resource_type": "canonical-order-summary", "scope_resolver": "scope_context_v2",
        "input_schema": QueryAuthoritativeOrdersInput.model_json_schema(),
        "output_schema": OrderSummary.model_json_schema(mode="serialization"),
        "provider": "canonical", "version": "1.0.0", "timeout_seconds": 30, "status": "active",
    }
