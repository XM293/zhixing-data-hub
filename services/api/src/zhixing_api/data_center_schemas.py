from datetime import date, datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel


class EnterpriseView(ApiModel):
    id: str
    code: str
    name: str
    timezone: str


class DatabaseView(ApiModel):
    engine: str
    persistent: bool
    schema_revision: str


class DataSourceView(ApiModel):
    key: str
    name: str
    system_type: str
    status: str
    connection_status: str | None = None
    source_schema_version: str
    mapping_version: str
    last_sync_at: datetime | None
    source_record_count: int
    sync_run_count: int


class MetricView(ApiModel):
    key: str
    label: str
    value: float
    unit: str
    change_rate: float | None
    as_of: datetime


class TwinNodeView(ApiModel):
    key: str
    label: str
    node_type: str
    status: str
    health: float
    position: tuple[float, float, float]
    description: str


class TwinEdgeView(ApiModel):
    key: str
    source: str
    target: str
    flow_type: str
    status: str
    traffic: float


class EventView(ApiModel):
    id: str
    event_type: str
    severity: str
    title: str
    detail: str
    occurred_at: datetime


class TwinSceneView(ApiModel):
    key: str
    name: str
    version: str
    status: str
    description: str
    parent_scene_key: str | None
    scene_level: str
    entry_space_key: str | None
    asset_bundle_key: str | None
    camera_preset: dict[str, object]
    updated_at: datetime


class TwinSpaceView(ApiModel):
    key: str
    label: str
    space_type: str
    parent_space_key: str | None
    status: str
    health: float
    alert_level: str
    metric_key: str | None
    position: tuple[float, float, float]
    size: tuple[float, float, float]
    description: str


class TwinActorView(ApiModel):
    key: str
    display_name: str
    role_title: str
    status: str
    home_space_key: str
    current_space_key: str
    avatar_style: str
    color: str
    position: tuple[float, float, float]
    capabilities: list[str]


class TwinRouteView(ApiModel):
    key: str
    source_space_key: str
    target_space_key: str
    route_type: str
    path: list[tuple[float, float, float]]


class TwinMeetingParticipantView(ApiModel):
    actor_key: str
    seat_key: str | None
    position: str
    finding: str
    status: str
    speaking_order: int


class TwinMeetingSeatView(ApiModel):
    key: str
    label: str
    layout_key: str
    position: tuple[float, float, float]
    rotation_y: float
    status: str


class TwinMeetingView(ApiModel):
    key: str
    title: str
    topic: str
    status: str
    evidence_snapshot: str
    decision: str
    room_space_key: str
    next_transition_at: datetime | None
    updated_at: datetime
    participants: list[TwinMeetingParticipantView]
    seats: list[TwinMeetingSeatView]


class TwinObjectActionView(ApiModel):
    key: str
    label: str
    action_type: Literal["navigate", "enter", "focus"]
    href: str | None = None
    target_key: str | None = None
    icon_key: str
    emphasis: Literal["primary", "secondary"] = "secondary"


class TwinInteractionView(ApiModel):
    entity_key: str
    entity_type: Literal["space", "actor", "hotspot", "meeting-seat"]
    detail_route: str | None
    enter_space_key: str | None
    actions: list[TwinObjectActionView]


class TwinHotspotView(ApiModel):
    key: str
    scene_key: str
    label: str
    hotspot_type: str
    status: str
    severity: str
    business_ref: str
    metric_key: str | None
    position: tuple[float, float, float]
    details: dict[str, object]


class TwinDataLayerView(ApiModel):
    key: str
    scene_key: str
    label: str
    category: str
    enabled_default: bool
    style: dict[str, object]


class SyncRunView(ApiModel):
    id: str
    source_key: str | None = None
    source_version: int | None = None
    status: str
    scenario: str
    volume_profile: str
    records_read: int
    records_written: int
    warning: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class PageView(ApiModel):
    offset: int
    limit: int
    total: int


class SyncRunListItem(ApiModel):
    id: str
    source_key: str
    source_name: str
    source_version: int | None = None
    status: str
    scenario: str
    volume_profile: str
    records_read: int
    records_written: int
    warning: str | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None


class SyncRunListResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    page: PageView
    status_counts: dict[str, int]
    items: list[SyncRunListItem]
    generated_at: datetime


class BusinessEntityView(ApiModel):
    id: str
    entity_type: str
    canonical_key: str
    display_name: str
    status: str
    attributes: dict[str, object]
    attribute_count: int
    updated_at: datetime


class BusinessEntityListResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    page: PageView
    type_counts: dict[str, int]
    items: list[BusinessEntityView]
    generated_at: datetime


class MetricCatalogView(ApiModel):
    id: str
    key: str
    label: str
    description: str
    formula_expression: str
    unit: str
    dimensions: list[str]
    owner: str
    version: str
    status: str
    source_key: str | None
    current_value: float | None
    change_rate: float | None
    as_of: datetime | None
    updated_at: datetime


class MetricCatalogResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    page: PageView
    status_counts: dict[str, int]
    items: list[MetricCatalogView]
    generated_at: datetime


class MetricSeriesPointView(ApiModel):
    as_of: datetime
    value: float
    change_rate: float | None


class MetricSeriesView(ApiModel):
    key: str
    label: str
    unit: str
    scope_key: str
    definition_version: str
    latest_value: float | None
    period_change_rate: float | None
    minimum: float | None
    maximum: float | None
    points: list[MetricSeriesPointView]


class MetricSeriesResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    scope_key: str
    date_from: datetime | None
    date_to: datetime | None
    granularity: Literal["day"] = "day"
    series: list[MetricSeriesView]
    generated_at: datetime


class DataQualityView(ApiModel):
    id: str
    key: str
    name: str
    description: str
    category: str
    asset_type: str
    asset_key: str
    expectation: str
    severity: str
    rule_status: str
    result_status: str
    observed_value: str | None
    affected_records: int
    details: dict[str, object]
    sync_run_id: str | None
    checked_at: datetime | None


class DataQualityResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    page: PageView
    result_counts: dict[str, int]
    items: list[DataQualityView]
    generated_at: datetime


class CommerceOperationsSummary(ApiModel):
    order_count: int
    order_line_count: int
    paid_gmv_yuan: float
    gross_margin_rate: float
    refund_count: int
    refund_amount_yuan: float
    refund_rate: float
    inventory_sku_count: int
    inventory_value_yuan: float
    low_stock_sku_count: int
    advertising_spend_yuan: float
    attributed_revenue_yuan: float
    advertising_roi: float


class CommerceFunnelStepView(ApiModel):
    key: str
    label: str
    count: int
    amount_yuan: float
    conversion_rate: float


class CommerceStorePerformanceView(ApiModel):
    store_key: str
    store_name: str
    channel: str
    order_count: int
    paid_gmv_yuan: float
    gross_margin_rate: float
    refund_count: int
    refund_rate: float
    advertising_spend_yuan: float
    attributed_revenue_yuan: float
    advertising_roi: float


class CommerceExceptionView(ApiModel):
    key: str
    exception_type: str
    severity: Literal["warning", "critical"]
    title: str
    detail: str
    value: float
    unit: str
    related_keys: list[str]
    source_key: str
    sync_run_id: str


class CommerceOrderView(ApiModel):
    order_key: str
    store_key: str
    store_name: str
    customer_key: str
    channel: str
    status: str
    business_date: date
    paid_amount_yuan: float
    gross_margin_yuan: float
    item_count: int
    province: str
    source_key: str
    sync_run_id: str


class CommerceLineageAssetView(ApiModel):
    key: str
    label: str
    table_name: str
    record_count: int
    source_key: str
    source_schema_version: str
    mapping_version: str
    latest_sync_run_id: str | None


class CommerceOperationsResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    scope_key: str
    business_date_from: date | None
    business_date_to: date | None
    summary: CommerceOperationsSummary
    funnel: list[CommerceFunnelStepView]
    stores: list[CommerceStorePerformanceView]
    exceptions: list[CommerceExceptionView]
    recent_orders: list[CommerceOrderView]
    lineage: list[CommerceLineageAssetView]
    generated_at: datetime


