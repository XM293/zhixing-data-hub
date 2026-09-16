from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from zhixing_api.models import ApiModel

RiskLevel = Literal["healthy", "watch", "high", "critical"]
ExecutionMode = Literal["model", "evidence-fallback"]


class AnalysisScopeView(ApiModel):
    type: Literal["enterprise", "store"]
    key: str
    label: str


class AnalysisMetricPointView(ApiModel):
    as_of: datetime
    value: float


class AnalysisMetricView(ApiModel):
    key: str
    label: str
    unit: str
    latest_value: float
    period_change_rate: float | None
    minimum: float
    maximum: float
    status: RiskLevel
    status_reason: str
    evidence_ref: str
    points: list[AnalysisMetricPointView]


class AnalysisCommerceFactView(ApiModel):
    key: str
    domain: Literal["orders", "refunds", "inventory", "advertising", "exception"]
    label: str
    evidence_ref: str
    value: float
    unit: str
    status: RiskLevel
    detail: str
    related_keys: list[str]
    source_keys: list[str]
    sync_run_ids: list[str]


class AnalysisFindingView(ApiModel):
    kind: Literal["fact", "inference", "risk"]
    severity: RiskLevel
    text: str
    evidence_refs: list[str]


class AnalysisRecommendationView(ApiModel):
    title: str
    action: str
    owner_role: str
    priority: Literal["normal", "high", "urgent"]
    evidence_refs: list[str]
    success_metric: str
    stop_condition: str


class AnalysisResultPayload(ApiModel):
    headline: str
    summary: str
    confidence: Literal["high", "medium", "low"]
    metric_snapshot: list[AnalysisMetricView]
    commerce_fact_snapshot: list[AnalysisCommerceFactView] = Field(default_factory=list)
    findings: list[AnalysisFindingView]
    recommendations: list[AnalysisRecommendationView]
    unknowns: list[str]


class AnalysisEvidenceSnapshotView(ApiModel):
    id: str
    key: str
    content_hash: str
    item_count: int
    frozen_at: datetime


class AnalysisActionProposalView(ApiModel):
    recommendation_index: int
    proposal_key: str
    status: Literal["pending_approval", "approved", "rejected"]
    work_item_key: str | None
    work_item_status: Literal["ready", "claimed", "in_progress", "blocked", "completed"] | None


class BusinessAnalysisRunView(ApiModel):
    id: str
    analysis_type: Literal["store-review", "enterprise-review"]
    scope: AnalysisScopeView
    window_days: int
    status: Literal["completed", "failed"]
    risk_level: RiskLevel
    provider: str
    model: str
    execution_mode: ExecutionMode
    fallback_reason: str | None
    result: AnalysisResultPayload
    evidence_snapshot: AnalysisEvidenceSnapshotView
    action_proposals: list[AnalysisActionProposalView] = Field(default_factory=list)
    workspace_key: str | None = None
    initiated_by_principal_id: str
    initiated_by_name: str
    request_id: str
    run_id: str
    created_at: datetime
    completed_at: datetime


class BusinessBriefSectionView(ApiModel):
    key: str
    title: str
    items: list[str]


class BusinessBriefContent(ApiModel):
    headline: str
    sections: list[BusinessBriefSectionView]
    evidence_refs: list[str]


class BusinessBriefView(ApiModel):
    id: str
    key: str
    version_number: int
    brief_type: Literal["daily", "weekly", "exception"]
    scope: AnalysisScopeView
    title: str
    status: Literal["generated", "confirmed", "superseded"]
    source_analysis_run_id: str
    evidence_snapshot_key: str
    provider: str
    model: str
    execution_mode: ExecutionMode
    content: BusinessBriefContent
    created_by_principal_id: str
    created_by_name: str
    request_id: str
    run_id: str
    created_at: datetime


class AnalysisStudioStats(ApiModel):
    analysis_run_count: int
    brief_count: int
    high_risk_count: int
    model_run_count: int
    latest_completed_at: datetime | None


class AnalysisStudioResponse(ApiModel):
    schema_version: Literal[1] = 1
    data_mode: Literal["database"] = "database"
    actor_name: str
    can_run: bool
    can_propose: bool
    selected_scope: AnalysisScopeView
    available_scopes: list[AnalysisScopeView]
    stats: AnalysisStudioStats
    latest_run: BusinessAnalysisRunView | None
    runs: list[BusinessAnalysisRunView]
    briefs: list[BusinessBriefView]
    generated_at: datetime


class BusinessAnalysisRunRequest(ApiModel):
    scope_key: str = Field(min_length=2, max_length=160)
    window_days: int = Field(default=30, ge=7, le=90)
    client_request_key: str = Field(min_length=8, max_length=160)
    workspace_key: str | None = Field(default=None, min_length=2, max_length=64)


class BusinessAnalysisRunResponse(ApiModel):
    schema_version: Literal[1] = 1
    idempotent: bool
    run: BusinessAnalysisRunView
    brief: BusinessBriefView
    studio: AnalysisStudioResponse
