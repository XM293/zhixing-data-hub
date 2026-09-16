import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from zhixing_api.actor_context import authenticate_local_actor
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.data_center_schemas import SyncRequest
from zhixing_api.data_models import (
    BusinessEntity,
    ExternalSystem,
    SourceMirrorPage,
    SourceResource,
    SyncCheckpoint,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.ingestion.mapping import MAPPING_VERSION
from zhixing_api.ingestion.mirror import defer_projection, list_mirror_pages
from zhixing_api.ingestion.queue import enqueue_sync
from zhixing_api.ingestion.replay import ReplayRequest, enqueue_replay
from zhixing_api.scope_context import build_scope_context
from zhixing_jobs import JobRepository, WorkerRunner

from zhixing_worker.archive import RawArchive
from zhixing_worker.config import WorkerSettings
from zhixing_worker.main import build_lingxing_sync_handler
from zhixing_worker.sync_store import SyncStore


@pytest.mark.parametrize("case", ["valid", "corrupt", "schema_pending"])
def test_deferred_mapping_has_independent_failure_and_checkpoint(tmp_path, case):
    database = Database(f"sqlite:///{tmp_path / 'mirror_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).resolve().parents[2]
        / "api/tests/fixtures/bootstrap-formal-synthetic.json").read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, confirmed=True, backup_id="synthetic-verify",
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Only-Password-380!")
    actor = authenticate_local_actor(database, login_name="admin-1@verify",
        password="Synthetic-Only-Password-380!", request_id="verify", run_id="verify")
    with database.session() as session:
        session.add(ExternalSystem(id="source", enterprise_id="legal-a", system_key="source",
            name="Synthetic", system_type="lingxing", status="configured",
            base_url="https://openapi.lingxing.com"))
        session.add(SourceResource(id="resource", external_system_id="source", resource_key="shops",
            path="/erp/sc/data/seller/lists", schema_status="confirmed", enabled=True))
        session.commit()
    scope = build_scope_context(database, actor).snapshot()
    run = enqueue_sync(database, enterprise_id="legal-a", source_key="source",
        initiator_id=actor.principal_id, request_id="verify", scope_snapshot=scope,
        actor_snapshot=actor.snapshot(), provider_enabled=True,
        payload=SyncRequest(projection_mode="deferred"))
    repository = JobRepository(database.engine)
    job = repository.get(run.task_id)
    assert job.payload["projection_mode"] == "deferred"
    store = SyncStore(database.engine)
    partition = str(job.payload["partition"])
    ref = store.begin_resource(sync_run_id=run.id, source_key="source", resource_key="shops",
                               partition=partition, enterprise_id="legal-a")
    archive = RawArchive(tmp_path / "raw")
    blob = archive.write({"code": 0, "data": [{"sid": 1, "name": "Synthetic", "status": 1}]})
    def register(connection, manifest_id, schema_status):
        defer_projection(connection, job=job, manifest_id=manifest_id,
                         schema_status=schema_status, scope_snapshot=scope)
    def interrupt_commit(connection, manifest_id, schema_status):
        register(connection, manifest_id, schema_status)
        raise RuntimeError("synthetic transaction interruption")
    arguments = dict(partition=partition, cursor="1", storage_key=blob.storage_key,
        content_hash=blob.content_hash, byte_count=blob.byte_count, row_count=1,
        page_number=1, schema_status="confirmed", fetched_at=datetime.now(UTC),
        after_archive=register)
    with pytest.raises(RuntimeError, match="synthetic transaction interruption"):
        store.record_page(ref, **{**arguments, "after_archive": interrupt_commit})
    assert store.checkpoint(ref, partition) is None
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SourceMirrorPage)) == 0
    if case == "schema_pending":
        with database.session() as session:
            session.get(SourceResource, "resource").schema_status = "schema_pending"
            session.commit()
    assert store.record_page(ref, **arguments)
    assert not store.record_page(ref, **arguments)
    store.finish_resource(ref.run_id)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(BusinessEntity)) == 0
        page = session.scalar(select(SourceMirrorPage))
        projection_id = page.projection_run_id
        assert session.scalar(select(func.count()).select_from(SourceMirrorPage)) == 1
        assert session.get(SyncRun, run.id).records_written == 0
        if case == "schema_pending":
            assert projection_id is None
            assert page.schema_status == "schema_pending"
        else:
            assert session.get(SyncRun, projection_id).status == "queued"
        assert session.scalar(select(SyncCheckpoint).where(
            SyncCheckpoint.partition_key == partition)).cursor == "1"
        listing = list_mirror_pages(session, enterprise_id="legal-a", source_id="source",
                                    offset=0, limit=25)
        assert listing.total == 1
        assert listing.items[0].row_count == 1
        assert listing.items[0].projection_status == ("schema_pending" if
            case == "schema_pending" else "queued")
        assert list_mirror_pages(session, enterprise_id="legal-b", source_id="source",
                                 offset=0, limit=25).total == 0
        assert not list_mirror_pages(session, enterprise_id="legal-a", source_id="source",
                                     offset=1, limit=25).items
    if case == "schema_pending":
        return
    # Consume only the projection task: the synthetic acquisition above has already committed.
    settings = WorkerSettings(database_url=database.url, worker_id="verify-mirror",
        poll_seconds=0, lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        source_archive_path=str(tmp_path / "raw"), lingxing_enabled=False)
    handler = build_lingxing_sync_handler(settings, database.engine,
        transport=httpx.MockTransport(lambda _: pytest.fail("offline mapping used HTTP")))
    runner = WorkerRunner(repository, {"data-source.sync": handler}, worker_id="verify-mirror",
                          lease_seconds=60)
    # Remove the acquisition task from the runnable set via the normal cancellation API.
    with database.session() as session:
        repository.cancel_in_session(session, run.task_id, "legal-a")
        session.commit()
    if case == "corrupt":
        (tmp_path / "raw" / blob.storage_key).write_bytes(b"synthetic-corruption")
    outcome = runner.run_once()
    assert outcome.status == ("failed" if case == "corrupt" else "succeeded")
    with database.session() as session:
        assert session.get(SyncRun, projection_id).status == outcome.status
        assert session.scalar(select(SyncCheckpoint).where(
            SyncCheckpoint.partition_key == partition)).cursor == "1"
        expected_count = 0 if case == "corrupt" else 1
        assert session.scalar(select(func.count()).select_from(BusinessEntity)) == expected_count
    if case == "valid":
        request = ReplayRequest(client_request_key="mirror-remap",
            expected_content_hash=blob.content_hash, expected_mapping_version=MAPPING_VERSION)
        replay = enqueue_replay(database, actor, page.raw_manifest_id, request)
        with database.session() as session:
            listing = list_mirror_pages(session, enterprise_id="legal-a", source_id="source",
                                        offset=0, limit=25)
            assert listing.items[0].projection_run_id == replay.id
            assert listing.items[0].projection_status == "queued"
        assert enqueue_replay(database, actor, page.raw_manifest_id, request).id == replay.id
        assert runner.run_once().status == "succeeded"
