from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from zhixing_api.models import ApiModel


class SearchKnowledgeInput(ApiModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=5, ge=1, le=8)


class ReadPolicyInput(SearchKnowledgeInput):
    policy_key: str | None = Field(default=None, max_length=120)


class GetMetricInput(ApiModel):
    metric_key: str | None = Field(default=None, max_length=100)
    query: str | None = Field(default=None, max_length=160)
    scope_key: str = Field(min_length=1, max_length=160)
    limit: int = Field(default=10, ge=1, le=20)
    days: int = Field(default=1, ge=1, le=365)

    @model_validator(mode="after")
    def require_metric_selector(self) -> GetMetricInput:
        if not (self.metric_key or self.query):
            raise ValueError("metric_key 与 query 至少提供一个")
        return self


class QueryCommerceFactsInput(ApiModel):
    scope_key: str = Field(min_length=1, max_length=160)
    limit: int = Field(default=20, ge=1, le=50)


class QueryAuthoritativeOrdersInput(ApiModel):
    date_from: date
    date_to: date

    @model_validator(mode="after")
    def valid_dates(self) -> QueryAuthoritativeOrdersInput:
        if self.date_to <= self.date_from:
            raise ValueError("结束日期必须晚于开始日期")
        return self


class QueryCustomer360Input(ApiModel):
    scope_key: str = Field(min_length=1, max_length=160)
    customer_key: str | None = Field(default=None, min_length=1, max_length=160)
    limit: int = Field(default=20, ge=1, le=50)


class ToolDefinitionView(ApiModel):
    key: str
    display_name: str
    description: str
    risk_level: Literal["R0", "R1", "R2", "R3"]
    permission_key: str
    resource_type: str
    scope_resolver: str
    input_schema: dict[str, object]
    output_schema: dict[str, object]
    provider: str
    version: str
    timeout_seconds: int
    status: str


class ToolCatalogResponse(ApiModel):
    schema_version: Literal[1] = 1
    actor_key: str
    permission_set_version: str
    items: list[ToolDefinitionView]
    generated_at: datetime


class ToolInvokeRequest(ApiModel):
    parameters: dict[str, object] = Field(default_factory=dict)


class ToolInvokeResponse(ApiModel):
    schema_version: Literal[1] = 1
    invocation_id: str
    tool: ToolDefinitionView
    actor_key: str
    authentication_method: str
    permission_set_version: str
    session_permission_set_version: str | None
    permission_set_version_changed: bool
    gateway_session_id: str | None
    agent_run_id: str | None
    status: Literal["succeeded"]
    output: dict[str, object]
    duration_ms: int
    request_id: str
    run_id: str
    finished_at: datetime


class ToolInvocationView(ApiModel):
    id: str
    tool_key: str
    tool_version: str
    actor_name: str
    risk_level: str
    permission_key: str
    authentication_method: str
    permission_set_version: str
    session_permission_set_version: str | None
    permission_set_version_changed: bool
    gateway_session_id: str | None
    agent_run_id: str | None
    status: Literal["succeeded", "denied", "failed"]
    error_code: str | None
    duration_ms: int
    request_id: str
    run_id: str
    input_parameters: dict[str, object]
    output_summary: dict[str, object]
    started_at: datetime
    finished_at: datetime


class ToolAdminStats(ApiModel):
    active_tools: int
    r0_tools: int
    invocations: int
    succeeded: int
    denied: int
    failed: int


class ToolAdminOverviewResponse(ApiModel):
    schema_version: Literal[1] = 1
    enterprise_id: str
    stats: ToolAdminStats
    tools: list[ToolDefinitionView]
    recent_invocations: list[ToolInvocationView]
    generated_at: datetime
