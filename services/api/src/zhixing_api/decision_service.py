from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from zhixing_agent_runtime import (
    AgentActor,
    AgentRunEvent,
    AgentRunSpec,
    AgentRuntime,
    RuntimeCredentials,
)

from zhixing_api.action_service import action_proposal_view, confirmation_view
from zhixing_api.actor_context import ActorContext, actor_scope_allows, resolve_enterprise_id
from zhixing_api.agent_runtime_service import (
    append_runtime_event,
    create_runtime_session,
    mark_runtime_session_failed,
)
from zhixing_api.ai_provider import AICompletion, AIProviderError, ResponsesAIProvider
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    ActionProposal,
    AgentRun,
    AgentRunEvidence,
    ApprovedMemory,
    DecisionPackage,
    EvidenceSnapshot,
    EvidenceSnapshotItem,
    MeetingClaim,
    MeetingDecisionConfirmation,
    MeetingDeliberationTurn,
    MemoryCandidate,
    MetricDefinition,
    MetricSnapshot,
    PlatformEvent,
    Principal,
    RoleTwinProfile,
    TwinActor,
    TwinMeeting,
    TwinMeetingParticipant,
    TwinMeetingSeat,
    TwinScene,
)
from zhixing_api.database import Database
from zhixing_api.decision_schemas import (
    CROSS_EXAMINATION_JSON_SCHEMA,
    DECISION_PACKAGE_JSON_SCHEMA,
    RISK_REVIEW_JSON_SCHEMA,
    ROLE_ANALYSIS_JSON_SCHEMA,
    ClaimItem,
    CrossExaminationItem,
    CrossExaminationPayload,
    DecisionAction,
    DecisionPackagePayload,
    DecisionPackageView,
    DigitalMeetingDetailResponse,
    EvidenceSnapshotItemView,
    EvidenceSnapshotView,
    MeetingClaimView,
    MeetingCreateRequest,
    MeetingCreateResponse,
    MeetingDeliberationTurnView,
    MeetingListItem,
    MeetingListResponse,
    MeetingParticipantView,
    MeetingRunResponse,
    MeetingScopeView,
    MeetingTemplateView,
    MemoryCandidateListResponse,
    MemoryCandidateView,
    RiskFailureMode,
    RiskReviewPayload,
    RoleAnalysisPayload,
    RoleTwinCatalogItem,
    RoleTwinCatalogResponse,
    TwinCatalogStats,
)
from zhixing_api.errors import ApiProblem
from zhixing_api.knowledge_service import search_evidence
from zhixing_api.mcp_schemas import McpSessionCreateRequest, McpSessionRevokeRequest
from zhixing_api.mcp_session_service import create_mcp_session, revoke_mcp_session
from zhixing_api.meeting_runtime_service import (
    create_meeting_runtime_run,
    update_meeting_runtime_run,
)
from zhixing_api.runtime_skill_service import select_runtime_skill
from zhixing_api.scope_context import build_scope_context
from zhixing_api.seed import MEETING_SCENE_ID
from zhixing_api.tool_service import list_tool_catalog
from zhixing_api.workspace_service import actor_snapshot_with_workspace

ExecutionMode = Literal["model", "evidence-fallback"]

MEETING_TEMPLATES: tuple[MeetingTemplateView, ...] = (
    MeetingTemplateView(
        key="budget-inventory-review",
        label="预算与库存联动",
        description="联合检查广告预算、转化效率、库存覆盖和停止条件。",
        default_title="广告预算与库存联动研判",
        default_topic="广告投入变化与库存覆盖出现背离，下一周期预算和补货节奏应如何调整？",
        default_success_metric="广告 ROI、退款率与库存覆盖保持在可复盘的联合约束内",
    ),
    MeetingTemplateView(
        key="inventory-clearance-review",
        label="滞销库存清理",
        description="评估清仓折扣、投放节奏、毛利和客户体验的联合影响。",
        default_title="滞销库存清理策略研判",
        default_topic="当前滞销库存是否应通过折扣和定向投放加速清理，并设置哪些风险边界？",
        default_success_metric="降低滞销库存，同时保持毛利、退款率与履约质量在约束内",
    ),
    MeetingTemplateView(
        key="kpi-incentive-review",
        label="KPI 激励复核",
        description="识别单指标激励、短期行为和跨部门目标冲突。",
        default_title="经营 KPI 激励机制研判",
        default_topic="当前 KPI 是否造成只追求成交而忽视退款、履约与客户体验的问题？",
        default_success_metric="形成兼顾增长、质量、履约和客户体验的可复盘 KPI 方案",
    ),
)


def list_role_twins(
    database: Database, enterprise_id: str | None = None
) -> RoleTwinCatalogResponse:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    now = datetime.now(UTC)
    with database.session() as session:
        profiles = list(
            session.scalars(
                select(RoleTwinProfile)
                .where(RoleTwinProfile.enterprise_id == enterprise_id)
                .order_by(RoleTwinProfile.published_at, RoleTwinProfile.twin_key)
            )
        )
        actors = {
            actor.actor_key: actor
            for actor in session.scalars(
                select(TwinActor).where(TwinActor.enterprise_id == enterprise_id)
            )
        }
        memories = list(
            session.scalars(
                select(MemoryCandidate).where(MemoryCandidate.enterprise_id == enterprise_id)
            )
        )
        runs = list(
            session.scalars(select(AgentRun).where(AgentRun.enterprise_id == enterprise_id))
        )

    items: list[RoleTwinCatalogItem] = []
    for profile in profiles:
        profile_memories = [item for item in memories if item.twin_profile_id == profile.id]
        profile_runs = [item for item in runs if item.twin_profile_id == profile.id]
        actor = actors.get(profile.twin_key)
        items.append(
            RoleTwinCatalogItem(
                key=profile.twin_key,
                display_name=profile.display_name,
                role_title=profile.role_title,
                status=profile.status,
                provider=profile.provider,
                model=profile.model,
                capabilities=actor.capabilities if actor else [],
                voice_guide=profile.voice_guide,
                reasoning_guide=profile.reasoning_guide,
                answer_policy=profile.answer_policy,
                active_memory_count=sum(item.status == "active" for item in profile_memories),
                candidate_memory_count=sum(item.status == "candidate" for item in profile_memories),
                conflicted_memory_count=sum(
                    item.conflict_status == "conflicted" for item in profile_memories
                ),
                run_count=len(profile_runs),
                published_at=profile.published_at,
                latest_run_at=max((item.created_at for item in profile_runs), default=None),
                updated_at=profile.updated_at,
            )
        )
    return RoleTwinCatalogResponse(
        stats=TwinCatalogStats(
            profile_count=len(profiles),
            active_memory_count=sum(item.status == "active" for item in memories),
            candidate_memory_count=sum(item.status == "candidate" for item in memories),
            conflicted_memory_count=sum(item.conflict_status == "conflicted" for item in memories),
            agent_run_count=len(runs),
        ),
        items=items,
        generated_at=now,
    )


def list_memories(
    database: Database, enterprise_id: str | None = None
) -> MemoryCandidateListResponse:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    with database.session() as session:
        rows = session.execute(
            select(MemoryCandidate, RoleTwinProfile)
            .join(RoleTwinProfile, RoleTwinProfile.id == MemoryCandidate.twin_profile_id)
            .where(MemoryCandidate.enterprise_id == enterprise_id)
            .order_by(MemoryCandidate.updated_at.desc())
        ).all()
        approved_by_candidate: dict[str, ApprovedMemory] = {}
        for approved in session.scalars(
            select(ApprovedMemory)
            .where(ApprovedMemory.enterprise_id == enterprise_id)
            .order_by(ApprovedMemory.candidate_id, ApprovedMemory.version_number.desc())
        ):
            approved_by_candidate.setdefault(approved.candidate_id, approved)
    return MemoryCandidateListResponse(
        status_counts=dict(Counter(candidate.status for candidate, _ in rows)),
        conflict_counts=dict(Counter(candidate.conflict_status for candidate, _ in rows)),
        items=[
            MemoryCandidateView(
                id=candidate.id,
                key=candidate.candidate_key,
                twin_key=profile.twin_key,
                twin_name=profile.display_name,
                category=candidate.category,
                content=candidate.content,
                source_type=candidate.source_type,
                source_ref=candidate.source_ref,
                confidence=candidate.confidence,
                conflict_status=candidate.conflict_status,
                conflict_ref=candidate.conflict_ref,
                evidence_refs=candidate.evidence_refs,
                status=candidate.status,
                reviewer=candidate.reviewer,
                review_reason=candidate.review_reason,
                reviewed_at=candidate.reviewed_at,
                effective_from=candidate.effective_from,
                retired_at=candidate.retired_at,
                approved_memory_id=(
                    approved_by_candidate[candidate.id].id
                    if candidate.id in approved_by_candidate
                    else None
                ),
                approved_memory_status=(
                    approved_by_candidate[candidate.id].status
                    if candidate.id in approved_by_candidate
                    else None
                ),
                memory_version=(
                    approved_by_candidate[candidate.id].version_number
                    if candidate.id in approved_by_candidate
                    else None
                ),
                created_at=candidate.created_at,
                updated_at=candidate.updated_at,
            )
            for candidate, profile in rows
        ],
        generated_at=datetime.now(UTC),
    )


def list_meetings(database: Database, actor: ActorContext) -> MeetingListResponse:
    enterprise_id = actor.enterprise_id
    with database.session() as session:
        catalog_meetings = list(
            session.scalars(
                select(TwinMeeting)
                .where(TwinMeeting.enterprise_id == enterprise_id)
                .order_by(TwinMeeting.updated_at.desc())
            )
        )
        meetings = [
            meeting
            for meeting in catalog_meetings
            if actor_scope_allows(
                actor,
                scope_type=meeting.scope_type,
                scope_id=(
                    actor.enterprise_id if meeting.scope_type == "enterprise" else meeting.scope_key
                ),
            )
        ]
        items = [_meeting_list_item(session, meeting) for meeting in meetings]
        scopes = _meeting_scope_catalog(session, actor, catalog_meetings)
    return MeetingListResponse(
        status_counts=dict(Counter(item.protocol_status for item in items)),
        templates=list(MEETING_TEMPLATES),
        scopes=scopes,
        items=items,
        generated_at=datetime.now(UTC),
    )


def get_meeting_scope(
    database: Database, meeting_key: str, enterprise_id: str | None = None
) -> tuple[str, str]:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    with database.session() as session:
        meeting = session.scalar(
            select(TwinMeeting).where(
                TwinMeeting.enterprise_id == enterprise_id,
                TwinMeeting.meeting_key == meeting_key,
            )
        )
        if meeting is None:
            raise LookupError("没有找到指定数字会议")
        return meeting.scope_type, meeting.scope_key


