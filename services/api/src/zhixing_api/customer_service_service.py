from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext
from zhixing_api.ai_provider import AICompletion, AIProviderError, ResponsesAIProvider
from zhixing_api.config import Settings
from zhixing_api.customer_service_reconciliation import (
    build_customer_service_canonical_fact as _canonical_order_fact,
)
from zhixing_api.customer_service_schemas import (
    CustomerServiceCanonicalFactView,
    CustomerServiceConversationDetail,
    CustomerServiceConversationView,
    CustomerServiceEventView,
    CustomerServiceEvidenceView,
    CustomerServiceMessageView,
    CustomerServiceMutationResponse,
    CustomerServiceOrderContextView,
    CustomerServicePolicyView,
    CustomerServiceReplyDraftView,
    CustomerServiceStats,
    CustomerServiceStudioResponse,
    CustomerServiceTwinView,
    RiskFlag,
)
from zhixing_api.data_models import (
    AgentRun,
    AgentRunContextItem,
    AgentRunEvidence,
    CustomerServiceConversation,
    CustomerServiceEvent,
    CustomerServiceMessage,
    CustomerServiceOrderContext,
    CustomerServiceReplyDraft,
    EvidenceSnapshot,
    EvidenceSnapshotItem,
    Principal,
    RoleTwinProfile,
    RoleTwinVersion,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.knowledge_schemas import KnowledgeVersionDetailResponse
from zhixing_api.knowledge_service import read_effective_policy

SERVICE_POLICY_KEY = "policy-service-compensation"
SERVICE_TWIN_KEY = "twin-service"

AI_REPLY_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "body": {"type": "string"},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "risk_flags": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "compensation_commitment", "refund_timeline", "unverified_logistics",
                    "safety_or_complaint", "legal_or_media", "personal_data",
                    "manual_request", "data_conflict", "other",
                ],
            },
        },
        "safe_to_send": {"type": "boolean"},
        "suggested_action": {
            "type": "string",
            "enum": ["reply", "investigate", "handoff"],
        },
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": [
        "body", "risk_level", "risk_flags", "safe_to_send", "suggested_action",
        "evidence_refs", "confidence",
    ],
}


def list_customer_service_studio(
    database: Database,
    actor: ActorContext,
    *,
    conversation_key: str | None = None,
) -> CustomerServiceStudioResponse:
    now = datetime.now(UTC)
    policy = read_effective_policy(
        database,
        enterprise_id=actor.enterprise_id,
        document_key=SERVICE_POLICY_KEY,
        as_of=now,
    )
    with database.session() as session:
        profile, twin_version = _service_twin(session, actor.enterprise_id)
        conversations = list(
            session.scalars(
                select(CustomerServiceConversation).where(
                    CustomerServiceConversation.enterprise_id == actor.enterprise_id
                )
            )
        )
        if not conversations:
            raise ApiProblem(
                status_code=404,
                code="customer_service.queue_empty",
                message="客服会话数据库当前为空",
            )
        selected = None
        if conversation_key:
            selected = next(
                (item for item in conversations if item.conversation_key == conversation_key),
                None,
            )
            if selected is None:
                raise ApiProblem(
                    status_code=404,
                    code="customer_service.conversation_not_found",
                    message="没有找到指定客服会话",
                )
        conversations.sort(key=_conversation_sort_key)
        selected = selected or conversations[0]
        message_rows = list(
            session.scalars(
                select(CustomerServiceMessage).where(
                    CustomerServiceMessage.conversation_id.in_(
                        [item.id for item in conversations]
                    )
                )
            )
        )
        draft_rows = list(
            session.scalars(
                select(CustomerServiceReplyDraft).where(
                    CustomerServiceReplyDraft.conversation_id.in_(
                        [item.id for item in conversations]
                    )
                )
            )
        )
        messages_by_conversation: dict[str, list[CustomerServiceMessage]] = {}
        for message in message_rows:
            messages_by_conversation.setdefault(message.conversation_id, []).append(message)
        drafts_by_conversation: dict[str, list[CustomerServiceReplyDraft]] = {}
        for draft in draft_rows:
            drafts_by_conversation.setdefault(draft.conversation_id, []).append(draft)
        all_snapshot_ids = {item.evidence_snapshot_id for item in draft_rows}
        all_evidence_items = list(
            session.scalars(
                select(EvidenceSnapshotItem)
                .where(EvidenceSnapshotItem.snapshot_id.in_(all_snapshot_ids))
                .order_by(EvidenceSnapshotItem.rank)
            )
        ) if all_snapshot_ids else []
        all_evidence_by_snapshot: dict[str, list[CustomerServiceEvidenceView]] = {}
        for item in all_evidence_items:
            all_evidence_by_snapshot.setdefault(item.snapshot_id, []).append(
                CustomerServiceEvidenceView.model_validate(item.payload)
            )
        conversation_views = [
            _conversation_view(
                item,
                messages_by_conversation.get(item.id, []),
                drafts_by_conversation.get(item.id, []),
                now,
            )
            for item in conversations
        ]
        detail = _conversation_detail(session, selected, now)
        stats = CustomerServiceStats(
            waiting_count=sum(item.status == "waiting" for item in conversations),
            review_required_count=sum(
                item.status == "review_required" for item in conversations
            ),
            handoff_count=sum(item.status == "handed_off" for item in conversations),
            overdue_count=sum(_utc(item.first_response_due_at) < now for item in conversations),
            safe_draft_count=sum(
                item.safe_to_send and item.status == "generated" for item in draft_rows
            ),
            total_count=len(conversations),
        )
    return CustomerServiceStudioResponse(
        actor_name=actor.display_name,
        can_generate="customer-service.reply.draft" in actor.permissions,
        can_send="customer-service.reply.send" in actor.permissions,
        can_handoff="customer-service.handoff.create" in actor.permissions,
        stats=stats,
        active_policy=_policy_view(policy),
        twin=CustomerServiceTwinView(
            key=profile.twin_key,
            display_name=twin_version.display_name,
            role_title=profile.role_title,
            version_number=twin_version.version_number,
            version_id=twin_version.id,
            status=twin_version.status,
        ),
        conversations=conversation_views,
        drafts=[
            _draft_view(item, all_evidence_by_snapshot.get(item.evidence_snapshot_id, []))
            for item in sorted(
                draft_rows,
                key=lambda row: _utc(row.created_at),
                reverse=True,
            )
        ],
        selected=detail,
        generated_at=now,
    )


