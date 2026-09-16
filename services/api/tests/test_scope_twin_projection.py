from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import create_engine

from zhixing_api.data_models import (
    Base,
    BusinessEntity,
    BusinessUnit,
    CanonicalEntityOrigin,
    Enterprise,
    EnterpriseGroup,
    ExternalSystem,
    SourceResource,
)
from zhixing_api.database import Database
from zhixing_api.scope_context import ScopeContext


def test_scope_twin_projects_only_granted_locations_and_retains_source_quality():
    from zhixing_api.ingestion.scope_twin import project_scope_twin

    database = Database.from_engine(create_engine("sqlite://"))
    Base.metadata.create_all(database.engine)
    now = datetime(2026, 9, 9, tzinfo=UTC)
    with database.session() as session:
        session.add(EnterpriseGroup(id="g", code="g", name="Synthetic group", status="active",
                                   timezone="UTC", created_at=now, updated_at=now))
        for legal in ("a", "b"):
            session.add(Enterprise(id=legal, code=legal, name=legal, group_id="g",
                                   timezone="UTC", created_at=now))
        for unit, legal in (("a1", "a"), ("a2", "a"), ("b1", "b")):
            session.add(BusinessUnit(id=unit, enterprise_id=legal, unit_key=unit, name=unit,
                unit_type="project", status="active", created_at=now, updated_at=now))
            session.add(ExternalSystem(id=unit, enterprise_id=legal, system_key="erp-" + unit,
                name="Synthetic " + unit, system_type="lingxing", base_url="https://example.invalid",
                status="configured", connection_status="connected"))
            session.add(SourceResource(id=unit, external_system_id=unit, resource_key="shops",
                path="/synthetic", enabled=True, schema_status="confirmed"))
            for suffix, kind in (("store", "store"), ("other", "store"), ("product", "product")):
                key = unit + suffix
                session.add(BusinessEntity(id=key, enterprise_id=legal, entity_type=kind,
                    canonical_key=key, display_name=key, status="active", attributes={},
                    updated_at=now))
                session.add(CanonicalEntityOrigin(id=key, enterprise_id=legal, entity_id=key,
                    external_system_id=unit, resource_key="shops", external_key=key,
                    business_unit_id=unit, raw_manifest_id="synthetic-raw", schema_version="1",
                    mapping_version="1", observed_at=now, status="assigned"))
        session.add(BusinessEntity(id="warehouse-a1", enterprise_id="a", entity_type="warehouse",
            canonical_key="warehouse-a1", display_name="Synthetic warehouse", status="active",
            attributes={}, updated_at=now))
        session.add(CanonicalEntityOrigin(id="warehouse-a1", enterprise_id="a",
            entity_id="warehouse-a1", external_system_id="a1", resource_key="warehouses_local",
            external_key="warehouse-a1", business_unit_id="a1", raw_manifest_id="synthetic-raw",
            schema_version="1", mapping_version="1", observed_at=now, status="assigned"))
        session.commit()
    scope = ScopeContext(group_id="g", group_name="Synthetic group", enterprise_id="a",
        enterprise_name="a", allowed_enterprise_ids=("a", "b"),
        selected_enterprise_ids=("a", "b"), business_unit_ids=("a1", "a2", "b1"),
        store_ids=("a1store", "a2store", "b1store"), warehouse_ids=("warehouse-a1",),
        scope_level="group",
        scope_version="synthetic", timezone="UTC")
    view = project_scope_twin(database, scope)
    assert {node.id for node in view.organizations} == {"g", "a", "b", "a1", "a2", "b1"}
    assert {row.entity_id for row in view.locations} == {
        "a1store", "a2store", "b1store", "warehouse-a1"}
    assert view.data_as_of.replace(tzinfo=UTC) == now
    page = project_scope_twin(database, scope, offset=1, limit=1)
    assert page.total == 4 and len(page.locations) == 1
    assert page.locations[0].origin_id == view.locations[1].origin_id
    narrow = replace(scope, selected_enterprise_ids=("a",), business_unit_ids=("a1",),
                     store_ids=("a1store",), scope_level="store")
    assert [row.entity_id for row in project_scope_twin(database, narrow).locations] == ["a1store"]
    single_store = replace(scope, store_ids=("a1store",), scope_level="store")
    assert {node.id for node in project_scope_twin(database, single_store).organizations} == {
        "g", "a", "a1"}
    assert [row.entity_id for row in project_scope_twin(database, single_store).locations] == [
        "a1store"]
    project = replace(scope, business_unit_ids=("a1",), scope_level="business_unit")
    assert {node.id for node in project_scope_twin(database, project).organizations} == {
        "g", "a", "a1"}
    denied = replace(scope, allowed_enterprise_ids=("a",))
    denied_view = project_scope_twin(database, denied)
    assert {node.id for node in denied_view.organizations} == {"g", "a", "a1", "a2"}
    assert {row.enterprise_id for row in denied_view.locations} == {"a"}
    with database.session() as session:
        session.get(SourceResource, "a1").schema_status = "schema_pending"
        session.get(ExternalSystem, "a1").status = "disabled"
        session.get(CanonicalEntityOrigin, "b1store").status = "unassigned"
        session.commit()
    view = project_scope_twin(database, scope)
    assert len(view.locations) == 3
    row = next(item for item in view.locations if item.entity_id == "a1store")
    assert row.schema_status == "schema_pending" and row.source_status == "disabled"
    assert not ({"base_url", "credential_ref", "records_read"} & row.model_dump().keys())
    empty = project_scope_twin(database, replace(scope, allowed_enterprise_ids=()))
    assert empty.organizations == [] and empty.locations == [] and empty.data_as_of is None
    with database.session() as session:
        session.get(CanonicalEntityOrigin, "a1store").business_unit_id = "b1"
        session.commit()
    assert {row.entity_id for row in project_scope_twin(database, scope).locations} == {
        "a2store", "warehouse-a1"}
    database.dispose()


def test_scope_twin_route_checks_permission_before_read(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import pytest

    from zhixing_api.errors import ApiProblem
    from zhixing_api.routers import canonical

    actor = object()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=object())))
    monkeypatch.setattr(canonical, "resolve_development_actor", lambda request: actor)

    def deny(candidate, permission, *args, **kwargs):
        assert candidate is actor and permission == "metric.query.execute"
        raise ApiProblem(status_code=403, code="permission.denied", message="denied")

    monkeypatch.setattr(canonical, "require_permission", deny)
    monkeypatch.setattr(canonical, "project_scope_twin", lambda *args, **kwargs:
                        pytest.fail("Unauthorized graph must not be read"))
    with pytest.raises(ApiProblem):
        asyncio.run(canonical.scope_twin(request, 0, 20))
