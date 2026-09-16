from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.action_schemas import ActionProposalView, MeetingDecisionConfirmationView
from zhixing_api.models import ApiModel

Confidence = Literal["high", "medium", "low"]
Stance = Literal["support", "oppose", "conditional"]
MeetingTemplateKey = Literal[
    "budget-inventory-review",
    "inventory-clearance-review",
    "kpi-incentive-review",
]
MeetingScopeType = Literal["enterprise", "store"]


class TwinCatalogStats(ApiModel):
    profile_count: int
    active_memory_count: int
    candidate_memory_count: int
    conflicted_memory_count: int
    agent_run_count: int


class RoleTwinCatalogItem(ApiModel):
    key: str
    display_name: str
    role_title: str
    status: str
    provider: str
    model: str
    capabilities: list[str]
    voice_guide: str
    reasoning_guide: str
    answer_policy: str
    active_memory_count: int
    candidate_memory_count: int
    conflicted_memory_count: int
    run_count: int
    published_at: datetime | None
    latest_run_at: datetime | None
    updated_at: datetime


class RoleTwinCatalogResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    stats: TwinCatalogStats
    items: list[RoleTwinCatalogItem]
    generated_at: datetime


class MemoryCandidateView(ApiModel):
    id: str
    key: str
    twin_key: str
    twin_name: str
    category: str
    content: str
    source_type: str
    source_ref: str
    confidence: float
    conflict_status: str
    conflict_ref: str | None
    evidence_refs: list[dict[str, object]]
    status: str
    reviewer: str | None
    review_reason: str | None
    reviewed_at: datetime | None
    effective_from: datetime | None
    retired_at: datetime | None
    approved_memory_id: str | None
    approved_memory_status: str | None
    memory_version: int | None
    created_at: datetime
    updated_at: datetime


class MemoryCandidateListResponse(ApiModel):
    schema_version: Literal[2] = 2
    data_mode: Literal["database"] = "database"
    status_counts: dict[str, int]
    conflict_counts: dict[str, int]
    items: list[MemoryCandidateView]
    generated_at: datetime


class MeetingListItem(ApiModel):
    key: str
    title: str
    topic: str
    status: str
    protocol_status: str
    template_key: str
    initiated_by_name: str
    scope_type: MeetingScopeType
    scope_key: str
    scope_label: str
    decision_owner: str
    deadline_at: datetime | None
    success_metric: str
    evidence_snapshot: str
    participant_count: int
    claim_count: int
    deliberation_count: int
    has_decision_package: bool
    workspace_key: str | None = None
    updated_at: datetime
    created_at: datetime


class MeetingListResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    status_counts: dict[str, int]
    templates: list[MeetingTemplateView]
    scopes: list[MeetingScopeView]
    items: list[MeetingListItem]
    generated_at: datetime


class MeetingTemplateView(ApiModel):
    key: MeetingTemplateKey
    label: str
    description: str
    default_title: str
    default_topic: str
    default_success_metric: str


class MeetingScopeView(ApiModel):
    type: MeetingScopeType
    key: str
    label: str
    has_metric_data: bool


class MeetingCreateRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    template_key: MeetingTemplateKey
    title: str = Field(min_length=4, max_length=240)
    topic: str = Field(min_length=10, max_length=500)
    scope_type: MeetingScopeType
    scope_key: str = Field(min_length=2, max_length=160)
    success_metric: str = Field(min_length=6, max_length=500)
    deadline_at: datetime | None = None
    participant_keys: list[str] = Field(min_length=3, max_length=6)
    workspace_key: str | None = Field(default=None, min_length=2, max_length=64)


class MeetingCreateResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    meeting: MeetingListItem


class EvidenceSnapshotItemView(ApiModel):
    type: str
    key: str
    version_ref: str | None
    label: str
    payload: dict[str, object]
    rank: int


class EvidenceSnapshotView(ApiModel):
    key: str
    purpose: str
    query: str
    content_hash: str
    item_count: int
    frozen_at: datetime
    items: list[EvidenceSnapshotItemView]


class ClaimItem(ApiModel):
    statement: str = Field(min_length=1)
    evidence_refs: list[str]
    assumption: str
    confidence: Confidence


class RoleAnalysisPayload(ApiModel):
    stance: Stance
    summary: str = Field(min_length=1)
    claims: list[ClaimItem]
    risks: list[str]
    unknowns: list[str]
    recommendation: str = Field(min_length=1)
    confidence: Confidence


class MeetingClaimView(RoleAnalysisPayload):
    id: str
    twin_key: str
    twin_name: str
    role_title: str
    phase: str
    created_at: datetime


class CrossExaminationItem(ApiModel):
    statement: str = Field(min_length=1)
    target_claim: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    new_evidence_refs: list[str]
    question: str = Field(min_length=1)
    confidence: Confidence


class CrossExaminationPayload(ApiModel):
    summary: str = Field(min_length=1)
    challenges: list[CrossExaminationItem] = Field(min_length=1)
    position_after: Stance
    position_changed: bool
    unresolved: list[str]
    confidence: Confidence


