from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import ToolDefinition

TOOL_DEFINITIONS: list[dict[str, object]] = [
    {
        "id": "tool_definition_read_policy_v1",
        "tool_key": "read_policy",
        "display_name": "读取企业制度",
        "description": "按制度键或问题读取当前可引用的企业制度条款和版本证据。",
        "risk_level": "R0",
        "permission_key": "knowledge.document.read",
        "resource_type": "knowledge.policy",
        "scope_resolver": "enterprise_shared_knowledge",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2, "maxLength": 500},
                "policy_key": {"type": ["string", "null"], "maxLength": 120},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "output_schema": {"type": "object", "required": ["query", "items"]},
        "provider": "zhixing-knowledge-service",
        "version": "1.0.0",
        "timeout_seconds": 10,
    },
    {
        "id": "tool_definition_search_knowledge_v1",
        "tool_key": "search_knowledge",
        "display_name": "检索企业知识",
        "description": "检索当前有效或已发布的企业知识切片，并返回版本与原文定位。",
        "risk_level": "R0",
        "permission_key": "knowledge.document.read",
        "resource_type": "knowledge.document",
        "scope_resolver": "enterprise_shared_knowledge",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 2, "maxLength": 500},
                "limit": {"type": "integer", "minimum": 1, "maximum": 8, "default": 5},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "output_schema": {"type": "object", "required": ["query", "items"]},
        "provider": "zhixing-knowledge-service",
        "version": "1.0.0",
        "timeout_seconds": 10,
    },
    {
        "id": "tool_definition_get_metric_v1_1",
        "tool_key": "get_metric",
        "display_name": "查询经营指标",
        "description": "按稳定指标键、授权范围和时间窗口读取指标口径、当前值与可追溯序列。",
        "risk_level": "R0",
        "permission_key": "metric.query.execute",
        "resource_type": "metric.snapshot",
        "scope_resolver": "metric_snapshot_scope_key",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_key": {"type": ["string", "null"], "maxLength": 100},
                "query": {"type": ["string", "null"], "maxLength": 160},
                "scope_key": {"type": "string", "minLength": 1, "maxLength": 160},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
                "days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 1},
            },
            "required": ["scope_key"],
            "additionalProperties": False,
        },
        "output_schema": {"type": "object", "required": ["scope_key", "items"]},
        "provider": "zhixing-metric-service",
        "version": "1.1.0",
        "timeout_seconds": 10,
    },
    {
        "id": "tool_definition_query_commerce_facts_v1",
        "tool_key": "query_commerce_facts",
        "display_name": "查询经营事实",
        "description": "按授权范围读取订单、退款、库存、广告、异常和来源血缘的受控经营事实视图。",
        "risk_level": "R0",
        "permission_key": "metric.query.execute",
        "resource_type": "commerce.fact",
        "scope_resolver": "commerce_scope_mapping",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope_key": {"type": "string", "minLength": 1, "maxLength": 160},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            },
            "required": ["scope_key"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "required": [
                "scope_key",
                "summary",
                "funnel",
                "exceptions",
                "recent_orders",
                "lineage",
            ],
        },
        "provider": "zhixing-commerce-fact-service",
        "version": "1.0.0",
        "timeout_seconds": 10,
    },
    {
        "id": "tool_definition_query_customer_360_v1_1",
        "tool_key": "query_customer_360",
        "display_name": "查询客户 360",
        "description": (
            "按授权范围读取客户汇总，或按稳定客户键下钻交易、退款、触点、"
            "策略边界和来源血缘。"
        ),
        "risk_level": "R0",
        "permission_key": "customer.profile.read",
        "resource_type": "customer.profile",
        "scope_resolver": "customer_scope_mapping",
        "input_schema": {
            "type": "object",
            "properties": {
                "scope_key": {"type": "string", "minLength": 1, "maxLength": 160},
                "customer_key": {
                    "type": ["string", "null"],
                    "minLength": 1,
                    "maxLength": 160,
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
            },
            "required": ["scope_key"],
            "additionalProperties": False,
        },
        "output_schema": {
            "oneOf": [
                {
                    "type": "object",
                    "required": [
                        "scope_key",
                        "summary",
                        "segments",
                        "channels",
                        "customers",
                        "recent_touchpoints",
                        "lineage",
                    ],
                },
                {
                    "type": "object",
                    "required": [
                        "scope_key",
                        "customer_key",
                        "profile",
                        "summary",
                        "recommendations",
                        "timeline",
                        "orders",
                        "refunds",
                        "touchpoints",
                        "lineage",
                    ],
                },
            ],
        },
        "provider": "zhixing-customer-360-service",
        "version": "1.1.0",
        "timeout_seconds": 10,
    },
]


def tool_seed_checksum_payload() -> list[dict[str, object]]:
    return TOOL_DEFINITIONS


def seed_tool_registry(session: Session, *, enterprise_id: str, now: datetime) -> None:
    existing = {
        (item.tool_key, item.version): item
        for item in session.scalars(
            select(ToolDefinition).where(ToolDefinition.enterprise_id == enterprise_id)
        )
    }
    for definition in TOOL_DEFINITIONS:
        tool_key = str(definition["tool_key"])
        version = str(definition["version"])
        item = existing.get((tool_key, version))
        if item is None:
            item = ToolDefinition(
                id=str(definition["id"]),
                enterprise_id=enterprise_id,
                tool_key=tool_key,
                version=version,
                created_at=now,
            )
            session.add(item)
        item.display_name = str(definition["display_name"])
        item.description = str(definition["description"])
        item.risk_level = str(definition["risk_level"])
        item.permission_key = str(definition["permission_key"])
        item.resource_type = str(definition["resource_type"])
        item.scope_resolver = str(definition["scope_resolver"])
        item.input_schema = dict(cast(dict[str, object], definition["input_schema"]))
        item.output_schema = dict(cast(dict[str, object], definition["output_schema"]))
        item.provider = str(definition["provider"])
        item.timeout_seconds = cast(int, definition["timeout_seconds"])
        item.status = "active"
        item.updated_at = now

    seeded_versions = {
        str(definition["tool_key"]): str(definition["version"])
        for definition in TOOL_DEFINITIONS
    }
    seeded_providers = {
        str(definition["tool_key"]): str(definition["provider"])
        for definition in TOOL_DEFINITIONS
    }
    for item in existing.values():
        if (
            item.tool_key in seeded_versions
            and item.version != seeded_versions[item.tool_key]
            and item.provider == seeded_providers[item.tool_key]
        ):
            item.status = "deprecated"
            item.updated_at = now
