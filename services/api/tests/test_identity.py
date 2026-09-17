from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.actor_context import actor_scope_allows, resolve_database_actor
from zhixing_api.config import Settings
from zhixing_api.data_models import AuthorizationDecision, IdentityManagementEvent, OrgUnit
from zhixing_api.identity_seed import role_permission_id
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'identity_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


def test_role_permission_id_stays_inside_postgresql_limit() -> None:
    value = role_permission_id(
        "regional-platform-administrator",
        "enterprise.data-governance.configuration.manage",
    )

    assert len(value) <= 64
    assert value == role_permission_id(
        "regional-platform-administrator",
        "enterprise.data-governance.configuration.manage",
    )


@pytest.mark.anyio
async def test_org_subtree_scope_includes_new_descendants_and_excludes_siblings(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/identity/admin/org-units",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "catalog-org-operations-east-001",
                "org_key": "operations-east",
                "name": "华东运营组",
                "unit_type": "team",
                "parent_org_key": "operations",
                "reason": "验证组织子树实时授权",
            },
        )

    assert created.status_code == 201, created.text
    with app.state.database.session() as session:
        child = session.scalar(
            select(OrgUnit).where(
                OrgUnit.enterprise_id == "ent_zhixing_demo",
                OrgUnit.org_key == "operations-east",
            )
        )
        assert child is not None
        child_id = child.id

    manager = resolve_database_actor(
        app.state.database,
        login_name="manager",
        request_id="req_org_subtree_test",
        run_id="run_org_subtree_test",
        authentication_method="test",
    )
    assert actor_scope_allows(
        manager,
        scope_type="org_unit",
        scope_id=child_id,
        database=app.state.database,
    )
    assert not actor_scope_allows(
        manager,
        scope_type="org_unit",
        scope_id="org_service",
        database=app.state.database,
    )


