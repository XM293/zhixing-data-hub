from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext
from zhixing_api.data_models import (
    ApprovedMemory,
    ChatImportRun,
    ChatMessage,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    MemoryCandidate,
    MemoryReviewEvent,
    Principal,
    RoleTwinProfile,
)
from zhixing_api.database import Database
from zhixing_api.decision_schemas import MemoryCandidateView
from zhixing_api.errors import ApiProblem
from zhixing_api.memory_schemas import (
    ApprovedMemoryView,
    ChatImportListResponse,
    ChatImportRequest,
    ChatImportResponse,
    ChatImportRunView,
    ChatMessageView,
    MemoryLifecycleRequest,
    MemoryMutationResponse,
    MemoryReviewEventView,
    MemoryReviewRequest,
)

_CHAT_LINE = re.compile(
    r"^\[?(?P<timestamp>\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(?::\d{2})?)\]?\s+"
    r"(?P<sender>[^:：]{1,160})[:：]\s*(?P<content>.+)$"
)
_TOPIC_LINE = re.compile(r"^#{1,3}\s*(?:话题|topic)\s*[:：]\s*(?P<topic>.+)$", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|元|万|天|小时|倍|x)?", re.I)
_DECISION_CUES = (
    "必须",
    "应该",
    "以后",
    "优先",
    "不得",
    "不要",
    "先",
    "再",
    "原则",
    "要求",
    "决定",
    "倾向",
    "建议",
    "仍按",
)
_BUSINESS_TERMS = (
    "退款率",
    "广告roi",
    "roi",
    "库存",
    "预算",
    "补偿",
    "客服",
    "绩效",
    "考核",
    "履约",
)


@dataclass(slots=True)
class ParsedChatMessage:
    sent_at: datetime | None
    sender: str
    topic_key: str
    content: str
    raw_line: str


