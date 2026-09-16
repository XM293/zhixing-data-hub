from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from test_fulfillment_mapping import synthetic_fulfillment

from zhixing_api.data_models import (
    Base,
    BusinessEntity,
    BusinessUnit,
    CanonicalFulfillment,
    CanonicalFulfillmentLine,
    ExternalSystem,
    SourceAuthorityAssignment,
    SourceBinding,
    SourceResource,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.bindings import review_binding
from zhixing_api.ingestion.persistence import _persist_row
from zhixing_api.ingestion.queries import canonical_page
from zhixing_api.scope_context import ScopeContext


def test_fulfillment_replay_preserves_valid_lines_and_requires_both_dimensions():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    database = Database.from_engine(engine)
    now = datetime.now(UTC)
    with database.session() as session:
        for unit, enterprise in (("a1", "a"), ("a2", "a"), ("b1", "b")):
            session.add(BusinessUnit(id=unit, enterprise_id=enterprise, unit_key=unit,
                name=unit, unit_type="project", status="active", created_at=now, updated_at=now))
        source = ExternalSystem(id="source", enterprise_id="a", system_key="synthetic",
            name="Synthetic", system_type="erp", provider_key="lingxing", status="configured",
            base_url="https://openapi.lingxing.com")
        session.add(source)
        for kind, external, canonical in (("store", "91", "sa"), ("warehouse", "92", "wa")):
            session.add(BusinessEntity(id=canonical, enterprise_id="a", entity_type=kind,
                canonical_key=canonical, display_name=f"Synthetic {kind}", status="active",
                attributes={}, updated_at=now))
            session.add(SourceBinding(id=kind, enterprise_id="a", business_unit_id="a1",
                source_system_id="source", external_key=f"{kind}:{external}",
                canonical_type=kind, canonical_id=canonical, status="approved",
                mapping_version="1", created_at=now, updated_at=now))
        session.commit()
        row = synthetic_fulfillment()
        scope = {"business_unit_ids": ["a1"], "store_ids": ["sa"], "warehouse_ids": ["wa"]}

        def persist(value, observed=now):
            return _persist_row(session, source, "fulfillments", "raw-synthetic", value,
                                observed, scope)

        assert persist(row) == "accepted"
        session.commit()
        original_id = session.scalar(select(CanonicalFulfillmentLine.id))
        assert persist(row) == "accepted"
        session.commit()
        assert session.scalar(select(CanonicalFulfillmentLine.id)) == original_id
        assert persist({**row, "status": 2, "update_at": "2026-09-08 11:00:00"}) == "stale"
        assert persist({**row, "status": 2}, now - timedelta(seconds=1)) == "stale"
        with pytest.raises(ValueError):
            persist({**row, "status": 2, "product_info": [*row["product_info"], {}]})
        session.commit()
        assert session.scalar(select(CanonicalFulfillment.status)) == "dispatched"
        assert session.scalar(select(CanonicalFulfillmentLine.quantity)) == 2
        warehouse = session.get(SourceBinding, "warehouse")
        warehouse.business_unit_id = "a2"
        session.flush()
        with pytest.raises(LookupError):
            persist(row)
        warehouse.business_unit_id = "a1"
        session.commit()

    for binding_id in ("store", "warehouse"):
        with pytest.raises(ApiProblem) as error:
            review_binding(database, enterprise_id="a", source_key="synthetic",
                binding_id=binding_id, principal_id="synthetic", status="approved",
                business_unit_id="a2")
        assert error.value.code == "source.binding_has_facts"

    context = ScopeContext(group_id="g", group_name="Synthetic", enterprise_id="a",
        enterprise_name="a", allowed_enterprise_ids=("a",), selected_enterprise_ids=("a", "b"),
        business_unit_ids=("a1", "a2", "b1"), store_ids=("sa",), warehouse_ids=("wa",),
        timezone="UTC", scope_version="v2")
    page = canonical_page(database, context, "fulfillments")
    assert page.total == 1 and len(page.items[0].lines) == 1
    assert page.items[0].source_timezone is None and page.items[0].base_freight_amount is None
    assert canonical_page(database, replace(context, warehouse_ids=()), "fulfillments").total == 0
    assert canonical_page(database, replace(context, store_ids=()), "fulfillments").total == 0
    assert canonical_page(database, replace(context, business_unit_ids=("a2",)),
                          "fulfillments").total == 0
    assert canonical_page(database, context, "fulfillments", authoritative_only=True).total == 0
    with database.session() as session:
        session.add(SourceResource(id="fulfillment-resource", external_system_id="source",
            resource_key="fulfillments", path="synthetic", enabled=True, schema_status="confirmed"))
        session.add(SourceAuthorityAssignment(id="fulfillment-authority", enterprise_id="a",
            business_unit_id="a1", external_system_id="source", resource_key="fulfillments",
            fact_family="fulfillments", status="active", version=1, created_at=now, updated_at=now))
        session.commit()
    assert canonical_page(database, context, "fulfillments", authoritative_only=True).total == 1
    with database.session() as session:
        session.get(SourceResource, "fulfillment-resource").schema_status = "schema_pending"
        session.commit()
    assert canonical_page(database, context, "fulfillments", authoritative_only=True).total == 0
    database.dispose()
