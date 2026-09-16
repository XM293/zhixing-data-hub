from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import select

from zhixing_api.actor_context import ActorContext, actor_scope_allows
from zhixing_api.ai_provider import AIProviderError, ResponsesAIProvider
from zhixing_api.config import Settings
from zhixing_api.customer_360_schemas import CustomerDetailResponse
from zhixing_api.customer_360_service import build_customer_detail
from zhixing_api.customer_operation_schemas import (
    CustomerOperationActionProposalLinkView,
    CustomerOperationDiagnosisView,
    CustomerOperationEvidenceSnapshotView,
    CustomerOperationEvidenceView,
    CustomerOperationResultPayload,
    CustomerOperationRunResponse,
    CustomerOperationRunView,
    CustomerOperationStepView,
    CustomerOperationStudioResponse,
)
from zhixing_api.data_models import (
    ActionProposal,
    CustomerOperationRun,
    EvidenceSnapshot,
    EvidenceSnapshotItem,
    Principal,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem

PROHIBITED_ACTIONS = [
    "自动向客户发送消息或营销内容",
    "自动发放优惠券、积分、赠品或其他权益",
    "自动承诺退款、补偿、价格或服务结果",
    "自动写回 CRM、ERP、客服或店铺系统",
]

AI_CUSTOMER_OPERATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "diagnoses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string", "enum": ["inference", "risk"]},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "text": {"type": "string"},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["kind", "severity", "text", "evidence_refs"],
            },
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "action": {"type": "string"},
                    "owner_role": {"type": "string"},
                    "priority": {"type": "string", "enum": ["normal", "high", "urgent"]},
                    "action_type": {
                        "type": "string",
                        "enum": [
                            "manual_review",
                            "service_handoff",
                            "content_preparation",
                            "audience_analysis",
                        ],
                    },
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                    "success_metric": {"type": "string"},
                    "stop_condition": {"type": "string"},
                },
                "required": [
                    "title",
                    "action",
                    "owner_role",
                    "priority",
                    "action_type",
                    "evidence_refs",
                    "success_metric",
                    "stop_condition",
                ],
            },
        },
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["headline", "summary", "diagnoses", "steps", "unknowns", "confidence"],
}


def list_customer_operation_studio(
    database: Database,
    actor: ActorContext,
    *,
    scope_key: str,
    customer_key: str,
) -> CustomerOperationStudioResponse:
    build_customer_detail(
        database,
        scope_key=scope_key,
        customer_key=customer_key,
        enterprise_id=actor.enterprise_id,
        limit=24,
    )
    scope_type: Literal["enterprise", "store"] = (
        "enterprise" if scope_key == "enterprise" else "store"
    )
    scope_id = actor.enterprise_id if scope_type == "enterprise" else scope_key
    with database.session() as session:
        runs = list(
            session.scalars(
                select(CustomerOperationRun)
                .where(
                    CustomerOperationRun.enterprise_id == actor.enterprise_id,
                    CustomerOperationRun.customer_key == customer_key,
                    CustomerOperationRun.scope_key == scope_key,
                )
                .order_by(CustomerOperationRun.completed_at.desc())
                .limit(20)
            )
        )
        views = _run_views(session, runs)
    return CustomerOperationStudioResponse(
        scope_key=scope_key,
        customer_key=customer_key,
        can_run=(
            "analysis.run" in actor.permissions
            and actor_scope_allows(actor, scope_type=scope_type, scope_id=scope_id)
        ),
        can_propose=(
            "action.propose" in actor.permissions
            and actor_scope_allows(actor, scope_type=scope_type, scope_id=scope_id)
        ),
        runs=views,
        generated_at=datetime.now(UTC),
    )


