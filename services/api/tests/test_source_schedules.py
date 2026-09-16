import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from zhixing_connectors.catalog import OFFICIAL_RAW_SPECS, ResourceSpec
from zhixing_jobs.models import BackgroundJob

from zhixing_api.actor_context import resolve_database_actor
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.data_models import (
    ExternalSystem,
    RawPageManifest,
    SourceDependencyValue,
    SourceResource,
    SourceSyncSchedule,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.planning import ScheduleRequest, plan_import, schedule_strategy
from zhixing_api.ingestion.schedules import _next_import, dispatch_due, save_schedule
from zhixing_api.scope_context import build_scope_context


def test_schedule_only_advances_after_success_rechecks_authority_and_reconciles(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'schedule_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
                      plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
                      credential_provider=lambda _: "Synthetic-Only-Password-397!")
    actor = resolve_database_actor(database, login_name="admin-1@verify", enterprise_id="legal-a",
                                   request_id="synthetic-request", run_id="synthetic-run")
    with database.session() as session:
        session.add(ExternalSystem(id="src", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="orders-res", external_system_id="src", resource_key="orders",
            method="POST", path="/erp/sc/data/mws/orders", enabled=True, schema_status="confirmed"))
        session.commit()
    now = datetime(2026, 9, 1, tzinfo=UTC)
    request = ScheduleRequest(name="Synthetic incremental", resource_key="orders",
        projection_mode="deferred",
        strategy="updated_utc", initial_start=now - timedelta(days=1))
    schedule = save_schedule(database, actor=actor, source_key="erp", payload=request,
                              scope=build_scope_context(database, actor).snapshot(), now=now)
    assert schedule.status == "paused"
    assert schedule.projection_mode == "deferred"
    assert dispatch_due(database, provider_enabled=True, now=now) == 0
    schedule = save_schedule(database, actor=actor, source_key="erp",
        payload=request.model_copy(update={"status": "active"}),
        scope=build_scope_context(database, actor).snapshot(), schedule_id=schedule.id, now=now)
    assert dispatch_due(database, provider_enabled=False, now=now) == 0
    assert dispatch_due(database, provider_enabled=True, now=now) == 1
    assert dispatch_due(database, provider_enabled=True, now=now) == 0
    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        assert current.watermark is None and current.active_run_id
        child = session.scalar(select(SyncRun).where(
            SyncRun.parent_run_id == current.active_run_id))
        child.status = "partial_failed"
        session.commit()
    dispatch_due(database, provider_enabled=True, now=now + timedelta(minutes=5))
    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        assert current.status == "needs_attention" and current.watermark is None
        assert current.error_code == "schedule.batch_partial_failed"
    # A reviewed resume retries the same time range without pretending the failed import succeeded.
    save_schedule(database, actor=actor, source_key="erp",
        payload=request.model_copy(update={"status": "active"}),
        scope=build_scope_context(database, actor).snapshot(), schedule_id=schedule.id, now=now)
    assert dispatch_due(database, provider_enabled=True, now=now) == 1
    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        child = session.scalar(select(SyncRun).where(
            SyncRun.parent_run_id == current.active_run_id))
        child.status = "succeeded"
        session.commit()
    dispatch_due(database, provider_enabled=True, now=now + timedelta(minutes=1))
    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        assert current.watermark.replace(tzinfo=UTC) == now - timedelta(seconds=120)
        assert current.last_success_at and current.active_run_id is None
    later = now + timedelta(days=1, minutes=10)
    assert dispatch_due(database, provider_enabled=True, now=later) == 1
    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        assert current.pending_reconciliation
        child = session.scalar(select(SyncRun).where(
            SyncRun.parent_run_id == current.active_run_id))
        job = session.get(BackgroundJob, child.task_id)
        assert job.payload["projection_mode"] == "deferred"
        assert datetime.fromisoformat(job.payload["window_start"]) <= now - timedelta(days=1)
        child.status = "succeeded"
        session.commit()
    dispatch_due(database, provider_enabled=True, now=later + timedelta(minutes=1))
    with database.session() as session:
        source = session.get(ExternalSystem, "src")
        source.status = "disabled"
        count = session.scalar(select(func.count()).select_from(BackgroundJob))
        session.commit()
    dispatch_due(database, provider_enabled=True, now=later + timedelta(hours=1))
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(BackgroundJob)) == count
        assert session.get(SourceSyncSchedule, schedule.id).status == "needs_attention"
    database.dispose()


