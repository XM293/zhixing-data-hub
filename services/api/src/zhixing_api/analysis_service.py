from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal, TypedDict, cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext
from zhixing_api.ai_provider import AIProviderError, ResponsesAIProvider
from zhixing_api.analysis_schemas import (
    AnalysisActionProposalView,
    AnalysisCommerceFactView,
    AnalysisEvidenceSnapshotView,
    AnalysisFindingView,
    AnalysisMetricPointView,
    AnalysisMetricView,
    AnalysisRecommendationView,
    AnalysisResultPayload,
    AnalysisScopeView,
    AnalysisStudioResponse,
    AnalysisStudioStats,
    BusinessAnalysisRunResponse,
    BusinessAnalysisRunView,
    BusinessBriefContent,
    BusinessBriefSectionView,
    BusinessBriefView,
    RiskLevel,
)
from zhixing_api.config import Settings
from zhixing_api.data_center_schemas import CommerceOperationsResponse, MetricSeriesView
from zhixing_api.data_center_service import build_commerce_operations, query_metric_series
from zhixing_api.data_models import (
    ActionProposal,
    ActionWorkItem,
    BusinessAnalysisRun,
    BusinessBrief,
    Enterprise,
    EvidenceSnapshot,
    EvidenceSnapshotItem,
    MetricSnapshot,
    Principal,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.workspace_service import actor_snapshot_with_workspace

ANALYSIS_METRIC_KEYS = ["gmv_today", "orders_today", "refund_rate", "ad_roi"]
RISK_ORDER: dict[str, int] = {"healthy": 0, "watch": 1, "high": 2, "critical": 3}
SCOPE_LABELS = {
    "store-flagship": "旗舰店",
    "store-outlet": "折扣店",
}


class FallbackPayload(TypedDict):
    headline: str
    summary: str
    findings: list[AnalysisFindingView]
    recommendations: list[AnalysisRecommendationView]
    unknowns: list[str]

AI_ANALYSIS_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["inference", "risk"]},
                    "severity": {
                        "type": "string",
                        "enum": ["healthy", "watch", "high", "critical"],
                    },
                    "text": {"type": "string"},
                    "evidence_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["kind", "severity", "text", "evidence_refs"],
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "action": {"type": "string"},
                    "owner_role": {"type": "string"},
                    "priority": {"type": "string", "enum": ["normal", "high", "urgent"]},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "success_metric": {"type": "string"},
                    "stop_condition": {"type": "string"},
                },
                "required": [
                    "title", "action", "owner_role", "priority", "evidence_refs",
                    "success_metric", "stop_condition",
                ],
            },
        },
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": [
        "headline", "summary", "findings", "recommendations", "unknowns", "confidence"
    ],
}


def available_analysis_scopes(database: Database, actor: ActorContext) -> list[AnalysisScopeView]:
    enterprise_allowed = any(
        scope.scope_type == "enterprise"
        and actor.enterprise_id in scope.scope_ids
        and scope.effect == "allow"
        for scope in actor.scopes
    )
    with database.session() as session:
        enterprise = session.get(Enterprise, actor.enterprise_id)
        metric_scopes = list(
            session.scalars(
                select(MetricSnapshot.scope_key)
                .where(MetricSnapshot.enterprise_id == actor.enterprise_id)
                .distinct()
                .order_by(MetricSnapshot.scope_key)
            )
        )
    scopes: list[AnalysisScopeView] = []
    if enterprise_allowed:
        scopes.append(
            AnalysisScopeView(
                type="enterprise",
                key="enterprise",
                label=enterprise.name if enterprise else "全企业",
            )
        )
        store_keys = [key for key in metric_scopes if key != "enterprise"]
    else:
        store_keys = sorted(
            {
                scope_id
                for scope in actor.scopes
                if scope.scope_type == "store" and scope.effect == "allow"
                for scope_id in scope.scope_ids
            }
        )
    scopes.extend(
        AnalysisScopeView(type="store", key=key, label=SCOPE_LABELS.get(key, key))
        for key in store_keys
    )
    return scopes


def resolve_analysis_scope(
    database: Database,
    actor: ActorContext,
    requested_scope_key: str | None,
) -> AnalysisScopeView:
    available = available_analysis_scopes(database, actor)
    if not available:
        raise ApiProblem(
            status_code=403,
            code="analysis.scope_unavailable",
            message="当前数据库身份没有可用于经营分析的数据范围",
        )
    if requested_scope_key:
        selected = next((item for item in available if item.key == requested_scope_key), None)
        if selected is None:
            raise ApiProblem(
                status_code=403,
                code="authorization.scope_denied",
                message="当前数据库身份的数据范围不包含目标分析范围",
                details={"scope_key": requested_scope_key},
            )
        return selected
    available_by_key = {item.key: item for item in available}
    with database.session() as session:
        latest_scope_key = session.scalar(
            select(BusinessAnalysisRun.scope_key)
            .where(
                BusinessAnalysisRun.enterprise_id == actor.enterprise_id,
                BusinessAnalysisRun.scope_key.in_(available_by_key),
            )
            .order_by(BusinessAnalysisRun.completed_at.desc())
            .limit(1)
        )
    if latest_scope_key:
        return available_by_key[latest_scope_key]
    return next((item for item in available if item.type == "store"), available[0])