async def generate_customer_service_draft(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    actor: ActorContext,
    *,
    conversation_key: str,
    client_request_key: str,
) -> CustomerServiceMutationResponse:
    with database.session() as session:
        conversation = _conversation(session, actor.enterprise_id, conversation_key)
        existing = session.scalar(
            select(CustomerServiceReplyDraft).where(
                CustomerServiceReplyDraft.enterprise_id == actor.enterprise_id,
                CustomerServiceReplyDraft.idempotency_key == client_request_key,
            )
        )
        if existing is not None:
            if existing.conversation_id != conversation.id:
                raise _idempotency_conflict()
            return CustomerServiceMutationResponse(
                idempotent=True,
                studio=list_customer_service_studio(
                    database, actor, conversation_key=conversation_key
                ),
            )
        if conversation.status in {"handed_off", "resolved"}:
            raise ApiProblem(
                status_code=409,
                code="customer_service.conversation_closed",
                message="已转交或已结束的会话不能继续生成草稿",
            )
        messages = list(
            session.scalars(
                select(CustomerServiceMessage)
                .where(CustomerServiceMessage.conversation_id == conversation.id)
                .order_by(CustomerServiceMessage.occurred_at)
            )
        )
        context = session.scalar(
            select(CustomerServiceOrderContext).where(
                CustomerServiceOrderContext.conversation_id == conversation.id
            )
        )
        if context is None:
            raise ApiProblem(
                status_code=409,
                code="customer_service.context_missing",
                message="当前会话缺少订单或售前上下文",
            )
        canonical_fact = _canonical_order_fact(session, conversation, context)
        profile, twin_version = _service_twin(session, actor.enterprise_id)

    now = datetime.now(UTC)
    policy = read_effective_policy(
        database,
        enterprise_id=actor.enterprise_id,
        document_key=SERVICE_POLICY_KEY,
        as_of=now,
    )
    evidence = _build_evidence(conversation, context, canonical_fact, policy)
    allowed_refs = {item.ref for item in evidence}
    deterministic_flags, requires_handoff, requires_review = _deterministic_risk(
        conversation, messages, context, canonical_fact
    )
    required_fact_refs = _required_canonical_fact_refs(
        conversation, messages, canonical_fact
    )
    required_policy_refs = _required_policy_refs(conversation, messages)
    required_evidence_refs = required_fact_refs | required_policy_refs
    fallback = _fallback_draft(
        conversation,
        context,
        canonical_fact,
        required_evidence_refs,
        deterministic_flags,
        requires_handoff,
    )
    started = perf_counter()
    completion: AICompletion | None = None
    fallback_reason: str | None = None
    try:
        completion = await provider.generate(
            settings,
            instructions=_draft_instructions(profile, twin_version),
            input_text=_draft_input(
                conversation,
                messages,
                context,
                evidence,
                required_evidence_refs,
            ),
            run_id=actor.run_id,
            schema_name="customer_service_reply_draft",
            response_schema=AI_REPLY_SCHEMA,
        )
        model_payload = completion.payload
        body = str(model_payload["body"]).strip()
        if len(body) < 2 or len(body) > 4000:
            raise ValueError("模型草稿长度不符合客服回复契约")
        evidence_refs = [str(item) for item in cast(list[object], model_payload["evidence_refs"])]
        if not evidence_refs or not set(evidence_refs).issubset(allowed_refs):
            raise ValueError("模型引用了本次证据快照之外的编号")
        if not required_evidence_refs.issubset(evidence_refs):
            raise ValueError("模型没有引用当前回复所需的数据或制度证据")
        model_flags = _validated_risk_flags(model_payload["risk_flags"])
        risk_flags = _ordered_flags([*deterministic_flags, *model_flags])
        model_risk = str(model_payload["risk_level"])
        risk_level = _highest_service_risk(conversation.risk_level, model_risk)
        if canonical_fact.material_conflict:
            risk_level = _highest_service_risk(risk_level, "medium")
        model_requires_review = risk_level != "low"
        safe_to_send = (
            bool(model_payload["safe_to_send"])
            and not requires_review
            and not model_requires_review
        )
        suggested_action = str(model_payload["suggested_action"])
        if requires_handoff or risk_level in {"high", "critical"}:
            suggested_action = "handoff"
        elif requires_review or model_requires_review:
            suggested_action = "investigate"
        execution_mode: Literal["model", "evidence-fallback"] = "model"
        provider_name = "openai-compatible-responses"
        model_name = settings.ai_model
    except (AIProviderError, KeyError, TypeError, ValueError) as exc:
        body = cast(str, fallback["body"])
        evidence_refs = cast(list[str], fallback["evidence_refs"])
        risk_flags = deterministic_flags
        risk_level = cast(
            Literal["low", "medium", "high", "critical"], conversation.risk_level
        )
        if canonical_fact.material_conflict:
            risk_level = _highest_service_risk(risk_level, "medium")
        safe_to_send = not requires_review
        suggested_action = "handoff" if requires_handoff else (
            "investigate" if requires_review else "reply"
        )
        execution_mode = "evidence-fallback"
        provider_name = "local-evidence"
        model_name = "deterministic-v1"
        fallback_reason = str(exc)
    duration_ms = max(1, round((perf_counter() - started) * 1000))

    snapshot_id = f"evidence_snapshot_{uuid4().hex}"
    agent_run_id = f"agent_run_{uuid4().hex}"
    draft_id = f"customer_draft_{uuid4().hex}"
    serialized_evidence = json.dumps(
        [item.model_dump(mode="json") for item in evidence],
        ensure_ascii=False,
        sort_keys=True,
    )
    with database.session() as session:
        persisted_conversation = _conversation(session, actor.enterprise_id, conversation_key)
        latest_version = session.scalar(
            select(func.max(CustomerServiceReplyDraft.version_number)).where(
                CustomerServiceReplyDraft.conversation_id == persisted_conversation.id
            )
        ) or 0
        session.add(
            EvidenceSnapshot(
                id=snapshot_id,
                enterprise_id=actor.enterprise_id,
                snapshot_key=f"evs-customer-service-{uuid4().hex[:12]}",
                purpose="customer-service-reply",
                query=f"{conversation_key}:{SERVICE_POLICY_KEY}",
                content_hash=_hash(serialized_evidence),
                item_count=len(evidence),
                frozen_at=now,
            )
        )
        session.flush()
        for rank, item in enumerate(evidence, start=1):
            session.add(
                EvidenceSnapshotItem(
                    id=f"evidence_snapshot_item_{uuid4().hex}",
                    snapshot_id=snapshot_id,
                    item_type=item.item_type,
                    item_key=item.ref,
                    version_ref=item.version_ref,
                    label=item.label,
                    payload=item.model_dump(mode="json"),
                    rank=rank,
                )
            )
        session.add(
            AgentRun(
                id=agent_run_id,
                enterprise_id=actor.enterprise_id,
                actor_principal_id=actor.principal_id,
                twin_profile_id=profile.id,
                role_twin_version_id=twin_version.id,
                run_type="customer-service-draft",
                phase="reply-drafting",
                question="\n".join(
                    item.content for item in messages if item.direction == "inbound"
                ),
                answer=body,
                answer_payload={
                    "body": body,
                    "risk_level": risk_level,
                    "risk_flags": risk_flags,
                    "safe_to_send": safe_to_send,
                    "suggested_action": suggested_action,
                    "evidence_refs": evidence_refs,
                },
                status="completed" if execution_mode == "model" else "degraded",
                provider=provider_name,
                model=model_name,
                fallback_reason=fallback_reason,
                duration_ms=duration_ms,
                input_tokens=completion.input_tokens if completion else None,
                output_tokens=completion.output_tokens if completion else None,
                created_at=now,
            )
        )
        session.flush()
        policy_evidence = [item for item in evidence if item.item_type == "policy"]
        policy_chunks = {chunk.id: chunk for chunk in policy.chunks}
        for rank, item in enumerate(policy_evidence, start=1):
            chunk = policy_chunks.get(str(item.version_ref))
            if chunk is None:
                continue
            session.add(
                AgentRunEvidence(
                    id=f"agent_evidence_{uuid4().hex}",
                    run_id=agent_run_id,
                    chunk_id=chunk.id,
                    rank=rank,
                    score=1.0,
                    excerpt=item.excerpt,
                    citation_label=item.label,
                )
            )
        for rank, item in enumerate(
            [entry for entry in evidence if entry.item_type != "policy"], start=1
        ):
            session.add(
                AgentRunContextItem(
                    id=f"agent_context_{uuid4().hex}",
                    run_id=agent_run_id,
                    item_type=f"customer-service-{item.item_type}",
                    item_id=item.locator or context.id,
                    version_ref=item.version_ref or context.payload_version,
                    rank=rank,
                    content_hash=_hash(item.excerpt),
                    excerpt=item.excerpt,
                    citation_label=item.label,
                )
            )
        existing_generated = list(
            session.scalars(
                select(CustomerServiceReplyDraft).where(
                    CustomerServiceReplyDraft.conversation_id == persisted_conversation.id,
                    CustomerServiceReplyDraft.status == "generated",
                )
            )
        )
        for old_draft in existing_generated:
            old_draft.status = "superseded"
        draft = CustomerServiceReplyDraft(
            id=draft_id,
            enterprise_id=actor.enterprise_id,
            conversation_id=persisted_conversation.id,
            version_number=int(latest_version) + 1,
            status="generated",
            body=body,
            risk_level=risk_level,
            risk_flags=risk_flags,
            safe_to_send=safe_to_send,
            suggested_action=suggested_action,
            evidence_refs=evidence_refs,
            provider=provider_name,
            model=model_name,
            execution_mode=execution_mode,
            fallback_reason=fallback_reason,
            evidence_snapshot_id=snapshot_id,
            agent_run_id=agent_run_id,
            role_twin_version_id=twin_version.id,
            created_by_principal_id=actor.principal_id,
            approved_by_principal_id=None,
            approval_note=None,
            idempotency_key=client_request_key,
            request_id=actor.request_id,
            run_id=actor.run_id,
            created_at=now,
            approved_at=None,
        )
        session.add(draft)
        persisted_conversation.status = "draft_ready" if safe_to_send else "review_required"
        persisted_conversation.updated_at = now
        session.add(
            _event(
                actor,
                persisted_conversation,
                event_type="draft_generated",
                idempotency_key=client_request_key,
                reply_draft_id=draft_id,
                details={
                    "safe_to_send": safe_to_send,
                    "suggested_action": suggested_action,
                    "risk_flags": risk_flags,
                    "execution_mode": execution_mode,
                },
                occurred_at=now,
            )
        )
        session.commit()
    return CustomerServiceMutationResponse(
        idempotent=False,
        studio=list_customer_service_studio(database, actor, conversation_key=conversation_key),
    )


