from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import create_engine

from zhixing_api.data_models import Base, CanonicalSalesOrder
from zhixing_api.database import Database
from zhixing_api.ingestion.queries import canonical_page
from zhixing_api.scope_context import ScopeContext


def test_canonical_query_filters_legal_project_store_and_does_not_sum_mixed_currencies():
    # The relational migration is covered separately. This fixture isolates query semantics.
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    database = Database.from_engine(engine)
    now = datetime.now(UTC)
    with database.session() as session:
        for key, enterprise, unit, store, currency in (
            ("1", "a", "a1", "sa", "KWD"), ("2", "a", "a2", "sb", "USD"),
            ("3", "b", "b1", "sc", "CNY"),
        ):
            session.add(CanonicalSalesOrder(id=key, enterprise_id=enterprise,
                        business_unit_id=unit, external_system_id="source", resource_key="orders",
                        external_key=key, raw_manifest_id=f"raw-{key}", schema_version="1",
                        mapping_version="1", observed_at=now, source_updated_at=now,
                        store_key=store, status="Shipped", amount="123.456", currency_code=currency,
                        ordered_at=now, source_local_time="2026-09-09 12:00:00",
                        business_date=now.date()))
        session.commit()
    context = ScopeContext(group_id="g", group_name="Synthetic", enterprise_id="a",
                enterprise_name="a", allowed_enterprise_ids=("a",), selected_enterprise_ids=("a",),
                business_unit_ids=("a1", "a2"), store_ids=("sa", "sb"), timezone="UTC",
                scope_version="v2")
    page = canonical_page(database, context, "orders", offset=0, limit=20)
    assert {row.id for row in page.items} == {"1", "2"} and page.total == 2
    assert page.currency_totals == {}  # Raw order totals are not an authorized financial metric.
    narrow = replace(context, business_unit_ids=("a1",), store_ids=("sa",),
                     scope_level="business_unit")
    assert [row.id for row in canonical_page(database, narrow, "orders").items] == ["1"]
    empty = replace(narrow, store_ids=())
    assert canonical_page(database, empty, "orders").total == 0
    database.dispose()
