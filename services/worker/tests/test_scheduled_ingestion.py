import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select
from zhixing_api.actor_context import resolve_database_actor
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.data_center_service import build_overview
from zhixing_api.data_models import (
    BusinessEntity,
    CanonicalEntityOrigin,
    ExternalSystem,
    RawPageManifest,
    SourceResource,
    SyncCheckpoint,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.ingestion.batches import cancel_import, enqueue_import
from zhixing_api.ingestion.planning import ImportRequest
from zhixing_api.scope_context import build_scope_context
from zhixing_jobs import JobRepository, PermanentJobError, WorkerRunner
from zhixing_jobs.models import BackgroundJob

from zhixing_worker.config import WorkerSettings
from zhixing_worker.main import _validate_source_job, build_lingxing_sync_handler


def test_batch_runs_with_real_job_leases_and_cancel_cascades(tmp_path, monkeypatch):
    database = Database(f"sqlite:///{tmp_path / 'batch_worker_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parents[2] /
        "api/tests/fixtures/bootstrap-formal-synthetic.json").read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Password-Only-378!")
    actor = resolve_database_actor(database, login_name="admin-1@verify", enterprise_id="legal-a",
                                   request_id="synthetic-request", run_id="synthetic-run")
    with database.session() as session:
        session.add(ExternalSystem(id="source-a", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        for resource in ("shops", "warehouses_local", "multiplatform_shops"):
            session.add(SourceResource(id=resource, external_system_id="source-a",
                resource_key=resource, method="GET", path="/synthetic", enabled=True,
                schema_status="confirmed"))
        session.commit()
    options = dict(enterprise_id=actor.enterprise_id, source_key="erp",
        initiator_id=actor.principal_id, request_id="synthetic-request",
        actor_snapshot=actor.snapshot(),
        scope_snapshot=build_scope_context(database, actor).snapshot(), provider_enabled=True)
    request = ImportRequest.model_validate({"client_request_key": "synthetic-run",
        "selections": [{"resource_key": "shops"}, {"resource_key": "warehouses_local"},
                       {"resource_key": "multiplatform_shops"}]})
    parent = enqueue_import(database, payload=request, **options)
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic-token", "refresh_token": "synthetic-refresh",
                "expires_in": 3600}})
        assert request.url.params.get("access_token") == "synthetic-token"
        if request.url.path.endswith("getSellerList"):
            return httpx.Response(200, json={"code": 0, "data": {"total": "1", "list": [
                {"store_id": "1234", "sid": "", "store_name": "Synthetic multi store",
                 "platform_code": "10008", "platform_name": "Walmart", "currency": "USD",
                 "is_sync": 1, "status": 1}]}})
        rows = ([{"sid": 1234, "name": "Synthetic store", "status": 1}]
                if request.url.path.endswith("/lists") else
                [{"wid": 987, "name": "Synthetic warehouse", "type": 1, "is_delete": 0}])
        return httpx.Response(200, json={"code": 0, "total": 1, "data": rows})
    settings = WorkerSettings(database_url=database.url, worker_id="synthetic-worker",
        poll_seconds=0, lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_enabled=True, lingxing_app_id="synthetic-app-16",
        lingxing_app_secret="synthetic-secret", source_archive_path=str(tmp_path / "raw"))
    runner = WorkerRunner(JobRepository(database.engine), {"data-source.sync":
        build_lingxing_sync_handler(settings, database.engine,
                                    transport=httpx.MockTransport(respond))},
        worker_id="synthetic-worker", lease_seconds=60)
    assert runner.run_once().status == "succeeded"
    with database.session() as session:
        assert session.get(SyncRun, parent.id).status == "running"
    assert runner.run_once().status == "succeeded"
    assert runner.run_once().status == "succeeded"
    with database.session() as session:
        row = session.get(SyncRun, parent.id)
        assert row.status == "succeeded" and row.records_read == row.records_written == 3
        assert session.scalar(select(func.count()).select_from(RawPageManifest)) == 3
        assert session.scalar(select(func.count()).select_from(BusinessEntity)) == 3
        stores = list(session.scalars(select(BusinessEntity).where(
            BusinessEntity.entity_type == "store")))
        assert len(stores) == 2 and all(item.status == "unassigned" for item in stores)
        for origin in session.scalars(select(CanonicalEntityOrigin)):
            raw = session.get(RawPageManifest, origin.raw_manifest_id)
            assert origin.observed_at.replace(tzinfo=UTC) == raw.fetched_at.replace(tzinfo=UTC)
    assert sum(path.endswith("access-token") for path in calls) == 1
    overview = build_overview(database, enterprise_id="legal-a")
    assert overview.source_record_count == 3
    assert overview.sources[0].source_record_count == 3
    assert overview.sources[0].sync_run_count == 1
    assert overview.latest_sync.id == parent.id
    cancelled = enqueue_import(database,
        payload=request.model_copy(update={"client_request_key": "synthetic-cancel"}), **options)
    with database.session() as session:
        cancel_import(database, session, session.get(SyncRun, cancelled.id),
                       principal_id=actor.principal_id)
        session.commit()
    assert runner.run_once() is None
    with database.session() as session:
        children = list(session.scalars(select(SyncRun).where(
            SyncRun.parent_run_id == cancelled.id)))
        assert len(children) == 3 and all(row.status == "cancelled" for row in children)
        assert all(session.get(BackgroundJob, row.task_id).status == "cancelled"
                   for row in children)
    assert len(calls) == 4
    # A page budget boundary is not a successful import or a failed attempt.
    with database.session() as session:
        session.add(SourceResource(id="finance", external_system_id="source-a",
            resource_key="finance", method="POST", path="/synthetic", enabled=True,
            schema_status="schema_pending"))
        session.commit()
    finance = enqueue_import(database, payload=ImportRequest.model_validate({
        "client_request_key": "synthetic-continuation", "selections": [{"resource_key": "finance",
        "resource_parameters": {"sid": "1234"},
        "window_start": "2026-09-01T00:00:00Z",
        "window_end": "2026-09-08T00:00:00Z"}]}),
        **options)
    offsets = []
    def paginated(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic", "expires_in": 3600}})
        body = json.loads(request.content)
        assert body["start_date"] == "2026-09-01"
        assert body["end_date"] == "2026-09-07"
        offset = body["offset"]
        offsets.append(offset)
        rows = [{"synthetic": offset + index} for index in range(20 if offset == 0 else 1)]
        return httpx.Response(200, json={"code": 0, "data": {"total": 21, "records": rows}})
    monkeypatch.setattr("zhixing_worker.main.SYNC_PAGES_PER_TURN", 1)
    runner = WorkerRunner(JobRepository(database.engine), {"data-source.sync":
        build_lingxing_sync_handler(settings, database.engine,
                                    transport=httpx.MockTransport(paginated))},
        worker_id="synthetic-worker", lease_seconds=60)
    assert runner.run_once().status == "queued"
    with database.session() as session:
        assert session.get(SyncRun, finance.id).status == "running"
        checkpoint = session.scalar(select(SyncCheckpoint).where(
            SyncCheckpoint.source_resource_id == "finance"))
        assert checkpoint.cursor == "1" and checkpoint.status == "active"
    assert runner.run_once().status == "succeeded"
    assert offsets == [0, 20]
    with database.session() as session:
        row = session.get(SyncRun, finance.id)
        assert row.status == "succeeded" and row.records_read == 21 and row.records_written == 0
        child = session.scalar(select(SyncRun).where(SyncRun.parent_run_id == finance.id))
        job = session.get(BackgroundJob, child.task_id)
        assert job.continuation_count == 1 and job.attempt == 2 and job.max_attempts == 3
    database.dispose()


def test_worker_rejects_job_after_resource_contract_version_changes(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'resource_version_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parents[2] /
        "api/tests/fixtures/bootstrap-formal-synthetic.json").read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Password-Only-379!")
    actor = resolve_database_actor(database, login_name="admin-1@verify", enterprise_id="legal-a",
                                   request_id="synthetic-request", run_id="synthetic-run")
    scope = build_scope_context(database, actor).snapshot()
    with database.session() as session:
        session.add(ExternalSystem(id="source-a", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="shops", external_system_id="source-a",
            resource_key="shops", method="GET", path="/synthetic", enabled=True,
            schema_status="confirmed", version="contract-1"))
        session.add(SyncRun(id="sync-version", enterprise_id="legal-a",
            external_system_id="source-a", source_version=1, status="queued", scenario="normal",
            volume_profile="standard", started_at=datetime.now(UTC),
            idempotency_key="sync-version", request_id="synthetic-version",
            scope_snapshot=scope))
        session.commit()
    job = SimpleNamespace(enterprise_id="legal-a", run_id="sync-version",
        request_id="synthetic-version", payload={"resource_version": "contract-1"},
        actor_snapshot=actor.snapshot())
    assert _validate_source_job(database, job, "shops")["enterprise_id"] == "legal-a"
    with database.session() as session:
        session.get(SourceResource, "shops").version = "contract-2"
        session.commit()
    with pytest.raises(PermanentJobError) as changed:
        _validate_source_job(database, job, "shops")
    assert changed.value.code == "sync.resource_contract_changed"
    database.dispose()
