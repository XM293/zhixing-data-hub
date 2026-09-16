from __future__ import annotations

import base64
import binascii
import csv
import io
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from zhixing_jobs.models import BackgroundJob, JobAttempt

from zhixing_api.actor_context import ActorContext, actor_scope_allows
from zhixing_api.data_models import (
    AccessDelegation,
    AccessRole,
    AccessRolePermission,
    BulkExchangeJob,
    BulkExchangeRow,
    DomainEvent,
    FileAsset,
    Membership,
    Notification,
    NotificationDelivery,
    OrgUnit,
    PermissionDefinition,
    PlatformDictionaryItem,
    PlatformDictionaryType,
    PlatformOperationEvent,
    PlatformParameter,
    Position,
    Principal,
    RoleAssignment,
    ScopeGrant,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.object_storage import ObjectStorageError, ObjectStorageRegistry
from zhixing_api.platform_admin_schemas import (
    AccessDelegationCreateRequest,
    AccessDelegationMutationResponse,
    AccessDelegationRevokeRequest,
    AccessDelegationView,
    AccessGovernanceResponse,
    BackgroundJobView,
    BulkExchangeCommitRequest,
    BulkExchangeDetailResponse,
    BulkExchangeExportRequest,
    BulkExchangeJobView,
    BulkExchangeListResponse,
    BulkExchangeMutationResponse,
    BulkExchangePreflightRequest,
    BulkExchangeRowView,
    DictionaryItemUpsertRequest,
    DictionaryItemView,
    DictionaryView,
    FileAssetListResponse,
    FileAssetMutationResponse,
    FileAssetUploadRequest,
    FileAssetView,
    JobAdminResponse,
    JobAttemptView,
    JobDetailResponse,
    JobRetryRequest,
    JobRetryResponse,
    NotificationInboxResponse,
    NotificationMutationResponse,
    NotificationPublishRequest,
    NotificationView,
    OrgTreeNode,
    ParameterUpdateRequest,
    ParameterView,
    PermissionExplanationResponse,
    PlatformConfigMutationResponse,
    PlatformConfigResponse,
    PrincipalOption,
)

TERMINAL_RETRY_STATUSES = {"failed", "cancelled"}
SUPPORTED_EXCHANGE_DATASETS = ["platform.dictionary-items"]
MAX_FILE_BYTES = 10 * 1024 * 1024


def utc_now() -> datetime:
    return datetime.now(UTC)


def job_admin_overview(
    database: Database,
    *,
    enterprise_id: str,
    status: str | None = None,
    job_type: str | None = None,
    query: str | None = None,
) -> JobAdminResponse:
    with database.session() as session:
        filters = [BackgroundJob.enterprise_id == enterprise_id]
        if status:
            filters.append(BackgroundJob.status == status)
        if job_type:
            filters.append(BackgroundJob.job_type == job_type)
        if query:
            term = f"%{query.strip()}%"
            filters.append(
                or_(
                    BackgroundJob.id.ilike(term),
                    BackgroundJob.request_id.ilike(term),
                    BackgroundJob.run_id.ilike(term),
                )
            )
        jobs = list(
            session.scalars(
                select(BackgroundJob)
                .where(*filters)
                .order_by(BackgroundJob.created_at.desc())
                .limit(300)
            )
        )
        status_counts: dict[str, int] = {
            str(row[0]): int(row[1])
            for row in session.execute(
                select(BackgroundJob.status, func.count(BackgroundJob.id))
                .where(BackgroundJob.enterprise_id == enterprise_id)
                .group_by(BackgroundJob.status)
            )
        }
        job_types = list(
            session.scalars(
                select(BackgroundJob.job_type)
                .where(BackgroundJob.enterprise_id == enterprise_id)
                .distinct()
                .order_by(BackgroundJob.job_type)
            )
        )
    stats = {
        key: int(status_counts.get(key, 0))
        for key in ("queued", "running", "retry_wait", "succeeded", "failed", "cancelled")
    }
    stats["total"] = sum(stats.values())
    return JobAdminResponse(
        stats=stats,
        job_types=job_types,
        items=[_job_view(job) for job in jobs],
        generated_at=utc_now(),
    )


def job_detail(database: Database, *, enterprise_id: str, job_id: str) -> JobDetailResponse:
    with database.session() as session:
        job = session.scalar(
            select(BackgroundJob).where(
                BackgroundJob.enterprise_id == enterprise_id,
                BackgroundJob.id == job_id,
            )
        )
        if job is None:
            raise ApiProblem(
                status_code=404,
                code="platform.job_not_found",
                message="后台任务不存在",
            )
        attempts = list(
            session.scalars(
                select(JobAttempt)
                .where(JobAttempt.job_id == job.id)
                .order_by(JobAttempt.attempt_no.desc())
            )
        )
        return JobDetailResponse(
            job=_job_view(job),
            payload=dict(job.payload),
            result=dict(job.result) if job.result is not None else None,
            required_permissions=list(job.required_permissions),
            permission_set_version=job.permission_set_version,
            attempts=[
                JobAttemptView(
                    attempt_no=item.attempt_no,
                    worker_id=item.worker_id,
                    status=item.status,
                    started_at=_as_utc(item.started_at),
                    finished_at=_optional_utc(item.finished_at),
                    error_code=item.error_code,
                    error_message=item.error_message,
                )
                for item in attempts
            ],
        )


def retry_job(
    database: Database,
    *,
    actor: ActorContext,
    job_id: str,
    payload: JobRetryRequest,
) -> JobRetryResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = utc_now()
    with database.session() as session:
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if replay is not None:
            _assert_replay(replay, payload_hash, "platform.job_retry_idempotency_conflict")
            job = _enterprise_job(session, actor.enterprise_id, job_id)
            return JobRetryResponse(job=_job_view(job), event_id=replay.id, replayed=True)
        job = _enterprise_job(session, actor.enterprise_id, job_id)
        if job.status not in TERMINAL_RETRY_STATUSES:
            raise ApiProblem(
                status_code=409,
                code="platform.job_retry_state_conflict",
                message="只有失败或已取消的任务可以重新排队",
                details={"status": job.status},
            )
        if job.attempt != payload.expected_attempt:
            raise ApiProblem(
                status_code=409,
                code="platform.job_retry_version_conflict",
                message="任务执行次数已变化，请刷新后重试",
            )
        job.status = "queued"
        job.available_at = now
        job.finished_at = None
        job.worker_id = None
        job.execution_token_hash = None
        job.claimed_at = None
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.max_attempts = max(job.max_attempts, job.attempt - job.continuation_count + 1)
        job.updated_at = now
        event = _add_operation_event(
            session,
            actor=actor,
            event_type="platform.job.retry_queued",
            target_type="background_job",
            target_id=job.id,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"attempt": job.attempt, "job_type": job.job_type},
            now=now,
        )
        session.commit()
        return JobRetryResponse(job=_job_view(job), event_id=event.id, replayed=False)


