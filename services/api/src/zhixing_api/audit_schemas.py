from __future__ import annotations

from datetime import datetime
from typing import Literal

from zhixing_api.models import ApiModel

AuditSource = Literal[
    "authorization",
    "identity",
    "mcp",
    "tool",
    "worker",
    "agent",
    "action",
    "platform",
]
AuditSeverity = Literal["normal", "warning", "critical"]


class AuditFiltersView(ApiModel):
    source: AuditSource | None
    outcome: str | None
    actor_principal_id: str | None
    request_id: str | None
    run_id: str | None
    query: str | None
    start_at: datetime | None
    end_at: datetime | None


class AuditStatsView(ApiModel):
    total_events: int
    events_last_24h: int
    attention_events: int
    unique_actors: int
    correlated_runs: int


class AuditCountFacetView(ApiModel):
    key: str
    count: int


class AuditActorFacetView(ApiModel):
    principal_id: str
    display_name: str
    count: int


class AuditFacetsView(ApiModel):
    sources: list[AuditCountFacetView]
    outcomes: list[AuditCountFacetView]
    actors: list[AuditActorFacetView]


class AuditAttributeView(ApiModel):
    key: str
    label: str
    value: str


class AuditEventView(ApiModel):
    id: str
    source: AuditSource
    event_type: str
    outcome: str
    severity: AuditSeverity
    actor_principal_id: str | None
    actor_name: str
    subject_type: str
    subject_key: str
    summary: str
    request_id: str | None
    run_id: str | None
    agent_run_id: str | None
    duration_ms: int | None
    occurred_at: datetime
    attributes: list[AuditAttributeView]


class AuditPaginationView(ApiModel):
    offset: int
    limit: int
    total: int
    has_more: bool


class UnifiedAuditLedgerResponse(ApiModel):
    schema_version: Literal[1] = 1
    enterprise_id: str
    filters: AuditFiltersView
    stats: AuditStatsView
    facets: AuditFacetsView
    items: list[AuditEventView]
    pagination: AuditPaginationView
    generated_at: datetime