def list_analysis_studio(
    database: Database,
    actor: ActorContext,
    *,
    scope_key: str | None = None,
) -> AnalysisStudioResponse:
    selected_scope = resolve_analysis_scope(database, actor, scope_key)
    available_scopes = available_analysis_scopes(database, actor)
    with database.session() as session:
        runs = list(
            session.scalars(
                select(BusinessAnalysisRun)
                .where(
                    BusinessAnalysisRun.enterprise_id == actor.enterprise_id,
                    BusinessAnalysisRun.scope_key == selected_scope.key,
                )
                .order_by(BusinessAnalysisRun.completed_at.desc())
                .limit(20)
            )
        )
        briefs = list(
            session.scalars(
                select(BusinessBrief)
                .where(
                    BusinessBrief.enterprise_id == actor.enterprise_id,
                    BusinessBrief.scope_key == selected_scope.key,
                )
                .order_by(BusinessBrief.created_at.desc())
                .limit(30)
            )
        )
        principal_ids = {
            *(item.initiated_by_principal_id for item in runs),
            *(item.created_by_principal_id for item in briefs),
        }
        principals = {
            item.id: item
            for item in session.scalars(select(Principal).where(Principal.id.in_(principal_ids)))
        } if principal_ids else {}
        snapshot_ids = {
            *(item.evidence_snapshot_id for item in runs),
            *(item.evidence_snapshot_id for item in briefs),
        }
        snapshots = {
            item.id: item
            for item in session.scalars(
                select(EvidenceSnapshot).where(EvidenceSnapshot.id.in_(snapshot_ids))
            )
        } if snapshot_ids else {}
        run_ids = [item.id for item in runs]
        action_proposals = list(
            session.scalars(
                select(ActionProposal).where(
                    ActionProposal.business_analysis_run_id.in_(run_ids)
                )
            )
        ) if run_ids else []
        proposal_ids = [item.id for item in action_proposals]
        work_items = {
            item.proposal_id: item
            for item in session.scalars(
                select(ActionWorkItem).where(ActionWorkItem.proposal_id.in_(proposal_ids))
            )
        } if proposal_ids else {}
        action_views_by_run: dict[str, list[AnalysisActionProposalView]] = {}
        for proposal in action_proposals:
            if proposal.business_analysis_run_id is None:
                continue
            work_item = work_items.get(proposal.id)
            action_views_by_run.setdefault(proposal.business_analysis_run_id, []).append(
                AnalysisActionProposalView(
                    recommendation_index=proposal.source_action_index,
                    proposal_key=proposal.proposal_key,
                    status=cast(
                        Literal["pending_approval", "approved", "rejected"],
                        proposal.status,
                    ),
                    work_item_key=work_item.work_key if work_item else None,
                    work_item_status=(
                        cast(
                            Literal[
                                "ready", "claimed", "in_progress", "blocked", "completed"
                            ],
                            work_item.status,
                        )
                        if work_item
                        else None
                    ),
                )
            )
        for views in action_views_by_run.values():
            views.sort(key=lambda item: item.recommendation_index)
    run_views = [
        _run_view(
            item,
            snapshots[item.evidence_snapshot_id],
            principals,
            action_views_by_run.get(item.id, []),
        )
        for item in runs
    ]
    brief_views = [
        _brief_view(item, snapshots[item.evidence_snapshot_id], principals) for item in briefs
    ]
    return AnalysisStudioResponse(
        actor_name=actor.display_name,
        can_run="analysis.run" in actor.permissions,
        can_propose="action.propose" in actor.permissions,
        selected_scope=selected_scope,
        available_scopes=available_scopes,
        stats=AnalysisStudioStats(
            analysis_run_count=len(runs),
            brief_count=len(briefs),
            high_risk_count=sum(item.risk_level in {"high", "critical"} for item in runs),
            model_run_count=sum(item.execution_mode == "model" for item in runs),
            latest_completed_at=runs[0].completed_at if runs else None,
        ),
        latest_run=run_views[0] if run_views else None,
        runs=run_views,
        briefs=brief_views,
        generated_at=datetime.now(UTC),
    )