def test_parameterized_snapshot_schedule_preserves_partition_identity(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'parameter_schedule_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
                      plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
                      credential_provider=lambda _: "Synthetic-Only-Password-398!")
    actor = resolve_database_actor(database, login_name="admin-1@verify", enterprise_id="legal-a",
                                   request_id="synthetic-request", run_id="synthetic-run")
    with database.session() as session:
        session.add(ExternalSystem(id="src", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="listing-res", external_system_id="src",
            resource_key="listings", method="POST", path="/erp/sc/data/mws/listing",
            enabled=True, schema_status="confirmed"))
        session.commit()
    with pytest.raises(ValueError):
        ScheduleRequest(name="Missing partition", resource_key="listings", strategy="snapshot")
    request = ScheduleRequest(name="Deleted listings", resource_key="listings",
        strategy="snapshot", status="active", interval_seconds=3600,
        resource_parameters={"sid": "23", "is_delete": "1"})
    schedule = save_schedule(database, actor=actor, source_key="erp", payload=request,
        scope=build_scope_context(database, actor).snapshot(), now=datetime(2026, 9, 1, tzinfo=UTC))
    assert schedule.resource_parameters == {"sid": "23", "is_delete": "1"}
    with pytest.raises(ApiProblem) as error:
        save_schedule(database, actor=actor, source_key="erp",
            payload=request.model_copy(update={"resource_parameters": {"sid": "24",
                                                                         "is_delete": "1"}}),
            scope=build_scope_context(database, actor).snapshot(), schedule_id=schedule.id,
            expected_version=schedule.version, now=datetime(2026, 9, 1, tzinfo=UTC))
    assert error.value.code == "source.schedule_identity_changed"
    assert dispatch_due(database, provider_enabled=True,
                        now=datetime(2026, 9, 1, tzinfo=UTC)) == 1
    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        child = session.scalar(select(SyncRun).where(
            SyncRun.parent_run_id == current.active_run_id))
        job = session.get(BackgroundJob, child.task_id)
        assert job.payload["resource_parameters"] == {"sid": "23", "is_delete": "1"}
    database.dispose()


def test_window_schedule_emits_catalog_partition_parameters(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'window_schedule_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
                      plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
                      credential_provider=lambda _: "Synthetic-Only-Password-399!")
    actor = resolve_database_actor(database, login_name="admin-1@verify", enterprise_id="legal-a",
                                   request_id="synthetic-request", run_id="synthetic-run")
    with database.session() as session:
        session.add(ExternalSystem(id="src", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="after-sales-res", external_system_id="src",
            resource_key="after_sales", method="POST", path="/synthetic", enabled=True,
            schema_status="confirmed"))
        session.commit()
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    schedule = save_schedule(database, actor=actor, source_key="erp", payload=ScheduleRequest(
        name="After sales", resource_key="after_sales", strategy="updated_utc", status="active",
        initial_start=datetime(2026, 9, 1, tzinfo=UTC)),
        scope=build_scope_context(database, actor).snapshot(), now=now)
    assert dispatch_due(database, provider_enabled=True, now=now) == 1
    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        child = session.scalar(select(SyncRun).where(
            SyncRun.parent_run_id == current.active_run_id))
        job = session.get(BackgroundJob, child.task_id)
        assert job.payload["resource_parameters"] == {}
        assert job.payload["window_start"].startswith("2026-09-01")
        assert job.payload["window_end"].startswith("2026-09-08")
    database.dispose()