def send_customer_service_sandbox_reply(
    database: Database,
    actor: ActorContext,
    *,
    draft_id: str,
    final_body: str | None,
    note: str,
    client_request_key: str,
) -> CustomerServiceMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        draft = session.scalar(
            select(CustomerServiceReplyDraft).where(
                CustomerServiceReplyDraft.enterprise_id == actor.enterprise_id,
                CustomerServiceReplyDraft.id == draft_id,
            )
        )
        if draft is None:
            raise ApiProblem(
                status_code=404,
                code="customer_service.draft_not_found",
                message="没有找到指定客服草稿",
            )
        conversation = session.get(CustomerServiceConversation, draft.conversation_id)
        if conversation is None:
            raise ApiProblem(
                status_code=409,
                code="customer_service.conversation_missing",
                message="客服草稿关联的会话已不存在",
            )
        existing = session.scalar(
            select(CustomerServiceEvent).where(
                CustomerServiceEvent.enterprise_id == actor.enterprise_id,
                CustomerServiceEvent.idempotency_key == client_request_key,
            )
        )
        if existing is not None:
            if existing.reply_draft_id != draft.id:
                raise _idempotency_conflict()
            return CustomerServiceMutationResponse(
                idempotent=True,
                studio=list_customer_service_studio(
                    database, actor, conversation_key=conversation.conversation_key
                ),
            )
        if draft.status == "sandbox_sent":
            raise ApiProblem(
                status_code=409,
                code="customer_service.draft_already_sent",
                message="该草稿已经写入沙箱通道",
            )
        context = session.scalar(
            select(CustomerServiceOrderContext).where(
                CustomerServiceOrderContext.conversation_id == conversation.id
            )
        )
        if context is None:
            raise ApiProblem(
                status_code=409,
                code="customer_service.context_missing",
                message="当前会话缺少订单或售前上下文",
            )
        current_fact = _canonical_order_fact(session, conversation, context)
        if current_fact.material_conflict:
            raise ApiProblem(
                status_code=409,
                code="customer_service.data_reconciliation_required",
                message="客服上下文与数据中心事实存在重大差异，核验完成前不能发送",
                details={
                    "difference_fields": [item.field for item in current_fact.differences],
                    "suggested_action": "investigate",
                },
            )
        if draft.status != "generated" or not draft.safe_to_send:
            raise ApiProblem(
                status_code=409,
                code="customer_service.human_review_required",
                message="风险规则未放行该草稿，不能执行沙箱发送",
                details={"suggested_action": draft.suggested_action},
            )
        body = final_body.strip() if final_body else draft.body
        if len(body) < 2:
            raise ApiProblem(
                status_code=422,
                code="customer_service.reply_empty",
                message="确认后的客服回复不能为空",
            )
        message_count = session.scalar(
            select(func.count(CustomerServiceMessage.id)).where(
                CustomerServiceMessage.conversation_id == conversation.id
            )
        ) or 0
        session.add(
            CustomerServiceMessage(
                id=f"customer_message_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                conversation_id=conversation.id,
                message_key=f"{conversation.conversation_key}:out:{int(message_count) + 1:02d}",
                sender_type="agent",
                direction="outbound",
                sender_name=actor.display_name,
                content=body,
                delivery_status="sandbox-sent",
                source_message_id=None,
                occurred_at=now,
                created_at=now,
            )
        )
        edited = body != draft.body
        draft.body = body
        draft.status = "sandbox_sent"
        draft.approved_by_principal_id = actor.principal_id
        draft.approval_note = note
        draft.approved_at = now
        conversation.status = "resolved"
        conversation.last_message_at = now
        conversation.updated_at = now
        session.add(
            _event(
                actor,
                conversation,
                event_type="sandbox_reply_sent",
                idempotency_key=client_request_key,
                reply_draft_id=draft.id,
                details={
                    "channel": "commerce-sandbox",
                    "delivery_status": "sandbox-sent",
                    "human_confirmed": True,
                    "edited": edited,
                    "note": note,
                },
                occurred_at=now,
            )
        )
        conversation_key = conversation.conversation_key
        session.commit()
    return CustomerServiceMutationResponse(
        idempotent=False,
        studio=list_customer_service_studio(database, actor, conversation_key=conversation_key),
    )


