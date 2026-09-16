"""Offline Raw replay; this module has no HTTP client or credential provider."""

from collections.abc import Callable
from datetime import UTC
from pathlib import Path

from sqlalchemy import select
from zhixing_api.data_models import (
    RawPageManifest,
    SourceMirrorPage,
    SourceResource,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.ingestion.mapping import MAPPING_VERSION
from zhixing_api.ingestion.persistence import persist_canonical_page
from zhixing_connectors.catalog import ResourceSpec, can_project_to_core, response_value
from zhixing_jobs import JobExecutionContext, JobRecord, PermanentJobError

from zhixing_worker.archive import RawArchive
from zhixing_worker.sync_store import ResourceRunRef, SyncStore


def replay_archived_page(database: Database, store: SyncStore, ref: ResourceRunRef,
                         job: JobRecord, context: JobExecutionContext, spec: ResourceSpec,
                         archive_root: Path, source_id: str,
                         validate_scope: Callable[[], dict[str, object]]) -> dict[str, object]:
    command = job.payload.get("raw_replay")
    if (not isinstance(command, dict) or command.get("mapping_version") != MAPPING_VERSION
            or not can_project_to_core(spec)):
        raise PermanentJobError("重放映射版本不可用", code="sync.replay_version_invalid")
    with database.session() as session:
        mirror = session.get(SourceMirrorPage, command.get("manifest_id"))
        manifest = session.scalar(select(RawPageManifest)
            .join(SyncResourceRun, SyncResourceRun.id == RawPageManifest.sync_resource_run_id)
            .join(SourceResource, SourceResource.id == SyncResourceRun.source_resource_id)
            .join(SyncRun, SyncRun.id == SyncResourceRun.sync_run_id).where(
                RawPageManifest.id == command.get("manifest_id"),
                SyncResourceRun.source_resource_id == ref.resource_id,
                SourceResource.schema_status == "confirmed", SourceResource.enabled.is_(True),
                SyncRun.enterprise_id == job.enterprise_id,
                SyncRun.external_system_id == source_id))
        if (manifest is None or manifest.fetched_at is None
                or (mirror is not None
                    and mirror.schema_status in {"scope_invalid", "schema_invalid"})
                or manifest.content_hash != command.get("content_hash")
                or not manifest.storage_key.endswith(".json.gz")):
            raise PermanentJobError("重放来源页不可用", code="sync.replay_manifest_invalid")
    context.ensure_active()
    try:
        payload = RawArchive(archive_root).read(manifest.storage_key, manifest.content_hash)
        rows = response_value(payload, spec.rows_path)
        if not isinstance(rows, list) or len(rows) != manifest.row_count:
            raise ValueError("row count drift")
    except (ValueError, OSError, EOFError):
        raise PermanentJobError("重放归档校验失败", code="sync.replay_archive_invalid") from None
    scope = validate_scope()
    context.ensure_active()
    observed = manifest.fetched_at
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    store.record_page(ref, partition=str(job.payload["partition"]), cursor="1",
        storage_key=manifest.storage_key, content_hash=manifest.content_hash,
        byte_count=manifest.bytes, row_count=manifest.row_count, page_number=1,
        schema_status=spec.schema_status, fetched_at=observed,
        request_parameters=manifest.request_parameters,
        fence=getattr(context, "fence", None),
        write_canonical=lambda connection, new_manifest: persist_canonical_page(connection,
            enterprise_id=job.enterprise_id, source_id=source_id, resource_key=spec.key,
            manifest_id=new_manifest, payload=payload, observed_at=observed,
            scope_snapshot=scope, request_parameters=manifest.request_parameters).accepted)
    return {"mode": "raw_replay", "origin_manifest_id": manifest.id,
            "mapping_version": MAPPING_VERSION, "row_count": manifest.row_count}
