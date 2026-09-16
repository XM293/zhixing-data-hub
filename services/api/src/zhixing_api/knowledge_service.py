from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from zhixing_agent_runtime import (
    AgentActor,
    AgentRunCancelled,
    AgentRunEvent,
    AgentRunSpec,
    AgentRuntime,
    AgentRuntimeError,
    RuntimeCredentials,
)

from zhixing_api.actor_context import ActorContext, resolve_enterprise_id
from zhixing_api.agent_context_service import build_metric_context
from zhixing_api.agent_runtime_service import (
    append_runtime_event,
    begin_runtime_turn,
    create_runtime_session,
    mark_runtime_session_failed,
    sanitize_runtime_error,
    validate_runtime_scope_for_resume,
)
from zhixing_api.ai_provider import AICompletion, AIProviderError, ResponsesAIProvider
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    AgentRunContextItem,
    AgentRunEvidence,
    AgentRuntimeSession,
    ApprovedMemory,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionRun,
    KnowledgeLifecycleEvent,
    KnowledgeVersion,
    Principal,
    RoleTwinProfile,
    TwinActor,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.knowledge_schemas import (
    EvidenceSearchResponse,
    EvidenceView,
    KnowledgeChunkView,
    KnowledgeConflictView,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentView,
    KnowledgeIngestionListResponse,
    KnowledgeIngestionRequest,
    KnowledgeIngestionResponse,
    KnowledgeIngestionRunView,
    KnowledgeLifecycleResponse,
    KnowledgeVersionDetailResponse,
    KnowledgeVersionView,
    MemoryContextView,
    MetricContextView,
    PageView,
    PolicyPublishRequest,
    PolicyRetireRequest,
    RoleTwinProfileView,
    TwinAnswerPayload,
    TwinAnswerResponse,
)
from zhixing_api.knowledge_text import TextChunk, chunk_document, content_hash, lexical_terms
from zhixing_api.mcp_schemas import McpSessionCreateRequest, McpSessionRevokeRequest
from zhixing_api.mcp_session_service import create_mcp_session, revoke_mcp_session
from zhixing_api.role_twin_service import current_twin_version
from zhixing_api.scope_context import build_scope_context

RULE_TOKEN_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|元|万元|天|日|月|年|小时|分钟|x|倍)",
    re.IGNORECASE,
)


def list_documents(
    database: Database,
    *,
    enterprise_id: str | None = None,
    query: str | None,
    status: str | None,
    offset: int,
    limit: int,
) -> KnowledgeDocumentListResponse:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    conditions = [KnowledgeDocument.enterprise_id == enterprise_id]
    if status:
        conditions.append(KnowledgeDocument.status == status)
    if query:
        pattern = f"%{query.strip()}%"
        conditions.append(
            or_(
                KnowledgeDocument.title.ilike(pattern),
                KnowledgeDocument.document_key.ilike(pattern),
                KnowledgeDocument.owner.ilike(pattern),
            )
        )
    with database.session() as session:
        total = int(
            session.scalar(select(func.count(KnowledgeDocument.id)).where(*conditions)) or 0
        )
        documents = list(
            session.scalars(
                select(KnowledgeDocument)
                .where(*conditions)
                .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id)
                .offset(offset)
                .limit(limit)
            )
        )
        document_ids = [item.id for item in documents]
        versions = (
            list(
                session.scalars(
                    select(KnowledgeVersion)
                    .where(KnowledgeVersion.document_id.in_(document_ids))
                    .order_by(
                        KnowledgeVersion.document_id,
                        KnowledgeVersion.version_number.desc(),
                    )
                )
            )
            if document_ids
            else []
        )
        version_ids = [item.id for item in versions]
        chunk_rows = (
            session.execute(
                select(KnowledgeChunk.version_id, func.count(KnowledgeChunk.id))
                .where(KnowledgeChunk.version_id.in_(version_ids))
                .group_by(KnowledgeChunk.version_id)
            ).all()
            if version_ids
            else []
        )
        status_rows = session.execute(
            select(KnowledgeDocument.status, func.count(KnowledgeDocument.id))
            .where(KnowledgeDocument.enterprise_id == enterprise_id)
            .group_by(KnowledgeDocument.status)
        ).all()
        total_versions = int(
            session.scalar(
                select(func.count(KnowledgeVersion.id))
                .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
                .where(KnowledgeDocument.enterprise_id == enterprise_id)
            )
            or 0
        )
        total_chunks = int(
            session.scalar(
                select(func.count(KnowledgeChunk.id))
                .join(KnowledgeVersion, KnowledgeVersion.id == KnowledgeChunk.version_id)
                .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
                .where(KnowledgeDocument.enterprise_id == enterprise_id)
            )
            or 0
        )

    chunk_counts = {str(version_id): int(count) for version_id, count in chunk_rows}
    by_document: dict[str, list[KnowledgeVersion]] = {}
    for version in versions:
        by_document.setdefault(version.document_id, []).append(version)
    return KnowledgeDocumentListResponse(
        page=PageView(offset=offset, limit=limit, total=total),
        status_counts={str(key): int(count) for key, count in status_rows},
        version_count=total_versions,
        chunk_count=total_chunks,
        items=[
            KnowledgeDocumentView(
                id=document.id,
                key=document.document_key,
                title=document.title,
                document_type=document.document_type,
                knowledge_space=document.knowledge_space,
                source_type=document.source_type,
                owner=document.owner,
                tags=document.tags,
                status=document.status,
                content_hash=document.content_hash,
                created_at=document.created_at,
                updated_at=document.updated_at,
                versions=[
                    KnowledgeVersionView(
                        id=version.id,
                        version_label=version.version_label,
                        version_number=version.version_number,
                        status=version.status,
                        effective_from=version.effective_from,
                        effective_until=version.effective_until,
                        published_at=version.published_at,
                        change_summary=version.change_summary,
                        chunk_count=chunk_counts.get(version.id, 0),
                    )
                    for version in by_document.get(document.id, [])
                ],
            )
            for document in documents
        ],
        generated_at=datetime.now(UTC),
    )


