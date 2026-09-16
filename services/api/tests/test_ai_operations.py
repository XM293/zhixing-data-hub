import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from zhixing_codex_runtime import CodexRuntimeProbe

from zhixing_api.ai_provider import AICompletion, AIProviderError
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    AgentRuntimeProbeRun,
    AIProviderProbeRun,
    RoleTwinProfile,
)
from zhixing_api.main import create_app


def make_settings(tmp_path: Path, *, ai_enabled: bool = True) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://test",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'ai-operations.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:9",
        ai_enabled=ai_enabled,
        ai_base_url="https://private-provider.invalid/v1",
        ai_api_key="test-only-key",
        ai_model="test-model",
        ai_timeout_seconds=10,
        agent_runtime_enabled=True,
        codex_command=sys.executable,
    )


@pytest.mark.anyio
async def test_ai_operations_overview_is_admin_only_and_aggregates_runs(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    now = datetime.now(UTC)
    with app.state.database.session() as session:
        profile = session.scalar(select(RoleTwinProfile).order_by(RoleTwinProfile.id))
        assert profile is not None
        session.add_all(
            [
                AgentRun(
                    id="agent_run_ai_ops_model",
                    enterprise_id=profile.enterprise_id,
                    actor_principal_id=None,
                    twin_profile_id=profile.id,
                    role_twin_version_id=None,
                    meeting_id=None,
                    run_type="answer",
                    phase=None,
                    question="test",
                    answer="test",
                    answer_payload={},
                    status="completed",
                    provider="openai-compatible-responses",
                    model="test-model",
                    fallback_reason=None,
                    duration_ms=1200,
                    input_tokens=100,
                    output_tokens=40,
                    created_at=now,
                ),
                AgentRun(
                    id="agent_run_ai_ops_degraded",
                    enterprise_id=profile.enterprise_id,
                    actor_principal_id=None,
                    twin_profile_id=profile.id,
                    role_twin_version_id=None,
                    meeting_id=None,
                    run_type="meeting",
                    phase=None,
                    question="test",
                    answer="test",
                    answer_payload={},
                    status="degraded",
                    provider="local-evidence",
                    model="deterministic-v1",
                    fallback_reason="provider unavailable",
                    duration_ms=300,
                    input_tokens=None,
                    output_tokens=None,
                    created_at=now - timedelta(minutes=10),
                ),
            ]
        )
        session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get(
            "/api/v1/ai-operations/overview",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )
        allowed = await client.get(
            "/api/v1/ai-operations/overview",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.permission_denied"
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["provider"] == {
        "provider_key": "openai-compatible-responses",
        "label": "OpenAI 兼容 Responses Provider",
        "protocol": "responses-v1",
        "endpoint_kind": "private-compatible",
        "enabled": True,
        "configured": True,
        "model": "test-model",
        "timeout_seconds": 10.0,
        "capabilities": ["responses", "json-schema", "usage-tokens", "no-store"],
    }
    assert payload["runtime"] == {
        "runtime_key": "codex-app-server",
        "label": "Codex 开源 Harness",
        "protocol": "app-server-json-rpc-v2",
        "enabled": True,
        "command_available": True,
        "model": None,
        "timeout_seconds": 20.0,
        "capabilities": ["start", "resume", "stream", "cancel", "mcp", "approvals"],
        "default_sandbox": "read-only",
        "approval_policy": "fail-closed",
    }
    assert payload["stats"]["total_runs"] == 2
    assert payload["stats"]["successful_runs"] == 1
    assert payload["stats"]["degraded_runs"] == 1
    assert payload["stats"]["input_tokens"] == 100
    assert payload["stats"]["output_tokens"] == 40
    assert payload["stats"]["token_coverage_rate"] == 0.5
    assert {item["run_type"] for item in payload["run_types"]} >= {"answer", "meeting"}
    serialized = allowed.text.casefold()
    assert "private-provider.invalid" not in serialized
    assert "test-only-key" not in serialized


@pytest.mark.anyio
async def test_provider_probe_persists_success_and_redacts_failure(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))

    class SuccessfulProvider:
        async def generate(self, *_args: object, **_kwargs: object) -> AICompletion:
            return AICompletion(
                payload={"status": "ok", "message": "responses ready"},
                input_tokens=18,
                output_tokens=7,
                structured_output=True,
            )

    app.state.ai_provider = SuccessfulProvider()
    admin = {"X-Zhixing-Demo-Actor": "admin"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        succeeded = await client.post(
            "/api/v1/ai-operations/probes",
            headers=admin,
            json={"model": "test-model-probe"},
        )
    assert succeeded.status_code == 200
    succeeded_payload = succeeded.json()
    assert succeeded_payload["status"] == "succeeded"
    assert succeeded_payload["structured_output_supported"] is True
    assert succeeded_payload["input_tokens"] == 18
    assert succeeded_payload["actor_name"] == "叶川 / 平台管理员"

    class FailingProvider:
        async def generate(self, *_args: object, **_kwargs: object) -> AICompletion:
            raise AIProviderError(
                "request failed at https://private-provider.invalid/v1 with token_testsecret123"
            )

    app.state.ai_provider = FailingProvider()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        failed = await client.post(
            "/api/v1/ai-operations/probes",
            headers=admin,
            json={},
        )
        overview = await client.get("/api/v1/ai-operations/overview", headers=admin)

    assert failed.status_code == 200
    failed_payload = failed.json()
    assert failed_payload["status"] == "failed"
    assert failed_payload["error_code"] == "provider_probe_failed"
    assert "private-provider.invalid" not in failed_payload["error_message"]
    assert "testsecret123" not in failed_payload["error_message"]
    assert overview.status_code == 200
    assert overview.json()["stats"]["probe_runs"] == 2
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(AIProviderProbeRun.id))) == 2
        saved = list(
            session.scalars(
                select(AIProviderProbeRun).order_by(AIProviderProbeRun.created_at)
            )
        )
        assert saved[0].model == "test-model-probe"
        assert "private-provider.invalid" not in (saved[1].error_message or "")
        assert "testsecret123" not in (saved[1].error_message or "")


@pytest.mark.anyio
async def test_agent_runtime_probe_persists_app_server_handshake(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))

    class SuccessfulRuntime:
        async def probe(self) -> CodexRuntimeProbe:
            return CodexRuntimeProbe(
                available=True,
                initialized=True,
                command="codex",
                version="codex-cli 0.test",
            )

    app.state.agent_runtime = SuccessfulRuntime()
    admin = {"X-Zhixing-Demo-Actor": "admin"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/ai-operations/runtime-probes", headers=admin)
        overview = await client.get("/api/v1/ai-operations/overview", headers=admin)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["initialized"] is True
    assert payload["command_version"] == "codex-cli 0.test"
    assert overview.status_code == 200
    assert overview.json()["runtime_probes"][0]["id"] == payload["id"]
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(AgentRuntimeProbeRun.id))) == 1