async def run_business_analysis(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    actor: ActorContext,
    *,
    scope: AnalysisScopeView,
    window_days: int,
    client_request_key: str,
    workspace_key: str | None = None,
) -> BusinessAnalysisRunResponse:
    with database.session() as session:
        existing = session.scalar(
            select(BusinessAnalysisRun).where(
                BusinessAnalysisRun.enterprise_id == actor.enterprise_id,
                BusinessAnalysisRun.idempotency_key == client_request_key,
            )
        )
        if existing is not None:
            if existing.scope_key != scope.key or existing.window_days != window_days:
                raise ApiProblem(
                    status_code=409,
                    code="analysis.idempotency_conflict",
                    message="该幂等键已用于不同的经营分析请求",
                )
            brief = session.scalar(
                select(BusinessBrief).where(
                    BusinessBrief.source_analysis_run_id == existing.id
                )
            )
            if brief is None:
                raise ApiProblem(
                    status_code=409,
                    code="analysis.brief_missing",
                    message="重复分析存在但关联简报缺失",
                )
            run_id = existing.id
            brief_id = brief.id
        else:
            run_id = ""
            brief_id = ""
    if run_id:
        studio = list_analysis_studio(database, actor, scope_key=scope.key)
        run_view = next(item for item in studio.runs if item.id == run_id)
        brief_view = next(item for item in studio.briefs if item.id == brief_id)
        return BusinessAnalysisRunResponse(
            idempotent=True,
            run=run_view,
            brief=brief_view,
            studio=studio,
        )

    series_response = query_metric_series(
        database,
        metric_keys=ANALYSIS_METRIC_KEYS,
        scope_key=scope.key,
        days=window_days,
        enterprise_id=actor.enterprise_id,
    )
    if not series_response.series or not any(item.points for item in series_response.series):
        raise ApiProblem(
            status_code=409,
            code="analysis.metric_context_missing",
            message="目标范围尚无可用于诊断的历史指标，请先完成数据同步",
            details={"scope_key": scope.key, "window_days": window_days},
        )

    now = datetime.now(UTC)
    analysis_id = f"business_analysis_{uuid4().hex}"
    snapshot, metric_views, commerce_views = _freeze_analysis_evidence(
        database,
        actor,
        scope=scope,
        window_days=window_days,
        analysis_id=analysis_id,
        series=series_response.series,
        now=now,
    )
    risk_level = _highest_risk(
        [*(item.status for item in metric_views), *(item.status for item in commerce_views)]
    )
    facts = [
        *(_metric_fact_finding(item) for item in metric_views),
        *(_commerce_fact_finding(item) for item in commerce_views),
    ]
    deterministic_unknowns = _commerce_unknowns(scope, commerce_views)
    fallback = _fallback_analysis(
        scope,
        metric_views,
        commerce_views,
        risk_level,
        deterministic_unknowns,
    )
    fallback_reason: str | None = None
    try:
        completion = await provider.generate(
            settings,
            instructions=(
                "你是企业经营分析负责人。只能依据输入中的 E 编号指标与经营事实证据形成判断，"
                "不能改写事实数值，也不能假设归因已经成立。输出区分推断、风险、建议和未知项；"
                "建议必须包含责任角色、成功指标和停止条件，不输出隐藏思维过程。"
            ),
            input_text=_analysis_input(scope, window_days, metric_views, commerce_views),
            run_id=analysis_id,
            schema_name="business_store_review",
            response_schema=AI_ANALYSIS_SCHEMA,
        )
        model_payload = completion.payload
        model_findings = [
            AnalysisFindingView.model_validate(item)
            for item in cast(list[object], model_payload.get("findings", []))
        ]
        model_recommendations = [
            AnalysisRecommendationView.model_validate(item)
            for item in cast(list[object], model_payload.get("recommendations", []))
        ]
        allowed_refs = {
            *(item.evidence_ref for item in metric_views),
            *(item.evidence_ref for item in commerce_views),
        }
        _validate_refs(model_findings, model_recommendations, allowed_refs)
        result = AnalysisResultPayload(
            headline=str(model_payload["headline"]),
            summary=str(model_payload["summary"]),
            confidence=cast(Literal["high", "medium", "low"], model_payload["confidence"]),
            metric_snapshot=metric_views,
            commerce_fact_snapshot=commerce_views,
            findings=[*facts, *model_findings],
            recommendations=model_recommendations,
            unknowns=_deduplicate_strings(
                [
                    *(str(item) for item in cast(list[object], model_payload["unknowns"])),
                    *deterministic_unknowns,
                ]
            ),
        )
        execution_mode: Literal["model", "evidence-fallback"] = "model"
        provider_name = "openai-compatible-responses"
    except (AIProviderError, KeyError, TypeError, ValueError) as exc:
        result = AnalysisResultPayload(
            headline=fallback["headline"],
            summary=fallback["summary"],
            confidence="medium",
            metric_snapshot=metric_views,
            commerce_fact_snapshot=commerce_views,
            findings=[*facts, *fallback["findings"]],
            recommendations=fallback["recommendations"],
            unknowns=fallback["unknowns"],
        )
        execution_mode = "evidence-fallback"
        provider_name = "local-evidence"
        fallback_reason = str(exc)

    with database.session() as session:
        run = BusinessAnalysisRun(
            id=analysis_id,
            enterprise_id=actor.enterprise_id,
            analysis_type="enterprise-review" if scope.type == "enterprise" else "store-review",
            scope_type=scope.type,
            scope_key=scope.key,
            scope_label=scope.label,
            window_days=window_days,
            status="completed",
            risk_level=risk_level,
            provider=provider_name,
            model=settings.ai_model if execution_mode == "model" else "deterministic-v1",
            execution_mode=execution_mode,
            fallback_reason=fallback_reason,
            evidence_snapshot_id=snapshot.id,
            result=result.model_dump(mode="json"),
            initiated_by_principal_id=actor.principal_id,
            actor_snapshot=actor_snapshot_with_workspace(actor, workspace_key),
            idempotency_key=client_request_key,
            request_id=actor.request_id,
            run_id=actor.run_id,
            created_at=now,
            completed_at=datetime.now(UTC),
        )
        session.add(run)
        session.flush()
        brief = _new_brief(session, run, result, actor, now, workspace_key=workspace_key)
        session.add(brief)
        session.commit()
        brief_id = brief.id

    studio = list_analysis_studio(database, actor, scope_key=scope.key)
    run_view = next(item for item in studio.runs if item.id == analysis_id)
    brief_view = next(item for item in studio.briefs if item.id == brief_id)
    return BusinessAnalysisRunResponse(
        idempotent=False,
        run=run_view,
        brief=brief_view,
        studio=studio,
    )


