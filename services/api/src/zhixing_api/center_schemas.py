from typing import Literal

from pydantic import Field

from zhixing_api.identity_schemas import CurrentIdentityResponse
from zhixing_api.models import ApiModel


class CenterCatalogItem(ApiModel):
    key: str
    group_key: str
    label: str
    short_label: str
    icon_key: str
    href: str
    delivery_state: Literal["prototype", "implemented", "unavailable"]
    required_permissions: list[str]
    scope_level: Literal["group", "enterprise", "business_unit", "org_unit", "store", "warehouse"]
    scene_node_key: str | None = None


class CenterCatalogGroup(ApiModel):
    key: str
    label: str
    order: int
    items: list[CenterCatalogItem]


class CenterCatalogResponse(ApiModel):
    schema_version: Literal[1] = 1
    group_id: str | None
    enterprise_id: str
    groups: list[CenterCatalogGroup]
    resolved_at: str


class ScopeContextResponse(ApiModel):
    schema_version: Literal[2] = 2
    group_id: str | None
    group_name: str | None
    enterprise_id: str
    enterprise_name: str
    allowed_enterprise_ids: list[str]
    business_unit_ids: list[str]
    scope_version: str
    timezone: str
    currency_code: str | None
    current_enterprise_id: str
    selected_enterprise_ids: list[str]
    store_ids: list[str]
    warehouse_ids: list[str]
    scope_level: str
    base_currency: str | None
    consolidation_profile_version: str | None
    data_as_of: str | None


class ContextSwitchRequest(ApiModel):
    enterprise_id: str = Field(min_length=1, max_length=64)
    scope_level: Literal[
        "group", "enterprise", "business_unit", "store", "warehouse"
    ] = "enterprise"
    selected_enterprise_ids: list[str] = Field(default_factory=list, max_length=100)
    business_unit_ids: list[str] = Field(default_factory=list, max_length=100)
    store_ids: list[str] = Field(default_factory=list, max_length=1000)
    warehouse_ids: list[str] = Field(default_factory=list, max_length=1000)


class ContextSwitchResponse(ApiModel):
    schema_version: Literal[1] = 1
    context: ScopeContextResponse
    identity: CurrentIdentityResponse
