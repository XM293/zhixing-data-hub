from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy.orm import Session


def test_source_operations_has_explicit_legal_governance_scope_and_no_business_facts():
    from zhixing_api.data_models import Base, Enterprise, ExternalSystem, SourceResource
    from zhixing_api.database import Database
    from zhixing_api.ingestion.operations import source_operations

    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)
    now = datetime.now(UTC)
    with Session(database.engine) as session:
        for legal in ("a", "b"):
            session.add(Enterprise(id=legal, code=legal, name=f"Synthetic {legal}",
                                   timezone="UTC", created_at=now))
            session.add(ExternalSystem(id=legal, enterprise_id=legal, system_key="erp",
                name=f"Synthetic ERP {legal}", system_type="lingxing",
                base_url="https://example.invalid"))
            session.add(SourceResource(id=legal, external_system_id=legal, resource_key="shops",
                path="/synthetic", schema_status="confirmed", enabled=True))
        session.add(SourceResource(id="pending", external_system_id="a", resource_key="purchases",
            path="/synthetic", schema_status="schema_pending", enabled=False))
        session.add(SourceResource(id="catalog-pending", external_system_id="a",
            resource_key="inbound_orders", path="/synthetic", schema_status="confirmed",
            enabled=False))
        session.commit()
    scope = SimpleNamespace(snapshot=lambda: {"scope_level": "business_unit",
                                              "selected_enterprise_ids": ["a"]})
    view = source_operations(database, "a", scope)
    assert view.enterprise_id == "a" and view.enterprise_name == "Synthetic a"
    assert len(view.sources) == 1 and view.sources[0].name == "Synthetic ERP a"
    assert view.resource_count == 3 and view.pending_resource_count == 1
    assert view.enabled_resource_count == 1 and view.source_record_count == 0
    assert view.latest_sync is None
    assert not ({"metrics", "events", "scene", "entity_count"} & view.model_dump().keys())
    from zhixing_api.data_models import RawPageManifest, SyncResourceRun, SyncRun

    with Session(database.engine) as session:
        for key, scenario in (("capture", "normal"), ("project", "raw_replay")):
            session.add(SyncRun(id=key, enterprise_id="a", external_system_id="a",
                scenario=scenario, status="succeeded", started_at=now))
            session.flush()
            session.add(SyncResourceRun(id=key, sync_run_id=key, source_resource_id="a",
                                       partition_key=key, status="succeeded"))
            session.flush()
            session.add(RawPageManifest(id=key, sync_resource_run_id=key,
                storage_key="synthetic", content_hash="0" * 64, bytes=1, row_count=5))
        session.commit()
    view = source_operations(database, "a", scope)
    assert view.source_record_count == 5
    assert view.sources[0].sync_run_count == 1
    assert view.latest_sync.id == "capture"
    database.dispose()


def test_source_operations_route_requires_legal_governance_permission(monkeypatch):
    import asyncio

    import pytest

    from zhixing_api.errors import ApiProblem
    from zhixing_api.routers import data_center

    actor = SimpleNamespace(enterprise_id="a")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=object())))
    monkeypatch.setattr(data_center, "resolve_development_actor", lambda request: actor)
    calls = []

    def deny(actor, permission, database, **kwargs):
        calls.append((permission, kwargs["scope_type"], kwargs["scope_id"]))
        raise ApiProblem(status_code=403, code="permission.denied", message="denied")

    monkeypatch.setattr(data_center, "require_permission", deny)
    monkeypatch.setattr(data_center, "source_operations", lambda *args:
                        pytest.fail("Denied requests must not read source operations"))
    with pytest.raises(ApiProblem):
        asyncio.run(data_center.source_operations_overview(request))
    assert calls == [("source.manage", "enterprise", "a")]