def _freeze_analysis_evidence(
    database: Database,
    actor: ActorContext,
    *,
    scope: AnalysisScopeView,
    window_days: int,
    analysis_id: str,
    series: list[MetricSeriesView],
    now: datetime,
) -> tuple[
    EvidenceSnapshot,
    list[AnalysisMetricView],
    list[AnalysisCommerceFactView],
]:
    metric_views: list[AnalysisMetricView] = []
    frozen_items: list[dict[str, object]] = []
    for index, metric in enumerate(series, start=1):
        points = list(metric.points)
        if (
            not points
            or metric.latest_value is None
            or metric.minimum is None
            or metric.maximum is None
        ):
            continue
        status, reason = _metric_risk(
            metric.key,
            float(metric.latest_value),
            float(metric.minimum),
            float(metric.maximum),
            metric.period_change_rate,
        )
        ref = f"E{index}"
        point_views = [
            AnalysisMetricPointView(as_of=item.as_of, value=item.value) for item in points
        ]
        view = AnalysisMetricView(
            key=metric.key,
            label=metric.label,
            unit=metric.unit,
            latest_value=float(metric.latest_value),
            period_change_rate=metric.period_change_rate,
            minimum=float(metric.minimum),
            maximum=float(metric.maximum),
            status=status,
            status_reason=reason,
            evidence_ref=ref,
            points=point_views,
        )
        metric_views.append(view)
        frozen_items.append(
            {
                "type": "metric-series",
                "key": view.key,
                "version_ref": metric.definition_version,
                "label": f"{view.label} · {scope.label}",
                "payload": view.model_dump(mode="json"),
            }
        )
    if not metric_views:
        raise ApiProblem(
            status_code=409,
            code="analysis.metric_context_missing",
            message="历史指标存在但没有可冻结的数据点",
        )
    try:
        commerce = build_commerce_operations(
            database,
            scope_key=scope.key,
            enterprise_id=actor.enterprise_id,
        )
    except ApiProblem as exc:
        if exc.code != "commerce.scope_mapping_missing":
            raise
        commerce = None
    commerce_views = _commerce_fact_views(
        commerce,
        first_evidence_index=(
            max(int(item.evidence_ref[1:]) for item in metric_views) + 1
        ),
    )
    for fact_view in commerce_views:
        frozen_items.append(
            {
                "type": (
                    "commerce-exception"
                    if fact_view.domain == "exception"
                    else "commerce-fact-summary"
                ),
                "key": fact_view.key,
                "version_ref": "|".join(fact_view.sync_run_ids) or "not-synced",
                "label": f"{fact_view.label} · {scope.label}",
                "payload": fact_view.model_dump(mode="json"),
            }
        )
    serialized = json.dumps(frozen_items, ensure_ascii=False, sort_keys=True)
    content_hash = sha256(serialized.encode("utf-8")).hexdigest()
    snapshot = EvidenceSnapshot(
        id=f"evidence_snapshot_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        snapshot_key=f"evs-analysis-{uuid4().hex[:12]}",
        purpose="business-analysis",
        query=(
            f"{scope.key}:{window_days}d:{','.join(ANALYSIS_METRIC_KEYS)}:"
            "canonical-commerce-facts"
        ),
        content_hash=content_hash,
        item_count=len(frozen_items),
        frozen_at=now,
    )
    with database.session() as session:
        session.add(snapshot)
        for rank, item in enumerate(frozen_items, start=1):
            session.add(
                EvidenceSnapshotItem(
                    id=f"evidence_item_{uuid4().hex}",
                    snapshot_id=snapshot.id,
                    item_type=str(item["type"]),
                    item_key=str(item["key"]),
                    version_ref=str(item["version_ref"]),
                    label=str(item["label"]),
                    payload=cast(dict[str, object], item["payload"]),
                    rank=rank,
                )
            )
        session.commit()
    return snapshot, metric_views, commerce_views