def import_chat_transcript(
    database: Database,
    actor: ActorContext,
    payload: ChatImportRequest,
) -> ChatImportResponse:
    now = datetime.now(UTC)
    content_hash = sha256(payload.content.strip().encode("utf-8")).hexdigest()
    messages = _parse_chat(payload.content, payload.timezone)
    if not messages:
        raise ApiProblem(
            status_code=422,
            code="memory.chat_format_unrecognized",
            message="未识别到聊天消息，请使用“[日期 时间] 姓名: 内容”格式",
        )

    with database.session() as session:
        profile = session.scalar(
            select(RoleTwinProfile).where(
                RoleTwinProfile.enterprise_id == actor.enterprise_id,
                RoleTwinProfile.twin_key == payload.twin_key,
            )
        )
        if profile is None:
            raise ApiProblem(
                status_code=404,
                code="memory.twin_not_found",
                message="未找到目标角色分身",
                details={"twin_key": payload.twin_key},
            )
        previous = session.scalar(
            select(ChatImportRun)
            .where(
                ChatImportRun.enterprise_id == actor.enterprise_id,
                ChatImportRun.twin_profile_id == profile.id,
                ChatImportRun.content_hash == content_hash,
                ChatImportRun.status.in_(("completed", "duplicate")),
            )
            .order_by(ChatImportRun.created_at)
        )
        if previous is not None:
            run = _new_chat_run(
                actor,
                profile,
                payload,
                content_hash=content_hash,
                status="duplicate",
                message_count=len(messages),
                topic_count=len({item.topic_key for item in messages}),
                candidate_count=0,
                participants=sorted({item.sender for item in messages}),
                started_at=_first_time(messages),
                ended_at=_last_time(messages),
                warnings=[
                    {
                        "code": "memory.duplicate_transcript",
                        "message": "相同聊天原件已经导入，本次未重复创建消息和候选",
                        "related_run_id": previous.id,
                    }
                ],
                now=now,
            )
            session.add(run)
            session.commit()
            return ChatImportResponse(
                duplicate=True,
                import_run=_chat_run_view(run, profile, actor.display_name),
                messages=[],
                candidates=[],
            )

        run_id = f"chat_import_{uuid4().hex}"
        stored_messages: list[ChatMessage] = []
        for ordinal, parsed in enumerate(messages, start=1):
            message = ChatMessage(
                id=f"chat_message_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                import_run_id=run_id,
                message_key=f"message-{ordinal:05d}",
                sent_at=parsed.sent_at,
                sender_name=parsed.sender,
                sender_ref=None,
                topic_key=parsed.topic_key,
                content=parsed.content,
                raw_payload={"line": parsed.raw_line},
                ordinal=ordinal,
            )
            stored_messages.append(message)

        warnings: list[dict[str, object]] = []
        candidates: list[MemoryCandidate] = []
        target_speakers = {
            item.strip().casefold() for item in payload.target_speakers if item.strip()
        }
        for message in stored_messages:
            if target_speakers and not any(
                target in message.sender_name.casefold() for target in target_speakers
            ):
                continue
            if not _is_memory_candidate(message.content):
                continue
            normalized = _normalize_memory(message.content)
            normalized_hash = sha256(normalized.encode("utf-8")).hexdigest()
            existing = session.scalar(
                select(MemoryCandidate).where(
                    MemoryCandidate.enterprise_id == actor.enterprise_id,
                    MemoryCandidate.twin_profile_id == profile.id,
                    MemoryCandidate.normalized_hash == normalized_hash,
                )
            )
            if existing is not None:
                warnings.append(
                    {
                        "code": "memory.duplicate_candidate",
                        "message": "消息与已有记忆候选重复，已保留原始消息但未重复创建候选",
                        "message_key": message.message_key,
                        "candidate_id": existing.id,
                    }
                )
                continue
            conflict_status, conflict_ref = _detect_policy_conflict(session, message.content)
            candidate = MemoryCandidate(
                id=f"memory_candidate_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                twin_profile_id=profile.id,
                candidate_key=f"chat-{normalized_hash[:24]}",
                category=_memory_category(message.content),
                content=message.content.strip(),
                source_type="chat-import",
                source_ref=f"{payload.source_filename} / {message.message_key}",
                normalized_hash=normalized_hash,
                confidence=_candidate_confidence(message.content),
                conflict_status=conflict_status,
                conflict_ref=conflict_ref,
                source_import_run_id=run_id,
                evidence_refs=[
                    {
                        "type": "chat-message",
                        "ref": message.id,
                        "excerpt": message.content,
                        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
                        "sender": message.sender_name,
                    }
                ],
                status="candidate",
                reviewer=None,
                review_reason=None,
                reviewed_at=None,
                effective_from=None,
                retired_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(candidate)
            candidates.append(candidate)

        run = ChatImportRun(
            id=run_id,
            enterprise_id=actor.enterprise_id,
            twin_profile_id=profile.id,
            actor_principal_id=actor.principal_id,
            request_id=actor.request_id,
            run_id=actor.run_id,
            source_filename=payload.source_filename,
            source_channel=payload.source_channel,
            content_hash=content_hash,
            status="completed",
            message_count=len(stored_messages),
            topic_count=len({item.topic_key for item in stored_messages}),
            candidate_count=len(candidates),
            participants=sorted({item.sender_name for item in stored_messages}),
            started_at=_first_time(messages),
            ended_at=_last_time(messages),
            warnings=warnings,
            created_at=now,
            finished_at=now,
        )
        session.add(run)
        session.add_all(stored_messages)
        session.commit()
        return ChatImportResponse(
            duplicate=False,
            import_run=_chat_run_view(run, profile, actor.display_name),
            messages=[_chat_message_view(item) for item in stored_messages],
            candidates=[_candidate_view(session, item, profile, None) for item in candidates],
        )


def list_chat_imports(
    database: Database,
    *,
    enterprise_id: str,
    limit: int,
) -> ChatImportListResponse:
    with database.session() as session:
        rows = session.execute(
            select(ChatImportRun, RoleTwinProfile, Principal)
            .join(RoleTwinProfile, RoleTwinProfile.id == ChatImportRun.twin_profile_id)
            .join(Principal, Principal.id == ChatImportRun.actor_principal_id)
            .where(ChatImportRun.enterprise_id == enterprise_id)
            .order_by(ChatImportRun.created_at.desc())
            .limit(limit)
        ).all()
    return ChatImportListResponse(
        status_counts=dict(Counter(run.status for run, _, _ in rows)),
        items=[
            _chat_run_view(run, profile, principal.display_name)
            for run, profile, principal in rows
        ],
        generated_at=datetime.now(UTC),
    )


def review_memory_candidate(
    database: Database,
    actor: ActorContext,
    *,
    candidate_id: str,
    payload: MemoryReviewRequest,
) -> MemoryMutationResponse:
    now = datetime.now(UTC)
    target_status = "approved" if payload.decision == "approve" else "rejected"
    event_type = "approved" if payload.decision == "approve" else "rejected"
    with database.session() as session:
        candidate, profile = _candidate_and_profile(session, actor, candidate_id)
        approved = _latest_approved(session, candidate.id)
        if candidate.status == target_status:
            return _mutation_response(
                session,
                candidate,
                profile,
                approved,
                _latest_event(session, candidate.id, event_type),
                idempotent=True,
            )
        if candidate.status != "candidate":
            raise _invalid_transition(candidate.status, target_status)

        if payload.decision == "approve":
            if candidate.conflict_status == "unverified":
                if payload.conflict_resolution != "verified_clear":
                    raise ApiProblem(
                        status_code=409,
                        code="memory.conflict_review_required",
                        message="待核验候选必须明确完成制度核验后才能批准",
                    )
                candidate.conflict_status = "clear"
                candidate.conflict_ref = None
            if candidate.conflict_status == "conflicted" and (
                payload.conflict_resolution != "retain_conflict"
            ):
                raise ApiProblem(
                    status_code=409,
                    code="memory.conflict_acknowledgement_required",
                    message="冲突候选只能保留为非激活历史记忆或直接拒绝",
                )
            version_number = int(
                session.scalar(
                    select(func.max(ApprovedMemory.version_number)).where(
                        ApprovedMemory.enterprise_id == actor.enterprise_id,
                        ApprovedMemory.memory_key == candidate.candidate_key,
                    )
                )
                or 0
            ) + 1
            approved = ApprovedMemory(
                id=f"approved_memory_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                twin_profile_id=candidate.twin_profile_id,
                candidate_id=candidate.id,
                memory_key=candidate.candidate_key,
                version_number=version_number,
                category=candidate.category,
                content=candidate.content,
                normalized_hash=candidate.normalized_hash,
                source_type=candidate.source_type,
                source_ref=candidate.source_ref,
                evidence_refs=candidate.evidence_refs,
                status="approved",
                approved_by_principal_id=actor.principal_id,
                approved_at=now,
                effective_from=None,
                effective_until=None,
                created_at=now,
            )
            session.add(approved)

        previous_status = candidate.status
        candidate.status = target_status
        candidate.reviewer = actor.display_name
        candidate.review_reason = payload.reason
        candidate.reviewed_at = now
        candidate.updated_at = now
        event = _new_event(
            actor,
            candidate,
            approved,
            event_type=event_type,
            from_status=previous_status,
            to_status=target_status,
            reason=payload.reason,
            now=now,
        )
        session.add(event)
        session.commit()
        return _mutation_response(
            session, candidate, profile, approved, event, idempotent=False
        )


def activate_memory(
    database: Database,
    actor: ActorContext,
    *,
    candidate_id: str,
    payload: MemoryLifecycleRequest,
) -> MemoryMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        candidate, profile = _candidate_and_profile(session, actor, candidate_id)
        approved = _latest_approved(session, candidate.id)
        if candidate.status == "active":
            return _mutation_response(
                session,
                candidate,
                profile,
                approved,
                _latest_event(session, candidate.id, "activated"),
                idempotent=True,
            )
        if candidate.status != "approved" or approved is None:
            raise _invalid_transition(candidate.status, "active")
        if candidate.conflict_status != "clear":
            raise ApiProblem(
                status_code=409,
                code="memory.conflicted_candidate_not_activatable",
                message="与正式制度冲突的记忆不得进入分身推理上下文",
                details={"conflict_ref": candidate.conflict_ref or "未核验"},
            )
        previous_status = candidate.status
        candidate.status = "active"
        candidate.effective_from = now
        candidate.updated_at = now
        approved.status = "active"
        approved.effective_from = now
        event = _new_event(
            actor,
            candidate,
            approved,
            event_type="activated",
            from_status=previous_status,
            to_status="active",
            reason=payload.reason,
            now=now,
        )
        session.add(event)
        session.commit()
        return _mutation_response(
            session, candidate, profile, approved, event, idempotent=False
        )


def retire_memory(
    database: Database,
    actor: ActorContext,
    *,
    candidate_id: str,
    payload: MemoryLifecycleRequest,
) -> MemoryMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        candidate, profile = _candidate_and_profile(session, actor, candidate_id)
        approved = _latest_approved(session, candidate.id)
        if candidate.status == "retired":
            return _mutation_response(
                session,
                candidate,
                profile,
                approved,
                _latest_event(session, candidate.id, "retired"),
                idempotent=True,
            )
        if candidate.status != "active" or approved is None:
            raise _invalid_transition(candidate.status, "retired")
        previous_status = candidate.status
        candidate.status = "retired"
        candidate.retired_at = now
        candidate.updated_at = now
        approved.status = "retired"
        approved.effective_until = now
        event = _new_event(
            actor,
            candidate,
            approved,
            event_type="retired",
            from_status=previous_status,
            to_status="retired",
            reason=payload.reason,
            now=now,
        )
        session.add(event)
        session.commit()
        return _mutation_response(
            session, candidate, profile, approved, event, idempotent=False
        )


def _new_chat_run(
    actor: ActorContext,
    profile: RoleTwinProfile,
    payload: ChatImportRequest,
    *,
    content_hash: str,
    status: str,
    message_count: int,
    topic_count: int,
    candidate_count: int,
    participants: list[str],
    started_at: datetime | None,
    ended_at: datetime | None,
    warnings: list[dict[str, object]],
    now: datetime,
) -> ChatImportRun:
    return ChatImportRun(
        id=f"chat_import_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        twin_profile_id=profile.id,
        actor_principal_id=actor.principal_id,
        request_id=actor.request_id,
        run_id=actor.run_id,
        source_filename=payload.source_filename,
        source_channel=payload.source_channel,
        content_hash=content_hash,
        status=status,
        message_count=message_count,
        topic_count=topic_count,
        candidate_count=candidate_count,
        participants=participants,
        started_at=started_at,
        ended_at=ended_at,
        warnings=warnings,
        created_at=now,
        finished_at=now,
    )


def _parse_chat(content: str, timezone_name: str) -> list[ParsedChatMessage]:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ApiProblem(
            status_code=422,
            code="memory.timezone_invalid",
            message="聊天记录时区无效",
            details={"timezone": timezone_name},
        ) from exc
    topic_key = "general"
    parsed: list[ParsedChatMessage] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        topic_match = _TOPIC_LINE.match(line)
        if topic_match:
            topic_key = _topic_key(topic_match.group("topic"))
            continue
        match = _CHAT_LINE.match(line)
        if match:
            timestamp_text = match.group("timestamp").replace("/", "-")
            timestamp = datetime.fromisoformat(timestamp_text)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone)
            parsed.append(
                ParsedChatMessage(
                    sent_at=timestamp.astimezone(UTC),
                    sender=match.group("sender").strip(),
                    topic_key=topic_key,
                    content=match.group("content").strip(),
                    raw_line=raw_line,
                )
            )
            continue
        if parsed:
            parsed[-1].content = f"{parsed[-1].content}\n{line}"
            parsed[-1].raw_line = f"{parsed[-1].raw_line}\n{raw_line}"
    return parsed


