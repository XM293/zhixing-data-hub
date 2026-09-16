from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    BusinessUnit,
    Enterprise,
    ExternalSystem,
    RawPageManifest,
    SourceDependencyTuple,
    SourceDependencyValue,
    SourceResource,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.ingestion.dependencies import persist_dependency_values
from zhixing_api.ingestion.parameter_fanout import plan_parameter_fanout
from zhixing_api.main import create_app


def test_dependency_values_are_scoped_deduplicated_and_keep_raw_lineage(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'dependencies-verify.db'}")
    database.migrate()
    now = datetime(2026, 9, 11, tzinfo=UTC)
    with database.session() as session:
        session.add(Enterprise(id="legal", code="LEGAL", name="Synthetic", timezone="UTC",
                               created_at=now))
        session.flush()
        session.add(BusinessUnit(id="project", enterprise_id="legal", unit_key="project",
            name="Synthetic project", unit_type="project", status="active",
            created_at=now, updated_at=now))
        session.add(ExternalSystem(id="source", enterprise_id="legal",
            business_unit_id="project", system_key="erp", name="Synthetic ERP",
            system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="resource", external_system_id="source",
            resource_key="products", method="POST", path="/readonly", enabled=True,
            schema_status="confirmed", validation_status="validated", version="synthetic"))
        session.add(SourceResource(id="multiplatform-resource", external_system_id="source",
            resource_key="official_2dbe32f66db9cd5b", method="POST", path="/readonly",
            enabled=True, schema_status="confirmed", validation_status="validated",
            version="synthetic"))
        session.add(SyncRun(id="run", enterprise_id="legal", external_system_id="source",
            status="running", scenario="normal", started_at=now))
        session.flush()
        session.add(SyncResourceRun(id="resource-run", sync_run_id="run",
            source_resource_id="resource", status="running"))
        session.flush()
        for ordinal in (1, 2):
            session.add(RawPageManifest(id=f"raw-{ordinal}",
                sync_resource_run_id="resource-run", storage_key=f"raw-{ordinal}.json.gz",
                content_hash=str(ordinal) * 64, schema_status="confirmed", fetched_at=now))
        session.commit()

    payload = {"code": 0, "data": [{
        "sid": 23,
        "msku": "MSKU-SYNTHETIC",
        "asin": "ASIN-SYNTHETIC",
        "parentAsin": "PARENT-ASIN-SYNTHETIC",
        "spu": "SPU-SYNTHETIC",
        "currencyCode": "USD",
        "financialEventGroupId": "FIN-GROUP-SYNTHETIC",
        "seller_id": "SELLER-SYNTHETIC",
        "inboundPlanId": "PLAN-SYNTHETIC",
        "shipmentId": "SHIPMENT-SYNTHETIC",
    }]}
    with database.engine.begin() as connection:
        first = persist_dependency_values(connection, enterprise_id="legal",
            external_system_id="source", source_resource_id="resource",
            resource_key="products", manifest_id="raw-1", payload=payload,
            request_parameters={}, observed_at=now)
        second = persist_dependency_values(connection, enterprise_id="legal",
            external_system_id="source", source_resource_id="resource",
            resource_key="products", manifest_id="raw-2", payload=payload,
            request_parameters={}, observed_at=now)
    assert first.discovered == 9 and first.created == 9
    assert first.tuples_discovered == 1 and first.tuples_created == 1
    assert second.discovered == 9 and second.created == 0
    assert second.tuples_discovered == 1 and second.tuples_created == 0
    with database.session() as session:
        rows = list(session.scalars(select(SourceDependencyValue).order_by(
            SourceDependencyValue.value_type)))
        assert [(row.value_type, row.external_value) for row in rows] == [
            ("asin", "ASIN-SYNTHETIC"),
            ("currencyCode", "USD"),
            ("financialEventGroupId", "FIN-GROUP-SYNTHETIC"),
            ("inboundPlanId", "PLAN-SYNTHETIC"),
            ("msku", "MSKU-SYNTHETIC"),
            ("parentAsin", "PARENT-ASIN-SYNTHETIC"),
            ("seller_id", "SELLER-SYNTHETIC"),
            ("shipmentId", "SHIPMENT-SYNTHETIC"),
            ("spu", "SPU-SYNTHETIC"),
        ]
        assert all(row.scope_kind == "store" and row.scope_external_key == "store:23"
                   for row in rows)
        assert all(row.business_unit_id == "project" and row.first_manifest_id == "raw-1"
                   and row.last_manifest_id == "raw-2" and row.occurrence_count == 2
                   for row in rows)
        dependency_tuple = session.scalar(select(SourceDependencyTuple))
        assert dependency_tuple.tuple_type == "inboundPlanId+shipmentId"
        assert dependency_tuple.tuple_values == {
            "inboundPlanId": "PLAN-SYNTHETIC",
            "shipmentId": "SHIPMENT-SYNTHETIC",
        }
        assert dependency_tuple.scope_external_key == "store:23"
        assert dependency_tuple.first_manifest_id == "raw-1"
        assert dependency_tuple.last_manifest_id == "raw-2"
        assert dependency_tuple.occurrence_count == 2
        sku_page = plan_parameter_fanout(session,
            external_system_id="source", resource_key="official_29c2ecea89316017",
            base_parameters={"storeId": "23"}, as_of=now, offset=0, limit=64)
        assert sku_page.total == 1 and sku_page.waiting_code is None
        assert sku_page.items == [{
            "sellerSku": "MSKU-SYNTHETIC",
            "sortField": "startTime",
            "sortType": "asc",
            "storeId": "23",
        }]
        tuple_page = plan_parameter_fanout(session,
            external_system_id="source", resource_key="official_216a0d9a9c31f09c",
            base_parameters={"sid": "23"}, as_of=now, offset=0, limit=64)
        assert tuple_page.total == 1 and tuple_page.items == [{
            "inboundPlanId": "PLAN-SYNTHETIC",
            "shipmentId": "SHIPMENT-SYNTHETIC",
            "sid": "23",
        }]
        export_page = plan_parameter_fanout(
            session, external_system_id="source", resource_key="official_ae7c34d7d1faf90a",
            base_parameters={"seller_id": "23"}, as_of=now, offset=0, limit=64)
        assert export_page.total == 1 and export_page.items == [{
            "financial_event_group_id": "FIN-GROUP-SYNTHETIC",
            "seller_id": "23",
        }]
        calendar_page = plan_parameter_fanout(session,
            external_system_id="source", resource_key="official_96b436a7b7ce62d2",
            base_parameters={"sids": "23"}, as_of=now, offset=0, limit=64)
        assert calendar_page.items == [{"site_date": "2026-09-11", "sids": "23"}]
        first_enum_page = plan_parameter_fanout(session,
            external_system_id="source", resource_key="official_8e9e5f51f4aa10e1",
            base_parameters={"sids": "23"}, as_of=now, offset=0, limit=64)
        second_enum_page = plan_parameter_fanout(session,
            external_system_id="source", resource_key="official_8e9e5f51f4aa10e1",
            base_parameters={"sids": "23"}, as_of=now, offset=64, limit=64)
        assert first_enum_page.total == 72 and len(first_enum_page.items) == 64
        assert first_enum_page.next_offset == 64
        assert second_enum_page.total == 72 and len(second_enum_page.items) == 8
        assert second_enum_page.next_offset is None
        manual_page = plan_parameter_fanout(session,
            external_system_id="source", resource_key="official_044ffc8e4003fc69",
            base_parameters={"sids": "23"}, as_of=now, offset=0, limit=64)
        assert manual_page.items == []
        assert manual_page.waiting_code == "source.parameters_manual_required"
    with database.engine.begin() as connection:
        scoped = persist_dependency_values(connection, enterprise_id="legal",
            external_system_id="source", source_resource_id="multiplatform-resource",
            resource_key="official_2dbe32f66db9cd5b", manifest_id="raw-2",
            payload={"data": [{"storeId": 34, "msku": "MULTI-MSKU-SYNTHETIC"}]},
            request_parameters={"sids": [34]}, observed_at=now)
    assert scoped.created == 1
    with database.session() as session:
        multi = session.scalar(select(SourceDependencyValue).where(
            SourceDependencyValue.external_value == "MULTI-MSKU-SYNTHETIC"))
        assert multi is not None
        assert multi.scope_external_key == "store:multiplatform:34"
        assert multi.extractor_version == "4"
    database.dispose()