def test_single_date_schedule_emits_complete_daily_partitions(monkeypatch):
    spec = ResourceSpec("daily", "POST", "/readonly", "W8",
        required_parameters=("sid", "event_date"), window_fields=("event_date",),
        window_format="date", schedule_strategy="source_window")
    monkeypatch.setattr("zhixing_api.ingestion.schedules.resource_spec", lambda _: spec)
    monkeypatch.setattr("zhixing_api.ingestion.schedules.schedule_strategy",
                        lambda _: "source_window")
    monkeypatch.setattr("zhixing_api.ingestion.planning.resource_spec", lambda _: spec)
    row = SimpleNamespace(resource_key="daily", strategy="source_window",
        initial_start=datetime(2026, 9, 1, 15, tzinfo=UTC), watermark=None,
        overlap_seconds=300, safety_lag_seconds=120, last_reconciled_at=None,
        reconcile_days=7, pending_reconciliation=False, id="daily-plan", version=1,
        projection_mode="deferred", resource_parameters={"sid": "23"})
    request = _next_import(row, datetime(2026, 9, 10, 12, tzinfo=UTC))
    assert request is not None and request.partition_days == 1
    pieces = plan_import(request)
    assert len(pieces) == 7
    assert pieces[0].window_start == datetime(2026, 9, 1, tzinfo=UTC)
    assert pieces[-1].window_end == datetime(2026, 9, 8, tzinfo=UTC)


