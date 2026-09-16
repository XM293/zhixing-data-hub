import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from zhixing_connectors.catalog import OFFICIAL_RAW_SPECS, resource_spec

from zhixing_api.actor_context import resolve_database_actor
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.data_models import (
    ExternalSystem,
    SourceBackfillPlan,
    SourceBinding,
    SourceResource,
    SourceSyncSchedule,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.rollout import (
    OfficialBackfillRolloutRequest,
    OfficialScheduleRolloutRequest,
    rollout_validated_store_backfills,
    rollout_validated_store_schedules,
)
from zhixing_api.scope_context import build_scope_context


def _auto_store_spec(*, scalar: bool, windowed: bool):
    return next(spec for spec in OFFICIAL_RAW_SPECS
        if spec.scope_kind == "store"
        and (spec.scope_parameter_mode == "scalar") == scalar
        and bool(spec.window_fields) == windowed
        and not (set(spec.required_parameters) - set(spec.window_fields)
                 - {str(spec.scope_parameter)}))


def test_validated_store_rollout_is_scoped_atomic_and_idempotent(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'rollout_verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
                      plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
                      credential_provider=lambda _: "Synthetic-Only-Password-430!")
    actor = resolve_database_actor(database, login_name="admin-1@verify", enterprise_id="legal-a",
                                   request_id="synthetic-request", run_id="synthetic-run")
    scalar = _auto_store_spec(scalar=True, windowed=False)
    grouped = _auto_store_spec(scalar=False, windowed=True)
    parameterized = next(spec for spec in OFFICIAL_RAW_SPECS
        if spec.key == "official_8e9e5f51f4aa10e1")
    multiplatform = resource_spec("official_2dbe32f66db9cd5b")
    assert multiplatform is not None and multiplatform.scope_namespace == "multiplatform"
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    with database.session() as session:
        session.add(ExternalSystem(id="source", enterprise_id="legal-a",
            business_unit_id="project-a", system_key="erp", name="Synthetic ERP",
            system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        for spec in (scalar, grouped, parameterized, multiplatform):
            session.add(SourceResource(id=f"resource-{spec.key}", external_system_id="source",
                resource_key=spec.key, method=spec.method, path=spec.path,
                enabled=True, schema_status="confirmed", validation_status="validated",
                version="synthetic-v1"))
        for ordinal in (11, 22):
            session.add(SourceBinding(id=f"binding-{ordinal}", enterprise_id="legal-a",
                business_unit_id="project-a", source_system_id="source",
                external_key=f"store:{ordinal}", canonical_type="store",
                canonical_id=f"store-{ordinal}", mapping_version="synthetic-v1",
                status="approved", suggestion_evidence=[], suggestion_evidence_count=0,
                created_at=now, updated_at=now))
        session.commit()

    scope = build_scope_context(database, actor,
        selection={"scope_level": "business_unit", "business_unit_ids": ["project-a"]})
    request = OfficialScheduleRolloutRequest(
        business_unit_id="project-a", status="paused",
        incremental_start=datetime(2026, 1, 1, tzinfo=UTC))
    first = rollout_validated_store_schedules(database, actor=actor, source_key="erp",
        payload=request, scope=scope, now=now)
    assert first.approved_store_count == 2
    assert first.validated_resource_count == 3
    assert first.planned_schedule_count == first.created_count == 4

    second = rollout_validated_store_schedules(database, actor=actor, source_key="erp",
        payload=request, scope=scope, now=now)
    assert second.created_count == second.updated_count == 0
    assert second.unchanged_count == 4

    activated = rollout_validated_store_schedules(database, actor=actor, source_key="erp",
        payload=request.model_copy(update={"status": "active"}), scope=scope, now=now)
    assert activated.updated_count == 4
    with database.session() as session:
        for resource in session.scalars(select(SourceResource)):
            resource.version = "synthetic-v2"
        session.commit()
    rebound = rollout_validated_store_schedules(database, actor=actor, source_key="erp",
        payload=request.model_copy(update={"status": "active"}), scope=scope, now=now)
    assert rebound.updated_count == 4
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(SourceSyncSchedule)) == 4
        rows = list(session.scalars(select(SourceSyncSchedule)))
        assert all(row.status == "active" and row.projection_mode == "deferred" for row in rows)
        assert all(row.resource_version == "synthetic-v2" for row in rows)
        scalar_values = sorted(row.resource_parameters[str(scalar.scope_parameter)]
                               for row in rows if row.resource_key == scalar.key)
        assert scalar_values == ["11", "22"]
        grouped_row = next(row for row in rows if row.resource_key == grouped.key)
        assert grouped_row.resource_parameters[str(grouped.scope_parameter)] == "11,22"
        parameterized_row = next(row for row in rows if row.resource_key == parameterized.key)
        assert parameterized_row.resource_parameters == {"sids": "11,22"}
        assert parameterized_row.parameter_policy_version == (
        "lingxing-parameter-policy-2026-09-13.5")
        assert all(row.resource_key != multiplatform.key for row in rows)

    restricted_scope = build_scope_context(database, actor,
        selection={"scope_level": "business_unit", "business_unit_ids": ["brand-a"]})
    with pytest.raises(ApiProblem) as denied:
        rollout_validated_store_schedules(database, actor=actor, source_key="erp",
            payload=request, scope=restricted_scope, now=now)
    assert denied.value.code == "scope.business_unit_denied"
    database.dispose()


def test_validated_store_history_rollout_uses_contract_windows_and_is_idempotent(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'history-rollout-verify.db'}")
    database.migrate()
    manifest = json.loads((Path(__file__).parent / "fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, backup_id="synthetic-backup", confirmed=True,
                      plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
                      credential_provider=lambda _: "Synthetic-Only-Password-431!")
    actor = resolve_database_actor(database, login_name="admin-1@verify", enterprise_id="legal-a",
                                   request_id="synthetic-request", run_id="synthetic-run")
    grouped = next(spec for spec in OFFICIAL_RAW_SPECS
        if spec.scope_kind == "store" and spec.scope_parameter_mode != "scalar"
        and spec.window_fields and spec.max_window_days == 90
        and not (set(spec.required_parameters) - set(spec.window_fields)
                 - {str(spec.scope_parameter)}))
    scalar = next(spec for spec in OFFICIAL_RAW_SPECS
        if spec.scope_kind == "store" and spec.scope_parameter_mode == "scalar"
        and spec.window_fields and spec.max_window_days == 365
        and not (set(spec.required_parameters) - set(spec.window_fields)
                 - {str(spec.scope_parameter)}))
    parameterized = next(spec for spec in OFFICIAL_RAW_SPECS
        if spec.key == "official_8e9e5f51f4aa10e1")
    now = datetime(2026, 9, 10, 12, tzinfo=UTC)
    with database.session() as session:
        session.add(ExternalSystem(id="source", enterprise_id="legal-a",
            business_unit_id="project-a", system_key="erp", name="Synthetic ERP",
            system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        for spec in (scalar, grouped, parameterized):
            session.add(SourceResource(id=f"resource-{spec.key}", external_system_id="source",
                resource_key=spec.key, method=spec.method, path=spec.path,
                enabled=True, schema_status="confirmed", validation_status="validated",
                version="synthetic-v1"))
        for ordinal in (11, 22):
            session.add(SourceBinding(id=f"binding-{ordinal}", enterprise_id="legal-a",
                business_unit_id="project-a", source_system_id="source",
                external_key=f"store:{ordinal}", canonical_type="store",
                canonical_id=f"store-{ordinal}", mapping_version="synthetic-v1",
                status="approved", suggestion_evidence=[], suggestion_evidence_count=0,
                created_at=now, updated_at=now))
        session.commit()

    scope = build_scope_context(database, actor,
        selection={"scope_level": "business_unit", "business_unit_ids": ["project-a"]})
    request = OfficialBackfillRolloutRequest(
        business_unit_id="project-a", status="paused",
        history_start=datetime(2025, 8, 1, tzinfo=UTC),
        history_end=datetime(2026, 9, 5, tzinfo=UTC), batch_size=8)
    first = rollout_validated_store_backfills(database, actor=actor, source_key="erp",
        payload=request, scope=scope, now=now)
    assert first.approved_store_count == 2
    assert first.validated_resource_count == 3
    assert first.planned_backfill_count == first.created_count == 4
    assert first.planned_window_count == 14

    second = rollout_validated_store_backfills(database, actor=actor, source_key="erp",
        payload=request, scope=scope, now=now)
    assert second.created_count == second.updated_count == 0
    assert second.unchanged_count == 4

    activated = rollout_validated_store_backfills(database, actor=actor, source_key="erp",
        payload=request.model_copy(update={"status": "active"}), scope=scope, now=now)
    assert activated.updated_count == 4
    with database.session() as session:
        rows = list(session.scalars(select(SourceBackfillPlan)))
        assert len(rows) == 4
        scalar_rows = [row for row in rows if row.resource_key == scalar.key]
        grouped_row = next(row for row in rows if row.resource_key == grouped.key)
        assert len(scalar_rows) == 2
        assert all(row.partition_days == 365 and row.windows_total == 2
                   and row.status == "active" for row in scalar_rows)
        assert grouped_row.partition_days == 90 and grouped_row.windows_total == 5
        assert grouped_row.resource_parameters[str(grouped.scope_parameter)] == "11,22"
        parameterized_row = next(row for row in rows
                                 if row.resource_key == parameterized.key)
        assert parameterized_row.parameter_policy_version == (
        "lingxing-parameter-policy-2026-09-13.5")
        for resource in session.scalars(select(SourceResource)):
            resource.version = "synthetic-v2"
        session.commit()
    rebound = rollout_validated_store_backfills(database, actor=actor, source_key="erp",
        payload=request.model_copy(update={"status": "active"}), scope=scope, now=now)
    assert rebound.created_count == 0 and rebound.updated_count == 4
    with database.session() as session:
        rows = list(session.scalars(select(SourceBackfillPlan)))
        assert len(rows) == 4
        assert all(row.resource_version == "synthetic-v2" for row in rows)
    database.dispose()