def ingest_document(
    database: Database,
    actor: ActorContext,
    payload: KnowledgeIngestionRequest,
) -> KnowledgeIngestionResponse:
    now = datetime.now(UTC)
    normalized_content = payload.content.strip()
    digest = content_hash(normalized_content)
    parsed_chunks = chunk_document(normalized_content)
    with database.session() as session:
        duplicate_row = session.execute(
            select(KnowledgeVersion, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
            .where(
                KnowledgeDocument.enterprise_id == actor.enterprise_id,
                KnowledgeVersion.content_hash == digest,
            )
            .order_by(KnowledgeVersion.created_at.desc())
        ).first()
        if duplicate_row is not None:
            duplicate_version, duplicate_document = duplicate_row
            run = KnowledgeIngestionRun(
                id=f"knowledge_ingestion_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                document_id=duplicate_document.id,
                version_id=duplicate_version.id,
                actor_principal_id=actor.principal_id,
                request_id=actor.request_id,
                run_id=actor.run_id,
                source_filename=payload.source_filename,
                source_type="uploaded-text",
                content_hash=digest,
                parser_provider="heading-text-v1",
                status="duplicate",
                chunk_count=int(
                    session.scalar(
                        select(func.count(KnowledgeChunk.id)).where(
                            KnowledgeChunk.version_id == duplicate_version.id
                        )
                    )
                    or 0
                ),
                warnings=[],
                error_code=None,
                created_at=now,
                finished_at=now,
            )
            session.add(run)
            session.commit()
            return _ingestion_response(
                session,
                run=run,
                document=duplicate_document,
                version=duplicate_version,
                actor_name=actor.display_name,
                duplicate=True,
            )

        document = session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.enterprise_id == actor.enterprise_id,
                KnowledgeDocument.document_key == payload.document_key,
            )
        )
        if document is None:
            document = KnowledgeDocument(
                id=f"knowledge_doc_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                document_key=payload.document_key,
                title=payload.title,
                document_type=payload.document_type,
                knowledge_space=payload.knowledge_space,
                source_type="uploaded-text",
                source_uri=payload.source_filename,
                content_hash=digest,
                owner=payload.owner,
                tags=_normalize_tags(payload.tags),
                status="active",
                created_at=now,
                updated_at=now,
            )
            session.add(document)
            session.flush()
        else:
            same_label = session.scalar(
                select(KnowledgeVersion).where(
                    KnowledgeVersion.document_id == document.id,
                    KnowledgeVersion.version_label == payload.version_label,
                )
            )
            if same_label is not None:
                raise ApiProblem(
                    status_code=409,
                    code="knowledge.version_label_conflict",
                    message="该文档已存在同名但内容不同的版本",
                    details={
                        "document_key": document.document_key,
                        "version_label": payload.version_label,
                    },
                )
            document.title = payload.title
            document.document_type = payload.document_type
            document.knowledge_space = payload.knowledge_space
            document.source_type = "uploaded-text"
            document.source_uri = payload.source_filename
            document.content_hash = digest
            document.owner = payload.owner
            document.tags = _normalize_tags(payload.tags)
            document.updated_at = now

        max_version = int(
            session.scalar(
                select(func.max(KnowledgeVersion.version_number)).where(
                    KnowledgeVersion.document_id == document.id
                )
            )
            or 0
        )
        conflicts = _detect_conflicts(session, document.id, parsed_chunks)
        version = KnowledgeVersion(
            id=f"knowledge_ver_{uuid4().hex}",
            document_id=document.id,
            version_label=payload.version_label,
            version_number=max_version + 1,
            status="draft",
            effective_from=None,
            effective_until=None,
            published_at=None,
            content=normalized_content,
            content_hash=digest,
            change_summary=payload.change_summary,
            created_at=now,
        )
        session.add(version)
        session.flush()
        for sequence, chunk in enumerate(parsed_chunks, start=1):
            session.add(
                KnowledgeChunk(
                    id=f"knowledge_chunk_{uuid4().hex}",
                    version_id=version.id,
                    chunk_key=f"{payload.document_key}:{payload.version_label}:{sequence:03d}",
                    sequence=sequence,
                    heading=chunk.heading,
                    content=chunk.content,
                    locator=chunk.locator,
                    token_estimate=chunk.token_estimate,
                    metadata_json={
                        "source_filename": payload.source_filename,
                        "parser_provider": "heading-text-v1",
                    },
                    index_status="indexed",
                    created_at=now,
                )
            )
        warning_payload = [item.model_dump(mode="json") for item in conflicts]
        run = KnowledgeIngestionRun(
            id=f"knowledge_ingestion_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            document_id=document.id,
            version_id=version.id,
            actor_principal_id=actor.principal_id,
            request_id=actor.request_id,
            run_id=actor.run_id,
            source_filename=payload.source_filename,
            source_type="uploaded-text",
            content_hash=digest,
            parser_provider="heading-text-v1",
            status="completed",
            chunk_count=len(parsed_chunks),
            warnings=warning_payload,
            error_code=None,
            created_at=now,
            finished_at=now,
        )
        session.add(run)
        session.add(
            _lifecycle_event(
                actor,
                document_id=document.id,
                version_id=version.id,
                event_type="ingested",
                from_status=None,
                to_status="draft",
                reason=payload.change_summary,
                effective_at=None,
                occurred_at=now,
            )
        )
        session.commit()
        return _ingestion_response(
            session,
            run=run,
            document=document,
            version=version,
            actor_name=actor.display_name,
            duplicate=False,
        )


def list_ingestion_runs(
    database: Database,
    *,
    enterprise_id: str,
    limit: int,
) -> KnowledgeIngestionListResponse:
    with database.session() as session:
        rows = session.execute(
            select(
                KnowledgeIngestionRun,
                KnowledgeDocument,
                KnowledgeVersion,
                Principal.display_name,
            )
            .outerjoin(KnowledgeDocument, KnowledgeDocument.id == KnowledgeIngestionRun.document_id)
            .outerjoin(KnowledgeVersion, KnowledgeVersion.id == KnowledgeIngestionRun.version_id)
            .join(Principal, Principal.id == KnowledgeIngestionRun.actor_principal_id)
            .where(KnowledgeIngestionRun.enterprise_id == enterprise_id)
            .order_by(KnowledgeIngestionRun.created_at.desc())
            .limit(limit)
        ).all()
        status_rows = session.execute(
            select(KnowledgeIngestionRun.status, func.count(KnowledgeIngestionRun.id))
            .where(KnowledgeIngestionRun.enterprise_id == enterprise_id)
            .group_by(KnowledgeIngestionRun.status)
        ).all()
    return KnowledgeIngestionListResponse(
        stats={str(key): int(count) for key, count in status_rows},
        items=[
            _ingestion_run_view(
                run,
                document=document,
                version=version,
                actor_name=str(actor_name),
            )
            for run, document, version, actor_name in rows
        ],
        generated_at=datetime.now(UTC),
    )


