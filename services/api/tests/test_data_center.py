import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from zhixing_jobs.models import BackgroundJob

from zhixing_api import data_center_service
from zhixing_api.config import Settings
from zhixing_api.connectors.contracts import (
    CanonicalEntity,
    CanonicalMetric,
    ConnectorBatch,
    ExternalRecord,
)
from zhixing_api.data_models import (
    AuthorizationDecision,
    BusinessEntity,
    BusinessUnit,
    ExternalSystem,
    MappingConflict,
    MetricSnapshot,
    SourceRecord,
    SourceResource,
    SyncCheckpoint,
    SyncRun,
    TwinActor,
    TwinInteractionProfile,
    TwinMeetingParticipant,
    TwinMeetingSeat,
    TwinRoute,
    TwinScene,
    TwinSpace,
)
from zhixing_api.main import create_app

ADMIN_HEADERS = {"X-Zhixing-Demo-Actor": "admin"}
CEO_HEADERS = {"X-Zhixing-Demo-Actor": "ceo"}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
        meeting_auto_start_seconds=0.02,
        meeting_scheduler_poll_seconds=0.01,
    )


@pytest.mark.anyio
async def test_mapping_conflicts_and_checkpoints_are_source_filtered_and_paged(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    now = datetime.now(UTC)
    with app.state.database.session() as session:
        business_unit = session.scalar(select(BusinessUnit))
        assert business_unit is not None
        source = ExternalSystem(
            id="source-page-test",
            enterprise_id=business_unit.enterprise_id,
            business_unit_id=business_unit.id,
            system_key="page-test",
            name="Page Test",
            system_type="lingxing",
            base_url="https://openapi.lingxing.com",
            status="configured",
            source_schema_version="v1",
            mapping_version="v1",
            access_mode="read_only",
            created_at=now,
            updated_at=now,
        )
        resource_key = "orders-page-test"
        resource = SourceResource(
            id="resource-page-test",
            external_system_id=source.id,
            resource_key=resource_key,
            method="POST",
            path="/readonly",
            schema_status="confirmed",
            enabled=True,
            version="v1",
            updated_at=now,
        )
        session.add_all([source, resource])
        session.flush()
        session.add_all([
            MappingConflict(
                id=f"conflict-page-{index}",
                external_system_id=source.id,
                enterprise_id=business_unit.enterprise_id,
                external_object_key=f"object-{'match' if index < 2 else 'other'}-{index}",
                resource_key=resource_key,
                status="pending" if index < 2 else "rejected",
                candidates=[],
                resolution={"error_code": "mapping.unassigned"},
            )
            for index in range(3)
        ])
        session.add_all([
            SyncCheckpoint(
                id=f"checkpoint-page-{index}",
                source_resource_id=resource.id,
                partition_key=f"partition-{'match' if index < 2 else 'other'}-{index}",
                cursor=str(index),
                status="active" if index < 2 else "failed",
                updated_at=now,
            )
            for index in range(3)
        ])
        session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        conflicts = await client.get("/api/v1/data-center/mapping-conflicts/page", params={
            "source_key": "page-test", "status": "pending", "query": "match",
            "offset": 1, "limit": 1,
        })
        assert conflicts.status_code == 200
        assert conflicts.json()["page"] == {"offset": 1, "limit": 1, "total": 2}
        assert len(conflicts.json()["items"]) == 1
        assert conflicts.json()["status_counts"] == {"pending": 2, "rejected": 1}
        assert all(item["source_key"] == "page-test" for item in conflicts.json()["items"])

        checkpoints = await client.get(
            "/api/v1/data-center/sources/page-test/checkpoints",
            params={"resource_key": resource_key, "status": "active",
                    "query": "match", "offset": 1, "limit": 1},
        )
        assert checkpoints.status_code == 200
        assert checkpoints.json()["page"] == {"offset": 1, "limit": 1, "total": 2}
        assert len(checkpoints.json()["items"]) == 1
        assert checkpoints.json()["items"][0]["resource_key"] == resource_key


@pytest.mark.anyio
async def test_lingxing_source_management_uses_scope_and_credential_references(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    with app.state.database.session() as session:
        business_unit = session.scalar(select(BusinessUnit))
        assert business_unit is not None
        unit_id = business_unit.id
        session.add(BusinessEntity(id="synthetic-store", enterprise_id=business_unit.enterprise_id,
                    entity_type="store", canonical_key="store-synthetic",
                    display_name="Synthetic Store", status="unassigned", attributes={},
                    updated_at=datetime.now(UTC)))
        session.commit()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        created = await client.post("/api/v1/data-center/sources", json={
            "system_key": "lingxing-synthetic", "name": "Synthetic ERP",
            "business_unit_id": unit_id, "credential_ref": "env:LINGXING_SYNTHETIC",
        })
        assert created.status_code == 201
        assert created.json()["business_unit_id"] == unit_id
        assert "credential_ref" not in created.json()
        with app.state.database.session() as session:
            source = session.scalar(select(ExternalSystem).where(
                ExternalSystem.system_key == "lingxing-synthetic"))
            source_id = source.id
            session.add(SourceResource(id="blocked-write-resource",
                external_system_id=source_id,
                resource_key="official_72d2c55bdbc031ea", method="POST",
                path="/basicOpen/multiplatform/cargo/storage", enabled=True,
                schema_status="confirmed", validation_status="validated",
                version="stale-review"))
            session.commit()
        resources = await client.get("/api/v1/data-center/sources/lingxing-synthetic/resources")
        assert resources.json()["provider_enabled"] is False
        assert not any(item["can_execute"] for item in resources.json()["items"])
        official = await client.get(
            "/api/v1/data-center/sources/lingxing-synthetic/official-operations",
            params={"execution_status": "metadata_only", "limit": 20},
        )
        assert official.status_code == 200
        assert official.json()["summary"]["official_read_operations"] == 470
        assert official.json()["summary"]["official_contracts_confirmed"] == 470
        assert official.json()["summary"]["runtime_operations"] > 250
        assert official.json()["page"]["total"] < 434
        assert len(official.json()["items"]) == 20
        assert all(not item["can_execute"] for item in official.json()["items"])
        blocked_write = await client.get(
            "/api/v1/data-center/sources/lingxing-synthetic/official-operations",
            params={"query": "/basicOpen/multiplatform/cargo/storage"},
        )
        assert blocked_write.status_code == 200
        assert blocked_write.json()["page"]["total"] == 1
        assert blocked_write.json()["items"][0]["raw_eligible"] is False
        daily = await client.get(
            "/api/v1/data-center/sources/lingxing-synthetic/official-operations",
            params={"query": "/erp/sc/data/mws_report/dailyInventory"},
        )
        assert daily.status_code == 200 and daily.json()["page"]["total"] == 1
        operation = daily.json()["items"][0]
        assert operation["raw_eligible"] is True and operation["registered"] is False
        assert operation["scope_fields"] == ["sid"]
        activated = await client.put(
            f"/api/v1/data-center/sources/lingxing-synthetic/official-operations/"
            f"{operation['id']}/resource", json={"enabled": True})
        assert activated.status_code == 200
        assert activated.json()["key"].startswith("official_")
        assert activated.json()["schema_status"] == "confirmed"
        assert activated.json()["projectable"] is False
        materialized = await client.put(
            "/api/v1/data-center/sources/lingxing-synthetic/official-resources/materialize")
        assert materialized.status_code == 200
        assert materialized.json()["eligible"] == 265
        assert materialized.json()["created"] == materialized.json()["eligible"] - 1
        assert materialized.json()["existing"] == 1
        assert materialized.json()["enabled"] == 1
        assert materialized.json()["retired"] == 1
        assert len(materialized.json()["contract_version"]) <= 32
        with app.state.database.session() as session:
            blocked = session.get(SourceResource, "blocked-write-resource")
            assert blocked.enabled is False
            assert blocked.validation_error_code == "source.read_only_review_blocked"
        pending_resource = next(item for item in resources.json()["items"]
                                if item["key"] == "report_export_status")
        assert pending_resource["schema_status"] == "schema_pending"
        assert pending_resource["enabled"] is False
        enabled_pending = await client.patch(
            "/api/v1/data-center/sources/lingxing-synthetic/resources/report_export_status",
            json={"enabled": True})
        assert enabled_pending.json()["enabled"] is True
        assert enabled_pending.json()["schema_status"] == "schema_pending"
        assert enabled_pending.json()["projectable"] is False
        authority_payload = {"business_unit_id": unit_id, "source_key": "lingxing-synthetic",
            "fact_family": "orders", "resource_key": "orders"}
        authority = await client.put("/api/v1/data-center/authority-assignments",
                                     json=authority_payload)
        assert authority.status_code == 200 and authority.json()["version"] == 1
        duplicate = await client.put("/api/v1/data-center/authority-assignments",
                                     json=authority_payload)
        assert duplicate.status_code == 409
        assignments = await client.get("/api/v1/data-center/authority-assignments")
        assert len(assignments.json()) == 1
        raw_only = await client.put("/api/v1/data-center/authority-assignments",
            json={**authority_payload, "resource_key": "report_export_status",
                  "expected_version": 1})
        assert raw_only.status_code == 422
        blocked = await client.post("/api/v1/data-center/sources/lingxing-synthetic/sync", json={})
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "source.provider_disabled"
        schedule_payload = {"name": "Synthetic snapshot", "resource_key": "shops",
                            "strategy": "snapshot"}
        prefix = "/api/v1/data-center/sources/lingxing-synthetic"
        schedule = await client.post(f"{prefix}/schedules", json=schedule_payload)
        assert schedule.status_code == 201 and schedule.json()["status"] == "paused"
        changed = await client.put(f"{prefix}/schedules/{schedule.json()['id']}?version=1",
            json={**schedule_payload, "interval_seconds": 600})
        assert changed.status_code == 200 and changed.json()["version"] == 2
        stale = await client.put(f"{prefix}/schedules/{schedule.json()['id']}?version=1",
                                 json=schedule_payload)
        assert stale.status_code == 409
        listed = await client.get(f"{prefix}/schedules")
        assert len(listed.json()) == 1
        backfill_payload = {"name": "Synthetic order history", "resource_key": "orders",
            "window_start": "2026-07-01T00:00:00Z",
            "window_end": "2026-08-01T00:00:00Z", "partition_days": 7,
            "batch_size": 4, "projection_mode": "deferred"}
        backfill = await client.post(f"{prefix}/backfills", json=backfill_payload)
        assert backfill.status_code == 201
        assert backfill.json()["status"] == "paused"
        assert backfill.json()["windows_total"] == 5
        backfills = await client.get(f"{prefix}/backfills")
        assert len(backfills.json()) == 1
        coverage = await client.get(
            f"{prefix}/backfills/{backfill.json()['id']}/windows")
        assert coverage.status_code == 200 and coverage.json()["items"] == []
        stale_backfill = await client.put(
            f"{prefix}/backfills/{backfill.json()['id']}?version=2", json=backfill_payload)
        assert stale_backfill.status_code == 409
        app.state.settings = replace(app.state.settings, lingxing_enabled=True)
        validation = await client.post(
            f"{prefix}/resources/{activated.json()['key']}/validate", json={
                "resource_parameters": {"sid": "23"},
                "window_start": "2026-09-08T00:00:00Z",
                "window_end": "2026-09-09T00:00:00Z",
            })
        assert validation.status_code == 202 and validation.json()["run"]["status"] == "queued"
        with app.state.database.session() as session:
            validation_run = session.get(SyncRun, validation.json()["run"]["id"])
            validation_job = session.get(BackgroundJob, validation_run.task_id)
            assert validation_job.payload["probe"] is True
            assert validation_job.priority == 100
            assert validation_job.payload["projection_mode"] == "deferred"
            validating_resource = session.scalar(select(SourceResource).where(
                SourceResource.external_system_id == source_id,
                SourceResource.resource_key == activated.json()["key"]))
            current_resource_version = validating_resource.version
            validating_resource.version = "synthetic-stale-contract"
            session.commit()
        busy_transition = await client.put(f"{prefix}/official-resources/materialize")
        assert busy_transition.status_code == 409
        assert busy_transition.json()["error"]["code"] == (
            "source.official_resource_transition_busy"
        )
        with app.state.database.session() as session:
            validating_resource = session.scalar(select(SourceResource).where(
                SourceResource.external_system_id == source_id,
                SourceResource.resource_key == activated.json()["key"]))
            validating_resource.version = current_resource_version
            session.commit()
        batch = await client.post(f"{prefix}/imports", json={
            "client_request_key": "synthetic-import",
            "selections": [{"resource_key": "shops"}, {"resource_key": "orders",
                "window_start": "2026-08-01T00:00:00Z", "window_end": "2026-08-10T00:00:00Z"}]})
        assert batch.status_code == 202 and batch.json()["status"] == "queued"
        assert batch.json()["partitions"] == 3
        cancelled = await client.post(f"/api/v1/data-center/sync-runs/{batch.json()['id']}/cancel")
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        binding = await client.post(
            "/api/v1/data-center/sources/lingxing-synthetic/bindings", json={
                "business_unit_id": unit_id, "external_key": "shop-synthetic",
                "canonical_id": "store-synthetic",
            }
        )
        assert binding.status_code == 201
        reviewed = await client.patch(
            f"/api/v1/data-center/sources/lingxing-synthetic/bindings/{binding.json()['id']}",
            json={"status": "approved"},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "approved"
        binding_page = await client.get(
            "/api/v1/data-center/sources/lingxing-synthetic/binding-page",
            params={"status": "approved", "canonical_type": "store", "limit": 20},
        )
        assert binding_page.status_code == 200
        assert binding_page.json()["page"]["total"] == 1
        assert binding_page.json()["items"][0]["suggestion_evidence_count"] == 0
        invalid_binding_filter = await client.get(
            "/api/v1/data-center/sources/lingxing-synthetic/binding-page",
            params={"status": "unknown"},
        )
        assert invalid_binding_filter.status_code == 422
        disabled = await client.patch(
            "/api/v1/data-center/sources/lingxing-synthetic",
            json={"status": "disabled", "expected_version": created.json()["version"]}
        )
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "disabled"


@pytest.mark.anyio
async def test_operational_canonical_api_is_scoped_and_rejects_authority_mode(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        page = await client.get(
            "/api/v1/data-center/canonical/operational",
            params={"resource_key": "monthly_exchange_rates", "limit": 20},
        )
        invalid = await client.get(
            "/api/v1/data-center/canonical/operational",
            params={"authoritative_only": "true"},
        )

    assert page.status_code == 200
    assert page.json()["offset"] == 0
    assert page.json()["limit"] == 20
    assert page.json()["total"] == 0
    assert page.json()["items"] == []
    assert page.json()["authority_applied"] is False
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "canonical.date_range_invalid"


@pytest.mark.anyio
async def test_overview_is_seeded_from_migrated_database(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        response = await client.get("/api/v1/data-center/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_mode"] == "database"
    assert payload["schema_version"] == 9
    assert payload["commerce_fact_count"] == 0
    assert payload["customer_profile_count"] == 0
    assert payload["customer_touchpoint_count"] == 0
    assert payload["database"]["schema_revision"] == app.state.database.migration_head()
    assert payload["enterprise"]["code"] == "ZHIXING-DEMO"
    assert len(payload["sources"]) == 4
    assert {item["system_type"] for item in payload["sources"]} == {
        "test-erp-oms",
        "test-crm",
        "test-advertising",
        "test-customer-service",
    }
    assert len(payload["nodes"]) == 13
    assert len(payload["edges"]) == 15
    assert payload["scene"]["key"] == "enterprise-campus"
    assert len(payload["scenes"]) == 3
    warehouse_scene = next(
        item for item in payload["scenes"] if item["key"] == "warehouse-interior"
    )
    assert warehouse_scene["parent_scene_key"] == "enterprise-campus"
    assert warehouse_scene["entry_space_key"] == "warehouse"
    assert len(payload["spaces"]) == 7
    campus = next(item for item in payload["spaces"] if item["key"] == "campus")
    warehouse = next(item for item in payload["spaces"] if item["key"] == "warehouse")
    meeting_room = next(item for item in payload["spaces"] if item["key"] == "decision-room")
    assert campus["size"] == [72.0, 1.0, 48.0]
    assert warehouse["position"] == [21.0, 2.6, -8.0]
    assert warehouse["size"] == [18.0, 5.2, 16.0]
    assert meeting_room["position"] == [18.0, 2.6, 12.0]
    assert payload["scene"]["version"] == "2.0.0"
    assert payload["scene"]["camera_preset"]["warehouse"]["look_at"] == [21.0, 2.1, -8.0]
    assert len(payload["actors"]) == 3
    assert len(payload["routes"]) == 3
    assert all(len(item["path"]) >= 5 for item in payload["routes"])
    assert len(payload["hotspots"]) == 10
    assert len(payload["data_layers"]) == 6
    assert sum(item["scene_key"] == "warehouse-interior" for item in payload["hotspots"]) == 6
    meeting_hotspots = [
        item for item in payload["hotspots"] if item["scene_key"] == "decision-room-interior"
    ]
    assert {item["hotspot_type"] for item in meeting_hotspots} == {
        "evidence-wall",
        "deliberation-map",
        "decision-output",
        "action-gate",
    }
    assert payload["meeting"]["status"] == "scheduled"
    assert payload["meeting"]["next_transition_at"] is None
    assert len(payload["meeting"]["seats"]) == 12
    assert payload["metric_definition_count"] == 21
    assert payload["knowledge_document_count"] == 6
    assert payload["knowledge_version_count"] == 7
    assert payload["knowledge_chunk_count"] == 30
    assert payload["role_twin_profile_count"] == 4
    assert payload["agent_run_count"] == 0
    assert payload["customer_operation_run_count"] == 0
    assert payload["tool_definition_count"] == 5
    assert payload["tool_invocation_count"] == 0
    assert len({item["key"] for item in payload["meeting"]["seats"]}) == 12
    assigned_seats = [
        item["seat_key"] for item in payload["meeting"]["participants"] if item["seat_key"]
    ]
    assert assigned_seats == ["seat-01", "seat-05", "seat-09"]
    assert len(set(assigned_seats)) == len(assigned_seats)
    interaction_keys = {item["entity_key"] for item in payload["interactions"]}
    assert interaction_keys.issuperset(
        {
            *(item["key"] for item in payload["spaces"]),
            *(item["key"] for item in payload["actors"]),
            *(item["key"] for item in payload["hotspots"]),
            *(item["key"] for item in payload["meeting"]["seats"]),
        }
    )
    warehouse_interaction = next(
        item for item in payload["interactions"] if item["entity_key"] == "warehouse"
    )
    assert warehouse_interaction["enter_space_key"] == "warehouse"
    assert {item["action_type"] for item in warehouse_interaction["actions"]} == {
        "enter",
        "navigate",
    }
    decision_hotspot = next(
        item for item in payload["hotspots"] if item["key"] == "meeting-decision-package"
    )
    assert decision_hotspot["details"] == {"state": "等待会议生成"}
    assert payload["metrics"] == []


@pytest.mark.anyio
async def test_data_center_rejects_anonymous_permission_and_scope_bypass(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        anonymous = await client.get("/api/v1/data-center/overview")
        permission_denied = await client.get(
            "/api/v1/data-center/sync-runs",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        scope_denied = await client.get(
            "/api/v1/data-center/metric-series",
            params={"metric_keys": "gmv_today", "scope_key": "enterprise"},
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        store_allowed = await client.get(
            "/api/v1/data-center/metric-series",
            params={"metric_keys": "gmv_today", "scope_key": "store-flagship"},
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )

    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "auth.development_actor_required"
    assert permission_denied.status_code == 403
    assert permission_denied.json()["error"]["code"] == "authorization.permission_denied"
    assert scope_denied.status_code == 403
    assert scope_denied.json()["error"]["code"] == "authorization.scope_denied"
    assert store_allowed.status_code == 200
    with app.state.database.session() as session:
        decisions = list(
            session.scalars(
                select(AuthorizationDecision).where(
                    AuthorizationDecision.actor_principal_id == "principal-employee-demo"
                )
            )
        )
    assert sorted((item.permission_key, item.decision) for item in decisions) == [
        ("metric.query.execute", "allow"),
        ("metric.query.execute", "deny"),
        ("source.manage", "deny"),
    ]


@pytest.mark.anyio
async def test_data_management_apis_share_persisted_sync_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime.now(UTC)
    batch = ConnectorBatch(
        source_schema_version="vendor-2026.08",
        mapping_version="1.0.0",
        records=(
            ExternalRecord(
                record_type="shops",
                external_id="SHOP-001",
                payload={"shop_code": "SHOP-001", "shop_title": "知行旗舰店"},
                observed_at=observed_at,
            ),
        ),
        entities=(
            CanonicalEntity(
                entity_type="store",
                canonical_key="SHOP-001",
                display_name="知行旗舰店",
                status="active",
                attributes={"channel": "tmall", "manager": "周岚"},
            ),
        ),
        metrics=tuple(
            CanonicalMetric(
                key=key,
                label=label,
                value=value,
                unit=unit,
                change_rate=0.05,
                as_of=observed_at,
            )
            for key, label, value, unit in [
                ("gmv_today", "今日成交", 2386000.0, "元"),
                ("orders_today", "支付订单", 13700.0, "单"),
                ("refund_rate", "退款率", 5.41, "%"),
                ("ad_roi", "广告 ROI", 3.24, "x"),
                ("active_members", "活跃会员", 183000.0, "人"),
                ("low_stock_skus", "低库存 SKU", 42.0, "SKU"),
            ]
        ),
        warnings=(),
    )

    class StubConnector:
        def __init__(self, _base_url: str) -> None:
            pass

        async def fetch(
            self,
            _scenario: str,
            _volume_profile: str = "standard",
        ) -> ConnectorBatch:
            return batch

    monkeypatch.setattr(
        data_center_service,
        "create_connector",
        lambda _system_type, base_url: StubConnector(base_url),
    )
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        pending_quality = await client.get(
            "/api/v1/data-center/quality", params={"status": "pending"}
        )
        synchronized = await client.post(
            "/api/v1/data-center/sources/mock-commerce/sync",
            json={"scenario": "normal"},
        )
        completed = await data_center_service.synchronize(
            app.state.database,
            app.state.settings,
            "normal",
            "standard",
            source_key="jky-erp-oms",
            enterprise_id="ent_zhixing_demo",
            execute=True,
        )
        runs = await client.get("/api/v1/data-center/sync-runs", params={"status": "succeeded"})
        entities = await client.get(
            "/api/v1/data-center/entities",
            params={"entity_type": "store", "query": "旗舰"},
        )
        metrics = await client.get("/api/v1/data-center/metrics")
        quality = await client.get("/api/v1/data-center/quality", params={"status": "passed"})
        reconciliation_quality = await client.get(
            "/api/v1/data-center/quality", params={"query": "客服订单"}
        )

    assert pending_quality.status_code == 200
    assert pending_quality.json()["page"]["total"] == 6
    assert pending_quality.json()["result_counts"] == {"pending": 6}
    assert synchronized.status_code == 200
    assert synchronized.json()["run"]["volume_profile"] == "standard"
    assert synchronized.json()["run"]["status"] == "queued"
    assert runs.status_code == 200
    assert runs.json()["page"]["total"] == 1
    assert runs.json()["items"][0]["source_key"] == "jky-erp-oms"
    assert runs.json()["items"][0]["duration_seconds"] is not None
    assert entities.status_code == 200
    assert entities.json()["page"]["total"] == 1
    assert entities.json()["items"][0]["attributes"]["channel"] == "tmall"
    assert metrics.status_code == 200
    assert metrics.json()["page"]["total"] == 21
    current_metrics = {item["key"]: item["current_value"] for item in metrics.json()["items"]}
    assert current_metrics["gmv_today"] == 2386000.0
    assert quality.status_code == 200
    assert quality.json()["page"]["total"] == 5
    assert quality.json()["result_counts"] == {"passed": 5, "pending": 1}
    assert {item["sync_run_id"] for item in quality.json()["items"]} == {
        completed.id
    }
    assert reconciliation_quality.status_code == 200
    assert reconciliation_quality.json()["page"]["total"] == 1
    assert reconciliation_quality.json()["items"][0]["result_status"] == "pending"


@pytest.mark.anyio
async def test_metric_history_is_idempotent_and_queryable_by_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch = ConnectorBatch(
        source_schema_version="vendor-2026.08",
        mapping_version="1.2.0",
        records=(
            ExternalRecord(
                record_type="metrics/daily",
                external_id="enterprise:gmv:2026-08-25",
                payload={"value": 100},
                observed_at=datetime(2026, 8, 25, tzinfo=UTC),
            ),
        ),
        entities=(),
        metrics=(
            CanonicalMetric(
                "gmv_today",
                "成交金额",
                100,
                "元",
                0.01,
                datetime(2026, 8, 25, tzinfo=UTC),
                "enterprise",
            ),
            CanonicalMetric(
                "gmv_today",
                "成交金额",
                120,
                "元",
                0.2,
                datetime(2026, 8, 26, tzinfo=UTC),
                "enterprise",
            ),
            CanonicalMetric(
                "gmv_today",
                "成交金额",
                150,
                "元",
                0.25,
                datetime(2026, 8, 27, tzinfo=UTC),
                "enterprise",
            ),
            CanonicalMetric(
                "gmv_today",
                "成交金额",
                60,
                "元",
                0.1,
                datetime(2026, 8, 26, tzinfo=UTC),
                "store-flagship",
            ),
            CanonicalMetric(
                "gmv_today",
                "成交金额",
                75,
                "元",
                0.25,
                datetime(2026, 8, 27, tzinfo=UTC),
                "store-flagship",
            ),
        ),
        warnings=(),
    )

    class StubConnector:
        def __init__(self, _base_url: str) -> None:
            pass

        async def fetch(
            self,
            _scenario: str,
            _volume_profile: str = "standard",
        ) -> ConnectorBatch:
            return batch

    monkeypatch.setattr(
        data_center_service,
        "create_connector",
        lambda _system_type, base_url: StubConnector(base_url),
    )
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        first = await client.post(
            "/api/v1/data-center/sources/mock-commerce/sync",
            json={"scenario": "normal"},
        )
        second = await client.post(
            "/api/v1/data-center/sources/mock-commerce/sync",
            json={"scenario": "normal"},
        )
        await data_center_service.synchronize(
            app.state.database,
            app.state.settings,
            "normal",
            "standard",
            source_key="jky-erp-oms",
            enterprise_id="ent_zhixing_demo",
            execute=True,
        )
        enterprise = await client.get(
            "/api/v1/data-center/metric-series",
            params={"metric_keys": "gmv_today", "scope_key": "enterprise", "days": 30},
        )
        store = await client.get(
            "/api/v1/data-center/metric-series",
            params={
                "metric_keys": "gmv_today",
                "scope_key": "store-flagship",
                "days": 30,
            },
        )

    assert first.status_code == second.status_code == 200
    assert enterprise.status_code == store.status_code == 200
    enterprise_series = enterprise.json()["series"][0]
    assert [point["value"] for point in enterprise_series["points"]] == [100, 120, 150]
    assert enterprise_series["period_change_rate"] == pytest.approx(0.5)
    assert enterprise_series["minimum"] == 100
    assert enterprise_series["maximum"] == 150
    assert [point["value"] for point in store.json()["series"][0]["points"]] == [60, 75]
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(MetricSnapshot.id))) == 5


@pytest.mark.anyio
async def test_four_sources_sync_independently_and_keep_raw_identity_per_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 8, 29, tzinfo=UTC)
    shared_batch = ConnectorBatch(
        source_schema_version="sandbox-v1",
        mapping_version="1.0.0",
        records=(
            ExternalRecord(
                record_type="shared-record",
                external_id="001",
                payload={"external_code": "001"},
                observed_at=observed_at,
            ),
        ),
        entities=(
            CanonicalEntity(
                entity_type="reference",
                canonical_key="shared-001",
                display_name="跨来源统一对象",
                status="active",
                attributes={"normalized": True},
            ),
        ),
        metrics=(),
        warnings=(),
    )

    class StubConnector:
        async def fetch(
            self,
            _scenario: str,
            _volume_profile: str = "standard",
        ) -> ConnectorBatch:
            return shared_batch

    monkeypatch.setattr(
        data_center_service,
        "create_connector",
        lambda _system_type, _base_url: StubConnector(),
    )
    app = create_app(make_settings(tmp_path))
    source_keys = (
        "jky-erp-oms",
        "crm-members",
        "advertising-platforms",
        "customer-service-channels",
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        responses = [
            await client.post(
                f"/api/v1/data-center/sources/{source_key}/sync",
                json={"scenario": "normal", "volume_profile": "small"},
            )
            for source_key in source_keys
        ]
        for source_key in source_keys:
            await data_center_service.synchronize(
                app.state.database,
                app.state.settings,
                "normal",
                "small",
                source_key=source_key,
                enterprise_id="ent_zhixing_demo",
                execute=True,
            )
        repeated = await client.post(
            "/api/v1/data-center/sources/crm-members/sync",
            json={"scenario": "normal", "volume_profile": "small"},
        )
        overview = await client.get("/api/v1/data-center/overview")
        missing = await client.post(
            "/api/v1/data-center/sources/not-registered/sync",
            json={"scenario": "normal"},
        )

    assert all(response.status_code == 200 for response in responses)
    assert repeated.status_code == 200
    assert missing.status_code == 404
    source_views = {item["key"]: item for item in overview.json()["sources"]}
    assert all(source_views[key]["status"] == "connected" for key in source_keys)
    assert {source_views[key]["source_record_count"] for key in source_keys} == {1}
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(SourceRecord.id))) == 4
        run_counts = dict(
            session.execute(
                select(ExternalSystem.system_key, func.count(SourceRecord.id))
                .join(SourceRecord, SourceRecord.external_system_id == ExternalSystem.id)
                .group_by(ExternalSystem.system_key)
            ).all()
        )
    assert run_counts == {key: 1 for key in source_keys}


def test_database_bootstrap_is_repeatable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    first = create_app(settings)

    with first.state.database.session() as session:
        campus = session.scalar(select(TwinSpace).where(TwinSpace.space_key == "campus"))
        actor = session.scalar(select(TwinActor).where(TwinActor.actor_key == "twin-ceo"))
        route = session.scalar(
            select(TwinRoute).where(TwinRoute.route_key == "ceo-to-decision-room")
        )
        scene = session.scalar(select(TwinScene).where(TwinScene.scene_key == "enterprise-campus"))
        seat = session.scalar(select(TwinMeetingSeat).where(TwinMeetingSeat.seat_key == "seat-01"))
        participant = session.scalar(
            select(TwinMeetingParticipant).where(TwinMeetingParticipant.actor_key == "twin-ceo")
        )
        interaction = session.scalar(
            select(TwinInteractionProfile).where(TwinInteractionProfile.entity_key == "warehouse")
        )
        assert (
            campus is not None
            and actor is not None
            and route is not None
            and scene is not None
            and seat is not None
            and participant is not None
            and interaction is not None
        )
        campus.size = [1.0, 1.0, 1.0]
        actor.position = [0.0, 0.0, 0.0]
        route.path = [[0.0, 0.0, 0.0]]
        scene.version = "stale"
        seat.position = [0.0, 0.0, 0.0]
        participant.seat_key = None
        interaction.actions = []
        session.commit()

    second = create_app(settings)

    assert first.state.database.revision() == first.state.database.migration_head()
    assert second.state.database.revision() == second.state.database.migration_head()
    with second.state.database.session() as session:
        campus = session.scalar(select(TwinSpace).where(TwinSpace.space_key == "campus"))
        actor = session.scalar(select(TwinActor).where(TwinActor.actor_key == "twin-ceo"))
        route = session.scalar(
            select(TwinRoute).where(TwinRoute.route_key == "ceo-to-decision-room")
        )
        scene = session.scalar(select(TwinScene).where(TwinScene.scene_key == "enterprise-campus"))
        seat = session.scalar(select(TwinMeetingSeat).where(TwinMeetingSeat.seat_key == "seat-01"))
        participant = session.scalar(
            select(TwinMeetingParticipant).where(TwinMeetingParticipant.actor_key == "twin-ceo")
        )
        interaction = session.scalar(
            select(TwinInteractionProfile).where(TwinInteractionProfile.entity_key == "warehouse")
        )
        assert campus is not None and campus.size == [72.0, 1.0, 48.0]
        assert actor is not None and actor.position == [-2.0, 0.12, 12.8]
        assert route is not None and len(route.path) == 5
        assert scene is not None and scene.version == "2.0.0"
        assert seat is not None and seat.position != [0.0, 0.0, 0.0]
        assert participant is not None and participant.seat_key == "seat-01"
        assert interaction is not None and len(interaction.actions) == 2


@pytest.mark.anyio
async def test_meeting_actions_persist_scene_state(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=CEO_HEADERS
    ) as client:
        convened = await client.post(
            "/api/v1/data-center/meetings/mtg-budget-20260825/actions",
            json={"action": "convene"},
        )
        started = await client.post(
            "/api/v1/data-center/meetings/mtg-budget-20260825/actions",
            json={"action": "start"},
        )
        decided = await client.post(
            "/api/v1/data-center/meetings/mtg-budget-20260825/actions",
            json={"action": "decide"},
        )

    assert convened.status_code == 200
    assert convened.json()["meeting"]["status"] == "convening"
    assert convened.json()["meeting"]["next_transition_at"] is not None
    assert started.json()["meeting"]["status"] == "in_session"
    assert started.json()["meeting"]["next_transition_at"] is None
    assert all(item["status"] == "present" for item in started.json()["meeting"]["participants"])
    assert decided.json()["meeting"]["status"] == "decision_ready"
    decision_hotspot = next(
        item
        for item in decided.json()["overview"]["hotspots"]
        if item["key"] == "meeting-decision-package"
    )
    assert decision_hotspot["details"]["state"] == "已生成"
    assert decision_hotspot["details"]["decision"] == decided.json()["meeting"]["decision"]


@pytest.mark.anyio
async def test_meeting_auto_start_is_owned_by_api_lifespan(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=CEO_HEADERS
        ) as client:
            convened = await client.post(
                "/api/v1/data-center/meetings/mtg-budget-20260825/actions",
                json={"action": "convene"},
            )
            assert convened.json()["meeting"]["status"] == "convening"

            await asyncio.sleep(0.08)
            overview = await client.get("/api/v1/data-center/overview")

    assert overview.json()["meeting"]["status"] == "in_session"


@pytest.mark.anyio
async def test_meeting_rejects_invalid_transition(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=CEO_HEADERS
    ) as client:
        response = await client.post(
            "/api/v1/data-center/meetings/mtg-budget-20260825/actions",
            json={"action": "decide"},
        )

    assert response.status_code == 409


@pytest.mark.anyio
async def test_meeting_action_rejects_unknown_meeting_key(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=CEO_HEADERS
    ) as client:
        response = await client.post(
            "/api/v1/data-center/meetings/unknown-meeting/actions",
            json={"action": "convene"},
        )

    assert response.status_code == 404