def _detect_policy_conflict(session: Session, content: str) -> tuple[str, str | None]:
    folded = content.casefold().replace(" ", "")
    if "正式制度为准" in folded or "现行制度为准" in folded:
        return "clear", None
    terms = {term for term in _BUSINESS_TERMS if term in folded}
    if not terms:
        return "unverified", None
    candidate_numbers = {item.replace(" ", "").casefold() for item in _NUMBER.findall(content)}
    rows = session.execute(
        select(KnowledgeChunk, KnowledgeVersion, KnowledgeDocument)
        .join(KnowledgeVersion, KnowledgeVersion.id == KnowledgeChunk.version_id)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
        .where(
            KnowledgeDocument.document_type == "policy",
            KnowledgeVersion.status.in_(("active", "published", "scheduled")),
        )
        .order_by(KnowledgeVersion.version_number.desc())
    ).all()
    for chunk, version, document in rows:
        chunk_text = chunk.content.casefold().replace(" ", "")
        if not any(term in chunk_text for term in terms):
            continue
        policy_numbers = {
            item.replace(" ", "").casefold() for item in _NUMBER.findall(chunk.content)
        }
        if candidate_numbers and policy_numbers and not candidate_numbers.issubset(policy_numbers):
            return (
                "conflicted",
                f"{document.title} {version.version_label} · {chunk.locator}",
            )
    return "unverified", None


