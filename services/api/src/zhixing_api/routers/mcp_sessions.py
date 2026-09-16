from fastapi import APIRouter, Request

from zhixing_api.actor_context import resolve_development_actor
from zhixing_api.mcp_schemas import (
    McpSessionCreateRequest,
    McpSessionCreateResponse,
    McpSessionListResponse,
    McpSessionRevokeRequest,
    McpSessionView,
)
from zhixing_api.mcp_session_service import (
    create_mcp_session,
    list_mcp_sessions,
    revoke_mcp_session,
)

router = APIRouter(prefix="/api/v1/mcp/sessions", tags=["mcp", "auth"])


@router.post("", response_model=McpSessionCreateResponse)
async def create_gateway_session(
    request: Request,
    payload: McpSessionCreateRequest,
) -> McpSessionCreateResponse:
    return create_mcp_session(
        request.app.state.database,
        resolve_development_actor(request),
        payload,
    )


@router.get("", response_model=McpSessionListResponse)
async def list_gateway_sessions(request: Request) -> McpSessionListResponse:
    return list_mcp_sessions(
        request.app.state.database,
        resolve_development_actor(request),
    )


@router.post("/{session_id}/revoke", response_model=McpSessionView)
async def revoke_gateway_session(
    request: Request,
    session_id: str,
    payload: McpSessionRevokeRequest,
) -> McpSessionView:
    return revoke_mcp_session(
        request.app.state.database,
        resolve_development_actor(request),
        session_id,
        payload,
    )