def _commerce_fact_views(
    commerce: CommerceOperationsResponse | None,
    *,
    first_evidence_index: int,
) -> list[AnalysisCommerceFactView]:
    if commerce is None or not any(item.record_count for item in commerce.lineage):
        return []
    lineage = {item.key: item for item in commerce.lineage}
    summary = commerce.summary
    views: list[AnalysisCommerceFactView] = []

    def add_summary(
        *,
        key: str,
        domain: Literal["orders", "refunds", "inventory", "advertising"],
        label: str,
        value: float,
        unit: str,
        status: RiskLevel,
        detail: str,
        lineage_keys: tuple[str, ...],
    ) -> None:
        source_keys, sync_run_ids = _commerce_lineage_refs(commerce, lineage_keys)
        views.append(
            AnalysisCommerceFactView(
                key=key,
                domain=domain,
                label=label,
                evidence_ref=f"E{first_evidence_index + len(views)}",
                value=value,
                unit=unit,
                status=status,
                detail=detail,
                related_keys=list(lineage_keys),
                source_keys=source_keys,
                sync_run_ids=sync_run_ids,
            )
        )

    if lineage.get("orders") and lineage["orders"].record_count:
        add_summary(
            key="commerce-summary:orders",
            domain="orders",
            label="订单与毛利事实",
            value=summary.paid_gmv_yuan,
            unit="元",
            status=_exception_risk(commerce, "margin"),
            detail=(
                f"{summary.order_count} 笔订单、{summary.order_line_count} 条订单行，"
                f"支付成交 {summary.paid_gmv_yuan:,.2f} 元，"
                f"规范成本口径毛利率 {summary.gross_margin_rate * 100:.2f}%。"
            ),
            lineage_keys=("orders", "order-lines"),
        )
    if lineage.get("refunds") and lineage["refunds"].record_count:
        add_summary(
            key="commerce-summary:refunds",
            domain="refunds",
            label="退款事实",
            value=summary.refund_rate * 100,
            unit="%",
            status=_refund_fact_risk(summary.refund_rate),
            detail=(
                f"{summary.refund_count} 笔退款，退款金额 {summary.refund_amount_yuan:,.2f} 元，"
                f"占支付成交 {summary.refund_rate * 100:.2f}%。"
            ),
            lineage_keys=("refunds", "orders"),
        )
    if lineage.get("inventory") and lineage["inventory"].record_count:
        low_stock_rate = (
            summary.low_stock_sku_count / summary.inventory_sku_count
            if summary.inventory_sku_count
            else 0.0
        )
        add_summary(
            key="commerce-summary:inventory",
            domain="inventory",
            label="库存事实",
            value=float(summary.low_stock_sku_count),
            unit="SKU",
            status=_inventory_fact_risk(low_stock_rate),
            detail=(
                f"{summary.inventory_sku_count} 个库存 SKU，"
                f"{summary.low_stock_sku_count} 个低于安全线，"
                f"库存成本价值 {summary.inventory_value_yuan:,.2f} 元。"
            ),
            lineage_keys=("inventory",),
        )
    if lineage.get("advertising") and lineage["advertising"].record_count:
        add_summary(
            key="commerce-summary:advertising",
            domain="advertising",
            label="广告投放事实",
            value=summary.advertising_roi,
            unit="x",
            status=_advertising_fact_risk(summary.advertising_roi),
            detail=(
                f"广告消耗 {summary.advertising_spend_yuan:,.2f} 元，"
                f"归因成交 {summary.attributed_revenue_yuan:,.2f} 元，"
                f"规范归因 ROI 为 {summary.advertising_roi:.2f}。"
            ),
            lineage_keys=("advertising",),
        )

    for exception in commerce.exceptions[:6]:
        views.append(
            AnalysisCommerceFactView(
                key=f"commerce-exception:{exception.key}",
                domain="exception",
                label=exception.title,
                evidence_ref=f"E{first_evidence_index + len(views)}",
                value=exception.value,
                unit=exception.unit,
                status="critical" if exception.severity == "critical" else "watch",
                detail=exception.detail,
                related_keys=exception.related_keys,
                source_keys=[exception.source_key],
                sync_run_ids=[exception.sync_run_id],
            )
        )
    return views


