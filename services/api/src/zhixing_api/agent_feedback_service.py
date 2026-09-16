from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import and_, or_, select

from zhixing_api.actor_context import ActorContext
from zhixing_api.agent_feedback_schemas import (
    AgentFeedbackCaseActionRequest,
    AgentFeedbackEventView,
    AgentFeedbackStats,
    AgentFeedbackStudioResponse,
    AgentFeedbackSubmitRequest,
    AgentRunFeedbackResponse,
    FeedbackKind,
    HandoffPriority,
    HandoffStatus,
    HumanHandoffCaseView,
    ResolutionType,
)
from zhixing_api.data_models import (
    AgentFeedbackEvent,
    AgentRun,
    EvaluationCandidate,
    HumanHandoffCase,
    Principal,
    RoleTwinProfile,
    RoleTwinVersion,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.evaluation_service import propose_evaluation_candidate_from_resolution


def get_agent_run_feedback(
    database: Database,
    actor: ActorContext,
    agent_run_id: str,
    *,
    idempotent: bool = False,
    feedback_event_id: str | None = None,
) -> AgentRunFeedbackResponse:
    with database.session() as session:
        run = session.get(AgentRun, agent_run_id)
        if run is None or run.enterprise_id != actor.enterprise_id:
            raise ApiProblem(
                status_code=404,
                code="agent_feedback.run_not_found",
                message="未找到可反馈的智能体运行",
            )
        _require_run_access(actor, run)
        case_query = select(HumanHandoffCase).where(
            HumanHandoffCase.enterprise_id == actor.enterprise_id,
            HumanHandoffCase.agent_run_id == run.id,
        )
        if "agent-feedback.review" not in actor.permissions:
            case_query = case_query.where(
                HumanHandoffCase.opened_by_principal_id == actor.principal_id
            )
        handoff_case = session.scalar(case_query.order_by(HumanHandoffCase.opened_at))
        if handoff_case is not None:
            event_scope = (
                AgentFeedbackEvent.handoff_case_id == handoff_case.id
                if "agent-feedback.review" in actor.permissions
                else or_(
                    AgentFeedbackEvent.handoff_case_id == handoff_case.id,
                    and_(
                        AgentFeedbackEvent.handoff_case_id.is_(None),
                        AgentFeedbackEvent.actor_principal_id == actor.principal_id,
                    ),
                )
            )
        else:
            event_scope = AgentFeedbackEvent.actor_principal_id == actor.principal_id
        events = list(
            session.scalars(
                select(AgentFeedbackEvent)
                .where(
                    AgentFeedbackEvent.enterprise_id == actor.enterprise_id,
                    AgentFeedbackEvent.agent_run_id == run.id,
                    event_scope,
                )
                .order_by(AgentFeedbackEvent.created_at)
            )
        )
        case_ids = [handoff_case.id] if handoff_case else []
        views = _build_views(
            runs=[run],
            cases=[handoff_case] if handoff_case else [],
            events=events,
            case_ids=case_ids,
            session=session,
        )
        feedback = next(
            (
                _event_view(item, views.principal_by_id)
                for item in events
                if item.id == feedback_event_id
            ),
            None,
        )
        return AgentRunFeedbackResponse(
            agent_run_id=run.id,
            idempotent=idempotent,
            feedback=feedback,
            feedback_events=[_event_view(item, views.principal_by_id) for item in events],
            handoff_case=views.case_views.get(handoff_case.id) if handoff_case else None,
        )


def submit_agent_run_feedback(
    database: Database,
    actor: ActorContext,
    agent_run_id: str,
    payload: AgentFeedbackSubmitRequest,
) -> AgentRunFeedbackResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        run = session.get(AgentRun, agent_run_id)
        if run is None or run.enterprise_id != actor.enterprise_id:
            raise ApiProblem(
                status_code=404,
                code="agent_feedback.run_not_found",
                message="未找到可反馈的智能体运行",
            )
        _require_run_access(actor, run)
        existing_event = session.scalar(
            select(AgentFeedbackEvent).where(
                AgentFeedbackEvent.enterprise_id == actor.enterprise_id,
                AgentFeedbackEvent.idempotency_key == payload.client_request_key,
            )
        )
        if existing_event is not None:
            if existing_event.agent_run_id != run.id:
                raise ApiProblem(
                    status_code=409,
                    code="agent_feedback.idempotency_conflict",
                    message="该反馈幂等键已用于其他运行",
                )
            event_id = existing_event.id
            duplicate = True
        else:
            handoff_case = None
            if payload.kind != "helpful":
                handoff_case = session.scalar(
                    select(HumanHandoffCase).where(
                        HumanHandoffCase.enterprise_id == actor.enterprise_id,
                        HumanHandoffCase.agent_run_id == run.id,
                        HumanHandoffCase.opened_by_principal_id == actor.principal_id,
                    )
                )
                if handoff_case is None:
                    handoff_case = HumanHandoffCase(
                        id=f"handoff_case_{uuid4().hex}",
                        enterprise_id=actor.enterprise_id,
                        agent_run_id=run.id,
                        opened_by_principal_id=actor.principal_id,
                        assigned_to_principal_id=None,
                        status="open",
                        priority=payload.priority,
                        category=payload.kind,
                        subject=run.question[:240],
                        resolution_type=None,
                        resolution_summary=None,
                        opened_at=now,
                        updated_at=now,
                        resolved_at=None,
                    )
                    session.add(handoff_case)
                    session.flush()
                elif handoff_case.status == "resolved":
                    handoff_case.status = "open"
                    handoff_case.priority = payload.priority
                    handoff_case.category = payload.kind
                    handoff_case.resolution_type = None
                    handoff_case.resolution_summary = None
                    handoff_case.resolved_at = None
                    handoff_case.updated_at = now
            event = AgentFeedbackEvent(
                id=f"agent_feedback_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                agent_run_id=run.id,
                handoff_case_id=handoff_case.id if handoff_case else None,
                actor_principal_id=actor.principal_id,
                event_type="feedback_submitted",
                feedback_kind=payload.kind,
                message=payload.message,
                expected_answer=payload.expected_answer,
                from_status=None,
                to_status=handoff_case.status if handoff_case else None,
                idempotency_key=payload.client_request_key,
                actor_snapshot=actor.snapshot(),
                request_id=actor.request_id,
                run_id=actor.run_id,
                created_at=now,
            )
            session.add(event)
            session.commit()
            event_id = event.id
            duplicate = False
    return get_agent_run_feedback(
        database,
        actor,
        agent_run_id,
        idempotent=duplicate,
        feedback_event_id=event_id,
    )


def list_agent_feedback_studio(
    database: Database,
    actor: ActorContext,
    *,
    opened_by_principal_id: str | None = None,
) -> AgentFeedbackStudioResponse:
    with database.session() as session:
        case_query = select(HumanHandoffCase).where(
            HumanHandoffCase.enterprise_id == actor.enterprise_id
        )
        if opened_by_principal_id is not None:
            case_query = case_query.where(
                HumanHandoffCase.opened_by_principal_id == opened_by_principal_id
            )
        cases = list(
            session.scalars(case_query)
        )
        run_ids = [item.agent_run_id for item in cases]
        runs = (
            list(session.scalars(select(AgentRun).where(AgentRun.id.in_(run_ids))))
            if run_ids
            else []
        )
        case_ids = [item.id for item in cases]
        events = list(
            session.scalars(
                select(AgentFeedbackEvent)
                .where(AgentFeedbackEvent.handoff_case_id.in_(case_ids))
                .order_by(AgentFeedbackEvent.created_at)
            )
        ) if case_ids else []
        views = _build_views(
            runs=runs,
            cases=cases,
            events=events,
            case_ids=case_ids,
            session=session,
        )
    priority_order = {"urgent": 0, "high": 1, "normal": 2}
    status_order = {"open": 0, "in_review": 1, "resolved": 2}
    ordered = sorted(
        cases,
        key=lambda item: (
            status_order.get(item.status, 3),
            priority_order.get(item.priority, 3),
            -item.updated_at.timestamp(),
        ),
    )
    return AgentFeedbackStudioResponse(
        stats=AgentFeedbackStats(
            case_count=len(cases),
            open_count=sum(item.status == "open" for item in cases),
            in_review_count=sum(item.status == "in_review" for item in cases),
            urgent_count=sum(
                item.priority == "urgent" and item.status != "resolved" for item in cases
            ),
            resolved_count=sum(item.status == "resolved" for item in cases),
            feedback_event_count=len(events),
        ),
        cases=[views.case_views[item.id] for item in ordered],
        generated_at=datetime.now(UTC),
    )


def act_on_handoff_case(
    database: Database,
    actor: ActorContext,
    case_id: str,
    payload: AgentFeedbackCaseActionRequest,
) -> AgentRunFeedbackResponse:
    now = datetime.now(UTC)
    should_propose_candidate = False
    with database.session() as session:
        handoff_case = session.get(HumanHandoffCase, case_id)
        if handoff_case is None or handoff_case.enterprise_id != actor.enterprise_id:
            raise ApiProblem(
                status_code=404,
                code="agent_feedback.case_not_found",
                message="人工接管工单不存在",
            )
        duplicate = session.scalar(
            select(AgentFeedbackEvent).where(
                AgentFeedbackEvent.enterprise_id == actor.enterprise_id,
                AgentFeedbackEvent.idempotency_key == payload.client_request_key,
            )
        )
        if duplicate is not None:
            if duplicate.handoff_case_id != case_id:
                raise ApiProblem(
                    status_code=409,
                    code="agent_feedback.idempotency_conflict",
                    message="该处理幂等键已用于其他工单",
                )
            event_id = duplicate.id
            run_id = handoff_case.agent_run_id
            should_propose_candidate = duplicate.event_type == "resolved"
        else:
            from_status = handoff_case.status
            event_type: Literal["assigned", "note_added", "resolved", "reopened"]
            if payload.action == "assign_to_me":
                if handoff_case.status == "resolved":
                    raise _transition_problem("已解决工单需要先重开")
                handoff_case.assigned_to_principal_id = actor.principal_id
                handoff_case.status = "in_review"
                event_type = "assigned"
            elif payload.action == "add_note":
                event_type = "note_added"
            elif payload.action == "resolve":
                if handoff_case.status == "resolved":
                    raise _transition_problem("工单已经解决")
                if payload.resolution_type is None or not payload.resolution_summary:
                    raise ApiProblem(
                        status_code=422,
                        code="agent_feedback.resolution_required",
                        message="解决工单必须选择处理类型并填写处理结论",
                    )
                handoff_case.assigned_to_principal_id = (
                    handoff_case.assigned_to_principal_id or actor.principal_id
                )
                handoff_case.status = "resolved"
                handoff_case.resolution_type = payload.resolution_type
                handoff_case.resolution_summary = payload.resolution_summary
                handoff_case.resolved_at = now
                event_type = "resolved"
            else:
                if handoff_case.status != "resolved":
                    raise _transition_problem("只有已解决工单可以重开")
                handoff_case.status = "open"
                handoff_case.assigned_to_principal_id = None
                handoff_case.resolution_type = None
                handoff_case.resolution_summary = None
                handoff_case.resolved_at = None
                event_type = "reopened"
            handoff_case.updated_at = now
            event = AgentFeedbackEvent(
                id=f"agent_feedback_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                agent_run_id=handoff_case.agent_run_id,
                handoff_case_id=handoff_case.id,
                actor_principal_id=actor.principal_id,
                event_type=event_type,
                feedback_kind=None,
                message=payload.message,
                expected_answer=payload.resolution_summary,
                from_status=from_status,
                to_status=handoff_case.status,
                idempotency_key=payload.client_request_key,
                actor_snapshot=actor.snapshot(),
                request_id=actor.request_id,
                run_id=actor.run_id,
                created_at=now,
            )
            session.add(event)
            session.commit()
            event_id = event.id
            run_id = handoff_case.agent_run_id
            should_propose_candidate = event_type == "resolved"
    if should_propose_candidate:
        propose_evaluation_candidate_from_resolution(
            database,
            actor,
            handoff_case_id=case_id,
            feedback_event_id=event_id,
        )
    return get_agent_run_feedback(
        database,
        actor,
        run_id,
        idempotent=duplicate is not None,
        feedback_event_id=event_id,
    )


class _ViewBundle:
    def __init__(
        self,
        *,
        principal_by_id: dict[str, Principal],
        case_views: dict[str, HumanHandoffCaseView],
    ) -> None:
        self.principal_by_id = principal_by_id
        self.case_views = case_views


def _build_views(*, runs, cases, events, case_ids, session) -> _ViewBundle:  # type: ignore[no-untyped-def]
    principal_ids = {
        *(item.actor_principal_id for item in events),
        *(item.opened_by_principal_id for item in cases),
        *(item.assigned_to_principal_id for item in cases if item.assigned_to_principal_id),
    }
    principals = (
        list(session.scalars(select(Principal).where(Principal.id.in_(principal_ids))))
        if principal_ids
        else []
    )
    principal_by_id = {item.id: item for item in principals}
    run_by_id = {item.id: item for item in runs}
    profile_ids = {item.twin_profile_id for item in runs}
    profiles = (
        list(
            session.scalars(
                select(RoleTwinProfile).where(RoleTwinProfile.id.in_(profile_ids))
            )
        )
        if profile_ids
        else []
    )
    profile_by_id = {item.id: item for item in profiles}
    version_ids = {item.role_twin_version_id for item in runs if item.role_twin_version_id}
    versions = (
        list(
            session.scalars(
                select(RoleTwinVersion).where(RoleTwinVersion.id.in_(version_ids))
            )
        )
        if version_ids
        else []
    )
    version_by_id = {item.id: item for item in versions}
    candidates = (
        list(
            session.scalars(
                select(EvaluationCandidate)
                .where(EvaluationCandidate.source_handoff_case_id.in_(case_ids))
                .order_by(EvaluationCandidate.created_at.desc())
            )
        )
        if case_ids
        else []
    )
    candidate_by_case = {
        item.source_handoff_case_id: item
        for item in reversed(candidates)
    }
    events_by_case: dict[str, list[AgentFeedbackEvent]] = defaultdict(list)
    for event in events:
        if event.handoff_case_id:
            events_by_case[event.handoff_case_id].append(event)
    case_views: dict[str, HumanHandoffCaseView] = {}
    for item in cases:
        run = run_by_id[item.agent_run_id]
        profile = profile_by_id[run.twin_profile_id]
        version = version_by_id.get(run.role_twin_version_id)
        opener = principal_by_id[item.opened_by_principal_id]
        assignee = principal_by_id.get(item.assigned_to_principal_id)
        candidate = candidate_by_case.get(item.id)
        case_views[item.id] = HumanHandoffCaseView(
            id=item.id,
            agent_run_id=run.id,
            twin_key=profile.twin_key,
            twin_name=profile.display_name,
            role_twin_version_number=version.version_number if version else None,
            question=run.question,
            answer=run.answer,
            execution_mode=(
                "model"
                if run.provider == "openai-compatible-responses"
                else "evidence-fallback"
            ),
            opened_by_principal_id=opener.id,
            opened_by_name=opener.display_name,
            assigned_to_principal_id=assignee.id if assignee else None,
            assigned_to_name=assignee.display_name if assignee else None,
            status=cast(HandoffStatus, item.status),
            priority=cast(HandoffPriority, item.priority),
            category=cast(FeedbackKind, item.category),
            subject=item.subject,
            resolution_type=cast(ResolutionType | None, item.resolution_type),
            resolution_summary=item.resolution_summary,
            evaluation_candidate_id=candidate.id if candidate else None,
            evaluation_candidate_status=(
                cast(Literal["pending", "accepted", "rejected"], candidate.status)
                if candidate
                else None
            ),
            opened_at=item.opened_at,
            updated_at=item.updated_at,
            resolved_at=item.resolved_at,
            events=[_event_view(event, principal_by_id) for event in events_by_case[item.id]],
        )
    return _ViewBundle(principal_by_id=principal_by_id, case_views=case_views)


def _event_view(
    event: AgentFeedbackEvent,
    principal_by_id: dict[str, Principal],
) -> AgentFeedbackEventView:
    principal = principal_by_id[event.actor_principal_id]
    return AgentFeedbackEventView(
        id=event.id,
        event_type=cast(
            Literal[
                "feedback_submitted",
                "assigned",
                "note_added",
                "resolved",
                "reopened",
            ],
            event.event_type,
        ),
        feedback_kind=cast(FeedbackKind | None, event.feedback_kind),
        actor_principal_id=principal.id,
        actor_name=principal.display_name,
        message=event.message,
        expected_answer=event.expected_answer,
        from_status=cast(HandoffStatus | None, event.from_status),
        to_status=cast(HandoffStatus | None, event.to_status),
        created_at=event.created_at,
    )


def _require_run_access(actor: ActorContext, run: AgentRun) -> None:
    if "agent-feedback.review" in actor.permissions:
        return
    if run.actor_principal_id != actor.principal_id:
        raise ApiProblem(
            status_code=403,
            code="agent_feedback.run_not_owned",
            message="当前身份只能查看和反馈自己发起的回答",
        )


def _transition_problem(message: str) -> ApiProblem:
    return ApiProblem(
        status_code=409,
        code="agent_feedback.invalid_transition",
        message=message,
    )
