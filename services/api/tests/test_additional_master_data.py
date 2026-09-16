import pytest


def test_spu_states_and_uncertain_attribute_identifiers_are_not_guessed():
    from zhixing_connectors.catalog import can_project_to_core, resource_spec

    from zhixing_api.ingestion.mapping import map_spu

    row = {"ps_id": 42, "spu": "SYNTHETIC-SPU", "spu_name": "Synthetic style",
           "cid": 7, "bid": 8, "developer_uid": 9, "cg_uid": 10, "status": 2,
           "cg_price": "1.125", "create_time": "2026-09-09 12:00:00"}
    for status, expected in ((0, "discontinued"), (1, "on_sale"),
                             (2, "developing"), (3, "clearance")):
        item = map_spu({**row, "status": status})
        assert item.entity_type == "product_style" and item.status == expected
        assert item.external_key == "42" and item.source_updated_at is None
        assert item.attributes == {"spu": "SYNTHETIC-SPU", "category_external_key": "7",
            "brand_external_key": "8", "developer_external_key": "9",
            "purchaser_external_key": "10"}
    for bad in ({**row, "status": 4}, {**row, "ps_id": True}, {**row, "ps_id": 0}):
        with pytest.raises(ValueError):
            map_spu(bad)
    attributes = resource_spec("product_attributes")
    assert attributes.schema_status == "confirmed" and can_project_to_core(attributes)


def test_product_tags_and_logistics_channels_use_confirmed_fields_only():
    from zhixing_connectors.catalog import resource_spec

    from zhixing_api.ingestion.mapping import map_logistics_channel, map_product_tag

    tag = map_product_tag({"label_id": "tag-synthetic", "label_name": "Synthetic tag",
                           "gmt_created": 49})
    assert (tag.entity_type, tag.external_key, tag.status) == (
        "product_tag", "tag-synthetic", "unknown")
    assert tag.source_updated_at is None and tag.attributes == {}
    assert tag.requires_assignment
    spec = resource_spec("product_tags")
    assert spec.method == "GET" and not spec.paginated and spec.rows_path == ("data", "list")
    channel = {"id": "42", "channel_name": "Synthetic channel", "enabled": 1,
        "provider": {"id": "7"}, "method_id": "9", "method_name": "Synthetic method",
        "gmt_modified": "2026-09-09 12:00:00", "freight": [{"billing_price": "1.125"}],
        "remark": "Synthetic private note"}
    mapped = map_logistics_channel(channel)
    assert mapped.entity_type == "logistics_channel" and mapped.status == "active"
    assert mapped.source_updated_at is None
    assert mapped.attributes == {"provider_external_key": "7", "method_external_key": "9"}
    assert map_logistics_channel({**channel, "enabled": 0}).status == "inactive"
    assert resource_spec("logistics_channels").page_size == 20
    for bad in ({**channel, "enabled": 2}, {**channel, "enabled": True},
                {**channel, "provider": []}, {**channel, "id": None}):
        with pytest.raises(ValueError):
            map_logistics_channel(bad)


def test_master_catalog_persistence_is_idempotent_isolated_and_preserves_previous_valid_rows():
    from datetime import UTC, datetime

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from zhixing_api.data_models import (
        Base,
        BusinessEntity,
        CanonicalEntityOrigin,
        ExternalSystem,
        MappingConflict,
        SourceBinding,
    )
    from zhixing_api.ingestion.persistence import persist_canonical_page
    from zhixing_api.ingestion.planning import schedule_strategy

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for legal in ("a", "b"):
            session.add(ExternalSystem(id=legal, enterprise_id=legal, system_key=legal,
                name="Synthetic ERP", system_type="lingxing", base_url="https://example.invalid"))
        session.commit()
    tag = {"label_id": "42", "label_name": "Synthetic tag"}
    channel = {"id": "42", "channel_name": "Synthetic channel", "enabled": 1,
               "provider": {"id": "7"}, "method_id": "9"}
    style = {"ps_id": 42, "spu": "SYNTHETIC-SPU", "spu_name": "Synthetic style",
             "cid": 7, "bid": 8, "developer_uid": 9, "cg_uid": 10, "status": 2}
    for index, legal in enumerate(("a", "b", "a")):
        for resource, data in (("product_tags", {"list": [tag], "total": 1}),
                               ("logistics_channels", [channel]), ("product_styles", [style])):
            assert schedule_strategy(resource) == "snapshot"
            with engine.begin() as connection:
                counts = persist_canonical_page(connection, enterprise_id=legal, source_id=legal,
                    resource_key=resource, manifest_id=f"raw-{index}-{resource}",
                    payload={"data": data},
                    observed_at=datetime(2026, 9, 9, tzinfo=UTC))
                assert counts.accepted == 1
    with engine.begin() as connection:
        counts = persist_canonical_page(connection, enterprise_id="a", source_id="a",
            resource_key="logistics_channels", manifest_id="raw-invalid",
            payload={"data": [{**channel, "enabled": 9}]},
            observed_at=datetime(2026, 9, 10, tzinfo=UTC))
        assert counts.rejected == 1 and counts.accepted == 0
    with Session(engine) as session:
        entities = session.scalars(select(BusinessEntity)).all()
        assert len(entities) == 6 and {item.enterprise_id for item in entities} == {"a", "b"}
        assert all(item.status == "unassigned" for item in entities)
        assert len(session.scalars(select(SourceBinding)).all()) == 6
        origins = session.scalars(select(CanonicalEntityOrigin)).all()
        assert len(origins) == 6 and all(item.raw_manifest_id != "raw-invalid" for item in origins)
        assert len(session.scalars(select(MappingConflict)).all()) == 1
    engine.dispose()