def _commerce_lineage_refs(
    commerce: CommerceOperationsResponse,
    keys: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    selected = [item for item in commerce.lineage if item.key in keys and item.record_count]
    source_keys = sorted({item.source_key for item in selected if item.source_key != "not-synced"})
    sync_run_ids = sorted(
        {item.latest_sync_run_id for item in selected if item.latest_sync_run_id is not None}
    )
    return source_keys, sync_run_ids


def _exception_risk(commerce: CommerceOperationsResponse, exception_type: str) -> RiskLevel:
    levels = [
        "critical" if item.severity == "critical" else "watch"
        for item in commerce.exceptions
        if item.exception_type == exception_type
    ]
    return _highest_risk(cast(list[RiskLevel], levels)) if levels else "healthy"


def _refund_fact_risk(rate: float) -> RiskLevel:
    if rate >= 0.06:
        return "critical"
    if rate >= 0.055:
        return "high"
    if rate >= 0.05:
        return "watch"
    return "healthy"


def _advertising_fact_risk(roi: float) -> RiskLevel:
    if roi < 2.0:
        return "critical"
    if roi < 2.5:
        return "high"
    if roi < 3.0:
        return "watch"
    return "healthy"


def _inventory_fact_risk(low_stock_rate: float) -> RiskLevel:
    if low_stock_rate >= 0.2:
        return "critical"
    if low_stock_rate >= 0.1:
        return "high"
    if low_stock_rate > 0:
        return "watch"
    return "healthy"


def _metric_risk(
    key: str,
    latest: float,
    minimum: float,
    maximum: float,
    change: float | None,
) -> tuple[RiskLevel, str]:
    if key == "refund_rate":
        observed = max(latest, maximum)
        if observed >= 6.0:
            return "critical", "观察窗口内退款率达到 6.0% 以上"
        if observed >= 5.5:
            return "high", "观察窗口内退款率超过 5.5% 目标线"
        if observed >= 5.0:
            return "watch", "退款率接近 5.5% 目标线"
        return "healthy", "退款率保持在首期目标线以内"
    if key == "ad_roi":
        if latest < 2.0 or minimum < 2.0:
            return "critical", "广告 ROI 曾低于 2.0"
        if latest < 2.5 or minimum < 2.5:
            return "high", "广告 ROI 曾低于 2.5 停止条件"
        if latest < 3.0 or minimum < 3.0:
            return "watch", "广告 ROI 在观察窗口内出现低于 3.0 的波动"
        return "healthy", "广告 ROI 保持在 3.0 以上"
    if change is not None:
        if change <= -0.15:
            return "critical", "观察窗口较期初下降 15% 以上"
        if change <= -0.08:
            return "high", "观察窗口较期初下降 8% 以上"
        if change <= -0.03:
            return "watch", "观察窗口较期初下降 3% 以上"
    return "healthy", "观察窗口趋势未触发下降阈值"


def _metric_fact_finding(metric: AnalysisMetricView) -> AnalysisFindingView:
    change_text = (
        "无可比期"
        if metric.period_change_rate is None
        else f"较窗口期初{'上升' if metric.period_change_rate >= 0 else '下降'}"
        f" {abs(metric.period_change_rate) * 100:.1f}%"
    )
    return AnalysisFindingView(
        kind="fact",
        severity=metric.status,
        text=(
            f"{metric.label}最新为 {_format_metric(metric.latest_value, metric.unit)}，"
            f"{change_text}；区间为 {_format_metric(metric.minimum, metric.unit)} 至 "
            f"{_format_metric(metric.maximum, metric.unit)}。"
        ),
        evidence_refs=[metric.evidence_ref],
    )


def _commerce_fact_finding(fact: AnalysisCommerceFactView) -> AnalysisFindingView:
    return AnalysisFindingView(
        kind="fact",
        severity=fact.status,
        text=f"{fact.label}：{fact.detail}",
        evidence_refs=[fact.evidence_ref],
    )


def _fallback_analysis(
    scope: AnalysisScopeView,
    metrics: list[AnalysisMetricView],
    commerce_facts: list[AnalysisCommerceFactView],
    risk: RiskLevel,
    deterministic_unknowns: list[str],
) -> FallbackPayload:
    risky_metrics = [item for item in metrics if item.status != "healthy"]
    risky_commerce = [item for item in commerce_facts if item.status != "healthy"]
    risky_count = len(risky_metrics) + len(risky_commerce)
    if risky_count:
        headline = f"{scope.label}有 {risky_count} 项指标或经营事实需要复核"
        summary = "指标与规范经营事实已冻结；当前先按阈值和异常规则识别风险，不把相关性解释为因果。"
    else:
        headline = f"{scope.label}核心指标与已接入经营事实处于健康区间"
        summary = "当前已接入证据未触发首期阈值，仍需持续观察尚未映射的数据维度。"
    findings = [
        AnalysisFindingView(
            kind="risk" if item.status in {"high", "critical"} else "inference",
            severity=item.status,
            text=f"{item.label}：{item.status_reason}。",
            evidence_refs=[item.evidence_ref],
        )
        for item in risky_metrics
    ]
    findings.extend(
        AnalysisFindingView(
            kind="risk" if item.status in {"high", "critical"} else "inference",
            severity=item.status,
            text=f"{item.label}：{item.detail}",
            evidence_refs=[item.evidence_ref],
        )
        for item in risky_commerce
    )
    recommendations = [
        *(_fallback_recommendation(item) for item in risky_metrics),
        *(_fallback_commerce_recommendation(item) for item in risky_commerce),
    ]
    if not recommendations:
        recommendations = [
            AnalysisRecommendationView(
                title="保持日度观察",
                action=(
                    "继续按当前数据口径跟踪成交、订单、退款率和广告 ROI，"
                    "出现阈值突破时再发起专项诊断。"
                ),
                owner_role="运营经理",
                priority="normal",
                evidence_refs=[item.evidence_ref for item in metrics],
                success_metric="核心指标保持在当前健康区间",
                stop_condition="任一指标进入高风险或严重风险",
            )
        ]
    return {
        "headline": headline,
        "summary": summary,
        "findings": findings,
        "recommendations": recommendations,
        "unknowns": deterministic_unknowns,
    }


def _fallback_recommendation(metric: AnalysisMetricView) -> AnalysisRecommendationView:
    if metric.key == "ad_roi":
        return AnalysisRecommendationView(
            title="复核低效投放日",
            action=(
                "按平台、计划、素材和人群拆分低 ROI 日期，先形成预算调整提案，"
                "不直接修改外部广告账户。"
            ),
            owner_role="运营经理",
            priority="high" if metric.status in {"high", "critical"} else "normal",
            evidence_refs=[metric.evidence_ref],
            success_metric="广告 ROI 连续 7 天不低于 3.0",
            stop_condition="广告 ROI 低于 2.5 时停止扩量并升级复核",
        )
    if metric.key == "refund_rate":
        return AnalysisRecommendationView(
            title="定位退款结构",
            action="按 SKU、原因和渠道拆分退款金额，确认是否由商品质量、履约或活动预期偏差驱动。",
            owner_role="运营经理",
            priority="urgent" if metric.status == "critical" else "high",
            evidence_refs=[metric.evidence_ref],
            success_metric="退款率回到 5.5% 以下",
            stop_condition="退款率达到 6.0% 时在 2 个工作日内完成专项复盘",
        )
    return AnalysisRecommendationView(
        title=f"复核{metric.label}变化",
        action=f"按渠道、商品和活动拆分{metric.label}变化，并将可验证原因形成经营行动提案。",
        owner_role="运营经理",
        priority="high" if metric.status in {"high", "critical"} else "normal",
        evidence_refs=[metric.evidence_ref],
        success_metric=f"{metric.label}恢复到观察窗口期初水平",
        stop_condition=f"{metric.label}继续下降 3% 时升级人工复核",
    )


def _fallback_commerce_recommendation(
    fact: AnalysisCommerceFactView,
) -> AnalysisRecommendationView:
    if fact.domain == "advertising":
        action = "按广告计划、商品和日期复核低回报记录，先形成预算调整提案，不直接修改外部账户。"
        success_metric = "广告归因 ROI 连续 7 天不低于 3.0"
        stop_condition = "广告归因 ROI 低于 2.5 时停止扩量并升级人工复核"
        owner = "投放负责人"
    elif fact.domain == "refunds":
        action = "按 SKU、退款原因和渠道拆分退款事实，确认集中退款是否需要商品或履约专项处理。"
        success_metric = "规范事实退款率回到 5.5% 以下"
        stop_condition = "退款率达到 6.0% 时启动专项复盘"
        owner = "运营经理"
    elif fact.domain == "inventory":
        action = "核对低库存 SKU 的可售、安全库存与在途数量，形成补货或调拨提案。"
        success_metric = "低库存 SKU 数持续下降"
        stop_condition = "可售库存低于安全线 50% 时升级供应链负责人"
        owner = "供应链负责人"
    else:
        action = (
            f"复核异常关联对象 {', '.join(fact.related_keys[:4])}，"
            "确认事实后再创建受控行动提案。"
        )
        success_metric = "异常事实完成归因并形成可验证处理结果"
        stop_condition = "异常继续扩大或影响客户时升级负责人"
        owner = "运营经理"
    return AnalysisRecommendationView(
        title=f"复核{fact.label}",
        action=action,
        owner_role=owner,
        priority="urgent" if fact.status == "critical" else "high",
        evidence_refs=[fact.evidence_ref],
        success_metric=success_metric,
        stop_condition=stop_condition,
    )


def _analysis_input(
    scope: AnalysisScopeView,
    window_days: int,
    metrics: list[AnalysisMetricView],
    commerce_facts: list[AnalysisCommerceFactView],
) -> str:
    lines = [f"分析范围：{scope.label}（{scope.key}）", f"观察窗口：{window_days} 天"]
    for metric in metrics:
        lines.append(
            f"{metric.evidence_ref} {metric.label}：最新 "
            f"{_format_metric(metric.latest_value, metric.unit)}；"
            f"期初变化 {metric.period_change_rate}; "
            f"最低 {_format_metric(metric.minimum, metric.unit)}；"
            f"最高 {_format_metric(metric.maximum, metric.unit)}；"
            f"规则判断：{metric.status_reason}。"
        )
    for fact in commerce_facts:
        lines.append(
            f"{fact.evidence_ref} {fact.label}：{fact.detail}"
            f"来源 {','.join(fact.source_keys) or '未登记'}；"
            f"同步批次 {','.join(fact.sync_run_ids) or '未登记'}。"
        )
    lines.append(
        "只能引用上述 E 编号。未被证据覆盖的归因、外部原因和范围映射必须写入 unknowns。"
    )
    return "\n".join(lines)


def _commerce_unknowns(
    scope: AnalysisScopeView,
    commerce_facts: list[AnalysisCommerceFactView],
) -> list[str]:
    if not commerce_facts:
        return [
            "当前范围尚无可冻结的规范订单、退款、库存或广告事实；本次只能依据指标序列判断。"
        ]
    domains = {item.domain for item in commerce_facts}
    unknowns: list[str] = []
    if scope.type == "store" and "inventory" not in domains:
        unknowns.append(
            "库存事实当前只具备企业/仓库口径，尚未建立可靠的门店库存归属映射，因此未纳入本次门店诊断。"
        )
    missing = [
        label
        for key, label in (
            ("orders", "订单"),
            ("refunds", "退款"),
            ("advertising", "广告投放"),
        )
        if key not in domains
    ]
    if missing:
        unknowns.append(f"当前范围尚缺{'、'.join(missing)}规范事实。")
    return unknowns


def _deduplicate_strings(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in items if item.strip()))


