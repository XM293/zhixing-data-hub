from __future__ import annotations

import asyncio
from typing import cast

from mcp import Client

from zhixing_mcp.api_client import GatewayApiClient
from zhixing_mcp.config import load_settings
from zhixing_mcp.server import create_server
from zhixing_mcp.stdio_runtime import build_stdio_server_parameters


async def verify() -> None:
    api_client = GatewayApiClient(load_settings())
    catalog = await api_client.catalog()
    catalog_items = cast(list[dict[str, object]], catalog["items"])
    catalog_keys = {str(item["key"]) for item in catalog_items}
    server = create_server(api_client, frozenset(catalog_keys))
    async with Client(server) as client:
        listed = await client.list_tools()
        knowledge_result = await client.call_tool(
            "search_knowledge",
            {"query": "广告预算止损条件", "limit": 3},
        )
        metric_result = await client.call_tool(
            "get_metric",
            {
                "metric_key": "gmv_today",
                "scope_key": "enterprise",
                "limit": 3,
                "days": 30,
            },
        )
    protocol_keys = {item.name for item in listed.tools}
    if catalog_keys != protocol_keys:
        raise RuntimeError(
            f"MCP 工具与 API 注册表不一致: catalog={catalog_keys}, protocol={protocol_keys}"
        )
    if not knowledge_result.structured_content or not knowledge_result.structured_content.get(
        "items"
    ):
        raise RuntimeError("MCP 知识检索没有返回数据库证据")
    if not metric_result.structured_content or not metric_result.structured_content.get("items"):
        raise RuntimeError("MCP 指标查询没有返回数据库快照")

    stdio_parameters = build_stdio_server_parameters()
    async with Client(stdio_parameters) as stdio_client:
        stdio_tools = await stdio_client.list_tools()
        stdio_result = await stdio_client.call_tool(
            "read_policy",
            {"query": "广告预算止损条件", "limit": 2},
        )
    stdio_keys = {item.name for item in stdio_tools.tools}
    if stdio_keys != protocol_keys:
        raise RuntimeError(f"STDIO 子进程工具不一致: {stdio_keys}")
    if not stdio_result.structured_content or not stdio_result.structured_content.get("items"):
        raise RuntimeError("STDIO 子进程制度读取没有返回数据库证据")

    print(
        {
            "status": "ok",
            "tools": sorted(protocol_keys),
            "evidence_items": len(knowledge_result.structured_content["items"]),
            "metric_items": len(metric_result.structured_content["items"]),
            "stdio_policy_items": len(stdio_result.structured_content["items"]),
        }
    )


if __name__ == "__main__":
    asyncio.run(verify())
