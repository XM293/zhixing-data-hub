from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    MemoryProviderEvaluationResult,
    MemoryProviderEvaluationRun,
)
from zhixing_api.main import create_app
from zhixing_api.memory_providers import ProviderHit, ProviderMemory


class FakeMemoryProvider:
    key = "tencentdb-agent-memory"
    label = "TencentDB Agent Memory"
    protocol = "gateway-v3"
    mode = "test-double"
    endpoint_fingerprint = "fake-tdai"
    authentication_configured = False

    def __init__(self, key: str = "tencentdb-agent-memory") -> None:
        self.key = key
        self.label = "Mem0" if key == "mem0" else "TencentDB Agent Memory"
        self.protocol = "self-hosted-http-v1" if key == "mem0" else "gateway-v3"
        self.memories: dict[str, list[ProviderMemory]] = {}

    async def health(self) -> None:
        return None

    async def index_memories(
        self,
        namespace: str,
        memories: list[ProviderMemory],
    ) -> int:
        self.memories[namespace] = memories
        return len(memories)

    async def search(
        self,
        namespace: str,
        query: str,
        *,
        top_k: int,
    ) -> list[ProviderHit]:
        category = (
            "communication-style"
            if "管理汇报" in query
            else "decision-rule"
            if "新建议" in query
            else "risk-rule"
            if "财务评审" in query
            else "operating-rule"
            if "运营试验" in query
            else "service-rule"
        )
        selected = [item for item in self.memories[namespace] if item.category == category]
        return [
            ProviderHit(
                provider_id=f"{self.key}:{item.memory_key}",
                memory_key=item.memory_key,
                content=item.content,
                score=0.93,
            )
            for item in selected[:top_k]
        ]


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'memory_provider_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


@pytest.mark.anyio
async def test_memory_provider_dual_run_is_scoped_audited_and_idempotent(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    app.state.memory_providers = {
        "tencentdb-agent-memory": FakeMemoryProvider(),
        "mem0": FakeMemoryProvider("mem0"),
    }
    request_payload = {
        "schema_version": 1,
        "client_request_key": "memory-provider-test-001",
        "provider_keys": ["tencentdb-agent-memory", "mem0"],
        "top_k": 3,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        catalog = await client.get(
            "/api/v1/memories/provider-operations",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )
        denied = await client.post(
            "/api/v1/memories/provider-evaluations",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json=request_payload,
        )
        created = await client.post(
            "/api/v1/memories/provider-evaluations",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json=request_payload,
        )
        repeated = await client.post(
            "/api/v1/memories/provider-evaluations",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json=request_payload,
        )
        conflict = await client.post(
            "/api/v1/memories/provider-evaluations",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={**request_payload, "top_k": 2},
        )

    assert catalog.status_code == 200
    assert catalog.json()["benchmark_version"] == "role-memory-provider-smoke-v1"
    assert catalog.json()["active_memory_count"] >= 4
    assert {item["key"] for item in catalog.json()["providers"]} == {
        "tencentdb-agent-memory",
        "mem0",
    }
    assert denied.status_code == 403
    assert created.status_code == 200
    run = created.json()
    assert run["status"] == "completed"
    assert run["actor_name"] == "林知远 / CEO"
    assert len(run["results"]) == 2
    assert all(item["recall_at_k"] == 1.0 for item in run["results"])
    assert all(item["failure_reason"] is None for item in run["results"])
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["id"] == run["id"]
    assert conflict.status_code == 409

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(MemoryProviderEvaluationRun.id))) == 1
        assert session.scalar(select(func.count(MemoryProviderEvaluationResult.id))) == 2
