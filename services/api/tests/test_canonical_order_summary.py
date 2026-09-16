from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from zhixing_api.data_models import (
    Base,
    BusinessUnit,
    CanonicalSalesOrder,
    Enterprise,
    ExternalSystem,
    SourceAuthorityAssignment,
    SourceResource,
)
from zhixing_api.database import Database
from zhixing_api.ingestion.metrics import summarize_orders
from zhixing_api.ingestion.queries import canonical_page
from zhixing_api.scope_context import ScopeContext


def test_authoritative_group_summary_preserves_currency_scope_and_quality(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    database = Database.from_engine(engine)
    now = datetime(2026, 9, 9, tzinfo=UTC)
    with database.session() as session:
        for legal, unit in (("a", "a1"), ("a", "a2"), ("b", "b1")):
            if unit != "a2":
                session.add(Enterprise(id=legal, code=legal, name=legal,
                                       timezone="UTC", created_at=now))
            session.add(BusinessUnit(id=unit, enterprise_id=legal, unit_key=unit,
                name=unit, unit_type="project", status="active", created_at=now, updated_at=now))
            session.add(ExternalSystem(id=unit, enterprise_id=legal, system_key=unit,
                name=unit, system_type="lingxing", base_url="https://example.invalid"))
            session.add(SourceResource(id=unit, external_system_id=unit, resource_key="orders",
                path="/synthetic", schema_status="confirmed", enabled=True))
            session.add(SourceAuthorityAssignment(id=unit, enterprise_id=legal,
                business_unit_id=unit, external_system_id=unit, resource_key="orders",
                fact_family="orders", status="active", version=1, created_at=now, updated_at=now))
        for key, legal, unit, currency, amount, source in (
            ("1", "a", "a1", "KWD", "1.125", "a1"),
            ("2", "a", "a2", "JPY", "100", "a2"),
            ("3", "b", "b1", "KWD", "2.125", "b1"),
            ("4", "b", "b1", None, None, "b1"),
            ("duplicate", "a", "a1", "KWD", "999", "b1"),
        ):
            session.add(CanonicalSalesOrder(id=key, enterprise_id=legal, business_unit_id=unit,
                external_system_id=source, resource_key="orders", external_key=key,
                raw_manifest_id=f"raw-{key}", schema_version="1", mapping_version="1",
                observed_at=now, store_key=unit, status="Shipped", amount=amount,
                currency_code=currency, ordered_at=now, source_local_time="2026-09-09",
                business_date=now.date()))
        session.commit()
    scope = ScopeContext(group_id="g", group_name="Synthetic", enterprise_id="a",
        enterprise_name="a", allowed_enterprise_ids=("a", "b"),
        selected_enterprise_ids=("a", "b"), business_unit_ids=("a1", "a2", "b1"),
        store_ids=("a1", "a2", "b1"), scope_level="group", timezone="UTC", scope_version="v2")
    result = summarize_orders(database, scope, date(2026, 9, 9), date(2026, 9, 10))
    assert result.order_count == 4
    from zhixing_connectors.catalog import RESOURCE_CATALOG

    with monkeypatch.context() as changed:
        changed.setattr("zhixing_api.ingestion.authority.RESOURCE_CATALOG", tuple(
            replace(item, schema_status="schema_pending") if item.key == "orders" else item
            for item in RESOURCE_CATALOG), raising=False)
        assert summarize_orders(database, scope, date(2026, 9, 9),
                                date(2026, 9, 10)).order_count == 0
    assert result.currency_totals == {"KWD": Decimal("3.250"), "JPY": Decimal("100")}
    assert result.missing_amount_count == 1
    assert result.base_amount is None and "fx_unavailable" in result.quality_flags
    assert sum(row.order_count for row in result.lineage) == 4
    for row in result.lineage:
        detail = canonical_page(database, scope, "orders", authoritative_only=True,
            source_id=row.external_system_id, business_unit_id=row.business_unit_id,
            resource_key=row.resource_key, schema_version=row.schema_version,
            mapping_version=row.mapping_version, date_from=date(2026, 9, 9),
            date_to=date(2026, 9, 10))
        assert detail.total == row.order_count
        assert all(item.raw_manifest_id.startswith("raw-") for item in detail.items)
    assert result.status_counts == {"Shipped": 4}
    assert result.scope_snapshot["data_as_of"] == result.data_as_of.isoformat()
    unauthorized = replace(scope, allowed_enterprise_ids=("a",))
    restricted = summarize_orders(database, unauthorized, date(2026, 9, 9), date(2026, 9, 10))
    assert restricted.order_count == 2
    narrow = replace(scope, selected_enterprise_ids=("a",), business_unit_ids=("a1",),
                     store_ids=("a1",), scope_level="store")
    assert summarize_orders(database, narrow, date(2026, 9, 9), date(2026, 9, 10)).order_count == 1
    assert summarize_orders(database, scope, date(2026, 9, 8), date(2026, 9, 9)).order_count == 0
    with database.session() as session:
        session.get(SourceResource, "b1").schema_status = "schema_pending"
        session.commit()
    assert summarize_orders(database, scope, date(2026, 9, 9), date(2026, 9, 10)).order_count == 2
    with database.session() as session:
        session.get(ExternalSystem, "a1").status = "disabled"
        session.get(SourceAuthorityAssignment, "a2").status = "disabled"
        session.commit()
    empty = summarize_orders(database, scope, date(2026, 9, 9), date(2026, 9, 10))
    assert empty.order_count == 0 and empty.data_as_of is None
    assert empty.currency_totals == {} and "no_authoritative_orders" in empty.quality_flags
    with pytest.raises(ValueError):
        summarize_orders(database, scope, date(2026, 9, 10), date(2026, 9, 9))
    database.dispose()


def test_summary_http_contract_requires_permission_and_valid_date_range(monkeypatch):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from zhixing_api.routers import canonical

    app = FastAPI()
    app.state.database = object()
    app.include_router(canonical.router)
    actor = SimpleNamespace(permissions=frozenset())
    monkeypatch.setattr(canonical, "resolve_development_actor", lambda request: actor)
    calls = []

    def deny(actor, permission, database, **kwargs):
        from fastapi import HTTPException
        calls.append(permission)
        raise HTTPException(status_code=403)

    monkeypatch.setattr(canonical, "require_permission", deny)
    with TestClient(app) as client:
        assert client.get("/api/v1/data-center/canonical/orders/summary",
            params={"date_from": "2026-09-09", "date_to": "2026-09-10"}).status_code == 403
        assert calls == ["metric.query.execute"]
        assert client.get("/api/v1/data-center/canonical/orders/summary",
            params={"date_from": "invalid", "date_to": "2026-09-10"}).status_code == 422
