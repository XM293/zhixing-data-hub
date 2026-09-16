from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from sqlalchemy import select, text

from zhixing_api.actor_context import (
    authenticate_local_actor,
    create_auth_session,
    resolve_database_actor,
)
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.data_models import Base, BusinessUnit, UserAccount
from zhixing_api.database import Database
from zhixing_api.retirement import analyze_retirement, execute_retirement
from zhixing_api.scope_context import build_scope_context


def test_bootstrap_preview_execute_and_repeat(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'bootstrap_verify.db'}")
    database.migrate()
    manifest = {
        "version": 1,
        "group": {
            "id": "group-synthetic",
            "code": "synthetic",
            "name": "Synthetic Group",
        },
        "enterprises": [
            {"id": "legal-a", "code": "legal-a", "name": "Legal A"},
            {"id": "legal-b", "code": "legal-b", "name": "Legal B"},
        ],
        "business_units": [
            {
                "id": "project-a", "enterprise_id": "legal-a",
                "unit_key": "project-a", "name": "Project A",
            },
            {
                "id": "project-b", "enterprise_id": "legal-b",
                "unit_key": "project-b", "name": "Project B",
            },
        ],
    }
    try:
        preview = analyze_bootstrap(database.engine, manifest)
        assert preview["enterprises"]["to_create"] == 2
        result = execute_bootstrap(database.engine, manifest, backup_id="backup-synthetic",
                                   confirmed=True, plan_hash=preview["plan_hash"])
        assert result["created"] == {"group": 1, "enterprises": 2, "business_units": 2}
        repeated = execute_bootstrap(
            database.engine, manifest, backup_id="backup-synthetic", confirmed=True,
            plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        )
        assert repeated["created"] == {"group": 0, "enterprises": 0, "business_units": 0}
    finally:
        database.dispose()


@pytest.fixture
def formal_manifest():
    return {
        "version": 2,
        "group": {"id": "group-verify", "code": "verify", "name": "Verify Group"},
        "enterprises": [
            {"id": key, "code": key, "name": key} for key in ("legal-a", "legal-b")
        ],
        "business_units": [
            {"id": key, "enterprise_id": enterprise, "unit_key": key, "name": key}
            for key, enterprise in (("project-a", "legal-a"), ("brand-a", "legal-a"),
                                    ("project-b", "legal-b"))
        ],
        "role_templates": [{
            "role_key": "source-admin", "name": "Source administrator",
            "permission_keys": ["platform.navigation.read", "identity.user.manage",
                                "identity.access.manage", "source.manage", "metric.query.execute"],
        }],
        "administrators": [{
            "id": f"admin-{index}", "home_enterprise_id": "legal-a",
            "login_name": f"admin-{index}@verify", "display_name": f"Verify Admin {index}",
            "password_env": f"BOOTSTRAP_VERIFY_ADMIN_{index}_PASSWORD",
            "enterprise_ids": ["legal-a", "legal-b"], "role_keys": ["source-admin"],
        } for index in (1, 2)],
    }


@pytest.fixture
def formal_database():
    database = Database("sqlite:///:memory:")
    Base.metadata.create_all(database.engine)
    yield database
    database.dispose()


