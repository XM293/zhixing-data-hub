from datetime import UTC, datetime

import pytest

from zhixing_api.ingestion.mapping import map_listing


def listing(**changes):
    return {"sid": 91, "seller_sku": "SYN-MSKU", "local_sku": "SYN-SKU",
            "item_name": "Synthetic listing", "asin": "SYN-ASIN", "fnsku": "",
            "status": 1, "is_delete": 0, "listing_update_date": "2026-09-10 01:02:03",
            **changes}


def test_listing_key_is_store_and_sku_not_optional_amazon_id():
    row = map_listing(listing(listing_id=""))
    assert row.entity_type == "listing" and row.status == "active"
    assert row.source_updated_at == datetime(2026, 9, 10, 1, 2, 3, tzinfo=UTC)
    assert row.attributes["local_sku"] == "SYN-SKU"
    assert row.external_key == map_listing(listing(listing_id="changed")).external_key
    assert row.external_key != map_listing(listing(sid=92)).external_key
    assert map_listing(listing(is_delete=1)).status == "deleted"
    assert map_listing(listing(status=0)).status == "inactive"
    assert map_listing(listing(is_delete=1, item_name="")).name == "SYN-MSKU"


@pytest.mark.parametrize("changes", [{"sid":0},{"seller_sku":""},{"status":9},
                                    {"is_delete":2},{"local_sku":{} },{"item_name":{} }])
def test_listing_invalid_identity_or_state_is_rejected(changes):
    with pytest.raises(ValueError):
        map_listing(listing(**changes))


def test_listing_projection_requires_store_scope_and_preserves_newer_entity(tmp_path):
    from sqlalchemy import select

    from zhixing_api.data_models import (
        BusinessEntity,
        BusinessUnit,
        CanonicalEntityOrigin,
        Enterprise,
        ExternalSystem,
        RawPageManifest,
        SourceBinding,
        SourceResource,
        SyncResourceRun,
        SyncRun,
    )
    from zhixing_api.database import Database
    from zhixing_api.errors import ApiProblem
    from zhixing_api.ingestion.bindings import review_binding
    from zhixing_api.ingestion.persistence import persist_canonical_page

    db = Database(f"sqlite:///{tmp_path / 'listing_verify.db'}")
    db.migrate()
    now = datetime(2026, 9, 10, tzinfo=UTC)
    with db.session() as session:
        session.add(Enterprise(id="legal", code="legal", name="Synthetic", timezone="UTC",
                               created_at=now))
        session.flush()
        session.add(BusinessUnit(id="unit", enterprise_id="legal", unit_key="unit", name="Unit",
            unit_type="project", status="active", created_at=now, updated_at=now))
        session.add(BusinessUnit(id="other-unit", enterprise_id="legal", unit_key="other-unit",
            name="Other", unit_type="project", status="active", created_at=now, updated_at=now))
        session.add(BusinessEntity(id="store", enterprise_id="legal", entity_type="store",
            canonical_key="store-key", display_name="Synthetic store", status="active",
            attributes={"source_status":"active"}, updated_at=now))
        session.add(ExternalSystem(id="src", enterprise_id="legal", system_key="erp",
            name="Synthetic ERP", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.flush()
        session.add(SourceBinding(id="binding", enterprise_id="legal", business_unit_id="unit",
            source_system_id="src", external_key="store:91", canonical_type="store",
            canonical_id="store-key", mapping_version="synthetic", status="approved",
            created_at=now, updated_at=now))
        session.add(SourceResource(id="resource", external_system_id="src", resource_key="listings",
            method="POST", path="/synthetic", enabled=True, schema_status="confirmed"))
        session.add(SyncRun(id="run", enterprise_id="legal", external_system_id="src",
                            status="running", scenario="normal", started_at=now))
        session.flush()
        session.add(SyncResourceRun(id="resource-run", sync_run_id="run",
                                    source_resource_id="resource", status="running"))
        session.flush()
        for index in range(5):
            session.add(RawPageManifest(id=f"raw-{index}", sync_resource_run_id="resource-run",
                storage_key=f"synthetic-{index}.json.gz", content_hash="0"*64, fetched_at=now))
        session.commit()
    def project(index, payload, unit="unit"):
        with db.engine.begin() as conn:
            return persist_canonical_page(conn, enterprise_id="legal", source_id="src",
                resource_key="listings", manifest_id=f"raw-{index}", payload={"data":[payload]},
                observed_at=now,
                scope_snapshot={"business_unit_ids":[unit],"store_ids":["store-key"]})
    assert project(0, listing()).accepted == 1
    assert project(1, listing()).accepted == 1
    assert project(2, listing(listing_update_date="2026-09-09 01:02:03", is_delete=1)).stale == 1
    assert project(3, listing(), unit="other-unit").unassigned == 1
    options = dict(enterprise_id="legal", source_key="erp", binding_id="binding",
                   principal_id="synthetic-reviewer")
    with pytest.raises(ApiProblem) as blocked:
        review_binding(db, **options, status="approved", business_unit_id="other-unit")
    assert blocked.value.code == "source.binding_has_facts"
    review_binding(db, **options, status="rejected")
    assert project(4, listing()).unassigned == 1
    with db.session() as session:
        entities = list(session.scalars(select(BusinessEntity).where(
            BusinessEntity.entity_type == "listing")))
        assert len(entities) == 1 and entities[0].status == "unassigned"
        origin = session.scalar(select(CanonicalEntityOrigin))
        assert origin.business_unit_id is None and origin.raw_manifest_id == "raw-1"
        assert entities[0].attributes["store_key"] == "store-key"
    review_binding(db, **options, status="approved", business_unit_id="unit")
    with db.session() as session:
        origin = session.scalar(select(CanonicalEntityOrigin))
        assert origin.status == "assigned" and origin.business_unit_id == "unit"
        assert session.get(BusinessEntity, origin.entity_id).status == "active"
    db.dispose()
