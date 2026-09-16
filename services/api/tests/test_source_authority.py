from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext, ActorScope
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
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.authority import AuthorityRequest, authority_condition, save_authority


def test_authority_selects_source_and_project_without_cross_legal_fallback():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(Enterprise(id="a", code="a", name="Synthetic", timezone="UTC", created_at=now))
        session.add(BusinessUnit(id="a1", enterprise_id="a", unit_key="a1", name="Synthetic",
            unit_type="project", status="active", created_at=now, updated_at=now))
        for source_id in ("s1", "s2"):
            session.add(ExternalSystem(id=source_id, enterprise_id="a", system_key=source_id,
                name="Synthetic", system_type="lingxing", base_url="https://example.invalid"))
            session.add(SourceResource(id=source_id, external_system_id=source_id,
                resource_key="orders", path="/synthetic", schema_status="confirmed", enabled=True))
        for key, legal, unit, source in (
            ("1", "a", "a1", "s1"), ("2", "a", "a1", "s2"),
            ("3", "a", "a2", "s2"), ("4", "b", "b1", "s1"),
        ):
            session.add(CanonicalSalesOrder(id=key, enterprise_id=legal, business_unit_id=unit,
                external_system_id=source, resource_key="orders", external_key=key,
                raw_manifest_id="synthetic", schema_version="1", mapping_version="1",
                observed_at=now, source_updated_at=now, store_key="synthetic", status="Shipped",
                ordered_at=now, source_local_time="2026-09-09 12:00:00", business_date=now.date()))
        session.add(SourceAuthorityAssignment(id="rule", enterprise_id="a", business_unit_id="a1",
            external_system_id="s2", fact_family="orders", resource_key="orders", status="active",
            version=1, created_at=now, updated_at=now))
        session.commit()
        selected = session.scalars(select(CanonicalSalesOrder.id).where(
            authority_condition(CanonicalSalesOrder, "orders"))).all()
        assert selected == ["2"]
    database = Database.from_engine(engine)
    actor = ActorContext(enterprise_id="a", principal_id="p", actor_key="p", user_account_id="u",
        login_name="synthetic", display_name="Synthetic", role_id="admin", access_role_keys=(),
        membership_ids=(), permissions=frozenset({"source.manage"}), permission_set_version="v1",
        request_id="r", run_id="r", scopes=(ActorScope("enterprise", ("a",), "allow"),))
    request = AuthorityRequest(business_unit_id="a1", source_key="s1", fact_family="orders",
                               resource_key="orders")
    with pytest.raises(ApiProblem) as conflict:
        save_authority(database, actor, request)
    assert conflict.value.code == "authority.version_conflict"
    saved = save_authority(database, actor, request.model_copy(update={"expected_version": 1}))
    assert saved.version == 2 and saved.source_key == "s1"
    with pytest.raises(ApiProblem) as denied:
        save_authority(database, actor, request.model_copy(update={"business_unit_id": "b1"}))
    assert denied.value.status_code == 403
    with Session(engine) as session:
        assert session.scalars(select(CanonicalSalesOrder.id).where(
            authority_condition(CanonicalSalesOrder, "orders"))).all() == ["1"]
        session.get(ExternalSystem, "s1").status = "disabled"
        session.commit()
        assert not session.scalars(select(CanonicalSalesOrder.id).where(
            authority_condition(CanonicalSalesOrder, "orders"))).all()
    engine.dispose()
