from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    AuthorizationDecision,
    MCPGatewaySession,
    MCPGatewaySessionEvent,
    RoleAssignment,
    RoleTwinProfile,
    ScopeGrant,
    ToolInvocation,
    UserAccount,
)
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://test",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'tools_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


def gateway_headers(session_token: str, client_id: str = "codex-test") -> dict[str, str]:
    return {
        "X-Zhixing-MCP-Session": session_token,
        "X-Zhixing-MCP-Client-ID": client_id,
        "X-Request-ID": "req_mcp_test1234567890",
        "X-Run-ID": "run_mcp_test1234567890",
    }


@pytest.mark.anyio
async def test_tool_catalog_and_invocations_use_database_actor_context(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        catalog = await client.get(
            "/api/v1/tools/catalog",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        search = await client.post(
            "/api/v1/tools/search_knowledge/invoke",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={"parameters": {"query": "退款率绩效权重", "limit": 3}},
        )
        policy = await client.post(
            "/api/v1/tools/read_policy/invoke",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={
                "parameters": {
                    "query": "退款率绩效权重",
                    "policy_key": "policy-commerce-kpi",
                    "limit": 4,
                }
            },
        )

    assert catalog.status_code == 200
    assert {item["key"] for item in catalog.json()["items"]} == {
        "get_metric",
        "query_commerce_facts",
        "query_customer_360",
        "read_policy",
        "search_knowledge",
    }
    assert all(item["risk_level"] == "R0" for item in catalog.json()["items"])
    metric_tool = next(item for item in catalog.json()["items"] if item["key"] == "get_metric")
    assert metric_tool["version"] == "1.1.0"
    assert metric_tool["input_schema"]["properties"]["days"]["maximum"] == 365

    assert search.status_code == 200
    search_payload = search.json()
    assert search_payload["actor_key"] == "principal-employee-demo"
    assert search_payload["status"] == "succeeded"
    assert search_payload["output"]["items"]
    assert search_payload["request_id"].startswith("req_")
    assert search_payload["run_id"].startswith("run_")

    assert policy.status_code == 200
    assert policy.json()["output"]["policy_key"] == "policy-commerce-kpi"
    assert {
        item["document_key"] for item in policy.json()["output"]["items"]
    } == {"policy-commerce-kpi"}

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(ToolInvocation.id))) == 2
        assert session.scalar(
            select(func.count(AuthorizationDecision.id)).where(
                AuthorizationDecision.permission_key == "knowledge.document.read",
                AuthorizationDecision.decision == "allow",
            )
        ) == 2