def platform_config_overview(database: Database, *, enterprise_id: str) -> PlatformConfigResponse:
    with database.session() as session:
        parameters = list(
            session.scalars(
                select(PlatformParameter)
                .where(PlatformParameter.enterprise_id == enterprise_id)
                .order_by(PlatformParameter.group_key, PlatformParameter.parameter_key)
            )
        )
        types = list(
            session.scalars(
                select(PlatformDictionaryType)
                .where(PlatformDictionaryType.enterprise_id == enterprise_id)
                .order_by(PlatformDictionaryType.dictionary_key)
            )
        )
        items = list(
            session.scalars(
                select(PlatformDictionaryItem)
                .where(PlatformDictionaryItem.enterprise_id == enterprise_id)
                .order_by(
                    PlatformDictionaryItem.dictionary_type_id,
                    PlatformDictionaryItem.sort_order,
                    PlatformDictionaryItem.item_key,
                )
            )
        )
    items_by_type: dict[str, list[PlatformDictionaryItem]] = {}
    for item in items:
        items_by_type.setdefault(item.dictionary_type_id, []).append(item)
    return PlatformConfigResponse(
        parameters=[_parameter_view(item) for item in parameters],
        dictionaries=[
            DictionaryView(
                dictionary_key=item.dictionary_key,
                name=item.name,
                status=item.status,
                revision=item.revision,
                items=[_dictionary_item_view(row) for row in items_by_type.get(item.id, [])],
            )
            for item in types
        ],
        generated_at=utc_now(),
    )


def update_parameter(
    database: Database,
    *,
    actor: ActorContext,
    parameter_key: str,
    payload: ParameterUpdateRequest,
) -> PlatformConfigMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    with database.session() as session:
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if replay is not None:
            _assert_replay(replay, payload_hash, "platform.config_idempotency_conflict")
            return PlatformConfigMutationResponse(event_id=replay.id, replayed=True)
        parameter = session.scalar(
            select(PlatformParameter).where(
                PlatformParameter.enterprise_id == actor.enterprise_id,
                PlatformParameter.parameter_key == parameter_key,
            )
        )
        if parameter is None:
            raise ApiProblem(
                status_code=404,
                code="platform.parameter_not_found",
                message="平台参数不存在",
            )
        if parameter.revision != payload.expected_revision:
            raise ApiProblem(
                status_code=409,
                code="platform.parameter_revision_conflict",
                message="平台参数已更新，请刷新后重试",
            )
        _validate_parameter_value(parameter.value_type, payload.value)
        before = parameter.value
        parameter.value = payload.value
        parameter.status = payload.status
        parameter.revision += 1
        parameter.updated_by_principal_id = actor.principal_id
        parameter.updated_at = utc_now()
        event = _add_operation_event(
            session,
            actor=actor,
            event_type="platform.parameter.configured",
            target_type="platform_parameter",
            target_id=parameter.parameter_key,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"before": before, "after": payload.value, "revision": parameter.revision},
        )
        session.commit()
        return PlatformConfigMutationResponse(event_id=event.id, replayed=False)


def upsert_dictionary_item(
    database: Database,
    *,
    actor: ActorContext,
    dictionary_key: str,
    item_key: str,
    payload: DictionaryItemUpsertRequest,
) -> PlatformConfigMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    with database.session() as session:
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if replay is not None:
            _assert_replay(replay, payload_hash, "platform.dictionary_idempotency_conflict")
            return PlatformConfigMutationResponse(event_id=replay.id, replayed=True)
        dictionary = session.scalar(
            select(PlatformDictionaryType).where(
                PlatformDictionaryType.enterprise_id == actor.enterprise_id,
                PlatformDictionaryType.dictionary_key == dictionary_key,
            )
        )
        if dictionary is None:
            raise ApiProblem(
                status_code=404,
                code="platform.dictionary_not_found",
                message="平台字典不存在",
            )
        item = session.scalar(
            select(PlatformDictionaryItem).where(
                PlatformDictionaryItem.dictionary_type_id == dictionary.id,
                PlatformDictionaryItem.item_key == item_key,
            )
        )
        now = utc_now()
        event_type = "platform.dictionary_item.created"
        if item is None:
            if payload.expected_revision is not None:
                raise ApiProblem(
                    status_code=409,
                    code="platform.dictionary_item_missing",
                    message="字典项不存在，不能按指定版本更新",
                )
            item = PlatformDictionaryItem(
                id=f"dictionary_item_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                dictionary_type_id=dictionary.id,
                item_key=item_key,
                label=payload.label,
                value=payload.value,
                sort_order=payload.sort_order,
                status=payload.status,
                revision=1,
                updated_at=now,
            )
            session.add(item)
        else:
            event_type = "platform.dictionary_item.configured"
            if payload.expected_revision != item.revision:
                raise ApiProblem(
                    status_code=409,
                    code="platform.dictionary_item_revision_conflict",
                    message="字典项已更新，请刷新后重试",
                )
            item.label = payload.label
            item.value = payload.value
            item.sort_order = payload.sort_order
            item.status = payload.status
            item.revision += 1
            item.updated_at = now
        event = _add_operation_event(
            session,
            actor=actor,
            event_type=event_type,
            target_type="platform_dictionary_item",
            target_id=f"{dictionary_key}:{item_key}",
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"dictionary_key": dictionary_key, "item_key": item_key},
            now=now,
        )
        session.commit()
        return PlatformConfigMutationResponse(event_id=event.id, replayed=False)


def notification_inbox(
    database: Database,
    *,
    actor: ActorContext,
    status: str | None = None,
) -> NotificationInboxResponse:
    with database.session() as session:
        filters = [
            Notification.enterprise_id == actor.enterprise_id,
            Notification.principal_id == actor.principal_id,
        ]
        if status:
            filters.append(Notification.status == status)
        notifications = list(
            session.scalars(
                select(Notification)
                .where(*filters)
                .order_by(Notification.created_at.desc())
                .limit(200)
            )
        )
        deliveries = (
            list(
                session.scalars(
                    select(NotificationDelivery).where(
                        NotificationDelivery.notification_id.in_(
                            [item.id for item in notifications]
                        )
                    )
                )
            )
            if notifications
            else []
        )
    delivery_map: dict[str, dict[str, str]] = {}
    for delivery in deliveries:
        delivery_map.setdefault(delivery.notification_id, {})[delivery.channel] = delivery.status
    items = [_notification_view(item, delivery_map.get(item.id, {})) for item in notifications]
    return NotificationInboxResponse(
        stats={
            "total": len(items),
            "unread": sum(item.status == "unread" for item in items),
            "read": sum(item.status == "read" for item in items),
            "critical": sum(item.severity == "critical" for item in items),
        },
        items=items,
        generated_at=utc_now(),
    )


