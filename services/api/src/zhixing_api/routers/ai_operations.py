from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.ai_operations_schemas import (
    AgentRuntimeCancelResponse,
    AgentRuntimeProbeRunView,
    AgentRuntimeSessionDetailResponse,
    AIOperationsOverviewResponse,
    AIProviderProbeRequest,
    AIProviderProbeRunView,
)
from zhixing_api.ai_operations_service import (
    agent_runtime_session_detail,
    ai_operations_overview,
    cancel_agent_runtime_session,
    resolve_agent_runtime_approval,
    run_agent_runtime_probe,
    run_provider_probe,
)


class RuntimeApprovalRequest(BaseModel):
    decision: str

router = APIRouter(prefix="/api/v1/ai-operations", tags=["ai-operations"])


def _require_runtime_management(request: Request, session_id: str) -> str:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "ai.provider.manage",
        request.app.state.database,
        resource_type="agent-runtime-session",
        resource_key=session_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return actor.enterprise_id


@router.get("/overview", response_model=AIOperationsOverviewResponse)
async def operations_overview(request: Request) -> AIOperationsOverviewResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "ai.provider.manage",
        request.app.state.database,
        resource_type="ai-provider",
        resource_key=actor.enterprise_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return ai_operations_overview(
        request.app.state.database,
        request.app.state.settings,
        enterprise_id=actor.enterprise_id,
    )


@router.post("/probes", response_model=AIProviderProbeRunView)
async def create_provider_probe(
    request: Request,
    payload: AIProviderProbeRequest,
) -> AIProviderProbeRunView:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "ai.provider.manage",
        request.app.state.database,
        resource_type="ai-provider-probe",
        resource_key=payload.model or request.app.state.settings.ai_model,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return await run_provider_probe(
        request.app.state.database,
        request.app.state.settings,
        request.app.state.ai_provider,
        actor,
        model=payload.model,
    )


@router.post("/runtime-probes", response_model=AgentRuntimeProbeRunView)
async def create_runtime_probe(request: Request) -> AgentRuntimeProbeRunView:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "ai.provider.manage",
        request.app.state.database,
        resource_type="agent-runtime-probe",
        resource_key="codex-app-server",
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return await run_agent_runtime_probe(
        request.app.state.database,
        request.app.state.settings,
        request.app.state.agent_runtime,
        actor,
    )


@router.get(
    "/runtime-sessions/{session_id}",
    response_model=AgentRuntimeSessionDetailResponse,
)
async def runtime_session_detail(
    request: Request,
    session_id: str,
) -> AgentRuntimeSessionDetailResponse:
    enterprise_id = _require_runtime_management(request, session_id)
    try:
        return agent_runtime_session_detail(
            request.app.state.database,
            enterprise_id=enterprise_id,
            runtime_session_id=session_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/runtime-sessions/{session_id}/cancel",
    response_model=AgentRuntimeCancelResponse,
)
async def cancel_runtime_session(
    request: Request,
    session_id: str,
) -> AgentRuntimeCancelResponse:
    enterprise_id = _require_runtime_management(request, session_id)
    try:
        return await cancel_agent_runtime_session(
            request.app.state.database,
            request.app.state.agent_runtime,
            enterprise_id=enterprise_id,
            runtime_session_id=session_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/runtime-sessions/{session_id}/approval",
    response_model=AgentRuntimeCancelResponse,
)
async def resolve_runtime_approval(
    request: Request,
    session_id: str,
    payload: RuntimeApprovalRequest,
) -> AgentRuntimeCancelResponse:
    enterprise_id = _require_runtime_management(request, session_id)
    try:
        return await resolve_agent_runtime_approval(
            request.app.state.database,
            request.app.state.agent_runtime,
            enterprise_id=enterprise_id,
            runtime_session_id=session_id,
            decision=payload.decision,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
