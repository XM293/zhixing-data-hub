from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel

FeedbackKind = Literal[
    "helpful",
    "inaccurate",
    "incomplete",
    "unsafe",
    "scope_issue",
    "handoff",
]
HandoffStatus = Literal["open", "in_review", "resolved"]
HandoffPriority = Literal["normal", "high", "urgent"]
ResolutionType = Literal[
    "corrected_answer",
    "policy_update",
    "memory_update",
    "no_issue",
    "rerouted",
]


class AgentFeedbackSubmitRequest(ApiModel):
    kind: FeedbackKind
    message: str = Field(min_length=2, max_length=2000)
    expected_answer: str | None = Field(default=None, max_length=4000)
    priority: HandoffPriority = "normal"
    client_request_key: str = Field(min_length=8, max_length=160)


class AgentFeedbackCaseActionRequest(ApiModel):
    action: Literal["assign_to_me", "add_note", "resolve", "reopen"]
    message: str = Field(min_length=2, max_length=2000)
    resolution_type: ResolutionType | None = None
    resolution_summary: str | None = Field(default=None, max_length=4000)
    client_request_key: str = Field(min_length=8, max_length=160)


class AgentFeedbackEventView(ApiModel):
    id: str
    event_type: Literal[
        "feedback_submitted",
        "assigned",
        "note_added",
        "resolved",
        "reopened",
    ]
    feedback_kind: FeedbackKind | None
    actor_principal_id: str
    actor_name: str
    message: str
    expected_answer: str | None
    from_status: HandoffStatus | None
    to_status: HandoffStatus | None
    created_at: datetime


class HumanHandoffCaseView(ApiModel):
    id: str
    agent_run_id: str
    twin_key: str
    twin_name: str
    role_twin_version_number: int | None
    question: str
    answer: str
    execution_mode: Literal["model", "evidence-fallback"]
    opened_by_principal_id: str
    opened_by_name: str
    assigned_to_principal_id: str | None
    assigned_to_name: str | None
    status: HandoffStatus
    priority: HandoffPriority
    category: FeedbackKind
    subject: str
    resolution_type: ResolutionType | None
    resolution_summary: str | None
    evaluation_candidate_id: str | None
    evaluation_candidate_status: Literal["pending", "accepted", "rejected"] | None
    opened_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    events: list[AgentFeedbackEventView]


class AgentRunFeedbackResponse(ApiModel):
    schema_version: Literal[1] = 1
    agent_run_id: str
    idempotent: bool = False
    feedback: AgentFeedbackEventView | None
    feedback_events: list[AgentFeedbackEventView]
    handoff_case: HumanHandoffCaseView | None


class AgentFeedbackStats(ApiModel):
    case_count: int
    open_count: int
    in_review_count: int
    urgent_count: int
    resolved_count: int
    feedback_event_count: int


class AgentFeedbackStudioResponse(ApiModel):
    schema_version: Literal[1] = 1
    stats: AgentFeedbackStats
    cases: list[HumanHandoffCaseView]
    generated_at: datetime