@pytest.mark.anyio
async def test_current_identity_uses_database_roles_scopes_and_navigation(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/api/v1/identity/me")
        unknown = await client.get(
            "/api/v1/identity/me", headers={"X-Zhixing-Demo-Actor": "missing"}
        )
        ceo = await client.get("/api/v1/identity/me", headers={"X-Zhixing-Demo-Actor": "ceo"})
        employee = await client.get(
            "/api/v1/identity/me", headers={"X-Zhixing-Demo-Actor": "employee"}
        )
        admin = await client.get("/api/v1/identity/me", headers={"X-Zhixing-Demo-Actor": "admin"})

    assert missing.status_code == 401
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "auth.development_actor_unknown"
    assert ceo.status_code == 200
    ceo_payload = ceo.json()
    assert ceo_payload["actor"]["principal_key"] == "principal-ceo-lin"
    assert ceo_payload["actor"]["organization"] == "知行电商集团"
    assert "meeting.decision.confirm" in ceo_payload["actor"]["permissions"]
    assert "knowledge.policy.publish" in ceo_payload["actor"]["permissions"]
    assert "memory.candidate.review" in ceo_payload["actor"]["permissions"]
    assert "memory.approved.retire" in ceo_payload["actor"]["permissions"]
    assert "evaluation.manage" in ceo_payload["actor"]["permissions"]
    assert "analysis.run" in ceo_payload["actor"]["permissions"]
    assert "analysis.schedule.manage" in ceo_payload["actor"]["permissions"]
    assert "actions" in ceo_payload["navigation_sections"]
    assert "admin" in ceo_payload["navigation_sections"]
    ceo_navigation = {item["key"]: item for item in ceo_payload["navigation"]}
    assert ceo_navigation["home"]["items"][-1]["key"] == "assistant"
    assert "sources" not in {
        item["key"] for item in ceo_navigation.get("data", {}).get("items", [])
    }
    assert {item["key"] for item in ceo_navigation["data"]["items"]} == {
        "commerce",
        "customers",
        "entities",
        "metrics",
        "quality",
    }
    assert ceo_navigation["data"]["href"] == "/console/data/commerce"
    assert {item["key"] for item in ceo_navigation["admin"]["items"]} == {
        "jobs",
        "config",
        "files",
    }
    assert employee.status_code == 200
    employee_payload = employee.json()
    assert employee_payload["navigation_sections"] == [
        "home",
        "cockpit",
        "data",
        "knowledge",
        "analysis",
        "actions",
    ]
    employee_navigation = {item["key"]: item for item in employee_payload["navigation"]}
    assert "assistant" in {item["key"] for item in employee_navigation["home"]["items"]}
    assert {item["key"] for item in employee_navigation["data"]["items"]} == {
        "commerce",
        "customers",
    }
    assert employee_navigation["data"]["href"] == "/console/data/commerce"
    assert "review-plans" in {item["key"] for item in employee_navigation["analysis"]["items"]}
    assert admin.status_code == 200
    admin_payload = admin.json()
    assert "admin" in admin_payload["navigation_sections"]
    assert "actions" in admin_payload["navigation_sections"]
    assert "meeting.decision.confirm" in admin_payload["actor"]["permissions"]
    assert "knowledge.document.ingest" in admin_payload["actor"]["permissions"]
    assert "memory.chat.ingest" in admin_payload["actor"]["permissions"]
    assert "memory.candidate.review" in admin_payload["actor"]["permissions"]
    assert "knowledge.policy.publish" in admin_payload["actor"]["permissions"]
    assert "evaluation.manage" in admin_payload["actor"]["permissions"]
    assert "analysis.read" in admin_payload["actor"]["permissions"]
    assert "analysis.run" in admin_payload["actor"]["permissions"]
    admin_navigation = {item["key"]: item for item in admin_payload["navigation"]}
    assert "actions" in admin_navigation
    assert {item["key"] for item in admin_navigation["admin"]["items"]} == {
        "users",
        "org",
        "access",
        "channels",
        "ai-runtime",
        "tools",
        "jobs",
        "config",
        "files",
        "exchange",
        "delegations",
        "audit",
    }
    assert admin_navigation["data"]["href"] == "/console/data/sources"


@pytest.mark.anyio
async def test_admin_overview_is_guarded_and_authorization_is_audited(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get(
            "/api/v1/identity/admin/overview",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        allowed = await client.get(
            "/api/v1/identity/admin/overview",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.permission_denied"
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["stats"]["active_users"] == 6
    assert payload["stats"]["org_units"] == 6
    assert payload["stats"]["positions"] == 6
    assert payload["stats"]["access_roles"] == 6
    assert payload["stats"]["permissions"] == 54
    assert payload["stats"]["authorization_decisions"] == 2
    assert payload["stats"]["denied_decisions"] == 1
    assert payload["stats"]["management_events"] == 0
    assert len(payload["users"]) == 6
    platform_admin = next(
        item for item in payload["access_roles"] if item["role_key"] == "platform-admin"
    )
    assert "identity.access.manage" in platform_admin["permissions"]
    assert "ai.provider.manage" in platform_admin["permissions"]
    assert "meeting.decision.confirm" in platform_admin["permissions"]

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(AuthorizationDecision.id))) == 2
        decisions = list(
            session.scalars(
                select(AuthorizationDecision).order_by(AuthorizationDecision.decided_at)
            )
        )
    assert [item.decision for item in decisions] == ["deny", "allow"]
    assert all(item.request_id.startswith("req_") for item in decisions)
    assert all(item.run_id.startswith("run_") for item in decisions)


@pytest.mark.anyio
async def test_governed_user_configuration_is_idempotent_versioned_and_audited(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    create_payload = {
        "schema_version": 1,
        "client_request_key": "identity-create-li-na-001",
        "login_name": "li.na",
        "display_name": "李娜 / 新零售运营",
        "email": "li.na@example.test",
        "experience_role_key": "employee",
        "org_key": "operations",
        "position_key": "operations-specialist",
        "status": "active",
        "role_assignments": [
            {
                "role_key": "employee",
                "scopes": [
                    {"scope_type": "self", "scope_ids": ["$self"], "effect": "allow"},
                    {
                        "scope_type": "store",
                        "scope_ids": ["store-outlet"],
                        "effect": "allow",
                    },
                ],
            }
        ],
        "reason": "新零售门店运营入职",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/api/v1/identity/admin/users",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json=create_payload,
        )
        created = await client.post(
            "/api/v1/identity/admin/users",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=create_payload,
        )
        replayed = await client.post(
            "/api/v1/identity/admin/users",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=create_payload,
        )
        identity = await client.get(
            "/api/v1/identity/me",
            headers={"X-Zhixing-Demo-Actor": "li.na"},
        )

        update_payload = {
            **{key: value for key, value in create_payload.items() if key != "login_name"},
            "client_request_key": "identity-configure-li-na-002",
            "expected_version": 1,
            "display_name": "李娜 / 客服运营",
            "experience_role_key": "service",
            "org_key": "customer-service",
            "position_key": "service-agent",
            "role_assignments": [
                {
                    "role_key": "service-agent",
                    "scopes": [
                        {
                            "scope_type": "business_unit",
                            "scope_ids": ["org_service"],
                            "effect": "allow",
                        }
                    ],
                }
            ],
            "reason": "转入客户服务中心",
        }
        updated = await client.put(
            "/api/v1/identity/admin/users/account_li_na/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=update_payload,
        )
        stale = await client.put(
            "/api/v1/identity/admin/users/account_li_na/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                **update_payload,
                "client_request_key": "identity-configure-li-na-stale",
                "display_name": "过期写入",
            },
        )
        suspended = await client.put(
            "/api/v1/identity/admin/users/account_li_na/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                **update_payload,
                "client_request_key": "identity-suspend-li-na-003",
                "expected_version": 2,
                "status": "suspended",
                "reason": "账号暂时停用",
            },
        )
        inactive_identity = await client.get(
            "/api/v1/identity/me",
            headers={"X-Zhixing-Demo-Actor": "li.na"},
        )
        overview = await client.get(
            "/api/v1/identity/admin/overview",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )

    assert denied.status_code == 403
    assert created.status_code == 201
    assert created.json()["account"]["version"] == 1
    assert created.json()["account"]["org_key"] == "operations"
    assert created.json()["account"]["role_assignments"][0]["role_key"] == "employee"
    assert replayed.status_code == 201
    assert replayed.json()["replayed"] is True
    assert replayed.json()["event_id"] == created.json()["event_id"]
    assert identity.status_code == 200
    self_scope = next(
        item for item in identity.json()["actor"]["scopes"] if item["scope_type"] == "self"
    )
    assert self_scope["scope_ids"] == [identity.json()["actor"]["principal_id"]]
    assert updated.status_code == 200, updated.text
    assert updated.json()["account"]["version"] == 2
    assert updated.json()["account"]["organization"] == "客户服务中心"
    assert updated.json()["account"]["access_roles"] == ["客服专员"]
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "identity.version_conflict"
    assert suspended.status_code == 200
    assert suspended.json()["account"]["version"] == 3
    assert inactive_identity.status_code == 401
    assert overview.status_code == 200
    assert overview.json()["stats"]["active_users"] == 6
    assert overview.json()["stats"]["management_events"] == 3
    assert overview.json()["recent_management_events"][0]["changed_fields"] == ["status"]

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(IdentityManagementEvent.id))) == 3


