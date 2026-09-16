from __future__ import annotations

import os
import sys
from collections.abc import Mapping

from mcp import StdioServerParameters

STDIO_RUNTIME_ENVIRONMENT_KEYS = (
    "ZHIXING_API_URL",
    "ZHIXING_MCP_SESSION_TOKEN",
    "ZHIXING_MCP_CLIENT_ID",
    "ZHIXING_MCP_RUN_ID",
)
STDIO_REQUIRED_ENVIRONMENT_KEYS = frozenset(
    {"ZHIXING_MCP_SESSION_TOKEN", "ZHIXING_MCP_CLIENT_ID"}
)


def build_stdio_server_parameters(
    environment: Mapping[str, str] | None = None,
) -> StdioServerParameters:
    source = os.environ if environment is None else environment
    child_environment = {
        key: value
        for key in STDIO_RUNTIME_ENVIRONMENT_KEYS
        if (value := source.get(key, "").strip())
    }
    missing = STDIO_REQUIRED_ENVIRONMENT_KEYS - child_environment.keys()
    if missing:
        raise RuntimeError(
            "ZHIXING_MCP_SESSION_TOKEN 与 ZHIXING_MCP_CLIENT_ID 必须由运行环境注入"
        )
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "zhixing_mcp.server"],
        env=child_environment,
    )