def set_notification_read(
    database: Database,
    *,
    actor: ActorContext,
    notification_id: str,
    read: bool,
) -> NotificationMutationResponse:
    with database.session() as session:
        item = session.scalar(
            select(Notification).where(
                Notification.enterprise_id == actor.enterprise_id,
                Notification.principal_id == actor.principal_id,
                Notification.id == notification_id,
            )
        )
        if item is None:
            raise ApiProblem(
                status_code=404,
                code="platform.notification_not_found",
                message="通知不存在",
            )
        item.status = "read" if read else "unread"
        item.read_at = utc_now() if read else None
        session.commit()
    return NotificationMutationResponse(affected=1)


def publish_notification(
    database: Database,
    *,
    actor: ActorContext,
    payload: NotificationPublishRequest,
) -> NotificationMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = utc_now()
    with database.session() as session:
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if replay is not None:
            _assert_replay(replay, payload_hash, "platform.notification_idempotency_conflict")
            return NotificationMutationResponse(
                affected=_int_value(replay.attributes.get("affected", 0)),
                event_id=cast(str | None, replay.attributes.get("domain_event_id")),
                replayed=True,
            )
        principals = list(
            session.scalars(
                select(Principal).where(
                    Principal.enterprise_id == actor.enterprise_id,
                    Principal.id.in_(sorted(set(payload.principal_ids))),
                    Principal.status == "active",
                )
            )
        )
        if len(principals) != len(set(payload.principal_ids)):
            raise ApiProblem(
                status_code=422,
                code="platform.notification_recipient_invalid",
                message="通知接收人不存在或未生效",
            )
        event = DomainEvent(
            id=f"domain_event_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            event_key=f"notification:{payload.client_request_key}",
            event_type="platform.notification.published",
            aggregate_type="notification_batch",
            aggregate_id=payload.client_request_key,
            payload={
                "category": payload.category,
                "severity": payload.severity,
                "recipient_count": len(principals),
            },
            status="published",
            occurred_at=now,
            published_at=now,
        )
        session.add(event)
        session.flush()
        for principal in principals:
            notification = Notification(
                id=f"notification_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                principal_id=principal.id,
                source_event_id=event.id,
                category=payload.category,
                title=payload.title,
                body=payload.body,
                severity=payload.severity,
                status="unread",
                action_route=payload.action_route,
                created_at=now,
                read_at=None,
            )
            session.add(notification)
            for channel in sorted(set(payload.channels)):
                session.add(
                    NotificationDelivery(
                        id=f"notification_delivery_{uuid4().hex}",
                        notification_id=notification.id,
                        channel=channel,
                        status="delivered" if channel == "inbox" else "pending",
                        attempt_count=1 if channel == "inbox" else 0,
                        last_error=None,
                        delivered_at=now if channel == "inbox" else None,
                    )
                )
        _add_operation_event(
            session,
            actor=actor,
            event_type="platform.notification.published",
            target_type="domain_event",
            target_id=event.id,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"affected": len(principals), "domain_event_id": event.id},
            now=now,
        )
        session.commit()
        return NotificationMutationResponse(
            affected=len(principals), event_id=event.id, replayed=False
        )


def list_file_assets(database: Database, *, actor: ActorContext) -> FileAssetListResponse:
    with database.session() as session:
        rows = list(
            session.execute(
                select(FileAsset, Principal)
                .join(Principal, Principal.id == FileAsset.uploaded_by_principal_id)
                .where(FileAsset.enterprise_id == actor.enterprise_id)
                .order_by(FileAsset.created_at.desc())
            )
        )
    items = [
        _file_view(asset, principal.display_name)
        for asset, principal in rows
        if _file_visible(database, actor, asset)
    ]
    return FileAssetListResponse(
        stats={
            "total": len(items),
            "active": sum(item.status == "active" for item in items),
            "bytes": sum(item.size_bytes for item in items),
            "categories": len({item.category for item in items}),
        },
        items=items,
        generated_at=utc_now(),
    )


def upload_file_asset(
    database: Database,
    *,
    actor: ActorContext,
    payload: FileAssetUploadRequest,
    storage: ObjectStorageRegistry,
) -> FileAssetMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    with database.session() as session:
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if replay is not None:
            _assert_replay(replay, payload_hash, "platform.file_idempotency_conflict")
            asset_id = str(replay.attributes.get("asset_id", ""))
            asset = session.get(FileAsset, asset_id)
            if asset is None:
                raise ApiProblem(
                    status_code=500,
                    code="platform.file_replay_missing",
                    message="文件请求已记录，但文件元数据不存在",
                )
            principal = session.get(Principal, asset.uploaded_by_principal_id)
            return FileAssetMutationResponse(
                asset=_file_view(asset, principal.display_name if principal else "未知"),
                event_id=replay.id,
                replayed=True,
            )
        duplicate = session.scalar(
            select(FileAsset).where(
                FileAsset.enterprise_id == actor.enterprise_id,
                FileAsset.asset_key == payload.asset_key,
            )
        )
        if duplicate is not None:
            raise ApiProblem(
                status_code=409,
                code="platform.file_asset_key_conflict",
                message="文件资产标识已存在",
            )
        if payload.required_permission not in actor.permissions:
            raise ApiProblem(
                status_code=403,
                code="platform.file_permission_invalid",
                message="不能创建高于当前账号权限的文件资产",
            )
        if not actor_scope_allows(
            actor,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            database=database,
        ):
            raise ApiProblem(
                status_code=403,
                code="platform.file_scope_invalid",
                message="文件资产范围超出当前账号范围",
            )
        content = _decode_file(payload.content_base64)
        digest = sha256(content).hexdigest()
        object_key = f"{actor.enterprise_id}/{uuid4().hex}"
        try:
            storage.put(object_key, content)
        except ObjectStorageError as exc:
            raise ApiProblem(
                status_code=503,
                code="platform.file_storage_unavailable",
                message="文件存储暂不可用",
            ) from exc
        now = utc_now()
        asset = FileAsset(
            id=f"file_asset_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            asset_key=payload.asset_key,
            file_name=Path(payload.file_name).name,
            media_type=payload.media_type,
            size_bytes=len(content),
            checksum_sha256=digest,
            storage_provider=storage.provider_key,
            object_key=object_key,
            category=payload.category,
            status="active",
            uploaded_by_principal_id=actor.principal_id,
            required_permission=payload.required_permission,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        session.add(asset)
        event = _add_operation_event(
            session,
            actor=actor,
            event_type="platform.file.uploaded",
            target_type="file_asset",
            target_id=asset.id,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"asset_id": asset.id, "checksum": digest, "size_bytes": len(content)},
            now=now,
        )
        session.commit()
        return FileAssetMutationResponse(
            asset=_file_view(asset, actor.display_name),
            event_id=event.id,
            replayed=False,
        )