def test_running_schedule_does_not_starve_ready_schedule(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'schedule_fairness_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Only-Password-400!")
    actor = resolve_database_actor(database, login_name="admin-1@verify", enterprise_id="legal-a",
                                   request_id="synthetic-request", run_id="synthetic-run")
    with database.session() as session:
        session.add(ExternalSystem(id="src", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="orders-res", external_system_id="src",
            resource_key="orders", method="POST", path="/erp/sc/data/mws/orders", enabled=True,
            schema_status="confirmed"))
        session.commit()
    now = datetime(2026, 9, 10, tzinfo=UTC)
    payload = ScheduleRequest(name="Synthetic incremental", resource_key="orders",
        strategy="updated_utc", status="active", initial_start=now - timedelta(days=1))
    blocker = save_schedule(database, actor=actor, source_key="erp", payload=payload,
        scope=build_scope_context(database, actor).snapshot(), now=now - timedelta(minutes=1))
    ready = save_schedule(database, actor=actor, source_key="erp",
        payload=payload.model_copy(update={"name": "Ready incremental"}),
        scope=build_scope_context(database, actor).snapshot(), now=now)
    with database.session() as session:
        parent = SyncRun(id="running-parent", enterprise_id="legal-a",
            external_system_id="src", source_version=1, status="running", scenario="import",
            volume_profile="standard", started_at=now - timedelta(minutes=1),
            idempotency_key="running-parent", request_id="synthetic-running",
            scope_snapshot={})
        session.add(parent)
        current = session.get(SourceSyncSchedule, blocker.id)
        current.active_run_id = parent.id
        current.next_run_at = now - timedelta(minutes=1)
        session.commit()
    assert dispatch_due(database, provider_enabled=True, now=now, limit=1) == 1
    with database.session() as session:
        assert session.get(SourceSyncSchedule, blocker.id).active_run_id == "running-parent"
        assert session.get(SourceSyncSchedule, ready.id).active_run_id is not None
    database.dispose()


def test_auto_official_resources_have_recurring_strategy():
    auto = [spec for spec in OFFICIAL_RAW_SPECS
            if not (set(spec.required_parameters) - set(spec.window_fields)
                    - {str(spec.scope_parameter)})]
    assert len(auto) == 186
    assert all(schedule_strategy(spec.key) == (
        "source_window" if spec.window_fields else "snapshot") for spec in auto)


def test_parameter_fanout_schedule_batches_one_window_before_advancing_watermark(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'schedule_fanout_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Only-Password-432!")
    actor = resolve_database_actor(database, login_name="admin-1@verify",
                                   enterprise_id="legal-a", request_id="synthetic-request",
                                   run_id="synthetic-run")
    key = "official_8e9e5f51f4aa10e1"
    spec = next(item for item in OFFICIAL_RAW_SPECS if item.key == key)
    with database.session() as session:
        session.add(ExternalSystem(id="src", enterprise_id="legal-a", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="enum-resource", external_system_id="src",
            resource_key=key, method=spec.method, path=spec.path, enabled=True,
            schema_status="confirmed", validation_status="validated", version="synthetic-v1"))
        session.commit()
    now = datetime(2026, 9, 11, 12, tzinfo=UTC)
    schedule = save_schedule(database, actor=actor, source_key="erp", payload=ScheduleRequest(
        name="Enum fanout", resource_key=key, strategy="source_window", status="active",
        resource_parameters={"sids": "23"}, initial_start=now - timedelta(days=1)),
        scope=build_scope_context(database, actor).snapshot(), now=now)
    assert schedule.parameter_policy_version == "lingxing-parameter-policy-2026-09-13.5"

    expected_batches = (32, 32, 8)
    for ordinal, expected in enumerate(expected_batches):
        assert dispatch_due(database, provider_enabled=True,
                            now=now + timedelta(minutes=ordinal * 2)) == 1
        with database.session() as session:
            current = session.get(SourceSyncSchedule, schedule.id)
            children = list(session.scalars(select(SyncRun).where(
                SyncRun.parent_run_id == current.active_run_id)))
            assert len(children) == expected
            for child in children:
                job = session.get(BackgroundJob, child.task_id)
                assert set(job.payload["resource_parameters"]) == {
                    "sids", "data_type", "date_unit", "result_type"}
                child.status = "succeeded"
            session.commit()
        dispatch_due(database, provider_enabled=True,
                     now=now + timedelta(minutes=ordinal * 2 + 1))

    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        assert current.active_run_id is None
        assert current.parameter_fanout_offset == 0
        assert current.parameter_fanout_total == 72
        assert current.parameter_cycle_as_of is None
        assert current.watermark is not None
    database.dispose()


def test_parameter_fanout_schedule_waits_for_scoped_dependency_values(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'schedule_dependency_wait_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Only-Password-433!")
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
    schedule = save_schedule(database, actor=actor, source_key="erp", payload=ScheduleRequest(
        name="Dependency fanout", resource_key=key, strategy="source_window", status="active",
        resource_parameters={"storeId": "23"}, initial_start=now - timedelta(days=1)),
        scope=build_scope_context(database, actor).snapshot(), now=now)
    assert dispatch_due(database, provider_enabled=True, now=now) == 0
    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        assert current.status == "waiting_for_dependency"
        assert current.parameter_waiting_code == "source.dependency_values_unavailable"
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
        for ordinal, scope_key in enumerate(("store:24", "store:23"), 1):
            session.add(SourceDependencyValue(id=f"dependency-{ordinal}",
                enterprise_id="legal-a", external_system_id="src",
                source_resource_id="dependency-resource",
                first_manifest_id="dependency-manifest", last_manifest_id="dependency-manifest",
                value_type="msku", external_value=f"MSKU-{ordinal}",
                value_hash=str(ordinal) * 64, scope_kind="store",
                scope_external_key=scope_key, status="active", first_seen_at=now,
                last_seen_at=now, occurrence_count=1, extractor_version="synthetic"))
        session.commit()
    assert dispatch_due(database, provider_enabled=True,
                        now=now + timedelta(minutes=5)) == 1
    with database.session() as session:
        current = session.get(SourceSyncSchedule, schedule.id)
        child = session.scalar(select(SyncRun).where(
            SyncRun.parent_run_id == current.active_run_id))
        job = session.get(BackgroundJob, child.task_id)
        assert job.payload["resource_parameters"]["sellerSku"] == "MSKU-2"
        assert job.payload["resource_parameters"]["storeId"] == "23"
    database.dispose()
