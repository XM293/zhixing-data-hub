from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from zhixing_jobs.models import BackgroundJob

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    ActionProposal,
    ActionWorkEvent,
    ActionWorkItem,
    AgentRun,
    AuthorizationDecision,
    Enterprise,
    MCPGatewaySession,
    MCPGatewaySessionEvent,
    Principal,
    RoleTwinProfile,
    ToolDefinition,
    ToolInvocation,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.main import create_app

ADMIN_HEADERS = {"X-Zhixing-Demo-Actor": "admin"}
EMPLOYEE_HEADERS = {"X-Zhixing-Demo-Actor": "employee"}
EXPECTED_SOURCES = {
    "authorization",
    "identity",
    "mcp",
    "tool",
    "worker",
    "agent",
    "action",
}
SENSITIVE_MARKER = "audit-sensitive-marker-9f347f"


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'audit_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


def identity_event_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "client_request_key": "audit-create-user-001",
        "login_name": "audit.reader",
        "display_name": "审计测试账号",
        "email": "audit.reader@example.test",
        "experience_role_key": "employee",
        "org_key": "operations",
        "position_key": "operations-specialist",
        "status": "active",
        "role_assignments": [
            {
                "role_key": "employee",
                "scopes": [{"scope_type": "self", "scope_ids": ["$self"], "effect": "allow"}],
            }
        ],
        "reason": "审计链路测试",
    }


