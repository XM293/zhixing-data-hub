from fastapi import APIRouter, Request

from zhixing_api.actor_context import ActorContext, require_permission, resolve_development_actor
from zhixing_api.role_twin_test_schemas import (
    RoleTwinTestMutationResponse,
    RoleTwinTestReviewRequest,
    RoleTwinTestRunRequest,
    RoleTwinTestStudioResponse,
)
from zhixing_api.role_twin_test_service import (
    list_role_twin_test_studio,
    review_role_twin_test_run,
    run_role_twin_test,
)

router = APIRouter(prefix="/api/v1", tags=["role-twin-tests"])


@router.get("/role-twin-test-studio", response_model=RoleTwinTestStudioResponse)
async def role_twin_test_studio(request: Request) -> RoleTwinTestStudioResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "role-twin.read", "role-twin-test", "studio")
    return list_role_twin_test_studio(request.app.state.database, actor)


@router.post(
    "/role-twin-test-cases/{case_key}/runs",
    response_model=RoleTwinTestMutationResponse,
)
async def role_twin_test_run(
    request: Request,
    case_key: str,
    payload: RoleTwinTestRunRequest,
) -> RoleTwinTestMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "role-twin.invoke", "role-twin", payload.twin_key)
    _authorize(
        request,
        actor,
        "knowledge.document.read",
        "knowledge.document",
        "role-twin-test-context",
    )
    return await run_role_twin_test(
        request.app.state.database,
        request.app.state.settings,
        request.app.state.ai_provider,
        request.app.state.agent_runtime,
        actor,
        case_key=case_key,
        twin_key=payload.twin_key,
    )


@router.post(
    "/role-twin-test-runs/{test_run_id}/reviews",
    response_model=RoleTwinTestMutationResponse,
)
async def role_twin_test_review(
    request: Request,
    test_run_id: str,
    payload: RoleTwinTestReviewRequest,
) -> RoleTwinTestMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(
        request,
        actor,
        "role-twin.configure",
        "role-twin-test-run",
        test_run_id,
    )
    return review_role_twin_test_run(
        request.app.state.database,
        actor,
        test_run_id=test_run_id,
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
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