class TwinOverviewResponse(ApiModel):
    schema_version: Literal[9] = 9
    data_mode: Literal["database"] = "database"
    enterprise: EnterpriseView
    database: DatabaseView
    sources: list[DataSourceView]
    metrics: list[MetricView]
    nodes: list[TwinNodeView]
    edges: list[TwinEdgeView]
    events: list[EventView]
    scene: TwinSceneView | None
    scenes: list[TwinSceneView]
    spaces: list[TwinSpaceView]
    actors: list[TwinActorView]
    routes: list[TwinRouteView]
    hotspots: list[TwinHotspotView]
    data_layers: list[TwinDataLayerView]
    interactions: list[TwinInteractionView]
    meeting: TwinMeetingView | None
    latest_sync: SyncRunView | None
    entity_count: int
    source_record_count: int
    commerce_fact_count: int
    customer_profile_count: int
    customer_touchpoint_count: int
    metric_definition_count: int
    knowledge_document_count: int
    knowledge_version_count: int
    knowledge_chunk_count: int
    role_twin_profile_count: int
    agent_run_count: int
    customer_operation_run_count: int
    tool_definition_count: int
    tool_invocation_count: int
    generated_at: datetime


class SyncRequest(ApiModel):
    projection_mode: Literal["inline", "deferred"] = "inline"
    client_request_key: str | None = None
    resource_key: str = Field(default="shops", min_length=1, max_length=120)
    resource_parameters: dict[str, str] = Field(default_factory=dict)
    window_start: datetime | None = None
    window_end: datetime | None = None
    scenario: Literal["normal", "delayed", "partial", "failure"] = "normal"
    volume_profile: Literal["small", "standard", "large"] = "standard"


class SyncResponse(ApiModel):
    run: SyncRunView


class SourceResourceView(ApiModel):
    key: str
    wave: str
    status: str
    schema_status: str = "schema_pending"
    schema_confirmation_available: bool = False
    enabled: bool = False
    read_only: bool
    projectable: bool
    method: str = ""
    path: str = ""
    required_parameters: list[str] = Field(default_factory=list)
    schedule_parameters: list[str] = Field(default_factory=list)
    window_fields: list[str] = Field(default_factory=list)
    window_format: str | None = None
    max_window_days: int = 7
    retention_days: int | None = None
    execution_mode: str = "pages"
    schedule_strategy: str | None = None
    fact_family: str | None = None
    can_execute: bool = False
    validation_status: str = "unvalidated"
    validation_run_id: str | None = None
    validation_error_code: str | None = None
    last_validated_at: datetime | None = None


class SourceResourceUpdateRequest(ApiModel):
    enabled: bool
    confirm_catalog_version: str | None = Field(default=None, min_length=1, max_length=96)


class SourceResourceValidationRequest(ApiModel):
    resource_parameters: dict[str, str] = Field(default_factory=dict)
    window_start: datetime | None = None
    window_end: datetime | None = None


class SyncCheckpointView(ApiModel):
    resource_key: str
    partition_key: str
    cursor: str | None
    page_number: int | None
    records_read: int | None
    updated_at: datetime | None
    status: str = "active"


class SyncCheckpointListResponse(ApiModel):
    schema_version: Literal[1] = 1
    page: PageView
    items: list[SyncCheckpointView]


class SourceResourceListResponse(ApiModel):
    catalog_version: str = ""
    provider_enabled: bool = False
    schema_version: Literal[1] = 1
    items: list[SourceResourceView]


class LingxingOfficialOperationView(ApiModel):
    id: str
    title: str
    document_path: str
    documentation_url: str
    method: Literal["GET", "POST"]
    path: str
    wave: Literal["W0", "W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8"]
    review_status: Literal[
        "read_candidate", "read_only_confirmed", "read_only_schema_pending"
    ]
    execution_status: Literal[
        "metadata_only", "runtime_raw_only", "runtime_projectable"
    ]
    schema_status: Literal["schema_pending", "confirmed"]
    resource_keys: list[str]
    document_sha256: str
    can_execute: bool
    contract_status: Literal["confirmed", "schema_pending", "document_changed"]
    required_fields: list[str] = Field(default_factory=list)
    scope_fields: list[str] = Field(default_factory=list)
    pagination_mode: str = "none"
    window_fields: list[str] = Field(default_factory=list)
    raw_eligible: bool = False
    registered: bool = False


