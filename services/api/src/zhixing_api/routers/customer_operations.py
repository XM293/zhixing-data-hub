from fastapi import APIRouter, Query, Request

from zhixing_api.action_schemas import (
    CustomerOperationActionProposalRequest,
    CustomerOperationActionProposalResponse,
)
from zhixing_api.action_service import create_customer_operation_action_proposals
from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.customer_operation_schemas import (
    CustomerOperationRunRequest,
    CustomerOperationRunResponse,
    CustomerOperationStudioResponse,
)
from zhixing_api.customer_operation_service import (
    list_customer_operation_studio,
    run_customer_operation_plan,
)

router = APIRouter(prefix="/api/v1/customer-operations", tags=["customer-operations"])


@router.get("/studio", response_model=CustomerOperationStudioResponse)
async def customer_operation_studio(
    request: Request,
    scope_key: str = Query(min_length=1, max_length=160),
    customer_key: str = Query(min_length=1, max_length=160),
) -> CustomerOperationStudioResponse:
    actor = resolve_development_actor(request)
    scope_type = "enterprise" if scope_key == "enterprise" else "store"
    scope_id = actor.enterprise_id if scope_type == "enterprise" else scope_key
    require_permission(
        actor,
        "customer.profile.read",
        request.app.state.database,
        resource_type="customer-operation",
        resource_key=f"customer-operation:{scope_key}:{customer_key}",
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return list_customer_operation_studio(
        request.app.state.database,
        actor,
        scope_key=scope_key,
        customer_key=customer_key,
    )


@router.post("/plans", response_model=CustomerOperationRunResponse)
async def create_customer_operation_plan(
    request: Request,
    payload: CustomerOperationRunRequest,
) -> CustomerOperationRunResponse:
    actor = resolve_development_actor(request)
    scope_type = "enterprise" if payload.scope_key == "enterprise" else "store"
    scope_id = actor.enterprise_id if scope_type == "enterprise" else payload.scope_key
    resource_key = f"customer-operation:{payload.scope_key}:{payload.customer_key}"
    require_permission(
        actor,
        "customer.profile.read",
        request.app.state.database,
        resource_type="customer-operation",
        resource_key=resource_key,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    require_permission(
        actor,
        "analysis.run",
        request.app.state.database,
        resource_type="customer-operation",
        resource_key=resource_key,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return await run_customer_operation_plan(
        request.app.state.database,
        request.app.state.settings,
        request.app.state.ai_provider,
        actor,
        scope_key=payload.scope_key,
        customer_key=payload.customer_key,
        objective=payload.objective,
        client_request_key=payload.client_request_key,
    )


@router.post(
    "/plans/{operation_id}/action-proposals",
    response_model=CustomerOperationActionProposalResponse,
)
async def create_action_proposals_from_customer_operation(
    request: Request,
    operation_id: str,
    payload: CustomerOperationActionProposalRequest,
) -> CustomerOperationActionProposalResponse:
    actor = resolve_development_actor(request)
    return create_customer_operation_action_proposals(
        request.app.state.database,
        operation_id=operation_id,
        actor=actor,
        payload=payload,
    )
