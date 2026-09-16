from __future__ import annotations

import hashlib
import json
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session
from zhixing_connectors.catalog import (
    resource_spec,
    validate_partition_parameters,
    validate_resource_parameters,
)
from zhixing_jobs.lingxing import LingxingSyncCommand
from zhixing_jobs.models import BackgroundJob
from zhixing_jobs.repository import JobRepository

from zhixing_api.connectors.registry import SYSTEM_TYPE_PROFILES
from zhixing_api.data_center_schemas import SyncRequest
from zhixing_api.data_models import (
    ExternalSystem,
    PlatformEvent,
    SourceResource,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem


def enqueue_sync(
    database: Database, *, enterprise_id: str, source_key: str, initiator_id: str,
    request_id: str, payload: SyncRequest, scope_snapshot: dict[str, object],
    probe: bool = False,
    actor_snapshot: dict[str, object] | None = None,
    provider_enabled: bool = False,
    transaction: Session | None = None,
) -> SyncRun:
    now = datetime.now(UTC)
    with nullcontext(transaction) if transaction is not None else database.session() as session:
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == enterprise_id,
            ExternalSystem.system_key == source_key,
        ).with_for_update())
        if source is None:
            raise LookupError("数据源不存在")
        if source.status == "disabled":
            raise ApiProblem(status_code=409, code="source.disabled", message="数据源已停用")
        lingxing = source.provider_key == "lingxing" or source.system_type == "lingxing"
        if not lingxing and payload.projection_mode == "deferred":
            raise ApiProblem(status_code=422, code="source.projection_mode_unsupported",
                             message="该来源不支持独立映射")
        if lingxing and not provider_enabled:
            raise ApiProblem(status_code=409, code="source.provider_disabled",
                             message="领星接入已停用")
        max_attempts = 3
        resource: SourceResource | None = None
        if not lingxing and source.system_type not in SYSTEM_TYPE_PROFILES:
            raise ApiProblem(status_code=422, code="source.provider_unsupported",
                             message="来源类型未配置执行器")
        if lingxing:
            spec = resource_spec(payload.resource_key)
            if spec is None or not spec.path:
                raise ApiProblem(status_code=422, code="source.resource_unknown",
                                 message="资源不在已确认只读目录内")
            if spec.execution_mode == "async_report":
                max_attempts = 120
            try:
                if spec.window_fields:
                    validate_partition_parameters(spec, dict(payload.resource_parameters))
                else:
                    validate_resource_parameters(spec, dict(payload.resource_parameters))
            except ValueError:
                raise ApiProblem(status_code=422, code="source.parameters_invalid",
                                 message="请填写资源要求的有效查询参数") from None
            resource = session.scalar(select(SourceResource).where(
                SourceResource.external_system_id == source.id,
                SourceResource.resource_key == payload.resource_key,
            ))
            if resource is None or not resource.enabled or not resource.path:
                raise ApiProblem(status_code=422, code="source.resource_disabled",
                                 message="来源资源未启用")
            if spec.mapping_key is None and not probe and (
                    resource.validation_status != "validated"):
                raise ApiProblem(status_code=422, code="source.resource_not_validated",
                                 message="Raw 资源必须先完成单页契约验证")
            maximum_window = timedelta(
                days=1 if len(spec.window_fields) == 1 else spec.max_window_days
            )
            if spec.window_fields and (
                    payload.window_start is None or payload.window_end is None
                    or payload.window_start.tzinfo is None or payload.window_end.tzinfo is None
                    or not timedelta(0) < payload.window_end - payload.window_start
                    <= maximum_window):
                raise ApiProblem(status_code=422, code="source.window_required",
                                 message="该资源同步时间窗口超过官方契约上限")
            if not spec.window_fields and (
                    payload.window_start is not None or payload.window_end is not None):
                raise ApiProblem(status_code=422, code="source.window_unsupported",
                                 message="该资源不接受时间窗口")
        selection = {key: scope_snapshot.get(key) for key in (
            "enterprise_id", "selected_enterprise_ids", "business_unit_ids", "store_ids",
            "warehouse_ids", "scope_version",
        )}
        fingerprint = hashlib.sha256(json.dumps({
            "source": source.id,
            "request": payload.model_dump(mode="json", exclude={"client_request_key"}),
            "selection": selection, "probe": probe,
        }, sort_keys=True).encode()).hexdigest()
        key = "source:" + hashlib.sha256(json.dumps([
            enterprise_id, source.id, payload.client_request_key or uuid4().hex
        ]).encode()).hexdigest()
        existing = session.scalar(select(SyncRun).where(
            SyncRun.enterprise_id == enterprise_id, SyncRun.external_system_id == source.id,
            SyncRun.idempotency_key == key,
        ))
        if existing is not None:
            job = session.get(BackgroundJob, existing.task_id)
            if job is None or job.payload.get("command_fingerprint") != fingerprint:
                raise ApiProblem(status_code=409, code="source.request_key_reused",
                                 message="请求标识已用于其他同步参数")
            return existing
        run = SyncRun(id=f"sync_{uuid4().hex}", enterprise_id=enterprise_id,
                      source_version=source.version,
                      external_system_id=source.id, status="queued", started_at=now,
                      scenario="probe" if probe else payload.scenario,
                      volume_profile=payload.volume_profile, idempotency_key=key,
                      request_id=request_id, scope_snapshot=scope_snapshot)
        session.add(run)
        session.flush()
        command = LingxingSyncCommand(
            enterprise_id, source_key, payload.resource_key, scope_snapshot=scope_snapshot,
            credential_ref=source.credential_ref,
            window_start=payload.window_start.isoformat() if payload.window_start else None,
            window_end=payload.window_end.isoformat() if payload.window_end else None,
            resource_parameters=dict(payload.resource_parameters),
        ).to_enqueue_job(initiator_id=initiator_id, request_id=request_id, run_id=run.id)
        command = replace(command, idempotency_key=key, payload={
            **command.payload, "provider": "lingxing" if lingxing else "mock",
            "source_version": source.version,
            "resource_version": resource.version if resource is not None else None,
            "projection_mode": payload.projection_mode,
            "command_fingerprint": fingerprint, "probe": probe,
        }, priority=100 if probe else command.priority, max_attempts=max_attempts,
            actor_snapshot=actor_snapshot or command.actor_snapshot,
            permission_set_version=str((actor_snapshot or {}).get("permission_set_version")
                                       or command.permission_set_version))
        queued = JobRepository(database.engine).enqueue_in_session(session, command, now=now)
        run.task_id = queued.job.id
        if lingxing and resource is not None:
            session.add(SyncResourceRun(id=f"resource_run_{uuid4().hex}", sync_run_id=run.id,
                source_resource_id=resource.id, status="queued",
                partition_key=str(command.payload["partition"])))
        if probe:
            source.connection_status = "probe_queued"
        session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=enterprise_id,
                    event_type="source.probe_queued" if probe else "source.sync_queued",
                    severity="info", title="来源任务已排队",
                    detail=json.dumps({"run_id": run.id, "task_id": run.task_id,
                                       "principal_id": initiator_id}), occurred_at=now))
        if transaction is None:
            session.commit()
        else:
            session.flush()
        return run