def read_file_asset(
    database: Database,
    *,
    actor: ActorContext,
    asset_id: str,
    storage: ObjectStorageRegistry,
) -> tuple[FileAsset, bytes]:
    with database.session() as session:
        asset = session.scalar(
            select(FileAsset).where(
                FileAsset.enterprise_id == actor.enterprise_id,
                FileAsset.id == asset_id,
                FileAsset.status == "active",
            )
        )
        if asset is None or not _file_visible(database, actor, asset):
            raise ApiProblem(
                status_code=404,
                code="platform.file_asset_not_found",
                message="文件资产不存在",
            )
        try:
            content = storage.get(asset.storage_provider, asset.object_key)
        except ObjectStorageError as exc:
            raise ApiProblem(
                status_code=404,
                code="platform.file_object_missing",
                message="文件对象不存在",
            ) from exc
        if sha256(content).hexdigest() != asset.checksum_sha256:
            raise ApiProblem(
                status_code=409,
                code="platform.file_checksum_mismatch",
                message="文件完整性校验失败",
            )
        session.expunge(asset)
        return asset, content


def list_bulk_exchanges(database: Database, *, enterprise_id: str) -> BulkExchangeListResponse:
    with database.session() as session:
        jobs = list(
            session.scalars(
                select(BulkExchangeJob)
                .where(BulkExchangeJob.enterprise_id == enterprise_id)
                .order_by(BulkExchangeJob.created_at.desc())
                .limit(200)
            )
        )
    return BulkExchangeListResponse(
        datasets=SUPPORTED_EXCHANGE_DATASETS,
        items=[_exchange_job_view(item) for item in jobs],
        generated_at=utc_now(),
    )


def bulk_exchange_detail(
    database: Database, *, enterprise_id: str, job_id: str
) -> BulkExchangeDetailResponse:
    with database.session() as session:
        job = _exchange_job(session, enterprise_id, job_id)
        rows = list(
            session.scalars(
                select(BulkExchangeRow)
                .where(BulkExchangeRow.exchange_job_id == job.id)
                .order_by(BulkExchangeRow.row_number)
                .limit(1000)
            )
        )
        return BulkExchangeDetailResponse(
            job=_exchange_job_view(job),
            rows=[_exchange_row_view(item) for item in rows],
        )


def preflight_bulk_exchange(
    database: Database,
    *,
    actor: ActorContext,
    payload: BulkExchangePreflightRequest,
) -> BulkExchangeMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    with database.session() as session:
        existing = session.scalar(
            select(BulkExchangeJob).where(
                BulkExchangeJob.enterprise_id == actor.enterprise_id,
                BulkExchangeJob.idempotency_key == payload.client_request_key,
            )
        )
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if existing is not None or replay is not None:
            if existing is None or replay is None:
                raise ApiProblem(
                    status_code=409,
                    code="platform.exchange_replay_incomplete",
                    message="批量请求记录不完整",
                )
            _assert_replay(replay, payload_hash, "platform.exchange_idempotency_conflict")
            return BulkExchangeMutationResponse(
                job=_exchange_job_view(existing), event_id=replay.id, replayed=True
            )
        parsed_rows = _parse_dictionary_csv(session, actor.enterprise_id, payload.content)
        now = utc_now()
        valid_count = sum(row[2] == "valid" for row in parsed_rows)
        invalid_count = len(parsed_rows) - valid_count
        job = BulkExchangeJob(
            id=f"bulk_exchange_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            operation="import",
            dataset_key=payload.dataset_key,
            file_format=payload.file_format,
            status="ready" if invalid_count == 0 else "validation_failed",
            file_asset_id=None,
            total_rows=len(parsed_rows),
            valid_rows=valid_count,
            invalid_rows=invalid_count,
            applied_rows=0,
            validation_summary={
                "required_columns": [
                    "dictionary_key",
                    "item_key",
                    "label",
                    "value",
                    "sort_order",
                    "status",
                ],
                "valid": valid_count,
                "invalid": invalid_count,
            },
            requested_by_principal_id=actor.principal_id,
            idempotency_key=payload.client_request_key,
            created_at=now,
            completed_at=now if invalid_count else None,
        )
        session.add(job)
        session.flush()
        for row_number, source, row_status, normalized, errors in parsed_rows:
            session.add(
                BulkExchangeRow(
                    id=f"bulk_exchange_row_{uuid4().hex}",
                    exchange_job_id=job.id,
                    row_number=row_number,
                    source_data=source,
                    normalized_data=normalized,
                    status=row_status,
                    errors=errors,
                )
            )
        event = _add_operation_event(
            session,
            actor=actor,
            event_type="platform.exchange.preflighted",
            target_type="bulk_exchange_job",
            target_id=job.id,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"job_id": job.id, "valid": valid_count, "invalid": invalid_count},
            now=now,
        )
        session.commit()
        return BulkExchangeMutationResponse(
            job=_exchange_job_view(job), event_id=event.id, replayed=False
        )


def commit_bulk_exchange(
    database: Database,
    *,
    actor: ActorContext,
    job_id: str,
    payload: BulkExchangeCommitRequest,
) -> BulkExchangeMutationResponse:
    payload_hash = _payload_hash({**payload.model_dump(mode="json"), "job_id": job_id})
    with database.session() as session:
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if replay is not None:
            _assert_replay(replay, payload_hash, "platform.exchange_commit_idempotency_conflict")
            return BulkExchangeMutationResponse(
                job=_exchange_job_view(_exchange_job(session, actor.enterprise_id, job_id)),
                event_id=replay.id,
                replayed=True,
            )
        job = _exchange_job(session, actor.enterprise_id, job_id)
        if job.status != "ready" or job.invalid_rows:
            raise ApiProblem(
                status_code=409,
                code="platform.exchange_not_ready",
                message="批量任务未通过预检",
            )
        rows = list(
            session.scalars(
                select(BulkExchangeRow)
                .where(
                    BulkExchangeRow.exchange_job_id == job.id,
                    BulkExchangeRow.status == "valid",
                )
                .order_by(BulkExchangeRow.row_number)
            )
        )
        applied = 0
        now = utc_now()
        for row in rows:
            data = row.normalized_data
            dictionary = session.scalar(
                select(PlatformDictionaryType).where(
                    PlatformDictionaryType.enterprise_id == actor.enterprise_id,
                    PlatformDictionaryType.dictionary_key == str(data["dictionary_key"]),
                )
            )
            if dictionary is None:
                raise ApiProblem(
                    status_code=409,
                    code="platform.exchange_dictionary_missing",
                    message="预检后的字典已不存在",
                )
            item = session.scalar(
                select(PlatformDictionaryItem).where(
                    PlatformDictionaryItem.dictionary_type_id == dictionary.id,
                    PlatformDictionaryItem.item_key == str(data["item_key"]),
                )
            )
            if item is None:
                item = PlatformDictionaryItem(
                    id=f"dictionary_item_{uuid4().hex}",
                    enterprise_id=actor.enterprise_id,
                    dictionary_type_id=dictionary.id,
                    item_key=str(data["item_key"]),
                    label=str(data["label"]),
                    value=data["value"],
                    sort_order=_int_value(data["sort_order"]),
                    status=str(data["status"]),
                    revision=1,
                    updated_at=now,
                )
                session.add(item)
            else:
                item.label = str(data["label"])
                item.value = data["value"]
                item.sort_order = _int_value(data["sort_order"])
                item.status = str(data["status"])
                item.revision += 1
                item.updated_at = now
            row.status = "applied"
            applied += 1
        job.status = "succeeded"
        job.applied_rows = applied
        job.completed_at = now
        event = _add_operation_event(
            session,
            actor=actor,
            event_type="platform.exchange.committed",
            target_type="bulk_exchange_job",
            target_id=job.id,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"job_id": job.id, "applied_rows": applied},
            now=now,
        )
        session.commit()
        return BulkExchangeMutationResponse(
            job=_exchange_job_view(job), event_id=event.id, replayed=False
        )


