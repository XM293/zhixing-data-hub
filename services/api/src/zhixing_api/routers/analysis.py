from fastapi import APIRouter, HTTPException, Query, Request, status
from zhixing_jobs import JOB_EXECUTION_TOKEN_HEADER, WORKER_ID_HEADER

from zhixing_api.action_schemas import (
    BusinessAnalysisActionProposalRequest,
    BusinessAnalysisActionProposalResponse,
)
from zhixing_api.action_service import create_business_analysis_action_proposals
from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.analysis_schemas import (
    AnalysisStudioResponse,
    BusinessAnalysisRunRequest,
    BusinessAnalysisRunResponse,
)
from zhixing_api.analysis_service import (
    list_analysis_studio,
    resolve_analysis_scope,
    run_business_analysis,
)
from zhixing_api.data_selection import require_selected_data_scope
from zhixing_api.review_schedule_schemas import (
    StoreReviewPlanActionRequest,
    StoreReviewPlanMutationResponse,
    StoreReviewPlanRequest,
    StoreReviewScheduleResponse,
)
from zhixing_api.review_schedule_service import (
    act_on_review_plan,
    create_review_plan,
    execute_review_job,
    list_review_schedule,
)
from zhixing_api.workspace_service import resolve_workspace_for_actor

router = APIRouter(prefix="/api/v1/analysis", tags=["business-analysis"])


@router.get("/studio", response_model=AnalysisStudioResponse)
async def analysis_studio(
    request: Request,
    scope_key: str | None = Query(default=None, min_length=2, max_length=160),
) -> AnalysisStudioResponse:
    actor = resolve_development_actor(request)
    scope = resolve_analysis_scope(request.app.state.database, actor, scope_key)
    require_permission(
        actor,
        "analysis.read",
        request.app.state.database,
        resource_type="business-analysis",
        resource_key=scope.key,
        scope_type=scope.type,
        scope_id=actor.enterprise_id if scope.type == "enterprise" else scope.key,
    )
    return list_analysis_studio(
        request.app.state.database,
        actor,
        scope_key=scope.key,
    )


@router.post("/store-reviews", response_model=BusinessAnalysisRunResponse)
async def create_store_review(
    request: Request,
    payload: BusinessAnalysisRunRequest,
) -> BusinessAnalysisRunResponse:
    actor = resolve_development_actor(request)
    resolve_workspace_for_actor(actor, payload.workspace_key)
    scope = resolve_analysis_scope(request.app.state.database, actor, payload.scope_key)
    require_selected_data_scope(request.app.state.database, actor, scope.key)
    scope_id = actor.enterprise_id if scope.type == "enterprise" else scope.key
    require_permission(
        actor,
        "analysis.run",
        request.app.state.database,
        resource_type="business-analysis",
        resource_key=scope.key,
        scope_type=scope.type,
        scope_id=scope_id,
    )
    require_permission(
        actor,
        "metric.query.execute",
        request.app.state.database,
        resource_type="metric-query",
        resource_key=f"analysis:{scope.key}",
        scope_type=scope.type,
        scope_id=scope_id,
    )
    return await run_business_analysis(
        request.app.state.database,
        request.app.state.settings,
        request.app.state.ai_provider,
        actor,
        scope=scope,
        window_days=payload.window_days,
        client_request_key=payload.client_request_key,
        workspace_key=payload.workspace_key,
    )


@router.post(
    "/runs/{analysis_run_id}/action-proposals",
    response_model=BusinessAnalysisActionProposalResponse,
)
async def create_analysis_action_proposals(
    request: Request,
    analysis_run_id: str,
    payload: BusinessAnalysisActionProposalRequest,
) -> BusinessAnalysisActionProposalResponse:
    actor = resolve_development_actor(request)
    try:
        return create_business_analysis_action_proposals(
            request.app.state.database,
            analysis_run_id=analysis_run_id,
            actor=actor,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/review-plans", response_model=StoreReviewScheduleResponse)
async def review_plans(request: Request) -> StoreReviewScheduleResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "analysis.schedule.read",
        request.app.state.database,
        resource_type="analysis-schedule",
        resource_key="overview",
    )
    return list_review_schedule(request.app.state.database, actor)


@router.post("/review-plans", response_model=StoreReviewPlanMutationResponse)
async def create_review_plan_endpoint(
    request: Request,
    payload: StoreReviewPlanRequest,
) -> StoreReviewPlanMutationResponse:
    actor = resolve_development_actor(request)
    scope = resolve_analysis_scope(request.app.state.database, actor, payload.scope_key)
    scope_id = actor.enterprise_id if scope.type == "enterprise" else scope.key
    require_permission(
        actor,
        "analysis.schedule.manage",
        request.app.state.database,
        resource_type="analysis-schedule",
        resource_key=scope.key,
        scope_type=scope.type,
        scope_id=scope_id,
    )
    return create_review_plan(request.app.state.database, actor, scope, payload)


@router.post(
    "/review-plans/{plan_key}/actions",
    response_model=StoreReviewPlanMutationResponse,
)
async def act_on_review_plan_endpoint(
    request: Request,
    plan_key: str,
    payload: StoreReviewPlanActionRequest,
) -> StoreReviewPlanMutationResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "analysis.schedule.manage",
        request.app.state.database,
        resource_type="analysis-schedule",
        resource_key=plan_key,
    )
    return act_on_review_plan(
        request.app.state.database,
        actor,
        plan_key=plan_key,
        payload=payload,
    )


@router.post("/internal/jobs/{job_id}/execute")
async def execute_review_job_endpoint(request: Request, job_id: str) -> dict[str, object]:
    return await execute_review_job(
        request.app.state.database,
        request.app.state.settings,
        request.app.state.ai_provider,
        job_id=job_id,
        worker_id=request.headers.get(WORKER_ID_HEADER),
        execution_token=request.headers.get(JOB_EXECUTION_TOKEN_HEADER),
        request_id=getattr(request.state, "request_id", ""),
        run_id=getattr(request.state, "run_id", ""),
    )
