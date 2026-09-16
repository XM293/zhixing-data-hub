from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from zhixing_jobs.models import BackgroundJob
from zhixing_jobs.repository import JobRepository

from zhixing_api.data_models import Enterprise, ExternalSystem, SourceResource, SyncRun
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.batches import enqueue_import, refresh_batch
from zhixing_api.ingestion.planning import ImportRequest


@pytest.fixture
def batch_database(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'batch_verify.db'}")
    database.migrate()
    with database.session() as session:
        session.add(Enterprise(id="legal", code="legal", name="Synthetic legal",
                               timezone="UTC", created_at=datetime.now(UTC)))
        session.flush()
        session.add(ExternalSystem(id="src", enterprise_id="legal", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        for key in ("shops", "orders"):
            session.add(SourceResource(id=f"res-{key}", external_system_id="src",
                resource_key=key, method="GET", path="/synthetic", enabled=True,
                schema_status="confirmed"))
        session.commit()
    yield database
    database.dispose()


def test_batch_queue_atomic_replay_and_parent_aggregation(batch_database, monkeypatch):
    database = batch_database
    request = ImportRequest.model_validate({"client_request_key": "synthetic-batch",
        "selections": [{"resource_key": "orders", "window_start": "2026-01-01T00:00:00Z",
                        "window_end": "2026-01-09T00:00:00Z"}, {"resource_key": "shops"}]})
    kwargs = dict(enterprise_id="legal", source_key="erp", initiator_id="synthetic-actor",
                  request_id="synthetic-request", scope_snapshot={"enterprise_id": "legal"},
                  actor_snapshot={"user_account_id": "synthetic-account"}, provider_enabled=True)
    parent = enqueue_import(database, payload=request, **kwargs)
    assert enqueue_import(database, payload=request, **kwargs).id == parent.id
    with database.session() as session:
        children = list(session.scalars(select(SyncRun).where(SyncRun.parent_run_id == parent.id)))
        assert len(children) == 3 and all(child.task_id for child in children)
        assert parent.source_version == 1 and all(child.source_version == 1 for child in children)
        jobs = list(session.scalars(select(BackgroundJob)))
        assert len(jobs) == 3 and {job.run_id for job in jobs} == {child.id for child in children}
        assert len({job.payload["partition"] for job in jobs if
                    job.payload["resource_key"] == "orders"}) == 2
        children[0].status, children[0].records_read = "succeeded", 4
        session.commit()
    with database.engine.begin() as connection:
        refresh_batch(connection, parent.id)
    with database.session() as session:
        assert session.get(SyncRun, parent.id).status == "running"
        children = list(session.scalars(select(SyncRun).where(SyncRun.parent_run_id == parent.id)))
        for child in children[1:]:
            child.status = "failed"
        session.commit()
    with database.engine.begin() as connection:
        refresh_batch(connection, parent.id)
    with database.session() as session:
        row = session.get(SyncRun, parent.id)
        assert row.status == "partial_failed" and row.records_read == 4 and row.finished_at
    with pytest.raises(ApiProblem) as collision:
        enqueue_import(database, payload=request.model_copy(update={"partition_days": 1}), **kwargs)
    assert collision.value.code == "source.request_key_reused"

    original = JobRepository.enqueue_in_session
    called = 0
    def fail_second(self, *args, **kwargs):
        nonlocal called
        called += 1
        if called == 2:
            raise RuntimeError("synthetic second enqueue failure")
        return original(self, *args, **kwargs)
    monkeypatch.setattr(JobRepository, "enqueue_in_session", fail_second)
    with pytest.raises(RuntimeError):
        enqueue_import(database,
                       payload=request.model_copy(update={"client_request_key": "rollback"}),
                       **kwargs)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SyncRun)) == 4
        assert session.scalar(select(func.count()).select_from(BackgroundJob)) == 3