def read_version(
    database: Database,
    *,
    enterprise_id: str,
    version_id: str,
) -> KnowledgeVersionDetailResponse:
    with database.session() as session:
        row = session.execute(
            select(KnowledgeVersion, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
            .where(
                KnowledgeDocument.enterprise_id == enterprise_id,
                KnowledgeVersion.id == version_id,
            )
        ).first()
        if row is None:
            raise ApiProblem(
                status_code=404,
                code="knowledge.version_not_found",
                message="没有找到指定知识版本",
            )
        version, document = row
        return _version_detail(session, document, version)


def read_effective_policy(
    database: Database,
    *,
    enterprise_id: str,
    document_key: str,
    as_of: datetime,
) -> KnowledgeVersionDetailResponse:
    effective_at = _as_utc(as_of)
    with database.session() as session:
        row = session.execute(
            select(KnowledgeVersion, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
            .where(
                KnowledgeDocument.enterprise_id == enterprise_id,
                KnowledgeDocument.document_key == document_key,
                KnowledgeDocument.document_type == "policy",
                KnowledgeVersion.status.in_(("active", "published", "scheduled")),
                KnowledgeVersion.effective_from.is_not(None),
                KnowledgeVersion.effective_from <= effective_at,
                or_(
                    KnowledgeVersion.effective_until.is_(None),
                    KnowledgeVersion.effective_until > effective_at,
                ),
            )
            .order_by(KnowledgeVersion.version_number.desc())
        ).first()
        if row is None:
            raise ApiProblem(
                status_code=404,
                code="knowledge.effective_version_not_found",
                message="指定时间没有生效的制度版本",
                details={"document_key": document_key, "as_of": effective_at.isoformat()},
            )
        version, document = row
        return _version_detail(session, document, version, resolved_at=effective_at)


def publish_policy_version(
    database: Database,
    actor: ActorContext,
    *,
    version_id: str,
    payload: PolicyPublishRequest,
) -> KnowledgeLifecycleResponse:
    now = datetime.now(UTC)
    effective_from = _as_utc(payload.effective_from)
    with database.session() as session:
        version, document = _get_version_document(session, actor.enterprise_id, version_id)
        if document.document_type != "policy":
            raise ApiProblem(
                status_code=409,
                code="knowledge.not_policy",
                message="只有制度类型的文档可以进入发布生命周期",
            )
        if version.status in {"active", "published"} and _same_instant(
            version.effective_from, effective_from
        ):
            event = session.scalar(
                select(KnowledgeLifecycleEvent)
                .where(
                    KnowledgeLifecycleEvent.version_id == version.id,
                    KnowledgeLifecycleEvent.event_type == "published",
                )
                .order_by(KnowledgeLifecycleEvent.occurred_at.desc())
            )
            return _lifecycle_response(
                document,
                version,
                event_id=event.id if event else "existing-publication",
                event_type="published",
                idempotent=True,
                occurred_at=event.occurred_at if event else version.published_at or now,
                chunk_count=_chunk_count(session, version.id),
            )
        if version.status != "draft":
            raise ApiProblem(
                status_code=409,
                code="knowledge.version_not_publishable",
                message="只有草稿版本可以发布",
                details={"status": version.status},
            )
        later_version = session.scalar(
            select(KnowledgeVersion).where(
                KnowledgeVersion.document_id == document.id,
                KnowledgeVersion.version_number > version.version_number,
                KnowledgeVersion.status.in_(("active", "published", "scheduled")),
            )
        )
        if later_version is not None:
            raise ApiProblem(
                status_code=409,
                code="knowledge.newer_version_already_published",
                message="该草稿之后已有生效或已发布版本",
                details={"newer_version": later_version.version_label},
            )
        previous_versions = list(
            session.scalars(
                select(KnowledgeVersion).where(
                    KnowledgeVersion.document_id == document.id,
                    KnowledgeVersion.id != version.id,
                    KnowledgeVersion.status.in_(("active", "published", "scheduled")),
                )
            )
        )
        for previous in previous_versions:
            previous_start = _coerce_utc(previous.effective_from)
            previous_end = _coerce_utc(previous.effective_until)
            if previous_start is None or previous_start >= effective_from:
                continue
            if previous_end is None or previous_end > effective_from:
                previous.effective_until = effective_from
            if effective_from <= now:
                previous.status = "archived"
        from_status = version.status
        version.status = "active" if effective_from <= now else "published"
        version.effective_from = effective_from
        version.effective_until = None
        version.published_at = now
        document.status = "active"
        document.content_hash = version.content_hash
        document.updated_at = now
        event = _lifecycle_event(
            actor,
            document_id=document.id,
            version_id=version.id,
            event_type="published",
            from_status=from_status,
            to_status=version.status,
            reason=payload.reason,
            effective_at=effective_from,
            occurred_at=now,
        )
        session.add(event)
        session.commit()
        return _lifecycle_response(
            document,
            version,
            event_id=event.id,
            event_type="published",
            idempotent=False,
            occurred_at=now,
            chunk_count=_chunk_count(session, version.id),
        )


def retire_policy_version(
    database: Database,
    actor: ActorContext,
    *,
    version_id: str,
    payload: PolicyRetireRequest,
) -> KnowledgeLifecycleResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        version, document = _get_version_document(session, actor.enterprise_id, version_id)
        if document.document_type != "policy":
            raise ApiProblem(
                status_code=409,
                code="knowledge.not_policy",
                message="只有制度版本可以退役",
            )
        if version.status == "archived":
            event = session.scalar(
                select(KnowledgeLifecycleEvent)
                .where(
                    KnowledgeLifecycleEvent.version_id == version.id,
                    KnowledgeLifecycleEvent.event_type == "retired",
                )
                .order_by(KnowledgeLifecycleEvent.occurred_at.desc())
            )
            return _lifecycle_response(
                document,
                version,
                event_id=event.id if event else "existing-retirement",
                event_type="retired",
                idempotent=True,
                occurred_at=event.occurred_at if event else version.effective_until or now,
                chunk_count=_chunk_count(session, version.id),
            )
        if version.status not in {"active", "published", "scheduled"}:
            raise ApiProblem(
                status_code=409,
                code="knowledge.version_not_retirable",
                message="该版本当前不能退役",
                details={"status": version.status},
            )
        from_status = version.status
        version.status = "archived"
        version.effective_until = now
        document.updated_at = now
        event = _lifecycle_event(
            actor,
            document_id=document.id,
            version_id=version.id,
            event_type="retired",
            from_status=from_status,
            to_status="archived",
            reason=payload.reason,
            effective_at=now,
            occurred_at=now,
        )
        session.add(event)
        session.commit()
        return _lifecycle_response(
            document,
            version,
            event_id=event.id,
            event_type="retired",
            idempotent=False,
            occurred_at=now,
            chunk_count=_chunk_count(session, version.id),
        )


def _ingestion_response(
    session: Session,
    *,
    run: KnowledgeIngestionRun,
    document: KnowledgeDocument,
    version: KnowledgeVersion,
    actor_name: str,
    duplicate: bool,
) -> KnowledgeIngestionResponse:
    return KnowledgeIngestionResponse(
        duplicate=duplicate,
        document=_document_view(session, document),
        version=_version_view(version, _chunk_count(session, version.id)),
        ingestion_run=_ingestion_run_view(
            run,
            document=document,
            version=version,
            actor_name=actor_name,
        ),
    )


def _ingestion_run_view(
    run: KnowledgeIngestionRun,
    *,
    document: KnowledgeDocument | None,
    version: KnowledgeVersion | None,
    actor_name: str,
) -> KnowledgeIngestionRunView:
    return KnowledgeIngestionRunView(
        id=run.id,
        document_key=document.document_key if document else None,
        document_title=document.title if document else None,
        version_id=version.id if version else None,
        version_label=version.version_label if version else None,
        actor_name=actor_name,
        source_filename=run.source_filename,
        content_hash=run.content_hash,
        parser_provider=run.parser_provider,
        status=cast(Literal["completed", "duplicate", "failed"], run.status),
        chunk_count=run.chunk_count,
        warnings=[KnowledgeConflictView.model_validate(item) for item in run.warnings],
        error_code=run.error_code,
        request_id=run.request_id,
        run_id=run.run_id,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def _version_detail(
    session: Session,
    document: KnowledgeDocument,
    version: KnowledgeVersion,
    *,
    resolved_at: datetime | None = None,
) -> KnowledgeVersionDetailResponse:
    chunks = list(
        session.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.version_id == version.id)
            .order_by(KnowledgeChunk.sequence)
        )
    )
    events = list(
        session.scalars(
            select(KnowledgeLifecycleEvent)
            .where(KnowledgeLifecycleEvent.version_id == version.id)
            .order_by(KnowledgeLifecycleEvent.occurred_at.desc())
        )
    )
    return KnowledgeVersionDetailResponse(
        document=_document_view(session, document),
        version=_version_view(version, len(chunks)),
        content=version.content,
        chunks=[
            KnowledgeChunkView(
                id=chunk.id,
                chunk_key=chunk.chunk_key,
                sequence=chunk.sequence,
                heading=chunk.heading,
                locator=chunk.locator,
                content=chunk.content,
                token_estimate=chunk.token_estimate,
                index_status=chunk.index_status,
            )
            for chunk in chunks
        ],
        lifecycle_events=[
            {
                "id": event.id,
                "event_type": event.event_type,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "reason": event.reason,
                "actor_principal_id": event.actor_principal_id,
                "effective_at": event.effective_at.isoformat() if event.effective_at else None,
                "request_id": event.request_id,
                "run_id": event.run_id,
                "occurred_at": event.occurred_at.isoformat(),
            }
            for event in events
        ],
        resolved_at=resolved_at or datetime.now(UTC),
    )


def _document_view(session: Session, document: KnowledgeDocument) -> KnowledgeDocumentView:
    versions = list(
        session.scalars(
            select(KnowledgeVersion)
            .where(KnowledgeVersion.document_id == document.id)
            .order_by(KnowledgeVersion.version_number.desc())
        )
    )
    counts = {
        str(version_id): int(count)
        for version_id, count in session.execute(
            select(KnowledgeChunk.version_id, func.count(KnowledgeChunk.id))
            .where(KnowledgeChunk.version_id.in_([version.id for version in versions]))
            .group_by(KnowledgeChunk.version_id)
        ).all()
    } if versions else {}
    return KnowledgeDocumentView(
        id=document.id,
        key=document.document_key,
        title=document.title,
        document_type=document.document_type,
        knowledge_space=document.knowledge_space,
        source_type=document.source_type,
        owner=document.owner,
        tags=document.tags,
        status=document.status,
        content_hash=document.content_hash,
        created_at=document.created_at,
        updated_at=document.updated_at,
        versions=[_version_view(version, counts.get(version.id, 0)) for version in versions],
    )


def _version_view(version: KnowledgeVersion, chunk_count: int) -> KnowledgeVersionView:
    return KnowledgeVersionView(
        id=version.id,
        version_label=version.version_label,
        version_number=version.version_number,
        status=version.status,
        effective_from=version.effective_from,
        effective_until=version.effective_until,
        published_at=version.published_at,
        change_summary=version.change_summary,
        chunk_count=chunk_count,
    )


def _detect_conflicts(
    session: Session,
    document_id: str,
    incoming_chunks: list[TextChunk],
) -> list[KnowledgeConflictView]:
    rows = session.execute(
        select(KnowledgeChunk, KnowledgeVersion)
        .join(KnowledgeVersion, KnowledgeVersion.id == KnowledgeChunk.version_id)
        .where(
            KnowledgeVersion.document_id == document_id,
            KnowledgeVersion.status.in_(("draft", "active", "published", "scheduled")),
        )
        .order_by(KnowledgeVersion.version_number.desc(), KnowledgeChunk.sequence)
    ).all()
    conflicts: list[KnowledgeConflictView] = []
    for incoming in incoming_chunks:
        for existing, version in rows:
            if incoming.heading != existing.heading or incoming.content == existing.content:
                continue
            incoming_rules = _rule_tokens(incoming.content)
            existing_rules = _rule_tokens(existing.content)
            critical = bool(incoming_rules or existing_rules) and incoming_rules != existing_rules
            conflicts.append(
                KnowledgeConflictView(
                    conflict_type=(
                        "policy_rule_value_changed" if critical else "policy_section_changed"
                    ),
                    severity="critical" if critical else "warning",
                    related_version_id=version.id,
                    related_version_label=version.version_label,
                    heading=incoming.heading,
                    locator=existing.locator,
                    summary=(
                        "同一章节的数值、日期或阈值发生变化，发布前必须复核"
                        if critical
                        else "同一章节内容发生变化，发布前需要确认替代关系"
                    ),
                )
            )
    return conflicts[:50]


def _get_version_document(
    session: Session,
    enterprise_id: str,
    version_id: str,
) -> tuple[KnowledgeVersion, KnowledgeDocument]:
    row = session.execute(
        select(KnowledgeVersion, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
        .where(
            KnowledgeDocument.enterprise_id == enterprise_id,
            KnowledgeVersion.id == version_id,
        )
    ).first()
    if row is None:
        raise ApiProblem(
            status_code=404,
            code="knowledge.version_not_found",
            message="没有找到指定知识版本",
        )
    return row[0], row[1]


def _lifecycle_event(
    actor: ActorContext,
    *,
    document_id: str,
    version_id: str,
    event_type: str,
    from_status: str | None,
    to_status: str,
    reason: str,
    effective_at: datetime | None,
    occurred_at: datetime,
) -> KnowledgeLifecycleEvent:
    return KnowledgeLifecycleEvent(
        id=f"knowledge_lifecycle_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        document_id=document_id,
        version_id=version_id,
        actor_principal_id=actor.principal_id,
        actor_snapshot=actor.snapshot(),
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        effective_at=effective_at,
        request_id=actor.request_id,
        run_id=actor.run_id,
        occurred_at=occurred_at,
    )


def _lifecycle_response(
    document: KnowledgeDocument,
    version: KnowledgeVersion,
    *,
    event_id: str,
    event_type: Literal["published", "retired"],
    idempotent: bool,
    occurred_at: datetime,
    chunk_count: int,
) -> KnowledgeLifecycleResponse:
    return KnowledgeLifecycleResponse(
        document_key=document.document_key,
        version=_version_view(version, chunk_count),
        event_id=event_id,
        event_type=event_type,
        idempotent=idempotent,
        occurred_at=occurred_at,
    )


def _chunk_count(session: Session, version_id: str) -> int:
    return int(
        session.scalar(
            select(func.count(KnowledgeChunk.id)).where(KnowledgeChunk.version_id == version_id)
        )
        or 0
    )


def _normalize_tags(tags: list[str]) -> list[str]:
    return list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))[:20]


