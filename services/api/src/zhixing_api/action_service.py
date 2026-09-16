from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zhixing_api.action_schemas import (
    ActionApprovalEventView,
    ActionDecisionRequest,
    ActionExecutionView,
    ActionProposalListResponse,
    ActionProposalStats,
    ActionProposalView,
    ActionWorkEventRequest,
    ActionWorkEventResponse,
    ActionWorkEventView,
    ActionWorkItemView,
    ActionWorkListResponse,
    ActionWorkStats,
    ActionWorkSummaryView,
    BusinessAnalysisActionProposalRequest,
    BusinessAnalysisActionProposalResponse,
    CustomerOperationActionProposalRequest,
    CustomerOperationActionProposalResponse,
    MeetingDecisionConfirmationView,
)
from zhixing_api.actor_context import ActorContext, actor_scope_allows, require_permission
from zhixing_api.analysis_schemas import AnalysisResultPayload
from zhixing_api.customer_operation_schemas import CustomerOperationResultPayload
from zhixing_api.data_models import (
    ActionApprovalEvent,
    ActionExecution,
    ActionProposal,
    ActionWorkEvent,
    ActionWorkItem,
    BusinessAnalysisRun,
    CustomerOperationRun,
    DecisionPackage,
    MeetingDecisionConfirmation,
    PlatformEvent,
    TwinMeeting,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.scope_context import build_scope_context

WorkStatus = Literal["ready", "claimed", "in_progress", "blocked", "completed"]
WorkAction = Literal["claim", "start", "block", "complete", "release", "reopen"]


def confirmation_view(
    session: Session,
    confirmation: MeetingDecisionConfirmation,
) -> MeetingDecisionConfirmationView:
    meeting = session.get(TwinMeeting, confirmation.meeting_id)
    if meeting is None:
        raise LookupError("人工确认关联的数字会议不存在")
    return MeetingDecisionConfirmationView(
        id=confirmation.id,
        meeting_key=meeting.meeting_key,
        decision_package_id=confirmation.decision_package_id,
        confirmed_by_actor_key=confirmation.confirmed_by_actor_key,
        confirmed_by_name=confirmation.confirmed_by_name,
        comment=confirmation.comment,
        confirmed_at=confirmation.confirmed_at,
    )


def action_proposal_view(session: Session, proposal: ActionProposal) -> ActionProposalView:
    meeting = session.get(TwinMeeting, proposal.meeting_id) if proposal.meeting_id else None
    if proposal.source_type == "meeting-decision" and meeting is None:
        raise LookupError("行动提案关联的数字会议不存在")
    customer_operation = (
        session.get(CustomerOperationRun, proposal.customer_operation_run_id)
        if proposal.customer_operation_run_id
        else None
    )
    if proposal.source_type == "customer-operation" and customer_operation is None:
        raise LookupError("行动提案关联的客户运营方案不存在")
    business_analysis = (
        session.get(BusinessAnalysisRun, proposal.business_analysis_run_id)
        if proposal.business_analysis_run_id
        else None
    )
    if proposal.source_type == "business-analysis" and business_analysis is None:
        raise LookupError("行动提案关联的经营分析不存在")
    if meeting is not None:
        source_route = f"/console/meetings/{meeting.meeting_key}"
    elif customer_operation is not None:
        source_route = (
            "/console/data/customers/"
            f"{customer_operation.scope_key}/{customer_operation.customer_key}"
        )
    elif business_analysis is not None:
        source_route = f"/console/analysis/store-review?scope={business_analysis.scope_key}"
    else:
        source_route = "/console/actions/proposals"
    events = list(
        session.scalars(
            select(ActionApprovalEvent)
            .where(ActionApprovalEvent.proposal_id == proposal.id)
            .order_by(ActionApprovalEvent.created_at)
        )
    )
    execution = session.scalar(
        select(ActionExecution).where(ActionExecution.proposal_id == proposal.id)
    )
    work_item = session.scalar(
        select(ActionWorkItem).where(ActionWorkItem.proposal_id == proposal.id)
    )
    return ActionProposalView(
        id=proposal.id,
        key=proposal.proposal_key,
        source_type=cast(
            Literal["meeting-decision", "customer-operation", "business-analysis"],
            proposal.source_type,
        ),
        source_key=proposal.source_key,
        source_label=proposal.source_label,
        source_route=source_route,
        scope_type=cast(Literal["enterprise", "store", "object"], proposal.scope_type),
        scope_key=proposal.scope_key,
        meeting_key=meeting.meeting_key if meeting else None,
        decision_package_id=proposal.decision_package_id,
        customer_operation_run_id=proposal.customer_operation_run_id,
        business_analysis_run_id=proposal.business_analysis_run_id,
        evidence_snapshot_id=proposal.evidence_snapshot_id,
        title=proposal.title,
        owner=proposal.owner,
        due_hint=proposal.due_hint,
        kpi=proposal.kpi,
        stop_condition=proposal.stop_condition,
        evidence_refs=proposal.evidence_refs,
        target_system=proposal.target_system,
        target_key=proposal.target_key,
        risk_level=cast(Literal["R2"], proposal.risk_level),
        action_level=cast(Literal["R2"], proposal.action_level),
        parameters=proposal.parameters,
        status=cast(Literal["pending_approval", "approved", "rejected"], proposal.status),
        requested_by_actor_key=proposal.requested_by_actor_key,
        requested_by_name=proposal.requested_by_name,
        idempotency_key=proposal.idempotency_key,
        approved_by_actor_key=proposal.approved_by_actor_key,
        approved_by_name=proposal.approved_by_name,
        approved_at=proposal.approved_at,
        decision_comment=proposal.decision_comment,
        approval_events=[
            ActionApprovalEventView(
                id=event.id,
                actor_key=event.actor_key,
                actor_name=event.actor_name,
                decision=cast(Literal["approved", "rejected"], event.decision),
                comment=event.comment,
                idempotency_key=event.idempotency_key,
                created_at=event.created_at,
            )
            for event in events
        ],
        execution=(
            ActionExecutionView(
                id=execution.id,
                key=execution.execution_key,
                idempotency_key=execution.idempotency_key,
                status=cast(Literal["recorded"], execution.status),
                external_write=False,
                actor_key=execution.actor_key,
                result=execution.result,
                started_at=execution.started_at,
                finished_at=execution.finished_at,
            )
            if execution
            else None
        ),
        work_item=(
            ActionWorkSummaryView(
                key=work_item.work_key,
                status=cast(
                    Literal["ready", "claimed", "in_progress", "blocked", "completed"],
                    work_item.status,
                ),
                assignee_name=work_item.assignee_name,
                version=work_item.version,
            )
            if work_item
            else None
        ),
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


def _create_action_work_item(
    session: Session,
    *,
    proposal: ActionProposal,
    actor: ActorContext,
    now: datetime,
    actor_snapshot: dict[str, object],
) -> ActionWorkItem:
    existing = session.scalar(
        select(ActionWorkItem).where(ActionWorkItem.proposal_id == proposal.id)
    )
    if existing is not None:
        return existing
    raw_priority = str(proposal.parameters.get("priority", "normal"))
    priority = raw_priority if raw_priority in {"normal", "high", "urgent"} else "normal"
    item = ActionWorkItem(
        id=f"action_work_{uuid4().hex}",
        enterprise_id=proposal.enterprise_id,
        work_key=f"work-{proposal.proposal_key}",
        proposal_id=proposal.id,
        scope_type=proposal.scope_type,
        scope_key=proposal.scope_key,
        status="ready",
        assignee_principal_id=None,
        assignee_name=None,
        owner_role=proposal.owner,
        title=proposal.title,
        due_hint=proposal.due_hint,
        kpi=proposal.kpi,
        stop_condition=proposal.stop_condition,
        priority=priority,
        version=1,
        claimed_at=None,
        started_at=None,
        blocked_at=None,
        completed_at=None,
        blocker_reason=None,
        result_summary=None,
        result_evidence_refs=[],
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    session.flush()
    session.add(
        ActionWorkEvent(
            id=f"action_work_event_{uuid4().hex}",
            enterprise_id=proposal.enterprise_id,
            work_item_id=item.id,
            actor_principal_id=actor.principal_id,
            actor_name=actor.display_name,
            event_type="created",
            from_status=None,
            to_status="ready",
            comment="行动提案审批通过，创建内部待领取工作项",
            evidence_refs=proposal.evidence_refs,
            idempotency_key=f"work-created:{proposal.proposal_key}",
            actor_snapshot=actor_snapshot,
            created_at=now,
        )
    )
    return item


def confirm_meeting_decision(
    database: Database,
    *,
    meeting_key: str,
    actor: ActorContext,
    comment: str,
) -> tuple[MeetingDecisionConfirmationView, list[ActionProposalView], int]:
    require_permission(
        actor,
        "meeting.decision.confirm",
        database,
        resource_type="meeting",
        resource_key=meeting_key,
        scope_type="object",
        scope_id=meeting_key,
    )
    snapshot = {**actor.snapshot(),
                "scope_context": build_scope_context(database, actor).snapshot()}
    now = datetime.now(UTC)
    with database.session() as session:
        meeting = session.scalar(select(TwinMeeting).where(TwinMeeting.meeting_key == meeting_key))
        if meeting is None:
            raise LookupError("数字会议不存在")
        package = session.scalar(
            select(DecisionPackage).where(DecisionPackage.meeting_id == meeting.id)
        )
        if package is None:
            raise ApiProblem(
                status_code=409,
                code="meeting.decision_package_required",
                message="会议尚未形成可确认的决策包",
            )
        existing = session.scalar(
            select(MeetingDecisionConfirmation).where(
                MeetingDecisionConfirmation.meeting_id == meeting.id
            )
        )
        if existing is not None:
            if existing.confirmed_by_actor_key != actor.actor_key:
                raise ApiProblem(
                    status_code=409,
                    code="meeting.decision_already_confirmed",
                    message="该决策包已经由其他负责人确认",
                    details={"confirmed_by": existing.confirmed_by_name},
                )
            existing_proposals = list(
                session.scalars(
                    select(ActionProposal)
                    .where(ActionProposal.meeting_id == meeting.id)
                    .order_by(ActionProposal.source_action_index)
                )
            )
            return (
                confirmation_view(session, existing),
                [action_proposal_view(session, proposal) for proposal in existing_proposals],
                0,
            )

        confirmation = MeetingDecisionConfirmation(
            id=f"meeting_confirmation_{uuid4().hex}",
            enterprise_id=meeting.enterprise_id,
            meeting_id=meeting.id,
            decision_package_id=package.id,
            confirmed_by_actor_key=actor.actor_key,
            confirmed_by_name=actor.display_name,
            actor_context=snapshot,
            comment=comment,
            confirmed_at=now,
        )
        session.add(confirmation)
        proposals: list[ActionProposal] = []
        for index, item in enumerate(package.actions):
            action = dict(item)
            raw_evidence_refs = action.get("evidence_refs", [])
            evidence_refs = (
                [str(ref) for ref in raw_evidence_refs]
                if isinstance(raw_evidence_refs, list)
                else []
            )
            proposal = ActionProposal(
                id=f"action_proposal_{uuid4().hex}",
                enterprise_id=meeting.enterprise_id,
                proposal_key=f"act-{meeting.meeting_key}-{index + 1:02d}",
                source_type="meeting-decision",
                source_key=meeting.meeting_key,
                source_label=meeting.title,
                scope_type="object",
                scope_key=meeting.meeting_key,
                meeting_id=meeting.id,
                decision_package_id=package.id,
                customer_operation_run_id=None,
                business_analysis_run_id=None,
                evidence_snapshot_id=None,
                source_action_index=index,
                title=str(action.get("title", f"会议行动 {index + 1}")),
                owner=str(action.get("owner", "待指定")),
                due_hint=str(action.get("due_hint", "待确认")),
                kpi=str(action.get("kpi", "待定义")),
                stop_condition=str(action.get("stop_condition", "待定义")),
                evidence_refs=evidence_refs,
                target_system="internal-action-ledger",
                target_key=f"meeting-action-{index + 1:02d}",
                risk_level="R2",
                action_level="R2",
                parameters={
                    "owner": str(action.get("owner", "待指定")),
                    "due_hint": str(action.get("due_hint", "待确认")),
                    "kpi": str(action.get("kpi", "待定义")),
                    "stop_condition": str(action.get("stop_condition", "待定义")),
                    "external_write": False,
                },
                status="pending_approval",
                requested_by_actor_key=actor.actor_key,
                requested_by_name=actor.display_name,
                idempotency_key=f"proposal:{package.id}:{index + 1}",
                approved_by_actor_key=None,
                approved_by_name=None,
                approved_at=None,
                decision_comment=None,
                created_at=now,
                updated_at=now,
            )
            session.add(proposal)
            proposals.append(proposal)
        package.status = "confirmed"
        package.updated_at = now
        meeting.protocol_status = "actions_created"
        meeting.updated_at = now
        session.add(
            PlatformEvent(
                id=f"event_{uuid4().hex}",
                enterprise_id=meeting.enterprise_id,
                event_type="meeting_decision_confirmed",
                severity="info",
                title="会议决策已由人类负责人确认",
                detail=f"{meeting.title} · 生成 {len(proposals)} 条 R2 行动提案 · 外部写入 0",
                occurred_at=now,
            )
        )
        session.commit()
        return (
            confirmation_view(session, confirmation),
            [action_proposal_view(session, proposal) for proposal in proposals],
            len(proposals),
        )


def list_action_proposals(
    database: Database,
    actor: ActorContext,
    *,
    status: Literal["pending_approval", "approved", "rejected"] | None = None,
    meeting_key: str | None = None,
) -> ActionProposalListResponse:
    permission = next(
        (
            item
            for item in ("action.approve", "action.propose", "action.work.read")
            if item in actor.permissions
        ),
        "action.work.read",
    )
    require_permission(
        actor,
        permission,
        database,
        resource_type="action_proposal",
        resource_key="action-proposal-ledger",
    )
    with database.session() as session:
        all_proposals = list(
            session.scalars(
                select(ActionProposal)
                .where(ActionProposal.enterprise_id == actor.enterprise_id)
                .order_by(ActionProposal.created_at.desc(), ActionProposal.source_action_index)
            )
        )
        all_proposals = [
            proposal
            for proposal in all_proposals
            if actor_scope_allows(
                actor,
                scope_type=proposal.scope_type,
                scope_id=(
                    actor.enterprise_id
                    if proposal.scope_type == "enterprise"
                    else proposal.scope_key
                ),
            )
        ]
        if not ({"action.approve", "action.propose"} & set(actor.permissions)):
            all_proposals = [
                proposal for proposal in all_proposals if proposal.status == "approved"
            ]
        selected = all_proposals
        if status:
            selected = [proposal for proposal in selected if proposal.status == status]
        if meeting_key:
            meeting = session.scalar(
                select(TwinMeeting).where(TwinMeeting.meeting_key == meeting_key)
            )
            selected = (
                [proposal for proposal in selected if proposal.meeting_id == meeting.id]
                if meeting
                else []
            )
        recorded_count = int(
            session.scalar(
                select(func.count(ActionExecution.id)).where(
                    ActionExecution.proposal_id.in_([item.id for item in all_proposals])
                )
            )
            or 0
        )
        return ActionProposalListResponse(
            stats=ActionProposalStats(
                total=len(all_proposals),
                pending_approval=sum(
                    proposal.status == "pending_approval" for proposal in all_proposals
                ),
                approved=sum(proposal.status == "approved" for proposal in all_proposals),
                rejected=sum(proposal.status == "rejected" for proposal in all_proposals),
                recorded_executions=recorded_count,
            ),
            items=[action_proposal_view(session, proposal) for proposal in selected],
            generated_at=datetime.now(UTC),
        )


def decide_action_proposal(
    database: Database,
    *,
    proposal_key: str,
    actor: ActorContext,
    payload: ActionDecisionRequest,
) -> ActionProposalView:
    with database.session() as lookup_session:
        lookup_proposal = lookup_session.scalar(
            select(ActionProposal).where(
                ActionProposal.enterprise_id == actor.enterprise_id,
                ActionProposal.proposal_key == proposal_key,
            )
        )
        if lookup_proposal is None:
            raise LookupError("行动提案不存在")
        proposal_scope_type = lookup_proposal.scope_type
        proposal_scope_id = (
            actor.enterprise_id
            if proposal_scope_type == "enterprise"
            else lookup_proposal.scope_key
        )
    require_permission(
        actor,
        "action.approve",
        database,
        resource_type="action_proposal",
        resource_key=proposal_key,
        scope_type=proposal_scope_type,
        scope_id=proposal_scope_id,
    )
    now = datetime.now(UTC)
    normalized_decision = "approved" if payload.decision == "approve" else "rejected"
    snapshot = {**actor.snapshot(),
                "scope_context": build_scope_context(database, actor).snapshot()}
    with database.session() as session:
        proposal = session.scalar(
            select(ActionProposal).where(ActionProposal.proposal_key == proposal_key)
        )
        if proposal is None:
            raise LookupError("行动提案不存在")
        existing_event = session.scalar(
            select(ActionApprovalEvent).where(
                ActionApprovalEvent.enterprise_id == proposal.enterprise_id,
                ActionApprovalEvent.idempotency_key == payload.idempotency_key,
            )
        )
        if existing_event is not None:
            if (
                existing_event.proposal_id != proposal.id
                or existing_event.decision != normalized_decision
            ):
                raise ApiProblem(
                    status_code=409,
                    code="action.idempotency_conflict",
                    message="审批幂等键已被不同操作使用",
                )
            return action_proposal_view(session, proposal)
        if proposal.status != "pending_approval":
            raise ApiProblem(
                status_code=409,
                code="action.already_decided",
                message="行动提案已经完成审批，不能再次改变结论",
                details={"status": proposal.status},
            )
        if proposal.requested_by_actor_key == actor.actor_key:
            raise ApiProblem(
                status_code=403,
                code="authorization.separation_of_duties",
                message="行动提案发起人与审批人必须分离",
            )

        event = ActionApprovalEvent(
            id=f"action_approval_{uuid4().hex}",
            enterprise_id=proposal.enterprise_id,
            proposal_id=proposal.id,
            actor_key=actor.actor_key,
            actor_name=actor.display_name,
            decision=normalized_decision,
            comment=payload.comment,
            idempotency_key=payload.idempotency_key,
            actor_context=snapshot,
            created_at=now,
        )
        session.add(event)
        proposal.status = normalized_decision
        proposal.approved_by_actor_key = actor.actor_key
        proposal.approved_by_name = actor.display_name
        proposal.approved_at = now
        proposal.decision_comment = payload.comment
        proposal.updated_at = now
        if normalized_decision == "approved":
            session.add(
                ActionExecution(
                    id=f"action_execution_{uuid4().hex}",
                    enterprise_id=proposal.enterprise_id,
                    execution_key=f"exec-{proposal.proposal_key}",
                    proposal_id=proposal.id,
                    idempotency_key=proposal.idempotency_key,
                    status="recorded",
                    external_write=False,
                    actor_key="internal-action-ledger-service",
                    result={
                        "message": "已登记内部行动台账并创建待领取工作项",
                        "external_write": False,
                        "target_system": proposal.target_system,
                    },
                    started_at=now,
                    finished_at=now,
                )
            )
            _create_action_work_item(session, proposal=proposal, actor=actor, now=now,
                                     actor_snapshot=snapshot)
        session.add(
            PlatformEvent(
                id=f"event_{uuid4().hex}",
                enterprise_id=proposal.enterprise_id,
                event_type=f"action_proposal_{normalized_decision}",
                severity="info" if normalized_decision == "approved" else "warning",
                title=(
                    "行动提案已批准并登记内部台账"
                    if normalized_decision == "approved"
                    else "行动提案已驳回"
                ),
                detail=f"{proposal.title} · {actor.display_name} · 外部写入 0",
                occurred_at=now,
            )
        )
        session.commit()
        return action_proposal_view(session, proposal)


def create_customer_operation_action_proposals(
    database: Database,
    *,
    operation_id: str,
    actor: ActorContext,
    payload: CustomerOperationActionProposalRequest,
) -> CustomerOperationActionProposalResponse:
    if len(set(payload.step_indexes)) != len(payload.step_indexes):
        raise ApiProblem(
            status_code=422,
            code="action.duplicate_step_index",
            message="同一个运营步骤不能重复提交",
        )
    with database.session() as session:
        operation = session.scalar(
            select(CustomerOperationRun).where(
                CustomerOperationRun.enterprise_id == actor.enterprise_id,
                CustomerOperationRun.id == operation_id,
            )
        )
        if operation is None:
            raise LookupError("客户运营方案不存在")
        operation_scope_type = operation.scope_type
        operation_scope_id = (
            actor.enterprise_id
            if operation.scope_type == "enterprise"
            else operation.scope_key
        )
    require_permission(
        actor,
        "action.propose",
        database,
        resource_type="customer_operation",
        resource_key=operation_id,
        scope_type=operation_scope_type,
        scope_id=operation_scope_id,
    )

    now = datetime.now(UTC)
    with database.session() as session:
        operation = session.get(CustomerOperationRun, operation_id)
        if operation is None or operation.enterprise_id != actor.enterprise_id:
            raise LookupError("客户运营方案不存在")
        result = CustomerOperationResultPayload.model_validate(operation.result)
        indexes = sorted(payload.step_indexes)
        if any(index < 0 or index >= len(result.steps) for index in indexes):
            raise ApiProblem(
                status_code=422,
                code="action.customer_operation_step_invalid",
                message="所选步骤不属于当前客户运营方案",
                details={"available_step_count": len(result.steps)},
            )

        existing_by_index = {
            proposal.source_action_index: proposal
            for proposal in session.scalars(
                select(ActionProposal).where(
                    ActionProposal.customer_operation_run_id == operation.id,
                    ActionProposal.source_action_index.in_(indexes),
                )
            )
        }
        for index, proposal in existing_by_index.items():
            if proposal.due_hint != payload.due_hint:
                raise ApiProblem(
                    status_code=409,
                    code="action.customer_operation_step_already_proposed",
                    message="该运营步骤已使用不同时间要求进入行动中心",
                    details={"step_index": index, "proposal_key": proposal.proposal_key},
                )

        items: list[ActionProposal] = []
        created: list[ActionProposal] = []
        for index in indexes:
            existing = existing_by_index.get(index)
            if existing is not None:
                items.append(existing)
                continue
            step = result.steps[index]
            proposal_idempotency_key = f"{payload.idempotency_key}:{index}"
            idempotency_conflict = session.scalar(
                select(ActionProposal).where(
                    ActionProposal.enterprise_id == actor.enterprise_id,
                    ActionProposal.idempotency_key == proposal_idempotency_key,
                )
            )
            if idempotency_conflict is not None:
                raise ApiProblem(
                    status_code=409,
                    code="action.idempotency_conflict",
                    message="行动提案幂等键已被不同来源步骤使用",
                )
            proposal = ActionProposal(
                id=f"action_proposal_{uuid4().hex}",
                enterprise_id=operation.enterprise_id,
                proposal_key=f"act-customer-{operation.id[-16:]}-{index + 1:02d}",
                source_type="customer-operation",
                source_key=operation.id,
                source_label=result.headline[:300],
                scope_type=operation.scope_type,
                scope_key=operation.scope_key,
                meeting_id=None,
                decision_package_id=None,
                customer_operation_run_id=operation.id,
                business_analysis_run_id=None,
                evidence_snapshot_id=operation.evidence_snapshot_id,
                source_action_index=index,
                title=step.title,
                owner=step.owner_role,
                due_hint=payload.due_hint,
                kpi=step.success_metric,
                stop_condition=step.stop_condition,
                evidence_refs=step.evidence_refs,
                target_system="internal-action-ledger",
                target_key=f"customer-operation:{operation.customer_key}:{index + 1}",
                risk_level="R2",
                action_level="R2",
                parameters={
                    "action": step.action,
                    "action_type": step.action_type,
                    "priority": step.priority,
                    "customer_key": operation.customer_key,
                    "external_write": False,
                },
                status="pending_approval",
                requested_by_actor_key=actor.actor_key,
                requested_by_name=actor.display_name,
                idempotency_key=proposal_idempotency_key,
                approved_by_actor_key=None,
                approved_by_name=None,
                approved_at=None,
                decision_comment=None,
                created_at=now,
                updated_at=now,
            )
            session.add(proposal)
            items.append(proposal)
            created.append(proposal)
        if created:
            session.add(
                PlatformEvent(
                    id=f"event_{uuid4().hex}",
                    enterprise_id=operation.enterprise_id,
                    event_type="customer_operation_actions_proposed",
                    severity="info",
                    title="客户运营步骤已进入行动审批",
                    detail=(
                        f"{operation.customer_key} · {len(created)} 条 R2 行动提案 · "
                        "外部写入 0"
                    ),
                    occurred_at=now,
                )
            )
        session.commit()
        views = [action_proposal_view(session, item) for item in items]
    return CustomerOperationActionProposalResponse(
        idempotent=not created,
        created_count=len(created),
        items=views,
    )


def create_business_analysis_action_proposals(
    database: Database,
    *,
    analysis_run_id: str,
    actor: ActorContext,
    payload: BusinessAnalysisActionProposalRequest,
) -> BusinessAnalysisActionProposalResponse:
    if len(set(payload.recommendation_indexes)) != len(payload.recommendation_indexes):
        raise ApiProblem(
            status_code=422,
            code="action.duplicate_recommendation_index",
            message="同一条经营建议不能重复提交",
        )
    with database.session() as session:
        run = session.scalar(
            select(BusinessAnalysisRun).where(
                BusinessAnalysisRun.enterprise_id == actor.enterprise_id,
                BusinessAnalysisRun.id == analysis_run_id,
            )
        )
        if run is None:
            raise LookupError("经营分析运行不存在")
        scope_type = run.scope_type
        scope_id = actor.enterprise_id if run.scope_type == "enterprise" else run.scope_key
    require_permission(
        actor,
        "action.propose",
        database,
        resource_type="business_analysis",
        resource_key=analysis_run_id,
        scope_type=scope_type,
        scope_id=scope_id,
    )

    now = datetime.now(UTC)
    with database.session() as session:
        run = session.get(BusinessAnalysisRun, analysis_run_id)
        if run is None or run.enterprise_id != actor.enterprise_id:
            raise LookupError("经营分析运行不存在")
        result = AnalysisResultPayload.model_validate(run.result)
        indexes = sorted(payload.recommendation_indexes)
        if any(index < 0 or index >= len(result.recommendations) for index in indexes):
            raise ApiProblem(
                status_code=422,
                code="action.business_analysis_recommendation_invalid",
                message="所选建议不属于当前经营分析运行",
                details={"available_recommendation_count": len(result.recommendations)},
            )
        existing_by_index = {
            proposal.source_action_index: proposal
            for proposal in session.scalars(
                select(ActionProposal).where(
                    ActionProposal.business_analysis_run_id == run.id,
                    ActionProposal.source_action_index.in_(indexes),
                )
            )
        }
        for index, proposal in existing_by_index.items():
            if proposal.due_hint != payload.due_hint:
                raise ApiProblem(
                    status_code=409,
                    code="action.business_analysis_recommendation_already_proposed",
                    message="该经营建议已使用不同时间要求进入行动中心",
                    details={"recommendation_index": index, "proposal_key": proposal.proposal_key},
                )

        items: list[ActionProposal] = []
        created: list[ActionProposal] = []
        for index in indexes:
            existing = existing_by_index.get(index)
            if existing is not None:
                items.append(existing)
                continue
            recommendation = result.recommendations[index]
            proposal_idempotency_key = f"{payload.idempotency_key}:{index}"
            idempotency_conflict = session.scalar(
                select(ActionProposal).where(
                    ActionProposal.enterprise_id == actor.enterprise_id,
                    ActionProposal.idempotency_key == proposal_idempotency_key,
                )
            )
            if idempotency_conflict is not None:
                raise ApiProblem(
                    status_code=409,
                    code="action.idempotency_conflict",
                    message="行动提案幂等键已被不同来源建议使用",
                )
            proposal = ActionProposal(
                id=f"action_proposal_{uuid4().hex}",
                enterprise_id=run.enterprise_id,
                proposal_key=f"act-analysis-{run.id[-16:]}-{index + 1:02d}",
                source_type="business-analysis",
                source_key=run.id,
                source_label=result.headline[:300],
                scope_type=run.scope_type,
                scope_key=run.scope_key,
                meeting_id=None,
                decision_package_id=None,
                customer_operation_run_id=None,
                business_analysis_run_id=run.id,
                evidence_snapshot_id=run.evidence_snapshot_id,
                source_action_index=index,
                title=recommendation.title,
                owner=recommendation.owner_role,
                due_hint=payload.due_hint,
                kpi=recommendation.success_metric,
                stop_condition=recommendation.stop_condition,
                evidence_refs=recommendation.evidence_refs,
                target_system="internal-action-workbench",
                target_key=f"business-analysis:{run.scope_key}:{index + 1}",
                risk_level="R2",
                action_level="R2",
                parameters={
                    "action": recommendation.action,
                    "priority": recommendation.priority,
                    "analysis_type": run.analysis_type,
                    "window_days": run.window_days,
                    "external_write": False,
                },
                status="pending_approval",
                requested_by_actor_key=actor.actor_key,
                requested_by_name=actor.display_name,
                idempotency_key=proposal_idempotency_key,
                approved_by_actor_key=None,
                approved_by_name=None,
                approved_at=None,
                decision_comment=None,
                created_at=now,
                updated_at=now,
            )
            session.add(proposal)
            items.append(proposal)
            created.append(proposal)
        if created:
            session.add(
                PlatformEvent(
                    id=f"event_{uuid4().hex}",
                    enterprise_id=run.enterprise_id,
                    event_type="business_analysis_actions_proposed",
                    severity="info",
                    title="经营诊断建议已进入行动审批",
                    detail=f"{run.scope_label} · {len(created)} 条 R2 行动提案 · 外部写入 0",
                    occurred_at=now,
                )
            )
        session.commit()
        views = [action_proposal_view(session, item) for item in items]
    return BusinessAnalysisActionProposalResponse(
        idempotent=not created,
        created_count=len(created),
        items=views,
    )


def list_action_work_items(
    database: Database,
    actor: ActorContext,
    *,
    status: WorkStatus | None = None,
) -> ActionWorkListResponse:
    require_permission(
        actor,
        "action.work.read",
        database,
        resource_type="action_work_item",
        resource_key="action-workbench",
    )
    with database.session() as session:
        all_items = list(
            session.scalars(
                select(ActionWorkItem)
                .where(ActionWorkItem.enterprise_id == actor.enterprise_id)
                .order_by(ActionWorkItem.updated_at.desc(), ActionWorkItem.created_at.desc())
            )
        )
        all_items = [
            item
            for item in all_items
            if actor_scope_allows(
                actor,
                scope_type=item.scope_type,
                scope_id=actor.enterprise_id if item.scope_type == "enterprise" else item.scope_key,
            )
        ]
        selected = [item for item in all_items if item.status == status] if status else all_items
        return ActionWorkListResponse(
            actor_name=actor.display_name,
            can_manage="action.work.manage" in actor.permissions,
            stats=ActionWorkStats(
                total=len(all_items),
                ready=sum(item.status == "ready" for item in all_items),
                claimed=sum(item.status == "claimed" for item in all_items),
                in_progress=sum(item.status == "in_progress" for item in all_items),
                blocked=sum(item.status == "blocked" for item in all_items),
                completed=sum(item.status == "completed" for item in all_items),
                mine=sum(item.assignee_principal_id == actor.principal_id for item in all_items),
            ),
            items=[_action_work_item_view(session, item, actor) for item in selected],
            generated_at=datetime.now(UTC),
        )


def transition_action_work_item(
    database: Database,
    *,
    work_key: str,
    actor: ActorContext,
    payload: ActionWorkEventRequest,
) -> ActionWorkEventResponse:
    with database.session() as lookup_session:
        lookup_item = lookup_session.scalar(
            select(ActionWorkItem).where(
                ActionWorkItem.enterprise_id == actor.enterprise_id,
                ActionWorkItem.work_key == work_key,
            )
        )
        if lookup_item is None:
            raise LookupError("行动工作项不存在")
        scope_type = lookup_item.scope_type
        scope_id = (
            actor.enterprise_id if lookup_item.scope_type == "enterprise" else lookup_item.scope_key
        )
    permission = (
        "action.work.manage"
        if "action.work.manage" in actor.permissions
        else "action.work.update"
    )
    require_permission(
        actor,
        permission,
        database,
        resource_type="action_work_item",
        resource_key=work_key,
        scope_type=scope_type,
        scope_id=scope_id,
    )

    snapshot = {**actor.snapshot(),
                "scope_context": build_scope_context(database, actor).snapshot()}
    now = datetime.now(UTC)
    with database.session() as session:
        item = session.scalar(
            select(ActionWorkItem).where(
                ActionWorkItem.enterprise_id == actor.enterprise_id,
                ActionWorkItem.work_key == work_key,
            )
        )
        if item is None:
            raise LookupError("行动工作项不存在")
        existing_event = session.scalar(
            select(ActionWorkEvent).where(
                ActionWorkEvent.enterprise_id == actor.enterprise_id,
                ActionWorkEvent.idempotency_key == payload.idempotency_key,
            )
        )
        if existing_event is not None:
            if (
                existing_event.work_item_id != item.id
                or existing_event.event_type != payload.action
            ):
                raise ApiProblem(
                    status_code=409,
                    code="action.work.idempotency_conflict",
                    message="工作项幂等键已被不同操作使用",
                )
            return ActionWorkEventResponse(
                idempotent=True,
                item=_action_work_item_view(session, item, actor),
            )
        if item.version != payload.expected_version:
            raise ApiProblem(
                status_code=409,
                code="action.work.version_conflict",
                message="工作项已被其他人更新，请刷新后重试",
                details={
                    "expected_version": payload.expected_version,
                    "current_version": item.version,
                },
            )
        available = _available_work_actions(item, actor)
        if payload.action not in available:
            raise ApiProblem(
                status_code=409,
                code="action.work.invalid_transition",
                message="当前状态或负责人不允许执行该操作",
                details={"status": item.status, "available_actions": available},
            )

        from_status = item.status
        if payload.action == "claim":
            item.status = "claimed"
            item.assignee_principal_id = actor.principal_id
            item.assignee_name = actor.display_name
            item.claimed_at = now
        elif payload.action == "start":
            item.status = "in_progress"
            item.started_at = item.started_at or now
            item.blocked_at = None
            item.blocker_reason = None
        elif payload.action == "block":
            item.status = "blocked"
            item.blocked_at = now
            item.blocker_reason = payload.comment
        elif payload.action == "complete":
            item.status = "completed"
            item.completed_at = now
            item.result_summary = payload.comment
            item.result_evidence_refs = payload.evidence_refs
            item.blocked_at = None
            item.blocker_reason = None
        elif payload.action == "release":
            item.status = "ready"
            item.assignee_principal_id = None
            item.assignee_name = None
            item.claimed_at = None
            item.blocked_at = None
            item.blocker_reason = None
        else:
            item.status = "claimed" if item.assignee_principal_id else "ready"
            item.completed_at = None
            item.result_summary = None
            item.result_evidence_refs = []

        item.version += 1
        item.updated_at = now
        session.add(
            ActionWorkEvent(
                id=f"action_work_event_{uuid4().hex}",
                enterprise_id=item.enterprise_id,
                work_item_id=item.id,
                actor_principal_id=actor.principal_id,
                actor_name=actor.display_name,
                event_type=payload.action,
                from_status=from_status,
                to_status=item.status,
                comment=payload.comment,
                evidence_refs=payload.evidence_refs,
                idempotency_key=payload.idempotency_key,
                actor_snapshot=snapshot,
                created_at=now,
            )
        )
        session.add(
            PlatformEvent(
                id=f"event_{uuid4().hex}",
                enterprise_id=item.enterprise_id,
                event_type=f"action_work_{payload.action}",
                severity="warning" if payload.action == "block" else "info",
                title=f"行动工作项已{_work_action_label(payload.action)}",
                detail=f"{item.title} · {actor.display_name} · v{item.version}",
                occurred_at=now,
            )
        )
        session.commit()
        return ActionWorkEventResponse(
            idempotent=False,
            item=_action_work_item_view(session, item, actor),
        )


def _action_work_item_view(
    session: Session,
    item: ActionWorkItem,
    actor: ActorContext,
) -> ActionWorkItemView:
    proposal = session.get(ActionProposal, item.proposal_id)
    if proposal is None:
        raise LookupError("工作项关联的行动提案不存在")
    proposal_view = action_proposal_view(session, proposal)
    events = list(
        session.scalars(
            select(ActionWorkEvent)
            .where(ActionWorkEvent.work_item_id == item.id)
            .order_by(ActionWorkEvent.created_at)
        )
    )
    available = _available_work_actions(item, actor)
    return ActionWorkItemView(
        id=item.id,
        key=item.work_key,
        proposal_key=proposal.proposal_key,
        source_type=proposal_view.source_type,
        source_label=proposal.source_label,
        source_route=proposal_view.source_route,
        scope_type=cast(Literal["enterprise", "store", "object"], item.scope_type),
        scope_key=item.scope_key,
        title=item.title,
        owner_role=item.owner_role,
        due_hint=item.due_hint,
        kpi=item.kpi,
        stop_condition=item.stop_condition,
        priority=cast(Literal["normal", "high", "urgent"], item.priority),
        status=cast(WorkStatus, item.status),
        assignee_principal_id=item.assignee_principal_id,
        assignee_name=item.assignee_name,
        version=item.version,
        can_update=bool(available),
        available_actions=available,
        blocker_reason=item.blocker_reason,
        result_summary=item.result_summary,
        result_evidence_refs=item.result_evidence_refs,
        claimed_at=item.claimed_at,
        started_at=item.started_at,
        blocked_at=item.blocked_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        events=[
            ActionWorkEventView(
                id=event.id,
                event_type=cast(WorkAction | Literal["created"], event.event_type),
                from_status=event.from_status,
                to_status=cast(WorkStatus, event.to_status),
                actor_principal_id=event.actor_principal_id,
                actor_name=event.actor_name,
                comment=event.comment,
                evidence_refs=event.evidence_refs,
                idempotency_key=event.idempotency_key,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


def _available_work_actions(item: ActionWorkItem, actor: ActorContext) -> list[WorkAction]:
    can_update = "action.work.update" in actor.permissions
    can_manage = "action.work.manage" in actor.permissions
    is_assignee = item.assignee_principal_id == actor.principal_id
    if item.status == "ready" and (can_update or can_manage):
        return ["claim"]
    if not (is_assignee or can_manage):
        return []
    if item.status == "claimed":
        return ["start", "release"]
    if item.status == "in_progress":
        return ["block", "complete", "release"]
    if item.status == "blocked":
        return ["start", "release"]
    if item.status == "completed" and can_manage:
        return ["reopen"]
    return []


def _work_action_label(action: WorkAction) -> str:
    return {
        "claim": "领取",
        "start": "开始",
        "block": "标记阻塞",
        "complete": "完成",
        "release": "释放",
        "reopen": "重新打开",
    }[action]