def export_bulk_exchange(
    database: Database,
    *,
    actor: ActorContext,
    payload: BulkExchangeExportRequest,
    storage: ObjectStorageRegistry,
) -> BulkExchangeMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    with database.session() as session:
        existing = session.scalar(
            select(BulkExchangeJob).where(
                BulkExchangeJob.enterprise_id == actor.enterprise_id,
                BulkExchangeJob.idempotency_key == payload.client_request_key,
            )
        )
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if existing is not None or replay is not None:
            if existing is None or replay is None:
                raise ApiProblem(
                    status_code=409,
                    code="platform.exchange_replay_incomplete",
                    message="批量请求记录不完整",
                )
            _assert_replay(replay, payload_hash, "platform.exchange_idempotency_conflict")
            return BulkExchangeMutationResponse(
                job=_exchange_job_view(existing), event_id=replay.id, replayed=True
            )
        rows = list(
            session.execute(
                select(PlatformDictionaryType, PlatformDictionaryItem)
                .join(
                    PlatformDictionaryItem,
                    PlatformDictionaryItem.dictionary_type_id == PlatformDictionaryType.id,
                )
                .where(PlatformDictionaryType.enterprise_id == actor.enterprise_id)
                .order_by(
                    PlatformDictionaryType.dictionary_key,
                    PlatformDictionaryItem.sort_order,
                    PlatformDictionaryItem.item_key,
                )
            )
        )
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["dictionary_key", "item_key", "label", "value", "sort_order", "status"])
        for dictionary, item in rows:
            writer.writerow(
                [
                    dictionary.dictionary_key,
                    item.item_key,
                    item.label,
                    json.dumps(item.value, ensure_ascii=False),
                    item.sort_order,
                    item.status,
                ]
            )
        content = stream.getvalue().encode("utf-8-sig")
        now = utc_now()
        object_key = f"{actor.enterprise_id}/{uuid4().hex}"
        try:
            storage.put(object_key, content)
        except ObjectStorageError as exc:
            raise ApiProblem(
                status_code=503,
                code="platform.file_storage_unavailable",
                message="文件存储暂不可用",
            ) from exc
        asset = FileAsset(
            id=f"file_asset_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            asset_key=f"dictionary-export-{uuid4().hex[:12]}",
            file_name=f"platform-dictionary-{now:%Y%m%d-%H%M%S}.csv",
            media_type="text/csv",
            size_bytes=len(content),
            checksum_sha256=sha256(content).hexdigest(),
            storage_provider=storage.provider_key,
            object_key=object_key,
            category="exchange",
            status="active",
            uploaded_by_principal_id=actor.principal_id,
            required_permission="bulk.exchange.read",
            scope_type="enterprise",
            scope_id=actor.enterprise_id,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        session.add(asset)
        session.flush()
        job = BulkExchangeJob(
            id=f"bulk_exchange_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            operation="export",
            dataset_key=payload.dataset_key,
            file_format=payload.file_format,
            status="succeeded",
            file_asset_id=asset.id,
            total_rows=len(rows),
            valid_rows=len(rows),
            invalid_rows=0,
            applied_rows=len(rows),
            validation_summary={"file_asset_id": asset.id, "exported_rows": len(rows)},
            requested_by_principal_id=actor.principal_id,
            idempotency_key=payload.client_request_key,
            created_at=now,
            completed_at=now,
        )
        session.add(job)
        event = _add_operation_event(
            session,
            actor=actor,
            event_type="platform.exchange.exported",
            target_type="bulk_exchange_job",
            target_id=job.id,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"job_id": job.id, "file_asset_id": asset.id, "rows": len(rows)},
            now=now,
        )
        session.commit()
        return BulkExchangeMutationResponse(
            job=_exchange_job_view(job), event_id=event.id, replayed=False
        )


def access_governance_overview(
    database: Database, *, enterprise_id: str
) -> AccessGovernanceResponse:
    with database.session() as session:
        orgs = list(
            session.scalars(
                select(OrgUnit).where(OrgUnit.enterprise_id == enterprise_id).order_by(OrgUnit.name)
            )
        )
        memberships = list(
            session.scalars(
                select(Membership).where(
                    Membership.enterprise_id == enterprise_id,
                    Membership.status == "active",
                )
            )
        )
        principal_rows = list(
            session.execute(
                select(Principal, UserAccount, OrgUnit, Position)
                .join(UserAccount, UserAccount.principal_id == Principal.id)
                .join(
                    Membership,
                    (Membership.principal_id == Principal.id)
                    & Membership.is_primary.is_(True)
                    & (Membership.status == "active"),
                )
                .join(OrgUnit, OrgUnit.id == Membership.org_unit_id)
                .join(Position, Position.id == Membership.position_id)
                .where(Principal.enterprise_id == enterprise_id)
                .order_by(Principal.display_name)
            )
        )
        delegations = list(
            session.scalars(
                select(AccessDelegation)
                .where(AccessDelegation.enterprise_id == enterprise_id)
                .order_by(AccessDelegation.created_at.desc())
            )
        )
        principals = {
            item.id: item
            for item in session.scalars(
                select(Principal).where(Principal.enterprise_id == enterprise_id)
            )
        }
        permissions = list(
            session.scalars(
                select(PermissionDefinition.permission_key)
                .where(PermissionDefinition.status == "active")
                .order_by(PermissionDefinition.permission_key)
            )
        )
    counts: dict[str, int] = {}
    for membership in memberships:
        counts[membership.org_unit_id] = counts.get(membership.org_unit_id, 0) + 1
    return AccessGovernanceResponse(
        org_tree=_build_org_tree(orgs, counts),
        principals=[
            PrincipalOption(
                id=principal.id,
                display_name=principal.display_name,
                account_key=account.account_key,
                organization=org.name,
                position=position.name,
            )
            for principal, account, org, position in principal_rows
        ],
        delegations=[_delegation_view(item, principals) for item in delegations],
        permission_catalog=permissions,
        generated_at=utc_now(),
    )