def _validate_refs(
    findings: list[AnalysisFindingView],
    recommendations: list[AnalysisRecommendationView],
    allowed: set[str],
) -> None:
    used = {ref for item in findings for ref in item.evidence_refs}
    used.update(ref for item in recommendations for ref in item.evidence_refs)
    invalid = used - allowed
    if invalid:
        raise ValueError("模型引用了不存在的经营证据：" + "、".join(sorted(invalid)))


def _new_brief(
    session: Session,
    run: BusinessAnalysisRun,
    result: AnalysisResultPayload,
    actor: ActorContext,
    now: datetime,
    *,
    workspace_key: str | None = None,
) -> BusinessBrief:
    brief_key = f"daily-{run.scope_key}-{now.date().isoformat()}"
    version_number = int(
        session.scalar(
            select(func.max(BusinessBrief.version_number)).where(
                BusinessBrief.enterprise_id == run.enterprise_id,
                BusinessBrief.brief_key == brief_key,
            )
        ) or 0
    ) + 1
    fact_items = [item.text for item in result.findings if item.kind == "fact"]
    risk_items = [item.text for item in result.findings if item.kind != "fact"]
    action_items = [
        f"{item.title}：{item.action}（责任：{item.owner_role}；停止条件：{item.stop_condition}）"
        for item in result.recommendations
    ]
    sections = [
        BusinessBriefSectionView(key="facts", title="经营事实", items=fact_items),
        BusinessBriefSectionView(
            key="risks",
            title="风险与判断",
            items=risk_items or ["当前没有指标触发首期风险阈值。"],
        ),
        BusinessBriefSectionView(key="actions", title="今日行动焦点", items=action_items),
        BusinessBriefSectionView(key="unknowns", title="未知与待补数据", items=result.unknowns),
    ]
    refs = {ref for item in result.findings for ref in item.evidence_refs}
    refs.update(ref for item in result.recommendations for ref in item.evidence_refs)
    content = BusinessBriefContent(
        headline=result.headline,
        sections=sections,
        evidence_refs=sorted(refs),
    )
    return BusinessBrief(
        id=f"business_brief_{uuid4().hex}",
        enterprise_id=run.enterprise_id,
        brief_key=brief_key,
        version_number=version_number,
        brief_type="daily",
        scope_type=run.scope_type,
        scope_key=run.scope_key,
        scope_label=run.scope_label,
        title=f"{now:%m 月 %d 日} {run.scope_label}经营简报",
        status="generated",
        source_analysis_run_id=run.id,
        evidence_snapshot_id=run.evidence_snapshot_id,
        provider=run.provider,
        model=run.model,
        execution_mode=run.execution_mode,
        content=content.model_dump(mode="json"),
        created_by_principal_id=actor.principal_id,
        actor_snapshot=actor_snapshot_with_workspace(actor, workspace_key),
        idempotency_key=f"brief:{run.id}",
        request_id=actor.request_id,
        run_id=actor.run_id,
        created_at=now,
    )


