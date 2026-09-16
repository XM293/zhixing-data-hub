import pytest


def test_erp_accounts_are_source_entities_without_platform_privileges_or_contact_fields():
    from zhixing_api.ingestion.mapping import map_source_user

    row = {"uid": 42, "realname": "Synthetic ERP user", "status": 0, "is_master": 1,
           "username": "synthetic-login", "role": "Synthetic ERP administrator",
           "seller": "Synthetic store names", "email": "synthetic@example.invalid",
           "mobile": "synthetic", "last_login_ip": "192.0.2.1"}
    mapped = map_source_user(row)
    assert mapped.entity_type == "source_user" and mapped.external_key == "42"
    assert mapped.status == "inactive" and mapped.requires_assignment
    assert mapped.attributes == {"is_master": True}
    assert map_source_user({**row, "status": 1}).status == "active"
    for bad in ({**row, "uid": 0}, {**row, "uid": True}, {**row, "status": 2},
                {**row, "is_master": 2}, {**row, "realname": None}):
        with pytest.raises(ValueError):
            map_source_user(bad)


def test_erp_directory_persistence_is_source_isolated_and_creates_no_login_identity():
    from datetime import UTC, datetime

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from zhixing_api.data_models import (
        Base,
        BusinessEntity,
        ExternalSystem,
        Principal,
        SourceBinding,
        UserAccount,
    )
    from zhixing_api.ingestion.persistence import persist_canonical_page

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for legal in ("a", "b"):
            session.add(ExternalSystem(id=f"source-{legal}", enterprise_id=legal,
                system_key=f"synthetic-{legal}", name="Synthetic ERP", system_type="lingxing",
                base_url="https://example.invalid"))
        session.commit()
    payload = {"data": [{"uid": 42, "realname": "Synthetic ERP user",
                         "status": 1, "is_master": 1}]}
    for page, legal in enumerate(("a", "b", "a")):
        with engine.begin() as connection:
            counts = persist_canonical_page(connection, enterprise_id=legal,
                source_id=f"source-{legal}", resource_key="erp_users", manifest_id=f"raw-{page}",
                payload=payload, observed_at=datetime.now(UTC))
            assert counts.accepted == 1
    with engine.begin() as connection:
        stale = persist_canonical_page(connection, enterprise_id="a", source_id="source-a",
            resource_key="erp_users", manifest_id="raw-old",
            payload={"data": [{**payload["data"][0], "status": 0}]},
            observed_at=datetime(2020, 1, 1, tzinfo=UTC))
        assert stale.stale == 1 and stale.accepted == 0
    with Session(engine) as session:
        entities = session.scalars(select(BusinessEntity)).all()
        assert len(entities) == 2 and {item.enterprise_id for item in entities} == {"a", "b"}
        assert all(item.entity_type == "source_user" and item.status == "unassigned"
                   for item in entities)
        assert all(item.attributes["source_status"] == "active" for item in entities)
        bindings = session.scalars(select(SourceBinding)).all()
        assert len(bindings) == 2 and all(item.status == "pending" for item in bindings)
        assert session.scalar(select(func.count()).select_from(UserAccount)) == 0
        assert session.scalar(select(func.count()).select_from(Principal)) == 0
    engine.dispose()