@pytest.mark.anyio
async def test_tool_gateway_rejects_forged_actor_and_out_of_scope_metric(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        forged = await client.post(
            "/api/v1/tools/search_knowledge/invoke",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={
                "parameters": {
                    "query": "广告预算",
                    "principal_id": "principal-ceo-lin",
                }
            },
        )
        denied = await client.post(
            "/api/v1/tools/get_metric/invoke",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={
                "parameters": {
                    "metric_key": "gmv_today",
                    "scope_key": "enterprise",
                }
            },
        )
        allowed = await client.post(
            "/api/v1/tools/get_metric/invoke",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={
                "parameters": {
                    "metric_key": "gmv_today",
                    "scope_key": "enterprise",
                    "days": 30,
                }
            },
        )

    assert forged.status_code == 422
    assert forged.json()["error"]["code"] == "tool.input_invalid"
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.scope_denied"
    assert allowed.status_code == 200
    assert allowed.json()["output"]["scope_key"] == "enterprise"
    assert allowed.json()["output"]["time_range"]["days"] == 30
    assert allowed.json()["output"]["items"][0]["key"] == "gmv_today"

    with app.state.database.session() as session:
        statuses = dict(
            session.execute(
                select(ToolInvocation.status, func.count(ToolInvocation.id)).group_by(
                    ToolInvocation.status
                )
            ).all()
        )
    assert statuses == {"denied": 1, "failed": 1, "succeeded": 1}


@pytest.mark.anyio
async def test_tool_admin_overview_is_guarded_and_summarizes_runs(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        employee = await client.get(
            "/api/v1/tools/admin/overview",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        await client.post(
            "/api/v1/tools/search_knowledge/invoke",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"parameters": {"query": "库存预警", "limit": 2}},
        )
        admin = await client.get(
            "/api/v1/tools/admin/overview",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )

    assert employee.status_code == 403
    assert admin.status_code == 200
    payload = admin.json()
    assert payload["stats"]["active_tools"] == 5
    assert payload["stats"]["r0_tools"] == 5
    assert payload["stats"]["invocations"] == 1
    assert payload["stats"]["succeeded"] == 1
    assert len(payload["recent_invocations"]) == 1
    assert payload["recent_invocations"][0]["permission_key"] == "knowledge.document.read"


@pytest.mark.anyio
async def test_mcp_session_limits_tools_scopes_and_agent_run_then_revokes(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    with app.state.database.session() as session:
        employee = session.scalar(
            select(UserAccount).where(UserAccount.local_login_name == "employee")
        )
        profile = session.scalar(select(RoleTwinProfile).order_by(RoleTwinProfile.id))
        assert employee is not None
        assert profile is not None
        session.add(
            AgentRun(
                id="agent_run_mcp_session_test",
                enterprise_id=employee.enterprise_id,
                actor_principal_id=employee.principal_id,
                twin_profile_id=profile.id,
                role_twin_version_id=None,
                meeting_id=None,
                run_type="answer",
                phase=None,
                question="MCP session test",
                answer="ready",
                answer_payload={},
                status="succeeded",
                provider="fake",
                model="fake",
                fallback_reason=None,
                duration_ms=1,
                input_tokens=None,
                output_tokens=None,
                created_at=datetime.now(UTC),
            )
        )
        session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/mcp/sessions",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={
                "client_id": "codex-test",
                "allowed_tool_keys": ["get_metric", "search_knowledge"],
                "scope_constraints": [
                    {"scope_type": "store", "scope_ids": ["store-flagship"]}
                ],
                "ttl_seconds": 900,
                "agent_run_id": "agent_run_mcp_session_test",
            },
        )
        assert created.status_code == 200
        session_token = created.json()["session_token"]
        session_id = created.json()["session"]["session_id"]
        headers = gateway_headers(session_token)
        catalog = await client.get("/api/v1/tools/catalog", headers=headers)
        allowed = await client.post(
            "/api/v1/tools/get_metric/invoke",
            headers=headers,
            json={"parameters": {"metric_key": "gmv_today", "scope_key": "store-flagship"}},
        )
        undeclared = await client.post(
            "/api/v1/tools/query_commerce_facts/invoke",
            headers=headers,
            json={"parameters": {"scope_key": "store-flagship"}},
        )
        over_scope = await client.post(
            "/api/v1/tools/get_metric/invoke",
            headers=headers,
            json={"parameters": {"metric_key": "gmv_today", "scope_key": "enterprise"}},
        )
        listed = await client.get(
            "/api/v1/mcp/sessions",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        revoked = await client.post(
            f"/api/v1/mcp/sessions/{session_id}/revoke",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={"reason": "测试完成后撤销"},
        )
        reused = await client.get("/api/v1/tools/catalog", headers=headers)

    assert {item["key"] for item in catalog.json()["items"]} == {
        "get_metric",
        "search_knowledge",
    }
    assert allowed.status_code == 200
    assert allowed.json()["authentication_method"] == "mcp-session"
    assert allowed.json()["gateway_session_id"] == session_id
    assert allowed.json()["agent_run_id"] == "agent_run_mcp_session_test"
    assert undeclared.status_code == 403
    assert undeclared.json()["error"]["code"] == "mcp.tool_not_allowed"
    assert over_scope.status_code == 403
    assert over_scope.json()["error"]["code"] == "authorization.scope_denied"
    assert listed.status_code == 200
    assert listed.json()["items"][0]["last_seen_at"] is not None
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "mcp.session_invalid"

    with app.state.database.session() as session:
        stored = session.get(MCPGatewaySession, session_id)
        assert stored is not None
        assert stored.session_token_hash == sha256(session_token.encode()).hexdigest()
        assert stored.session_token_hash != session_token
        assert stored.actor_snapshot["principal_id"] == stored.principal_id
        assert stored.allowed_tool_keys == ["get_metric", "search_knowledge"]
        assert stored.agent_run_id == "agent_run_mcp_session_test"
        assert session.scalar(
            select(func.count(MCPGatewaySessionEvent.id)).where(
                MCPGatewaySessionEvent.gateway_session_id == session_id
            )
        ) == 2
        invocations = list(
            session.scalars(
                select(ToolInvocation)
                .where(ToolInvocation.gateway_session_id == session_id)
                .order_by(ToolInvocation.started_at)
            )
        )
        assert [item.status for item in invocations] == ["succeeded", "denied", "denied"]
        assert all(item.authentication_method == "mcp-session" for item in invocations)
        assert all(item.agent_run_id == "agent_run_mcp_session_test" for item in invocations)


@pytest.mark.anyio
async def test_mcp_session_reauthorizes_current_scope_after_issue(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/mcp/sessions",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json={
                "client_id": "codex-manager",
                "allowed_tool_keys": ["get_metric"],
                "scope_constraints": [
                    {"scope_type": "store", "scope_ids": ["store-flagship"]}
                ],
                "ttl_seconds": 900,
            },
        )
        assert created.status_code == 200
        session_token = created.json()["session_token"]
        session_id = created.json()["session"]["session_id"]
        issued_version = created.json()["session"]["issued_permission_set_version"]

        with app.state.database.session() as session:
            manager = session.scalar(
                select(UserAccount).where(UserAccount.local_login_name == "manager")
            )
            assert manager is not None
            assignment_ids = list(
                session.scalars(
                    select(RoleAssignment.id).where(
                        RoleAssignment.principal_id == manager.principal_id
                    )
                )
            )
            store_grant = session.scalar(
                select(ScopeGrant).where(
                    ScopeGrant.role_assignment_id.in_(assignment_ids),
                    ScopeGrant.scope_type == "store",
                )
            )
            assert store_grant is not None
            store_grant.scope_ids = ["store-outlet"]
            session.commit()

        denied = await client.post(
            "/api/v1/tools/get_metric/invoke",
            headers=gateway_headers(session_token, "codex-manager"),
            json={"parameters": {"metric_key": "gmv_today", "scope_key": "store-flagship"}},
        )
        listed = await client.get(
            "/api/v1/mcp/sessions",
            headers={"X-Zhixing-Demo-Actor": "manager"},
        )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.scope_denied"
    session_view = next(item for item in listed.json()["items"] if item["session_id"] == session_id)
    assert session_view["permission_set_version_changed"] is True
    assert session_view["current_permission_set_version"] != issued_version
    with app.state.database.session() as session:
        invocation = session.scalar(
            select(ToolInvocation).where(ToolInvocation.gateway_session_id == session_id)
        )
        assert invocation is not None
        assert invocation.status == "denied"
        assert invocation.session_permission_set_version == issued_version
        assert invocation.permission_set_version != issued_version