def _run_view(
    run: BusinessAnalysisRun,
    snapshot: EvidenceSnapshot,
    principals: dict[str, Principal],
    action_proposals: list[AnalysisActionProposalView],
) -> BusinessAnalysisRunView:
    principal = principals.get(run.initiated_by_principal_id)
    actor_snapshot = run.actor_snapshot if isinstance(run.actor_snapshot, dict) else {}
    workspace_key = actor_snapshot.get("workspace_key")
    return BusinessAnalysisRunView(
        id=run.id,
        analysis_type=cast(
            Literal["store-review", "enterprise-review"], run.analysis_type
        ),
        scope=AnalysisScopeView(
            type=cast(Literal["enterprise", "store"], run.scope_type),
            key=run.scope_key,
            label=run.scope_label,
        ),
        window_days=run.window_days,
        status=cast(Literal["completed", "failed"], run.status),
        risk_level=cast(RiskLevel, run.risk_level),
        provider=run.provider,
        model=run.model,
        execution_mode=cast(Literal["model", "evidence-fallback"], run.execution_mode),
        fallback_reason=run.fallback_reason,
        result=AnalysisResultPayload.model_validate(run.result),
        evidence_snapshot=AnalysisEvidenceSnapshotView(
            id=snapshot.id,
            key=snapshot.snapshot_key,
            content_hash=snapshot.content_hash,
            item_count=snapshot.item_count,
            frozen_at=snapshot.frozen_at,
        ),
        action_proposals=action_proposals,
        workspace_key=workspace_key if isinstance(workspace_key, str) else None,
        initiated_by_principal_id=run.initiated_by_principal_id,
        initiated_by_name=principal.display_name if principal else run.initiated_by_principal_id,
        request_id=run.request_id,
        run_id=run.run_id,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _brief_view(
    brief: BusinessBrief,
    snapshot: EvidenceSnapshot,
    principals: dict[str, Principal],
) -> BusinessBriefView:
    principal = principals.get(brief.created_by_principal_id)
    return BusinessBriefView(
        id=brief.id,
        key=brief.brief_key,
        version_number=brief.version_number,
        brief_type=cast(Literal["daily", "weekly", "exception"], brief.brief_type),
        scope=AnalysisScopeView(
            type=cast(Literal["enterprise", "store"], brief.scope_type),
            key=brief.scope_key,
            label=brief.scope_label,
        ),
        title=brief.title,
        status=cast(Literal["generated", "confirmed", "superseded"], brief.status),
        source_analysis_run_id=brief.source_analysis_run_id,
        evidence_snapshot_key=snapshot.snapshot_key,
        provider=brief.provider,
        model=brief.model,
        execution_mode=cast(Literal["model", "evidence-fallback"], brief.execution_mode),
        content=BusinessBriefContent.model_validate(brief.content),
        created_by_principal_id=brief.created_by_principal_id,
        created_by_name=principal.display_name if principal else brief.created_by_principal_id,
        request_id=brief.request_id,
        run_id=brief.run_id,
        created_at=brief.created_at,
    )


def _highest_risk(levels: Iterable[RiskLevel]) -> RiskLevel:
    return max(levels, key=lambda value: RISK_ORDER[value])


def _format_metric(value: float, unit: str) -> str:
    if unit == "元":
        return f"{value / 10000:.1f} 万元" if abs(value) >= 10000 else f"{value:.0f} 元"
    if unit in {"%", "x"}:
        return f"{value:.2f}{unit}"
    return f"{value:,.0f} {unit}"
