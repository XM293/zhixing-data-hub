from fastapi import APIRouter, Query, Request

from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.decision_schemas import MemoryCandidateListResponse
from zhixing_api.decision_service import list_memories
from zhixing_api.memory_provider_service import (
    memory_provider_operations,
    run_memory_provider_evaluation,
)
from zhixing_api.memory_schemas import (
    ChatImportListResponse,
    ChatImportRequest,
    ChatImportResponse,
    MemoryLifecycleRequest,
    MemoryMutationResponse,
    MemoryProviderEvaluationRequest,
    MemoryProviderEvaluationRunView,
    MemoryProviderOperationsResponse,
    MemoryReviewRequest,
)
from zhixing_api.memory_service import (
    activate_memory,
    import_chat_transcript,
    list_chat_imports,
    retire_memory,
    review_memory_candidate,
)

router = APIRouter(prefix="/api/v1/memories", tags=["role-memory"])


@router.get("/provider-operations", response_model=MemoryProviderOperationsResponse)
async def provider_operations(request: Request) -> MemoryProviderOperationsResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "memory.candidate.read",
        request.app.state.database,
        resource_type="memory.provider-evaluation",
        resource_key="catalog",
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return memory_provider_operations(
        request.app.state.database,
        request.app.state.memory_providers,
        enterprise_id=actor.enterprise_id,
    )


@router.post(
    "/provider-evaluations",
    response_model=MemoryProviderEvaluationRunView,
)
async def create_provider_evaluation(
    request: Request,
    payload: MemoryProviderEvaluationRequest,
) -> MemoryProviderEvaluationRunView:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "memory.candidate.review",
        request.app.state.database,
        resource_type="memory.provider-evaluation",
        resource_key=payload.client_request_key,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return await run_memory_provider_evaluation(
        request.app.state.database,
        request.app.state.memory_providers,
        actor,
        payload,
    )


@router.get("", response_model=MemoryCandidateListResponse)
async def memories(request: Request) -> MemoryCandidateListResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "memory.candidate.read",
        request.app.state.database,
        resource_type="memory.candidate",
        resource_key="catalog",
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return list_memories(request.app.state.database, actor.enterprise_id)


@router.post("/chat-imports", response_model=ChatImportResponse)
async def import_chat(
    request: Request,
    payload: ChatImportRequest,
) -> ChatImportResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "memory.chat.ingest",
        request.app.state.database,
        resource_type="memory.chat",
        resource_key=payload.twin_key,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return import_chat_transcript(request.app.state.database, actor, payload)


@router.get("/chat-imports", response_model=ChatImportListResponse)
async def chat_imports(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
) -> ChatImportListResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "memory.chat.ingest",
        request.app.state.database,
        resource_type="memory.chat",
        resource_key="imports",
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return list_chat_imports(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        limit=limit,
    )


@router.post("/{candidate_id}/review", response_model=MemoryMutationResponse)
async def review_candidate(
    request: Request,
    candidate_id: str,
    payload: MemoryReviewRequest,
) -> MemoryMutationResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "memory.candidate.review",
        request.app.state.database,
        resource_type="memory.candidate",
        resource_key=candidate_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return review_memory_candidate(
        request.app.state.database,
        actor,
        candidate_id=candidate_id,
        payload=payload,
    )


@router.post("/{candidate_id}/activate", response_model=MemoryMutationResponse)
async def activate_candidate(
    request: Request,
    candidate_id: str,
    payload: MemoryLifecycleRequest,
) -> MemoryMutationResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "memory.candidate.review",
        request.app.state.database,
        resource_type="memory.candidate",
        resource_key=candidate_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return activate_memory(
        request.app.state.database,
        actor,
        candidate_id=candidate_id,
        payload=payload,
    )


@router.post("/{candidate_id}/retire", response_model=MemoryMutationResponse)
async def retire_candidate(
    request: Request,
    candidate_id: str,
    payload: MemoryLifecycleRequest,
) -> MemoryMutationResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "memory.approved.retire",
        request.app.state.database,
        resource_type="memory.approved",
        resource_key=candidate_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return retire_memory(
        request.app.state.database,
        actor,
        candidate_id=candidate_id,
        payload=payload,
    )
