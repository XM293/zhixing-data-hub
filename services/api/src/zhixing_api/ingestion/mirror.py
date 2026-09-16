"""Atomic mirror receipts and offline projection commands; no external requests."""
import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, func, select
from sqlalchemy.orm import Session
from zhixing_connectors.catalog import can_project_to_core, resource_spec
from zhixing_jobs import JobRecord, JobRepository
from zhixing_jobs.lingxing import LingxingSyncCommand

from zhixing_api.actor_context import ActorContext, require_permission
from zhixing_api.data_models import (
    ExternalSystem,
    PlatformEvent,
    RawPageManifest,
    SourceMirrorPage,
    SourceResource,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem

from .mapping import MAPPING_VERSION


class MirrorPageView(BaseModel):
    raw_manifest_id: str
    resource_key: str
    acquisition_run_id: str
    projection_run_id: str | None
    projection_status: str
    mapping_version: str | None
    schema_status: str
    fetched_at: datetime | None
    row_count: int
    records_written: int
    content_hash: str


class MirrorQuarantineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    expected_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reason: Literal["scope_invalid", "schema_invalid"]


class MirrorPageList(BaseModel):
    schema_version: Literal[1] = 1
    items: list[MirrorPageView]
    total: int
    offset: int
    limit: int


def list_mirror_pages(session: Session, *, enterprise_id: str, source_id: str,
                      offset: int, limit: int) -> MirrorPageList:
    page = SourceMirrorPage
    predicates = (page.enterprise_id == enterprise_id,
                  ExternalSystem.enterprise_id == enterprise_id,
                  ExternalSystem.id == source_id)
    base = select(page, SourceResource.resource_key, RawPageManifest,
                  SyncRun.status, SyncRun.records_written).join(
        SourceResource, SourceResource.id == page.source_resource_id).join(
        ExternalSystem, ExternalSystem.id == SourceResource.external_system_id).join(
        RawPageManifest, RawPageManifest.id == page.raw_manifest_id).outerjoin(
        SyncRun, (SyncRun.id == page.projection_run_id)
        & (SyncRun.enterprise_id == enterprise_id)).where(*predicates)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(base.order_by(page.created_at.desc(), page.raw_manifest_id)
                           .offset(offset).limit(limit)).all()
    return MirrorPageList(total=total, offset=offset, limit=limit, items=[MirrorPageView(
        raw_manifest_id=mirror.raw_manifest_id, resource_key=resource_key,
        acquisition_run_id=mirror.acquisition_run_id, projection_run_id=mirror.projection_run_id,
        projection_status=state or "schema_pending", mapping_version=mirror.mapping_version,
        schema_status=mirror.schema_status, fetched_at=raw.fetched_at,
        row_count=raw.row_count, records_written=written or 0,
        content_hash=raw.content_hash,
    ) for mirror, resource_key, raw, state, written in rows])


def quarantine_mirror_page(database: Database, actor: ActorContext, manifest_id: str,
                           payload: MirrorQuarantineRequest) -> SourceMirrorPage:
    require_permission(actor, "source.manage", database, resource_type="raw-manifest",
                       resource_key=manifest_id, scope_type="enterprise",
                       scope_id=actor.enterprise_id)
    with database.session() as session:
        row = session.execute(select(SourceMirrorPage, RawPageManifest, SourceResource,
                                     ExternalSystem)
            .join(RawPageManifest, RawPageManifest.id == SourceMirrorPage.raw_manifest_id)
            .join(SourceResource, SourceResource.id == SourceMirrorPage.source_resource_id)
            .join(ExternalSystem, ExternalSystem.id == SourceResource.external_system_id)
            .where(SourceMirrorPage.raw_manifest_id == manifest_id,
                   SourceMirrorPage.enterprise_id == actor.enterprise_id,
                   ExternalSystem.enterprise_id == actor.enterprise_id)).first()
        if row is None:
            raise ApiProblem(status_code=404, code="mirror.page_missing",
                             message="镜像页不存在")
        mirror, manifest, resource, _source = row
        session.refresh(mirror, with_for_update=True)
        if manifest.content_hash != payload.expected_content_hash:
            raise ApiProblem(status_code=409, code="mirror.content_changed",
                             message="Raw 页内容版本已变化")
        if mirror.schema_status in {"scope_invalid", "schema_invalid"}:
            if mirror.schema_status != payload.reason:
                raise ApiProblem(status_code=409, code="mirror.quarantine_conflict",
                                 message="镜像页已按其他原因隔离")
            return cast(SourceMirrorPage, mirror)
        if mirror.projection_run_id:
            projection = session.get(SyncRun, mirror.projection_run_id)
            if projection is not None and projection.status in {"queued", "running"}:
                raise ApiProblem(status_code=409, code="mirror.projection_busy",
                                 message="请先取消正在执行的规范映射")
        mirror.schema_status = payload.reason
        mirror.mapping_version = None
        now = datetime.now(UTC)
        session.add(PlatformEvent(id=f"event_{uuid4().hex}",
            enterprise_id=actor.enterprise_id, event_type="source.raw_page_quarantined",
            severity="warning", title="Raw 页已隔离", detail=json.dumps({
                "manifest_id": manifest_id, "resource_key": resource.resource_key,
                "reason": payload.reason, "principal_id": actor.principal_id,
            }, ensure_ascii=False), occurred_at=now))
        session.commit()
        return cast(SourceMirrorPage, mirror)


def defer_projection(connection: Connection, *, job: JobRecord, manifest_id: str,
                     schema_status: str, scope_snapshot: dict[str, object]) -> None:
    # The caller owns commit/rollback, including the acquisition checkpoint.
    with Session(bind=connection, join_transaction_mode="rollback_only") as session:
        if session.get(SourceMirrorPage, manifest_id) is not None:
            return
        manifest, resource, source, acquisition = session.execute(select(
            RawPageManifest, SourceResource, ExternalSystem, SyncRun)
            .join(SyncResourceRun, SyncResourceRun.id == RawPageManifest.sync_resource_run_id)
            .join(SourceResource, SourceResource.id == SyncResourceRun.source_resource_id)
            .join(ExternalSystem, ExternalSystem.id == SourceResource.external_system_id)
            .join(SyncRun, SyncRun.id == SyncResourceRun.sync_run_id).where(
                RawPageManifest.id == manifest_id, SyncRun.id == job.run_id,
                SyncRun.enterprise_id == job.enterprise_id,
                ExternalSystem.enterprise_id == job.enterprise_id,
                SyncRun.external_system_id == ExternalSystem.id)).one()
        now = datetime.now(UTC)
        spec = resource_spec(resource.resource_key)
        projectable = (schema_status == "confirmed" and spec is not None
                       and can_project_to_core(spec) and manifest.storage_key.endswith(".json.gz"))
        projection_id = None
        if projectable:
            projection_id = f"sync_{uuid4().hex}"
            key = f"mirror:{manifest_id}:{MAPPING_VERSION}"
            run = SyncRun(id=projection_id, enterprise_id=job.enterprise_id,
                external_system_id=source.id, source_version=acquisition.source_version,
                status="queued", scenario="raw_replay", started_at=now,
                request_id=job.request_id, scope_snapshot=scope_snapshot, idempotency_key=key)
            session.add(run)
            session.flush()
            command = LingxingSyncCommand(job.enterprise_id, source.system_key,
                resource.resource_key, partition=f"replay:{projection_id}",
                scope_snapshot=scope_snapshot).to_enqueue_job(
                    initiator_id=job.initiator_id, request_id=job.request_id, run_id=projection_id)
            command = replace(command, idempotency_key=key, actor_snapshot=job.actor_snapshot,
                permission_set_version=job.permission_set_version,
                payload={**command.payload, "source_version": acquisition.source_version,
                    "raw_replay": {"manifest_id": manifest_id,
                        "content_hash": manifest.content_hash, "mapping_version": MAPPING_VERSION}})
            queued = JobRepository(connection.engine).enqueue_in_session(session, command, now=now)
            run.task_id = queued.job.id
            session.add(SyncResourceRun(id=f"resource_run_{uuid4().hex}", sync_run_id=projection_id,
                source_resource_id=resource.id, status="queued",
                partition_key=f"replay:{projection_id}"))
            session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=job.enterprise_id,
                event_type="source.projection_queued", severity="info", title="规范映射已排队",
                detail=f"manifest_id={manifest_id}; run_id={projection_id}", occurred_at=now))
        session.add(SourceMirrorPage(raw_manifest_id=manifest_id, enterprise_id=job.enterprise_id,
            source_resource_id=resource.id, acquisition_run_id=job.run_id,
            projection_run_id=projection_id, schema_status=schema_status,
            mapping_version=MAPPING_VERSION if projectable else None, created_at=now))
        session.flush()