def handoff_customer_service_conversation(
    database: Database,
    actor: ActorContext,
    *,
    conversation_key: str,
    reason: str,
    client_request_key: str,
) -> CustomerServiceMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        conversation = _conversation(session, actor.enterprise_id, conversation_key)
        existing = session.scalar(
            select(CustomerServiceEvent).where(
                CustomerServiceEvent.enterprise_id == actor.enterprise_id,
                CustomerServiceEvent.idempotency_key == client_request_key,
            )
        )
        if existing is not None:
            if existing.conversation_id != conversation.id:
                raise _idempotency_conflict()
            return CustomerServiceMutationResponse(
                idempotent=True,
                studio=list_customer_service_studio(
                    database, actor, conversation_key=conversation_key
                ),
            )
        if conversation.status == "resolved":
            raise ApiProblem(
                status_code=409,
                code="customer_service.conversation_resolved",
                message="已结束的会话不能创建人工接管",
            )
        latest_draft_id = session.scalar(
            select(CustomerServiceReplyDraft.id)
            .where(CustomerServiceReplyDraft.conversation_id == conversation.id)
            .order_by(CustomerServiceReplyDraft.version_number.desc())
            .limit(1)
        )
        conversation.status = "handed_off"
        conversation.updated_at = now
        session.add(
            _event(
                actor,
                conversation,
                event_type="handoff_created",
                idempotency_key=client_request_key,
                reply_draft_id=latest_draft_id,
                details={
                    "reason": reason,
                    "queue": "customer-service-risk-review",
                    "production_action": False,
                },
                occurred_at=now,
            )
        )
        session.commit()
    return CustomerServiceMutationResponse(
        idempotent=False,
        studio=list_customer_service_studio(database, actor, conversation_key=conversation_key),
    )


