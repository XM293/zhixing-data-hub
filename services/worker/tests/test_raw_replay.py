import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from zhixing_api.actor_context import authenticate_local_actor
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.data_models import (
    BusinessEntity,
    CanonicalEntityOrigin,
    ExternalSystem,
    RawPageManifest,
    SourceMirrorPage,
    SourceResource,
    SyncCheckpoint,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.mapping import MAPPING_VERSION
from zhixing_api.ingestion.mirror import MirrorQuarantineRequest, quarantine_mirror_page
from zhixing_api.ingestion.replay import ReplayRequest, enqueue_replay
from zhixing_jobs import JobRepository, WorkerRunner

from zhixing_worker.archive import RawArchive
from zhixing_worker.config import WorkerSettings
from zhixing_worker.main import build_lingxing_sync_handler


@pytest.mark.parametrize("original_schema", ["confirmed", "schema_pending"])
def test_raw_replay_queue_without_network_preserves_time_and_checkpoint(tmp_path, original_schema):
    database = Database(f"sqlite:///{tmp_path / 'replay_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).resolve().parents[2]
        / "api/tests/fixtures/bootstrap-formal-synthetic.json").read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, confirmed=True, backup_id="synthetic-verify",
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Only-Password-380!")
    actor = authenticate_local_actor(database, login_name="admin-1@verify",
        password="Synthetic-Only-Password-380!", request_id="verify", run_id="verify")
    fetched = datetime(2020, 1, 1, tzinfo=UTC)
    archive = RawArchive(tmp_path / "raw")
    blob = archive.write({"code": 0, "data": [{"sid": 1, "name": "Synthetic", "status": 1}]})
    with database.session() as session:
        session.add(ExternalSystem(id="source", enterprise_id="legal-a", system_key="source",
            name="Synthetic", system_type="lingxing", status="configured",
            base_url="https://openapi.lingxing.com"))
        session.add(SourceResource(id="resource", external_system_id="source", resource_key="shops",
            path="/erp/sc/data/seller/lists", schema_status="confirmed", enabled=True))
        session.add(SyncRun(id="origin", enterprise_id="legal-a", external_system_id="source",
            scenario="normal", status="succeeded", started_at=fetched))
        session.flush()
        session.add(SyncResourceRun(id="origin-resource", sync_run_id="origin",
            source_resource_id="resource", partition_key="external", status="succeeded"))
        session.flush()
        session.add(RawPageManifest(id="raw-origin", sync_resource_run_id="origin-resource",
            storage_key=blob.storage_key, content_hash=blob.content_hash, bytes=blob.byte_count,
            row_count=1, page_number=1, fetched_at=fetched, schema_status=original_schema,
            request_parameters={"sid": 1}))
        session.add(SyncCheckpoint(id="external", source_resource_id="resource",
            partition_key="external", cursor="25", status="completed"))
        session.commit()
    request = ReplayRequest(client_request_key="synthetic-replay",
        expected_content_hash=blob.content_hash, expected_mapping_version=MAPPING_VERSION)
    run = enqueue_replay(database, actor, "raw-origin", request)
    assert run.status == "queued"
    assert enqueue_replay(database, actor, "raw-origin", request).id == run.id
    with pytest.raises(ApiProblem):
        enqueue_replay(database, actor, "raw-origin", request.model_copy(update={
            "expected_content_hash": "0" * 64}))
    calls = []
    def no_network(request):
        calls.append(request.url.path)
        raise AssertionError("Raw replay cannot use network")
    settings = WorkerSettings(database_url=database.url, worker_id="verify-replay",
        poll_seconds=0, lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_enabled=False, source_archive_path=str(tmp_path / "raw"))
    runner = WorkerRunner(JobRepository(database.engine), {"data-source.sync":
        build_lingxing_sync_handler(settings, database.engine,
                                    transport=httpx.MockTransport(no_network))},
        worker_id="verify-replay", lease_seconds=60)
    assert runner.run_once().status == "succeeded"
    assert calls == []
    with database.session() as session:
        assert session.get(SyncCheckpoint, "external").cursor == "25"
        assert session.get(SyncRun, run.id).records_written == 1
        assert session.scalar(select(BusinessEntity)).display_name == "Synthetic"
        origin = session.scalar(select(CanonicalEntityOrigin))
        assert origin.observed_at.year == 2020
        replayed = session.get(RawPageManifest, origin.raw_manifest_id)
        assert replayed.fetched_at.year == 2020
        assert replayed.request_parameters == {"sid": 1}
        origin.observed_at = datetime(2026, 1, 1, tzinfo=UTC)
        session.scalar(select(BusinessEntity)).display_name = "Newer synthetic observation"
        session.commit()
    with pytest.raises(ApiProblem):
        enqueue_replay(database, replace(actor, enterprise_id="legal-b"), "raw-origin", request)
    second = enqueue_replay(database, actor, "raw-origin", request.model_copy(update={
        "client_request_key": "synthetic-replay-again"}))
    assert runner.run_once().status == "succeeded"
    with database.session() as session:
        assert session.get(SyncRun, second.id).records_written == 0
        assert session.scalar(select(BusinessEntity)).display_name == "Newer synthetic observation"
        session.get(RawPageManifest, "raw-origin").storage_key = "../escape.json.gz"
        session.commit()
    invalid = enqueue_replay(database, actor, "raw-origin", request.model_copy(update={
        "client_request_key": "synthetic-invalid-path"}))
    assert runner.run_once().status == "failed"
    with database.session() as session:
        assert session.get(SyncRun, invalid.id).status == "failed"
        assert session.scalar(select(BusinessEntity)).display_name == "Newer synthetic observation"
        assert session.get(SyncCheckpoint, "external").cursor == "25"
    with database.session() as session:
        session.get(RawPageManifest, "raw-origin").storage_key = blob.storage_key
        session.commit()
    downgraded = enqueue_replay(database, actor, "raw-origin", request.model_copy(update={
        "client_request_key": "synthetic-schema-downgrade"}))
    with database.session() as session:
        session.get(SourceResource, "resource").schema_status = "schema_pending"
        session.commit()
    assert runner.run_once().status == "failed"
    with database.session() as session:
        assert session.get(SyncRun, downgraded.id).records_written == 0
        assert session.scalar(select(BusinessEntity)).display_name == "Newer synthetic observation"
        session.get(SourceResource, "resource").schema_status = "confirmed"
        session.commit()
    fenced = enqueue_replay(database, actor, "raw-origin", request.model_copy(update={
        "client_request_key": "synthetic-scope-fenced"}))
    with database.session() as session:
        session.add(SourceMirrorPage(raw_manifest_id="raw-origin", enterprise_id="legal-a",
            source_resource_id="resource", acquisition_run_id="origin",
            projection_run_id=None, schema_status="confirmed", mapping_version=MAPPING_VERSION,
            created_at=datetime.now(UTC)))
        session.commit()
    with pytest.raises(ApiProblem) as changed:
        quarantine_mirror_page(database, actor, "raw-origin", MirrorQuarantineRequest(
            expected_content_hash="0" * 64, reason="scope_invalid"))
    assert changed.value.code == "mirror.content_changed"
    quarantined = quarantine_mirror_page(database, actor, "raw-origin",
        MirrorQuarantineRequest(expected_content_hash=blob.content_hash,
                                reason="scope_invalid"))
    assert quarantined.schema_status == "scope_invalid"
    assert quarantine_mirror_page(database, actor, "raw-origin", MirrorQuarantineRequest(
        expected_content_hash=blob.content_hash,
        reason="scope_invalid")).schema_status == "scope_invalid"
    assert runner.run_once().status == "failed"
    with database.session() as session:
        assert session.get(SyncRun, fenced.id).records_written == 0
        assert session.scalar(select(BusinessEntity)).display_name == "Newer synthetic observation"
    with pytest.raises(ApiProblem) as error:
        enqueue_replay(database, actor, "raw-origin", request.model_copy(update={
            "client_request_key": "synthetic-scope-invalid"}))
    assert error.value.code == "replay.unavailable"
    assert calls == []
    database.dispose()
