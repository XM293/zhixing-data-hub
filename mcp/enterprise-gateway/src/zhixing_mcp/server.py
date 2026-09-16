from __future__ import annotations

import asyncio
from typing import cast

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from zhixing_mcp.api_client import GatewayApiClient
from zhixing_mcp.config import load_settings

ALL_TOOL_KEYS = frozenset(
    {
        "read_policy",
        "search_knowledge",
        "get_metric",
        "query_commerce_facts",
        "query_customer_360",
    }
)


def create_server(
    api_client: GatewayApiClient,
    enabled_tool_keys: frozenset[str] | None = None,
) -> MCPServer:
    enabled = ALL_TOOL_KEYS if enabled_tool_keys is None else enabled_tool_keys
    server = MCPServer(
        "zhixing-enterprise-gateway",
        version="0.1.0",
        instructions=(
            "使用知行数枢企业 API 读取制度、知识、经营指标、规范经营事实和客户洞察。"
            "工具身份由短期受限会话建立，不接受主体、访问角色或权限参数。"
        ),
    )

    read_only = ToolAnnotations(
        read_only_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    )

    if "read_policy" in enabled:

        @server.tool(annotations=read_only)
        async def read_policy(
            query: str,
            policy_key: str | None = None,
            limit: int = 5,
        ) -> dict[str, object]:
            """读取当前企业制度条款，返回版本、生效时间、原文定位和引用摘录。"""
            parameters: dict[str, object] = {"query": query, "limit": limit}
            if policy_key is not None:
                parameters["policy_key"] = policy_key
            return await api_client.invoke("read_policy", parameters)

    if "search_knowledge" in enabled:

        @server.tool(annotations=read_only)
        async def search_knowledge(query: str, limit: int = 5) -> dict[str, object]:
            """检索企业知识中心，返回可追溯的文档版本和证据切片。"""
            return await api_client.invoke(
                "search_knowledge",
                {"query": query, "limit": limit},
            )

    if "get_metric" in enabled:

        @server.tool(annotations=read_only)
        async def get_metric(
            scope_key: str,
            metric_key: str | None = None,
            query: str | None = None,
            limit: int = 10,
            days: int = 1,
        ) -> dict[str, object]:
            """读取授权范围内的经营指标口径、当前值与日粒度序列，不执行任意 SQL。"""
            parameters: dict[str, object] = {
                "scope_key": scope_key,
                "limit": limit,
                "days": days,
            }
            if metric_key is not None:
                parameters["metric_key"] = metric_key
            if query is not None:
                parameters["query"] = query
            return await api_client.invoke("get_metric", parameters)

    if "query_commerce_facts" in enabled:

        @server.tool(annotations=read_only)
        async def query_commerce_facts(
            scope_key: str,
            limit: int = 20,
        ) -> dict[str, object]:
            """读取授权范围的订单、退款、库存、投放、异常和血缘视图，不执行任意 SQL。"""
            return await api_client.invoke(
                "query_commerce_facts",
                {"scope_key": scope_key, "limit": limit},
            )

    if "query_customer_360" in enabled:

        @server.tool(annotations=read_only)
        async def query_customer_360(
            scope_key: str,
            customer_key: str | None = None,
            limit: int = 20,
        ) -> dict[str, object]:
            """读取授权范围内的客户汇总，或按客户键下钻交易、触点、策略边界与血缘。"""
            parameters: dict[str, object] = {"scope_key": scope_key, "limit": limit}
            if customer_key is not None:
                parameters["customer_key"] = customer_key
            return await api_client.invoke(
                "query_customer_360",
                parameters,
            )

    return server


def main() -> None:
    api_client = GatewayApiClient(load_settings())
    catalog = asyncio.run(api_client.catalog())
    items = cast(list[dict[str, object]], catalog["items"])
    enabled = frozenset(str(item["key"]) for item in items)
    unknown = enabled - ALL_TOOL_KEYS
    if unknown:
        raise RuntimeError(f"MCP 网关缺少已登记工具处理器: {sorted(unknown)}")
    create_server(api_client, enabled).run()


if __name__ == "__main__":
    main()
