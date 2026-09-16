from fastapi import APIRouter, Request

from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.mcp_session_service import resolve_tool_request_context
from zhixing_api.tool_schemas import (
    ToolAdminOverviewResponse,
    ToolCatalogResponse,
    ToolInvokeRequest,
    ToolInvokeResponse,
)
from zhixing_api.tool_service import invoke_tool, list_tool_catalog, tool_admin_overview

router = APIRouter(prefix="/api/v1/tools", tags=["tools", "mcp"])


@router.get("/catalog", response_model=ToolCatalogResponse)
async def tool_catalog(request: Request) -> ToolCatalogResponse:
    context = resolve_tool_request_context(request)
    actor = context.actor
    require_permission(
        actor,
        "platform.navigation.read",
        request.app.state.database,
        resource_type="tool_catalog",
        resource_key="active-tools",
    )
    return list_tool_catalog(
        request.app.state.database,
        actor,
        allowed_tool_keys=context.allowed_tool_keys,
    )


@router.get("/admin/overview", response_model=ToolAdminOverviewResponse)
async def tool_admin(request: Request) -> ToolAdminOverviewResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "identity.access.manage",
        request.app.state.database,
        resource_type="tool_registry",
        resource_key=actor.enterprise_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return tool_admin_overview(request.app.state.database, enterprise_id=actor.enterprise_id)


@router.post("/{tool_key}/invoke", response_model=ToolInvokeResponse)
async def tool_invoke(
    request: Request,
    tool_key: str,
    payload: ToolInvokeRequest,
) -> ToolInvokeResponse:
    context = resolve_tool_request_context(request)
    actor = context.actor
    return await invoke_tool(
        request.app.state.database,
        request.app.state.settings,
        request.app.state.ai_provider,
        actor,
        tool_key=tool_key,
        parameters=payload.parameters,
        gateway_session_id=context.gateway_session_id,
        agent_run_id=context.agent_run_id,
        session_permission_set_version=context.session_permission_set_version,
        allowed_tool_keys=context.allowed_tool_keys,
    )
