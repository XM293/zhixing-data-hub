from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel


class PageView(ApiModel):
    offset: int
    limit: int
    total: int


class KnowledgeVersionView(ApiModel):
    id: str
    version_label: str
    version_number: int
    status: str
    effective_from: datetime | None
    effective_until: datetime | None
    published_at: datetime | None
    change_summary: str
    chunk_count: int


class KnowledgeDocumentView(ApiModel):
    id: str
    key: str
    title: str
    document_type: str
    knowledge_space: str
    source_type: str
    owner: str
    tags: list[str]
    status: str
    content_hash: str
    created_at: datetime
    updated_at: datetime
    versions: list[KnowledgeVersionView]


class KnowledgeDocumentListResponse(ApiModel):
    schema_version: Literal[1] = 1
    page: PageView
    status_counts: dict[str, int]
    version_count: int
    chunk_count: int
    items: list[KnowledgeDocumentView]
    generated_at: datetime


class KnowledgeConflictView(ApiModel):
    conflict_type: str
    severity: Literal["warning", "critical"]
    related_version_id: str
    related_version_label: str
    heading: str
    locator: str
    summary: str


class KnowledgeIngestionRequest(ApiModel):
    document_key: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    title: str = Field(min_length=2, max_length=240)
    document_type: Literal["policy", "manual", "decision", "handbook"]
    knowledge_space: str = Field(min_length=2, max_length=120)
    owner: str = Field(min_length=2, max_length=160)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source_filename: str = Field(min_length=1, max_length=260)
    version_label: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=20, max_length=500_000)
    change_summary: str = Field(min_length=2, max_length=1000)


class KnowledgeIngestionRunView(ApiModel):
    id: str
    document_key: str | None
    document_title: str | None
    version_id: str | None
    version_label: str | None
    actor_name: str
    source_filename: str
    content_hash: str
    parser_provider: str
    status: Literal["completed", "duplicate", "failed"]
    chunk_count: int
    warnings: list[KnowledgeConflictView]
    error_code: str | None
    request_id: str
    run_id: str
    created_at: datetime
    finished_at: datetime


class KnowledgeIngestionResponse(ApiModel):
    schema_version: Literal[1] = 1
    duplicate: bool
    document: KnowledgeDocumentView
    version: KnowledgeVersionView
    ingestion_run: KnowledgeIngestionRunView


class KnowledgeIngestionListResponse(ApiModel):
    schema_version: Literal[1] = 1
    stats: dict[str, int]
    items: list[KnowledgeIngestionRunView]
    generated_at: datetime


class KnowledgeChunkView(ApiModel):
    id: str
    chunk_key: str
    sequence: int
    heading: str
    locator: str
    content: str
    token_estimate: int
    index_status: str


class KnowledgeVersionDetailResponse(ApiModel):
    schema_version: Literal[1] = 1
    document: KnowledgeDocumentView
    version: KnowledgeVersionView
    content: str
    chunks: list[KnowledgeChunkView]
    lifecycle_events: list[dict[str, object]]
    resolved_at: datetime


class PolicyPublishRequest(ApiModel):
    effective_from: datetime
    reason: str = Field(min_length=2, max_length=1000)


class PolicyRetireRequest(ApiModel):
    reason: str = Field(min_length=2, max_length=1000)


class KnowledgeLifecycleResponse(ApiModel):
    schema_version: Literal[1] = 1
    document_key: str
    version: KnowledgeVersionView
    event_id: str
    event_type: Literal["published", "retired"]
    idempotent: bool
    occurred_at: datetime


class EvidenceView(ApiModel):
    chunk_id: str
    document_key: str
    document_title: str
    version_id: str
    version_label: str
    version_status: str
    effective_from: datetime | None
    heading: str
    locator: str
    excerpt: str
    score: float


class EvidenceSearchResponse(ApiModel):
    schema_version: Literal[1] = 1
    query: str
    retrieval_provider: str
    items: list[EvidenceView]
    generated_at: datetime


class KnowledgeProviderEvaluationRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    provider_keys: list[Literal["weknora", "ragflow", "openviking"]] = Field(
        min_length=1,
        max_length=3,
    )
    top_k: int = Field(default=3, ge=1, le=10)


class KnowledgeProviderDescriptorView(ApiModel):
    key: str
    label: str
    protocol: str
    mode: str
    endpoint_fingerprint: str
    authentication_configured: bool


class KnowledgeBenchmarkCaseView(ApiModel):
    key: str
    category: str
    query: str
    expected_chunk_keys: list[str]
    expected_document_keys: list[str]


class KnowledgeProviderQueryResultView(ApiModel):
    case_key: str
    query: str
    expected_chunk_keys: list[str]
    returned_chunk_keys: list[str]
    hit: bool
    reciprocal_rank: float
    latency_ms: int
    top_score: float


class KnowledgeProviderEvaluationResultView(ApiModel):
    provider_key: str
    provider_mode: str
    protocol: str
    endpoint_fingerprint: str
    status: Literal["succeeded", "failed"]
    indexed_document_count: int
    indexed_chunk_count: int
    query_count: int
    hit_count: int
    recall_at_k: float
    mean_reciprocal_rank: float
    average_latency_ms: int
    p95_latency_ms: int
    items: list[KnowledgeProviderQueryResultView]
    failure_reason: str | None


class KnowledgeProviderEvaluationRunView(ApiModel):
    id: str
    evaluation_key: str
    benchmark_version: str
    status: Literal["running", "completed", "partial", "failed"]
    provider_keys: list[str]
    document_count: int
    chunk_count: int
    case_count: int
    actor_name: str
    idempotent: bool = False
    request_id: str
    run_id: str
    started_at: datetime
    finished_at: datetime | None
    results: list[KnowledgeProviderEvaluationResultView]


class KnowledgeProviderOperationsResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    benchmark_version: str
    active_document_count: int
    active_chunk_count: int
    benchmark_cases: list[KnowledgeBenchmarkCaseView]
    providers: list[KnowledgeProviderDescriptorView]
    runs: list[KnowledgeProviderEvaluationRunView]
    generated_at: datetime


class RoleTwinProfileView(ApiModel):
    key: str
    display_name: str
    role_title: str
    capabilities: list[str]
    provider: str
    model: str
    status: str
    published_at: datetime | None
    run_count: int
    latest_run_at: datetime | None


class TwinAnswerRequest(ApiModel):
    question: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=8)
    scope_key: str | None = Field(default=None, min_length=1, max_length=160)
    workspace_key: str | None = Field(default=None, min_length=2, max_length=64)
    runtime_session_id: str | None = Field(default=None, min_length=1, max_length=64)


class TwinAnswerPayload(ApiModel):
    summary: str = Field(min_length=1)
    facts: list[str]
    actions: list[str]
    caveats: list[str]
    confidence: Literal["high", "medium", "low"]


class MemoryContextView(ApiModel):
    id: str
    memory_key: str
    version_number: int
    category: str
    content: str
    source_ref: str
    effective_from: datetime | None


class MetricContextPointView(ApiModel):
    as_of: datetime
    value: float
    change_rate: float | None


class MetricContextView(ApiModel):
    key: str
    label: str
    unit: str
    scope_key: str
    definition_version: str
    date_from: datetime | None
    date_to: datetime | None
    latest_value: float | None
    period_change_rate: float | None
    minimum: float | None
    maximum: float | None
    points: list[MetricContextPointView]


class TwinAnswerResponse(ApiModel):
    schema_version: Literal[3] = 3
    run_id: str
    twin: RoleTwinProfileView
    question: str
    answer: TwinAnswerPayload
    evidence: list[EvidenceView]
    metric_context: list[MetricContextView]
    memory_context: list[MemoryContextView]
    execution_mode: Literal["model", "evidence-fallback"]
    provider: str
    model: str
    duration_ms: int
    created_at: datetime
    workspace_key: str | None = None
    runtime_session_id: str | None = None
    runtime_turn_id: str | None = None