@pytest.mark.anyio
async def test_identity_management_rejects_conflicting_replay_and_self_lockout(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    payload = {
        "schema_version": 1,
        "client_request_key": "identity-create-conflict-001",
        "login_name": "new.manager",
        "display_name": "新经理",
        "email": None,
        "experience_role_key": "manager",
        "org_key": "operations",
        "position_key": "operations-manager",
        "status": "active",
        "role_assignments": [
            {
                "role_key": "operations-manager",
                "scopes": [
                    {
                        "scope_type": "org_subtree",
                        "scope_ids": ["org_operations"],
                        "effect": "allow",
                    }
                ],
            }
        ],
        "reason": "新增区域经理",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/identity/admin/users",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=payload,
        )
        conflicting_replay = await client.post(
            "/api/v1/identity/admin/users",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={**payload, "display_name": "另一个人"},
        )
        overview = await client.get(
            "/api/v1/identity/admin/overview",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )
        admin_user = next(
            item for item in overview.json()["users"] if item["account_key"] == "account_admin"
        )
        self_lockout = await client.put(
            "/api/v1/identity/admin/users/account_admin/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "schema_version": 1,
                "client_request_key": "identity-admin-lockout-001",
                "expected_version": admin_user["version"],
                "display_name": admin_user["display_name"],
                "email": admin_user["email"],
                "experience_role_key": admin_user["experience_role_key"],
                "org_key": admin_user["org_key"],
                "position_key": admin_user["position_key"],
                "status": "suspended",
                "role_assignments": [
                    {
                        "role_key": assignment["role_key"],
                        "scopes": assignment["scopes"],
                    }
                    for assignment in admin_user["role_assignments"]
                ],
                "reason": "尝试停用当前管理员",
            },
        )

    assert created.status_code == 201
    assert conflicting_replay.status_code == 409
    assert conflicting_replay.json()["error"]["code"] == "identity.idempotency_conflict"
    assert self_lockout.status_code == 409, self_lockout.text
    assert self_lockout.json()["error"]["code"] == "identity.self_lockout_denied"


