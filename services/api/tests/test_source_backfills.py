import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from zhixing_connectors.catalog import OFFICIAL_RAW_SPECS
from zhixing_jobs.models import BackgroundJob

from zhixing_api.actor_context import resolve_database_actor
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.data_models import (
    ExternalSystem,
    RawPageManifest,
    SourceBackfillPlan,
    SourceCoverageWindow,
    SourceDependencyValue,
    SourceResource,
    SyncCheckpoint,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.ingestion.backfills import BackfillRequest, dispatch_backfills, save_backfill
from zhixing_api.scope_context import build_scope_context


def _database(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'backfill_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
                      plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
                      credential_provider=lambda _: "Synthetic-Only-Password-401!")
    with database.session() as session:
        session.add(ExternalSystem(id="src", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="orders-res", external_system_id="src",
            resource_key="orders", method="POST", path="/erp/sc/data/mws/orders",
            enabled=True, schema_status="confirmed"))
        session.commit()
    return database


def _actor_and_scope(database):
    actor = resolve_database_actor(database, login_name="admin-1@verify",
                                   enterprise_id="legal-a", request_id="synthetic-request",
                                   run_id="synthetic-run")
    return actor, build_scope_context(database, actor).snapshot()


def test_backfill_records_each_window_and_advances_only_acquired_coverage(tmp_path):
    database = _database(tmp_path)
    actor, scope = _actor_and_scope(database)
    start = datetime(2026, 8, 1, tzinfo=UTC)
    request = BackfillRequest(name="Order history", resource_key="orders", status="paused",
        window_start=start, window_end=start + timedelta(days=20), partition_days=7,
        batch_size=3, projection_mode="deferred")
    plan = save_backfill(database, actor=actor, source_key="erp", payload=request, scope=scope,
                         now=start + timedelta(days=30))
    assert plan.status == "paused" and plan.windows_total == 3
    assert dispatch_backfills(database, provider_enabled=True, now=start) == 0

    plan = save_backfill(database, actor=actor, source_key="erp",
        payload=request.model_copy(update={"status": "active"}), scope=scope,
        backfill_id=plan.id, expected_version=plan.version, now=start + timedelta(days=30))
    assert dispatch_backfills(database, provider_enabled=True, now=start + timedelta(days=30)) == 1
    with database.session() as session:
        current = session.get(SourceBackfillPlan, plan.id)
        windows = list(session.scalars(select(SourceCoverageWindow).where(
            SourceCoverageWindow.backfill_plan_id == plan.id).order_by(
                SourceCoverageWindow.window_start)))
        assert len(windows) == 3 and all(item.status == "queued" for item in windows)
        assert windows[0].window_start.replace(tzinfo=UTC) == start
        assert windows[-1].window_end.replace(tzinfo=UTC) == start + timedelta(days=20)
        children = list(session.scalars(select(SyncRun).where(
            SyncRun.parent_run_id == current.active_run_id).order_by(
                SyncRun.started_at, SyncRun.id)))
        by_id = {child.id: child for child in children}
        for ordinal, window in enumerate(windows):
            child = by_id[window.sync_run_id]
            child.status = "succeeded" if ordinal < 2 else "partial_failed"
            child.records_read = [8, 0, 3][ordinal]
            child.records_written = [8, 0, 0][ordinal]
            if ordinal == 2:
                resource_run = session.scalar(select(SyncResourceRun).where(
                    SyncResourceRun.sync_run_id == child.id))
                resource_run.status = "partial_failed"
                session.add(RawPageManifest(id="raw-conflict", sync_resource_run_id=resource_run.id,
                    storage_key="synthetic/raw.json.gz", content_hash="a" * 64, compression="gzip",
                    bytes=1, row_count=3, page_number=1, schema_status="confirmed",
                    request_parameters={}, fetched_at=start))
                session.add(SyncCheckpoint(id="checkpoint-conflict",
                    source_resource_id=resource_run.source_resource_id,
                    partition_key=resource_run.partition_key, cursor="1", status="completed",
                    updated_at=start))
        session.commit()

    assert dispatch_backfills(database, provider_enabled=True,
                              now=start + timedelta(days=30, minutes=1)) == 0
    with database.session() as session:
        current = session.get(SourceBackfillPlan, plan.id)
        assert current.status == "completed" and current.active_run_id is None
        assert current.cursor.replace(tzinfo=UTC) == request.window_end
        assert (current.windows_succeeded, current.windows_no_data,
                current.windows_with_conflicts, current.windows_failed) == (1, 1, 1, 0)
        assert (current.records_read, current.records_written) == (11, 8)
    database.dispose()


def test_backfill_failure_stops_at_failed_window_and_resume_retries_without_gaps(tmp_path):
    database = _database(tmp_path)
    actor, scope = _actor_and_scope(database)
    start = datetime(2026, 7, 1, tzinfo=UTC)
    request = BackfillRequest(name="Order history", resource_key="orders", status="active",
        window_start=start, window_end=start + timedelta(days=14), partition_days=7,
        batch_size=2)
    plan = save_backfill(database, actor=actor, source_key="erp", payload=request, scope=scope,
                         now=start + timedelta(days=30))
    assert dispatch_backfills(database, provider_enabled=True,
                              now=start + timedelta(days=30)) == 1
    with database.session() as session:
        current = session.get(SourceBackfillPlan, plan.id)
        windows = list(session.scalars(select(SourceCoverageWindow).where(
            SourceCoverageWindow.backfill_plan_id == plan.id).order_by(
                SourceCoverageWindow.window_start)))
        first, second = (session.get(SyncRun, item.sync_run_id) for item in windows)
        first.status, first.records_read = "succeeded", 2
        second.status = "failed"
        session.commit()
    dispatch_backfills(database, provider_enabled=True,
                       now=start + timedelta(days=30, minutes=1))
    with database.session() as session:
        current = session.get(SourceBackfillPlan, plan.id)
        assert current.status == "needs_attention"
        assert current.cursor.replace(tzinfo=UTC) == start + timedelta(days=7)
        assert current.windows_failed == 1
    save_backfill(database, actor=actor, source_key="erp",
        payload=request.model_copy(update={"status": "active"}), scope=scope,
        backfill_id=plan.id, expected_version=current.version,
        now=start + timedelta(days=30, minutes=2))
    assert dispatch_backfills(database, provider_enabled=True,
                              now=start + timedelta(days=30, minutes=2)) == 1
    with database.session() as session:
        current = session.get(SourceBackfillPlan, plan.id)
        retry = session.scalar(select(SourceCoverageWindow).where(
            SourceCoverageWindow.backfill_plan_id == plan.id,
            SourceCoverageWindow.window_start == start + timedelta(days=7)))
        assert retry.attempt_count == 2 and retry.sync_run_id
        retried_windows = list(session.scalars(select(SourceCoverageWindow).where(
            SourceCoverageWindow.backfill_plan_id == plan.id,
            SourceCoverageWindow.attempt_count == 2)))
        assert [item.window_start for item in retried_windows] == [retry.window_start]
        job = session.scalar(select(BackgroundJob).where(BackgroundJob.run_id == retry.sync_run_id))
        assert job.payload["window_start"].startswith("2026-07-08")
        assert current.active_run_id is not None
    database.dispose()


def test_single_date_resources_require_daily_backfill_partitions(monkeypatch):
    from zhixing_connectors.catalog import ResourceSpec

    monkeypatch.setattr("zhixing_api.ingestion.backfills.resource_spec", lambda _: ResourceSpec(
        "daily", "POST", "/readonly", "W8", required_parameters=("sid", "event_date"),
        window_fields=("event_date",), window_format="date", schedule_strategy="source_window"))
    start = datetime(2026, 9, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="source.single_date_partition_requires_one_day"):
        BackfillRequest(name="Daily history", resource_key="daily",
            resource_parameters={"sid": "23"}, window_start=start,
            window_end=start + timedelta(days=2), partition_days=2)


def test_backfill_partition_uses_documented_resource_limit(monkeypatch):
    from zhixing_connectors.catalog import ResourceSpec

    monkeypatch.setattr("zhixing_api.ingestion.backfills.resource_spec", lambda _: ResourceSpec(
        "history", "POST", "/readonly", "W8", required_parameters=("start", "end"),
        window_fields=("start", "end"),
        window_format="date", schedule_strategy="source_window", max_window_days=90))
    start = datetime(2026, 1, 1, tzinfo=UTC)
    request = BackfillRequest(name="Documented history", resource_key="history",
        window_start=start, window_end=start + timedelta(days=180), partition_days=90)
    assert request.partition_days == 90
    with pytest.raises(ValueError, match="source.partition_exceeds_contract"):
        BackfillRequest(name="Oversized history", resource_key="history",
            window_start=start, window_end=start + timedelta(days=180), partition_days=91)


def test_parameter_fanout_backfill_completes_every_partition_before_coverage(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'backfill_fanout_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Only-Password-434!")
    actor = resolve_database_actor(database, login_name="admin-1@verify",
                                   enterprise_id="legal-a", request_id="synthetic-request",
                                   run_id="synthetic-run")
    key = "official_8e9e5f51f4aa10e1"
    spec = next(item for item in OFFICIAL_RAW_SPECS if item.key == key)
    now = datetime(2026, 9, 11, 12, tzinfo=UTC)
    with database.session() as session:
        session.add(ExternalSystem(id="src", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="enum-resource", external_system_id="src",
            resource_key=key, method=spec.method, path=spec.path, enabled=True,
            schema_status="confirmed", validation_status="validated", version="synthetic-v1"))
        session.commit()
    request = BackfillRequest(name="Enum history", resource_key=key, status="active",
        resource_parameters={"sids": "23"}, window_start=now - timedelta(days=1),
        window_end=now, partition_days=1, batch_size=16, projection_mode="deferred")
    plan = save_backfill(database, actor=actor, source_key="erp", payload=request,
        scope=build_scope_context(database, actor).snapshot(), now=now)
    assert plan.parameter_policy_version == "lingxing-parameter-policy-2026-09-13.5"
    assert dispatch_backfills(database, provider_enabled=True, now=now) == 1

    for expected in (32, 32, 8):
        with database.session() as session:
            current = session.get(SourceBackfillPlan, plan.id)
            parent = session.get(SyncRun, current.active_run_id)
            children = list(session.scalars(select(SyncRun).where(
                SyncRun.parent_run_id == parent.id)))
            assert len(children) == expected
            coverage = session.scalar(select(SourceCoverageWindow).where(
                SourceCoverageWindow.backfill_plan_id == plan.id))
            assert coverage.sync_run_id == parent.id
            for child in children:
                child.status = "succeeded"
            session.commit()
        dispatch_backfills(database, provider_enabled=True, now=now + timedelta(minutes=1))

    with database.session() as session:
        current = session.get(SourceBackfillPlan, plan.id)
        coverage = session.scalar(select(SourceCoverageWindow).where(
            SourceCoverageWindow.backfill_plan_id == plan.id))
        assert current.status == "completed"
        assert current.cursor.replace(tzinfo=UTC) == request.window_end
        assert coverage.status == "no_data"
        assert coverage.parameter_fanout_offset == 0
        assert coverage.parameter_fanout_total == 72
        assert coverage.parameter_cycle_as_of is None
    database.dispose()


def test_parameter_fanout_backfill_waits_for_scoped_dependency_values(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'backfill_dependency_wait_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Only-Password-435!")
    actor = resolve_database_actor(database, login_name="admin-1@verify",
                                   enterprise_id="legal-a", request_id="synthetic-request",
                                   run_id="synthetic-run")
    key = "official_29c2ecea89316017"
    spec = next(item for item in OFFICIAL_RAW_SPECS if item.key == key)
    now = datetime(2026, 9, 11, 12, tzinfo=UTC)
    with database.session() as session:
        session.add(ExternalSystem(id="src", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="dependency-resource", external_system_id="src",
            resource_key=key, method=spec.method, path=spec.path, enabled=True,
            schema_status="confirmed", validation_status="validated", version="synthetic-v1"))
        session.commit()
    request = BackfillRequest(name="Dependency history", resource_key=key, status="active",
        resource_parameters={"storeId": "23"}, window_start=now - timedelta(days=1),
        window_end=now, partition_days=1, projection_mode="deferred")
    plan = save_backfill(database, actor=actor, source_key="erp", payload=request,
        scope=build_scope_context(database, actor).snapshot(), now=now)
    assert dispatch_backfills(database, provider_enabled=True, now=now) == 0
    with database.session() as session:
        current = session.get(SourceBackfillPlan, plan.id)
        coverage = session.scalar(select(SourceCoverageWindow).where(
            SourceCoverageWindow.backfill_plan_id == plan.id))
        assert current.status == "waiting_for_dependency"
        assert current.parameter_waiting_code == "source.dependency_values_unavailable"
        assert coverage.status == "fanout_pending"
        acquisition = SyncRun(id="dependency-acquisition", enterprise_id="legal-a",
            external_system_id="src", status="succeeded", scenario="normal", started_at=now,
            finished_at=now)
        session.add(acquisition)
        session.flush()
        session.add(SyncResourceRun(id="dependency-acquisition-resource",
            sync_run_id=acquisition.id, source_resource_id="dependency-resource",
            status="succeeded"))
        session.flush()
        session.add(RawPageManifest(id="dependency-manifest",
            sync_resource_run_id="dependency-acquisition-resource",
            storage_key="synthetic/dependency.json.gz", content_hash="a" * 64,
            schema_status="confirmed", fetched_at=now))
        session.flush()
        session.add(SourceDependencyValue(id="dependency", enterprise_id="legal-a",
            external_system_id="src", source_resource_id="dependency-resource",
            first_manifest_id="dependency-manifest", last_manifest_id="dependency-manifest",
            value_type="msku",
            external_value="MSKU-23", value_hash="1" * 64, scope_kind="store",
            scope_external_key="store:23", status="active", first_seen_at=now,
            last_seen_at=now, occurrence_count=1, extractor_version="synthetic"))
        session.commit()
    assert dispatch_backfills(database, provider_enabled=True,
                              now=now + timedelta(minutes=5)) == 1
    with database.session() as session:
        current = session.get(SourceBackfillPlan, plan.id)
        child = session.scalar(select(SyncRun).where(
            SyncRun.parent_run_id == current.active_run_id))
        job = session.get(BackgroundJob, child.task_id)
        assert job.payload["resource_parameters"]["sellerSku"] == "MSKU-23"
        assert job.payload["resource_parameters"]["storeId"] == "23"
    database.dispose()
