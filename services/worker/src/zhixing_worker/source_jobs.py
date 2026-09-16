from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import Engine
from zhixing_api.connectors.contracts import ConnectorError
from zhixing_api.connectors.registry import SYSTEM_TYPE_PROFILES, create_connector
from zhixing_api.data_center_service import _persist_batch, _record_quality_results
from zhixing_api.data_models import ExternalSystem, SyncRun
from zhixing_api.database import Database
from zhixing_jobs import JobExecutionContext, JobRecord, PermanentJobError, RetryableJobError


def execute_mock_source(engine: Engine, job: JobRecord,
                        context: JobExecutionContext) -> Mapping[str, object]:
    """Preserve explicitly configured test connectors, with I/O owned by Worker."""
    database = Database.from_engine(engine)
    context.ensure_active()
    with database.session() as session:
        run = session.get(SyncRun, job.run_id)
        source = session.get(ExternalSystem, run.external_system_id) if run else None
        if (run is None or source is None or run.enterprise_id != job.enterprise_id
                or source.enterprise_id != job.enterprise_id or source.status == "disabled"
                or source.system_type not in SYSTEM_TYPE_PROFILES
                or source.provider_key == "lingxing"):
            raise PermanentJobError("测试来源配置已失效", code="sync.mock_source_invalid")
        connector = create_connector(source.system_type, source.base_url)
        scenario, volume = run.scenario, run.volume_profile
    try:
        batch = asyncio.run(connector.fetch("normal" if scenario == "probe" else scenario, volume))
    except ConnectorError:
        raise RetryableJobError("测试来源暂时不可用", code="sync.mock_unavailable") from None
    context.ensure_active()
    with database.session() as session:
        run = session.get(SyncRun, job.run_id)
        source = session.get(ExternalSystem, run.external_system_id) if run else None
        if run is None or source is None or source.status == "disabled":
            raise PermanentJobError("测试来源已停用", code="sync.mock_source_invalid")
        written = _persist_batch(session, run, batch)
        run.records_read, run.records_written = len(batch.records), written
        run.status = "partial_failed" if batch.warnings else "succeeded"
        run.finished_at = datetime.now(UTC)
        source.last_sync_at = run.finished_at
        source.status = "degraded" if batch.warnings else "connected"
        _record_quality_results(session, run, batch)
        session.commit()
    return {"records_read": len(batch.records), "records_written": written}
