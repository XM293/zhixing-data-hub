from datetime import datetime
from typing import Literal

from zhixing_api.identity_schemas import NavigationSectionView
from zhixing_api.models import ApiModel

WorkspaceKey = Literal[
    "executive",
    "manager",
    "operator",
    "service",
    "finance",
    "people",
    "data-governance",
    "platform-ops",
    "ai-ops",
]
DeliveryState = Literal["prototype", "implemented", "unavailable"]
Tone = Literal["positive", "warning", "critical", "info", "neutral"]


class WorkspaceScopeView(ApiModel):
    kind: str
    keys: list[str]
    label: str
    as_of: datetime


class WorkspaceProfileView(ApiModel):
    schema_version: Literal[1] = 1
    key: WorkspaceKey
    label: str
    audience: list[str]
    default_route: str
    navigation_keys: list[str]
    metric_keys: list[str]
    attention_query_keys: list[str]
    quick_action_keys: list[str]
    scene_key: str | None
    layout_version: int
    delivery_state: DeliveryState


class WorkspaceMetricView(ApiModel):
    key: str
    label: str
    value: float
    unit: str
    change_rate: float | None
    as_of: datetime
    status: Tone
    status_reason: str
    href: str | None
    evidence_refs: list[str]


class WorkspaceAttentionView(ApiModel):
    key: str
    kind: Literal["anomaly", "decision", "approval", "work", "system", "quality"]
    title: str
    detail: str
    severity: Literal["critical", "high", "warning", "info", "neutral"]
    status: str
    href: str | None
    evidence_refs: list[str]
    as_of: datetime | None


class WorkspaceActivityView(ApiModel):
    key: str
    kind: str
    title: str
    detail: str
    status: str
    href: str | None
    occurred_at: datetime


class WorkspaceFreshnessView(ApiModel):
    key: str
    label: str
    status: str
    as_of: datetime | None
    detail: str


class WorkspaceQuickActionView(ApiModel):
    key: str
    label: str
    href: str
    required_permission: str | None
    enabled: bool
    disabled_reason: str | None


class WorkspaceSceneView(ApiModel):
    key: str
    label: str
    route: str | None
    enabled: bool
    object_refs: list[str]
    layer_keys: list[str]


class WorkspaceCatalogResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    default_workspace_key: WorkspaceKey
    workspaces: list[WorkspaceProfileView]
    scope: WorkspaceScopeView
    generated_at: datetime


class WorkspaceReadModelResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    workspace: WorkspaceProfileView
    actor_name: str
    actor_position: str
    actor_organization: str
    scope: WorkspaceScopeView
    scope_context: dict[str, object]
    navigation: list[NavigationSectionView]
    metrics: list[WorkspaceMetricView]
    attention: list[WorkspaceAttentionView]
    decisions: list[WorkspaceAttentionView]
    work_items: list[WorkspaceAttentionView]
    activities: list[WorkspaceActivityView]
    freshness: list[WorkspaceFreshnessView]
    quick_actions: list[WorkspaceQuickActionView]
    scene: WorkspaceSceneView | None
    generated_at: datetime
