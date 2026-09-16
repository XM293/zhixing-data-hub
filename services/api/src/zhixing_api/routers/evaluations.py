from fastapi import APIRouter, Request

from zhixing_api.actor_context import ActorContext, require_permission, resolve_development_actor
from zhixing_api.evaluation_schemas import (
    EvaluationCandidateActionRequest,
    EvaluationCandidateMutationResponse,
    EvaluationRunMutationResponse,
    EvaluationRunRequest,
    EvaluationStudioResponse,
)
from zhixing_api.evaluation_service import (
    list_evaluation_studio,
    review_evaluation_candidate,
    run_evaluation_suite,
)

router = APIRouter(prefix="/api/v1", tags=["evaluations"])


@router.get("/evaluations/studio", response_model=EvaluationStudioResponse)
async def evaluation_studio(request: Request) -> EvaluationStudioResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "evaluation.read", "evaluation", "studio")
    return list_evaluation_studio(request.app.state.database, actor)


@router.post(
    "/evaluation-suites/{suite_key}/runs",
    response_model=EvaluationRunMutationResponse,
)
async def evaluation_run(
    request: Request,
    suite_key: str,
    payload: EvaluationRunRequest,
) -> EvaluationRunMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "evaluation.run", "evaluation-suite", suite_key)
    return await run_evaluation_suite(
        request.app.state.database,
        request.app.state.settings,
        request.app.state.ai_provider,
        request.app.state.agent_runtime,
        actor,
        suite_key=suite_key,
        client_request_key=payload.client_request_key,
        case_keys=payload.case_keys,
    )


@router.post(
    "/evaluation-candidates/{candidate_id}/actions",
    response_model=EvaluationCandidateMutationResponse,
)
async def evaluation_candidate_action(
    request: Request,
    candidate_id: str,
    payload: EvaluationCandidateActionRequest,
) -> EvaluationCandidateMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "evaluation.manage", "evaluation-candidate", candidate_id)
    return review_evaluation_candidate(
        request.app.state.database,
        actor,
        candidate_id=candidate_id,
        payload=payload,
    )


def _authorize(
    request: Request,
    actor: ActorContext,
    permission: str,
    resource_type: str,
    resource_key: str,
) -> None:
    require_permission(
        actor,
        permission,
        request.app.state.database,
        resource_type=resource_type,
        resource_key=resource_key,
    )
