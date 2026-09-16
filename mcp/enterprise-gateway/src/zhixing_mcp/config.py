from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    api_base_url: str
    session_token: str
    client_id: str
    timeout_seconds: float
    run_id: str | None = None


def load_settings() -> GatewaySettings:
    session_token = getenv("ZHIXING_MCP_SESSION_TOKEN", "").strip()
    client_id = getenv("ZHIXING_MCP_CLIENT_ID", "").strip().casefold()
    if not session_token or not client_id:
        raise RuntimeError(
            "ZHIXING_MCP_SESSION_TOKEN 与 ZHIXING_MCP_CLIENT_ID 必须由运行环境注入"
        )
    return GatewaySettings(
        api_base_url=getenv("ZHIXING_API_URL", "http://127.0.0.1:8000").rstrip("/"),
        session_token=session_token,
        client_id=client_id,
        timeout_seconds=float(getenv("ZHIXING_MCP_TIMEOUT_SECONDS", "15")),
        run_id=getenv("ZHIXING_MCP_RUN_ID", "").strip() or None,
    )
