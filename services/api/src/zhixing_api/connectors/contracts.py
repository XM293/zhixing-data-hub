from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol

AuthoritativeFactType = Literal[
    "orders",
    "order_lines",
    "refunds",
    "inventory",
    "advertising",
    "customer_profiles",
    "customer_touchpoints",
]
AUTHORITATIVE_FACT_TYPES = {
    "orders",
    "order_lines",
    "refunds",
    "inventory",
    "advertising",
    "customer_profiles",
    "customer_touchpoints",
}


class ConnectorError(RuntimeError):
    pass


SyncMode = Literal["full", "incremental", "backfill"]
ResourceStatus = Literal["succeeded", "partial", "failed", "skipped"]


@dataclass(frozen=True, slots=True)
class ConnectorCursor:
    """Opaque cursor owned by a connector; the platform never parses it."""

    resource: str
    value: str | None
    has_more: bool = False
    next_value: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectorResourceResult:
    resource: str
    status: ResourceStatus
    fetched_count: int
    accepted_count: int
    cursor: ConnectorCursor | None
    source_schema_version: str
    mapping_version: str
    error_code: str | None = None
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class ConnectorSyncRequest:
    mode: SyncMode
    cursors: tuple[ConnectorCursor, ...] = ()
    window_start: datetime | None = None
    window_end: datetime | None = None
    page_size: int = 500


@dataclass(frozen=True, slots=True)
class ConnectorSyncResult:
    batch: ConnectorBatch
    resources: tuple[ConnectorResourceResult, ...]
    completed: bool


def validate_connector_batch(batch: ConnectorBatch) -> None:
    if not batch.source_schema_version.strip():
        raise ConnectorError("source_schema_version cannot be empty")
    if not batch.mapping_version.strip():
        raise ConnectorError("mapping_version cannot be empty")
    unknown = set(batch.authoritative_fact_types) - AUTHORITATIVE_FACT_TYPES
    if unknown:
        raise ConnectorError(f"unknown authoritative fact types: {sorted(unknown)}")
    for record in batch.records:
        if not record.record_type.strip() or not record.external_id.strip():
            raise ConnectorError("external records require record_type and external_id")


@dataclass(frozen=True, slots=True)
class ExternalRecord:
    record_type: str
    external_id: str
    payload: dict[str, object]
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CanonicalEntity:
    entity_type: str
    canonical_key: str
    display_name: str
    status: str
    attributes: dict[str, object]


@dataclass(frozen=True, slots=True)
class CanonicalMetric:
    key: str
    label: str
    value: float
    unit: str
    change_rate: float | None
    as_of: datetime
    scope_key: str = "enterprise"


@dataclass(frozen=True, slots=True)
class CanonicalScopeMapping:
    scope_type: str
    scope_key: str
    external_scope_key: str
    label: str
    status: str
    attributes: dict[str, object]


@dataclass(frozen=True, slots=True)
class CanonicalOrderFact:
    order_key: str
    store_key: str
    customer_key: str
    channel: str
    status: str
    business_date: date
    paid_at: datetime
    shipped_at: datetime | None
    paid_amount_fen: int
    item_amount_fen: int
    discount_amount_fen: int
    freight_amount_fen: int
    cost_amount_fen: int
    item_count: int
    province: str


@dataclass(frozen=True, slots=True)
class CanonicalOrderLineFact:
    line_key: str
    order_key: str
    product_key: str
    sku_key: str
    quantity: int
    unit_price_fen: int
    paid_amount_fen: int
    cost_amount_fen: int
    refund_quantity: int
    refund_amount_fen: int


@dataclass(frozen=True, slots=True)
class CanonicalRefundFact:
    refund_key: str
    order_key: str
    line_key: str
    store_key: str
    customer_key: str
    sku_key: str
    reason_category: str
    status: str
    requested_at: datetime
    completed_at: datetime | None
    refund_amount_fen: int
    quantity: int


@dataclass(frozen=True, slots=True)
class CanonicalInventorySnapshotFact:
    snapshot_key: str
    warehouse_key: str
    product_key: str
    sku_key: str
    as_of: datetime
    available_quantity: int
    reserved_quantity: int
    in_transit_quantity: int
    safety_quantity: int
    inventory_cost_fen: int
    days_cover: float
    status: str


@dataclass(frozen=True, slots=True)
class CanonicalAdPerformanceFact:
    performance_key: str
    campaign_key: str
    store_key: str
    product_key: str
    channel: str
    business_date: date
    impressions: int
    clicks: int
    spend_fen: int
    attributed_order_count: int
    attributed_revenue_fen: int


@dataclass(frozen=True, slots=True)
class CanonicalCustomerProfile:
    customer_key: str
    display_name: str
    home_store_key: str
    member_level: str
    lifecycle_stage: str
    status: str
    province: str
    acquisition_channel: str
    registered_at: datetime
    last_active_at: datetime
    member_points: int
    growth_value: int
    churn_risk_score: float
    preferred_category: str
    consent_status: str
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CanonicalCustomerTouchpointFact:
    touchpoint_key: str
    customer_key: str
    store_key: str
    touchpoint_type: str
    channel: str
    occurred_at: datetime
    campaign_key: str | None
    value_fen: int
    properties: dict[str, object]


@dataclass(frozen=True, slots=True)
class ConnectorBatch:
    source_schema_version: str
    mapping_version: str
    records: tuple[ExternalRecord, ...]
    entities: tuple[CanonicalEntity, ...]
    metrics: tuple[CanonicalMetric, ...]
    warnings: tuple[str, ...]
    scope_mappings: tuple[CanonicalScopeMapping, ...] = ()
    orders: tuple[CanonicalOrderFact, ...] = ()
    order_lines: tuple[CanonicalOrderLineFact, ...] = ()
    refunds: tuple[CanonicalRefundFact, ...] = ()
    inventory: tuple[CanonicalInventorySnapshotFact, ...] = ()
    advertising: tuple[CanonicalAdPerformanceFact, ...] = ()
    customer_profiles: tuple[CanonicalCustomerProfile, ...] = ()
    customer_touchpoints: tuple[CanonicalCustomerTouchpointFact, ...] = ()
    authoritative_fact_types: tuple[AuthoritativeFactType, ...] = ()


class DataConnector(Protocol):
    async def fetch(self, scenario: str, volume_profile: str = "standard") -> ConnectorBatch: ...


class IncrementalDataConnector(DataConnector, Protocol):
    async def sync(self, request: ConnectorSyncRequest) -> ConnectorSyncResult: ...
