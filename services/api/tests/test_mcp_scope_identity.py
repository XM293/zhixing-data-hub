from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from zhixing_api.actor_context import ActorContext, ActorScope, actor_scope_allows
from zhixing_api.mcp_session_service import _constrain_actor, resolve_mcp_session


def actor():
    return ActorContext(enterprise_id="legal-b", principal_id="group-admin",
        actor_key="admin", user_account_id="account-a", login_name="shared@verify",
        display_name="Synthetic administrator", role_id="role", access_role_keys=(),
        membership_ids=(), permissions=frozenset(), permission_set_version="v2",
        request_id="request", run_id="run", scopes=(
            ActorScope("enterprise", ("legal-b",), "allow"),
            ActorScope("store", ("private-store",), "deny")))


def test_enterprise_session_constraint_preserves_explicit_store_denial():
    constrained = _constrain_actor(actor(), [
        {"scope_type": "enterprise", "scope_ids": ["legal-b"]}])
    assert not actor_scope_allows(constrained, scope_type="store", scope_id="private-store")
    assert actor_scope_allows(constrained, scope_type="store", scope_id="public-store")


def test_current_legal_grant_does_not_authorize_an_unrelated_legal():
    assert actor_scope_allows(actor(), scope_type="enterprise", scope_id="legal-b")
    assert not actor_scope_allows(actor(), scope_type="enterprise", scope_id="legal-c")
    explicit = replace(actor(), scopes=(*actor().scopes,
        ActorScope("enterprise", ("legal-c",), "allow")))
    assert actor_scope_allows(explicit, scope_type="enterprise", scope_id="legal-c")


def test_session_reauthorization_uses_issued_account_and_legal_identity(monkeypatch):
    gateway = SimpleNamespace(id="session", status="active",
        expires_at=datetime.now(UTC) + timedelta(hours=1), user_account_id="account-a",
        enterprise_id="legal-b", principal_id="group-admin", allowed_tool_keys=[],
        scope_constraints=[], issued_permission_set_version="v1", agent_run_id=None,
        actor_snapshot={})
    account = SimpleNamespace(local_login_name="shared@verify")

    class Session:
        def scalar(self, statement):
            return gateway

        def get(self, model, key):
            return account if key == "account-a" else gateway

        def commit(self):
            pass

    class Database:
        @contextmanager
        def session(self):
            yield Session()

    resolved = {}

    def resolve(database, **kwargs):
        resolved.update(kwargs)
        return actor()

    monkeypatch.setattr("zhixing_api.mcp_session_service.resolve_database_actor", resolve)
    context = resolve_mcp_session(Database(), raw_token="synthetic-token",
        client_id="verify", request_id="request", run_id="run")
    assert resolved["user_account_id"] == "account-a"
    assert resolved["enterprise_id"] == "legal-b"
    assert context.actor.enterprise_id == "legal-b"


@pytest.mark.parametrize("level,allowed_type,allowed_id", [
    ("store", "store", "selected-store"),
    ("business_unit", "business_unit", "selected-project"),
    ("warehouse", "warehouse", "selected-warehouse"),
])
def test_selected_session_scope_cannot_expand_to_enterprise(
    monkeypatch, level, allowed_type, allowed_id,
):
    from zhixing_api.mcp_session_service import _selected_session_actor

    selection = {"scope_level": level}
    scope = SimpleNamespace(scope_level=level, business_unit_ids=("selected-project",),
        store_ids=("selected-store",), warehouse_ids=("selected-warehouse",))
    monkeypatch.setattr("zhixing_api.mcp_session_service.build_scope_context",
        lambda database, current, selection: scope)
    constrained = _selected_session_actor(None, actor(), selection)
    assert constrained.scope_selection == selection
    assert actor_scope_allows(constrained, scope_type=allowed_type, scope_id=allowed_id)
    assert not actor_scope_allows(constrained, scope_type="enterprise", scope_id="legal-b")
    assert not actor_scope_allows(constrained, scope_type="store", scope_id="sibling-store")
    assert not actor_scope_allows(constrained, scope_type="store", scope_id="private-store")
