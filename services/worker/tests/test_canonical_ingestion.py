from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from zhixing_api.data_models import (
    AccessRole,
    AccessRolePermission,
    BusinessEntity,
    BusinessUnit,
    CanonicalFulfillment,
    CanonicalFulfillmentLine,
    CanonicalInventoryBalance,
    CanonicalSalesOrder,
    CanonicalSalesOrderLine,
    Enterprise,
    EnterpriseGroup,
    ExternalSystem,
    MappingConflict,
    PermissionDefinition,
    Principal,
    RawPageManifest,
    RoleAssignment,
    ScopeGrant,
    SourceBinding,
    SourceResource,
    StagingPageResult,
    SyncRun,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.ingestion.bindings import review_binding

from zhixing_worker.config import WorkerSettings
from zhixing_worker.main import build_lingxing_sync_handler


def test_worker_raw_to_core_isolation_late_update_and_partial_failure(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'canonical_verify.db'}")
    database.migrate()
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(EnterpriseGroup(id="g", code="g", name="Synthetic Group", status="active",
                                    timezone="UTC", created_at=now, updated_at=now))
        session.flush()
        for enterprise in ("a", "b"):
            session.add(Enterprise(id=enterprise, code=enterprise, name=enterprise, group_id="g",
                                   timezone="UTC", created_at=now))
        session.flush()
        for unit, enterprise in (("a1", "a"), ("a2", "a"), ("b1", "b")):
            session.add(BusinessUnit(id=unit, enterprise_id=enterprise, unit_key=unit,
                                     name=unit, unit_type="project", status="active",
                                     created_at=now, updated_at=now))
        session.add(PermissionDefinition(id="sync-permission", permission_key="source.manage",
                    label="Manage source", resource="source", action="manage", risk_level="low",
                    status="active"))
        for enterprise in ("a", "b"):
            session.add(Principal(id=f"actor-{enterprise}", enterprise_id=enterprise,
                principal_key="operator", principal_type="person", display_name="Synthetic",
                status="active", created_at=now, updated_at=now))
            session.add(AccessRole(id=f"role-{enterprise}", enterprise_id=enterprise,
                role_key="operator", name="Synthetic", description="Synthetic role",
                version="1", status="active", created_at=now))
        session.flush()
        for enterprise in ("a", "b"):
            session.add(UserAccount(id=f"account-{enterprise}", enterprise_id=enterprise,
                principal_id=f"actor-{enterprise}", account_key="operator", local_login_name="same",
                experience_role_key="admin", authentication_source="test", status="active",
                created_at=now, updated_at=now))
            session.add(AccessRolePermission(id=f"permit-{enterprise}",
                access_role_id=f"role-{enterprise}", permission_id="sync-permission",
                effect="allow"))
            session.add(RoleAssignment(id=f"assignment-{enterprise}", enterprise_id=enterprise,
                principal_id=f"actor-{enterprise}", access_role_id=f"role-{enterprise}",
                status="active", valid_from=now))
        session.flush()
        for enterprise in ("a", "b"):
            session.add(ScopeGrant(id=f"scope-{enterprise}", enterprise_id=enterprise,
                role_assignment_id=f"assignment-{enterprise}", scope_type="enterprise",
                scope_ids=[enterprise], effect="allow", valid_from=now))
        session.flush()
        for enterprise in ("a", "b"):
            session.add(ExternalSystem(id=f"src-{enterprise}", enterprise_id=enterprise,
                        system_key="lingxing-main", name="Synthetic ERP", system_type="erp",
                        provider_key="lingxing", base_url="https://openapi.lingxing.com",
                        status="configured"))
        session.flush()
        for enterprise in ("a", "b"):
            for key in ("shops", "orders", "products", "warehouses_local", "inventory",
                        "fulfillments"):
                session.add(SourceResource(id=f"res-{enterprise}-{key}",
                            external_system_id=f"src-{enterprise}", resource_key=key,
                            method="GET" if key == "shops" else "POST", path="synthetic",
                            schema_status="confirmed", enabled=True))
        session.commit()

    settings = WorkerSettings(database_url=database.url, worker_id="verify", poll_seconds=0,
                lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
                lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic-secret",
                lingxing_enabled=True,
                source_archive_path=str(tmp_path / "raw"))

    def ingest(enterprise, resource, rows):
        run_id = uuid4().hex
        with database.session() as session:
            session.add(SyncRun(id=run_id, enterprise_id=enterprise,
                                external_system_id=f"src-{enterprise}", status="queued",
                                scenario="synthetic", started_at=now))
            session.commit()
        def respond(request):
            if request.url.path.endswith("access-token"):
                return httpx.Response(200, json={"code": 200, "data": {
                    "access_token": "synthetic-token", "refresh_token": "synthetic-refresh",
                    "expires_in": 3600}})
            assert "access_token" in request.url.params and "sign" in request.url.params
            return httpx.Response(200, json={"code": 0, "total": len(rows), "data": rows})
        handler = build_lingxing_sync_handler(settings, database.engine,
                                              transport=httpx.MockTransport(respond))
        handler(SimpleNamespace(id=run_id, run_id=run_id, request_id="synthetic-request",
                enterprise_id=enterprise,
                actor_snapshot={"user_account_id": f"account-{enterprise}"},
                payload={
            "provider": "lingxing", "source_id": "lingxing-main", "resource_key": resource,
            "window_start": "2026-09-08T00:00:00Z", "window_end": "2026-09-10T00:00:00Z",
            "resource_parameters": {"start_date": "2026-09-08", "end_date": "2026-09-10"}
                if resource == "fulfillments" else {},
            "scope_snapshot": {"enterprise_id": enterprise},
        }), SimpleNamespace(ensure_active=lambda: None))
        return run_id

    try:
        for enterprise in ("a", "b"):
            ingest(enterprise, "shops", [{"sid": 91, "name": "Synthetic Store", "status": 1}])
        with database.session() as session:
            entities = list(session.scalars(select(BusinessEntity)))
            assert len(entities) == 2 and all(row.status == "unassigned" for row in entities)
            assert entities[0].id != entities[1].id
        order = {"sid": 91, "amazon_order_id": "SYN-ORDER", "order_status": "Shipped",
                 "order_total_amount": "123.456", "order_total_currency_code": "KWD",
                 "purchase_date_local": "2026-09-08 23:30:00",
                 "purchase_date_local_utc": "2026-09-09 06:30:00",
                 "last_update_date_utc": "2026-09-09 07:00:00",
                 "item_list": [{"seller_sku": "SYN-SKU", "quantity_ordered": 2}]}
        pending_run = ingest("a", "orders", [order])
        with database.session() as session:
            assert session.scalar(select(func.count()).select_from(CanonicalSalesOrder)) == 0
            assert session.get(SyncRun, pending_run).status == "partial_failed"
            binding = session.scalar(select(SourceBinding).where(
                SourceBinding.enterprise_id == "a"
            ))
            binding_id = binding.id
        review_binding(database, enterprise_id="a", source_key="lingxing-main",
                       binding_id=binding_id, principal_id="actor-a", status="approved",
                       business_unit_id="a1", store_timezone="America/Los_Angeles")
        good_run = ingest("a", "orders", [order])
        ingest("b", "orders", [order])
        ingest("a", "orders", [{**order, "order_total_amount": "9.99",
                                  "last_update_date_utc": "2026-09-08 07:00:00"}])
        ingest("a", "orders", [{**order, "order_total_amount": "NaN"}])
        with database.session() as session:
            facts = list(session.scalars(select(CanonicalSalesOrder)))
            assert len(facts) == 1 and facts[0].enterprise_id == "a"
            assert facts[0].amount == Decimal("123.456") and facts[0].base_amount is None
            assert facts[0].business_unit_id == "a1"
            assert session.get(RawPageManifest, facts[0].raw_manifest_id)
            assert session.scalar(select(func.count()).select_from(CanonicalSalesOrderLine)) == 1
            assert session.get(SyncRun, good_run).records_written == 1
            assert session.scalar(select(func.sum(StagingPageResult.stale))) == 1
            assert session.scalar(select(func.count()).select_from(MappingConflict)) >= 3
        ingest("a", "products", [{"id": 12, "sku": "SYN-SKU", "product_name": "Synthetic product",
                                    "open_status": 1, "update_time": 1788912000}])
        ingest("a", "warehouses_local", [{"wid": 71, "name": "Synthetic warehouse", "type": 1,
                                           "is_delete": 0}])
        with database.session() as session:
            waiting = list(session.scalars(select(SourceBinding).where(
                SourceBinding.enterprise_id == "a", SourceBinding.status == "pending")))
        for binding in waiting:
            review_binding(database, enterprise_id="a", source_key="lingxing-main",
                           binding_id=binding.id, principal_id="actor-a", status="approved",
                           business_unit_id="a1")
        ingest("a", "inventory", [{"wid": 71, "product_id": 12, "sku": "SYN-SKU",
            "seller_id": "91", "fnsku": "", "product_total": 12, "product_valid_num": 8,
            "product_bad_num": 1, "product_qc_num": 1, "product_lock_num": 2,
            "product_onway": 4}])
        shipment = {"wo_id": 81, "wo_number": "SYNTHETIC-SHIPMENT", "sid": 91, "wid": 71,
            "status": 3, "logistics_status": 5, "order_number": "SYNTHETIC-SYSTEM-ORDER",
            "platform_order_no": ["SYN-ORDER"], "create_at": "2026-09-09 10:00:00",
            "update_at": "2026-09-09 11:00:00", "delivered_at": "2026-09-09 10:30:00",
            "logistics_freight": "1.125", "logistics_freight_currency_code": "KWD",
            "product_info": [{"wod_id": 82, "product_id": 12, "sku": "SYN-SKU",
                              "count": 2, "bundle_type": 0}]}
        shipment_run = ingest("a", "fulfillments", [shipment])
        ingest("a", "fulfillments", [{**shipment, "product_info": [{}]}])
        ingest("a", "fulfillments", [{**shipment, "status": 2,
                                      "update_at": "2026-09-08 11:00:00"}])
        with database.session() as session:
            fulfillment = session.scalar(select(CanonicalFulfillment))
            assert fulfillment.status == "dispatched" and fulfillment.business_unit_id == "a1"
            assert fulfillment.freight_amount == Decimal("1.125")
            assert fulfillment.source_timezone is None and fulfillment.dispatched_at is None
            assert session.get(RawPageManifest, fulfillment.raw_manifest_id) is not None
            assert session.scalar(select(CanonicalFulfillmentLine.quantity)) == 2
            assert session.get(SyncRun, shipment_run).records_written == 1
            stock = session.scalar(select(CanonicalInventoryBalance))
            assert stock is not None and stock.available == 8 and stock.business_unit_id == "a1"
            order_row = session.scalar(select(CanonicalSalesOrder))
            assert order_row.store_timezone == "America/Los_Angeles"
            session.get(SourceResource, "res-a-orders").schema_status = "schema_pending"
            session.commit()
        downgraded_run = ingest("a", "orders", [{**order, "order_total_amount": "999.999",
            "last_update_date_utc": "2026-09-10 07:00:00"}])
        with database.session() as session:
            assert session.scalar(select(CanonicalSalesOrder)).amount == Decimal("123.456")
            assert session.get(SyncRun, downgraded_run).records_written == 0
    finally:
        database.dispose()
