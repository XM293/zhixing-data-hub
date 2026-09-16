from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from zhixing_agent_runtime import AgentRunCancelled

from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.knowledge_provider_service import (
    knowledge_provider_operations,
    run_knowledge_provider_evaluation,
)
from zhixing_api.knowledge_schemas import (
    EvidenceSearchResponse,
    KnowledgeDocumentListResponse,
    KnowledgeIngestionListResponse,
    KnowledgeIngestionRequest,
    KnowledgeIngestionResponse,
    KnowledgeLifecycleResponse,
    KnowledgeProviderEvaluationRequest,
    KnowledgeProviderEvaluationRunView,
    KnowledgeProviderOperationsResponse,
    KnowledgeVersionDetailResponse,
    PolicyPublishRequest,
    PolicyRetireRequest,
    RoleTwinProfileView,
    TwinAnswerRequest,
    TwinAnswerResponse,
)
from zhixing_api.knowledge_service import (
    answer_with_twin,
    get_twin_profile,
    ingest_document,
    list_documents,
    list_ingestion_runs,
    publish_policy_version,
    read_effective_policy,
    read_version,
    retire_policy_version,
    search_evidence,
)
from zhixing_api.workspace_service import resolve_workspace_for_actor

router = APIRouter(prefix="/api/v1", tags=["knowledge", "role-twin"])


@router.get(
    "/knowledge/provider-operations",
    response_model=KnowledgeProviderOperationsResponse,
)
async def knowledge_provider_operation_catalog(
    request: Request,
) -> KnowledgeProviderOperationsResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "knowledge.document.read",
        request.app.state.database,
        resource_type="knowledge.provider-evaluation",
        resource_key="catalog",
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return knowledge_provider_operations(
        request.app.state.database,
        request.app.state.knowledge_providers,
        enterprise_id=actor.enterprise_id,
    )


@router.post(
    "/knowledge/provider-evaluations",
    response_model=KnowledgeProviderEvaluationRunView,
)
async def create_knowledge_provider_evaluation(
    request: Request,
    payload: KnowledgeProviderEvaluationRequest,
) -> KnowledgeProviderEvaluationRunView:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "knowledge.provider.evaluate",
        request.app.state.database,
        resource_type="knowledge.provider-evaluation",
        resource_key=payload.client_request_key,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return await run_knowledge_provider_evaluation(
        request.app.state.database,
        request.app.state.knowledge_providers,
        actor,
        payload,
    )


@router.get("/knowledge/documents", response_model=KnowledgeDocumentListResponse)
async def knowledge_documents(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    query: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> KnowledgeDocumentListResponse:
    actor = resolve_development_actor(request)
    return list_documents(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        query=query,
        status=status_filter,
        offset=offset,
        limit=limit,
    )


@router.get("/knowledge/evidence/search", response_model=EvidenceSearchResponse)
async def evidence_search(
    request: Request,
    query: str = Query(min_length=2, max_length=500),
    limit: int = Query(default=8, ge=1, le=20),
) -> EvidenceSearchResponse:
    actor = resolve_development_actor(request)
    return search_evidence(
        request.app.state.database, query, limit=limit, enterprise_id=actor.enterprise_id
    )


@router.post("/knowledge/ingestions", response_model=KnowledgeIngestionResponse)
async def knowledge_ingestion(
    request: Request,
    payload: KnowledgeIngestionRequest,
) -> KnowledgeIngestionResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "knowledge.document.ingest",
        request.app.state.database,
        resource_type="knowledge.document",
        resource_key=payload.document_key,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return ingest_document(request.app.state.database, actor, payload)


@router.get("/knowledge/ingestions", response_model=KnowledgeIngestionListResponse)
async def knowledge_ingestion_runs(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
) -> KnowledgeIngestionListResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "knowledge.document.ingest",
        request.app.state.database,
        resource_type="knowledge.ingestion",
        resource_key="runs",
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return list_ingestion_runs(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        limit=limit,
    )


@router.get(
    "/knowledge/versions/{version_id}",
    response_model=KnowledgeVersionDetailResponse,
)
async def knowledge_version(
    request: Request,
    version_id: str,
) -> KnowledgeVersionDetailResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "knowledge.document.read",
        request.app.state.database,
        resource_type="knowledge.version",
        resource_key=version_id,
    )
    return read_version(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        version_id=version_id,
    )


@router.get(
    "/knowledge/policies/{document_key}/effective",
    response_model=KnowledgeVersionDetailResponse,
)
async def effective_policy(
    request: Request,
    document_key: str,
    as_of: datetime | None = None,
) -> KnowledgeVersionDetailResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "knowledge.document.read",
        request.app.state.database,
        resource_type="knowledge.policy",
        resource_key=document_key,
    )
    return read_effective_policy(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        document_key=document_key,
        as_of=as_of or datetime.now(UTC),
    )


@router.post(
    "/knowledge/versions/{version_id}/publish",
    response_model=KnowledgeLifecycleResponse,
)
async def publish_policy(
    request: Request,
    version_id: str,
    payload: PolicyPublishRequest,
) -> KnowledgeLifecycleResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "knowledge.policy.publish",
        request.app.state.database,
        resource_type="knowledge.version",
        resource_key=version_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return publish_policy_version(
        request.app.state.database,
        actor,
        version_id=version_id,
        payload=payload,
    )


@router.post(
    "/knowledge/versions/{version_id}/retire",
    response_model=KnowledgeLifecycleResponse,
)
async def retire_policy(
    request: Request,
    version_id: str,
    payload: PolicyRetireRequest,
) -> KnowledgeLifecycleResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "knowledge.policy.publish",
        request.app.state.database,
        resource_type="knowledge.version",
        resource_key=version_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    return retire_policy_version(
        request.app.state.database,
        actor,
        version_id=version_id,
        payload=payload,
    )


@router.get("/twins/{twin_key}", response_model=RoleTwinProfileView)
async def twin_profile(request: Request, twin_key: str) -> RoleTwinProfileView:
    actor = resolve_development_actor(request)
    try:
        return get_twin_profile(request.app.state.database, twin_key, actor.enterprise_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/twins/{twin_key}/answers", response_model=TwinAnswerResponse)
async def twin_answer(
    request: Request,
    twin_key: str,
    payload: TwinAnswerRequest,
) -> TwinAnswerResponse:
    actor = resolve_development_actor(request)
    resolve_workspace_for_actor(actor, payload.workspace_key)
    require_permission(
        actor,
        "role-twin.invoke",
        request.app.state.database,
        resource_type="role-twin",
        resource_key=twin_key,
    )
    require_permission(
        actor,
        "knowledge.document.read",
        request.app.state.database,
        resource_type="knowledge.document",
        resource_key="answer-context",
    )
    try:
        return await answer_with_twin(
            request.app.state.database,
            request.app.state.settings,
            request.app.state.ai_provider,
            request.app.state.agent_runtime,
            actor=actor,
            twin_key=twin_key,
            question=payload.question.strip(),
            top_k=payload.top_k,
            scope_key=payload.scope_key,
            workspace_key=payload.workspace_key,
            runtime_session_id=payload.runtime_session_id,
        )
    except AgentRunCancelled as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