def _candidate_and_profile(
    session: Session,
    actor: ActorContext,
    candidate_id: str,
) -> tuple[MemoryCandidate, RoleTwinProfile]:
    row = session.execute(
        select(MemoryCandidate, RoleTwinProfile)
        .join(RoleTwinProfile, RoleTwinProfile.id == MemoryCandidate.twin_profile_id)
        .where(
            MemoryCandidate.id == candidate_id,
            MemoryCandidate.enterprise_id == actor.enterprise_id,
        )
    ).first()
    if row is None:
        raise ApiProblem(
            status_code=404,
            code="memory.candidate_not_found",
            message="未找到记忆候选",
            details={"candidate_id": candidate_id},
        )
    return row[0], row[1]


def _latest_approved(session: Session, candidate_id: str) -> ApprovedMemory | None:
    return session.scalar(
        select(ApprovedMemory)
        .where(ApprovedMemory.candidate_id == candidate_id)
        .order_by(ApprovedMemory.version_number.desc())
    )


def _latest_event(
    session: Session,
    candidate_id: str,
    event_type: str,
) -> MemoryReviewEvent:
    event = session.scalar(
        select(MemoryReviewEvent)
        .where(
            MemoryReviewEvent.candidate_id == candidate_id,
            MemoryReviewEvent.event_type == event_type,
        )
        .order_by(MemoryReviewEvent.occurred_at.desc())
    )
    if event is None:
        raise ApiProblem(
            status_code=409,
            code="memory.lifecycle_event_missing",
            message="记忆状态存在但缺少对应生命周期事件",
        )
    return event