def create_access_delegation(
    database: Database,
    *,
    actor: ActorContext,
    payload: AccessDelegationCreateRequest,
) -> AccessDelegationMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = utc_now()
    with database.session() as session:
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if replay is not None:
            _assert_replay(replay, payload_hash, "identity.delegation_idempotency_conflict")
            delegation = session.get(AccessDelegation, str(replay.attributes["delegation_id"]))
            if delegation is None:
                raise ApiProblem(
                    status_code=500,
                    code="identity.delegation_replay_missing",
                    message="委托记录不存在",
                )
            principals = _principal_map(session, actor.enterprise_id)
            return AccessDelegationMutationResponse(
                delegation=_delegation_view(delegation, principals),
                event_id=replay.id,
                replayed=True,
            )
        if payload.delegator_principal_id == payload.delegatee_principal_id:
            raise ApiProblem(
                status_code=422,
                code="identity.delegation_self_invalid",
                message="委托人与被委托人不能相同",
            )
        if payload.valid_to <= payload.valid_from or payload.valid_to <= now:
            raise ApiProblem(
                status_code=422,
                code="identity.delegation_period_invalid",
                message="委托有效期无效",
            )
        principals = _principal_map(session, actor.enterprise_id)
        if (
            payload.delegator_principal_id not in principals
            or payload.delegatee_principal_id not in principals
        ):
            raise ApiProblem(
                status_code=422,
                code="identity.delegation_principal_invalid",
                message="委托主体不存在",
            )
        direct_permissions, direct_scopes, _, _ = _principal_access_material(
            session, actor.enterprise_id, payload.delegator_principal_id, now
        )
        requested = sorted(set(payload.permissions))
        if len(requested) != len(payload.permissions) or not set(requested).issubset(
            direct_permissions
        ):
            raise ApiProblem(
                status_code=422,
                code="identity.delegation_permission_invalid",
                message="委托权限必须是委托人的直接有效权限子集",
            )
        _validate_delegation_scopes(payload.scopes, direct_scopes)
        duplicate = session.scalar(
            select(AccessDelegation).where(
                AccessDelegation.enterprise_id == actor.enterprise_id,
                AccessDelegation.delegation_key == payload.delegation_key,
            )
        )
        if duplicate is not None:
            raise ApiProblem(
                status_code=409,
                code="identity.delegation_key_conflict",
                message="委托标识已存在",
            )
        delegation = AccessDelegation(
            id=f"access_delegation_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            delegation_key=payload.delegation_key,
            delegator_principal_id=payload.delegator_principal_id,
            delegatee_principal_id=payload.delegatee_principal_id,
            permissions=requested,
            scopes=payload.scopes,
            status="active" if payload.valid_from <= now else "scheduled",
            valid_from=payload.valid_from,
            valid_to=payload.valid_to,
            reason=payload.reason,
            revision=1,
            created_by_principal_id=actor.principal_id,
            created_at=now,
            updated_at=now,
        )
        session.add(delegation)
        event = _add_operation_event(
            session,
            actor=actor,
            event_type="identity.access_delegation.created",
            target_type="access_delegation",
            target_id=delegation.id,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"delegation_id": delegation.id, "permissions": requested},
            now=now,
        )
        session.commit()
        return AccessDelegationMutationResponse(
            delegation=_delegation_view(delegation, principals),
            event_id=event.id,
            replayed=False,
        )


def revoke_access_delegation(
    database: Database,
    *,
    actor: ActorContext,
    delegation_id: str,
    payload: AccessDelegationRevokeRequest,
) -> AccessDelegationMutationResponse:
    payload_hash = _payload_hash({**payload.model_dump(mode="json"), "id": delegation_id})
    with database.session() as session:
        replay = _operation_replay(session, actor.enterprise_id, payload.client_request_key)
        if replay is not None:
            _assert_replay(replay, payload_hash, "identity.delegation_revoke_conflict")
            delegation = session.get(AccessDelegation, delegation_id)
            if delegation is None:
                raise ApiProblem(
                    status_code=404,
                    code="identity.delegation_not_found",
                    message="临时委托不存在",
                )
            return AccessDelegationMutationResponse(
                delegation=_delegation_view(
                    delegation, _principal_map(session, actor.enterprise_id)
                ),
                event_id=replay.id,
                replayed=True,
            )
        delegation = session.scalar(
            select(AccessDelegation).where(
                AccessDelegation.enterprise_id == actor.enterprise_id,
                AccessDelegation.id == delegation_id,
            )
        )
        if delegation is None:
            raise ApiProblem(
                status_code=404,
                code="identity.delegation_not_found",
                message="临时委托不存在",
            )
        if delegation.revision != payload.expected_revision:
            raise ApiProblem(
                status_code=409,
                code="identity.delegation_revision_conflict",
                message="临时委托已更新，请刷新后重试",
            )
        if delegation.status == "revoked":
            raise ApiProblem(
                status_code=409,
                code="identity.delegation_already_revoked",
                message="临时委托已撤销",
            )
        delegation.status = "revoked"
        delegation.revision += 1
        delegation.updated_at = utc_now()
        event = _add_operation_event(
            session,
            actor=actor,
            event_type="identity.access_delegation.revoked",
            target_type="access_delegation",
            target_id=delegation.id,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            attributes={"delegation_id": delegation.id},
        )
        principals = _principal_map(session, actor.enterprise_id)
        session.commit()
        return AccessDelegationMutationResponse(
            delegation=_delegation_view(delegation, principals),
            event_id=event.id,
            replayed=False,
        )


def explain_principal_permissions(
    database: Database, *, enterprise_id: str, principal_id: str
) -> PermissionExplanationResponse:
    now = utc_now()
    with database.session() as session:
        principal = session.scalar(
            select(Principal).where(
                Principal.enterprise_id == enterprise_id,
                Principal.id == principal_id,
            )
        )
        if principal is None:
            raise ApiProblem(
                status_code=404,
                code="identity.principal_not_found",
                message="企业主体不存在",
            )
        direct, scopes, roles, _ = _principal_access_material(
            session, enterprise_id, principal_id, now
        )
        delegations = list(
            session.scalars(
                select(AccessDelegation).where(
                    AccessDelegation.enterprise_id == enterprise_id,
                    AccessDelegation.delegatee_principal_id == principal_id,
                    AccessDelegation.status.in_(("active", "scheduled")),
                    AccessDelegation.valid_from <= now,
                    AccessDelegation.valid_to > now,
                )
            )
        )
        delegated = sorted({key for item in delegations for key in item.permissions})
        delegated_scopes = [scope for item in delegations for scope in item.scopes]
        return PermissionExplanationResponse(
            principal_id=principal.id,
            principal_name=principal.display_name,
            direct_roles=roles,
            direct_permissions=sorted(direct),
            delegated_permissions=delegated,
            effective_permissions=sorted(direct | set(delegated)),
            scopes=[*scopes, *delegated_scopes],
            active_delegations=[item.delegation_key for item in delegations],
            generated_at=now,
        )


