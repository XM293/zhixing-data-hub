from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.knowledge_schemas import TwinAnswerPayload
from zhixing_api.models import ApiModel


class RoleTwinTestRunRequest(ApiModel):
    twin_key: str = Field(min_length=3, max_length=100)


class RoleTwinTestReviewRequest(ApiModel):
    decision: Literal["pass", "needs_revision", "fail"]
    evidence_grounding: int = Field(ge=1, le=5)
    boundary_adherence: int = Field(ge=1, le=5)
    voice_match: int = Field(ge=1, le=5)
    usefulness: int = Field(ge=1, le=5)
    notes: str = Field(min_length=2, max_length=2000)


class RoleTwinTestTwinOption(ApiModel):
    key: str
    display_name: str
    role_title: str
    current_version_number: int
    status: str


class RoleTwinTestContextRef(ApiModel):
    kind: Literal["data", "evidence", "memory"]
    label: str
    version_ref: str | None
    excerpt: str
    rank: int


class RoleTwinTestReviewView(ApiModel):
    id: str
    decision: Literal["pass", "needs_revision", "fail"]
    evidence_grounding: int
    boundary_adherence: int
    voice_match: int
    usefulness: int
    average_score: float
    notes: str
    reviewer_name: str
    request_id: str
    run_id: str
    created_at: datetime


class RoleTwinTestRunView(ApiModel):
    id: str
    case_key: str
    case_version_number: int
    twin_key: str
    twin_name: str
    role_twin_version_number: int
    agent_run_id: str
    question: str
    answer: TwinAnswerPayload
    evidence_count: int
    metric_context_count: int
    memory_context_count: int
    context_refs: list[RoleTwinTestContextRef]
    execution_mode: Literal["model", "evidence-fallback"]
    provider: str
    model: str
    duration_ms: int
    status: str
    actor_name: str
    created_at: datetime
    reviews: list[RoleTwinTestReviewView]
    latest_review: RoleTwinTestReviewView | None


class RoleTwinTestCaseView(ApiModel):
    id: str
    key: str
    version_number: int
    status: str
    title: str
    category: Literal["knowledge", "data", "boundary", "style", "decision"]
    risk_level: Literal["low", "medium", "high"]
    question: str
    expected_behaviors: list[str]
    expected_evidence_refs: list[str]
    target_twin_key: str
    target_twin_name: str
    created_at: datetime
    runs: list[RoleTwinTestRunView]


class RoleTwinTestStats(ApiModel):
    case_count: int
    run_count: int
    pending_review_count: int
    reviewed_count: int
    passed_count: int
    pass_rate: float | None


class RoleTwinTestStudioResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    stats: RoleTwinTestStats
    twins: list[RoleTwinTestTwinOption]
    cases: list[RoleTwinTestCaseView]
    generated_at: datetime


class RoleTwinTestMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    run: RoleTwinTestRunView
    studio: RoleTwinTestStudioResponse