def _conversation_detail(
    session: Session,
    conversation: CustomerServiceConversation,
    now: datetime,
) -> CustomerServiceConversationDetail:
    messages = list(
        session.scalars(
            select(CustomerServiceMessage)
            .where(CustomerServiceMessage.conversation_id == conversation.id)
            .order_by(CustomerServiceMessage.occurred_at)
        )
    )
    context = session.scalar(
        select(CustomerServiceOrderContext).where(
            CustomerServiceOrderContext.conversation_id == conversation.id
        )
    )
    if context is None:
        raise ApiProblem(
            status_code=409,
            code="customer_service.context_missing",
            message="当前会话缺少订单或售前上下文",
        )
    drafts = list(
        session.scalars(
            select(CustomerServiceReplyDraft)
            .where(CustomerServiceReplyDraft.conversation_id == conversation.id)
            .order_by(CustomerServiceReplyDraft.version_number.desc())
        )
    )
    events = list(
        session.scalars(
            select(CustomerServiceEvent)
            .where(CustomerServiceEvent.conversation_id == conversation.id)
            .order_by(CustomerServiceEvent.occurred_at.desc())
        )
    )
    principal_ids = {item.actor_principal_id for item in events}
    principals = {
        item.id: item.display_name
        for item in session.scalars(select(Principal).where(Principal.id.in_(principal_ids)))
    } if principal_ids else {}
    snapshot_ids = {item.evidence_snapshot_id for item in drafts}
    evidence_items = list(
        session.scalars(
            select(EvidenceSnapshotItem)
            .where(EvidenceSnapshotItem.snapshot_id.in_(snapshot_ids))
            .order_by(EvidenceSnapshotItem.rank)
        )
    ) if snapshot_ids else []
    evidence_by_snapshot: dict[str, list[CustomerServiceEvidenceView]] = {}
    for item in evidence_items:
        evidence_by_snapshot.setdefault(item.snapshot_id, []).append(
            CustomerServiceEvidenceView.model_validate(item.payload)
        )
    return CustomerServiceConversationDetail(
        conversation=_conversation_view(conversation, messages, drafts, now),
        messages=[
            CustomerServiceMessageView(
                id=item.id,
                message_key=item.message_key,
                sender_type=cast(Literal["customer", "agent", "system"], item.sender_type),
                direction=cast(Literal["inbound", "outbound"], item.direction),
                sender_name=item.sender_name,
                content=item.content,
                delivery_status=item.delivery_status,
                occurred_at=item.occurred_at,
            )
            for item in messages
        ],
        order_context=CustomerServiceOrderContextView(
            context_type=cast(Literal["order", "pre-sale"], context.context_type),
            order_key=context.order_key,
            order_status=context.order_status,
            paid_amount=context.paid_amount,
            currency=context.currency,
            product_summary=context.product_summary,
            item_quantity=context.item_quantity,
            payment_at=context.payment_at,
            logistics_status=context.logistics_status,
            carrier=context.carrier,
            tracking_no=context.tracking_no,
            latest_logistics_event=context.latest_logistics_event,
            promised_delivery_at=context.promised_delivery_at,
            latest_logistics_at=context.latest_logistics_at,
            delayed_hours=context.delayed_hours,
            aftersale_status=context.aftersale_status,
            source_system_key=context.source_system_key,
            payload_version=context.payload_version,
            synced_at=context.synced_at,
        ),
        canonical_order_fact=_canonical_order_fact(session, conversation, context),
        drafts=[
            _draft_view(item, evidence_by_snapshot.get(item.evidence_snapshot_id, []))
            for item in drafts
        ],
        events=[
            CustomerServiceEventView(
                id=item.id,
                event_type=cast(
                    Literal["draft_generated", "sandbox_reply_sent", "handoff_created"],
                    item.event_type,
                ),
                reply_draft_id=item.reply_draft_id,
                actor_principal_id=item.actor_principal_id,
                actor_name=principals.get(item.actor_principal_id, item.actor_principal_id),
                details=item.details,
                occurred_at=item.occurred_at,
            )
            for item in events
        ],
    )


def _conversation_view(
    conversation: CustomerServiceConversation,
    messages: list[CustomerServiceMessage],
    drafts: list[CustomerServiceReplyDraft],
    now: datetime,
) -> CustomerServiceConversationView:
    latest = max(messages, key=lambda item: _utc(item.occurred_at), default=None)
    return CustomerServiceConversationView(
        id=conversation.id,
        enterprise_id=conversation.enterprise_id,
        conversation_key=conversation.conversation_key,
        channel_key=conversation.channel_key,
        external_conversation_id=conversation.external_conversation_id,
        source_system_key=conversation.source_system_key,
        customer_key=conversation.customer_key,
        customer_name=conversation.customer_name,
        order_key=conversation.order_key,
        store_scope_key=conversation.store_scope_key,
        topic=conversation.topic,
        status=cast(
            Literal["waiting", "draft_ready", "review_required", "handed_off", "resolved"],
            conversation.status,
        ),
        priority=cast(Literal["normal", "high", "urgent"], conversation.priority),
        sentiment=cast(Literal["calm", "concerned", "angry"], conversation.sentiment),
        risk_level=cast(
            Literal["low", "medium", "high", "critical"], conversation.risk_level
        ),
        risk_reason=conversation.risk_reason,
        assigned_principal_id=conversation.assigned_principal_id,
        last_message_at=conversation.last_message_at,
        first_response_due_at=conversation.first_response_due_at,
        latest_sync_at=conversation.latest_sync_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        last_message_preview=latest.content[:120] if latest else "",
        message_count=len(messages),
        draft_count=len(drafts),
        sla_overdue=(
            _utc(conversation.first_response_due_at) < now
            and conversation.status not in {"resolved", "handed_off"}
        ),
    )


