import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from test_fulfillment_mapping import synthetic_fulfillment

from zhixing_api.data_models import (
    Base,
    BusinessEntity,
    BusinessUnit,
    ExternalSystem,
    SourceBinding,
)
from zhixing_api.ingestion.persistence import _persist_row, _resolve_bindings


def _binding(
    *, binding_id: str, kind: str, external: str, canonical: str,
    now: datetime, business_unit_id: str | None = None, status: str = "pending",
) -> SourceBinding:
    return SourceBinding(
        id=binding_id, enterprise_id="legal", business_unit_id=business_unit_id,
        source_system_id="source", external_key=f"{kind}:{external}",
        canonical_type=kind, canonical_id=canonical, mapping_version="test",
        status=status, created_at=now, updated_at=now,
    )


def test_related_approved_dimension_creates_auditable_non_automatic_suggestion() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 10, tzinfo=UTC)
    with Session(engine) as session:
        session.add(BusinessUnit(id="project", enterprise_id="legal", unit_key="project",
            name="Synthetic project", unit_type="project", status="active",
            created_at=now, updated_at=now))
        source = ExternalSystem(id="source", enterprise_id="legal", business_unit_id="project",
            system_key="source", name="Synthetic", system_type="lingxing",
            base_url="https://openapi.lingxing.com", status="configured")
        session.add(source)
        for kind, canonical in (("store", "store-key"), ("product", "product-key"),
                                ("warehouse", "warehouse-key")):
            session.add(BusinessEntity(id=canonical, enterprise_id="legal", entity_type=kind,
                canonical_key=canonical, display_name=f"Synthetic {kind}",
                status="active" if kind == "store" else "unassigned",
                attributes={}, updated_at=now))
        session.add(_binding(binding_id="store", kind="store", external="11",
            canonical="store-key", now=now, business_unit_id="project", status="approved"))
        session.add(_binding(binding_id="product", kind="product", external="33",
            canonical="product-key", now=now))
        session.add(_binding(binding_id="warehouse", kind="warehouse", external="22",
            canonical="warehouse-key", now=now))
        session.flush()

        source_row = {"amazon_order_id": "A-1", "sid": 11, "order_status": "Shipped",
                      "purchase_date": "2026-09-09T19:00:00+00:00", "sku": "SKU-1",
                      "pid": 33, "quantity": 1, "currency": "USD",
                      "item_price": "10.125"}
        with pytest.raises(LookupError, match="mapping.unassigned"):
            _persist_row(session, source, "source_reports", "raw-source", source_row,
                now, {"business_unit_ids": ["project"], "store_ids": ["store-key"]},
                {"sid": 11})
        product = session.get(SourceBinding, "product")
        assert product.status == "pending" and product.business_unit_id is None
        assert product.suggested_business_unit_id == "project"
        assert product.suggestion_reason == "approved_related_dimension"
        assert product.suggestion_evidence_count == 1

        # A replay of the same Raw page is idempotent evidence.
        with pytest.raises(LookupError, match="mapping.unassigned"):
            _persist_row(session, source, "source_reports", "raw-source", source_row,
                now, {"business_unit_ids": ["project"], "store_ids": ["store-key"]},
                {"sid": 11})
        assert product.suggestion_evidence_count == 1

        with pytest.raises(LookupError, match="mapping.unassigned"):
            _persist_row(session, source, "fulfillments", "raw-fulfillment",
                {**synthetic_fulfillment(), "sid": 11, "wid": 22}, now,
                {"business_unit_ids": ["project"], "store_ids": ["store-key"]})
        warehouse = session.get(SourceBinding, "warehouse")
        assert warehouse.suggested_business_unit_id == "project"
        assert warehouse.suggestion_evidence_count == 1

        schema = json.loads((Path(__file__).resolve().parents[3]
            / "contracts/data/source-binding-suggestion.schema.json").read_text())
        for item in (product, warehouse):
            jsonschema.validate({
                "suggested_business_unit_id": item.suggested_business_unit_id,
                "suggestion_reason": item.suggestion_reason,
                "suggestion_evidence": item.suggestion_evidence,
                "suggestion_evidence_count": item.suggestion_evidence_count,
            }, schema)
        assert session.scalars(select(SourceBinding).where(
            SourceBinding.status == "approved")).all() == [session.get(SourceBinding, "store")]
    engine.dispose()


def test_conflicting_approved_dimensions_do_not_suggest_a_target() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 10, tzinfo=UTC)
    with Session(engine) as session:
        for unit in ("project-a", "project-b"):
            session.add(BusinessUnit(id=unit, enterprise_id="legal", unit_key=unit,
                name=unit, unit_type="project", status="active", created_at=now, updated_at=now))
        source = ExternalSystem(id="source", enterprise_id="legal", system_key="source",
            name="Synthetic", system_type="lingxing", base_url="https://openapi.lingxing.com",
            status="configured")
        session.add(source)
        session.add(_binding(binding_id="store", kind="store", external="11",
            canonical="store-key", now=now, business_unit_id="project-a", status="approved"))
        session.add(_binding(binding_id="warehouse", kind="warehouse", external="22",
            canonical="warehouse-key", now=now, business_unit_id="project-b", status="approved"))
        session.add(_binding(binding_id="product", kind="product", external="33",
            canonical="product-key", now=now))
        session.flush()
        with pytest.raises(LookupError, match="mapping.unassigned"):
            _resolve_bindings(session, source, (("store", "11"), ("warehouse", "22"),
                ("product", "33")), resource="synthetic", manifest="raw-conflict",
                observed_at=now)
        product = session.get(SourceBinding, "product")
        assert product.suggested_business_unit_id is None
        assert product.suggestion_reason == "conflicting_related_dimensions"
    engine.dispose()