def _rule_tokens(content: str) -> set[str]:
    return {re.sub(r"\s+", "", item).casefold() for item in RULE_TOKEN_PATTERN.findall(content)}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ApiProblem(
            status_code=422,
            code="knowledge.timezone_required",
            message="制度生效时间必须包含时区",
        )
    return value.astimezone(UTC)


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _same_instant(left: datetime | None, right: datetime) -> bool:
    return _coerce_utc(left) == _coerce_utc(right)


def search_evidence(
    database: Database,
    query: str,
    *,
    limit: int = 5,
    enterprise_id: str | None = None,
) -> EvidenceSearchResponse:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    now = datetime.now(UTC)
    with database.session() as session:
        rows = session.execute(
            select(KnowledgeChunk, KnowledgeVersion, KnowledgeDocument)
            .join(KnowledgeVersion, KnowledgeVersion.id == KnowledgeChunk.version_id)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
            .where(
                KnowledgeDocument.enterprise_id == enterprise_id,
                KnowledgeDocument.status == "active",
                KnowledgeChunk.index_status == "indexed",
                KnowledgeVersion.status.in_(("active", "published", "scheduled")),
            )
        ).all()

    query_terms = lexical_terms(query)
    ranked: list[tuple[float, KnowledgeChunk, KnowledgeVersion, KnowledgeDocument]] = []
    for chunk, version, document in rows:
        title_terms = lexical_terms(f"{document.title} {chunk.heading} {' '.join(document.tags)}")
        content_terms = lexical_terms(chunk.content)
        title_hits = len(query_terms & title_terms)
        shared_content_terms = query_terms & content_terms
        content_hits = len(shared_content_terms)
        temporal_hits = sum(1 for term in shared_content_terms if term[:1].isdigit())
        exact_bonus = 8 if query.strip() in chunk.content else 0
        active_bonus = 4 if version.status == "active" else 1
        effective_bonus = (
            2 if version.effective_from and version.effective_from.date() <= now.date() else 0
        )
        score = (
            title_hits * 4
            + content_hits
            + temporal_hits * 5
            + exact_bonus
            + active_bonus
            + effective_bonus
        )
        if score > 0:
            ranked.append((float(score), chunk, version, document))
    if not ranked:
        ranked = [
            (1.0, chunk, version, document)
            for chunk, version, document in rows
            if version.status == "active"
        ]
    ranked.sort(
        key=lambda item: (
            item[0],
            item[2].version_number,
            -item[1].sequence,
        ),
        reverse=True,
    )
    top_score = ranked[0][0] if ranked else 1.0
    selected = [item for item in ranked if item[0] >= top_score * 0.45][:limit]
    items = [
        EvidenceView(
            chunk_id=chunk.id,
            document_key=document.document_key,
            document_title=document.title,
            version_id=version.id,
            version_label=version.version_label,
            version_status=version.status,
            effective_from=version.effective_from,
            heading=chunk.heading,
            locator=chunk.locator,
            excerpt=_excerpt(chunk.content),
            score=round(score / top_score, 4),
        )
        for score, chunk, version, document in selected
    ]
    return EvidenceSearchResponse(
        query=query,
        retrieval_provider="local-lexical-v1",
        items=items,
        generated_at=now,
    )


