from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.decision_schemas import MemoryCandidateView
from zhixing_api.models import ApiModel


class ChatImportRequest(ApiModel):
    twin_key: str = Field(min_length=3, max_length=120, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    source_filename: str = Field(min_length=1, max_length=260)
    source_channel: str = Field(default="manual-paste", min_length=2, max_length=64)
    timezone: str = Field(default="Asia/Shanghai", min_length=3, max_length=64)
    target_speakers: list[str] = Field(default_factory=list, max_length=20)
    content: str = Field(min_length=20, max_length=1_000_000)


class ChatImportRunView(ApiModel):
    id: str
    twin_key: str
    twin_name: str
    actor_name: str
    source_filename: str
    source_channel: str
    content_hash: str
    status: Literal["completed", "duplicate", "failed"]
    message_count: int
    topic_count: int
    candidate_count: int
    participants: list[str]
    started_at: datetime | None
    ended_at: datetime | None
    warnings: list[dict[str, object]]
    request_id: str
    run_id: str
    created_at: datetime
    finished_at: datetime


class ChatMessageView(ApiModel):
    id: str
    message_key: str
    sent_at: datetime | None
    sender_name: str
    topic_key: str
    content: str
    ordinal: int


class ChatImportResponse(ApiModel):
    schema_version: Literal[1] = 1
    duplicate: bool
    import_run: ChatImportRunView
    messages: list[ChatMessageView]
    candidates: list[MemoryCandidateView]


class ChatImportListResponse(ApiModel):
    schema_version: Literal[1] = 1
    status_counts: dict[str, int]
    items: list[ChatImportRunView]
    generated_at: datetime


class MemoryReviewRequest(ApiModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=2, max_length=1000)
    conflict_resolution: Literal["verified_clear", "retain_conflict"] | None = None


class MemoryLifecycleRequest(ApiModel):
    reason: str = Field(min_length=2, max_length=1000)


class ApprovedMemoryView(ApiModel):
    id: str
    candidate_id: str
    memory_key: str
    twin_key: str
    version_number: int
    category: str
    content: str
    source_type: str
    source_ref: str
    evidence_refs: list[dict[str, object]]
    status: Literal["approved", "active", "retired"]
    approved_by: str
    approved_at: datetime
    effective_from: datetime | None
    effective_until: datetime | None


class MemoryReviewEventView(ApiModel):
    id: str
    event_type: Literal["approved", "rejected", "activated", "retired"]
    from_status: str
    to_status: str
    actor_name: str
    reason: str
    request_id: str
    run_id: str
    occurred_at: datetime


class MemoryMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    candidate: MemoryCandidateView
    approved_memory: ApprovedMemoryView | None
    event: MemoryReviewEventView


class MemoryProviderEvaluationRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    provider_keys: list[Literal["tencentdb-agent-memory", "mem0"]] = Field(
        min_length=1,
        max_length=2,
    )
    top_k: int = Field(default=3, ge=1, le=10)


class MemoryProviderDescriptorView(ApiModel):
    key: str
    label: str
    protocol: str
    mode: str
    endpoint_fingerprint: str
    authentication_configured: bool


class MemoryBenchmarkCaseView(ApiModel):
    key: str
    category: str
    query: str
    expected_memory_keys: list[str]
    expected_twin_keys: list[str]


class MemoryProviderQueryResultView(ApiModel):
    case_key: str
    query: str
    expected_memory_keys: list[str]
    returned_memory_keys: list[str]
    hit: bool
    latency_ms: int
    top_score: float


class MemoryProviderEvaluationResultView(ApiModel):
    provider_key: str
    provider_mode: str
    protocol: str
    endpoint_fingerprint: str
    status: Literal["succeeded", "failed"]
    indexed_memory_count: int
    query_count: int
    hit_count: int
    recall_at_k: float
    average_latency_ms: int
    p95_latency_ms: int
    items: list[MemoryProviderQueryResultView]
    failure_reason: str | None


class MemoryProviderEvaluationRunView(ApiModel):
    id: str
    evaluation_key: str
    benchmark_version: str
    status: Literal["running", "completed", "partial", "failed"]
    provider_keys: list[str]
    memory_count: int
    case_count: int
    actor_name: str
    idempotent: bool = False
    request_id: str
    run_id: str
    started_at: datetime
    finished_at: datetime | None
    results: list[MemoryProviderEvaluationResultView]


class MemoryProviderOperationsResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    benchmark_version: str
    active_memory_count: int
    benchmark_cases: list[MemoryBenchmarkCaseView]
    providers: list[MemoryProviderDescriptorView]
    runs: list[MemoryProviderEvaluationRunView]
    generated_at: datetime