async def run_customer_operation_plan(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    actor: ActorContext,
    *,
    scope_key: str,
    customer_key: str,
    objective: str,
    client_request_key: str,
) -> CustomerOperationRunResponse:
    with database.session() as session:
        existing = session.scalar(
            select(CustomerOperationRun).where(
                CustomerOperationRun.enterprise_id == actor.enterprise_id,
                CustomerOperationRun.idempotency_key == client_request_key,
            )
        )
        if existing is not None:
            if (
                existing.scope_key != scope_key
                or existing.customer_key != customer_key
                or existing.objective != objective
            ):
                raise ApiProblem(
                    status_code=409,
                    code="customer_operation.idempotency_conflict",
                    message="该幂等键已用于不同的客户运营方案请求",
                )
            existing_id = existing.id
        else:
            existing_id = None
    if existing_id is not None:
        studio = list_customer_operation_studio(
            database,
            actor,
            scope_key=scope_key,
            customer_key=customer_key,
        )
        run_view = next(item for item in studio.runs if item.id == existing_id)
        return CustomerOperationRunResponse(idempotent=True, run=run_view, studio=studio)

    detail = build_customer_detail(
        database,
        scope_key=scope_key,
        customer_key=customer_key,
        enterprise_id=actor.enterprise_id,
        limit=24,
    )
    now = datetime.now(UTC)
    operation_id = f"customer_operation_{uuid4().hex}"
    snapshot, snapshot_items, evidence = _prepare_evidence(
        actor,
        detail=detail,
        objective=objective,
        operation_id=operation_id,
        now=now,
    )
    allowed_refs = {item.evidence_ref for item in evidence}
    fallback_result = _fallback_result(detail, objective, evidence)
    fallback_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    try:
        completion = await provider.generate(
            settings,
            instructions=(
                "你是企业客户运营分析负责人。只能依据输入中的 E 编号证据形成方案，并明确区分"
                "推断与风险。不得假设客户授权、不得发送消息、发券、承诺补偿或写回任何外部系统。"
                "所有步骤只是等待人工审核的内部计划，动作类型只能使用给定枚举。不要输出隐藏思维过程。"
            ),
            input_text=_model_input(detail, objective, evidence),
            run_id=operation_id,
            schema_name="governed_customer_operation_plan",
            response_schema=AI_CUSTOMER_OPERATION_SCHEMA,
        )
        diagnoses = [
            CustomerOperationDiagnosisView.model_validate(item)
            for item in cast(list[object], completion.payload.get("diagnoses", []))
        ]
        steps = [
            CustomerOperationStepView.model_validate(
                {
                    **cast(dict[str, object], item),
                    "requires_human_approval": True,
                    "external_write_allowed": False,
                }
            )
            for item in cast(list[object], completion.payload.get("steps", []))
        ]
        if not steps:
            raise ValueError("模型未返回可执行的内部方案步骤")
        _validate_evidence_refs([*diagnoses, *steps], allowed_refs)
        result = CustomerOperationResultPayload(
            headline=str(completion.payload["headline"]),
            summary=str(completion.payload["summary"]),
            objective=objective,
            confidence=cast(
                Literal["high", "medium", "low"], completion.payload["confidence"]
            ),
            diagnoses=[*_fact_diagnoses(detail), *diagnoses],
            steps=steps,
            unknowns=_model_unknowns(completion.payload, detail),
            prohibited_actions=PROHIBITED_ACTIONS,
        )
        execution_mode: Literal["model", "rule-fallback"] = "model"
        provider_name = "openai-compatible-responses"
        model_name = settings.ai_model
        input_tokens = completion.input_tokens
        output_tokens = completion.output_tokens
    except (AIProviderError, KeyError, TypeError, ValueError) as exc:
        result = fallback_result
        execution_mode = "rule-fallback"
        provider_name = "local-evidence"
        model_name = "deterministic-customer-playbook-v1"
        fallback_reason = str(exc)[:1000]

    completed_at = datetime.now(UTC)
    duration_ms = max(0, round((completed_at - now).total_seconds() * 1000))
    scope_type: Literal["enterprise", "store"] = (
        "enterprise" if scope_key == "enterprise" else "store"
    )
    with database.session() as session:
        session.add(snapshot)
        session.add_all(snapshot_items)
        session.add(
            CustomerOperationRun(
                id=operation_id,
                enterprise_id=actor.enterprise_id,
                customer_key=customer_key,
                scope_type=scope_type,
                scope_key=scope_key,
                objective=objective,
                status="completed",
                risk_level=detail.summary.risk_level,
                provider=provider_name,
                model=model_name,
                execution_mode=execution_mode,
                fallback_reason=fallback_reason,
                evidence_snapshot_id=snapshot.id,
                result=result.model_dump(mode="json"),
                initiated_by_principal_id=actor.principal_id,
                actor_snapshot=actor.snapshot(),
                idempotency_key=client_request_key,
                request_id=actor.request_id,
                run_id=actor.run_id,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                created_at=now,
                completed_at=completed_at,
            )
        )
        session.commit()

    studio = list_customer_operation_studio(
        database,
        actor,
        scope_key=scope_key,
        customer_key=customer_key,
    )
    run_view = next(item for item in studio.runs if item.id == operation_id)
    return CustomerOperationRunResponse(idempotent=False, run=run_view, studio=studio)


