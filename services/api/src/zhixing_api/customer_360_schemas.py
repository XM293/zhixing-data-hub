from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from zhixing_api.models import ApiModel


class Customer360Summary(ApiModel):
    profile_count: int
    active_customer_count: int
    consented_customer_count: int
    at_risk_customer_count: int
    purchasing_customer_count: int
    repeat_customer_count: int
    repeat_purchase_rate: float
    paid_gmv_yuan: float
    average_customer_value_yuan: float
    touchpoint_count: int


class CustomerSegmentView(ApiModel):
    key: str
    label: str
    customer_count: int
    purchasing_customer_count: int
    paid_gmv_yuan: float
    average_order_count: float
    at_risk_customer_count: int


class CustomerChannelView(ApiModel):
    key: str
    label: str
    customer_count: int
    touchpoint_count: int
    purchasing_customer_count: int
    paid_gmv_yuan: float


class CustomerTrendPointView(ApiModel):
    business_date: date
    touchpoint_count: int
    active_customer_count: int


class CustomerProfileView(ApiModel):
    customer_key: str
    display_name: str
    home_store_key: str
    home_store_name: str
    member_level: str
    lifecycle_stage: str
    status: str
    province: str
    acquisition_channel: str
    preferred_category: str
    churn_risk_score: float
    consent_status: str
    member_points: int
    growth_value: int
    tags: list[str]
    registered_at: datetime
    last_active_at: datetime
    order_count: int
    paid_gmv_yuan: float
    refund_amount_yuan: float
    last_order_at: datetime | None
    touchpoint_count: int
    last_touchpoint_at: datetime | None
    source_key: str
    sync_run_id: str


class CustomerTouchpointView(ApiModel):
    touchpoint_key: str
    customer_key: str
    customer_name: str
    store_key: str
    touchpoint_type: str
    channel: str
    occurred_at: datetime
    campaign_key: str | None
    value_yuan: float
    properties: dict[str, object]
    source_key: str
    sync_run_id: str


class CustomerLineageAssetView(ApiModel):
    key: str
    label: str
    table_name: str
    record_count: int
    source_key: str
    source_schema_version: str
    mapping_version: str
    latest_sync_run_id: str | None


class Customer360Response(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    scope_key: str
    summary: Customer360Summary
    segments: list[CustomerSegmentView]
    channels: list[CustomerChannelView]
    touchpoint_trend: list[CustomerTrendPointView]
    customers: list[CustomerProfileView]
    recent_touchpoints: list[CustomerTouchpointView]
    lineage: list[CustomerLineageAssetView]
    generated_at: datetime


class CustomerDetailSummary(ApiModel):
    lifetime_order_count: int
    paid_gmv_yuan: float
    average_order_value_yuan: float
    refund_count: int
    refund_amount_yuan: float
    refund_rate: float
    touchpoint_count: int
    days_since_last_active: int
    days_since_last_order: int | None
    engagement_eligible: bool
    risk_level: Literal["low", "medium", "high"]


class CustomerOrderView(ApiModel):
    order_key: str
    store_key: str
    store_name: str
    channel: str
    status: str
    business_date: date
    paid_at: datetime
    shipped_at: datetime | None
    paid_amount_yuan: float
    gross_margin_yuan: float
    gross_margin_rate: float
    item_count: int
    source_key: str
    sync_run_id: str


class CustomerRefundView(ApiModel):
    refund_key: str
    order_key: str
    sku_key: str
    reason_category: str
    status: str
    requested_at: datetime
    completed_at: datetime | None
    refund_amount_yuan: float
    quantity: int
    source_key: str
    sync_run_id: str


class CustomerTimelineEventView(ApiModel):
    event_key: str
    event_type: Literal["profile", "order", "refund", "touchpoint"]
    occurred_at: datetime
    title: str
    detail: str
    value_yuan: float | None
    source_key: str
    sync_run_id: str
    evidence_key: str


class CustomerRecommendationView(ApiModel):
    key: str
    title: str
    priority: Literal["critical", "high", "medium", "low"]
    rationale: str
    objective: str
    action_boundary: str
    eligible: bool
    evidence_keys: list[str]


class CustomerDetailResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    scope_key: str
    customer_key: str
    recommendation_mode: Literal["deterministic_playbook"] = "deterministic_playbook"
    playbook_version: str
    profile: CustomerProfileView
    summary: CustomerDetailSummary
    recommendations: list[CustomerRecommendationView]
    timeline: list[CustomerTimelineEventView]
    orders: list[CustomerOrderView]
    refunds: list[CustomerRefundView]
    touchpoints: list[CustomerTouchpointView]
    lineage: list[CustomerLineageAssetView]
    generated_at: datetime