def _job_view(job: BackgroundJob) -> BackgroundJobView:
    return BackgroundJobView(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        priority=job.priority,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        continuation_count=job.continuation_count,
        continuation_progress=job.continuation_progress,
        initiator_id=job.initiator_id,
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        request_id=job.request_id,
        run_id=job.run_id,
        worker_id=job.worker_id,
        last_error_code=job.last_error_code,
        last_error_message=job.last_error_message,
        created_at=_as_utc(job.created_at),
        updated_at=_as_utc(job.updated_at),
        finished_at=_optional_utc(job.finished_at),
    )


def _enterprise_job(session: Session, enterprise_id: str, job_id: str) -> BackgroundJob:
    job = session.scalar(
        select(BackgroundJob).where(
            BackgroundJob.enterprise_id == enterprise_id,
            BackgroundJob.id == job_id,
        )
    )
    if job is None:
        raise ApiProblem(status_code=404, code="platform.job_not_found", message="后台任务不存在")
    return job


def _parameter_view(item: PlatformParameter) -> ParameterView:
    return ParameterView(
        parameter_key=item.parameter_key,
        group_key=item.group_key,
        label=item.label,
        value_type=item.value_type,
        value=item.value,
        status=item.status,
        revision=item.revision,
        updated_at=_as_utc(item.updated_at),
    )


def _dictionary_item_view(item: PlatformDictionaryItem) -> DictionaryItemView:
    return DictionaryItemView(
        item_key=item.item_key,
        label=item.label,
        value=item.value,
        sort_order=item.sort_order,
        status=item.status,
        revision=item.revision,
    )


def _notification_view(item: Notification, deliveries: dict[str, str]) -> NotificationView:
    return NotificationView(
        id=item.id,
        category=item.category,
        title=item.title,
        body=item.body,
        severity=item.severity,
        status=item.status,
        action_route=item.action_route,
        created_at=_as_utc(item.created_at),
        read_at=_optional_utc(item.read_at),
        deliveries=deliveries,
    )


def _file_view(asset: FileAsset, uploader_name: str) -> FileAssetView:
    return FileAssetView(
        id=asset.id,
        asset_key=asset.asset_key,
        file_name=asset.file_name,
        media_type=asset.media_type,
        size_bytes=asset.size_bytes,
        checksum_sha256=asset.checksum_sha256,
        storage_provider=asset.storage_provider,
        category=asset.category,
        status=asset.status,
        uploader_name=uploader_name,
        required_permission=asset.required_permission,
        scope_type=asset.scope_type,
        scope_id=asset.scope_id,
        revision=asset.revision,
        created_at=_as_utc(asset.created_at),
    )


def _file_visible(database: Database, actor: ActorContext, asset: FileAsset) -> bool:
    return asset.required_permission in actor.permissions and actor_scope_allows(
        actor,
        scope_type=asset.scope_type,
        scope_id=asset.scope_id,
        database=database,
    )


def _exchange_job_view(job: BulkExchangeJob) -> BulkExchangeJobView:
    return BulkExchangeJobView(
        id=job.id,
        operation=job.operation,
        dataset_key=job.dataset_key,
        file_format=job.file_format,
        status=job.status,
        total_rows=job.total_rows,
        valid_rows=job.valid_rows,
        invalid_rows=job.invalid_rows,
        applied_rows=job.applied_rows,
        validation_summary=dict(job.validation_summary),
        created_at=_as_utc(job.created_at),
        completed_at=_optional_utc(job.completed_at),
    )


def _exchange_row_view(row: BulkExchangeRow) -> BulkExchangeRowView:
    return BulkExchangeRowView(
        row_number=row.row_number,
        status=row.status,
        normalized_data=dict(row.normalized_data),
        errors=list(row.errors),
    )


def _exchange_job(session: Session, enterprise_id: str, job_id: str) -> BulkExchangeJob:
    job = session.scalar(
        select(BulkExchangeJob).where(
            BulkExchangeJob.enterprise_id == enterprise_id,
            BulkExchangeJob.id == job_id,
        )
    )
    if job is None:
        raise ApiProblem(
            status_code=404,
            code="platform.exchange_not_found",
            message="批量任务不存在",
        )
    return job


def _build_org_tree(orgs: list[OrgUnit], counts: dict[str, int]) -> list[OrgTreeNode]:
    children: dict[str | None, list[OrgUnit]] = {}
    for org in orgs:
        children.setdefault(org.parent_org_unit_id, []).append(org)

    def build(org: OrgUnit) -> OrgTreeNode:
        return OrgTreeNode(
            id=org.id,
            org_key=org.org_key,
            name=org.name,
            unit_type=org.unit_type,
            status=org.status,
            member_count=counts.get(org.id, 0),
            children=[
                build(item) for item in sorted(children.get(org.id, []), key=lambda x: x.name)
            ],
        )

    return [build(item) for item in sorted(children.get(None, []), key=lambda x: x.name)]


def _delegation_view(
    item: AccessDelegation, principals: dict[str, Principal]
) -> AccessDelegationView:
    delegator = principals.get(item.delegator_principal_id)
    delegatee = principals.get(item.delegatee_principal_id)
    now = utc_now()
    valid_from = _as_utc(item.valid_from)
    valid_to = _as_utc(item.valid_to)
    status = item.status
    if status in {"active", "scheduled"} and valid_to <= now:
        status = "expired"
    elif status == "scheduled" and valid_from <= now:
        status = "active"
    return AccessDelegationView(
        id=item.id,
        delegation_key=item.delegation_key,
        delegator_principal_id=item.delegator_principal_id,
        delegator_name=delegator.display_name if delegator else "未知",
        delegatee_principal_id=item.delegatee_principal_id,
        delegatee_name=delegatee.display_name if delegatee else "未知",
        permissions=list(item.permissions),
        scopes=list(item.scopes),
        status=status,
        valid_from=valid_from,
        valid_to=valid_to,
        reason=item.reason,
        revision=item.revision,
        created_at=_as_utc(item.created_at),
    )


def _principal_map(session: Session, enterprise_id: str) -> dict[str, Principal]:
    return {
        item.id: item
        for item in session.scalars(
            select(Principal).where(Principal.enterprise_id == enterprise_id)
        )
    }


