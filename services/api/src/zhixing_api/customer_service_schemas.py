from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel

ConversationStatus = Literal[
    "waiting", "draft_ready", "review_required", "handed_off", "resolved"
]
Priority = Literal["normal", "high", "urgent"]
Sentiment = Literal["calm", "concerned", "angry"]
RiskLevel = Literal["low", "medium", "high", "critical"]
RiskFlag = Literal[
    "compensation_commitment",
    "refund_timeline",
    "unverified_logistics",
    "safety_or_complaint",
    "legal_or_media",
    "personal_data",
    "manual_request",
    "data_conflict",
    "other",
]


class CustomerServiceConversationView(ApiModel):
    schema_version: Literal[1] = 1
    id: str
    enterprise_id: str
    conversation_key: str
    channel_key: str
    external_conversation_id: str | None
    source_system_key: str
    customer_key: str
    customer_name: str
    order_key: str | None
    store_scope_key: str
    topic: str
    status: ConversationStatus
    priority: Priority
    sentiment: Sentiment
    risk_level: RiskLevel
    risk_reason: str
    assigned_principal_id: str | None
    last_message_at: datetime
    first_response_due_at: datetime
    latest_sync_at: datetime
    created_at: datetime
    updated_at: datetime
    last_message_preview: str
    message_count: int
    draft_count: int
    sla_overdue: bool


class CustomerServiceMessageView(ApiModel):
    id: str
    message_key: str
    sender_type: Literal["customer", "agent", "system"]
    direction: Literal["inbound", "outbound"]
    sender_name: str
    content: str
    delivery_status: str
    occurred_at: datetime


class CustomerServiceOrderContextView(ApiModel):
    context_type: Literal["order", "pre-sale"]
    order_key: str | None
    order_status: str | None
    paid_amount: float | None
    currency: str
    product_summary: str
    item_quantity: int
    payment_at: datetime | None
    logistics_status: str | None
    carrier: str | None
    tracking_no: str | None
    latest_logistics_event: str | None
    promised_delivery_at: datetime | None
    latest_logistics_at: datetime | None
    delayed_hours: int
    aftersale_status: str | None
    source_system_key: str
    payload_version: str
    synced_at: datetime


class CustomerServiceReconciliationDifferenceView(ApiModel):
    field: Literal["order_status", "paid_amount", "item_count", "refund_state"]
    severity: Literal["info", "warning", "critical"]
    context_value: str | None
    canonical_value: str | None
    message: str


class CustomerServiceCanonicalFactView(ApiModel):
    match_status: Literal["matched", "not_applicable", "missing", "scope_mismatch"]
    match_reason: str
    consistency_status: Literal["consistent", "conflict", "not_checked"]
    consistency_reason: str
    material_conflict: bool
    differences: list[CustomerServiceReconciliationDifferenceView]
    order_key: str | None
    customer_key: str | None
    store_scope_key: str
    external_store_key: str | None
    order_status: str | None
    paid_amount: float | None
    cost_amount: float | None
    gross_margin_rate: float | None
    currency: str
    item_count: int | None
    refund_count: int
    refund_amount: float
    refund_statuses: list[str]
    business_date: date | None
    paid_at: datetime | None
    source_system_key: str | None
    sync_run_ids: list[str]
    scope_mapping_id: str | None
    mapping_version: str | None


class CustomerServiceEvidenceView(ApiModel):
    ref: str = Field(pattern=r"^(D|K)[1-9][0-9]*$")
    item_type: Literal[
        "order", "logistics", "order-fact", "refund-fact", "reconciliation", "policy"
    ]
    label: str
    version_ref: str | None
    excerpt: str
    locator: str | None


class CustomerServiceReplyDraftView(ApiModel):
    schema_version: Literal[1] = 1
    id: str
    enterprise_id: str
    conversation_id: str
    version_number: int
    status: Literal["generated", "sandbox_sent", "rejected", "superseded"]
    body: str
    risk_level: RiskLevel
    risk_flags: list[RiskFlag]
    safe_to_send: bool
    suggested_action: Literal["reply", "investigate", "handoff"]
    evidence_refs: list[str]
    evidence: list[CustomerServiceEvidenceView]
    provider: str
    model: str
    execution_mode: Literal["model", "evidence-fallback"]
    fallback_reason: str | None
    evidence_snapshot_id: str
    agent_run_id: str
    role_twin_version_id: str
    created_by_principal_id: str
    approved_by_principal_id: str | None
    approval_note: str | None
    idempotency_key: str
    request_id: str
    run_id: str
    created_at: datetime
    approved_at: datetime | None


class CustomerServiceEventView(ApiModel):
    id: str
    event_type: Literal["draft_generated", "sandbox_reply_sent", "handoff_created"]
    reply_draft_id: str | None
    actor_principal_id: str
    actor_name: str
    details: dict[str, object]
    occurred_at: datetime


class CustomerServiceConversationDetail(ApiModel):
    conversation: CustomerServiceConversationView
    messages: list[CustomerServiceMessageView]
    order_context: CustomerServiceOrderContextView
    canonical_order_fact: CustomerServiceCanonicalFactView
    drafts: list[CustomerServiceReplyDraftView]
    events: list[CustomerServiceEventView]


class CustomerServicePolicyView(ApiModel):
    document_key: str
    title: str
    version_label: str
    status: str
    effective_from: datetime | None
    resolved_at: datetime


class CustomerServiceTwinView(ApiModel):
    key: str
    display_name: str
    role_title: str
    version_number: int
    version_id: str
    status: str


class CustomerServiceStats(ApiModel):
    waiting_count: int
    review_required_count: int
    handoff_count: int
    overdue_count: int
    safe_draft_count: int
    total_count: int


class CustomerServiceStudioResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    channel_mode: Literal["commerce-sandbox"] = "commerce-sandbox"
    actor_name: str
    can_generate: bool
    can_send: bool
    can_handoff: bool
    stats: CustomerServiceStats
    active_policy: CustomerServicePolicyView
    twin: CustomerServiceTwinView
    conversations: list[CustomerServiceConversationView]
    drafts: list[CustomerServiceReplyDraftView]
    selected: CustomerServiceConversationDetail
    generated_at: datetime


class CustomerServiceDraftRequest(ApiModel):
    client_request_key: str = Field(min_length=8, max_length=160)


class CustomerServiceHandoffRequest(ApiModel):
    reason: str = Field(min_length=2, max_length=1000)
    client_request_key: str = Field(min_length=8, max_length=160)


class CustomerServiceSandboxSendRequest(ApiModel):
    final_body: str | None = Field(default=None, min_length=2, max_length=4000)
    note: str = Field(min_length=2, max_length=1000)
    client_request_key: str = Field(min_length=8, max_length=160)


class CustomerServiceMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    studio: CustomerServiceStudioResponse
