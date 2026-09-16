from __future__ import annotations

from typing import cast

import httpx
import pytest
from mcp import Client

from zhixing_mcp.api_client import GatewayApiClient, ToolGatewayError
from zhixing_mcp.config import GatewaySettings
from zhixing_mcp.server import create_server
from zhixing_mcp.stdio_runtime import build_stdio_server_parameters


def make_client(handler: httpx.AsyncBaseTransport) -> GatewayApiClient:
    return GatewayApiClient(
        GatewaySettings(
            api_base_url="http://api.test",
            session_token="mcp-test-session-token",
            client_id="codex-test",
            timeout_seconds=2,
            run_id="run_mcp_test1234567890",
        ),
        transport=handler,
    )


def test_stdio_parameters_forward_only_gateway_runtime_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parameters = build_stdio_server_parameters(
        {
            "ZHIXING_API_URL": "http://api.test",
            "ZHIXING_MCP_SESSION_TOKEN": "stdio-session-secret",
            "ZHIXING_MCP_CLIENT_ID": "codex-stdio-test",
            "ZHIXING_MCP_RUN_ID": "run_stdio_test1234567890",
            "UNRELATED_SECRET": "must-not-reach-child",
            "PATH": "must-be-provided-by-sdk-default-environment",
        }
    )

    assert parameters.env == {
        "ZHIXING_API_URL": "http://api.test",
        "ZHIXING_MCP_SESSION_TOKEN": "stdio-session-secret",
        "ZHIXING_MCP_CLIENT_ID": "codex-stdio-test",
        "ZHIXING_MCP_RUN_ID": "run_stdio_test1234567890",
    }
    assert "UNRELATED_SECRET" not in parameters.env
    assert "PATH" not in parameters.env
    captured = capsys.readouterr()
    assert "stdio-session-secret" not in captured.out
    assert "stdio-session-secret" not in captured.err


@pytest.mark.anyio
async def test_mcp_server_lists_five_tools_and_propagates_trace_metadata() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "invocation_id": "tool_invocation_test",
                "actor_key": "principal-ceo-lin",
                "request_id": "req_test1234567890",
                "run_id": "run_test1234567890",
                "duration_ms": 3,
                "authentication_method": "mcp-session",
                "permission_set_version": "access-current",
                "session_permission_set_version": "access-issued",
                "permission_set_version_changed": True,
                "gateway_session_id": "mcp_session_test",
                "agent_run_id": "agent_run_test",
                "output": {"query": "退款率", "items": [{"document_key": "policy-kpi"}]},
            },
        )

    server = create_server(make_client(httpx.MockTransport(handler)))
    async with Client(server) as client:
        listed = await client.list_tools()
        result = await client.call_tool(
            "search_knowledge",
            {"query": "退款率", "limit": 3},
        )

    assert {item.name for item in listed.tools} == {
        "get_metric",
        "query_commerce_facts",
        "query_customer_360",
        "read_policy",
        "search_knowledge",
    }
    assert all(item.annotations is not None for item in listed.tools)
    assert all(item.annotations.read_only_hint is True for item in listed.tools if item.annotations)
    assert all(
        item.annotations.idempotent_hint is True for item in listed.tools if item.annotations
    )
    assert all(
        item.annotations.open_world_hint is False for item in listed.tools if item.annotations
    )
    structured = cast(dict[str, object], result.structured_content)
    assert structured["query"] == "退款率"
    trace = cast(dict[str, object], structured["_zhixing"])
    assert trace["invocation_id"] == "tool_invocation_test"
    assert captured[0].headers["X-Zhixing-MCP-Session"] == "mcp-test-session-token"
    assert captured[0].headers["X-Zhixing-MCP-Client-ID"] == "codex-test"
    assert captured[0].headers["X-Run-ID"] == "run_mcp_test1234567890"
    assert captured[0].headers["X-Request-ID"].startswith("req_mcp_")
    assert "X-Zhixing-Demo-Actor" not in captured[0].headers
    assert trace["gateway_session_id"] == "mcp_session_test"
    assert trace["agent_run_id"] == "agent_run_test"
    assert trace["permission_set_version_changed"] is True
    assert b"principal_id" not in captured[0].content


@pytest.mark.anyio
async def test_gateway_surfaces_api_authorization_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": "authorization.scope_denied",
                    "message": "当前身份不包含企业范围",
                }
            },
        )

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(ToolGatewayError) as raised:
        await client.invoke(
            "get_metric",
            {"metric_key": "gmv_today", "scope_key": "enterprise"},
        )

    assert raised.value.code == "authorization.scope_denied"
    assert raised.value.status_code == 403


@pytest.mark.anyio
async def test_mcp_server_projects_only_session_allowed_tools() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    server = create_server(
        make_client(httpx.MockTransport(handler)),
        frozenset({"get_metric", "search_knowledge"}),
    )
    async with Client(server) as client:
        listed = await client.list_tools()

    assert {item.name for item in listed.tools} == {"get_metric", "search_knowledge"}