def _new_event(
    actor: ActorContext,
    candidate: MemoryCandidate,
    approved: ApprovedMemory | None,
    *,
    event_type: str,
    from_status: str,
    to_status: str,
    reason: str,
    now: datetime,
) -> MemoryReviewEvent:
    return MemoryReviewEvent(
        id=f"memory_event_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        candidate_id=candidate.id,
        approved_memory_id=approved.id if approved else None,
        actor_principal_id=actor.principal_id,
        actor_snapshot=actor.snapshot(),
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        request_id=actor.request_id,
        run_id=actor.run_id,
        occurred_at=now,
    )


def _mutation_response(
    session: Session,
    candidate: MemoryCandidate,
    profile: RoleTwinProfile,
    approved: ApprovedMemory | None,
    event: MemoryReviewEvent,
    *,
    idempotent: bool,
) -> MemoryMutationResponse:
    approved_by = ""
    if approved is not None:
        principal = session.get(Principal, approved.approved_by_principal_id)
        approved_by = principal.display_name if principal else approved.approved_by_principal_id
    actor_name = str(event.actor_snapshot.get("display_name") or event.actor_principal_id)
    return MemoryMutationResponse(
        idempotent=idempotent,
        candidate=_candidate_view(session, candidate, profile, approved),
        approved_memory=(
            _approved_view(approved, profile, approved_by) if approved is not None else None
        ),
        event=MemoryReviewEventView(
            id=event.id,
            event_type=event.event_type,  # type: ignore[arg-type]
            from_status=event.from_status,
            to_status=event.to_status,
            actor_name=actor_name,
            reason=event.reason,
            request_id=event.request_id,
            run_id=event.run_id,
            occurred_at=event.occurred_at,
        ),
    )


