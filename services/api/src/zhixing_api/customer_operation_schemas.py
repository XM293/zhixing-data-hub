from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel

CustomerOperationActionType = Literal[
    "manual_review",
    "service_handoff",
    "content_preparation",
    "audience_analysis",
]


class CustomerOperationEvidenceView(ApiModel):
    evidence_ref: str = Field(pattern=r"^E[1-9][0-9]*$")
    item_type: str
    item_key: str
    label: str
    version_ref: str | None
    payload: dict[str, object]


class CustomerOperationDiagnosisView(ApiModel):
    kind: Literal["fact", "inference", "risk"]
    severity: Literal["low", "medium", "high"]
    text: str
    evidence_refs: list[str]


class CustomerOperationStepView(ApiModel):
    title: str
    action: str
    owner_role: str
    priority: Literal["normal", "high", "urgent"]
    action_type: CustomerOperationActionType
    evidence_refs: list[str]
    success_metric: str
    stop_condition: str
    requires_human_approval: Literal[True] = True
    external_write_allowed: Literal[False] = False


class CustomerOperationResultPayload(ApiModel):
    headline: str
    summary: str
    objective: str
    confidence: Literal["high", "medium", "low"]
    diagnoses: list[CustomerOperationDiagnosisView]
    steps: list[CustomerOperationStepView]
    unknowns: list[str]
    prohibited_actions: list[str]


class CustomerOperationEvidenceSnapshotView(ApiModel):
    id: str
    snapshot_key: str
    purpose: Literal["customer-operation"]
    content_hash: str
    item_count: int
    frozen_at: datetime


class CustomerOperationActionProposalLinkView(ApiModel):
    step_index: int
    proposal_key: str
    status: Literal["pending_approval", "approved", "rejected"]


class CustomerOperationRunView(ApiModel):
    id: str
    customer_key: str
    scope_type: Literal["enterprise", "store"]
    scope_key: str
    objective: str
    status: Literal["completed"]
    risk_level: Literal["low", "medium", "high"]
    provider: str
    model: str
    execution_mode: Literal["model", "rule-fallback"]
    fallback_reason: str | None
    result: CustomerOperationResultPayload
    evidence_snapshot: CustomerOperationEvidenceSnapshotView
    evidence: list[CustomerOperationEvidenceView]
    action_proposals: list[CustomerOperationActionProposalLinkView]
    initiated_by_name: str
    initiated_by_principal_id: str
    request_id: str
    run_id: str
    duration_ms: int
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime
    completed_at: datetime


class CustomerOperationStudioResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    scope_key: str
    customer_key: str
    can_run: bool
    can_propose: bool
    runs: list[CustomerOperationRunView]
    generated_at: datetime


class CustomerOperationRunRequest(ApiModel):
    scope_key: str = Field(min_length=1, max_length=160)
    customer_key: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=8, max_length=1000)
    client_request_key: str = Field(min_length=8, max_length=160)


class CustomerOperationRunResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    run: CustomerOperationRunView
    studio: CustomerOperationStudioResponse