def seed_audit_facts(database: Database) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        principal = session.get(Principal, "principal-platform-admin")
        account = session.get(UserAccount, "account_admin")
        tool = session.scalar(select(ToolDefinition).limit(1))
        assert principal is not None
        assert account is not None
        assert tool is not None

        twin = RoleTwinProfile(
            id="twin_audit_test",
            enterprise_id="ent_zhixing_demo",
            role_template_id=None,
            owner_principal_id=principal.id,
            twin_key="audit-test",
            display_name="审计测试分身",
            role_title="审计测试",
            voice_guide="",
            reasoning_guide="",
            answer_policy="",
            provider="test",
            model="test-model",
            status="published",
            published_at=now,
            updated_at=now,
        )
        agent_run = AgentRun(
            id="agent_run_audit_test",
            enterprise_id="ent_zhixing_demo",
            actor_principal_id=principal.id,
            twin_profile_id=twin.id,
            role_twin_version_id=None,
            meeting_id=None,
            run_type="answer",
            phase="complete",
            question=SENSITIVE_MARKER,
            answer=SENSITIVE_MARKER,
            answer_payload={"details": SENSITIVE_MARKER},
            status="completed",
            provider="test",
            model="test-model",
            fallback_reason=None,
            duration_ms=120,
            input_tokens=10,
            output_tokens=20,
            created_at=now,
        )
        gateway = MCPGatewaySession(
            id="mcp_session_audit_test",
            enterprise_id="ent_zhixing_demo",
            user_account_id=account.id,
            principal_id=principal.id,
            client_id="audit-test-client",
            session_token_hash=SENSITIVE_MARKER,
            allowed_tool_keys=[tool.tool_key],
            scope_constraints=[{"scope_type": "enterprise", "scope_ids": ["ent_zhixing_demo"]}],
            issued_permission_set_version="audit-test-v1",
            actor_snapshot={"cookie": SENSITIVE_MARKER},
            agent_run_id=agent_run.id,
            status="active",
            issued_at=now,
            expires_at=now + timedelta(minutes=10),
            last_seen_at=None,
            revoked_at=None,
            revoked_by_principal_id=None,
            revoke_reason=None,
            request_id="req_audit_mcp",
            run_id="run_audit_shared",
        )
        gateway_event = MCPGatewaySessionEvent(
            id="mcp_event_audit_test",
            enterprise_id="ent_zhixing_demo",
            gateway_session_id=gateway.id,
            actor_principal_id=principal.id,
            event_type="issued",
            reason="trusted_mcp_session_issued",
            permission_set_version="audit-test-v1",
            request_id="req_audit_mcp",
            run_id="run_audit_shared",
            occurred_at=now,
        )
        invocation = ToolInvocation(
            id="tool_invocation_audit_test",
            enterprise_id="ent_zhixing_demo",
            tool_definition_id=tool.id,
            tool_key=tool.tool_key,
            tool_version=tool.version,
            actor_principal_id=principal.id,
            actor_snapshot={"authorization": SENSITIVE_MARKER},
            gateway_session_id=gateway.id,
            agent_run_id=agent_run.id,
            authentication_method="mcp_session",
            permission_set_version="audit-test-v1",
            session_permission_set_version="audit-test-v1",
            request_id="req_audit_tool",
            run_id="run_audit_shared",
            input_parameters={"prompt": SENSITIVE_MARKER},
            output_summary={"customer": SENSITIVE_MARKER},
            status="succeeded",
            error_code=None,
            duration_ms=85,
            started_at=now,
            finished_at=now,
        )
        job = BackgroundJob(
            id="job_audit_test",
            enterprise_id="ent_zhixing_demo",
            job_type="analysis.daily-store-review",
            payload={"token": SENSITIVE_MARKER},
            status="failed",
            priority=10,
            attempt=1,
            max_attempts=3,
            timeout_seconds=30,
            available_at=now,
            claimed_at=now,
            heartbeat_at=now,
            lease_expires_at=None,
            started_at=now,
            finished_at=now,
            idempotency_key="audit-job-001",
            initiator_type="principal",
            initiator_id=principal.id,
            actor_snapshot={"cookie": SENSITIVE_MARKER},
            permission_set_version="audit-test-v1",
            required_permissions=["analysis.run"],
            scope_type="enterprise",
            scope_id="ent_zhixing_demo",
            execution_token_hash=None,
            request_id="req_audit_job",
            run_id="run_audit_shared",
            worker_id="audit-worker",
            result={"details": SENSITIVE_MARKER},
            last_error_code="job.audit_test_failed",
            last_error_message=SENSITIVE_MARKER,
            created_at=now,
            updated_at=now,
        )
        proposal = ActionProposal(
            id="action_proposal_audit_test",
            enterprise_id="ent_zhixing_demo",
            proposal_key="audit-proposal-001",
            source_type="internal",
            source_key="audit-source-001",
            source_label="审计测试来源",
            scope_type="enterprise",
            scope_key="ent_zhixing_demo",
            meeting_id=None,
            decision_package_id=None,
            customer_operation_run_id=None,
            business_analysis_run_id=None,
            evidence_snapshot_id=None,
            source_action_index=0,
            title="审计测试工作",
            owner="平台管理员",
            due_hint="当日",
            kpi="完成",
            stop_condition="异常停止",
            evidence_refs=[],
            target_system="internal",
            target_key="audit-target-001",
            risk_level="R0",
            action_level="R0",
            parameters={},
            status="approved",
            requested_by_actor_key=principal.principal_key,
            requested_by_name=principal.display_name,
            idempotency_key="audit-proposal-001",
            approved_by_actor_key=principal.principal_key,
            approved_by_name=principal.display_name,
            approved_at=now,
            decision_comment=None,
            created_at=now,
            updated_at=now,
        )
        work_item = ActionWorkItem(
            id="action_work_audit_test",
            enterprise_id="ent_zhixing_demo",
            work_key="audit-work-001",
            proposal_id=proposal.id,
            scope_type="enterprise",
            scope_key="ent_zhixing_demo",
            status="completed",
            assignee_principal_id=principal.id,
            assignee_name=principal.display_name,
            owner_role="平台管理员",
            title="审计测试工作",
            due_hint="当日",
            kpi="完成",
            stop_condition="异常停止",
            priority="normal",
            version=1,
            claimed_at=now,
            started_at=now,
            blocked_at=None,
            completed_at=now,
            blocker_reason=None,
            result_summary=SENSITIVE_MARKER,
            result_evidence_refs=[],
            created_at=now,
            updated_at=now,
        )
        work_event = ActionWorkEvent(
            id="action_event_audit_test",
            enterprise_id="ent_zhixing_demo",
            work_item_id=work_item.id,
            actor_principal_id=principal.id,
            actor_name=principal.display_name,
            event_type="completed",
            from_status="in_progress",
            to_status="completed",
            comment=SENSITIVE_MARKER,
            evidence_refs=[],
            idempotency_key="audit-action-event-001",
            actor_snapshot={"cookie": SENSITIVE_MARKER},
            created_at=now,
        )
        session.add_all(
            [
                twin,
                agent_run,
                gateway,
                gateway_event,
                invocation,
                job,
                proposal,
                work_item,
                work_event,
            ]
        )
        session.commit()