def get_twin_profile(
    database: Database, twin_key: str, enterprise_id: str | None = None
) -> RoleTwinProfileView:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    with database.session() as session:
        profile = session.scalar(
            select(RoleTwinProfile).where(
                RoleTwinProfile.enterprise_id == enterprise_id,
                RoleTwinProfile.twin_key == twin_key,
            )
        )
        if profile is None:
            raise LookupError("没有找到指定角色分身")
        actor = session.scalar(
            select(TwinActor).where(
                TwinActor.enterprise_id == enterprise_id,
                TwinActor.actor_key == twin_key,
            )
        )
        run_count = int(
            session.scalar(
                select(func.count(AgentRun.id)).where(AgentRun.twin_profile_id == profile.id)
            )
            or 0
        )
        latest_run_at = session.scalar(
            select(func.max(AgentRun.created_at)).where(AgentRun.twin_profile_id == profile.id)
        )
    return RoleTwinProfileView(
        key=profile.twin_key,
        display_name=profile.display_name,
        role_title=profile.role_title,
        capabilities=actor.capabilities if actor else [],
        provider=profile.provider,
        model=profile.model,
        status=profile.status,
        published_at=profile.published_at,
        run_count=run_count,
        latest_run_at=latest_run_at,
    )


async def answer_with_twin(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    runtime: AgentRuntime,
    *,
    actor: ActorContext,
    twin_key: str,
    question: str,
    top_k: int,
    scope_key: str | None = None,
    workspace_key: str | None = None,
    runtime_session_id: str | None = None,
) -> TwinAnswerResponse:
    if runtime_session_id and not settings.agent_runtime_enabled:
        raise ValueError("Agent Runtime 未启用，不能继续该会话")
    started = perf_counter()
    created_at = datetime.now(UTC)
    run_id = f"agent_run_{uuid4().hex}"
    evidence_response = search_evidence(
        database, question, limit=top_k, enterprise_id=actor.enterprise_id
    )
    metric_context = build_metric_context(
        database,
        actor,
        question=question,
        requested_scope_key=scope_key,
    )
    get_twin_profile(database, twin_key, actor.enterprise_id)
    with database.session() as session:
        profile = session.scalar(
            select(RoleTwinProfile).where(
                RoleTwinProfile.enterprise_id == actor.enterprise_id,
                RoleTwinProfile.twin_key == twin_key,
            )
        )
        if profile is None:
            raise LookupError("没有找到指定角色分身")
        profile_id = profile.id
        active_role_version = current_twin_version(session, profile.id)
        if profile.role_template_id is not None and active_role_version is None:
            raise LookupError("角色分身尚无已发布配置版本")
        role_version_id = active_role_version.id if active_role_version else None
        voice_guide = (
            active_role_version.voice_guide if active_role_version else profile.voice_guide
        )
        reasoning_guide = (
            active_role_version.reasoning_guide if active_role_version else profile.reasoning_guide
        )
        answer_policy = (
            active_role_version.answer_policy if active_role_version else profile.answer_policy
        )
        active_memories = list(
            session.scalars(
                select(ApprovedMemory)
                .where(
                    ApprovedMemory.enterprise_id == actor.enterprise_id,
                    ApprovedMemory.twin_profile_id == profile.id,
                    ApprovedMemory.status == "active",
                )
                .order_by(ApprovedMemory.category, ApprovedMemory.memory_key)
                .limit(12)
            )
        )

    followup_target = (
        _runtime_followup_target(
            database,
            actor=actor,
            twin_profile_id=profile_id,
            runtime_session_id=runtime_session_id,
        )
        if runtime_session_id
        else None
    )
    if workspace_key and runtime_session_id:
        previous_workspace_key = _runtime_workspace_key(
            database,
            runtime_session_id=runtime_session_id,
            actor=actor,
        )
        if previous_workspace_key and previous_workspace_key != workspace_key:
            raise ValueError("Runtime 会话不能切换工作空间")

    memory_context = [
        MemoryContextView(
            id=memory.id,
            memory_key=memory.memory_key,
            version_number=memory.version_number,
            category=memory.category,
            content=memory.content,
            source_ref=memory.source_ref,
            effective_from=memory.effective_from,
        )
        for memory in active_memories
    ]

    instructions = _answer_instructions(voice_guide, reasoning_guide, answer_policy)
    input_text = _answer_input(
        question,
        evidence_response.items,
        metric_context,
        memory_context,
        created_at,
    )
    initial_provider = runtime.runtime_key if settings.agent_runtime_enabled else (
        "openai-compatible-responses"
    )
    initial_model = (
        settings.codex_runtime_model or "codex-default"
        if settings.agent_runtime_enabled
        else settings.ai_model
    )
    _persist_agent_run_start(
        database,
        actor=actor,
        run_id=run_id,
        profile_id=profile_id,
        role_version_id=role_version_id,
        question=question,
        provider=initial_provider,
        model=initial_model,
        created_at=created_at,
        evidence=evidence_response.items,
        active_memories=active_memories,
        metric_context=metric_context,
        workspace_key=workspace_key,
    )

    completion: AICompletion | None = None
    answer_runtime_session_id: str | None = None
    answer_runtime_turn_id: str | None = None
    fallback_reasons: list[str] = []
    if (
        not evidence_response.items
        and not metric_context
        and not memory_context
        and followup_target is None
    ):
        answer = TwinAnswerPayload(
            summary="当前知识中心没有检索到足以回答该问题的正式资料。",
            facts=[],
            actions=["补充或发布相关企业资料后重新提问。"],
            caveats=["未使用无来源内容进行推断。"],
            confidence="low",
        )
        fallback_reasons.append("没有可用证据")
        execution_mode: Literal["model", "evidence-fallback"] = "evidence-fallback"
        provider_name = "local-evidence"
        model_name = "deterministic-v1"
    else:
        answer = None
        if settings.agent_runtime_enabled:
            try:
                (
                    answer,
                    answer_runtime_session_id,
                    answer_runtime_turn_id,
                ) = await _generate_runtime_answer(
                    database,
                    settings,
                    runtime,
                    actor=actor,
                    run_id=run_id,
                    twin_key=twin_key,
                    role_version_id=role_version_id,
                    instructions=instructions,
                    input_text=input_text,
                    question=question,
                    evidence=evidence_response.items,
                    memories=memory_context,
                    metrics=metric_context,
                    now=created_at,
                    workspace_key=workspace_key,
                    existing_runtime_session_id=(
                        followup_target[0] if followup_target else None
                    ),
                    runtime_thread_id=(followup_target[1] if followup_target else None),
                )
                provider_name = runtime.runtime_key
                model_name = settings.codex_runtime_model or "codex-default"
            except AgentRunCancelled:
                duration_ms = max(1, round((perf_counter() - started) * 1000))
                with database.session() as session:
                    cancelled_run = session.get(AgentRun, run_id)
                    if cancelled_run is not None:
                        cancelled_run.status = "cancelled"
                        cancelled_run.provider = runtime.runtime_key
                        cancelled_run.model = settings.codex_runtime_model or "codex-default"
                        cancelled_run.fallback_reason = "Agent Runtime 运行已取消"
                        cancelled_run.duration_ms = duration_ms
                        session.commit()
                raise
            except Exception as exc:
                runtime_error = sanitize_runtime_error(
                    str(exc) or exc.__class__.__name__
                )
                fallback_reasons.append(
                    f"Agent Runtime 降级: {runtime_error}"
                )

        if answer is None:
            try:
                completion, answer = await _generate_provider_answer(
                    provider,
                    settings,
                    instructions=instructions,
                    input_text=input_text,
                    run_id=run_id,
                    question=question,
                    evidence=evidence_response.items,
                    memories=memory_context,
                    metrics=metric_context,
                    now=created_at,
                )
                provider_name = "openai-compatible-responses"
                model_name = settings.ai_model
            except (AIProviderError, ValueError) as exc:
                fallback_reasons.append(sanitize_runtime_error(str(exc)))
                answer = _fallback_answer(
                    evidence_response.items,
                    metric_context,
                    memory_context,
                )
                provider_name = "local-evidence"
                model_name = "deterministic-v1"
                execution_mode = "evidence-fallback"
            else:
                execution_mode = "model"
        else:
            execution_mode = "model"

    duration_ms = max(1, round((perf_counter() - started) * 1000))
    assert answer is not None
    fallback_reason = " | ".join(fallback_reasons)[:500] or None
    with database.session() as session:
        run = session.get(AgentRun, run_id)
        if run is None:
            raise LookupError("没有找到已创建的 AgentRun")
        run.answer = answer.summary
        run.answer_payload = answer.model_dump(mode="json")
        run.status = "completed" if execution_mode == "model" else "degraded"
        run.provider = provider_name
        run.model = model_name
        run.fallback_reason = fallback_reason
        run.duration_ms = duration_ms
        run.input_tokens = completion.input_tokens if completion else None
        run.output_tokens = completion.output_tokens if completion else None
        session.commit()

    return TwinAnswerResponse(
        run_id=run_id,
        twin=get_twin_profile(database, twin_key, actor.enterprise_id),
        question=question,
        answer=answer,
        evidence=evidence_response.items,
        metric_context=metric_context,
        memory_context=memory_context,
        execution_mode=execution_mode,
        provider=provider_name,
        model=model_name,
        duration_ms=duration_ms,
        created_at=created_at,
        workspace_key=workspace_key,
        runtime_session_id=answer_runtime_session_id,
        runtime_turn_id=answer_runtime_turn_id,
    )