def _draft_view(
    draft: CustomerServiceReplyDraft,
    evidence: list[CustomerServiceEvidenceView],
) -> CustomerServiceReplyDraftView:
    return CustomerServiceReplyDraftView(
        id=draft.id,
        enterprise_id=draft.enterprise_id,
        conversation_id=draft.conversation_id,
        version_number=draft.version_number,
        status=cast(
            Literal["generated", "sandbox_sent", "rejected", "superseded"], draft.status
        ),
        body=draft.body,
        risk_level=cast(
            Literal["low", "medium", "high", "critical"], draft.risk_level
        ),
        risk_flags=cast(list[RiskFlag], draft.risk_flags),
        safe_to_send=draft.safe_to_send,
        suggested_action=cast(
            Literal["reply", "investigate", "handoff"], draft.suggested_action
        ),
        evidence_refs=draft.evidence_refs,
        evidence=evidence,
        provider=draft.provider,
        model=draft.model,
        execution_mode=cast(
            Literal["model", "evidence-fallback"], draft.execution_mode
        ),
        fallback_reason=draft.fallback_reason,
        evidence_snapshot_id=draft.evidence_snapshot_id,
        agent_run_id=draft.agent_run_id,
        role_twin_version_id=draft.role_twin_version_id,
        created_by_principal_id=draft.created_by_principal_id,
        approved_by_principal_id=draft.approved_by_principal_id,
        approval_note=draft.approval_note,
        idempotency_key=draft.idempotency_key,
        request_id=draft.request_id,
        run_id=draft.run_id,
        created_at=draft.created_at,
        approved_at=draft.approved_at,
    )


def _build_evidence(
    conversation: CustomerServiceConversation,
    context: CustomerServiceOrderContext,
    canonical_fact: CustomerServiceCanonicalFactView,
    policy: KnowledgeVersionDetailResponse,
) -> list[CustomerServiceEvidenceView]:
    order_excerpt = (
        f"订单={context.order_key or '售前咨询'}；状态={context.order_status or '无'}；"
        "实付="
        f"{context.paid_amount if context.paid_amount is not None else '无'} "
        f"{context.currency}；"
        f"商品={context.product_summary}；数量={context.item_quantity}"
    )
    logistics_excerpt = (
        f"物流状态={context.logistics_status or '无'}；承运商={context.carrier or '无'}；"
        f"轨迹={context.latest_logistics_event or '无可验证轨迹'}；延迟={context.delayed_hours}小时"
    )
    items = [
        CustomerServiceEvidenceView(
            ref="D1",
            item_type="order",
            label=f"订单上下文 · {conversation.order_key or conversation.customer_key}",
            version_ref=context.payload_version,
            excerpt=order_excerpt,
            locator=context.source_system_key,
        ),
        CustomerServiceEvidenceView(
            ref="D2",
            item_type="logistics",
            label="履约上下文 · 沙箱同步快照",
            version_ref=context.payload_version,
            excerpt=logistics_excerpt,
            locator=context.tracking_no,
        ),
    ]
    if canonical_fact.match_status == "matched":
        order_fact_excerpt = (
            f"规范订单={canonical_fact.order_key}；状态={canonical_fact.order_status}；"
            f"实付={canonical_fact.paid_amount} {canonical_fact.currency}；"
            f"成本={canonical_fact.cost_amount} {canonical_fact.currency}；"
            f"毛利率={_percent(canonical_fact.gross_margin_rate)}；"
            f"商品件数={canonical_fact.item_count}；业务日期={canonical_fact.business_date}；"
            f"来源={canonical_fact.source_system_key}；同步批次={','.join(canonical_fact.sync_run_ids)}"
        )
        items.append(
            CustomerServiceEvidenceView(
                ref="D3",
                item_type="order-fact",
                label=f"数据中心规范订单事实 · {canonical_fact.order_key}",
                version_ref=canonical_fact.sync_run_ids[0]
                if canonical_fact.sync_run_ids
                else canonical_fact.mapping_version,
                excerpt=order_fact_excerpt,
                locator=canonical_fact.order_key,
            )
        )
        if canonical_fact.refund_count > 0:
            items.append(
                CustomerServiceEvidenceView(
                    ref="D4",
                    item_type="refund-fact",
                    label=f"数据中心规范退款事实 · {canonical_fact.order_key}",
                    version_ref=canonical_fact.sync_run_ids[-1]
                    if canonical_fact.sync_run_ids
                    else canonical_fact.mapping_version,
                    excerpt=(
                        f"退款记录={canonical_fact.refund_count}；"
                        f"退款金额={canonical_fact.refund_amount} {canonical_fact.currency}；"
                        f"退款状态={','.join(canonical_fact.refund_statuses) or '无'}"
                    ),
                    locator=canonical_fact.order_key,
                )
            )
        if canonical_fact.differences:
            items.append(
                CustomerServiceEvidenceView(
                    ref="D5",
                    item_type="reconciliation",
                    label=f"跨源订单对账结果 · {canonical_fact.order_key}",
                    version_ref=canonical_fact.mapping_version,
                    excerpt="；".join(item.message for item in canonical_fact.differences),
                    locator=canonical_fact.order_key,
                )
            )
    items.extend(
        CustomerServiceEvidenceView(
            ref=f"K{index}",
            item_type="policy",
            label=f"{policy.document.title} {policy.version.version_label} · {chunk.heading}",
            version_ref=chunk.id,
            excerpt=chunk.content[:700],
            locator=chunk.locator,
        )
        for index, chunk in enumerate(policy.chunks[:6], start=1)
    )
    return items


def _percent(value: float | None) -> str:
    return f"{value * 100:.2f}%" if value is not None else "无"