def test_dependency_extraction_rejects_container_boolean_and_ambiguous_store_scope(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'dependencies-edge-verify.db'}")
    database.migrate()
    now = datetime(2026, 9, 11, tzinfo=UTC)
    with database.session() as session:
        session.add(Enterprise(id="legal", code="LEGAL", name="Synthetic", timezone="UTC",
                               created_at=now))
        session.add(ExternalSystem(id="source", enterprise_id="legal", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceResource(id="resource", external_system_id="source",
            resource_key="products", method="POST", path="/readonly", enabled=True,
            schema_status="confirmed", validation_status="validated", version="synthetic"))
        session.add(SyncRun(id="run", enterprise_id="legal", external_system_id="source",
            status="running", scenario="normal", started_at=now))
        session.flush()
        session.add(SyncResourceRun(id="resource-run", sync_run_id="run",
            source_resource_id="resource", status="running"))
        session.flush()
        session.add(RawPageManifest(id="raw", sync_resource_run_id="resource-run",
            storage_key="raw.json.gz", content_hash="a" * 64,
            schema_status="confirmed", fetched_at=now))
        session.commit()

    payload = {"data": [{"msku": ["container-is-not-an-id"], "asin": True},
                        {"shipmentId": "SHIP-1"}]}
    with database.engine.begin() as connection:
        result = persist_dependency_values(connection, enterprise_id="legal",
            external_system_id="source", source_resource_id="resource",
            resource_key="products", manifest_id="raw", payload=payload,
            request_parameters={"filters": {"sid": [1, 2]}}, observed_at=now)
    assert result.discovered == 1
    with database.session() as session:
        row = session.scalar(select(SourceDependencyValue))
        assert row.value_type == "shipmentId"
        assert row.scope_kind == "source" and row.scope_external_key == ""
    database.dispose()


@pytest.mark.anyio
async def test_dependency_values_api_is_enterprise_scoped_and_filterable(tmp_path):
    settings = Settings(
        environment="test", timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'dependency-api-test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )
    app = create_app(settings)
    now = datetime(2026, 9, 11, tzinfo=UTC)
    with app.state.database.session() as session:
        enterprise = session.scalar(select(Enterprise))
        source = ExternalSystem(id="dependency-source", enterprise_id=enterprise.id,
            system_key="dependency-source", name="Synthetic ERP", system_type="lingxing",
            provider_key="lingxing", base_url="https://openapi.lingxing.com",
            status="configured")
        session.add(source)
        session.add(SourceResource(id="dependency-resource", external_system_id=source.id,
            resource_key="products", method="POST", path="/readonly", enabled=True,
            schema_status="confirmed", validation_status="validated", version="synthetic"))
        session.add(SyncRun(id="dependency-run", enterprise_id=enterprise.id,
            external_system_id=source.id, status="succeeded", scenario="normal",
            started_at=now, finished_at=now))
        session.flush()
        session.add(SyncResourceRun(id="dependency-resource-run", sync_run_id="dependency-run",
            source_resource_id="dependency-resource", status="succeeded"))
        session.flush()
        session.add(RawPageManifest(id="dependency-raw",
            sync_resource_run_id="dependency-resource-run", storage_key="raw.json.gz",
            content_hash="c" * 64, schema_status="confirmed", fetched_at=now))
        session.flush()
        session.add(SourceDependencyValue(id="dependency-value", enterprise_id=enterprise.id,
            external_system_id=source.id, source_resource_id="dependency-resource",
            first_manifest_id="dependency-raw", last_manifest_id="dependency-raw",
            value_type="msku", external_value="MSKU-SYNTHETIC", value_hash="d" * 64,
            scope_kind="store", scope_external_key="store:23", status="active",
            first_seen_at=now, last_seen_at=now, occurrence_count=1, extractor_version="1"))
        session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-Zhixing-Demo-Actor": "admin"}) as client:
        response = await client.get(
            "/api/v1/data-center/sources/dependency-source/dependency-values",
            params={"value_type": "msku", "scope_kind": "store", "status": "active"})
        empty = await client.get(
            "/api/v1/data-center/sources/dependency-source/dependency-values",
            params={"resource_key": "orders"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["external_value"] == "MSKU-SYNTHETIC"
    assert empty.status_code == 200 and empty.json()["total"] == 0
    app.state.database.dispose()
