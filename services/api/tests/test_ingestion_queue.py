from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from zhixing_jobs.models import BackgroundJob
from zhixing_jobs.repository import JobRepository

from zhixing_api.data_center_schemas import SyncRequest
from zhixing_api.data_center_service import build_overview, list_sync_runs
from zhixing_api.data_models import Enterprise, ExternalSystem, SourceResource, SyncRun
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.queue import enqueue_sync


def test_source_queue_is_atomic_and_request_idempotency_links_every_run(tmp_path, monkeypatch):
    database = Database(f"sqlite:///{tmp_path / 'queue_verify.db'}")
    database.migrate()
    with database.session() as session:
        session.add(Enterprise(id="legal", code="legal", name="Synthetic legal entity",
                               timezone="UTC", created_at=datetime.now(UTC)))
        session.flush()
        session.add(ExternalSystem(id="src", enterprise_id="legal", system_key="erp",
                    name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
                    base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="res", external_system_id="src", resource_key="shops",
                    method="GET", path="/erp/sc/data/seller/lists", enabled=True,
                    schema_status="confirmed"))
        session.commit()
    kwargs = {"enterprise_id": "legal", "source_key": "erp", "initiator_id": "actor-test",
              "request_id": "request-test", "scope_snapshot": {"enterprise_id": "legal"},
              "provider_enabled": True}
    try:
        with pytest.raises(ApiProblem) as disabled:
            enqueue_sync(database, payload=SyncRequest(), **{**kwargs, "provider_enabled": False})
        assert disabled.value.code == "source.provider_disabled"
        first = enqueue_sync(database, payload=SyncRequest(client_request_key="first"), **kwargs)
        with database.session() as session:
            session.get(ExternalSystem, "src").version = 2
            session.commit()
        retry = enqueue_sync(database, payload=SyncRequest(client_request_key="first"), **kwargs)
        second = enqueue_sync(database, payload=SyncRequest(client_request_key="second"), **kwargs)
        assert first.id == retry.id and first.id != second.id
        assert first.task_id and first.task_id != second.task_id
        assert first.source_version == retry.source_version == 1 and second.source_version == 2
        with database.session() as session:
            assert session.get(BackgroundJob, first.task_id).payload["source_version"] == 1
            assert session.get(BackgroundJob, second.task_id).payload["source_version"] == 2
        page = list_sync_runs(database, enterprise_id="legal", status=None, query=None,
                              offset=0, limit=20)
        assert {item.id: item.source_version for item in page.items} == {
            first.id: 1, second.id: 2}
        overview = build_overview(database, enterprise_id="legal")
        assert overview.scene is None and overview.meeting is None
        assert len(overview.sources) == 1 and overview.latest_sync is not None
        with pytest.raises(ApiProblem) as error:
            enqueue_sync(database, payload=SyncRequest(client_request_key="first",
                                                       volume_profile="large"), **kwargs)
        assert error.value.code == "source.request_key_reused"
        def fail(*args, **kwargs):
            raise RuntimeError("synthetic queue persistence failure")
        monkeypatch.setattr(JobRepository, "enqueue_in_session", fail)
        with pytest.raises(RuntimeError):
            enqueue_sync(database, payload=SyncRequest(client_request_key="failed"), **kwargs)
        with database.session() as session:
            assert session.scalar(select(func.count()).select_from(SyncRun)) == 2
            jobs = list(session.scalars(select(BackgroundJob)))
            assert {job.run_id for job in jobs} == {first.id, second.id}
    finally:
        database.dispose()