def _deterministic_risk(
    conversation: CustomerServiceConversation,
    messages: list[CustomerServiceMessage],
    context: CustomerServiceOrderContext,
    canonical_fact: CustomerServiceCanonicalFactView,
) -> tuple[list[RiskFlag], bool, bool]:
    text = " ".join(
        [conversation.topic, *(item.content for item in messages)]
    ).casefold()
    flags: list[RiskFlag] = []
    amounts = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\s*元", text)]
    if ("补偿" in text or "赔偿" in text) and (not amounts or max(amounts) > 50):
        flags.append("compensation_commitment")
    if "退款" in text and any(term in text for term in ("今天", "马上", "到账", "时点")):
        flags.append("refund_timeline")
    if any(term in text for term in ("物流", "包裹", "快递", "地址")) and (
        context.delayed_hours > 0 or not context.latest_logistics_event
    ):
        flags.append("unverified_logistics")
    if any(term in text for term in ("安全", "漏液", "破损", "质量", "小孩")):
        flags.append("safety_or_complaint")
    if any(term in text for term in ("媒体", "监管", "投诉平台", "律师", "起诉")):
        flags.append("legal_or_media")
    if any(term in text for term in ("个人数据", "购买记录", "隐私", "删除账号")):
        flags.append("personal_data")
    if any(term in text for term in ("转人工", "人工客服", "人工处理")):
        flags.append("manual_request")
    if conversation.risk_level in {"high", "critical"} and not flags:
        flags.append("other")
    if canonical_fact.material_conflict:
        flags.append("data_conflict")
    flags = _ordered_flags(flags)
    handoff_flags = {
        "compensation_commitment", "refund_timeline", "safety_or_complaint",
        "legal_or_media", "personal_data", "manual_request",
    }
    requires_handoff = (
        conversation.risk_level in {"high", "critical"}
        or bool(set(flags) & handoff_flags)
    )
    requires_review = (
        requires_handoff
        or conversation.risk_level == "medium"
        or canonical_fact.material_conflict
    )
    return flags, requires_handoff, requires_review


def _fallback_draft(
    conversation: CustomerServiceConversation,
    context: CustomerServiceOrderContext,
    canonical_fact: CustomerServiceCanonicalFactView,
    required_evidence_refs: set[str],
    flags: list[RiskFlag],
    requires_handoff: bool,
) -> dict[str, object]:
    canonical_clause = (
        f"数据中心规范订单 {canonical_fact.order_key} 当前状态为"
        f"{canonical_fact.order_status or '待核验'} [D3]。"
        if "D3" in required_evidence_refs
        else ""
    )
    refund_clause = (
        f"数据中心同时记录 {canonical_fact.refund_count} 笔退款事实，"
        f"金额合计 {canonical_fact.refund_amount} {canonical_fact.currency} [D4]。"
        if "D4" in required_evidence_refs
        else ""
    )
    policy_refs = sorted(ref for ref in required_evidence_refs if ref.startswith("K"))
    policy_citation = "".join(f"[{ref}]" for ref in policy_refs)
    if canonical_fact.material_conflict:
        body = (
            f"您好，关于“{conversation.topic}”我已经记录。当前客服业务上下文与数据中心"
            "规范事实存在差异 [D1][D3][D5]，在金额、状态、商品件数或退款记录完成"
            f"人工核验前，我不会承诺处理结果或发送交易结论 {policy_citation}。"
        )
    elif requires_handoff:
        body = (
            f"您好，关于“{conversation.topic}”我已经记录，并核对到当前订单与履约信息 [D1][D2]。"
            f"{canonical_clause}{refund_clause}"
            "该事项涉及需要专人核验的承诺或风险边界，我先为您转交人工专员；"
            f"核验完成前不会承诺补偿金额、退款到账或处理时点 {policy_citation}。"
        )
    elif context.context_type == "pre-sale":
        body = (
            f"您好，已看到您的咨询。当前商品信息为：{context.product_summary} [D1]。"
            f"建议您结合实际使用场景确认，并按当前有效规则处理 {policy_citation}。"
        )
    else:
        body = (
            f"您好，已核对客服订单上下文 [D1]。{canonical_clause}{refund_clause}"
            f"关于“{conversation.topic}”，"
            f"我会按当前生效规则协助处理，不会补充未经系统验证的承诺 {policy_citation}。"
        )
    base_refs = ["D1", "D2"] if requires_handoff else ["D1"]
    refs = [*base_refs, *sorted(required_evidence_refs)]
    return {"body": body, "evidence_refs": refs, "risk_flags": flags}


def _required_canonical_fact_refs(
    conversation: CustomerServiceConversation,
    messages: list[CustomerServiceMessage],
    canonical_fact: CustomerServiceCanonicalFactView,
) -> set[str]:
    if canonical_fact.match_status != "matched":
        return set()
    required = {"D3"}
    if canonical_fact.material_conflict:
        required.add("D5")
    text = " ".join(
        [conversation.topic, *(item.content for item in messages)]
    ).casefold()
    if canonical_fact.refund_count > 0 and any(
        term in text for term in ("退款", "退货", "退回", "到账", "售后")
    ):
        required.add("D4")
    return required


def _required_policy_refs(
    conversation: CustomerServiceConversation,
    messages: list[CustomerServiceMessage],
) -> set[str]:
    text = " ".join(
        [conversation.topic, *(item.content for item in messages)]
    ).casefold()
    required: set[str] = set()
    topic_rules = (
        ("K1", ("补偿", "赔偿", "优惠券")),
        ("K2", ("物流", "快递", "延迟", "丢件", "轨迹")),
        ("K3", ("退货", "退款", "退回", "到账", "售后")),
        ("K4", ("发票", "地址", "扣款", "支付", "门牌")),
        ("K5", ("尺码", "优惠", "活动", "错发", "错误商品", "清洁", "保养", "洗衣")),
        ("K6", ("安全", "漏液", "媒体", "监管", "隐私", "个人数据", "删除账号", "人工")),
    )
    for ref, terms in topic_rules:
        if any(term in text for term in terms):
            required.add(ref)
    if conversation.risk_level in {"high", "critical"}:
        required.add("K6")
    return required or {"K6"}


def _draft_instructions(profile: RoleTwinProfile, version: RoleTwinVersion) -> str:
    return f"""你是企业电商客服回复草稿助手，只能输出供人工确认的草稿。
角色：{version.display_name} / {profile.role_title}
表达方式：{version.voice_guide}
判断要求：{version.reasoning_guide}
回答边界：{version.answer_policy}
只能依据 D/K 编号证据；不得虚构订单、物流、退款、补偿或处理时点。
存在 D3 时，凡回复订单状态、金额或订单处理必须引用 D3；存在 D4 且问题涉及退货、
退款或到账时必须引用 D4。不能用客服上下文 D1/D2 替代数据中心规范交易事实。
存在 D5 时说明跨源数据发生重大差异，必须引用 D5，safe_to_send=false 且
suggested_action=investigate；不得自行选择其中一套数据继续回复。
必须引用输入中列出的 K 编号对应场景制度；没有制度依据时不得根据常识补写操作流程。
遇到安全、媒体监管、隐私、超授权补偿或客户要求人工时，
必须 safe_to_send=false 且 suggested_action=handoff。
不要输出隐藏思维过程。"""


