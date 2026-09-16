from fastapi import APIRouter, Query, Request

from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.customer_service_schemas import (
    CustomerServiceDraftRequest,
    CustomerServiceHandoffRequest,
    CustomerServiceMutationResponse,
    CustomerServiceSandboxSendRequest,
    CustomerServiceStudioResponse,
)
from zhixing_api.customer_service_service import (
    generate_customer_service_draft,
    handoff_customer_service_conversation,
    list_customer_service_studio,
    send_customer_service_sandbox_reply,
)

router = APIRouter(prefix="/api/v1/customer-service", tags=["customer-service"])


@router.get("/studio", response_model=CustomerServiceStudioResponse)
async def customer_service_studio(
    request: Request,
    conversation_key: str | None = Query(default=None, min_length=3, max_length=120),
) -> CustomerServiceStudioResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "customer-service.conversation.read",
        request.app.state.database,
        resource_type="customer-service-queue",
        resource_key=conversation_key or "assigned-queue",
    )
    return list_customer_service_studio(
        request.app.state.database,
        actor,
        conversation_key=conversation_key,
    )


@router.post(
    "/conversations/{conversation_key}/drafts",
    response_model=CustomerServiceMutationResponse,
)
async def create_customer_service_draft(
    request: Request,
    conversation_key: str,
    payload: CustomerServiceDraftRequest,
) -> CustomerServiceMutationResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "customer-service.reply.draft",
        request.app.state.database,
        resource_type="customer-service-conversation",
        resource_key=conversation_key,
    )
    return await generate_customer_service_draft(
        request.app.state.database,
        request.app.state.settings,
        request.app.state.ai_provider,
        actor,
        conversation_key=conversation_key,
        client_request_key=payload.client_request_key,
    )


@router.post(
    "/conversations/{conversation_key}/handoffs",
    response_model=CustomerServiceMutationResponse,
)
async def create_customer_service_handoff(
    request: Request,
    conversation_key: str,
    payload: CustomerServiceHandoffRequest,
) -> CustomerServiceMutationResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "customer-service.handoff.create",
        request.app.state.database,
        resource_type="customer-service-conversation",
        resource_key=conversation_key,
    )
    return handoff_customer_service_conversation(
        request.app.state.database,
        actor,
        conversation_key=conversation_key,
        reason=payload.reason,
        client_request_key=payload.client_request_key,
    )


@router.post(
    "/drafts/{draft_id}/sandbox-send",
    response_model=CustomerServiceMutationResponse,
)
async def send_customer_service_reply(
    request: Request,
    draft_id: str,
    payload: CustomerServiceSandboxSendRequest,
) -> CustomerServiceMutationResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "customer-service.reply.send",
        request.app.state.database,
        resource_type="customer-service-reply-draft",
        resource_key=draft_id,
    )
    return send_customer_service_sandbox_reply(
        request.app.state.database,
        actor,
        draft_id=draft_id,
        final_body=payload.final_body,
        note=payload.note,
        client_request_key=payload.client_request_key,
    )
