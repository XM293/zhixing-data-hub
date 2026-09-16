from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel


class EvaluationRunRequest(ApiModel):
    client_request_key: str = Field(min_length=8, max_length=160)
    case_keys: list[str] = Field(default_factory=list, max_length=100)


class EvaluationCandidateActionRequest(ApiModel):
    action: Literal["accept", "reject"]
    reason: str = Field(min_length=2, max_length=2000)
    suite_key: str = Field(default="m1-role-twin-smoke", min_length=3, max_length=120)
    client_request_key: str = Field(min_length=8, max_length=160)


class EvaluationCheckView(ApiModel):
    key: str
    label: str
    passed: bool
    expected: str
    actual: str


class EvaluationCaseView(ApiModel):
    key: str
    version_number: int
    domain: str
    risk_level: str
    title: str
    actor_login_name: str
    target_twin_key: str
    input: dict[str, object]
    expectations: dict[str, object]
    status: str


class EvaluationRunItemView(ApiModel):
    id: str
    case_key: str
    case_version_number: int
    case_title: str
    domain: str
    risk_level: str
    actor_name: str
    actor_principal_id: str | None
    agent_run_id: str | None
    case_snapshot: dict[str, object]
    actor_snapshot: dict[str, object]
    outcome: Literal["passed", "failed", "review_required", "error"]
    checks: list[EvaluationCheckView]
    error_types: list[str]
    observed_error_code: str | None
    duration_ms: int
    created_at: datetime


class EvaluationRunView(ApiModel):
    id: str
    suite_key: str
    suite_version_number: int
    status: Literal["running", "completed", "failed"]
    provider: str
    model: str
    code_version: str
    config_version: str
    baseline_run_id: str | None
    pass_rate_delta: float | None
    total_count: int
    passed_count: int
    failed_count: int
    review_required_count: int
    error_count: int
    pass_rate: float
    duration_ms: int
    initiated_by_name: str
    started_at: datetime
    completed_at: datetime | None
    items: list[EvaluationRunItemView]


class EvaluationSuiteView(ApiModel):
    key: str
    version_number: int
    domain: str
    title: str
    description: str
    status: str
    cases: list[EvaluationCaseView]
    latest_run: EvaluationRunView | None
    recent_runs: list[EvaluationRunView]


class EvaluationCandidateView(ApiModel):
    id: str
    source_handoff_case_id: str
    source_feedback_event_id: str
    source_agent_run_id: str
    proposed_case_key: str
    proposed_title: str
    domain: str
    risk_level: str
    actor_login_name: str
    target_twin_key: str
    input: dict[str, object]
    expectations: dict[str, object]
    resolution_summary: str
    status: Literal["pending", "accepted", "rejected"]
    proposed_by_name: str
    reviewed_by_name: str | None
    accepted_case_id: str | None
    review_reason: str | None
    created_at: datetime
    reviewed_at: datetime | None


class EvaluationStudioStats(ApiModel):
    suite_count: int
    case_count: int
    run_count: int
    latest_pass_rate: float | None
    pending_manual_review_count: int
    candidate_count: int
    pending_candidate_count: int


class EvaluationStudioResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    stats: EvaluationStudioStats
    suites: list[EvaluationSuiteView]
    candidates: list[EvaluationCandidateView]
    generated_at: datetime


class EvaluationRunMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    run: EvaluationRunView
    studio: EvaluationStudioResponse


class EvaluationCandidateMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    candidate: EvaluationCandidateView
    studio: EvaluationStudioResponse
