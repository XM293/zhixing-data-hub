from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select
from zhixing_connectors.catalog import effective_schema_status, resource_spec

from zhixing_api.data_center_schemas import DataSourceView, SyncRunView
from zhixing_api.data_center_service import _run_view
from zhixing_api.data_models import (
    Enterprise,
    ExternalSystem,
    RawPageManifest,
    SourceRecord,
    SourceResource,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.scope_context import ScopeContext


class SourceOperationsView(BaseModel):
    schema_version: Literal[1] = 1
    enterprise_id: str
    enterprise_name: str
    scope_context: dict[str, object]
    sources: list[DataSourceView]
    source_record_count: int
    resource_count: int
    enabled_resource_count: int
    pending_resource_count: int
    latest_sync: SyncRunView | None
    generated_at: datetime


def source_operations(database: Database, enterprise_id: str,
                      scope: ScopeContext) -> SourceOperationsView:
    with database.session() as session:
        enterprise = session.get(Enterprise, enterprise_id)
        if enterprise is None:
            raise LookupError("source.enterprise_missing")
        sources = session.scalars(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == enterprise_id).order_by(ExternalSystem.name)).all()
        ids = [source.id for source in sources]
        counts = {str(key): int(count) for key, count in session.execute(
            select(SourceRecord.external_system_id, func.count(SourceRecord.id)).where(
                SourceRecord.enterprise_id == enterprise_id,
                SourceRecord.external_system_id.in_(ids)).group_by(SourceRecord.external_system_id))}
        for key, count in session.execute(select(SyncRun.external_system_id,
            func.sum(RawPageManifest.row_count)).select_from(RawPageManifest)
            .join(SyncResourceRun, SyncResourceRun.id == RawPageManifest.sync_resource_run_id)
            .join(SyncRun, SyncRun.id == SyncResourceRun.sync_run_id)
            .where(SyncRun.enterprise_id == enterprise_id, SyncRun.external_system_id.in_(ids),
                   SyncRun.scenario != "raw_replay")
            .group_by(SyncRun.external_system_id)):
            counts[str(key)] = counts.get(str(key), 0) + int(count or 0)
        runs = {str(key): int(count) for key, count in session.execute(
            select(SyncRun.external_system_id, func.count(SyncRun.id)).where(
                SyncRun.enterprise_id == enterprise_id, SyncRun.external_system_id.in_(ids),
                SyncRun.scenario != "raw_replay",
                SyncRun.parent_run_id.is_(None)).group_by(SyncRun.external_system_id))}
        resources = session.execute(select(SourceResource.enabled, SourceResource.schema_status,
            SourceResource.resource_key,
            func.count(SourceResource.id)).where(SourceResource.external_system_id.in_(ids))
            .group_by(SourceResource.enabled, SourceResource.schema_status,
                      SourceResource.resource_key)).all()
        latest = session.scalar(select(SyncRun).where(SyncRun.enterprise_id == enterprise_id,
            SyncRun.scenario != "raw_replay",
            SyncRun.external_system_id.in_(ids), SyncRun.parent_run_id.is_(None))
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc()).limit(1))
        keys = {source.id: source.system_key for source in sources}
        return SourceOperationsView(enterprise_id=enterprise_id, enterprise_name=enterprise.name,
            scope_context=scope.snapshot(), source_record_count=sum(counts.values()),
            resource_count=sum(int(count) for _, _, _, count in resources),
            enabled_resource_count=sum(int(count) for enabled, _, _, count in resources if enabled),
            pending_resource_count=sum(int(count) for _, schema, key, count in resources
                if effective_schema_status(resource_spec(key), schema) != "confirmed"),
            latest_sync=(_run_view(latest, source_key=keys[latest.external_system_id])
                         if latest else None),
            generated_at=datetime.now(UTC), sources=[DataSourceView(
                key=source.system_key, name=source.name, system_type=source.system_type,
                status=source.status, connection_status=source.connection_status,
                source_schema_version=source.source_schema_version,
                mapping_version=source.mapping_version, last_sync_at=source.last_sync_at,
                source_record_count=counts.get(source.id, 0), sync_run_count=runs.get(source.id, 0),
            ) for source in sources])