def _draft_input(
    conversation: CustomerServiceConversation,
    messages: list[CustomerServiceMessage],
    context: CustomerServiceOrderContext,
    evidence: list[CustomerServiceEvidenceView],
    required_evidence_refs: set[str],
) -> str:
    transcript = "\n".join(
        f"{item.sender_name}: {item.content}" for item in messages if item.direction == "inbound"
    )
    evidence_text = "\n".join(
        f"[{item.ref}] {item.label}: {item.excerpt}" for item in evidence
    )
    return f"""会话主题：{conversation.topic}
平台预判风险：{conversation.risk_level} / {conversation.risk_reason}
店铺范围：{conversation.store_scope_key}
订单类型：{context.context_type}
本次输出 evidence_refs 必须包含：{', '.join(sorted(required_evidence_refs))}
缺少任一必需引用时，整个模型输出会被服务端拒绝。
客户消息：
{transcript}

可用证据：
{evidence_text}"""


def _service_twin(
    session: Session,
    enterprise_id: str,
) -> tuple[RoleTwinProfile, RoleTwinVersion]:
    profile = session.scalar(
        select(RoleTwinProfile).where(
            RoleTwinProfile.enterprise_id == enterprise_id,
            RoleTwinProfile.twin_key == SERVICE_TWIN_KEY,
            RoleTwinProfile.status == "published",
        )
    )
    if profile is None:
        raise ApiProblem(
            status_code=409,
            code="customer_service.twin_unavailable",
            message="客服角色分身尚未发布",
        )
    version = session.scalar(
        select(RoleTwinVersion)
        .where(
            RoleTwinVersion.twin_profile_id == profile.id,
            RoleTwinVersion.status == "published",
        )
        .order_by(RoleTwinVersion.version_number.desc())
    )
    if version is None:
        raise ApiProblem(
            status_code=409,
            code="customer_service.twin_version_unavailable",
            message="客服角色分身缺少已发布版本",
        )
    return profile, version


def _conversation(
    session: Session,
    enterprise_id: str,
    conversation_key: str,
) -> CustomerServiceConversation:
    conversation = session.scalar(
        select(CustomerServiceConversation).where(
            CustomerServiceConversation.enterprise_id == enterprise_id,
            CustomerServiceConversation.conversation_key == conversation_key,
        )
    )
    if conversation is None:
        raise ApiProblem(
            status_code=404,
            code="customer_service.conversation_not_found",
            message="没有找到指定客服会话",
        )
    return conversation


def _event(
    actor: ActorContext,
    conversation: CustomerServiceConversation,
    *,
    event_type: str,
    idempotency_key: str,
    reply_draft_id: str | None,
    details: dict[str, object],
    occurred_at: datetime,
) -> CustomerServiceEvent:
    return CustomerServiceEvent(
        id=f"customer_event_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        conversation_id=conversation.id,
        reply_draft_id=reply_draft_id,
        event_type=event_type,
        actor_principal_id=actor.principal_id,
        actor_snapshot=actor.snapshot(),
        details=details,
        idempotency_key=idempotency_key,
        request_id=actor.request_id,
        run_id=actor.run_id,
        occurred_at=occurred_at,
    )


def _policy_view(policy: KnowledgeVersionDetailResponse) -> CustomerServicePolicyView:
    return CustomerServicePolicyView(
        document_key=policy.document.key,
        title=policy.document.title,
        version_label=policy.version.version_label,
        status=policy.version.status,
        effective_from=policy.version.effective_from,
        resolved_at=policy.resolved_at,
    )


def _conversation_sort_key(
    conversation: CustomerServiceConversation,
) -> tuple[int, int, datetime]:
    status_order = {
        "review_required": 0,
        "waiting": 1,
        "draft_ready": 2,
        "handed_off": 3,
        "resolved": 4,
    }
    priority_order = {"urgent": 0, "high": 1, "normal": 2}
    return (
        status_order.get(conversation.status, 9),
        priority_order.get(conversation.priority, 9),
        _utc(conversation.last_message_at),
    )


def _validated_risk_flags(value: object) -> list[RiskFlag]:
    if not isinstance(value, list):
        raise ValueError("模型风险标记不是数组")
    allowed = {
        "compensation_commitment", "refund_timeline", "unverified_logistics",
        "safety_or_complaint", "legal_or_media", "personal_data",
        "manual_request", "data_conflict", "other",
    }
    flags = [str(item) for item in value]
    if not set(flags).issubset(allowed):
        raise ValueError("模型返回未知风险标记")
    return cast(list[RiskFlag], flags)


def _ordered_flags(flags: list[RiskFlag]) -> list[RiskFlag]:
    order = [
        "compensation_commitment", "refund_timeline", "unverified_logistics",
        "safety_or_complaint", "legal_or_media", "personal_data",
        "manual_request", "data_conflict", "other",
    ]
    return cast(list[RiskFlag], [item for item in order if item in set(flags)])


def _highest_service_risk(
    first: str,
    second: str,
) -> Literal["low", "medium", "high", "critical"]:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    if first not in order or second not in order:
        raise ValueError("模型返回未知风险等级")
    return cast(
        Literal["low", "medium", "high", "critical"],
        max((first, second), key=lambda item: order[item]),
    )


def _idempotency_conflict() -> ApiProblem:
    return ApiProblem(
        status_code=409,
        code="customer_service.idempotency_conflict",
        message="该幂等键已经用于另一个客服动作",
    )


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