@pytest.mark.anyio
async def test_reviewed_order_tool_bootstrap_scope_audit_and_deny(formal_database, formal_manifest):
    from zhixing_api.data_models import ToolDefinition, ToolInvocation
    from zhixing_api.errors import ApiProblem
    from zhixing_api.tool_service import invoke_tool

    database = formal_database
    formal_manifest["read_only_tools"] = ["query_authoritative_orders"]
    preview = analyze_bootstrap(database.engine, formal_manifest)
    impact = next(row for row in preview["tables"] if row["table"] == "tool_definitions")
    assert impact["to_create"] == 2
    execute_bootstrap(database.engine, formal_manifest, backup_id="verify-backup", confirmed=True,
        plan_hash=preview["plan_hash"], credential_provider=lambda _: "Synthetic-Verify-Only-379!")
    actor = authenticate_local_actor(database, login_name="admin-1@verify",
        password="Synthetic-Verify-Only-379!", request_id="verify", run_id="verify")
    actor = replace(actor, scope_selection={"scope_level": "group"})
    params = {"date_from": "2026-09-01", "date_to": "2026-09-10"}
    result = await invoke_tool(database, None, None, actor,
        tool_key="query_authoritative_orders", parameters=params)
    assert result.output["definition_version"] == "canonical-orders-v1"
    assert set(result.output["scope_snapshot"]["selected_enterprise_ids"]) == {"legal-a", "legal-b"}
    assert result.output["order_count"] == 0
    assert result.output["base_amount"] is None
    from zhixing_api.workspace_service import build_workspace_read_model
    workspace = build_workspace_read_model(database, actor, "platform-ops")
    assert workspace.scope_context["schema_version"] == 2
    assert workspace.scope.kind == "group"
    assert workspace.metrics == workspace.activities == workspace.decisions == []
    assert workspace.scene is None
    for parameters, allowed, current_actor in (
        ({**params, "enterprise_id": "other"}, None, actor),
        (params, frozenset(), actor),
        (params, None, replace(actor, permissions=frozenset())),
    ):
        with pytest.raises(ApiProblem):
            await invoke_tool(database, None, None, current_actor,
                tool_key="query_authoritative_orders", parameters=parameters,
                allowed_tool_keys=allowed)
    with database.session() as session:
        assert len(session.scalars(select(ToolDefinition)).all()) == 2
        calls = session.scalars(select(ToolInvocation)).all()
        assert sorted(call.status for call in calls) == ["denied", "denied", "failed", "succeeded"]
        success = next(call for call in calls if call.status == "succeeded")
        assert success.actor_snapshot["scope_context"] == result.output["scope_snapshot"]
    repeated = analyze_bootstrap(database.engine, formal_manifest)
    assert next(row for row in repeated["tables"] if row["table"] == "tool_definitions")[
        "to_create"] == 0
    for tools in (["unknown"], ["query_authoritative_orders", "query_authoritative_orders"]):
        formal_manifest["read_only_tools"] = tools
        with pytest.raises(ValueError):
            analyze_bootstrap(database.engine, formal_manifest)


def test_formal_bootstrap_real_login_scope_and_repeat(formal_database, formal_manifest):
    database = formal_database
    preview = analyze_bootstrap(database.engine, formal_manifest)
    tables = {row["table"]: row for row in preview["tables"]}
    assert tables["user_accounts"]["to_create"] == 2
    assert tables["role_assignments"]["to_create"] == 4
    password = "synthetic-bootstrap-password"
    result = execute_bootstrap(
        database.engine, formal_manifest, backup_id="verify-backup", confirmed=True,
        plan_hash=preview["plan_hash"], credential_provider=lambda key: password,
    )
    assert result["status"] == "succeeded"
    assert password not in str(result)
    for login in ("admin-1@verify", "admin-2@verify"):
        actor = authenticate_local_actor(database, login_name=login, password=password,
                                         request_id="verify", run_id="verify")
        assert {"identity.user.manage", "source.manage"} <= actor.permissions
        scope = build_scope_context(database, actor, selection={"scope_level": "group"})
        assert set(scope.selected_enterprise_ids) == {"legal-a", "legal-b"}
        assert set(scope.business_unit_ids) == {"project-a", "brand-a", "project-b"}
        switched = resolve_database_actor(database, login_name=login, enterprise_id="legal-b",
                                          user_account_id=actor.user_account_id,
                                          request_id="verify", run_id="verify")
        assert "source.manage" in switched.permissions
    with database.session() as session:
        previous_hashes = list(session.scalars(select(UserAccount.password_hash)))
    repeated = execute_bootstrap(
        database.engine, formal_manifest, backup_id="verify-backup", confirmed=True,
        plan_hash=analyze_bootstrap(database.engine, formal_manifest)["plan_hash"],
        credential_provider=lambda key: pytest.fail("repeat must not read credentials"),
    )
    assert not any(repeated["created"].values())
    with database.session() as session:
        assert list(session.scalars(select(UserAccount.password_hash))) == previous_hashes


