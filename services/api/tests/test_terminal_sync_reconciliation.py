from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from zhixing_jobs import EnqueueJob, JobRepository, JobsBase

from zhixing_api.data_models import Base, ExternalSystem, SourceResource, SyncResourceRun, SyncRun
from zhixing_api.ingestion.batches import reconcile_terminal_runs


def test_terminal_jobs_close_standalone_run_and_resource_without_overwriting_valid_result():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    JobsBase.metadata.create_all(engine)
    repository = JobRepository(engine)
    with Session(engine) as session:
        session.add(ExternalSystem(id="source", enterprise_id="legal", system_key="synthetic",
            name="Synthetic ERP", system_type="lingxing", base_url="https://example.invalid"))
        session.flush()
        session.add(SourceResource(id="resource", external_system_id="source", resource_key="shops",
            method="GET", path="/synthetic", enabled=True, schema_status="confirmed"))
        for key, status in (("run-queued", "queued"), ("run-valid", "succeeded")):
            session.add(SyncRun(id=key, enterprise_id="legal", external_system_id="source",
                status=status, scenario="import", started_at=datetime.now(UTC),
                records_read=3, records_written=2))
            session.flush()
            session.add(SyncResourceRun(id=f"resource-{key}", sync_run_id=key,
                source_resource_id="resource", partition_key=key, status=status,
                records_read=3, records_written=2))
        session.commit()
    for key in ("run-queued", "run-valid"):
        job = repository.enqueue(EnqueueJob(enterprise_id="legal", job_type="data-source.sync",
            payload={}, idempotency_key=key, initiator_type="user", initiator_id="synthetic",
            actor_snapshot={"principal_id": "synthetic"}, permission_set_version="synthetic",
            required_permissions=(),
            scope_type="enterprise", scope_id="legal", run_id=key)).job
        with Session(engine) as session:
            session.get(SyncRun, key).task_id = job.id
            session.commit()
        claimed = repository.claim("synthetic", lease_seconds=60)
        repository.fail(claimed.id, "synthetic", error_code="sync.resource_not_registered",
            error_message="Synthetic failure", retryable=False,
            execution_token=claimed.execution_token)
    with engine.begin() as connection:
        reconcile_terminal_runs(connection)
    with Session(engine) as session:
        assert session.get(SyncRun, "run-queued").status == "failed"
        resource = session.get(SyncResourceRun, "resource-run-queued")
        assert resource.status == "failed" and resource.error_code == "sync.resource_not_registered"
        assert resource.records_written == 2
        assert session.get(SyncRun, "run-valid").status == "succeeded"
        before = session.scalar(select(SyncRun.finished_at).where(SyncRun.id == "run-queued"))
    with engine.begin() as connection:
        reconcile_terminal_runs(connection)
    with Session(engine) as session:
        assert session.get(SyncRun, "run-queued").finished_at == before
    engine.dispose()