def _prepare_evidence(
    actor: ActorContext,
    *,
    detail: CustomerDetailResponse,
    objective: str,
    operation_id: str,
    now: datetime,
) -> tuple[EvidenceSnapshot, list[EvidenceSnapshotItem], list[CustomerOperationEvidenceView]]:
    rows: list[tuple[str, str, str, str | None, dict[str, object]]] = [
        (
            "customer-profile",
            f"profile:{detail.customer_key}",
            f"客户主档 · {detail.profile.display_name}",
            detail.profile.sync_run_id,
            cast(dict[str, object], detail.profile.model_dump(mode="json")),
        ),
        (
            "customer-summary",
            f"summary:{detail.customer_key}",
            "客户经营与风险汇总",
            detail.playbook_version,
            cast(dict[str, object], detail.summary.model_dump(mode="json")),
        ),
    ]
    rows.extend(
        (
            "customer-order",
            f"order:{item.order_key}",
            f"订单 {item.order_key}",
            item.sync_run_id,
            cast(dict[str, object], item.model_dump(mode="json")),
        )
        for item in detail.orders[:8]
    )
    rows.extend(
        (
            "customer-refund",
            f"refund:{item.refund_key}",
            f"退款 {item.refund_key}",
            item.sync_run_id,
            cast(dict[str, object], item.model_dump(mode="json")),
        )
        for item in detail.refunds[:8]
    )
    rows.extend(
        (
            "customer-touchpoint",
            f"touchpoint:{item.touchpoint_key}",
            f"客户触点 {item.touchpoint_type}",
            item.sync_run_id,
            cast(dict[str, object], item.model_dump(mode="json")),
        )
        for item in detail.touchpoints[:12]
    )
    rows = rows[:24]
    serialized = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snapshot = EvidenceSnapshot(
        id=f"evidence_snapshot_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        snapshot_key=f"customer-operation:{operation_id}",
        purpose="customer-operation",
        query=json.dumps(
            {
                "scope_key": detail.scope_key,
                "customer_key": detail.customer_key,
                "objective": objective,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        content_hash=sha256(serialized.encode()).hexdigest(),
        item_count=len(rows),
        frozen_at=now,
    )
    evidence = [
        CustomerOperationEvidenceView(
            evidence_ref=f"E{rank}",
            item_type=item_type,
            item_key=item_key,
            label=label,
            version_ref=version_ref,
            payload=payload,
        )
        for rank, (item_type, item_key, label, version_ref, payload) in enumerate(
            rows, start=1
        )
    ]
    items = [
        EvidenceSnapshotItem(
            id=f"evidence_snapshot_item_{uuid4().hex}",
            snapshot_id=snapshot.id,
            item_type=item.item_type,
            item_key=item.item_key,
            version_ref=item.version_ref,
            label=item.label,
            payload={"evidence_ref": item.evidence_ref, **item.payload},
            rank=rank,
        )
        for rank, item in enumerate(evidence, start=1)
    ]
    return snapshot, items, evidence


def _fallback_result(
    detail: CustomerDetailResponse,
    objective: str,
    evidence: list[CustomerOperationEvidenceView],
) -> CustomerOperationResultPayload:
    refs_by_key = {item.item_key: item.evidence_ref for item in evidence}
    steps: list[CustomerOperationStepView] = []
    for recommendation in detail.recommendations:
        action_type: Literal[
            "manual_review", "service_handoff", "content_preparation", "audience_analysis"
        ]
        if recommendation.key in {"refund-experience-review", "consent-boundary"}:
            action_type = "service_handoff"
        elif recommendation.key in {"retention-review", "reactivation-review"}:
            action_type = "manual_review"
        elif recommendation.key == "new-customer-onboarding":
            action_type = "content_preparation"
        else:
            action_type = "audience_analysis"
        evidence_refs = [
            refs_by_key[key] for key in recommendation.evidence_keys if key in refs_by_key
        ] or ["E1"]
        steps.append(
            CustomerOperationStepView(
                title=recommendation.title,
                action=(
                    f"{recommendation.objective}。{recommendation.action_boundary}"
                ),
                owner_role="客户运营负责人" if action_type != "service_handoff" else "客服主管",
                priority=(
                    "urgent"
                    if recommendation.priority == "critical"
                    else "high"
                    if recommendation.priority == "high"
                    else "normal"
                ),
                action_type=action_type,
                evidence_refs=evidence_refs,
                success_metric="人工复核结论、责任人和后续指标已记录",
                stop_condition="证据不足、客户授权失效或风险边界变化时停止",
            )
        )
    if not steps:
        steps.append(
            CustomerOperationStepView(
                title="完成人工客户画像复核",
                action="核对当前主档、交易和互动证据，记录是否需要进入运营观察队列。",
                owner_role="客户运营负责人",
                priority="normal",
                action_type="manual_review",
                evidence_refs=["E1", "E2"],
                success_metric="形成有证据引用的人工复核结论",
                stop_condition="当前证据不足以支持运营动作时停止",
            )
        )
    return CustomerOperationResultPayload(
        headline=f"{detail.profile.display_name}客户运营复核方案",
        summary=(
            f"基于客户主档、交易、退款和触点事实形成 {len(steps)} 项内部方案；"
            "所有对外动作仍需人工批准。"
        ),
        objective=objective,
        confidence="medium",
        diagnoses=_fact_diagnoses(detail),
        steps=steps,
        unknowns=_deterministic_unknowns(detail),
        prohibited_actions=PROHIBITED_ACTIONS,
    )


def _fact_diagnoses(detail: CustomerDetailResponse) -> list[CustomerOperationDiagnosisView]:
    severity = detail.summary.risk_level
    diagnoses = [
        CustomerOperationDiagnosisView(
            kind="fact",
            severity=severity,
            text=(
                f"客户生命周期为 {detail.profile.lifecycle_stage}，流失风险分为 "
                f"{detail.profile.churn_risk_score:.0%}，当前同意状态为 "
                f"{detail.profile.consent_status}。"
            ),
            evidence_refs=["E1"],
        ),
        CustomerOperationDiagnosisView(
            kind="fact",
            severity=severity,
            text=(
                f"累计 {detail.summary.lifetime_order_count} 单、成交 "
                f"{detail.summary.paid_gmv_yuan:.2f} 元、退款率 "
                f"{detail.summary.refund_rate:.1%}。"
            ),
            evidence_refs=["E2"],
        ),
    ]
    return diagnoses


def _deterministic_unknowns(detail: CustomerDetailResponse) -> list[str]:
    unknowns = ["当前证据不包含完整客户服务工单、实时库存和活动权益审批状态。"]
    if not detail.summary.engagement_eligible:
        unknowns.append("客户当前不具备触达资格，必须先核验同意历史。")
    return unknowns


def _model_unknowns(
    payload: dict[str, object],
    detail: CustomerDetailResponse,
) -> list[str]:
    values = [
        *(str(item) for item in cast(list[object], payload.get("unknowns", []))),
        *_deterministic_unknowns(detail),
    ]
    return list(dict.fromkeys(item for item in values if item.strip()))


def _validate_evidence_refs(
    items: list[CustomerOperationDiagnosisView | CustomerOperationStepView],
    allowed_refs: set[str],
) -> None:
    unknown = sorted(
        {
            ref
            for item in items
            for ref in item.evidence_refs
            if ref not in allowed_refs
        }
    )
    if unknown:
        raise ValueError(f"模型引用了未冻结的证据：{', '.join(unknown)}")


def _model_input(
    detail: CustomerDetailResponse,
    objective: str,
    evidence: list[CustomerOperationEvidenceView],
) -> str:
    return json.dumps(
        {
            "objective": objective,
            "scope_key": detail.scope_key,
            "customer_key": detail.customer_key,
            "engagement_eligible": detail.summary.engagement_eligible,
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "prohibited_actions": PROHIBITED_ACTIONS,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _run_views(
    session: object,
    runs: list[CustomerOperationRun],
) -> list[CustomerOperationRunView]:
    if not runs:
        return []
    snapshot_ids = {item.evidence_snapshot_id for item in runs}
    principal_ids = {item.initiated_by_principal_id for item in runs}
    run_ids = {item.id for item in runs}
    snapshots = {
        item.id: item
        for item in session.scalars(  # type: ignore[attr-defined]
            select(EvidenceSnapshot).where(EvidenceSnapshot.id.in_(snapshot_ids))
        )
    }
    items_by_snapshot: dict[str, list[EvidenceSnapshotItem]] = {}
    for item in session.scalars(  # type: ignore[attr-defined]
        select(EvidenceSnapshotItem)
        .where(EvidenceSnapshotItem.snapshot_id.in_(snapshot_ids))
        .order_by(EvidenceSnapshotItem.snapshot_id, EvidenceSnapshotItem.rank)
    ):
        items_by_snapshot.setdefault(item.snapshot_id, []).append(item)
    principals = {
        item.id: item
        for item in session.scalars(  # type: ignore[attr-defined]
            select(Principal).where(Principal.id.in_(principal_ids))
        )
    }
    proposals_by_run: dict[str, list[ActionProposal]] = {}
    for proposal in session.scalars(  # type: ignore[attr-defined]
        select(ActionProposal)
        .where(ActionProposal.customer_operation_run_id.in_(run_ids))
        .order_by(ActionProposal.customer_operation_run_id, ActionProposal.source_action_index)
    ):
        if proposal.customer_operation_run_id:
            proposals_by_run.setdefault(proposal.customer_operation_run_id, []).append(proposal)
    result: list[CustomerOperationRunView] = []
    for run in runs:
        snapshot = snapshots[run.evidence_snapshot_id]
        evidence = [
            CustomerOperationEvidenceView(
                evidence_ref=str(item.payload.get("evidence_ref", f"E{item.rank}")),
                item_type=item.item_type,
                item_key=item.item_key,
                label=item.label,
                version_ref=item.version_ref,
                payload={
                    key: value for key, value in item.payload.items() if key != "evidence_ref"
                },
            )
            for item in items_by_snapshot.get(snapshot.id, [])
        ]
        result.append(
            CustomerOperationRunView(
                id=run.id,
                customer_key=run.customer_key,
                scope_type=cast(Literal["enterprise", "store"], run.scope_type),
                scope_key=run.scope_key,
                objective=run.objective,
                status="completed",
                risk_level=cast(Literal["low", "medium", "high"], run.risk_level),
                provider=run.provider,
                model=run.model,
                execution_mode=cast(Literal["model", "rule-fallback"], run.execution_mode),
                fallback_reason=run.fallback_reason,
                result=CustomerOperationResultPayload.model_validate(run.result),
                evidence_snapshot=CustomerOperationEvidenceSnapshotView(
                    id=snapshot.id,
                    snapshot_key=snapshot.snapshot_key,
                    purpose="customer-operation",
                    content_hash=snapshot.content_hash,
                    item_count=snapshot.item_count,
                    frozen_at=snapshot.frozen_at,
                ),
                evidence=evidence,
                action_proposals=[
                    CustomerOperationActionProposalLinkView(
                        step_index=proposal.source_action_index,
                        proposal_key=proposal.proposal_key,
                        status=cast(
                            Literal["pending_approval", "approved", "rejected"],
                            proposal.status,
                        ),
                    )
                    for proposal in proposals_by_run.get(run.id, [])
                ],
                initiated_by_name=principals[run.initiated_by_principal_id].display_name,
                initiated_by_principal_id=run.initiated_by_principal_id,
                request_id=run.request_id,
                run_id=run.run_id,
                duration_ms=run.duration_ms,
                input_tokens=run.input_tokens,
                output_tokens=run.output_tokens,
                created_at=run.created_at,
                completed_at=run.completed_at,
            )
        )
    return result
