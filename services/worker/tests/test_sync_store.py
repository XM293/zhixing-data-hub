from sqlalchemy import create_engine, text

from zhixing_worker.sync_store import SyncStore


def test_probe_result_updates_resource_validation_ledger():
    from datetime import UTC, datetime

    from sqlalchemy.orm import Session
    from zhixing_api.data_models import Base, ExternalSystem, SourceResource, SyncRun

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(ExternalSystem(id="source", enterprise_id="a", system_key="erp",
            name="Synthetic", system_type="lingxing", base_url="https://example.invalid",
            status="configured"))
        session.add(SourceResource(id="resource", external_system_id="source",
            resource_key="shops", path="/synthetic", schema_status="confirmed", enabled=True))
        session.add(SyncRun(id="probe-failed", enterprise_id="a", external_system_id="source",
            source_version=1, status="queued", scenario="probe", volume_profile="standard",
            started_at=now, idempotency_key="probe-failed", request_id="probe-failed",
            scope_snapshot={}))
        session.commit()
    store = SyncStore(engine)
    failed = store.begin_resource(sync_run_id="probe-failed", source_key="erp",
        resource_key="shops", partition="failed", enterprise_id="a")
    store.finish_resource(failed.run_id, status="failed", error_code="sync.schema_pending")
    with Session(engine) as session:
        resource = session.get(SourceResource, "resource")
        assert resource.validation_status == "needs_attention"
        assert resource.validation_run_id == "probe-failed"
        assert resource.validation_error_code == "sync.schema_pending"
        assert resource.last_validated_at is not None
        session.add(SyncRun(id="probe-success", enterprise_id="a", external_system_id="source",
            source_version=1, status="queued", scenario="probe", volume_profile="standard",
            started_at=now, idempotency_key="probe-success", request_id="probe-success",
            scope_snapshot={}))
        session.commit()
    succeeded = store.begin_resource(sync_run_id="probe-success", source_key="erp",
        resource_key="shops", partition="success", enterprise_id="a")
    store.finish_resource(succeeded.run_id)
    with Session(engine) as session:
        resource = session.get(SourceResource, "resource")
        assert resource.validation_status == "validated"
        assert resource.validation_run_id == "probe-success"
        assert resource.validation_error_code is None
    engine.dispose()


def test_page_commit_checks_current_source_disable_and_schema_in_transaction():
    from datetime import UTC, datetime

    import pytest
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session
    from zhixing_api.data_models import (
        Base,
        ExternalSystem,
        RawPageManifest,
        SourceResource,
        SyncCheckpoint,
        SyncRun,
    )
    from zhixing_jobs import PermanentJobError

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(ExternalSystem(id="source", enterprise_id="a", system_key="erp",
            name="Synthetic", system_type="lingxing", base_url="https://example.invalid"))
        session.add(SourceResource(id="resource", external_system_id="source", resource_key="shops",
            path="/synthetic", schema_status="schema_pending", enabled=True))
        session.add(SyncRun(id="run", enterprise_id="a", external_system_id="source",
                           status="queued", scenario="normal", started_at=datetime.now(UTC)))
        session.commit()
    store = SyncStore(engine)
    ref = store.begin_resource(sync_run_id="run", source_key="erp", resource_key="shops",
                               enterprise_id="a", partition="default")
    arguments = dict(partition="default", cursor="1", storage_key="synthetic.json.gz",
                     content_hash="a" * 64, byte_count=1, row_count=1, page_number=1,
                     request_parameters={"sid": 2, "start_date": "2026-09-01"},
                     schema_status="confirmed", write_canonical=lambda *args:
                         pytest.fail("Pending schema must never invoke canonical persistence"))
    assert store.record_page(ref, **arguments)
    with Session(engine) as session:
        manifest = session.scalar(select(RawPageManifest))
        assert manifest.schema_status == "schema_pending"
        assert manifest.request_parameters == {"sid": 2, "start_date": "2026-09-01"}
        session.get(ExternalSystem, "source").status = "disabled"
        session.commit()
    with pytest.raises(PermanentJobError):
        store.record_page(ref, **{**arguments, "cursor": "2", "page_number": 2,
                                  "content_hash": "b" * 64})
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RawPageManifest)) == 1
        assert session.scalar(select(SyncCheckpoint)).cursor == "1"
    engine.dispose()


def test_manifest_and_checkpoint_are_transactional_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        for statement in (
            "CREATE TABLE external_systems (id TEXT PRIMARY KEY, system_key TEXT)",
            "CREATE TABLE source_resources (id TEXT PRIMARY KEY, "
            "external_system_id TEXT, resource_key TEXT, enabled BOOLEAN)",
            "CREATE TABLE sync_resource_runs (id TEXT PRIMARY KEY, sync_run_id TEXT, "
            "source_resource_id TEXT, status TEXT, partition_key TEXT, "
            "records_read INTEGER, records_written INTEGER)",
            "CREATE TABLE sync_checkpoints (id TEXT PRIMARY KEY, "
            "source_resource_id TEXT, partition_key TEXT, cursor TEXT, status TEXT)",
            "CREATE TABLE raw_page_manifests (id TEXT PRIMARY KEY, "
            "sync_resource_run_id TEXT, storage_key TEXT, content_hash TEXT UNIQUE, "
            "compression TEXT, bytes INTEGER, row_count INTEGER)",
        ):
            connection.execute(text(statement))
        connection.execute(
            text("INSERT INTO external_systems VALUES ('source-1', 'lingxing-main')")
        )
        connection.execute(
            text(
                "INSERT INTO source_resources "
                "VALUES ('resource-1', 'source-1', 'orders', true)"
            )
        )

    store = SyncStore(engine)
    ref = store.begin_resource(
        sync_run_id="run-1",
        source_key="lingxing-main",
        resource_key="orders",
        partition="shop-1",
    )
    arguments = {
        "partition": "shop-1",
        "cursor": "2",
        "storage_key": "ab/hash.json.gz",
        "content_hash": "a" * 64,
        "byte_count": 120,
        "row_count": 3,
    }
    assert store.record_page(ref, **arguments) is True
    assert store.record_page(ref, **arguments) is False
    store.finish_resource(ref.run_id)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM raw_page_manifests")).scalar_one() == 1
        assert connection.execute(text("SELECT cursor FROM sync_checkpoints")).scalar_one() == "2"
        row = connection.execute(
            text("SELECT status, records_read, records_written FROM sync_resource_runs")
        ).one()
        assert tuple(row) == ("succeeded", 3, 0)