def create_digital_meeting(
    database: Database,
    actor: ActorContext,
    payload: MeetingCreateRequest,
) -> MeetingCreateResponse:
    snapshot = actor_snapshot_with_workspace(actor, payload.workspace_key)
    snapshot["scope_context"] = build_scope_context(database, actor).snapshot()
    request_material = payload.model_dump(mode="json", exclude={"client_request_key"})
    request_hash = sha256(
        json.dumps(
            request_material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    participant_keys = payload.participant_keys
    if len(participant_keys) != len(set(participant_keys)):
        raise ApiProblem(
            status_code=422,
            code="meeting.participant_duplicate",
            message="同一个角色分身不能重复参加同一会议",
        )
    if payload.scope_type == "enterprise" and payload.scope_key not in {
        "enterprise",
        actor.enterprise_id,
    }:
        raise ApiProblem(
            status_code=422,
            code="meeting.enterprise_scope_invalid",
            message="企业级会议必须使用 enterprise 作为数据范围键",
        )

    now = datetime.now(UTC)
    with database.session() as session:
        existing = session.scalar(
            select(TwinMeeting).where(
                TwinMeeting.enterprise_id == actor.enterprise_id,
                TwinMeeting.idempotency_key == payload.client_request_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ApiProblem(
                    status_code=409,
                    code="meeting.idempotency_conflict",
                    message="同一请求键已经用于不同的会议内容",
                )
            return MeetingCreateResponse(
                idempotent=True,
                meeting=_meeting_list_item(session, existing),
            )

        profile_rows = list(
            session.scalars(
                select(RoleTwinProfile).where(
                    RoleTwinProfile.enterprise_id == actor.enterprise_id,
                    RoleTwinProfile.twin_key.in_(participant_keys),
                    RoleTwinProfile.status == "published",
                    RoleTwinProfile.published_at.is_not(None),
                )
            )
        )
        profile_by_key = {profile.twin_key: profile for profile in profile_rows}
        unavailable = [key for key in participant_keys if key not in profile_by_key]
        if unavailable:
            raise ApiProblem(
                status_code=422,
                code="meeting.participant_unavailable",
                message="会议只能选择已发布且可用的角色分身",
                details={"participant_keys": unavailable},
            )

        scene = session.get(TwinScene, MEETING_SCENE_ID)
        if scene is None or scene.enterprise_id != actor.enterprise_id:
            raise ApiProblem(
                status_code=409,
                code="meeting.room_unavailable",
                message="数字决策会议空间尚未准备完成",
            )
        seats = list(
            session.scalars(
                select(TwinMeetingSeat)
                .where(
                    TwinMeetingSeat.scene_id == scene.id,
                    TwinMeetingSeat.status == "available",
                )
                .order_by(TwinMeetingSeat.sort_order)
                .limit(len(participant_keys))
            )
        )
        if len(seats) < len(participant_keys):
            raise ApiProblem(
                status_code=409,
                code="meeting.seat_capacity_exceeded",
                message="数字会议室可用席位不足",
            )

        meeting_key = f"mtg-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        normalized_scope_key = (
            "enterprise" if payload.scope_type == "enterprise" else payload.scope_key
        )
        meeting = TwinMeeting(
            id=f"meeting_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            scene_id=scene.id,
            meeting_key=meeting_key,
            title=payload.title.strip(),
            topic=payload.topic.strip(),
            status="scheduled",
            protocol_status="draft",
            template_key=payload.template_key,
            initiated_by_principal_id=actor.principal_id,
            actor_snapshot=snapshot,
            idempotency_key=payload.client_request_key,
            request_hash=request_hash,
            scope_type=payload.scope_type,
            scope_key=normalized_scope_key,
            decision_owner=actor.display_name,
            deadline_at=payload.deadline_at,
            success_metric=payload.success_metric.strip(),
            evidence_snapshot=f"pending:{meeting_key}",
            decision="等待数字会议运行",
            room_space_key="decision-room",
            next_transition_at=None,
            updated_at=now,
            created_at=now,
        )
        session.add(meeting)
        for index, (participant_key, seat) in enumerate(
            zip(participant_keys, seats, strict=True), start=1
        ):
            session.add(
                TwinMeetingParticipant(
                    id=f"participant_{uuid4().hex}",
                    meeting_id=meeting.id,
                    actor_key=participant_key,
                    seat_key=seat.seat_key,
                    position="等待独立研判",
                    finding="会议尚未运行",
                    status="invited",
                    speaking_order=index,
                )
            )
        session.add(
            PlatformEvent(
                id=f"event_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                event_type="decision_meeting_created",
                severity="info",
                title="已创建受治理数字会议",
                detail=(
                    f"{meeting.title} · {payload.scope_type}:{normalized_scope_key} · "
                    f"{len(participant_keys)} 位角色分身"
                ),
                occurred_at=now,
            )
        )
        session.flush()
        result = _meeting_list_item(session, meeting)
        session.commit()
        return MeetingCreateResponse(idempotent=False, meeting=result)


def get_meeting_detail(
    database: Database, meeting_key: str, enterprise_id: str | None = None
) -> DigitalMeetingDetailResponse:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    with database.session() as session:
        meeting = session.scalar(
            select(TwinMeeting).where(
                TwinMeeting.enterprise_id == enterprise_id,
                TwinMeeting.meeting_key == meeting_key,
            )
        )
        if meeting is None:
            raise LookupError("没有找到指定数字会议")
        meeting_item = _meeting_list_item(session, meeting)
        profiles = {
            profile.twin_key: profile
            for profile in session.scalars(
                select(RoleTwinProfile).where(RoleTwinProfile.enterprise_id == enterprise_id)
            )
        }
        profiles_by_id = {profile.id: profile for profile in profiles.values()}
        participants = list(
            session.scalars(
                select(TwinMeetingParticipant)
                .where(TwinMeetingParticipant.meeting_id == meeting.id)
                .order_by(TwinMeetingParticipant.speaking_order)
            )
        )
        snapshot = session.scalar(
            select(EvidenceSnapshot).where(
                EvidenceSnapshot.enterprise_id == enterprise_id,
                EvidenceSnapshot.snapshot_key == meeting.evidence_snapshot,
            )
        )
        snapshot_view = _snapshot_view(session, snapshot) if snapshot else None
        claim_rows = session.execute(
            select(MeetingClaim, RoleTwinProfile)
            .join(RoleTwinProfile, RoleTwinProfile.id == MeetingClaim.twin_profile_id)
            .where(MeetingClaim.meeting_id == meeting.id)
            .order_by(MeetingClaim.created_at, RoleTwinProfile.twin_key)
        ).all()
        deliberation_turns = list(
            session.scalars(
                select(MeetingDeliberationTurn)
                .where(MeetingDeliberationTurn.meeting_id == meeting.id)
                .order_by(
                    MeetingDeliberationTurn.round_number,
                    MeetingDeliberationTurn.created_at,
                )
            )
        )
        decision = session.scalar(
            select(DecisionPackage).where(DecisionPackage.meeting_id == meeting.id)
        )
        confirmation = session.scalar(
            select(MeetingDecisionConfirmation).where(
                MeetingDecisionConfirmation.meeting_id == meeting.id
            )
        )
        action_proposals = list(
            session.scalars(
                select(ActionProposal)
                .where(ActionProposal.meeting_id == meeting.id)
                .order_by(ActionProposal.source_action_index)
            )
        )
        confirmation_result = confirmation_view(session, confirmation) if confirmation else None
        action_proposal_results = [
            action_proposal_view(session, proposal) for proposal in action_proposals
        ]

    return DigitalMeetingDetailResponse(
        meeting=meeting_item,
        participants=[
            MeetingParticipantView(
                actor_key=participant.actor_key,
                role_name=profiles[participant.actor_key].display_name
                if participant.actor_key in profiles
                else participant.actor_key,
                position=participant.position,
                finding=participant.finding,
                status=participant.status,
                speaking_order=participant.speaking_order,
            )
            for participant in participants
        ],
        evidence=snapshot_view,
        claims=[_claim_view(claim, profile) for claim, profile in claim_rows],
        deliberation_turns=[
            _deliberation_turn_view(
                turn,
                profiles_by_id[turn.speaker_twin_profile_id],
                profiles_by_id.get(turn.target_twin_profile_id)
                if turn.target_twin_profile_id
                else None,
            )
            for turn in deliberation_turns
        ],
        decision_package=_decision_view(decision) if decision else None,
        confirmation=confirmation_result,
        action_proposals=action_proposal_results,
        generated_at=datetime.now(UTC),
    )


async def run_digital_meeting(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    actor: ActorContext,
    *,
    meeting_key: str,
    refresh_evidence: bool,
    runtime: AgentRuntime | None = None,
) -> MeetingRunResponse:
    enterprise_id = actor.enterprise_id
    started = perf_counter()
    with database.session() as session:
        meeting = session.scalar(
            select(TwinMeeting).where(
                TwinMeeting.enterprise_id == enterprise_id,
                TwinMeeting.meeting_key == meeting_key,
            )
        )
        if meeting is None:
            raise LookupError("没有找到指定数字会议")
        confirmed_package = session.scalar(
            select(DecisionPackage).where(
                DecisionPackage.meeting_id == meeting.id,
                DecisionPackage.status == "confirmed",
            )
        )
        if confirmed_package is not None:
            raise ApiProblem(
                status_code=409,
                code="meeting.confirmed_decision_locked",
                message="已确认的决策不能直接重新运行会议；请先完成行动闭环或创建新议题",
            )
        current_snapshot = session.scalar(
            select(EvidenceSnapshot).where(
                EvidenceSnapshot.enterprise_id == enterprise_id,
                EvidenceSnapshot.snapshot_key == meeting.evidence_snapshot,
            )
        )
    if refresh_evidence or current_snapshot is None:
        _freeze_evidence(database, meeting_key, enterprise_id=enterprise_id)

    with database.session() as session:
        meeting = session.scalar(select(TwinMeeting).where(TwinMeeting.meeting_key == meeting_key))
        if meeting is None:
            raise LookupError("没有找到指定数字会议")
        snapshot = session.scalar(
            select(EvidenceSnapshot).where(
                EvidenceSnapshot.snapshot_key == meeting.evidence_snapshot
            )
        )
        if snapshot is None:
            raise RuntimeError("会议证据快照冻结失败")
        snapshot_items = list(
            session.scalars(
                select(EvidenceSnapshotItem)
                .where(EvidenceSnapshotItem.snapshot_id == snapshot.id)
                .order_by(EvidenceSnapshotItem.rank)
            )
        )
        participants = list(
            session.scalars(
                select(TwinMeetingParticipant)
                .where(TwinMeetingParticipant.meeting_id == meeting.id)
                .order_by(TwinMeetingParticipant.speaking_order)
            )
        )
        profile_by_key = {
            profile.twin_key: profile
            for profile in session.scalars(
                select(RoleTwinProfile).where(
                    RoleTwinProfile.enterprise_id == enterprise_id,
                    RoleTwinProfile.twin_key.in_(
                        [participant.actor_key for participant in participants]
                    ),
                )
            )
        }
        profiles = [
            profile_by_key[participant.actor_key]
            for participant in participants
            if participant.actor_key in profile_by_key
        ]
        meeting_id = meeting.id
        topic = meeting.topic
        title = meeting.title
        owner = meeting.decision_owner
        success_metric = meeting.success_metric
    if len(profiles) < 3:
        raise RuntimeError("首期数字会议需要 CEO、运营和财务三个角色分身")

    evidence_text = _evidence_text(snapshot_items)
    allowed_refs = {f"E{item.rank}" for item in snapshot_items}
    # Register the run before invoking Runtime. Agent Runtime sessions and
    # MCP gateway sessions both reference AgentRun, so late-only persistence
    # would make the execution untraceable and prevent approval recovery.
    role_run_ids: dict[str, str] = {}
    run_created_at = datetime.now(UTC)
    with database.session() as session:
        for profile in profiles:
            run_id = f"agent_run_{uuid4().hex}"
            role_run_ids[profile.id] = run_id
            session.add(
                AgentRun(
                    id=run_id,
                    enterprise_id=actor.enterprise_id,
                    actor_principal_id=actor.principal_id,
                    twin_profile_id=profile.id,
                    meeting_id=meeting_id,
                    run_type="meeting",
                    phase="independent_analysis",
                    question=topic,
                    answer="",
                    answer_payload={},
                    status="running",
                    provider=(
                        "codex-runtime" if settings.agent_runtime_enabled and runtime else "pending"
                    ),
                    model=(settings.codex_runtime_model or settings.ai_model)
                    if settings.agent_runtime_enabled and runtime
                    else "pending",
                    fallback_reason=None,
                    duration_ms=0,
                    input_tokens=None,
                    output_tokens=None,
                    created_at=run_created_at,
                )
            )
        session.commit()
    role_results = await asyncio.gather(
        *(
            _run_role_analysis(
                settings,
                provider,
                database=database,
                actor=actor,
                runtime=runtime,
                meeting_id=meeting_id,
                participant_id=next(
                    item.id for item in participants if item.actor_key == profile.twin_key
                ),
                evidence_snapshot_id=snapshot.id,
                agent_run_id=role_run_ids[profile.id],
                profile=profile,
                title=title,
                topic=topic,
                decision_owner=owner,
                success_metric=success_metric,
                evidence_text=evidence_text,
                allowed_refs=allowed_refs,
            )
            for profile in profiles
        )
    )

    execution_modes: dict[str, ExecutionMode] = {}
    claim_payloads: list[tuple[RoleTwinProfile, RoleAnalysisPayload]] = []
    now = datetime.now(UTC)
    with database.session() as session:
        meeting = session.get(TwinMeeting, meeting_id)
        if meeting is None:
            raise LookupError("数字会议在执行期间被删除")
        for profile, (payload, completion, mode, fallback_reason, duration_ms) in zip(
            profiles, role_results, strict=True
        ):
            execution_modes[profile.twin_key] = mode
            claim_payloads.append((profile, payload))
            claim = session.scalar(
                select(MeetingClaim).where(
                    MeetingClaim.meeting_id == meeting.id,
                    MeetingClaim.twin_profile_id == profile.id,
                    MeetingClaim.phase == "independent_analysis",
                )
            )
            if claim is None:
                claim = MeetingClaim(
                    id=f"meeting_claim_{uuid4().hex}",
                    meeting_id=meeting.id,
                    twin_profile_id=profile.id,
                    phase="independent_analysis",
                    stance=payload.stance,
                    summary=payload.summary,
                    claims=[item.model_dump(mode="json") for item in payload.claims],
                    risks=payload.risks,
                    unknowns=payload.unknowns,
                    recommendation=payload.recommendation,
                    confidence=payload.confidence,
                    created_at=now,
                )
                session.add(claim)
            else:
                claim.stance = payload.stance
                claim.summary = payload.summary
                claim.claims = [item.model_dump(mode="json") for item in payload.claims]
                claim.risks = payload.risks
                claim.unknowns = payload.unknowns
                claim.recommendation = payload.recommendation
                claim.confidence = payload.confidence
                claim.created_at = now
            run_id = role_run_ids[profile.id]
            saved_run = session.get(AgentRun, run_id)
            if saved_run is None:
                raise RuntimeError("独立分析运行记录未能预登记")
            saved_run.answer = payload.summary
            saved_run.answer_payload = payload.model_dump(mode="json")
            saved_run.status = "completed" if mode == "model" else "degraded"
            saved_run.provider = (
                "codex-runtime"
                if settings.agent_runtime_enabled and runtime and mode == "model"
                else "openai-compatible-responses"
                if mode == "model"
                else "local-evidence"
            )
            saved_run.model = (
                (settings.codex_runtime_model or settings.ai_model)
                if settings.agent_runtime_enabled and runtime and mode == "model"
                else settings.ai_model
                if mode == "model"
                else "deterministic-v1"
            )
            saved_run.fallback_reason = fallback_reason
            saved_run.duration_ms = duration_ms
            saved_run.input_tokens = completion.input_tokens if completion else None
            saved_run.output_tokens = completion.output_tokens if completion else None
            for item in snapshot_items:
                chunk_id = item.payload.get("chunk_id")
                if item.item_type == "knowledge" and isinstance(chunk_id, str):
                    session.add(
                        AgentRunEvidence(
                            id=f"agent_evidence_{uuid4().hex}",
                            run_id=run_id,
                            chunk_id=chunk_id,
                            rank=item.rank,
                            score=float(str(item.payload.get("score", 1.0))),
                            excerpt=str(item.payload.get("excerpt", "")),
                            citation_label=item.label,
                        )
                    )
        meeting.protocol_status = "independent_analysis"
        meeting.updated_at = now
        session.add(
            PlatformEvent(
                id=f"event_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                event_type="decision_meeting_phase_completed",
                severity="info",
                title="数字会议完成独立分析",
                detail=f"{meeting.title} · {len(claim_payloads)} 个角色独立观点已持久化",
                occurred_at=now,
            )
        )
        session.commit()

    round_one_pairs = [
        (profile, profiles[(index + 1) % len(profiles)]) for index, profile in enumerate(profiles)
    ]
    analysis_by_profile_id = {profile.id: payload for profile, payload in claim_payloads}
    cross_one_run_ids: dict[str, str] = {}
    if settings.agent_runtime_enabled and runtime is not None:
        cross_one_run_ids = _precreate_meeting_phase_runs(
            database,
            actor=actor,
            meeting_id=meeting_id,
            topic=topic,
            profiles=[speaker for speaker, _ in round_one_pairs],
            run_type="meeting-challenge",
            phase="cross_examination_round_1",
            model=settings.codex_runtime_model or settings.ai_model,
        )
    round_one_results = await asyncio.gather(
        *(
            _run_cross_examination(
                settings,
                provider,
                database=database,
                actor=actor,
                runtime=runtime,
                agent_run_id=cross_one_run_ids.get(speaker.id),
                speaker=speaker,
                target=target,
                title=title,
                topic=topic,
                evidence_text=evidence_text,
                analyses=claim_payloads,
                prior_turn=None,
                prior_refs=_analysis_refs(analysis_by_profile_id[speaker.id]),
                allowed_refs=allowed_refs,
                turn_type="challenge",
            )
            for speaker, target in round_one_pairs
        )
    )
    round_one_turns = [
        (speaker, target, payload, completion, mode, reason, duration_ms)
        for (speaker, target), (payload, completion, mode, reason, duration_ms) in zip(
            round_one_pairs, round_one_results, strict=True
        )
    ]
    for speaker, _, _, _, mode, _, _ in round_one_turns:
        execution_modes[f"cross-1:{speaker.twin_key}"] = mode
    _persist_deliberation_phase(
        database,
        meeting_id=meeting_id,
        topic=topic,
        phase="cross_examination_round_1",
        round_number=1,
        turn_type="challenge",
        turns=round_one_turns,
        snapshot_items=snapshot_items,
        protocol_status="cross_examination",
        model_name=settings.ai_model,
        actor_principal_id=actor.principal_id,
        runtime_run_ids=cross_one_run_ids or None,
    )

    challenge_by_target_id = {
        target.id: (speaker, payload) for speaker, target, payload, *_ in round_one_turns
    }
    round_one_by_speaker_id = {speaker.id: payload for speaker, _, payload, *_ in round_one_turns}
    round_two_specs = [(speaker, *challenge_by_target_id[speaker.id]) for speaker in profiles]
    cross_two_run_ids: dict[str, str] = {}
    if settings.agent_runtime_enabled and runtime is not None:
        cross_two_run_ids = _precreate_meeting_phase_runs(
            database,
            actor=actor,
            meeting_id=meeting_id,
            topic=topic,
            profiles=[speaker for speaker, _, _ in round_two_specs],
            run_type="meeting-response",
            phase="cross_examination_round_2",
            model=settings.codex_runtime_model or settings.ai_model,
        )
    round_two_results = await asyncio.gather(
        *(
            _run_cross_examination(
                settings,
                provider,
                database=database,
                actor=actor,
                runtime=runtime,
                agent_run_id=cross_two_run_ids.get(speaker.id),
                speaker=speaker,
                target=challenger,
                title=title,
                topic=topic,
                evidence_text=evidence_text,
                analyses=claim_payloads,
                prior_turn=challenge,
                prior_refs=(
                    _analysis_refs(analysis_by_profile_id[speaker.id])
                    | _cross_refs(round_one_by_speaker_id[speaker.id])
                ),
                allowed_refs=allowed_refs,
                turn_type="response",
            )
            for speaker, challenger, challenge in round_two_specs
        )
    )
    round_two_turns = [
        (speaker, challenger, payload, completion, mode, reason, duration_ms)
        for (speaker, challenger, _), (
            payload,
            completion,
            mode,
            reason,
            duration_ms,
        ) in zip(round_two_specs, round_two_results, strict=True)
    ]
    for speaker, _, _, _, mode, _, _ in round_two_turns:
        execution_modes[f"cross-2:{speaker.twin_key}"] = mode
    _persist_deliberation_phase(
        database,
        meeting_id=meeting_id,
        topic=topic,
        phase="cross_examination_round_2",
        round_number=2,
        turn_type="response",
        turns=round_two_turns,
        snapshot_items=snapshot_items,
        protocol_status="cross_examination",
        model_name=settings.ai_model,
        actor_principal_id=actor.principal_id,
        runtime_run_ids=cross_two_run_ids or None,
    )

    deliberation_payloads = [
        (speaker, target, payload)
        for speaker, target, payload, *_ in [*round_one_turns, *round_two_turns]
        if target is not None and isinstance(payload, CrossExaminationPayload)
    ]
    risk_run_id: str | None = None
    if settings.agent_runtime_enabled and runtime is not None:
        risk_run_id = f"agent_run_{uuid4().hex}"
        with database.session() as session:
            session.add(
                AgentRun(
                    id=risk_run_id,
                    enterprise_id=actor.enterprise_id,
                    actor_principal_id=actor.principal_id,
                    twin_profile_id=profiles[-1].id,
                    meeting_id=meeting_id,
                    run_type="meeting-risk-review",
                    phase="risk_review",
                    question=topic,
                    answer="",
                    answer_payload={},
                    status="running",
                    provider="codex-runtime",
                    model=settings.codex_runtime_model or settings.ai_model,
                    fallback_reason=None,
                    duration_ms=0,
                    input_tokens=None,
                    output_tokens=None,
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
    risk_payload, risk_completion, risk_mode, risk_reason, risk_duration = await _run_risk_review(
        settings,
        provider,
        database=database,
        actor=actor,
        runtime=runtime,
        agent_run_id=risk_run_id,
        title=title,
        topic=topic,
        evidence_text=evidence_text,
        analyses=claim_payloads,
        deliberations=deliberation_payloads,
        allowed_refs=allowed_refs,
    )
    execution_modes["risk-review"] = risk_mode
    _persist_deliberation_phase(
        database,
        meeting_id=meeting_id,
        topic=topic,
        phase="risk_review",
        round_number=3,
        turn_type="risk_review",
        turns=[
            (
                profiles[-1],
                None,
                risk_payload,
                risk_completion,
                risk_mode,
                risk_reason,
                risk_duration,
            )
        ],
        snapshot_items=snapshot_items,
        protocol_status="risk_review",
        model_name=settings.ai_model,
        actor_principal_id=actor.principal_id,
        runtime_run_ids={profiles[-1].id: risk_run_id} if risk_run_id else None,
    )

    moderator_run_id: str | None = None
    if settings.agent_runtime_enabled and runtime is not None:
        moderator_run_id = f"agent_run_{uuid4().hex}"
        with database.session() as session:
            session.add(
                AgentRun(
                    id=moderator_run_id,
                    enterprise_id=actor.enterprise_id,
                    actor_principal_id=actor.principal_id,
                    twin_profile_id=profiles[0].id,
                    meeting_id=meeting_id,
                    run_type="meeting-moderator",
                    phase="decision_drafted",
                    question=topic,
                    answer="",
                    answer_payload={},
                    status="running",
                    provider="codex-runtime",
                    model=settings.codex_runtime_model or settings.ai_model,
                    fallback_reason=None,
                    duration_ms=0,
                    input_tokens=None,
                    output_tokens=None,
                    created_at=datetime.now(UTC),
                )
            )
            session.commit()
    decision, completion, mode, fallback_reason, moderator_duration = await _run_moderator(
        settings,
        provider,
        database=database,
        actor=actor,
        runtime=runtime,
        agent_run_id=moderator_run_id,
        title=title,
        topic=topic,
        decision_owner=owner,
        success_metric=success_metric,
        evidence_text=evidence_text,
        analyses=claim_payloads,
        deliberations=deliberation_payloads,
        risk_review=risk_payload,
        allowed_refs=allowed_refs,
    )
    execution_modes["moderator"] = mode
    now = datetime.now(UTC)
    with database.session() as session:
        meeting = session.get(TwinMeeting, meeting_id)
        if meeting is None:
            raise LookupError("数字会议在汇总期间被删除")
        package = session.scalar(
            select(DecisionPackage).where(DecisionPackage.meeting_id == meeting.id)
        )
        if package is None:
            package = DecisionPackage(
                id=f"decision_package_{uuid4().hex}",
                meeting_id=meeting.id,
                summary=decision.summary,
                consensus=decision.consensus,
                disagreements=decision.disagreements,
                risks=decision.risks,
                decision=decision.decision,
                actions=[item.model_dump(mode="json") for item in decision.actions],
                confidence=decision.confidence,
                status="draft",
                created_at=now,
                updated_at=now,
            )
            session.add(package)
        else:
            package.summary = decision.summary
            package.consensus = decision.consensus
            package.disagreements = decision.disagreements
            package.risks = decision.risks
            package.decision = decision.decision
            package.actions = [item.model_dump(mode="json") for item in decision.actions]
            package.confidence = decision.confidence
            package.status = "draft"
            package.updated_at = now
        if moderator_run_id is None:
            moderator_run_id = f"agent_run_{uuid4().hex}"
            session.add(
                AgentRun(
                    id=moderator_run_id,
                    enterprise_id=actor.enterprise_id,
                    actor_principal_id=actor.principal_id,
                    twin_profile_id=profiles[0].id,
                    meeting_id=meeting.id,
                    run_type="meeting-moderator",
                    phase="decision_drafted",
                    question=topic,
                    answer=decision.summary,
                    answer_payload=decision.model_dump(mode="json"),
                    status="completed" if mode == "model" else "degraded",
                    provider=(
                        "openai-compatible-responses" if mode == "model" else "local-evidence"
                    ),
                    model=settings.ai_model if mode == "model" else "deterministic-v1",
                    fallback_reason=fallback_reason,
                    duration_ms=moderator_duration,
                    input_tokens=completion.input_tokens if completion else None,
                    output_tokens=completion.output_tokens if completion else None,
                    created_at=now,
                )
            )
        else:
            saved_moderator_run = session.get(AgentRun, moderator_run_id)
            if saved_moderator_run is None:
                raise RuntimeError("主持汇总运行记录未能预登记")
            saved_moderator_run.answer = decision.summary
            saved_moderator_run.answer_payload = decision.model_dump(mode="json")
            saved_moderator_run.status = "completed" if mode == "model" else "degraded"
            saved_moderator_run.provider = "codex-runtime" if mode == "model" else "local-evidence"
            saved_moderator_run.model = (
                settings.codex_runtime_model or settings.ai_model
                if mode == "model"
                else "deterministic-v1"
            )
            saved_moderator_run.fallback_reason = fallback_reason
            saved_moderator_run.duration_ms = moderator_duration
            saved_moderator_run.input_tokens = completion.input_tokens if completion else None
            saved_moderator_run.output_tokens = completion.output_tokens if completion else None
        meeting.protocol_status = "decision_drafted"
        meeting.status = "decision_ready"
        meeting.decision = decision.decision
        meeting.updated_at = now
        participant_rows = list(
            session.scalars(
                select(TwinMeetingParticipant).where(
                    TwinMeetingParticipant.meeting_id == meeting.id
                )
            )
        )
        payload_by_key = {profile.twin_key: payload for profile, payload in claim_payloads}
        for participant in participant_rows:
            if participant.actor_key in payload_by_key:
                participant.finding = payload_by_key[participant.actor_key].summary
                participant.status = "present"
        session.add(
            PlatformEvent(
                id=f"event_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                event_type="decision_meeting_completed",
                severity="info",
                title="数字会议形成数据库决策包",
                detail=(
                    f"{meeting.title} · {len(claim_payloads)} 个独立观点 · "
                    f"{len(deliberation_payloads)} 条两轮审议 · 1 次反方风险审查"
                ),
                occurred_at=now,
            )
        )
        session.commit()

    return MeetingRunResponse(
        detail=get_meeting_detail(database, meeting_key, actor.enterprise_id),
        execution_modes=execution_modes,
        duration_ms=max(1, round((perf_counter() - started) * 1000)),
    )


def _precreate_meeting_phase_runs(
    database: Database,
    *,
    actor: ActorContext,
    meeting_id: str,
    topic: str,
    profiles: list[RoleTwinProfile],
    run_type: str,
    phase: str,
    model: str,
) -> dict[str, str]:
    run_ids = {profile.id: f"agent_run_{uuid4().hex}" for profile in profiles}
    now = datetime.now(UTC)
    with database.session() as session:
        for profile in profiles:
            session.add(
                AgentRun(
                    id=run_ids[profile.id],
                    enterprise_id=actor.enterprise_id,
                    actor_principal_id=actor.principal_id,
                    twin_profile_id=profile.id,
                    meeting_id=meeting_id,
                    run_type=run_type,
                    phase=phase,
                    question=topic,
                    answer="",
                    answer_payload={},
                    status="running",
                    provider="codex-runtime",
                    model=model,
                    fallback_reason=None,
                    duration_ms=0,
                    input_tokens=None,
                    output_tokens=None,
                    created_at=now,
                )
            )
        session.commit()
    return run_ids


def _persist_deliberation_phase(
    database: Database,
    *,
    meeting_id: str,
    topic: str,
    phase: str,
    round_number: int,
    turn_type: Literal["challenge", "response", "risk_review"],
    turns: Sequence[
        tuple[
            RoleTwinProfile,
            RoleTwinProfile | None,
            CrossExaminationPayload | RiskReviewPayload,
            AICompletion | None,
            ExecutionMode,
            str | None,
            int,
        ]
    ],
    snapshot_items: list[EvidenceSnapshotItem],
    protocol_status: str,
    model_name: str,
    actor_principal_id: str,
    runtime_run_ids: dict[str, str] | None = None,
) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        meeting = session.get(TwinMeeting, meeting_id)
        if meeting is None:
            raise LookupError("数字会议在质询期间被删除")
        for speaker, target, payload, completion, mode, fallback_reason, duration_ms in turns:
            if isinstance(payload, CrossExaminationPayload):
                evidence_refs = sorted(
                    {ref for item in payload.challenges for ref in item.evidence_refs}
                )
                new_evidence_refs = sorted(
                    {ref for item in payload.challenges for ref in item.new_evidence_refs}
                )
                position_after: str | None = payload.position_after
                position_changed = payload.position_changed
            else:
                evidence_refs = sorted(
                    {ref for item in payload.failure_modes for ref in item.evidence_refs}
                )
                new_evidence_refs = evidence_refs
                position_after = None
                position_changed = False
            turn = session.scalar(
                select(MeetingDeliberationTurn).where(
                    MeetingDeliberationTurn.meeting_id == meeting.id,
                    MeetingDeliberationTurn.speaker_twin_profile_id == speaker.id,
                    MeetingDeliberationTurn.phase == phase,
                )
            )
            if turn is None:
                turn = MeetingDeliberationTurn(
                    id=f"meeting_turn_{uuid4().hex}",
                    meeting_id=meeting.id,
                    speaker_twin_profile_id=speaker.id,
                    target_twin_profile_id=target.id if target else None,
                    phase=phase,
                    round_number=round_number,
                    turn_type=turn_type,
                    summary=payload.summary,
                    payload=payload.model_dump(mode="json"),
                    evidence_refs=evidence_refs,
                    new_evidence_refs=new_evidence_refs,
                    position_after=position_after,
                    position_changed=position_changed,
                    confidence=payload.confidence,
                    created_at=now,
                )
                session.add(turn)
            else:
                turn.target_twin_profile_id = target.id if target else None
                turn.round_number = round_number
                turn.turn_type = turn_type
                turn.summary = payload.summary
                turn.payload = payload.model_dump(mode="json")
                turn.evidence_refs = evidence_refs
                turn.new_evidence_refs = new_evidence_refs
                turn.position_after = position_after
                turn.position_changed = position_changed
                turn.confidence = payload.confidence
                turn.created_at = now
            run_id = (runtime_run_ids or {}).get(speaker.id)
            if run_id is None:
                run_id = f"agent_run_{uuid4().hex}"
                session.add(
                    AgentRun(
                        id=run_id,
                        enterprise_id=meeting.enterprise_id,
                        actor_principal_id=actor_principal_id,
                        twin_profile_id=speaker.id,
                        meeting_id=meeting.id,
                        run_type=f"meeting-{turn_type}",
                        phase=phase,
                        question=topic,
                        answer=payload.summary,
                        answer_payload=payload.model_dump(mode="json"),
                        status="completed" if mode == "model" else "degraded",
                        provider=(
                            "openai-compatible-responses" if mode == "model" else "local-evidence"
                        ),
                        model=model_name if mode == "model" else "deterministic-v1",
                        fallback_reason=fallback_reason,
                        duration_ms=duration_ms,
                        input_tokens=completion.input_tokens if completion else None,
                        output_tokens=completion.output_tokens if completion else None,
                        created_at=now,
                    )
                )
            else:
                saved_run = session.get(AgentRun, run_id)
                if saved_run is None:
                    raise RuntimeError("风险审查运行记录未能预登记")
                saved_run.answer = payload.summary
                saved_run.answer_payload = payload.model_dump(mode="json")
                saved_run.status = "completed" if mode == "model" else "degraded"
                saved_run.provider = "codex-runtime" if mode == "model" else "local-evidence"
                if mode != "model":
                    saved_run.model = "deterministic-v1"
                saved_run.fallback_reason = fallback_reason
                saved_run.duration_ms = duration_ms
                saved_run.input_tokens = completion.input_tokens if completion else None
                saved_run.output_tokens = completion.output_tokens if completion else None
            for item in snapshot_items:
                chunk_id = item.payload.get("chunk_id")
                if item.item_type == "knowledge" and isinstance(chunk_id, str):
                    session.add(
                        AgentRunEvidence(
                            id=f"agent_evidence_{uuid4().hex}",
                            run_id=run_id,
                            chunk_id=chunk_id,
                            rank=item.rank,
                            score=float(str(item.payload.get("score", 1.0))),
                            excerpt=str(item.payload.get("excerpt", "")),
                            citation_label=item.label,
                        )
                    )
        meeting.protocol_status = protocol_status
        meeting.updated_at = now
        session.add(
            PlatformEvent(
                id=f"event_{uuid4().hex}",
                enterprise_id=meeting.enterprise_id,
                event_type="decision_meeting_phase_completed",
                severity="info",
                title=f"数字会议完成{phase}",
                detail=f"{meeting.title} · {len(turns)} 条阶段记录已持久化",
                occurred_at=now,
            )
        )
        session.commit()


def _meeting_list_item(session: Session, meeting: TwinMeeting) -> MeetingListItem:
    participant_count = int(
        session.scalar(
            select(func.count(TwinMeetingParticipant.id)).where(
                TwinMeetingParticipant.meeting_id == meeting.id
            )
        )
        or 0
    )
    claim_count = int(
        session.scalar(
            select(func.count(MeetingClaim.id)).where(MeetingClaim.meeting_id == meeting.id)
        )
        or 0
    )
    deliberation_count = int(
        session.scalar(
            select(func.count(MeetingDeliberationTurn.id)).where(
                MeetingDeliberationTurn.meeting_id == meeting.id
            )
        )
        or 0
    )
    has_decision = (
        session.scalar(
            select(func.count(DecisionPackage.id)).where(DecisionPackage.meeting_id == meeting.id)
        )
        or 0
    ) > 0
    actor_snapshot = meeting.actor_snapshot or {}
    snapshot_display_name = actor_snapshot.get("display_name")
    initiated_by_name = snapshot_display_name if isinstance(snapshot_display_name, str) else None
    if initiated_by_name is None and meeting.initiated_by_principal_id:
        principal = session.get(Principal, meeting.initiated_by_principal_id)
        initiated_by_name = principal.display_name if principal else None
    if initiated_by_name is None:
        initiated_by_name = meeting.decision_owner
    scope_label = _meeting_scope_label(meeting.scope_type, meeting.scope_key)
    workspace_key = actor_snapshot.get("workspace_key")
    return MeetingListItem(
        key=meeting.meeting_key,
        title=meeting.title,
        topic=meeting.topic,
        status=meeting.status,
        protocol_status=meeting.protocol_status,
        template_key=meeting.template_key,
        initiated_by_name=initiated_by_name,
        scope_type=cast(Literal["enterprise", "store"], meeting.scope_type),
        scope_key=meeting.scope_key,
        scope_label=scope_label,
        decision_owner=meeting.decision_owner,
        deadline_at=meeting.deadline_at,
        success_metric=meeting.success_metric,
        evidence_snapshot=meeting.evidence_snapshot,
        participant_count=participant_count,
        claim_count=claim_count,
        deliberation_count=deliberation_count,
        has_decision_package=has_decision,
        workspace_key=workspace_key if isinstance(workspace_key, str) else None,
        updated_at=meeting.updated_at,
        created_at=meeting.created_at,
    )


def _meeting_scope_catalog(
    session: Session,
    actor: ActorContext,
    meetings: Sequence[TwinMeeting],
) -> list[MeetingScopeView]:
    metric_scope_keys = set(
        session.scalars(
            select(MetricSnapshot.scope_key)
            .where(MetricSnapshot.enterprise_id == actor.enterprise_id)
            .distinct()
        )
    )
    candidate_keys = metric_scope_keys | {meeting.scope_key for meeting in meetings}
    for scope in actor.scopes:
        if scope.effect == "allow" and scope.scope_type in {"enterprise", "store"}:
            candidate_keys.update(scope.scope_ids)
    if actor_scope_allows(
        actor,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    ):
        candidate_keys.add("enterprise")

    result: list[MeetingScopeView] = []
    for scope_key in sorted(candidate_keys, key=lambda item: (item != "enterprise", item)):
        scope_type: Literal["enterprise", "store"] = (
            "enterprise" if scope_key in {"enterprise", actor.enterprise_id} else "store"
        )
        scope_id = actor.enterprise_id if scope_type == "enterprise" else scope_key
        if not actor_scope_allows(actor, scope_type=scope_type, scope_id=scope_id):
            continue
        normalized_key = "enterprise" if scope_type == "enterprise" else scope_key
        if any(item.key == normalized_key for item in result):
            continue
        result.append(
            MeetingScopeView(
                type=scope_type,
                key=normalized_key,
                label=_meeting_scope_label(scope_type, normalized_key),
                has_metric_data=normalized_key in metric_scope_keys,
            )
        )
    return result


def _meeting_scope_label(scope_type: str, scope_key: str) -> str:
    if scope_type == "enterprise":
        return "全企业"
    return {
        "store-flagship": "旗舰店",
        "store-outlet": "奥莱店",
    }.get(scope_key, scope_key)


def _snapshot_view(session: Session, snapshot: EvidenceSnapshot) -> EvidenceSnapshotView:
    items = list(
        session.scalars(
            select(EvidenceSnapshotItem)
            .where(EvidenceSnapshotItem.snapshot_id == snapshot.id)
            .order_by(EvidenceSnapshotItem.rank)
        )
    )
    return EvidenceSnapshotView(
        key=snapshot.snapshot_key,
        purpose=snapshot.purpose,
        query=snapshot.query,
        content_hash=snapshot.content_hash,
        item_count=snapshot.item_count,
        frozen_at=snapshot.frozen_at,
        items=[
            EvidenceSnapshotItemView(
                type=item.item_type,
                key=item.item_key,
                version_ref=item.version_ref,
                label=item.label,
                payload=item.payload,
                rank=item.rank,
            )
            for item in items
        ],
    )


def _claim_view(claim: MeetingClaim, profile: RoleTwinProfile) -> MeetingClaimView:
    payload = RoleAnalysisPayload.model_validate(
        {
            "stance": claim.stance,
            "summary": claim.summary,
            "claims": claim.claims,
            "risks": claim.risks,
            "unknowns": claim.unknowns,
            "recommendation": claim.recommendation,
            "confidence": claim.confidence,
        }
    )
    return MeetingClaimView(
        id=claim.id,
        twin_key=profile.twin_key,
        twin_name=profile.display_name,
        role_title=profile.role_title,
        phase=claim.phase,
        created_at=claim.created_at,
        **payload.model_dump(),
    )


def _deliberation_turn_view(
    turn: MeetingDeliberationTurn,
    speaker: RoleTwinProfile,
    target: RoleTwinProfile | None,
) -> MeetingDeliberationTurnView:
    payload: CrossExaminationPayload | RiskReviewPayload
    if turn.turn_type == "risk_review":
        payload = RiskReviewPayload.model_validate(turn.payload)
    else:
        payload = CrossExaminationPayload.model_validate(turn.payload)
    return MeetingDeliberationTurnView(
        id=turn.id,
        speaker_twin_key=speaker.twin_key,
        speaker_name=speaker.display_name,
        speaker_role_title=speaker.role_title,
        target_twin_key=target.twin_key if target else None,
        target_name=target.display_name if target else None,
        phase=turn.phase,
        round_number=turn.round_number,
        turn_type=cast(Literal["challenge", "response", "risk_review"], turn.turn_type),
        summary=turn.summary,
        payload=payload,
        evidence_refs=turn.evidence_refs,
        new_evidence_refs=turn.new_evidence_refs,
        position_after=cast(
            Literal["support", "oppose", "conditional"] | None, turn.position_after
        ),
        position_changed=turn.position_changed,
        confidence=cast(Literal["high", "medium", "low"], turn.confidence),
        created_at=turn.created_at,
    )


def _decision_view(package: DecisionPackage) -> DecisionPackageView:
    payload = DecisionPackagePayload.model_validate(
        {
            "summary": package.summary,
            "consensus": package.consensus,
            "disagreements": package.disagreements,
            "risks": package.risks,
            "decision": package.decision,
            "actions": package.actions,
            "confidence": package.confidence,
        }
    )
    return DecisionPackageView(
        id=package.id,
        status=package.status,
        created_at=package.created_at,
        updated_at=package.updated_at,
        **payload.model_dump(),
    )


def _freeze_evidence(
    database: Database, meeting_key: str, *, enterprise_id: str | None = None
) -> EvidenceSnapshotView:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    with database.session() as session:
        meeting = session.scalar(
            select(TwinMeeting).where(
                TwinMeeting.enterprise_id == enterprise_id,
                TwinMeeting.meeting_key == meeting_key,
            )
        )
        if meeting is None:
            raise LookupError("没有找到指定数字会议")
        query = f"{meeting.topic} {meeting.success_metric} 广告 ROI 库存 预算 制度"
        enterprise_id = meeting.enterprise_id
        scope_key = meeting.scope_key
        participant_keys = list(
            session.scalars(
                select(TwinMeetingParticipant.actor_key).where(
                    TwinMeetingParticipant.meeting_id == meeting.id
                )
            )
        )
    knowledge = search_evidence(database, query, limit=6, enterprise_id=enterprise_id)
    now = datetime.now(UTC)
    frozen_items: list[dict[str, object]] = []
    for evidence in knowledge.items:
        frozen_items.append(
            {
                "type": "knowledge",
                "key": evidence.document_key,
                "version_ref": evidence.version_label,
                "label": (
                    f"{evidence.document_title} {evidence.version_label} · {evidence.locator}"
                ),
                "payload": {
                    "chunk_id": evidence.chunk_id,
                    "excerpt": evidence.excerpt,
                    "score": evidence.score,
                    "effective_from": (
                        evidence.effective_from.isoformat() if evidence.effective_from else None
                    ),
                    "version_status": evidence.version_status,
                },
            }
        )
    with database.session() as session:
        definitions = {
            item.metric_key: item
            for item in session.scalars(
                select(MetricDefinition).where(
                    MetricDefinition.enterprise_id == enterprise_id,
                    MetricDefinition.status == "active",
                )
            )
        }
        snapshots = list(
            session.scalars(
                select(MetricSnapshot)
                .where(
                    MetricSnapshot.enterprise_id == enterprise_id,
                    MetricSnapshot.scope_key == scope_key,
                )
                .order_by(MetricSnapshot.as_of.desc())
            )
        )
        latest_metrics: dict[str, MetricSnapshot] = {}
        for snapshot in snapshots:
            latest_metrics.setdefault(snapshot.metric_key, snapshot)
        for metric in latest_metrics.values():
            definition = definitions.get(metric.metric_key)
            frozen_items.append(
                {
                    "type": "metric",
                    "key": metric.metric_key,
                    "version_ref": definition.version if definition else None,
                    "label": f"{metric.label} · {metric.value:g}{metric.unit}",
                    "payload": {
                        "value": metric.value,
                        "unit": metric.unit,
                        "change_rate": metric.change_rate,
                        "as_of": metric.as_of.isoformat(),
                        "definition": definition.description if definition else "",
                        "formula": definition.formula_expression if definition else "",
                        "scope_key": metric.scope_key,
                    },
                }
            )
        memory_rows = session.execute(
            select(ApprovedMemory, RoleTwinProfile, MemoryCandidate)
            .join(RoleTwinProfile, RoleTwinProfile.id == ApprovedMemory.twin_profile_id)
            .join(MemoryCandidate, MemoryCandidate.id == ApprovedMemory.candidate_id)
            .where(
                ApprovedMemory.enterprise_id == enterprise_id,
                ApprovedMemory.status == "active",
                RoleTwinProfile.twin_key.in_(participant_keys),
            )
            .order_by(RoleTwinProfile.twin_key, ApprovedMemory.memory_key)
        ).all()
        for memory, profile, candidate in memory_rows:
            frozen_items.append(
                {
                    "type": "memory",
                    "key": memory.memory_key,
                    "version_ref": f"v{memory.version_number}:{memory.normalized_hash[:12]}",
                    "label": f"{profile.display_name} · {memory.category}",
                    "payload": {
                        "content": memory.content,
                        "source_ref": memory.source_ref,
                        "confidence": candidate.confidence,
                        "approved_at": memory.approved_at.isoformat(),
                        "effective_from": (
                            memory.effective_from.isoformat() if memory.effective_from else None
                        ),
                    },
                }
            )
        serialized = json.dumps(frozen_items, ensure_ascii=False, sort_keys=True)
        content_hash = sha256(serialized.encode("utf-8")).hexdigest()
        snapshot_key = f"evs-{meeting_key}-{uuid4().hex[:8]}"
        evidence_snapshot = EvidenceSnapshot(
            id=f"evidence_snapshot_{uuid4().hex}",
            enterprise_id=enterprise_id,
            snapshot_key=snapshot_key,
            purpose="decision-meeting",
            query=query,
            content_hash=content_hash,
            item_count=len(frozen_items),
            frozen_at=now,
        )
        session.add(evidence_snapshot)
        for rank, item in enumerate(frozen_items, start=1):
            session.add(
                EvidenceSnapshotItem(
                    id=f"evidence_item_{uuid4().hex}",
                    snapshot_id=evidence_snapshot.id,
                    item_type=str(item["type"]),
                    item_key=str(item["key"]),
                    version_ref=(str(item["version_ref"]) if item.get("version_ref") else None),
                    label=str(item["label"]),
                    payload=cast(dict[str, object], item["payload"]),
                    rank=rank,
                )
            )
        meeting = session.scalar(
            select(TwinMeeting).where(
                TwinMeeting.enterprise_id == enterprise_id,
                TwinMeeting.meeting_key == meeting_key,
            )
        )
        if meeting is None:
            raise LookupError("没有找到指定数字会议")
        meeting.evidence_snapshot = snapshot_key
        meeting.protocol_status = "evidence_frozen"
        meeting.updated_at = now
        session.commit()
        return _snapshot_view(session, evidence_snapshot)


async def _run_role_analysis(
    settings: Settings,
    provider: ResponsesAIProvider,
    *,
    database: Database,
    actor: ActorContext,
    runtime: AgentRuntime | None,
    meeting_id: str,
    participant_id: str,
    evidence_snapshot_id: str,
    agent_run_id: str,
    profile: RoleTwinProfile,
    title: str,
    topic: str,
    decision_owner: str,
    success_metric: str,
    evidence_text: str,
    allowed_refs: set[str],
) -> tuple[RoleAnalysisPayload, AICompletion | None, ExecutionMode, str | None, int]:
    started = perf_counter()
    instructions = f"""你是{profile.display_name}，岗位是{profile.role_title}。
表达要求：{profile.voice_guide}
分析要求：{profile.reasoning_guide}
边界规则：{profile.answer_policy}
只能使用冻结证据，主张必须引用 E 编号。区分事实、假设、风险和未知项。
不要输出隐藏思维过程，不要编造数值、日期、制度或权限。"""
    input_text = f"""会议：{title}
议题：{topic}
决策负责人：{decision_owner}
成功指标：{success_metric}

冻结证据：
{evidence_text}"""
    try:
        if settings.agent_runtime_enabled and runtime is not None:
            completion = await _run_role_analysis_runtime(
                database,
                settings,
                runtime,
                actor=actor,
                meeting_id=meeting_id,
                participant_id=participant_id,
                evidence_snapshot_id=evidence_snapshot_id,
                agent_run_id=agent_run_id,
                profile=profile,
                instructions=instructions,
                input_text=input_text,
            )
        else:
            completion = await provider.generate(
                settings,
                instructions=instructions,
                input_text=input_text,
                run_id=agent_run_id,
                schema_name="meeting_role_analysis",
                response_schema=ROLE_ANALYSIS_JSON_SCHEMA,
            )
        payload = RoleAnalysisPayload.model_validate(completion.payload)
        invalid_refs = {
            ref
            for claim in payload.claims
            for ref in claim.evidence_refs
            if ref not in allowed_refs
        }
        if invalid_refs:
            raise ValueError("角色分析引用了不存在的证据：" + "、".join(sorted(invalid_refs)))
        unsupported_numbers = _unsupported_numeric_output(payload.model_dump_json(), input_text)
        if unsupported_numbers:
            raise ValueError(
                "角色分析包含冻结证据中不存在的数值或日期："
                + "、".join(sorted(unsupported_numbers))
            )
        mode: ExecutionMode = "model"
        fallback_reason = None
    except (AIProviderError, ApiProblem, ValueError) as exc:
        completion = None
        payload = _fallback_role_analysis(profile, allowed_refs)
        mode = "evidence-fallback"
        fallback_reason = str(exc)
    duration_ms = max(1, round((perf_counter() - started) * 1000))
    return payload, completion, mode, fallback_reason, duration_ms


async def _run_role_analysis_runtime(
    database: Database,
    settings: Settings,
    runtime: AgentRuntime,
    *,
    actor: ActorContext,
    meeting_id: str,
    participant_id: str,
    evidence_snapshot_id: str,
    agent_run_id: str,
    profile: RoleTwinProfile,
    instructions: str,
    input_text: str,
) -> AICompletion:
    """Run one independent meeting opinion through the governed Runtime path."""
    available_tool_keys = {
        item.key for item in list_tool_catalog(database, actor).items if item.risk_level == "R0"
    }
    skill = select_runtime_skill(
        database,
        actor,
        skill_key="policy-grounded-answer",
        required_tool_keys=available_tool_keys,
    )
    gateway = create_mcp_session(
        database,
        actor,
        McpSessionCreateRequest(
            client_id=settings.codex_runtime_mcp_client_id,
            allowed_tool_keys=list(skill.tool_keys),
            scope_constraints=[],
            ttl_seconds=settings.codex_runtime_mcp_ttl_seconds,
            agent_run_id=agent_run_id,
            workspace_key=None,
        ),
    )
    credentials = RuntimeCredentials(
        mcp_session_token=gateway.session_token,
        mcp_client_id=gateway.session.client_id,
    )
    spec = AgentRunSpec(
        run_id=agent_run_id,
        actor=AgentActor(
            enterprise_id=actor.enterprise_id,
            principal_id=actor.principal_id,
            actor_key=actor.actor_key,
            permission_set_version=actor.permission_set_version,
            authentication_method=actor.authentication_method,
        ),
        input_text=input_text,
        instructions=(
            f"{skill.instructions}\n\n会议角色边界：{instructions}\n"
            "最终只输出符合指定 JSON Schema 的角色分析对象。"
        ),
        cwd=settings.codex_runtime_cwd,
        model=settings.codex_runtime_model or settings.ai_model,
        allowed_tool_keys=tuple(skill.tool_keys),
        output_schema=RoleAnalysisPayload.model_json_schema(),
        scope_context=build_scope_context(database, actor).snapshot(),
        metadata={
            "meeting_id": meeting_id,
            "participant_id": participant_id,
            "evidence_snapshot_id": evidence_snapshot_id,
            "skill_key": skill.skill_key,
            "skill_version": str(skill.version_number),
        },
    )
    runtime_session_id: str | None = None
    runtime_turn_id: str | None = None
    mapping_id: str | None = None
    try:
        handle = await runtime.start(spec, credentials)
        runtime_session, runtime_turn = create_runtime_session(
            database,
            actor,
            agent_run_id=agent_run_id,
            handle=handle,
            spec=spec,
            mcp_gateway_session_id=gateway.session.session_id,
            model=settings.codex_runtime_model or settings.ai_model,
        )
        runtime_session_id = runtime_session.id
        runtime_turn_id = runtime_turn.id
        mapping = create_meeting_runtime_run(
            database,
            enterprise_id=actor.enterprise_id,
            meeting_id=meeting_id,
            participant_id=participant_id,
            agent_run_id=agent_run_id,
            runtime_session_id=runtime_session_id,
            evidence_snapshot_id=evidence_snapshot_id,
            skill_key=skill.skill_key,
            skill_version=skill.version_number,
            tool_keys=list(skill.tool_keys),
            status="running",
        )
        mapping_id = mapping.id
        final_message: str | None = None
        terminal_event: AgentRunEvent | None = None
        async for event in runtime.stream(agent_run_id):
            append_runtime_event(
                database,
                runtime_session_id=runtime_session_id,
                runtime_turn_id=runtime_turn_id,
                event=event,
            )
            if event.event_type == "message.completed" and event.message:
                final_message = event.message
            if event.event_type in {"run.completed", "run.failed", "run.cancelled"}:
                terminal_event = event
        if terminal_event is None or terminal_event.event_type != "run.completed":
            raise ValueError(
                terminal_event.message if terminal_event else "Agent Runtime 未返回最终状态"
            )
        if not final_message:
            raise ValueError("Agent Runtime 未返回角色分析")
        payload = json.loads(_strip_json_fence(final_message))
        if not isinstance(payload, dict):
            raise ValueError("Agent Runtime 角色分析结构无效")
        result = RoleAnalysisPayload.model_validate(payload)
        update_meeting_runtime_run(
            database,
            run_id=mapping_id,
            status="completed",
            runtime_session_id=runtime_session_id,
        )
        return AICompletion(
            payload=result.model_dump(mode="json"),
            input_tokens=None,
            output_tokens=None,
        )
    except Exception as exc:
        if runtime_session_id and runtime_turn_id:
            mark_runtime_session_failed(
                database,
                runtime_session_id=runtime_session_id,
                runtime_turn_id=runtime_turn_id,
                error_code="meeting_role_runtime_failed",
                error_message=str(exc) or exc.__class__.__name__,
            )
        if mapping_id:
            update_meeting_runtime_run(
                database,
                run_id=mapping_id,
                status="failed",
                runtime_session_id=runtime_session_id,
                failure_code="meeting_role_runtime_failed",
                failure_message=str(exc),
            )
        raise
    finally:
        try:
            await runtime.release(agent_run_id)
        except Exception:
            pass
        try:
            revoke_mcp_session(
                database,
                actor,
                gateway.session.session_id,
                McpSessionRevokeRequest(reason="meeting_runtime_turn_finished"),
            )
        except Exception:
            pass


def _strip_json_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


async def _run_cross_examination(
    settings: Settings,
    provider: ResponsesAIProvider,
    *,
    database: Database,
    actor: ActorContext,
    runtime: AgentRuntime | None,
    agent_run_id: str | None,
    speaker: RoleTwinProfile,
    target: RoleTwinProfile,
    title: str,
    topic: str,
    evidence_text: str,
    analyses: list[tuple[RoleTwinProfile, RoleAnalysisPayload]],
    prior_turn: CrossExaminationPayload | None,
    prior_refs: set[str],
    allowed_refs: set[str],
    turn_type: Literal["challenge", "response"],
) -> tuple[
    CrossExaminationPayload,
    AICompletion | None,
    ExecutionMode,
    str | None,
    int,
]:
    started = perf_counter()
    analyses_text = "\n\n".join(
        f"[{profile.display_name}/{profile.role_title}]\n{payload.model_dump_json()}"
        for profile, payload in analyses
    )
    prior_text = prior_turn.model_dump_json() if prior_turn else "无"
    available_new_refs = sorted(allowed_refs - prior_refs)
    phase_instruction = (
        f"你正在进行第一轮交叉质询，必须针对{target.display_name}的具体主张、假设或未知项提出挑战。"
        if turn_type == "challenge"
        else (
            f"你正在进行第二轮答辩，必须回应{target.display_name}对你的上一轮质询，"
            "并明确立场是否变化。"
        )
    )
    instructions = f"""你是{speaker.display_name}，岗位是{speaker.role_title}。
{phase_instruction}
表达要求：{speaker.voice_guide}
只能使用冻结证据。每个质询点必须引用 E 编号。
evidence_refs 必须包含本条发言使用的全部证据；new_evidence_refs 是其中相对你前序发言新增的子集。
本轮至少选择一个可用新证据：{", ".join(available_new_refs) or "无；此时缩小主张并保留未解决问题"}。
禁止重复自己的独立结论，禁止编造数字、日期、制度或权限；没有新增证据时应缩小主张并留下未解决问题。
不要输出隐藏思维过程。"""
    input_text = f"""会议：{title}
议题：{topic}
发言者：{speaker.display_name}
本轮目标角色：{target.display_name}
本轮类型：{turn_type}
发言者前序已使用证据：{", ".join(sorted(prior_refs)) or "无"}

冻结证据：
{evidence_text}

全部独立分析：
{analyses_text}

需要回应的上一轮质询：
{prior_text}"""
    try:
        if settings.agent_runtime_enabled and runtime is not None and agent_run_id:
            first_completion = await _run_meeting_runtime_json(
                database,
                settings,
                runtime,
                actor=actor,
                agent_run_id=agent_run_id,
                instructions=instructions,
                input_text=input_text,
                output_schema=CrossExaminationPayload.model_json_schema(),
            )
        else:
            first_completion = await provider.generate(
                settings,
                instructions=instructions,
                input_text=input_text,
                run_id=f"meeting_cross_{turn_type}_{uuid4().hex}",
                schema_name="meeting_cross_examination",
                response_schema=CROSS_EXAMINATION_JSON_SCHEMA,
            )
        try:
            payload = _validated_cross_examination(
                first_completion,
                allowed_refs=allowed_refs,
                prior_refs=prior_refs,
                source_text=input_text,
            )
            completion = first_completion
        except ValueError as validation_error:
            correction_refs = ", ".join(available_new_refs[:12]) or "没有剩余新证据"
            retry_completion = await provider.generate(
                settings,
                instructions=(
                    f"{instructions}\n"
                    "上次输出没有通过业务校验。这是唯一一次结构纠正重试："
                    f"{validation_error}。"
                    f"可作为新增证据的编号为：{correction_refs}。"
                    "只修正证据编号、数值表达和 JSON 结构，不扩大主张。"
                ),
                input_text=input_text,
                run_id=f"meeting_cross_{turn_type}_retry_{uuid4().hex}",
                schema_name="meeting_cross_examination",
                response_schema=CROSS_EXAMINATION_JSON_SCHEMA,
            )
            payload = _validated_cross_examination(
                retry_completion,
                allowed_refs=allowed_refs,
                prior_refs=prior_refs,
                source_text=input_text,
            )
            completion = _merge_completion_usage(first_completion, retry_completion)
        mode: ExecutionMode = "model"
        fallback_reason = None
    except (AIProviderError, ApiProblem, ValueError) as exc:
        completion = None
        speaker_analysis = next(
            payload for profile, payload in analyses if profile.id == speaker.id
        )
        target_analysis = next(payload for profile, payload in analyses if profile.id == target.id)
        payload = _fallback_cross_examination(
            speaker,
            target,
            speaker_analysis=speaker_analysis,
            target_analysis=target_analysis,
            prior_turn=prior_turn,
            prior_refs=prior_refs,
            allowed_refs=allowed_refs,
            turn_type=turn_type,
        )
        mode = "evidence-fallback"
        fallback_reason = str(exc)
    duration_ms = max(1, round((perf_counter() - started) * 1000))
    return payload, completion, mode, fallback_reason, duration_ms


def _validated_cross_examination(
    completion: AICompletion,
    *,
    allowed_refs: set[str],
    prior_refs: set[str],
    source_text: str,
) -> CrossExaminationPayload:
    payload = CrossExaminationPayload.model_validate(completion.payload)
    payload = payload.model_copy(
        update={
            "challenges": [
                challenge.model_copy(
                    update={
                        "evidence_refs": list(
                            dict.fromkeys(challenge.evidence_refs + challenge.new_evidence_refs)
                        )
                    }
                )
                for challenge in payload.challenges
            ]
        }
    )
    all_refs = {ref for challenge in payload.challenges for ref in challenge.evidence_refs}
    new_refs = {ref for challenge in payload.challenges for ref in challenge.new_evidence_refs}
    invalid_refs = (all_refs | new_refs) - allowed_refs
    if invalid_refs:
        raise ValueError("交叉质询引用了不存在的证据：" + "、".join(sorted(invalid_refs)))
    if allowed_refs - prior_refs and not (new_refs - prior_refs):
        raise ValueError("交叉质询没有引入发言者前序未使用的冻结证据")
    unsupported_numbers = _unsupported_numeric_output(payload.model_dump_json(), source_text)
    if unsupported_numbers:
        raise ValueError(
            "交叉质询包含冻结证据中不存在的数值或日期：" + "、".join(sorted(unsupported_numbers))
        )
    return payload


def _merge_completion_usage(first: AICompletion, second: AICompletion) -> AICompletion:
    def total(left: int | None, right: int | None) -> int | None:
        return left + right if left is not None and right is not None else right or left

    return AICompletion(
        payload=second.payload,
        input_tokens=total(first.input_tokens, second.input_tokens),
        output_tokens=total(first.output_tokens, second.output_tokens),
        structured_output=first.structured_output and second.structured_output,
    )


async def _run_risk_review(
    settings: Settings,
    provider: ResponsesAIProvider,
    *,
    database: Database,
    actor: ActorContext,
    runtime: AgentRuntime | None,
    agent_run_id: str | None,
    title: str,
    topic: str,
    evidence_text: str,
    analyses: list[tuple[RoleTwinProfile, RoleAnalysisPayload]],
    deliberations: list[tuple[RoleTwinProfile, RoleTwinProfile, CrossExaminationPayload]],
    allowed_refs: set[str],
) -> tuple[RiskReviewPayload, AICompletion | None, ExecutionMode, str | None, int]:
    started = perf_counter()
    analysis_text = "\n\n".join(
        f"[{profile.display_name}/{profile.role_title}]\n{payload.model_dump_json()}"
        for profile, payload in analyses
    )
    deliberation_text = "\n\n".join(
        f"[{speaker.display_name} -> {target.display_name}]\n{payload.model_dump_json()}"
        for speaker, target, payload in deliberations
    )
    input_text = f"""会议：{title}
议题：{topic}

冻结证据：
{evidence_text}

独立分析：
{analysis_text}

两轮交叉质询：
{deliberation_text}"""
    instructions = """你是数字会议的反方风险审查智能体。
从失败机制、错误激励、反事实、退出条件和证据缺口五个角度审查当前方案。
每个 failure_mode 必须引用冻结证据 E 编号；不得把推测写成事实，不得编造数值、日期、制度或权限。
    保留无法通过当前证据解决的问题，不要替人类做最终确认，也不要输出隐藏思维过程。"""
    try:
        if settings.agent_runtime_enabled and runtime is not None and agent_run_id:
            completion = await _run_meeting_runtime_json(
                database,
                settings,
                runtime,
                actor=actor,
                agent_run_id=agent_run_id,
                instructions=instructions,
                input_text=input_text,
                output_schema=RiskReviewPayload.model_json_schema(),
            )
        else:
            completion = await provider.generate(
                settings,
                instructions=instructions,
                input_text=input_text,
                run_id=f"meeting_risk_{uuid4().hex}",
                schema_name="meeting_risk_review",
                response_schema=RISK_REVIEW_JSON_SCHEMA,
            )
        payload = RiskReviewPayload.model_validate(completion.payload)
        refs = {ref for item in payload.failure_modes for ref in item.evidence_refs}
        invalid_refs = refs - allowed_refs
        if invalid_refs:
            raise ValueError("风险审查引用了不存在的证据：" + "、".join(sorted(invalid_refs)))
        unsupported_numbers = _unsupported_numeric_output(payload.model_dump_json(), input_text)
        if unsupported_numbers:
            raise ValueError(
                "风险审查包含冻结证据中不存在的数值或日期："
                + "、".join(sorted(unsupported_numbers))
            )
        mode: ExecutionMode = "model"
        fallback_reason = None
    except (AIProviderError, ApiProblem, ValueError) as exc:
        completion = None
        payload = _fallback_risk_review(allowed_refs)
        mode = "evidence-fallback"
        fallback_reason = str(exc)
    duration_ms = max(1, round((perf_counter() - started) * 1000))
    return payload, completion, mode, fallback_reason, duration_ms


async def _run_moderator(
    settings: Settings,
    provider: ResponsesAIProvider,
    *,
    database: Database,
    actor: ActorContext,
    runtime: AgentRuntime | None,
    agent_run_id: str | None,
    title: str,
    topic: str,
    decision_owner: str,
    success_metric: str,
    evidence_text: str,
    analyses: list[tuple[RoleTwinProfile, RoleAnalysisPayload]],
    deliberations: list[tuple[RoleTwinProfile, RoleTwinProfile, CrossExaminationPayload]],
    risk_review: RiskReviewPayload,
    allowed_refs: set[str],
) -> tuple[DecisionPackagePayload, AICompletion | None, ExecutionMode, str | None, int]:
    started = perf_counter()
    analysis_text = "\n\n".join(
        f"[{profile.display_name}/{profile.role_title}]\n{payload.model_dump_json()}"
        for profile, payload in analyses
    )
    deliberation_text = "\n\n".join(
        f"[{speaker.display_name} -> {target.display_name}]\n{payload.model_dump_json()}"
        for speaker, target, payload in deliberations
    )
    input_text = f"""会议：{title}
议题：{topic}
决策负责人：{decision_owner}
成功指标：{success_metric}

冻结证据：
{evidence_text}

三个角色的独立分析：
{analysis_text}

两轮交叉质询：
{deliberation_text}

反方风险审查：
{risk_review.model_dump_json()}"""
    instructions = """你是企业数字会议的主持与决策秘书。
比较三个角色的独立主张、两轮质询和反方审查，保留真实分歧、未知项、立场变化和失败退出条件。
只能引用给定 E 编号，不得扩大证据范围，不得替人类确认最终执行。
行动项必须有负责人、期限提示、KPI、停止条件和证据引用。
    不要输出隐藏思维过程，也不要编造冻结证据中不存在的数值、日期或制度。"""
    try:
        if settings.agent_runtime_enabled and runtime is not None and agent_run_id:
            completion = await _run_meeting_runtime_json(
                database,
                settings,
                runtime,
                actor=actor,
                agent_run_id=agent_run_id,
                instructions=instructions,
                input_text=input_text,
                output_schema=DecisionPackagePayload.model_json_schema(),
            )
        else:
            completion = await provider.generate(
                settings,
                instructions=instructions,
                input_text=input_text,
                run_id=f"meeting_moderator_{uuid4().hex}",
                schema_name="meeting_decision_package",
                response_schema=DECISION_PACKAGE_JSON_SCHEMA,
            )
        payload = DecisionPackagePayload.model_validate(completion.payload)
        invalid_refs = {
            ref
            for action in payload.actions
            for ref in action.evidence_refs
            if ref not in allowed_refs
        }
        if invalid_refs:
            raise ValueError("决策包引用了不存在的证据：" + "、".join(sorted(invalid_refs)))
        unsupported_numbers = _unsupported_numeric_output(payload.model_dump_json(), input_text)
        if unsupported_numbers:
            raise ValueError(
                "决策包包含冻结证据中不存在的数值或日期：" + "、".join(sorted(unsupported_numbers))
            )
        mode: ExecutionMode = "model"
        fallback_reason = None
    except (AIProviderError, ApiProblem, ValueError) as exc:
        completion = None
        payload = _fallback_decision_package(
            analyses,
            risk_review=risk_review,
            decision_owner=decision_owner,
            success_metric=success_metric,
            allowed_refs=allowed_refs,
        )
        mode = "evidence-fallback"
        fallback_reason = str(exc)
    duration_ms = max(1, round((perf_counter() - started) * 1000))
    return payload, completion, mode, fallback_reason, duration_ms


async def _run_meeting_runtime_json(
    database: Database,
    settings: Settings,
    runtime: AgentRuntime,
    *,
    actor: ActorContext,
    agent_run_id: str,
    instructions: str,
    input_text: str,
    output_schema: dict[str, object],
) -> AICompletion:
    available_tool_keys = {
        item.key for item in list_tool_catalog(database, actor).items if item.risk_level == "R0"
    }
    skill = select_runtime_skill(
        database,
        actor,
        skill_key="policy-grounded-answer",
        required_tool_keys=available_tool_keys,
    )
    gateway = create_mcp_session(
        database,
        actor,
        McpSessionCreateRequest(
            client_id=settings.codex_runtime_mcp_client_id,
            allowed_tool_keys=list(skill.tool_keys),
            scope_constraints=[],
            ttl_seconds=settings.codex_runtime_mcp_ttl_seconds,
            agent_run_id=agent_run_id,
            workspace_key=None,
        ),
    )
    credentials = RuntimeCredentials(
        mcp_session_token=gateway.session_token,
        mcp_client_id=gateway.session.client_id,
    )
    spec = AgentRunSpec(
        run_id=agent_run_id,
        actor=AgentActor(
            enterprise_id=actor.enterprise_id,
            principal_id=actor.principal_id,
            actor_key=actor.actor_key,
            permission_set_version=actor.permission_set_version,
            authentication_method=actor.authentication_method,
        ),
        input_text=input_text,
        instructions=(
            f"{skill.instructions}\n\n会议阶段边界：{instructions}\n"
            "最终只输出符合指定 JSON Schema 的 JSON 对象。"
        ),
        cwd=settings.codex_runtime_cwd,
        model=settings.codex_runtime_model or settings.ai_model,
        allowed_tool_keys=tuple(skill.tool_keys),
        output_schema=output_schema,
        scope_context=build_scope_context(database, actor).snapshot(),
        metadata={"skill_key": skill.skill_key, "skill_version": str(skill.version_number)},
    )
    runtime_session_id: str | None = None
    runtime_turn_id: str | None = None
    try:
        handle = await runtime.start(spec, credentials)
        runtime_session, runtime_turn = create_runtime_session(
            database,
            actor,
            agent_run_id=agent_run_id,
            handle=handle,
            spec=spec,
            mcp_gateway_session_id=gateway.session.session_id,
            model=settings.codex_runtime_model or settings.ai_model,
        )
        runtime_session_id = runtime_session.id
        runtime_turn_id = runtime_turn.id
        final_message: str | None = None
        terminal_event: AgentRunEvent | None = None
        async for event in runtime.stream(agent_run_id):
            append_runtime_event(
                database,
                runtime_session_id=runtime_session_id,
                runtime_turn_id=runtime_turn_id,
                event=event,
            )
            if event.event_type == "message.completed" and event.message:
                final_message = event.message
            if event.event_type in {"run.completed", "run.failed", "run.cancelled"}:
                terminal_event = event
        if terminal_event is None or terminal_event.event_type != "run.completed":
            raise ValueError(
                terminal_event.message if terminal_event else "Agent Runtime 未返回最终状态"
            )
        if not final_message:
            raise ValueError("Agent Runtime 未返回主持汇总")
        payload = json.loads(_strip_json_fence(final_message))
        if not isinstance(payload, dict):
            raise ValueError("Agent Runtime 主持汇总结构无效")
        return AICompletion(payload=payload, input_tokens=None, output_tokens=None)
    except Exception as exc:
        if runtime_session_id and runtime_turn_id:
            mark_runtime_session_failed(
                database,
                runtime_session_id=runtime_session_id,
                runtime_turn_id=runtime_turn_id,
                error_code="meeting_moderator_runtime_failed",
                error_message=str(exc) or exc.__class__.__name__,
            )
        raise
    finally:
        try:
            await runtime.release(agent_run_id)
        except Exception:
            pass
        try:
            revoke_mcp_session(
                database,
                actor,
                gateway.session.session_id,
                McpSessionRevokeRequest(reason="meeting_moderator_runtime_finished"),
            )
        except Exception:
            pass


def _fallback_role_analysis(
    profile: RoleTwinProfile,
    allowed_refs: set[str],
) -> RoleAnalysisPayload:
    refs = sorted(allowed_refs, key=lambda value: int(value[1:]))[:3]
    if profile.twin_key == "twin-ops":
        summary = "运营侧建议在库存和履约约束内做受控投放试验，再根据结果决定是否扩量。"
        recommendation = "先锁定素材、人群、预算边界和观察口径，异常时及时停止。"
        risks = ["投放增量可能无法带来同等成交增量。", "重点商品库存可能限制扩量。"]
    elif profile.twin_key == "twin-finance":
        summary = "财务侧只支持有预算上限、收益口径和停止条件的可回收试验。"
        recommendation = "人工确认预算上限，并按统一指标口径复盘边际回报。"
        risks = ["费用增长可能快于成交增长。", "缺少毛利和现金回收数据会降低判断质量。"]
    else:
        summary = "管理侧建议形成小范围、可复盘、可停止的条件性方案，不直接扩大正式预算。"
        recommendation = "由决策负责人确认成功指标、责任人和停止条件后再创建行动提议。"
        risks = ["证据时间窗口有限。", "当前验证数据不足以代表长期经营趋势。"]
    return RoleAnalysisPayload(
        stance="conditional",
        summary=summary,
        claims=[
            ClaimItem(
                statement=summary,
                evidence_refs=refs,
                assumption="冻结证据在本次会议期间保持不变。",
                confidence="medium",
            )
        ],
        risks=risks,
        unknowns=["尚未接入完整历史时间序列，需要在人工确认前补充核对。"],
        recommendation=recommendation,
        confidence="medium",
    )


def _analysis_refs(payload: RoleAnalysisPayload) -> set[str]:
    return {ref for claim in payload.claims for ref in claim.evidence_refs}


def _cross_refs(payload: CrossExaminationPayload) -> set[str]:
    return {ref for challenge in payload.challenges for ref in challenge.evidence_refs}


def _fallback_cross_examination(
    speaker: RoleTwinProfile,
    target: RoleTwinProfile,
    *,
    speaker_analysis: RoleAnalysisPayload,
    target_analysis: RoleAnalysisPayload,
    prior_turn: CrossExaminationPayload | None,
    prior_refs: set[str],
    allowed_refs: set[str],
    turn_type: Literal["challenge", "response"],
) -> CrossExaminationPayload:
    ordered_refs = sorted(allowed_refs, key=lambda value: int(value[1:]))
    novel_ref = next((ref for ref in ordered_refs if ref not in prior_refs), ordered_refs[0])
    if turn_type == "challenge":
        summary = (
            f"{speaker.display_name}要求{target.display_name}补充验证关键假设，避免重复原有结论。"
        )
        target_claim = target_analysis.claims[0].statement
        statement = f"当前主张仍需用{novel_ref}对应证据校验其适用边界。"
        question = "如果新增证据与原假设冲突，是否缩小方案范围或触发停止条件？"
    else:
        summary = f"{speaker.display_name}回应质询后维持条件性立场，并补充新的证据边界。"
        target_claim = prior_turn.summary if prior_turn else speaker_analysis.summary
        statement = f"回应接受对证据边界的质疑，并用{novel_ref}补充校验。"
        question = "当前冻结证据仍不能解决哪些执行前提？"
    return CrossExaminationPayload(
        summary=summary,
        challenges=[
            CrossExaminationItem(
                statement=statement,
                target_claim=target_claim,
                evidence_refs=[novel_ref],
                new_evidence_refs=[novel_ref],
                question=question,
                confidence="medium",
            )
        ],
        position_after=speaker_analysis.stance,
        position_changed=False,
        unresolved=["缺少更长历史窗口，仍需人工确认当前证据是否足以执行。"],
        confidence="medium",
    )


def _fallback_risk_review(allowed_refs: set[str]) -> RiskReviewPayload:
    refs = sorted(allowed_refs, key=lambda value: int(value[1:]))[:3]
    return RiskReviewPayload(
        summary="反方审查认为受控试验仍可能被短期指标和库存代理信号误导，必须保留退出条件。",
        failure_modes=[
            RiskFailureMode(
                risk="短期经营变化被误判为可持续趋势。",
                mechanism="当前证据以快照和有限制度片段为主，无法验证长期因果关系。",
                evidence_refs=refs,
                trigger="关键指标与库存约束无法同时满足。",
                mitigation="缩小试验范围并在人工确认前补齐历史对照。",
            )
        ],
        counterfactuals=["如果成交变化主要来自自然流量，增加投放可能不会带来同等增量。"],
        incentive_risks=["只考核成交可能激励忽略退款、毛利和履约能力。"],
        unresolved=["缺少完整历史序列和毛利数据，无法确认方案的长期净收益。"],
        confidence="medium",
    )


def _fallback_decision_package(
    analyses: list[tuple[RoleTwinProfile, RoleAnalysisPayload]],
    *,
    risk_review: RiskReviewPayload,
    decision_owner: str,
    success_metric: str,
    allowed_refs: set[str],
) -> DecisionPackagePayload:
    refs = sorted(allowed_refs, key=lambda value: int(value[1:]))[:4]
    return DecisionPackagePayload(
        summary="三个角色均支持先形成受控试验方案，但对数据完整性和预算风险保留意见。",
        consensus=["先试验再扩量。", "行动必须绑定统一指标、责任人和停止条件。"],
        disagreements=["运营更关注试验速度，财务更关注预算可回收性和历史数据完整度。"],
        risks=sorted(
            {risk for _, payload in analyses for risk in payload.risks}
            | {item.risk for item in risk_review.failure_modes}
        ),
        decision="形成条件性试验建议，等待人类决策负责人确认，不直接修改外部系统。",
        actions=[
            DecisionAction(
                title="提交受控经营试验方案",
                owner=decision_owner,
                due_hint="人工确认后启动",
                kpi=success_metric,
                stop_condition="任一已确认成功指标不满足时停止并复盘。",
                evidence_refs=refs,
            )
        ],
        confidence="medium",
    )


def _evidence_text(items: list[EvidenceSnapshotItem]) -> str:
    lines: list[str] = []
    for item in items:
        change_rate = item.payload.get("change_rate")
        business_formats: list[str] = []
        if isinstance(change_rate, int | float):
            business_formats.append(f"业务百分比={change_rate * 100:.1f}%")
        value = item.payload.get("value")
        unit = item.payload.get("unit")
        if isinstance(value, int | float) and isinstance(unit, str) and value >= 10_000:
            converted = value / 10_000
            business_formats.append(
                "业务万位口径="
                + "/".join(
                    [
                        f"{converted:.1f}万",
                        f"{converted:.2f}万",
                        f"{converted:.3f}万",
                        f"{converted:.4f}万",
                    ]
                )
            )
        business_format = f" | {' | '.join(business_formats)}" if business_formats else ""
        lines.append(
            f"[E{item.rank}] 类型={item.item_type} | {item.label} | "
            f"版本={item.version_ref or '无'} | "
            f"{json.dumps(item.payload, ensure_ascii=False, sort_keys=True)}"
            f"{business_format}"
        )
    return "\n".join(lines)


def _unsupported_numeric_output(output: str, source: str) -> set[str]:
    patterns = (
        r"\d{4}-\d{2}-\d{2}",
        r"\d+(?:\.\d+)?\s*(?:年|月|日|天|%|元|万|x|倍)",
        r"\d+(?:\.\d+)?\s*(?:个)?工作日",
    )

    def claims(value: str) -> set[str]:
        return {
            re.sub(r"\s+", "", match)
            for pattern in patterns
            for match in re.findall(pattern, value)
        }

    return claims(output) - claims(source)