class RiskFailureMode(ApiModel):
    risk: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    evidence_refs: list[str] = Field(min_length=1)
    trigger: str = Field(min_length=1)
    mitigation: str = Field(min_length=1)


class RiskReviewPayload(ApiModel):
    summary: str = Field(min_length=1)
    failure_modes: list[RiskFailureMode] = Field(min_length=1)
    counterfactuals: list[str]
    incentive_risks: list[str]
    unresolved: list[str]
    confidence: Confidence


class MeetingDeliberationTurnView(ApiModel):
    id: str
    speaker_twin_key: str
    speaker_name: str
    speaker_role_title: str
    target_twin_key: str | None
    target_name: str | None
    phase: str
    round_number: int
    turn_type: Literal["challenge", "response", "risk_review"]
    summary: str
    payload: CrossExaminationPayload | RiskReviewPayload
    evidence_refs: list[str]
    new_evidence_refs: list[str]
    position_after: Stance | None
    position_changed: bool
    confidence: Confidence
    created_at: datetime


class DecisionAction(ApiModel):
    title: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    due_hint: str = Field(min_length=1)
    kpi: str = Field(min_length=1)
    stop_condition: str = Field(min_length=1)
    evidence_refs: list[str]


class DecisionPackagePayload(ApiModel):
    summary: str = Field(min_length=1)
    consensus: list[str]
    disagreements: list[str]
    risks: list[str]
    decision: str = Field(min_length=1)
    actions: list[DecisionAction]
    confidence: Confidence


class DecisionPackageView(DecisionPackagePayload):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime


class MeetingParticipantView(ApiModel):
    actor_key: str
    role_name: str
    position: str
    finding: str
    status: str
    speaking_order: int


class DigitalMeetingDetailResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    meeting: MeetingListItem
    participants: list[MeetingParticipantView]
    evidence: EvidenceSnapshotView | None
    claims: list[MeetingClaimView]
    deliberation_turns: list[MeetingDeliberationTurnView]
    decision_package: DecisionPackageView | None
    confirmation: MeetingDecisionConfirmationView | None
    action_proposals: list[ActionProposalView]
    generated_at: datetime


class MeetingRunRequest(ApiModel):
    refresh_evidence: bool = True


class MeetingRunResponse(ApiModel):
    schema_version: Literal[1] = 1
    detail: DigitalMeetingDetailResponse
    execution_modes: dict[str, Literal["model", "evidence-fallback"]]
    duration_ms: int


class MeetingConfirmRequest(ApiModel):
    comment: str = Field(min_length=1, max_length=1000)


class MeetingConfirmResponse(ApiModel):
    schema_version: Literal[1] = 1
    detail: DigitalMeetingDetailResponse
    created_action_count: int


ROLE_ANALYSIS_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "stance": {"type": "string", "enum": ["support", "oppose", "conditional"]},
        "summary": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "statement": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "assumption": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": ["statement", "evidence_refs", "assumption", "confidence"],
            },
        },
        "risks": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "recommendation": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": [
        "stance",
        "summary",
        "claims",
        "risks",
        "unknowns",
        "recommendation",
        "confidence",
    ],
}


CROSS_EXAMINATION_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "challenges": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "statement": {"type": "string"},
                    "target_claim": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "new_evidence_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "question": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": [
                    "statement",
                    "target_claim",
                    "evidence_refs",
                    "new_evidence_refs",
                    "question",
                    "confidence",
                ],
            },
        },
        "position_after": {
            "type": "string",
            "enum": ["support", "oppose", "conditional"],
        },
        "position_changed": {"type": "boolean"},
        "unresolved": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": [
        "summary",
        "challenges",
        "position_after",
        "position_changed",
        "unresolved",
        "confidence",
    ],
}


RISK_REVIEW_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "failure_modes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "risk": {"type": "string"},
                    "mechanism": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "trigger": {"type": "string"},
                    "mitigation": {"type": "string"},
                },
                "required": ["risk", "mechanism", "evidence_refs", "trigger", "mitigation"],
            },
        },
        "counterfactuals": {"type": "array", "items": {"type": "string"}},
        "incentive_risks": {"type": "array", "items": {"type": "string"}},
        "unresolved": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": [
        "summary",
        "failure_modes",
        "counterfactuals",
        "incentive_risks",
        "unresolved",
        "confidence",
    ],
}


DECISION_PACKAGE_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "consensus": {"type": "array", "items": {"type": "string"}},
        "disagreements": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "decision": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "owner": {"type": "string"},
                    "due_hint": {"type": "string"},
                    "kpi": {"type": "string"},
                    "stop_condition": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "title",
                    "owner",
                    "due_hint",
                    "kpi",
                    "stop_condition",
                    "evidence_refs",
                ],
            },
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": [
        "summary",
        "consensus",
        "disagreements",
        "risks",
        "decision",
        "actions",
        "confidence",
    ],
}
