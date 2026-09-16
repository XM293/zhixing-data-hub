from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, Connection, Engine, bindparam, inspect, select, text
from zhixing_api.data_models import ExternalSystem, SourceResource
from zhixing_api.ingestion.batches import refresh_batch
from zhixing_connectors.catalog import effective_schema_status, resource_spec
from zhixing_jobs import PermanentJobError


@dataclass(frozen=True, slots=True)
class ResourceRunRef:
    resource_id: str
    run_id: str


class SyncStore:
    """Small Worker-owned persistence boundary for the 0054 ingestion ledger."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        inspector = inspect(engine)
        self._tables = set(inspector.get_table_names())
        self._columns = {
            table: {item["name"] for item in inspector.get_columns(table)}
            for table in self._tables.intersection({
                "external_systems", "source_resources", "sync_resource_runs",
                "raw_page_manifests", "sync_checkpoints", "sync_runs",
            })
        }

    def _has_column(self, table: str, column: str) -> bool:
        return column in self._columns.get(table, set())

    def _has_table(self, table: str) -> bool:
        return table in self._tables

    def begin_resource(
        self,
        *,
        sync_run_id: str,
        source_key: str,
        resource_key: str,
        partition: str,
        enterprise_id: str | None = None,
        fence: Callable[[Connection], None] | None = None,
    ) -> ResourceRunRef:
        with self.engine.begin() as connection:
            if fence is not None:
                fence(connection)
            enterprise_clause = (
                " AND es.enterprise_id = :enterprise_id"
                if enterprise_id is not None
                and self._has_column("external_systems", "enterprise_id")
                else ""
            )
            status_clause = (
                " AND COALESCE(es.status, '') <> 'disabled'"
                if self._has_column("external_systems", "status") else ""
            )
            resource_id = connection.execute(
                text(
                    "SELECT sr.id FROM source_resources sr "
                    "JOIN external_systems es ON es.id = sr.external_system_id "
                    "WHERE es.system_key = :source_key AND sr.resource_key = :resource_key "
                    "AND sr.enabled = true" + status_clause + enterprise_clause
                ),
                {
                    "source_key": source_key,
                    "resource_key": resource_key,
                    "enterprise_id": enterprise_id,
                },
            ).scalar_one_or_none()
            if resource_id is None:
                raise LookupError("source resource is missing or disabled")
            existing = connection.execute(
                text(
                    "SELECT id FROM sync_resource_runs WHERE sync_run_id = :sync_run_id "
                    "AND source_resource_id = :resource_id AND partition_key = :partition"
                ),
                {
                    "sync_run_id": sync_run_id,
                    "resource_id": resource_id,
                    "partition": partition,
                },
            ).scalar_one_or_none()
            run_id = str(existing or f"sync_resource_run_{uuid4().hex}")
            if existing is not None:
                connection.execute(text(
                    "UPDATE sync_resource_runs SET status = 'running' WHERE id = :id"
                ), {"id": run_id})
                if self._has_column("sync_resource_runs", "started_at"):
                    connection.execute(text(
                        "UPDATE sync_resource_runs SET started_at = "
                        "COALESCE(started_at, CURRENT_TIMESTAMP), finished_at = NULL, "
                        "error_code = NULL WHERE id = :id"
                    ), {"id": run_id})
            if self._has_table("sync_runs"):
                connection.execute(text(
                    "UPDATE sync_runs SET status = 'running', finished_at = NULL "
                    "WHERE id = :id AND status <> 'cancelled'"
                ), {"id": sync_run_id})
            if existing is None:
                if self._has_column("sync_resource_runs", "started_at"):
                    connection.execute(
                        text(
                            "INSERT INTO sync_resource_runs "
                            "(id, sync_run_id, source_resource_id, status, partition_key, "
                            "records_read, records_written, started_at) VALUES "
                            "(:id, :sync_run_id, :resource_id, 'running', :partition, "
                            "0, 0, CURRENT_TIMESTAMP)"
                        ),
                        {
                            "id": run_id,
                            "sync_run_id": sync_run_id,
                            "resource_id": resource_id,
                            "partition": partition,
                        },
                    )
                else:
                    connection.execute(
                        text(
                            "INSERT INTO sync_resource_runs "
                            "(id, sync_run_id, source_resource_id, status, partition_key, "
                            "records_read, records_written) VALUES "
                            "(:id, :sync_run_id, :resource_id, 'running', :partition, 0, 0)"
                        ),
                        {
                            "id": run_id,
                            "sync_run_id": sync_run_id,
                            "resource_id": resource_id,
                            "partition": partition,
                        },
                    )
            return ResourceRunRef(resource_id=str(resource_id), run_id=run_id)

    def checkpoint(self, ref: ResourceRunRef, partition: str) -> str | None:
        with self.engine.begin() as connection:
            return connection.execute(
                text(
                    "SELECT cursor FROM sync_checkpoints "
                    "WHERE source_resource_id = :resource_id AND partition_key = :partition "
                    "AND status <> 'completed'"
                ),
                {"resource_id": ref.resource_id, "partition": partition},
            ).scalar_one_or_none()

    def record_page(
        self,
        ref: ResourceRunRef,
        *,
        partition: str,
        cursor: str,
        storage_key: str,
        content_hash: str,
        byte_count: int,
        row_count: int,
        page_number: int | None = None,
        schema_status: str = "unknown",
        request_parameters: dict[str, object] | None = None,
        fetched_at: datetime | None = None,
        write_canonical: Callable[[Connection, str], int] | None = None,
        after_archive: Callable[[Connection, str, str], None] | None = None,
        fence: Callable[[Connection], None] | None = None,
    ) -> bool:
        """Persist one page once and advance its checkpoint transactionally."""
        with self.engine.begin() as connection:
            if fence is not None:
                fence(connection)
            if self._has_column("source_resources", "schema_status"):
                resource = connection.execute(select(SourceResource.resource_key,
                    SourceResource.schema_status, SourceResource.enabled,
                    ExternalSystem.status.label("source_status"))
                    .join(ExternalSystem, ExternalSystem.id == SourceResource.external_system_id)
                    .where(SourceResource.id == ref.resource_id).with_for_update()).one_or_none()
                if resource is None or not resource.enabled or resource.source_status == "disabled":
                    raise PermanentJobError("来源资源已停用", code="sync.resource_disabled")
                current_schema = effective_schema_status(
                    resource_spec(resource.resource_key), resource.schema_status)
                if schema_status != "confirmed" or current_schema != "confirmed":
                    schema_status = "schema_pending"
                    write_canonical = None
            elif write_canonical is not None:
                raise PermanentJobError("来源资源缺少 Schema 状态",
                                        code="sync.resource_schema_missing")
            if page_number is not None and self._has_column("raw_page_manifests", "page_number"):
                exists = connection.execute(
                    text(
                        "SELECT id FROM raw_page_manifests "
                        "WHERE sync_resource_run_id = :run_id AND page_number = :page"
                    ),
                    {"run_id": ref.run_id, "page": page_number},
                ).scalar_one_or_none()
            else:
                exists = connection.execute(
                    text(
                        "SELECT id FROM raw_page_manifests "
                        "WHERE sync_resource_run_id = :run_id AND content_hash = :digest"
                    ),
                    {"run_id": ref.run_id, "digest": content_hash},
                ).scalar_one_or_none()
            if exists is not None:
                return False
            values = {
                "id": f"raw_page_{uuid4().hex}",
                "run_id": ref.run_id,
                "storage_key": storage_key,
                "digest": content_hash,
                "bytes": byte_count,
                "rows": row_count,
                "page": page_number,
                "schema_status": schema_status,
                "request_parameters": request_parameters or {},
                "cursor": cursor,
                "fetched_at": fetched_at or datetime.now(UTC),
            }
            if self._has_column("raw_page_manifests", "page_number"):
                request_column = (", request_parameters"
                                  if self._has_column("raw_page_manifests",
                                                      "request_parameters") else "")
                request_value = (", :request_parameters" if request_column else "")
                statement = text(
                    "INSERT INTO raw_page_manifests "
                    "(id, sync_resource_run_id, storage_key, content_hash, compression, "
                    "bytes, row_count, page_number, schema_status, fetched_at"
                    f"{request_column}) VALUES "
                    "(:id, :run_id, :storage_key, :digest, 'gzip', :bytes, :rows, "
                    ":page, :schema_status, :fetched_at"
                    f"{request_value})")
                if request_column:
                    statement = statement.bindparams(bindparam("request_parameters", type_=JSON))
                connection.execute(statement, values)
            else:
                request_column = (", request_parameters"
                                  if self._has_column("raw_page_manifests",
                                                      "request_parameters") else "")
                request_value = (", :request_parameters" if request_column else "")
                statement = text(
                    "INSERT INTO raw_page_manifests "
                    "(id, sync_resource_run_id, storage_key, content_hash, compression, "
                    f"bytes, row_count{request_column}) VALUES "
                    "(:id, :run_id, :storage_key, :digest, 'gzip', :bytes, :rows"
                    f"{request_value})")
                if request_column:
                    statement = statement.bindparams(bindparam("request_parameters", type_=JSON))
                connection.execute(statement, values)
            written = write_canonical(connection, str(values["id"])) if write_canonical else 0
            if after_archive is not None:
                after_archive(connection, str(values["id"]), schema_status)
            if self._has_column("raw_page_manifests", "cursor"):
                connection.execute(text(
                    "UPDATE raw_page_manifests SET cursor = :cursor WHERE id = :id"
                ), values)
            checkpoint_id = connection.execute(
                text(
                    "SELECT id FROM sync_checkpoints WHERE source_resource_id = :resource_id "
                    "AND partition_key = :partition"
                ),
                {"resource_id": ref.resource_id, "partition": partition},
            ).scalar_one_or_none()
            if checkpoint_id is None:
                connection.execute(
                    text(
                        "INSERT INTO sync_checkpoints "
                        "(id, source_resource_id, partition_key, cursor, status) "
                        "VALUES (:id, :resource_id, :partition, :cursor, 'active')"
                    ),
                    {
                        "id": f"checkpoint_{uuid4().hex}",
                        "resource_id": ref.resource_id,
                        "partition": partition,
                        "cursor": cursor,
                    },
                )
            else:
                if self._has_column("sync_checkpoints", "updated_at"):
                    connection.execute(
                        text(
                            "UPDATE sync_checkpoints SET cursor = :cursor, status = 'active', "
                            "updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                        ),
                        {"cursor": cursor, "id": checkpoint_id},
                    )
                else:
                    connection.execute(
                        text(
                            "UPDATE sync_checkpoints SET cursor = :cursor, status = 'active' "
                            "WHERE id = :id"
                        ),
                        {"cursor": cursor, "id": checkpoint_id},
                    )
            if self._has_column("sync_checkpoints", "updated_at"):
                connection.execute(text(
                    "UPDATE sync_checkpoints SET updated_at = CURRENT_TIMESTAMP "
                    "WHERE source_resource_id = :resource_id AND partition_key = :partition"
                ), {"resource_id": ref.resource_id, "partition": partition})
            connection.execute(
                text(
                    "UPDATE sync_resource_runs SET records_read = records_read + :rows, "
                    "records_written = records_written + :written "
                    "WHERE id = :run_id"
                ),
                {"rows": row_count, "written": written, "run_id": ref.run_id},
            )
            if fence is not None:
                fence(connection)
            return True

    def finish_resource(self, run_id: str, *, status: str = "succeeded",
                        error_code: str | None = None,
                        fence: Callable[[Connection], None] | None = None) -> None:
        with self.engine.begin() as connection:
            if fence is not None:
                fence(connection)
            if status == "succeeded" and self._has_table("staging_page_results"):
                failures = connection.execute(text(
                    "SELECT COALESCE(SUM(s.rejected + s.unassigned), 0) "
                    "FROM staging_page_results s JOIN raw_page_manifests m "
                    "ON m.id = s.raw_manifest_id WHERE m.sync_resource_run_id = :id"
                ), {"id": run_id}).scalar_one()
                if failures:
                    status = "partial_failed"
            connection.execute(
                text("UPDATE sync_resource_runs SET status = :status WHERE id = :id"),
                {"status": status, "id": run_id},
            )
            if self._has_column("sync_resource_runs", "finished_at"):
                connection.execute(text(
                    "UPDATE sync_resource_runs SET finished_at = "
                    "CASE WHEN :status = 'queued' THEN NULL ELSE CURRENT_TIMESTAMP END "
                    "WHERE id = :id"
                ), {"id": run_id, "status": status})
            if self._has_column("sync_resource_runs", "error_code"):
                connection.execute(text(
                    "UPDATE sync_resource_runs SET error_code = :code WHERE id = :id"
                ), {"id": run_id, "code": error_code})
            if status in {"succeeded", "partial_failed"}:
                connection.execute(text(
                    "UPDATE sync_checkpoints SET status = 'completed' "
                    "WHERE source_resource_id = (SELECT source_resource_id "
                    "FROM sync_resource_runs WHERE id = :id) "
                    "AND partition_key = (SELECT partition_key FROM sync_resource_runs "
                    "WHERE id = :id)"
                ), {"id": run_id})
            if self._has_table("sync_runs"):
                parent = connection.execute(
                    text(
                        "SELECT sync_run_id FROM sync_resource_runs WHERE id = :id"
                    ),
                    {"id": run_id},
                ).scalar_one_or_none()
                if parent is not None:
                    counts = connection.execute(
                        text(
                            "SELECT COUNT(*) AS total, "
                            "SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) AS succeeded, "
                            "SUM(CASE WHEN status = 'partial_failed' "
                            "THEN 1 ELSE 0 END) AS partial, "
                            "SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled, "
                            "SUM(CASE WHEN status IN ('failed', 'cancelled', 'partial_failed') "
                            "THEN 1 ELSE 0 END) AS failed, "
                            "SUM(CASE WHEN status IN ('queued', 'running') "
                            "THEN 1 ELSE 0 END) AS active, "
                            "COALESCE(SUM(records_read), 0) AS records_read, "
                            "COALESCE(SUM(records_written), 0) AS records_written "
                            "FROM sync_resource_runs WHERE sync_run_id = :parent"
                        ),
                        {"parent": parent},
                    ).mappings().one()
                    total = int(counts["total"] or 0)
                    succeeded = int(counts["succeeded"] or 0)
                    failed = int(counts["failed"] or 0)
                    active = int(counts["active"] or 0)
                    aggregate = (
                        "running" if active else
                        "cancelled" if int(counts["cancelled"] or 0) == total else
                        "partial_failed" if int(counts["partial"] or 0) > 0 else
                        "succeeded" if succeeded == total else
                        "failed" if failed == total else
                        "partial_failed"
                    )
                    connection.execute(
                        text(
                            "UPDATE sync_runs SET status = :status, records_read = :read, "
                            "records_written = :written, finished_at = "
                            "CASE WHEN :active = 0 THEN CURRENT_TIMESTAMP ELSE finished_at END "
                            "WHERE id = :id AND status <> 'cancelled'"
                        ),
                        {
                            "status": aggregate,
                            "read": int(counts["records_read"] or 0),
                            "written": int(counts["records_written"] or 0),
                            "active": active,
                            "id": parent,
                        },
                    )
                    if self._has_column("sync_runs", "parent_run_id"):
                        batch = connection.execute(text(
                            "SELECT parent_run_id FROM sync_runs WHERE id = :id"
                        ), {"id": parent}).scalar_one_or_none()
                        if batch:
                            refresh_batch(connection, str(batch))
                    if (not active
                            and self._has_column("source_resources", "validation_status")):
                        connection.execute(text(
                            "UPDATE source_resources SET validation_status = :validation, "
                            "validation_run_id = :run_id, validation_error_code = :error, "
                            "last_validated_at = CURRENT_TIMESTAMP "
                            "WHERE id = (SELECT source_resource_id FROM sync_resource_runs "
                            "WHERE id = :resource_run) AND (SELECT scenario FROM sync_runs "
                            "WHERE id = :run_id) = 'probe'"
                        ), {"resource_run": run_id, "run_id": parent,
                            "validation": "validated" if aggregate == "succeeded"
                                          else "needs_attention",
                            "error": error_code})
                    if self._has_column("external_systems", "connection_status") and not active:
                        connection.execute(text(
                            "UPDATE external_systems SET connection_status = :status, "
                            "last_probe_at = CASE WHEN (SELECT scenario FROM sync_runs "
                            "WHERE id = :id) = 'probe' THEN CURRENT_TIMESTAMP "
                            "ELSE last_probe_at END, "
                            "last_sync_at = CASE WHEN :success THEN CURRENT_TIMESTAMP "
                            "ELSE last_sync_at END WHERE id = (SELECT external_system_id "
                            "FROM sync_runs WHERE id = :id) AND status <> 'disabled'"
                        ), {"id": parent,
                            "status": "connected" if aggregate == "succeeded" else
                                      "degraded" if aggregate == "partial_failed" else aggregate,
                            "success": aggregate in {"succeeded", "partial_failed"}})
                    if self._has_table("platform_events"):
                        connection.execute(text(
                            "INSERT INTO platform_events "
                            "(id, enterprise_id, event_type, severity, title, detail, occurred_at) "
                            "SELECT :event, enterprise_id, 'source.resource_finished', "
                            ":severity, '来源资源运行状态更新', :detail, CURRENT_TIMESTAMP "
                            "FROM sync_runs WHERE id = :parent"
                        ), {"event": f"event_{uuid4().hex}", "parent": parent,
                            "severity": "info" if aggregate == "succeeded" else "warning",
                            "detail": f"resource_run={run_id}; status={status}; "
                                      f"error_code={error_code or ''}"})
            if fence is not None:
                fence(connection)
