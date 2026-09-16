"""Queue-only, explicitly versioned replay of one existing Raw page."""

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from zhixing_connectors.catalog import can_project_to_core, resource_spec
from zhixing_jobs import JobRepository
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
from zhixing_api.scope_context import build_scope_context

from .mapping import MAPPING_VERSION


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    client_request_key: str = Field(min_length=1, max_length=96)
    expected_content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_mapping_version: str = Field(min_length=1, max_length=32)


def enqueue_replay(database: Database, actor: ActorContext, manifest_id: str,
                   payload: ReplayRequest) -> SyncRun:
    require_permission(actor, "source.manage", database, resource_type="raw-replay",
                       resource_key=manifest_id, scope_type="enterprise",
                       scope_id=actor.enterprise_id)
    scope = build_scope_context(database, actor).snapshot()
    now = datetime.now(UTC)
    with database.session() as session:
        row = session.execute(select(RawPageManifest, SourceResource, ExternalSystem)
            .join(SyncResourceRun, SyncResourceRun.id == RawPageManifest.sync_resource_run_id)
            .join(SyncRun, SyncRun.id == SyncResourceRun.sync_run_id)
            .join(SourceResource, SourceResource.id == SyncResourceRun.source_resource_id)
            .join(ExternalSystem, ExternalSystem.id == SourceResource.external_system_id)
            .where(RawPageManifest.id == manifest_id, SyncRun.enterprise_id == actor.enterprise_id,
                   ExternalSystem.enterprise_id == actor.enterprise_id,
                   SyncRun.external_system_id == ExternalSystem.id)).first()
        if row is None:
            raise ApiProblem(status_code=404, code="replay.manifest_missing",
                             message="Raw 页不存在")
        manifest, resource, source = row
        mirror = session.get(SourceMirrorPage, manifest_id)
        # Serialize commands for this source before checking request-key reuse.
        session.refresh(source, with_for_update=True)
        spec = resource_spec(resource.resource_key)
        if (spec is None or not can_project_to_core(spec) or not resource.enabled
                or resource.schema_status != "confirmed" or source.status == "disabled"
                or manifest.fetched_at is None or not manifest.storage_key.endswith(".json.gz")
                or (mirror is not None
                    and mirror.schema_status in {"scope_invalid", "schema_invalid"})):
            raise ApiProblem(status_code=409, code="replay.unavailable",
                             message="该 Raw 页不可规范重放")
        if (manifest.content_hash != payload.expected_content_hash
                or payload.expected_mapping_version != MAPPING_VERSION):
            raise ApiProblem(status_code=409, code="replay.version_changed",
                             message="内容或映射版本已变化")
        key = "replay:" + hashlib.sha256(json.dumps([
            actor.enterprise_id, source.id, payload.client_request_key]).encode()).hexdigest()
        fingerprint = hashlib.sha256(json.dumps({"manifest": manifest_id,
            "hash": manifest.content_hash, "mapping": MAPPING_VERSION,
            "scope_version": scope["scope_version"]}, sort_keys=True).encode()).hexdigest()
        existing = session.scalar(select(SyncRun).where(SyncRun.idempotency_key == key,
            SyncRun.enterprise_id == actor.enterprise_id))
        if existing is not None:
            if existing.command_fingerprint != fingerprint:
                raise ApiProblem(status_code=409, code="replay.request_key_reused",
                                 message="请求标识已用于其他重放参数")
            return existing
        if mirror is not None and mirror.projection_run_id:
            active = session.get(SyncRun, mirror.projection_run_id)
            if active is not None and active.status in {"queued", "running"}:
                raise ApiProblem(status_code=409, code="replay.projection_busy",
                                 message="该页规范映射正在执行")
        run = SyncRun(id=f"sync_{uuid4().hex}", enterprise_id=actor.enterprise_id,
            source_version=source.version,
            external_system_id=source.id, status="queued", scenario="raw_replay", started_at=now,
            request_id=actor.request_id, scope_snapshot=scope, idempotency_key=key,
            command_fingerprint=fingerprint)
        session.add(run)
        session.flush()
        if mirror is not None:
            mirror.projection_run_id = run.id
            mirror.mapping_version = MAPPING_VERSION
        command = LingxingSyncCommand(actor.enterprise_id, source.system_key, resource.resource_key,
            partition=f"replay:{run.id}", scope_snapshot=scope).to_enqueue_job(
                initiator_id=actor.principal_id, request_id=actor.request_id, run_id=run.id)
        command = replace(command, idempotency_key=key, actor_snapshot=actor.snapshot(),
            permission_set_version=actor.permission_set_version,
            payload={**command.payload, "source_version": source.version,
                     "raw_replay": {"manifest_id": manifest.id,
                "content_hash": manifest.content_hash, "mapping_version": MAPPING_VERSION}})
        job = JobRepository(database.engine).enqueue_in_session(session, command, now=now)
        run.task_id = job.job.id
        session.add(SyncResourceRun(id=f"resource_run_{uuid4().hex}", sync_run_id=run.id,
            source_resource_id=resource.id, status="queued", partition_key=f"replay:{run.id}"))
        session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=actor.enterprise_id,
            event_type="source.raw_replay_queued", severity="info", title="Raw 重放已排队",
            detail=json.dumps({"manifest_id": manifest.id, "run_id": run.id,
                               "mapping_version": MAPPING_VERSION,
                               "principal_id": actor.principal_id}), occurred_at=now))
        session.commit()
        return run