@pytest.mark.anyio
async def test_identity_catalog_operations_are_versioned_idempotent_and_audited(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/api/v1/identity/admin/org-units",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={
                "client_request_key": "catalog-denied-001",
                "org_key": "sales",
                "name": "销售中心",
                "unit_type": "department",
                "reason": "权限测试",
            },
        )
        created_org = await client.post(
            "/api/v1/identity/admin/org-units",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "catalog-org-create-001",
                "org_key": "sales",
                "name": "销售中心",
                "unit_type": "department",
                "parent_org_key": "group",
                "reason": "新增销售组织",
            },
        )
        replay_org = await client.post(
            "/api/v1/identity/admin/org-units",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "catalog-org-create-001",
                "org_key": "sales",
                "name": "销售中心",
                "unit_type": "department",
                "parent_org_key": "group",
                "reason": "新增销售组织",
            },
        )
        overview = await client.get(
            "/api/v1/identity/admin/overview",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )
        sales = next(item for item in overview.json()["org_units"] if item["org_key"] == "sales")
        created_position = await client.post(
            "/api/v1/identity/admin/positions",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "catalog-position-create-001",
                "position_key": "sales-manager",
                "name": "销售经理",
                "position_level": "manager",
                "org_key": "sales",
                "reason": "新增销售岗位",
            },
        )
        created_role = await client.post(
            "/api/v1/identity/admin/access-roles",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "catalog-role-create-001",
                "role_key": "sales-analyst",
                "name": "销售分析员",
                "description": "销售范围经营分析",
                "permissions": ["platform.navigation.read", "analysis.read"],
                "reason": "新增销售访问角色",
            },
        )
        updated_role = await client.put(
            "/api/v1/identity/admin/access-roles/sales-analyst",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "catalog-role-update-001",
                "expected_revision": 1,
                "name": "销售经营分析员",
                "description": "销售范围经营分析与客户画像",
                "status": "active",
                "permissions": [
                    "platform.navigation.read",
                    "analysis.read",
                    "customer.profile.read",
                ],
                "reason": "扩展客户分析能力",
            },
        )
        self_lockout_role = await client.put(
            "/api/v1/identity/admin/access-roles/platform-admin",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "catalog-role-self-lockout-001",
                "expected_revision": 1,
                "name": "平台管理员",
                "description": "尝试移除自身管理能力",
                "status": "active",
                "permissions": ["platform.navigation.read"],
                "reason": "自锁保护测试",
            },
        )
        stale_role = await client.put(
            "/api/v1/identity/admin/access-roles/sales-analyst",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "catalog-role-update-stale",
                "expected_revision": 1,
                "name": "过期角色",
                "description": "过期写入",
                "status": "active",
                "permissions": ["analysis.read"],
                "reason": "并发冲突测试",
            },
        )
        updated_org = await client.put(
            "/api/v1/identity/admin/org-units/sales",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "catalog-org-update-001",
                "expected_version": sales["version"],
                "name": "销售与增长中心",
                "unit_type": "department",
                "parent_org_key": "group",
                "status": "active",
                "reason": "组织名称升级",
            },
        )

    assert denied.status_code == 403
    assert created_org.status_code == 201
    assert replay_org.status_code == 201
    assert replay_org.json()["replayed"] is True
    assert replay_org.json()["event_id"] == created_org.json()["event_id"]
    assert created_position.status_code == 201
    assert created_role.status_code == 201
    assert updated_role.status_code == 200
    assert self_lockout_role.status_code == 409
    assert self_lockout_role.json()["error"]["code"] == "identity.self_lockout_denied"
    assert stale_role.status_code == 409
    assert stale_role.json()["error"]["code"] == "identity.access_role_version_conflict"
    assert updated_org.status_code == 200

    with app.state.database.session() as session:
        from zhixing_api.data_models import IdentityCatalogEvent

        assert session.scalar(select(func.count(IdentityCatalogEvent.id))) == 5
