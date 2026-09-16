from __future__ import annotations

from typing import cast
from uuid import uuid4

import httpx

from zhixing_mcp.config import GatewaySettings


class ToolGatewayError(RuntimeError):
    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status_code = status_code


class GatewayApiClient:
    def __init__(
        self,
        settings: GatewaySettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.run_id = settings.run_id or f"run_mcp_{uuid4().hex}"

    async def catalog(self) -> dict[str, object]:
        return await self._request("GET", "/api/v1/tools/catalog")

    async def invoke(self, tool_key: str, parameters: dict[str, object]) -> dict[str, object]:
        payload = await self._request(
            "POST",
            f"/api/v1/tools/{tool_key}/invoke",
            json={"parameters": parameters},
        )
        output = dict(cast(dict[str, object], payload["output"]))
        output["_zhixing"] = {
            "invocation_id": payload["invocation_id"],
            "actor_key": payload["actor_key"],
            "request_id": payload["request_id"],
            "run_id": payload["run_id"],
            "duration_ms": payload["duration_ms"],
            "authentication_method": payload["authentication_method"],
            "permission_set_version": payload["permission_set_version"],
            "session_permission_set_version": payload["session_permission_set_version"],
            "permission_set_version_changed": payload["permission_set_version_changed"],
            "gateway_session_id": payload["gateway_session_id"],
            "agent_run_id": payload["agent_run_id"],
        }
        return output

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        headers = {
            "X-Zhixing-MCP-Session": self.settings.session_token,
            "X-Zhixing-MCP-Client-ID": self.settings.client_id,
            "X-Request-ID": f"req_mcp_{uuid4().hex}",
            "X-Run-ID": self.run_id,
        }
        async with httpx.AsyncClient(
            base_url=self.settings.api_base_url,
            headers=headers,
            timeout=self.settings.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.request(method, path, json=json)
        payload = cast(dict[str, object], response.json())
        if response.is_error:
            error = cast(dict[str, object], payload.get("error", {}))
            raise ToolGatewayError(
                code=str(error.get("code", "tool.gateway_failed")),
                message=str(error.get("message", "企业工具网关调用失败")),
                status_code=response.status_code,
            )
        return payload
