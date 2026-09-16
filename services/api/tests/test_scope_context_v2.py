from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine

from zhixing_api.actor_context import ActorContext, ActorScope, actor_scope_allows
from zhixing_api.data_models import (
    Base,
    BusinessEntity,
    BusinessUnit,
    CanonicalEntityOrigin,
    Enterprise,
    EnterpriseGroup,
    EnterpriseMembership,
    Principal,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.mcp_session_service import _selected_session_actor
from zhixing_api.scope_context import build_scope_context


def test_group_expansion_honors_membership_explicit_deny_and_selected_projects(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'scope_v2_verify.db'}")
    database.migrate()
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(EnterpriseGroup(id="g", code="g", name="Synthetic group", status="active",
                    timezone="UTC", created_at=now, updated_at=now))
        session.flush()
        for key in ("a", "b"):
            session.add(Enterprise(id=key, code=key, name=key, group_id="g", timezone="UTC",
                                   created_at=now))
        session.flush()
        session.add(Principal(id="principal", enterprise_id="a", principal_key="principal",
                    principal_type="person", display_name="Synthetic principal", status="active",
                    created_at=now, updated_at=now))
        session.flush()
        for enterprise in ("a", "b"):
            session.add(EnterpriseMembership(id=f"member-{enterprise}", principal_id="principal",
                        enterprise_id=enterprise, membership_type="member", is_primary=False,
                        status="active", valid_from=now, created_at=now, updated_at=now))
        for key, enterprise in (("a1", "a"), ("a2", "a"), ("b1", "b")):
            session.add(BusinessUnit(id=key, enterprise_id=enterprise, unit_key=key,
                        name=key, unit_type="project", status="active", created_at=now,
                        updated_at=now))
        session.commit()
    actor = ActorContext(enterprise_id="a", principal_id="principal", actor_key="principal",
            user_account_id="account", login_name="synthetic", display_name="Synthetic",
            role_id="admin", access_role_keys=("admin",), membership_ids=(),
            permissions=frozenset({"source.manage"}), permission_set_version="test-v2",
            request_id="request-test", run_id="run-test", group_id="g",
            scopes=(ActorScope("enterprise", ("a", "b"), "allow"),
                    ActorScope("enterprise", ("b",), "deny")))
    try:
        context = build_scope_context(database, actor, selection={"scope_level": "group"})
        assert context.allowed_enterprise_ids == ("a",)
        assert context.selected_enterprise_ids == ("a",)
        assert set(context.business_unit_ids) == {"a1", "a2"}
        assert context.snapshot()["current_enterprise_id"] == "a"
        with pytest.raises(ApiProblem):
            build_scope_context(database, actor, selection={"scope_level": "group",
                                                          "selected_enterprise_ids": ["b"]})
        with pytest.raises(ApiProblem):
            build_scope_context(database, actor, selection={"scope_level": "business_unit",
                                                          "business_unit_ids": ["b1"]})
    finally:
        database.dispose()


def test_store_only_scope_derives_project_without_granting_sibling_stores(monkeypatch):
    from types import SimpleNamespace

    from zhixing_api import agent_context_service
    from zhixing_api.routers import data_center

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    database = Database.from_engine(engine)
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(Enterprise(id="a", code="a", name="Synthetic", timezone="UTC", created_at=now))
        session.add(BusinessUnit(id="a1", enterprise_id="a", unit_key="a1", name="Synthetic",
            unit_type="project", status="active", created_at=now, updated_at=now))
        for key in ("store-a", "store-b"):
            session.add(BusinessEntity(id=key, enterprise_id="a", canonical_key=key,
                entity_type="store", display_name="Synthetic", status="active", attributes={},
                updated_at=now))
            session.add(CanonicalEntityOrigin(id=key, enterprise_id="a", entity_id=key,
                business_unit_id="a1", external_system_id="source", resource_key="shops",
                external_key=key, raw_manifest_id="synthetic", schema_version="1",
                mapping_version="1", observed_at=now, status="assigned"))
        session.commit()
    actor = ActorContext(enterprise_id="a", principal_id="principal", actor_key="principal",
        user_account_id="account", login_name="synthetic", display_name="Synthetic",
        role_id="reader", access_role_keys=(), membership_ids=(), permissions=frozenset(),
        permission_set_version="v1", request_id="request", run_id="run",
        scopes=(ActorScope("store", ("store-a",), "allow"),))
    scope = build_scope_context(database, actor)
    assert scope.business_unit_ids == ("a1",) and scope.store_ids == ("store-a",)
    enterprise_actor = replace(actor, scopes=(ActorScope("enterprise", ("a",), "allow"),))
    selection = {"scope_level": "store", "store_ids": ["store-a"]}
    mcp_actor = _selected_session_actor(database, enterprise_actor, selection)
    assert actor_scope_allows(mcp_actor, scope_type="store", scope_id="store-a")
    assert not actor_scope_allows(mcp_actor, scope_type="store", scope_id="store-b")
    assert not actor_scope_allows(mcp_actor, scope_type="enterprise", scope_id="a")
    selected_actor = replace(enterprise_actor, scope_selection=selection,
        permissions=frozenset({"metric.query.execute", "source.manage"}))
    monkeypatch.setattr(data_center, "resolve_development_actor", lambda request: selected_actor)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=database)))
    for key in ("enterprise", "store-b"):
        with pytest.raises(ApiProblem):
            data_center._authorize(request, "metric.query.execute",
                resource_type="metric.series", resource_key="synthetic", scope_key=key)
    assert data_center._authorize(request, "metric.query.execute",
        resource_type="metric.series", resource_key="synthetic",
        scope_key="store-a") == selected_actor
    assert data_center._authorize(request, "source.manage",
        resource_type="source", resource_key="synthetic", scope_key="enterprise") == selected_actor
    queried_scopes = []
    original_query = agent_context_service.query_metric_series

    def scoped_query(database, **kwargs):
        queried_scopes.append(kwargs["scope_key"])
        return original_query(database, **kwargs)

    monkeypatch.setattr(agent_context_service, "query_metric_series", scoped_query)
    agent_context_service.build_metric_context(database, selected_actor,
        question="查询订单指标", requested_scope_key=None)
    assert queried_scopes == ["store-a"]
    with pytest.raises(ApiProblem):
        _selected_session_actor(database, replace(enterprise_actor,
            scopes=(*enterprise_actor.scopes, ActorScope("store", ("store-a",), "deny"))),
            selection)
    denied = build_scope_context(database, replace(actor, scopes=(*actor.scopes,
        ActorScope("business_unit", ("a1",), "deny"))))
    assert denied.business_unit_ids == () and denied.store_ids == ()
    database.dispose()