def _persist_agent_run_start(
    database: Database,
    *,
    actor: ActorContext,
    run_id: str,
    profile_id: str,
    role_version_id: str | None,
    question: str,
    provider: str,
    model: str,
    created_at: datetime,
    evidence: list[EvidenceView],
    active_memories: list[ApprovedMemory],
    metric_context: list[MetricContextView],
    workspace_key: str | None,
) -> None:
    with database.session() as session:
        session.add(
            AgentRun(
                id=run_id,
                enterprise_id=actor.enterprise_id,
                actor_principal_id=actor.principal_id,
                twin_profile_id=profile_id,
                role_twin_version_id=role_version_id,
                question=question,
                answer="",
                answer_payload={},
                status="running",
                provider=provider,
                model=model,
                fallback_reason=None,
                duration_ms=0,
                input_tokens=None,
                output_tokens=None,
                created_at=created_at,
            )
        )
        for rank, item in enumerate(evidence, start=1):
            session.add(
                AgentRunEvidence(
                    id=f"agent_evidence_{uuid4().hex}",
                    run_id=run_id,
                    chunk_id=item.chunk_id,
                    rank=rank,
                    score=item.score,
                    excerpt=item.excerpt,
                    citation_label=(
                        f"{item.document_title} {item.version_label} · {item.locator}"
                    ),
                )
            )
        if workspace_key:
            session.add(
                AgentRunContextItem(
                    id=f"agent_context_{uuid4().hex}",
                    run_id=run_id,
                    item_type="workspace",
                    item_id=workspace_key,
                    version_ref="workspace-profile-v1",
                    rank=0,
                    content_hash=content_hash(workspace_key),
                    excerpt=workspace_key,
                    citation_label=f"当前工作空间 · {workspace_key}",
                )
            )
        for rank, memory in enumerate(active_memories, start=1):
            session.add(
                AgentRunContextItem(
                    id=f"agent_context_{uuid4().hex}",
                    run_id=run_id,
                    item_type="approved-memory",
                    item_id=memory.id,
                    version_ref=f"v{memory.version_number}",
                    rank=rank,
                    content_hash=memory.normalized_hash,
                    excerpt=_excerpt(memory.content),
                    citation_label=f"角色记忆 v{memory.version_number} · {memory.source_ref}",
                )
            )
        for rank, metric in enumerate(metric_context, start=1):
            serialized = metric.model_dump_json()
            session.add(
                AgentRunContextItem(
                    id=f"agent_context_{uuid4().hex}",
                    run_id=run_id,
                    item_type="metric-series",
                    item_id=f"metric_{content_hash(f'{metric.key}:{metric.scope_key}')[:24]}",
                    version_ref=metric.definition_version,
                    rank=rank,
                    content_hash=content_hash(serialized),
                    excerpt=_metric_context_line(metric, include_points=False),
                    citation_label=(
                        f"经营指标 · {metric.label} · {metric.scope_key} · "
                        f"{_metric_date_range(metric)}"
                    ),
                )
            )
        session.commit()


def _runtime_workspace_key(
    database: Database,
    *,
    actor: ActorContext,
    runtime_session_id: str,
) -> str | None:
    with database.session() as session:
        runtime_session = session.scalar(
            select(AgentRuntimeSession).where(
                AgentRuntimeSession.id == runtime_session_id,
                AgentRuntimeSession.enterprise_id == actor.enterprise_id,
            )
        )
        if runtime_session is None:
            return None
        item = session.scalar(
            select(AgentRunContextItem)
            .where(
                AgentRunContextItem.run_id == runtime_session.agent_run_id,
                AgentRunContextItem.item_type == "workspace",
            )
            .order_by(AgentRunContextItem.rank)
            .limit(1)
        )
        return item.item_id if item else None


def _runtime_followup_target(
    database: Database,
    *,
    actor: ActorContext,
    twin_profile_id: str,
    runtime_session_id: str,
) -> tuple[str, str]:
    with database.session() as session:
        runtime_session = session.scalar(
            select(AgentRuntimeSession).where(
                AgentRuntimeSession.id == runtime_session_id,
                AgentRuntimeSession.enterprise_id == actor.enterprise_id,
            )
        )
        if runtime_session is None:
            raise LookupError("没有找到 Agent Runtime 会话")
        root_run = session.get(AgentRun, runtime_session.agent_run_id)
        if root_run is None or root_run.actor_principal_id != actor.principal_id:
            raise LookupError("没有找到 Agent Runtime 会话")
        if root_run.twin_profile_id != twin_profile_id:
            raise ValueError("Runtime 会话不属于当前角色分身")
        if runtime_session.status != "completed":
            raise ValueError("上一轮 Runtime 尚未完成，不能继续提问")
        validate_runtime_scope_for_resume(
            runtime_session.runtime_spec or {}, build_scope_context(database, actor).snapshot(),
        )
        return runtime_session.id, runtime_session.runtime_thread_id