def test_bootstrap_confirmation_hash_and_credentials_fail_atomically(
    formal_database, formal_manifest,
):
    engine = formal_database.engine
    preview = analyze_bootstrap(engine, formal_manifest)
    with pytest.raises(ValueError, match="confirmation"):
        execute_bootstrap(engine, formal_manifest, backup_id="verify",
                          plan_hash=preview["plan_hash"])
    with pytest.raises(ValueError, match="plan"):
        execute_bootstrap(engine, formal_manifest, backup_id="verify", confirmed=True,
                          plan_hash="stale")
    with pytest.raises(ValueError, match="credential"):
        execute_bootstrap(engine, formal_manifest, backup_id="verify", confirmed=True,
                          plan_hash=preview["plan_hash"], credential_provider=lambda key: "")
    assert analyze_bootstrap(engine, formal_manifest)["plan_hash"] == preview["plan_hash"]


def test_bootstrap_rejects_manifest_cycles_unknown_fields_and_identity_drift(
    formal_database, formal_manifest,
):
    for mutate in (
        lambda item: item["administrators"][0].update(password="must-not-be-accepted"),
        lambda item: item["business_units"][0].update(parent_id="project-b"),
        lambda item: item["business_units"][0].update(parent_id="project-a"),
        lambda item: item["group"].update(timezone="Invalid/Timezone"),
        lambda item: item["role_templates"][0].update(permission_keys=["invented.permission"]),
    ):
        invalid = deepcopy(formal_manifest)
        mutate(invalid)
        with pytest.raises(ValueError):
            analyze_bootstrap(formal_database.engine, invalid)
    execute_bootstrap(
        formal_database.engine, formal_manifest, backup_id="verify", confirmed=True,
        plan_hash=analyze_bootstrap(formal_database.engine, formal_manifest)["plan_hash"],
        credential_provider=lambda key: "synthetic-bootstrap-password",
    )
    with formal_database.session() as session:
        session.get(BusinessUnit, "project-a").status = "disabled"
        session.commit()
    with pytest.raises(ValueError, match="drift"):
        analyze_bootstrap(formal_database.engine, formal_manifest)


def test_retirement_preserves_formal_access_and_revokes_sessions(formal_database, formal_manifest):
    database = formal_database
    password = "synthetic-bootstrap-password"
    execute_bootstrap(
        database.engine, formal_manifest, backup_id="verify", confirmed=True,
        plan_hash=analyze_bootstrap(database.engine, formal_manifest)["plan_hash"],
        credential_provider=lambda key: password,
    )
    actor = authenticate_local_actor(database, login_name="admin-1@verify", password=password,
                                     request_id="verify", run_id="verify")
    create_auth_session(database, actor)
    with database.engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE verify_facts (id TEXT PRIMARY KEY, "
            "enterprise_id TEXT REFERENCES enterprises(id))",
        ))
        connection.execute(text("INSERT INTO verify_facts VALUES ('fact-a', 'legal-a')"))
    manifest = {"version": 1, "enterprise_id": "legal-a", "revoke_sessions": True,
                "tables": [{"table": "verify_facts", "ids": ["fact-a"], "expected_count": 1}]}
    for protected in ("role_assignments", "scope_grants", "enterprise_memberships",
                      "access_role_permissions", "enterprise_scope_grants"):
        with pytest.raises(ValueError, match="protected"):
            analyze_retirement(database.engine, {**manifest, "tables": [
                {"table": protected, "ids": [], "expected_count": 0},
            ]})
    plan = analyze_retirement(database.engine, manifest)
    result = execute_retirement(database.engine, manifest, backup_id="verify",
                                plan_hash=plan["plan_hash"], confirmed=True)
    assert result == {"deleted": 1, "revoked": 1}
    restored = authenticate_local_actor(database, login_name="admin-1@verify", password=password,
                                        request_id="verify-again", run_id="verify-again")
    assert restored.permissions == actor.permissions
    assert not any(row["to_create"] for row in
                   analyze_bootstrap(database.engine, formal_manifest)["tables"])