def _principal_access_material(
    session: Session,
    enterprise_id: str,
    principal_id: str,
    now: datetime,
) -> tuple[set[str], list[dict[str, object]], list[str], list[str]]:
    assignments = list(
        session.scalars(
            select(RoleAssignment).where(
                RoleAssignment.enterprise_id == enterprise_id,
                RoleAssignment.principal_id == principal_id,
                RoleAssignment.status == "active",
                RoleAssignment.valid_from <= now,
                or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to > now),
            )
        )
    )
    role_ids = [item.access_role_id for item in assignments]
    roles = (
        list(
            session.scalars(
                select(AccessRole).where(AccessRole.id.in_(role_ids), AccessRole.status == "active")
            )
        )
        if role_ids
        else []
    )
    rows = (
        list(
            session.execute(
                select(PermissionDefinition.permission_key, AccessRolePermission.effect)
                .join(
                    AccessRolePermission,
                    AccessRolePermission.permission_id == PermissionDefinition.id,
                )
                .where(
                    AccessRolePermission.access_role_id.in_(role_ids),
                    PermissionDefinition.status == "active",
                )
            )
        )
        if role_ids
        else []
    )
    allowed = {key for key, effect in rows if effect == "allow"}
    denied = {key for key, effect in rows if effect == "deny"}
    assignment_ids = [item.id for item in assignments]
    grants = (
        list(
            session.scalars(
                select(ScopeGrant).where(
                    ScopeGrant.role_assignment_id.in_(assignment_ids),
                    ScopeGrant.valid_from <= now,
                    or_(ScopeGrant.valid_to.is_(None), ScopeGrant.valid_to > now),
                )
            )
        )
        if assignment_ids
        else []
    )
    scopes: list[dict[str, object]] = [
        cast(
            dict[str, object],
            {
                "scope_type": grant.scope_type,
                "scope_ids": list(grant.scope_ids),
                "effect": grant.effect,
            },
        )
        for grant in grants
    ]
    return allowed - denied, scopes, sorted(item.role_key for item in roles), assignment_ids


def _validate_delegation_scopes(
    requested: list[dict[str, object]], direct: list[dict[str, object]]
) -> None:
    direct_pairs = {
        (str(scope.get("scope_type")), str(scope_id))
        for scope in direct
        if scope.get("effect") == "allow"
        for scope_id in cast(list[object], scope.get("scope_ids", []))
    }
    enterprise_allowed = any(pair[0] == "enterprise" for pair in direct_pairs)
    for scope in requested:
        scope_type = str(scope.get("scope_type", ""))
        scope_ids = scope.get("scope_ids")
        if not scope_type or not isinstance(scope_ids, list) or not scope_ids:
            raise ApiProblem(
                status_code=422,
                code="identity.delegation_scope_invalid",
                message="委托范围格式无效",
            )
        if not enterprise_allowed and any(
            (scope_type, str(item)) not in direct_pairs for item in scope_ids
        ):
            raise ApiProblem(
                status_code=422,
                code="identity.delegation_scope_exceeded",
                message="委托范围必须是委托人的直接有效范围子集",
            )


def _parse_dictionary_csv(
    session: Session, enterprise_id: str, content: str
) -> list[tuple[int, dict[str, object], str, dict[str, object], list[dict[str, object]]]]:
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
    required = {"dictionary_key", "item_key", "label", "value", "sort_order", "status"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise ApiProblem(
            status_code=422,
            code="platform.exchange_columns_invalid",
            message="CSV 字段不完整",
            details={"required_columns": sorted(required)},
        )
    dictionary_keys = set(
        session.scalars(
            select(PlatformDictionaryType.dictionary_key).where(
                PlatformDictionaryType.enterprise_id == enterprise_id
            )
        )
    )
    result = []
    for row_number, raw in enumerate(reader, start=2):
        source: dict[str, object] = {str(key): str(value or "") for key, value in raw.items()}
        errors: list[dict[str, object]] = []
        dictionary_key = str(source["dictionary_key"]).strip()
        item_key = str(source["item_key"]).strip()
        label = str(source["label"]).strip()
        status = str(source["status"]).strip().casefold()
        if dictionary_key not in dictionary_keys:
            errors.append({"field": "dictionary_key", "code": "not_found"})
        if not item_key:
            errors.append({"field": "item_key", "code": "required"})
        if not label:
            errors.append({"field": "label", "code": "required"})
        if status not in {"active", "inactive"}:
            errors.append({"field": "status", "code": "invalid"})
        try:
            sort_order = int(str(source["sort_order"] or "0"))
            if sort_order < 0:
                raise ValueError
        except ValueError:
            sort_order = 0
            errors.append({"field": "sort_order", "code": "invalid"})
        try:
            value: object = json.loads(str(source["value"]))
        except json.JSONDecodeError:
            value = source["value"]
        normalized = {
            "dictionary_key": dictionary_key,
            "item_key": item_key,
            "label": label,
            "value": value,
            "sort_order": sort_order,
            "status": status,
        }
        result.append((row_number, source, "invalid" if errors else "valid", normalized, errors))
    if not result:
        raise ApiProblem(
            status_code=422,
            code="platform.exchange_empty",
            message="CSV 没有数据行",
        )
    return result


def _validate_parameter_value(value_type: str, value: object) -> None:
    valid = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "json": isinstance(value, dict | list),
    }.get(value_type, False)
    if not valid:
        raise ApiProblem(
            status_code=422,
            code="platform.parameter_value_invalid",
            message="平台参数值类型不匹配",
            details={"value_type": value_type},
        )


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return int(str(value))


def _decode_file(content_base64: str) -> bytes:
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ApiProblem(
            status_code=422,
            code="platform.file_content_invalid",
            message="文件内容不是有效的 Base64 数据",
        ) from exc
    if not content or len(content) > MAX_FILE_BYTES:
        raise ApiProblem(
            status_code=422,
            code="platform.file_size_invalid",
            message="文件大小必须在 1 字节到 10 MB 之间",
        )
    return content


def _operation_replay(
    session: Session, enterprise_id: str, idempotency_key: str
) -> PlatformOperationEvent | None:
    return session.scalar(
        select(PlatformOperationEvent).where(
            PlatformOperationEvent.enterprise_id == enterprise_id,
            PlatformOperationEvent.idempotency_key == idempotency_key,
        )
    )


def _assert_replay(event: PlatformOperationEvent, payload_hash: str, code: str) -> None:
    if event.payload_hash != payload_hash:
        raise ApiProblem(
            status_code=409,
            code=code,
            message="该请求键已用于不同操作",
        )


def _add_operation_event(
    session: Session,
    *,
    actor: ActorContext,
    event_type: str,
    target_type: str,
    target_id: str,
    reason: str,
    idempotency_key: str,
    payload_hash: str,
    attributes: dict[str, object],
    now: datetime | None = None,
) -> PlatformOperationEvent:
    event = PlatformOperationEvent(
        id=f"platform_operation_event_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        actor_principal_id=actor.principal_id,
        reason=reason,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        attributes=attributes,
        request_id=actor.request_id,
        run_id=actor.run_id,
        occurred_at=now or utc_now(),
    )
    session.add(event)
    return event


def _payload_hash(payload: dict[str, object]) -> str:
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(material.encode()).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _optional_utc(value: datetime | None) -> datetime | None:
    return _as_utc(value) if value is not None else None
