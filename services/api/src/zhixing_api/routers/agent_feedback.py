from fastapi import APIRouter, Request

from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.agent_feedback_schemas import (
    AgentFeedbackCaseActionRequest,
    AgentFeedbackStudioResponse,
    AgentFeedbackSubmitRequest,
    AgentRunFeedbackResponse,
)
from zhixing_api.agent_feedback_service import (
    act_on_handoff_case,
    get_agent_run_feedback,
    list_agent_feedback_studio,
    submit_agent_run_feedback,
)

router = APIRouter(prefix="/api/v1", tags=["agent-feedback"])


@router.get("/agent-runs/{agent_run_id}/feedback", response_model=AgentRunFeedbackResponse)
async def agent_run_feedback(request: Request, agent_run_id: str) -> AgentRunFeedbackResponse:
    actor = resolve_development_actor(request)
    permission = (
        "agent-feedback.review"
        if "agent-feedback.review" in actor.permissions
        else "agent-feedback.submit"
    )
    require_permission(
        actor,
        permission,
        request.app.state.database,
        resource_type="agent-run",
        resource_key=agent_run_id,
    )
    return get_agent_run_feedback(request.app.state.database, actor, agent_run_id)


@router.post("/agent-runs/{agent_run_id}/feedback", response_model=AgentRunFeedbackResponse)
async def submit_feedback(
    request: Request,
    agent_run_id: str,
    payload: AgentFeedbackSubmitRequest,
) -> AgentRunFeedbackResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "agent-feedback.submit",
        request.app.state.database,
        resource_type="agent-run",
        resource_key=agent_run_id,
    )
    return submit_agent_run_feedback(
        request.app.state.database,
        actor,
        agent_run_id,
        payload,
    )


@router.get("/agent-feedback/studio", response_model=AgentFeedbackStudioResponse)
async def feedback_studio(request: Request) -> AgentFeedbackStudioResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "agent-feedback.review",
        request.app.state.database,
        resource_type="agent-feedback",
        resource_key="studio",
    )
    return list_agent_feedback_studio(request.app.state.database, actor)


@router.get("/agent-feedback/mine", response_model=AgentFeedbackStudioResponse)
async def my_feedback(request: Request) -> AgentFeedbackStudioResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "agent-feedback.submit",
        request.app.state.database,
        resource_type="agent-feedback",
        resource_key="mine",
    )
    return list_agent_feedback_studio(
        request.app.state.database,
        actor,
        opened_by_principal_id=actor.principal_id,
    )


@router.post(
    "/agent-feedback/cases/{case_id}/actions",
    response_model=AgentRunFeedbackResponse,
)
async def feedback_case_action(
    request: Request,
    case_id: str,
    payload: AgentFeedbackCaseActionRequest,
) -> AgentRunFeedbackResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "agent-feedback.review",
        request.app.state.database,
        resource_type="agent-feedback-case",
        resource_key=case_id,
    )
    return act_on_handoff_case(
        request.app.state.database,
        actor,
        case_id,
        payload,
    )
