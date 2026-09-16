from decimal import Decimal

import pytest

from zhixing_api.ingestion.after_sales import map_after_sales


def example():
    return {"id": 1, "sid": 5, "amazon_order_id": "SYNTHETIC-ORDER", "item_list": [
        {"item_identifier": "synthetic-refund", "after_type": "退款", "after_quantity": 1,
         "msku": "SYNTHETIC-SKU", "after_time": "2026-09-01 12:00:00",
         "data_update_time": "2026-09-01 13:00:00", "refund_amount": "-$28.0200",
         "after_reason": "Synthetic reason"},
        {"item_identifier": "synthetic-return", "after_type": "退货", "after_quantity": 2,
         "msku": "SYNTHETIC-SKU", "after_time": "2026-09-02 12:00:00",
         "data_update_time": "2026-09-02 13:00:00", "refund_amount": "",
         "return_status": "Approved"}]}


def test_after_sales_uses_child_identity_and_never_infers_currency_or_timezone():
    rows = map_after_sales(example())
    assert len(rows) == 2 and rows[0].external_key != rows[1].external_key
    assert rows[0].source_item_key == "synthetic-refund"
    assert rows[0].amount == Decimal("-28.0200") and rows[0].currency_code is None
    assert rows[0].occurred_at is None and rows[0].source_updated_at is None
    assert set(rows[0].quality_flags) == {"currency_pending", "timezone_pending"}
    assert rows[1].after_type == "return" and rows[1].quantity == 2
    localized = map_after_sales(example(), timezone="Asia/Shanghai")
    assert localized[0].occurred_at.isoformat() == "2026-09-01T04:00:00+00:00"
    assert localized[0].quality_flags == ["currency_pending"]
    data = example()
    data["item_list"][1]["item_identifier"] = "synthetic-refund"
    with pytest.raises(ValueError, match="duplicate"):
        map_after_sales(data)
    data = example()
    del data["item_list"][0]["item_identifier"]
    data["item_list"][0]["md5"] = "deprecated"
    with pytest.raises(ValueError):
        map_after_sales(data)


def test_ambiguous_local_time_and_unconfirmed_number_format_stay_pending():
    data = example()
    data["item_list"][0].update(after_time="2026-11-01 01:30:00",
        data_update_time="2026-11-01 01:35:00", refund_amount="-$1,234.50")
    item = map_after_sales(data, timezone="America/New_York")[0]
    assert item.occurred_at is None and item.amount is None
    assert "timezone_pending" in item.quality_flags
    assert "amount_format_pending" in item.quality_flags


def test_after_sale_persistence_counts_children_and_preserves_valid_facts():
    from datetime import UTC, datetime

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from zhixing_api.data_models import (
        Base,
        BusinessEntity,
        BusinessUnit,
        CanonicalAfterSale,
        ExternalSystem,
        SourceBinding,
    )
    from zhixing_api.database import Database
    from zhixing_api.errors import ApiProblem
    from zhixing_api.ingestion.bindings import review_binding
    from zhixing_api.ingestion.persistence import persist_canonical_page

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(ExternalSystem(id="source", enterprise_id="legal", name="Synthetic",
            provider_key="lingxing", system_type="erp", status="active", system_key="synthetic",
            base_url="https://example.invalid"))
        session.add(BusinessUnit(id="project", enterprise_id="legal", name="Synthetic",
            unit_key="synthetic", unit_type="project", status="active",
            created_at=now, updated_at=now))
        session.add(BusinessUnit(id="project-other", enterprise_id="legal", name="Synthetic Other",
            unit_key="other", unit_type="project", status="active", created_at=now, updated_at=now))
        session.add(BusinessEntity(id="store", enterprise_id="legal", canonical_key="store",
            entity_type="store", display_name="Synthetic", status="active", attributes={},
            updated_at=now))
        session.add(SourceBinding(id="binding", enterprise_id="legal", business_unit_id="project",
            source_system_id="source", external_key="store:5", canonical_type="store",
            canonical_id="store", mapping_version="1", status="approved",
            created_at=now, updated_at=now))
        session.commit()

    def persist(row, manifest):
        with engine.begin() as connection:
            return persist_canonical_page(connection, enterprise_id="legal", source_id="source",
                resource_key="after_sales", manifest_id=manifest, payload={"data": [row]},
                observed_at=datetime.now(UTC), scope_snapshot={"business_unit_ids": ["project"]})

    assert persist(example(), "first").accepted == 2
    older = example()
    older["item_list"][0].update(data_update_time="2026-08-01 13:00:00", after_quantity=9)
    assert persist(older, "older").stale == 1
    invalid = example()
    invalid["item_list"][0]["after_quantity"] = 7
    invalid["item_list"][1]["after_type"] = "unknown"
    assert persist(invalid, "invalid").rejected == 1
    with Session(engine) as session:
        rows = session.scalars(select(CanonicalAfterSale)).all()
        assert len(rows) == 2
        refund = next(row for row in rows if row.after_type == "refund")
        assert refund.quantity == 1 and refund.raw_manifest_id == "first"
        assert refund.currency_code is None and "currency_pending" in refund.quality_flags
    database = Database.from_engine(engine)
    review_binding(database, enterprise_id="legal", source_key="synthetic", binding_id="binding",
                   principal_id="synthetic", status="rejected")
    with pytest.raises(ApiProblem) as move:
        review_binding(database, enterprise_id="legal", source_key="synthetic",
            binding_id="binding",
            principal_id="synthetic", status="approved", business_unit_id="project-other")
    assert move.value.code == "source.binding_has_facts"
    engine.dispose()