class LingxingOfficialOperationListResponse(ApiModel):
    schema_version: Literal[1] = 1
    registry_version: str
    source: str
    summary: dict[str, object]
    page: PageView
    items: list[LingxingOfficialOperationView]


class OfficialResourceActivationRequest(ApiModel):
    enabled: bool = False


class OfficialResourceMaterializationResponse(ApiModel):
    eligible: int
    created: int
    existing: int
    enabled: int
    retired: int
    contract_version: str


class SourceRegistrationRequest(ApiModel):
    system_key: str
    name: str
    system_type: str = "lingxing"
    base_url: str = "https://openapi.lingxing.com"
    provider_key: str = "lingxing"
    business_unit_id: str | None = None
    credential_ref: str | None = Field(
        default=None, pattern=r"^(env|vault|secret):[A-Za-z0-9_.:-]{1,180}$"
    )


class SourceUpdateRequest(ApiModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    base_url: str | None = None
    status: str | None = None
    business_unit_id: str | None = None
    credential_ref: str | None = Field(
        default=None, pattern=r"^(env|vault|secret):[A-Za-z0-9_.:-]{1,180}$"
    )


class SourceBindingRequest(ApiModel):
    business_unit_id: str
    external_key: str
    canonical_type: str = "store"
    canonical_id: str
    mapping_version: str = "1"


class SourceBindingView(ApiModel):
    id: str
    enterprise_id: str
    business_unit_id: str | None
    source_system_id: str
    external_key: str
    canonical_type: str
    canonical_id: str
    status: str
    suggested_business_unit_id: str | None = None
    suggestion_reason: str | None = None
    suggestion_evidence: list[object] = Field(default_factory=list)
    suggestion_evidence_count: int = 0


class SourceBindingListResponse(ApiModel):
    schema_version: Literal[1] = 1
    page: PageView
    items: list[SourceBindingView]


class SourceBindingReviewRequest(ApiModel):
    status: Literal["approved", "rejected"]
    business_unit_id: str | None = Field(default=None, max_length=64)
    store_timezone: str | None = Field(default=None, max_length=64)


class SourceProbeView(ApiModel):
    source_key: str
    status: str
    read_only: bool
    reachable: bool
    detail: str


class MappingConflictView(ApiModel):
    id: str
    source_key: str
    external_object_key: str
    status: str
    candidates: list[object]
    reviewed_by: str | None
    reviewed_at: datetime | None
    resource_key: str | None = None
    raw_manifest_id: str | None = None
    error_code: str | None = None
    resolved_manifest_id: str | None = None


class MappingConflictListResponse(ApiModel):
    schema_version: Literal[1] = 1
    page: PageView
    status_counts: dict[str, int]
    items: list[MappingConflictView]


class MappingConflictReviewRequest(ApiModel):
    status: Literal["approved", "rejected"]
    expected_manifest_id: str | None = None


class SourceAuthorityRuleRequest(ApiModel):
    fact_family: str
    authority_resource_key: str
    supplement_resource_keys: list[str] = Field(default_factory=list)
    late_arrival_window_hours: int = 24


class SourceAuthorityRuleView(ApiModel):
    id: str
    enterprise_id: str
    fact_family: str
    authority_resource_key: str
    supplement_resource_keys: list[str]
    late_arrival_window_hours: int


class SourceRegistrationView(ApiModel):
    id: str
    enterprise_id: str
    business_unit_id: str | None = None
    system_key: str
    name: str
    system_type: str
    base_url: str
    provider_key: str | None
    access_mode: str
    status: str
    connection_status: str = "unknown"
    version: int
    created_at: datetime | None = None
    last_probe_at: datetime | None = None


class MeetingActionRequest(ApiModel):
    action: Literal["convene", "start", "decide", "reset"]


class MeetingActionResponse(ApiModel):
    meeting: TwinMeetingView
    overview: TwinOverviewResponse