async def _generate_runtime_answer(
    database: Database,
    settings: Settings,
    runtime: AgentRuntime,
    *,
    actor: ActorContext,
    run_id: str,
    twin_key: str,
    role_version_id: str | None,
    instructions: str,
    input_text: str,
    question: str,
    evidence: list[EvidenceView],
    memories: list[MemoryContextView],
    metrics: list[MetricContextView],
    now: datetime,
    workspace_key: str | None = None,
    existing_runtime_session_id: str | None = None,
    runtime_thread_id: str | None = None,
) -> tuple[TwinAnswerPayload, str, str]:
    from zhixing_api.runtime_skill_service import select_runtime_skill
    from zhixing_api.tool_service import list_tool_catalog

    available_tool_keys = {
        item.key
        for item in list_tool_catalog(database, actor).items
        if item.risk_level == "R0"
    }
    skill_key = "store-performance-brief" if metrics else "policy-grounded-answer"
    skill = select_runtime_skill(
        database,
        actor,
        skill_key=skill_key,
        required_tool_keys=available_tool_keys,
    )
    tool_keys = list(skill.tool_keys)

    gateway = create_mcp_session(
        database,
        actor,
        McpSessionCreateRequest(
            client_id=settings.codex_runtime_mcp_client_id,
            allowed_tool_keys=tool_keys,
            scope_constraints=[],
            ttl_seconds=settings.codex_runtime_mcp_ttl_seconds,
            agent_run_id=run_id,
            workspace_key=workspace_key,
        ),
    )
    credentials = RuntimeCredentials(
        mcp_session_token=gateway.session_token,
        mcp_client_id=gateway.session.client_id,
    )
    spec = AgentRunSpec(
        run_id=run_id,
        actor=AgentActor(
            enterprise_id=actor.enterprise_id,
            principal_id=actor.principal_id,
            actor_key=actor.actor_key,
            permission_set_version=actor.permission_set_version,
            authentication_method=actor.authentication_method,
        ),
        input_text=input_text,
        instructions=f"{skill.instructions}\n\n角色边界：{instructions}",
        cwd=settings.codex_runtime_cwd,
        model=settings.codex_runtime_model or None,
        allowed_tool_keys=tuple(tool_keys),
        output_schema=TwinAnswerPayload.model_json_schema(),
        scope_context=build_scope_context(database, actor).snapshot(),
        metadata={
            "twin_key": twin_key,
            "role_version_id": role_version_id or "legacy",
            "workspace_key": workspace_key or "unspecified",
            "skill_key": skill.skill_key,
            "skill_version": str(skill.version_number),
        },
    )
    runtime_session_id: str | None = None
    runtime_turn_id: str | None = None
    try:
        if existing_runtime_session_id and runtime_thread_id:
            handle = await runtime.resume(
                run_id,
                input_text,
                credentials,
                runtime_thread_id=runtime_thread_id,
                spec=spec,
            )
            runtime_turn = begin_runtime_turn(
                database,
                actor,
                runtime_session_id=existing_runtime_session_id,
                agent_run_id=run_id,
                mcp_gateway_session_id=gateway.session.session_id,
                handle=handle,
                model=settings.codex_runtime_model or None,
            )
            runtime_session_id = existing_runtime_session_id
        else:
            handle = await runtime.start(spec, credentials)
            runtime_session, runtime_turn = create_runtime_session(
                database,
                actor,
                agent_run_id=run_id,
                handle=handle,
                spec=spec,
                mcp_gateway_session_id=gateway.session.session_id,
                model=settings.codex_runtime_model or None,
            )
            runtime_session_id = runtime_session.id
        runtime_turn_id = runtime_turn.id
        answer = await _consume_runtime_answer(
            database,
            runtime,
            run_id=run_id,
            runtime_session_id=runtime_session_id,
            runtime_turn_id=runtime_turn.id,
        )
        unsupported_claims = _unsupported_numeric_claims(
            answer,
            evidence,
            memories,
            metrics,
            question=question,
            now=now,
        )
        if unsupported_claims:
            correction = (
                "上一次输出未通过数值证据校验。重新回答时不得推导日期、金额、比例、"
                "阈值或时间范围；删除所有不能从原问题或既有证据中逐字引用的数值。"
            )
            resumed = await runtime.resume(run_id, correction, credentials)
            runtime_turn = begin_runtime_turn(
                database,
                actor,
                runtime_session_id=runtime_session_id,
                agent_run_id=run_id,
                mcp_gateway_session_id=gateway.session.session_id,
                handle=resumed,
                model=settings.codex_runtime_model or None,
            )
            runtime_turn_id = runtime_turn.id
            answer = await _consume_runtime_answer(
                database,
                runtime,
                run_id=run_id,
                runtime_session_id=runtime_session_id,
                runtime_turn_id=runtime_turn.id,
            )
            unsupported_claims = _unsupported_numeric_claims(
                answer,
                evidence,
                memories,
                metrics,
                question=question,
                now=now,
            )
            if unsupported_claims:
                raise ValueError(
                    "Runtime 答案包含证据中不存在的数值或日期："
                    + "、".join(sorted(unsupported_claims))
                )
        assert runtime_session_id is not None
        return answer, runtime_session_id, runtime_turn.id
    except Exception as exc:
        if runtime_session_id and runtime_turn_id:
            mark_runtime_session_failed(
                database,
                runtime_session_id=runtime_session_id,
                runtime_turn_id=runtime_turn_id,
                error_code="runtime_answer_failed",
                error_message=str(exc) or exc.__class__.__name__,
            )
        raise
    finally:
        try:
            await runtime.release(run_id)
        except Exception:
            pass
        try:
            revoke_mcp_session(
                database,
                actor,
                gateway.session.session_id,
                McpSessionRevokeRequest(reason="agent_runtime_turn_finished"),
            )
        except Exception:
            pass