def _candidate_view(
    session: Session,
    candidate: MemoryCandidate,
    profile: RoleTwinProfile,
    approved: ApprovedMemory | None = None,
) -> MemoryCandidateView:
    approved = approved if approved is not None else _latest_approved(session, candidate.id)
    return MemoryCandidateView(
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
        approved_memory_id=approved.id if approved else None,
        approved_memory_status=approved.status if approved else None,
        memory_version=approved.version_number if approved else None,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def _approved_view(
    approved: ApprovedMemory,
    profile: RoleTwinProfile,
    approved_by: str,
) -> ApprovedMemoryView:
    return ApprovedMemoryView(
        id=approved.id,
        candidate_id=approved.candidate_id,
        memory_key=approved.memory_key,
        twin_key=profile.twin_key,
        version_number=approved.version_number,
        category=approved.category,
        content=approved.content,
        source_type=approved.source_type,
        source_ref=approved.source_ref,
        evidence_refs=approved.evidence_refs,
        status=approved.status,  # type: ignore[arg-type]
        approved_by=approved_by,
        approved_at=approved.approved_at,
        effective_from=approved.effective_from,
        effective_until=approved.effective_until,
    )


def _chat_run_view(
    run: ChatImportRun,
    profile: RoleTwinProfile,
    actor_name: str,
) -> ChatImportRunView:
    return ChatImportRunView(
        id=run.id,
        twin_key=profile.twin_key,
        twin_name=profile.display_name,
        actor_name=actor_name,
        source_filename=run.source_filename,
        source_channel=run.source_channel,
        content_hash=run.content_hash,
        status=run.status,  # type: ignore[arg-type]
        message_count=run.message_count,
        topic_count=run.topic_count,
        candidate_count=run.candidate_count,
        participants=run.participants,
        started_at=run.started_at,
        ended_at=run.ended_at,
        warnings=run.warnings,
        request_id=run.request_id,
        run_id=run.run_id,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def _chat_message_view(message: ChatMessage) -> ChatMessageView:
    return ChatMessageView(
        id=message.id,
        message_key=message.message_key,
        sent_at=message.sent_at,
        sender_name=message.sender_name,
        topic_key=message.topic_key,
        content=message.content,
        ordinal=message.ordinal,
    )


def _invalid_transition(current: str, target: str) -> ApiProblem:
    return ApiProblem(
        status_code=409,
        code="memory.invalid_transition",
        message="当前记忆状态不能执行该操作",
        details={"current_status": current, "target_status": target},
    )


def _normalize_memory(content: str) -> str:
    return re.sub(r"[\W_]+", "", content, flags=re.UNICODE).casefold()


def _is_memory_candidate(content: str) -> bool:
    compact = content.strip()
    return len(compact) >= 8 and any(cue in compact for cue in _DECISION_CUES)


def _candidate_confidence(content: str) -> float:
    cue_count = sum(cue in content for cue in _DECISION_CUES)
    return min(0.94, 0.66 + cue_count * 0.07)


def _memory_category(content: str) -> str:
    if any(term in content for term in ("先给结论", "表达", "汇报", "沟通")):
        return "communication-style"
    if any(term in content for term in ("必须", "不得", "规则", "制度", "要求")):
        return "decision-rule"
    if any(term in content for term in ("优先", "倾向", "建议")):
        return "management-preference"
    return "management-principle"


def _topic_key(topic: str) -> str:
    compact = re.sub(r"\s+", "-", topic.strip()).casefold()
    return f"topic-{sha256(compact.encode('utf-8')).hexdigest()[:12]}"


def _first_time(messages: list[ParsedChatMessage]) -> datetime | None:
    values = [item.sent_at for item in messages if item.sent_at is not None]
    return min(values) if values else None


def _last_time(messages: list[ParsedChatMessage]) -> datetime | None:
    values = [item.sent_at for item in messages if item.sent_at is not None]
    return max(values) if values else None