@pytest.mark.anyio
async def test_audit_ledger_is_guarded_and_normalizes_all_sources(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get("/api/v1/audit/events", headers=EMPLOYEE_HEADERS)
        created = await client.post(
            "/api/v1/identity/admin/users",
            headers=ADMIN_HEADERS,
            json=identity_event_payload(),
        )
        seed_audit_facts(app.state.database)
        ledger = await client.get(
            "/api/v1/audit/events?limit=100",
            headers=ADMIN_HEADERS,
        )

        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "authorization.permission_denied"
        assert created.status_code == 201
        assert ledger.status_code == 200

        payload = ledger.json()
        assert payload["schema_version"] == 1
        assert payload["enterprise_id"] == "ent_zhixing_demo"
        assert {item["key"] for item in payload["facets"]["sources"]} == EXPECTED_SOURCES
        assert payload["pagination"]["limit"] == 100
        assert payload["stats"]["total_events"] >= len(payload["items"])

        for source in EXPECTED_SOURCES:
            response = await client.get(
                "/api/v1/audit/events",
                headers=ADMIN_HEADERS,
                params={"source": source, "limit": 1},
            )
            assert response.status_code == 200
            source_payload = response.json()
            assert source_payload["pagination"]["total"] >= 1
            assert source_payload["items"][0]["source"] == source


@pytest.mark.anyio
async def test_audit_filters_pagination_and_actor_facets_are_stable(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get("/api/v1/audit/events", headers=EMPLOYEE_HEADERS)
        assert denied.status_code == 403
        initial = await client.get(
            "/api/v1/audit/events",
            headers=ADMIN_HEADERS,
            params={"source": "authorization", "limit": 1},
        )
        assert initial.status_code == 200
        first_payload = initial.json()
        event = first_payload["items"][0]

        filtered = await client.get(
            "/api/v1/audit/events",
            headers=ADMIN_HEADERS,
            params={
                "source": "authorization",
                "outcome": event["outcome"],
                "actor_principal_id": event["actor_principal_id"],
                "request_id": event["request_id"],
                "run_id": event["run_id"],
                "query": event["subject_key"],
                "limit": 10,
            },
        )
        second_page = await client.get(
            "/api/v1/audit/events",
            headers=ADMIN_HEADERS,
            params={"source": "authorization", "offset": 1, "limit": 1},
        )
        actor_filter = await client.get(
            "/api/v1/audit/events",
            headers=ADMIN_HEADERS,
            params={
                "source": "authorization",
                "actor_principal_id": event["actor_principal_id"],
                "limit": 1,
            },
        )
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        empty_time_window = await client.get(
            "/api/v1/audit/events",
            headers=ADMIN_HEADERS,
            params={"start_at": future},
        )

    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert filtered_payload["pagination"]["total"] == 1
    assert filtered_payload["items"][0]["id"] == event["id"]
    assert actor_filter.status_code == 200
    assert len(actor_filter.json()["facets"]["actors"]) >= 2
    assert second_page.status_code == 200
    assert second_page.json()["pagination"]["offset"] == 1
    assert second_page.json()["pagination"]["has_more"] == (
        second_page.json()["pagination"]["total"] > 2
    )
    assert empty_time_window.status_code == 200
    assert empty_time_window.json()["pagination"]["total"] == 0


@pytest.mark.anyio
async def test_audit_response_is_enterprise_isolated_and_omits_sensitive_payloads(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    now = datetime.now(UTC)
    seed_audit_facts(app.state.database)
    with app.state.database.session() as session:
        agent_run = session.scalar(select(AgentRun).limit(1))
        background_job = session.scalar(select(BackgroundJob).limit(1))
        work_event = session.scalar(select(ActionWorkEvent).limit(1))
        assert agent_run is not None
        assert background_job is not None
        assert work_event is not None
        agent_run.created_at = now
        background_job.created_at = now
        work_event.created_at = now
        session.add(
            Enterprise(
                id="ent_audit_isolated",
                code="audit-isolated",
                name="隔离企业",
                timezone="Asia/Shanghai",
                created_at=now,
            )
        )
        session.add(
            Principal(
                id="principal_audit_isolated",
                enterprise_id="ent_audit_isolated",
                principal_key="isolated-admin",
                principal_type="user",
                display_name="隔离管理员",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            AuthorizationDecision(
                id="authz_audit_isolated",
                enterprise_id="ent_audit_isolated",
                request_id="req_audit_isolated",
                run_id="run_audit_isolated",
                actor_principal_id="principal_audit_isolated",
                permission_key="audit.event.read",
                resource_type="audit-ledger",
                resource_key=SENSITIVE_MARKER,
                decision="allow",
                reason=SENSITIVE_MARKER,
                policy_version="isolated-v1",
                scope_snapshot=[{"token": SENSITIVE_MARKER}],
                decided_at=now,
            )
        )
        session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ledger = await client.get(
            "/api/v1/audit/events?limit=100",
            headers=ADMIN_HEADERS,
        )
        isolated_search = await client.get(
            "/api/v1/audit/events",
            headers=ADMIN_HEADERS,
            params={"query": SENSITIVE_MARKER},
        )

    assert ledger.status_code == 200
    response_text = ledger.text
    assert SENSITIVE_MARKER not in response_text
    for forbidden_key in (
        "actor_snapshot",
        "answer_payload",
        "before_snapshot",
        "comment",
        "details",
        "input_parameters",
        "last_error_message",
        "output_summary",
        "payload",
        "question",
        "scope_snapshot",
        "session_token_hash",
    ):
        assert f'"{forbidden_key}"' not in response_text
    assert isolated_search.status_code == 200
    assert isolated_search.json()["pagination"]["total"] == 0


@pytest.mark.anyio
async def test_audit_rejects_invalid_time_ranges_and_page_sizes(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        invalid_range = await client.get(
            "/api/v1/audit/events",
            headers=ADMIN_HEADERS,
            params={
                "start_at": "2026-08-31T00:00:00Z",
                "end_at": "2026-08-30T00:00:00Z",
            },
        )
        invalid_limit = await client.get(
            "/api/v1/audit/events?limit=101",
            headers=ADMIN_HEADERS,
        )

    assert invalid_range.status_code == 422
    assert invalid_range.json()["error"]["code"] == "audit.time_range_invalid"
    assert invalid_limit.status_code == 422