async def _consume_runtime_answer(
    database: Database,
    runtime: AgentRuntime,
    *,
    run_id: str,
    runtime_session_id: str,
    runtime_turn_id: str,
) -> TwinAnswerPayload:
    final_message: str | None = None
    terminal_event: AgentRunEvent | None = None
    async for event in runtime.stream(run_id):
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
    if terminal_event is None:
        raise AgentRuntimeError("Agent Runtime 未返回最终状态")
    if terminal_event.event_type == "run.cancelled":
        raise AgentRunCancelled("Agent Runtime 运行已取消")
    if terminal_event.event_type != "run.completed":
        raise AgentRuntimeError(terminal_event.message or "Agent Runtime 未完成回答")
    if not final_message:
        raise AgentRuntimeError("Agent Runtime 未返回最终回答")
    try:
        payload = json.loads(_strip_json_fence(final_message))
    except json.JSONDecodeError as exc:
        raise AgentRuntimeError("Agent Runtime 最终回答不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise AgentRuntimeError("Agent Runtime 最终回答结构无效")
    return TwinAnswerPayload.model_validate(payload)


async def _generate_provider_answer(
    provider: ResponsesAIProvider,
    settings: Settings,
    *,
    instructions: str,
    input_text: str,
    run_id: str,
    question: str,
    evidence: list[EvidenceView],
    memories: list[MemoryContextView],
    metrics: list[MetricContextView],
    now: datetime,
) -> tuple[AICompletion, TwinAnswerPayload]:
    completion = await provider.generate(
        settings,
        instructions=instructions,
        input_text=input_text,
        run_id=run_id,
    )
    answer = TwinAnswerPayload.model_validate(completion.payload)
    unsupported_claims = _unsupported_numeric_claims(
        answer,
        evidence,
        memories,
        metrics,
        question=question,
        now=now,
    )
    if unsupported_claims:
        completion = await provider.generate(
            settings,
            instructions=(
                f"{instructions}\n"
                "上一次输出未通过数值证据校验。重新回答时不得推导日期、金额、比例、"
                "阈值或时间范围；删除所有不能从输入原文逐字引用的数值。"
            ),
            input_text=input_text,
            run_id=run_id,
        )
        answer = TwinAnswerPayload.model_validate(completion.payload)
        unsupported_claims = _unsupported_numeric_claims(
            answer,
            evidence,
            memories,
            metrics,
            question=question,
            now=now,
        )
        if unsupported_claims:
            raise ValueError(
                "模型答案包含证据中不存在的数值或日期："
                + "、".join(sorted(unsupported_claims))
            )
    return completion, answer


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        return stripped[7:-3].strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return stripped[3:-3].strip()
    return stripped


def _answer_instructions(voice: str, reasoning: str, policy: str) -> str:
    return f"""你是企业内部的角色分身。
只能根据用户提供的正式证据、结构化经营数据和已审核角色记忆回答。
表达方式：{voice}
分析要求：{reasoning}
回答规则：{policy}
正式制度和带口径版本的经营指标是事实真值；角色记忆只能补充表达方式、管理偏好和历史经验，不能覆盖正式证据。
存在冲突、未核验、已拒绝或已退役的记忆不会出现在输入中，也不得自行推测。
不要编造数据、制度、引文或权限。区分事实、建议和未知；未来生效规则不能描述为当前规则。
输出中的每个日期、比例、金额、阈值和时间范围必须能在问题或证据中逐字找到。
不要输出隐藏思维过程，只返回简洁结论、可核验事实、行动建议、限制和置信度。"""


def _answer_input(
    question: str,
    evidence: list[EvidenceView],
    metrics: list[MetricContextView],
    memories: list[MemoryContextView],
    now: datetime,
) -> str:
    sources = "\n\n".join(
        f"[E{index}] {item.document_title} {item.version_label} | 状态={item.version_status} | "
        f"生效时间={item.effective_from.isoformat() if item.effective_from else '未设置'} | "
        f"位置={item.locator}\n{item.excerpt}"
        for index, item in enumerate(evidence, start=1)
    )
    memory_sources = "\n".join(
        f"[M{index}] 类别={item.category} | 版本=v{item.version_number} | "
        f"来源={item.source_ref}\n{item.content}"
        for index, item in enumerate(memories, start=1)
    )
    metric_sources = "\n".join(
        f"[D{index}] {_metric_context_line(item, include_points=True)}"
        for index, item in enumerate(metrics, start=1)
    )
    return (
        f"当前时间：{now.isoformat()}\n企业问题：{question}\n\n"
        f"正式证据（事实优先）：\n{sources or '无'}\n\n"
        f"结构化经营数据（按数据范围授权、口径版本可追溯）：\n"
        f"{metric_sources or '无'}\n\n"
        f"已审核且已激活的角色记忆（仅作补充）：\n{memory_sources or '无'}"
    )


def _fallback_answer(
    evidence: list[EvidenceView],
    metrics: list[MetricContextView],
    memories: list[MemoryContextView],
) -> TwinAnswerPayload:
    facts = [
        f"{item.document_title} {item.version_label}（{item.locator}）：{item.excerpt}"
        for item in evidence[:3]
    ]
    memory_facts = [
        f"已审核角色记忆 v{item.version_number}（{item.source_ref}）：{item.content}"
        for item in memories[:2]
    ]
    metric_facts = [
        f"经营数据 D{index}：{_metric_context_line(item, include_points=False)}"
        for index, item in enumerate(metrics[:4], start=1)
    ]
    return TwinAnswerPayload(
        summary="已按正式资料、授权经营数据与已激活角色记忆给出可追溯摘要；模型接口未启用或暂不可用。",
        facts=[*metric_facts, *facts, *memory_facts],
        actions=["按引用位置核对现行版本与生效时间，再执行制度或经营动作。"],
        caveats=["这是确定性降级结果；角色记忆不覆盖正式制度和经营事实。"],
        confidence="medium" if len(evidence) + len(metrics) + len(memories) >= 2 else "low",
    )


def _excerpt(content: str, limit: int = 280) -> str:
    normalized = " ".join(content.split())
    return normalized if len(normalized) <= limit else f"{normalized[:limit].rstrip()}..."


def _unsupported_numeric_claims(
    answer: TwinAnswerPayload,
    evidence: list[EvidenceView],
    memories: list[MemoryContextView] | None = None,
    metrics: list[MetricContextView] | None = None,
    *,
    question: str,
    now: datetime,
) -> set[str]:
    source = " ".join(
        [
            question,
            now.date().isoformat(),
            *(
                f"{item.excerpt} {item.effective_from.isoformat() if item.effective_from else ''}"
                for item in evidence
            ),
            *(item.content for item in memories or []),
            *(_metric_context_line(item, include_points=True) for item in metrics or []),
        ]
    )
    output = " ".join([answer.summary, *answer.facts, *answer.actions, *answer.caveats])
    return _numeric_claims(output) - _numeric_claims(source)


def _metric_context_line(metric: MetricContextView, *, include_points: bool) -> str:
    period_change = (
        f"{metric.period_change_rate * 100:.2f}%"
        if metric.period_change_rate is not None
        else "暂无"
    )
    line = (
        f"指标={metric.label} | 指标键={metric.key} | 范围={metric.scope_key} | "
        f"口径版本={metric.definition_version} | 时间={_metric_date_range(metric)} | "
        f"最新={_metric_value(metric.latest_value, metric.unit)} | 区间变化={period_change} | "
        f"最低={_metric_value(metric.minimum, metric.unit)} | "
        f"最高={_metric_value(metric.maximum, metric.unit)}"
    )
    if not include_points:
        return line
    points = ", ".join(
        f"{point.as_of.date().isoformat()}:{_metric_value(point.value, metric.unit)}"
        for point in metric.points
    )
    return f"{line} | 日序列={points or '无'}"


def _metric_value(value: float | None, unit: str) -> str:
    if value is None:
        return "暂无"
    normalized = f"{value:.4f}".rstrip("0").rstrip(".")
    return f"{normalized}{unit}"


def _metric_date_range(metric: MetricContextView) -> str:
    if metric.date_from is None or metric.date_to is None:
        return "暂无"
    return f"{metric.date_from.date().isoformat()}至{metric.date_to.date().isoformat()}"


def _numeric_claims(value: str) -> set[str]:
    normalized = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", value)
    normalized = re.sub(
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        lambda match: (
            f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
        ),
        normalized,
    )
    normalized = re.sub(
        r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        lambda match: f"--{int(match.group(1)):02d}-{int(match.group(2)):02d}",
        normalized,
    )
    patterns = (
        r"\d{4}-\d{2}-\d{2}",
        r"--\d{2}-\d{2}",
        r"\d+(?:\.\d+)?\s*(?:年|月|日|天|%|元|万)",
        r"\d+(?:\.\d+)?\s*(?:个)?工作日",
    )
    claims = {
        re.sub(r"\s+", "", match)
        for pattern in patterns
        for match in re.findall(pattern, normalized)
    }
    for year, month, day in re.findall(r"(\d{4})-(\d{2})-(\d{2})", normalized):
        claims.update(
            {
                f"{year}-{month}-{day}",
                f"--{month}-{day}",
                f"{int(month)}月",
                f"{int(day)}日",
            }
        )
    return claims
