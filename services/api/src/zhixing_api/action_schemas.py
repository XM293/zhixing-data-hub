from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel


class MeetingDecisionConfirmationView(ApiModel):
    id: str
    meeting_key: str
    decision_package_id: str
    confirmed_by_actor_key: str
    confirmed_by_name: str
    comment: str
    confirmed_at: datetime


class ActionApprovalEventView(ApiModel):
    id: str
    actor_key: str
    actor_name: str
    decision: Literal["approved", "rejected"]
    comment: str
    idempotency_key: str
    created_at: datetime


class ActionExecutionView(ApiModel):
    id: str
    key: str
    idempotency_key: str
    status: Literal["recorded"]
    external_write: Literal[False]
    actor_key: str
    result: dict[str, object]
    started_at: datetime
    finished_at: datetime


class ActionWorkSummaryView(ApiModel):
    key: str
    status: Literal["ready", "claimed", "in_progress", "blocked", "completed"]
    assignee_name: str | None
    version: int


class ActionProposalView(ApiModel):
    id: str
    key: str
    source_type: Literal["meeting-decision", "customer-operation", "business-analysis"]
    source_key: str
    source_label: str
    source_route: str
    scope_type: Literal["enterprise", "store", "object"]
    scope_key: str
    meeting_key: str | None
    decision_package_id: str | None
    customer_operation_run_id: str | None
    business_analysis_run_id: str | None
    evidence_snapshot_id: str | None
    title: str
    owner: str
    due_hint: str
    kpi: str
    stop_condition: str
    evidence_refs: list[str]
    target_system: str
    target_key: str
    risk_level: Literal["R2"]
    action_level: Literal["R2"]
    parameters: dict[str, object]
    status: Literal["pending_approval", "approved", "rejected"]
    requested_by_actor_key: str
    requested_by_name: str
    idempotency_key: str
    approved_by_actor_key: str | None
    approved_by_name: str | None
    approved_at: datetime | None
    decision_comment: str | None
    approval_events: list[ActionApprovalEventView]
    execution: ActionExecutionView | None
    work_item: ActionWorkSummaryView | None
    created_at: datetime
    updated_at: datetime


class ActionProposalStats(ApiModel):
    total: int
    pending_approval: int
    approved: int
    rejected: int
    recorded_executions: int


class ActionProposalListResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    stats: ActionProposalStats
    items: list[ActionProposalView]
    generated_at: datetime


class ActionDecisionRequest(ApiModel):
    decision: Literal["approve", "reject"]
    comment: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=200, pattern=r"^[a-zA-Z0-9:_-]+$")


class ActionDecisionResponse(ApiModel):
    schema_version: Literal[1] = 1
    item: ActionProposalView


class CustomerOperationActionProposalRequest(ApiModel):
    step_indexes: list[int] = Field(min_length=1, max_length=6)
    due_hint: str = Field(min_length=2, max_length=300)
    idempotency_key: str = Field(
        min_length=8,
        max_length=160,
        pattern=r"^[a-zA-Z0-9:_-]+$",
    )


class CustomerOperationActionProposalResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    created_count: int
    items: list[ActionProposalView]


class BusinessAnalysisActionProposalRequest(ApiModel):
    recommendation_indexes: list[int] = Field(min_length=1, max_length=6)
    due_hint: str = Field(min_length=2, max_length=300)
    idempotency_key: str = Field(
        min_length=8,
        max_length=160,
        pattern=r"^[a-zA-Z0-9:_-]+$",
    )


class BusinessAnalysisActionProposalResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    created_count: int
    items: list[ActionProposalView]


class ActionWorkEventView(ApiModel):
    id: str
    event_type: Literal["created", "claim", "start", "block", "complete", "release", "reopen"]
    from_status: str | None
    to_status: Literal["ready", "claimed", "in_progress", "blocked", "completed"]
    actor_principal_id: str
    actor_name: str
    comment: str
    evidence_refs: list[str]
    idempotency_key: str
    created_at: datetime


class ActionWorkItemView(ApiModel):
    id: str
    key: str
    proposal_key: str
    source_type: Literal["meeting-decision", "customer-operation", "business-analysis"]
    source_label: str
    source_route: str
    scope_type: Literal["enterprise", "store", "object"]
    scope_key: str
    title: str
    owner_role: str
    due_hint: str
    kpi: str
    stop_condition: str
    priority: Literal["normal", "high", "urgent"]
    status: Literal["ready", "claimed", "in_progress", "blocked", "completed"]
    assignee_principal_id: str | None
    assignee_name: str | None
    version: int
    can_update: bool
    available_actions: list[
        Literal["claim", "start", "block", "complete", "release", "reopen"]
    ]
    blocker_reason: str | None
    result_summary: str | None
    result_evidence_refs: list[str]
    claimed_at: datetime | None
    started_at: datetime | None
    blocked_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    events: list[ActionWorkEventView]


class ActionWorkStats(ApiModel):
    total: int
    ready: int
    claimed: int
    in_progress: int
    blocked: int
    completed: int
    mine: int


class ActionWorkListResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    actor_name: str
    can_manage: bool
    stats: ActionWorkStats
    items: list[ActionWorkItemView]
    generated_at: datetime


class ActionWorkEventRequest(ApiModel):
    action: Literal["claim", "start", "block", "complete", "release", "reopen"]
    comment: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(
        min_length=8,
        max_length=200,
        pattern=r"^[a-zA-Z0-9:_-]+$",
    )


class ActionWorkEventResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    item: ActionWorkItemView
