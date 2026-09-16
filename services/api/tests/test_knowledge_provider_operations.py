from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    KnowledgeProviderEvaluationResult,
    KnowledgeProviderEvaluationRun,
)
from zhixing_api.knowledge_providers import (
    ProviderKnowledgeDocument,
    ProviderKnowledgeHit,
    ProviderKnowledgeIndex,
)
from zhixing_api.main import create_app


class FakeKnowledgeProvider:
    key = "weknora"
    label = "WeKnora"
    protocol = "knowledge-search-v1"
    mode = "test-double"
    endpoint_fingerprint = "fake-weknora"
    authentication_configured = False

    def __init__(self, key: str = "weknora") -> None:
        self.key = key
        self.label = {
            "ragflow": "RAGFlow",
            "openviking": "OpenViking",
        }.get(key, "WeKnora")
        self.protocol = {
            "ragflow": "retrieval-api-v1",
            "openviking": "context-resource-search-v1",
        }.get(key, "knowledge-search-v1")
        self.indexes: dict[str, list[ProviderKnowledgeDocument]] = {}

    async def health(self) -> None:
        return None

    async def index_documents(
        self,
        namespace: str,
        documents: list[ProviderKnowledgeDocument],
    ) -> ProviderKnowledgeIndex:
        self.indexes[namespace] = documents
        return ProviderKnowledgeIndex(
            document_count=len(documents),
            chunk_count=sum(len(item.chunks) for item in documents),
            scope_ids=[item.document_key for item in documents],
        )

    async def search(
        self,
        index: ProviderKnowledgeIndex,
        query: str,
        *,
        top_k: int,
    ) -> list[ProviderKnowledgeHit]:
        documents = self.indexes[next(iter(self.indexes))]
        heading = (
            "诊断顺序"
            if "成交异常" in query
            else "预算分级"
            if "5 万元" in query
            else "止损条件"
            if "停止扩量" in query
            else "退款率考核"
            if "退款率" in query
            else "预警分级"
            if "3 天" in query
            else "普通补偿权限"
            if "补偿范围" in query
            else "高风险会话"
            if "转人工" in query
            else "保留条件"
        )
        matches = [
            chunk
            for document in documents
            for chunk in document.chunks
            if chunk.heading == heading
        ]
        return [
            ProviderKnowledgeHit(
                provider_id=f"{self.key}:{chunk.chunk_key}",
                chunk_key=chunk.chunk_key,
                content=chunk.content,
                score=0.96,
            )
            for chunk in matches[:top_k]
        ]


class FailingKnowledgeProvider(FakeKnowledgeProvider):
    async def health(self) -> None:
        raise RuntimeError("openviking unavailable token-secret-value")


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'knowledge_provider_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


@pytest.mark.anyio
async def test_knowledge_provider_dual_run_is_effective_scoped_audited_and_idempotent(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    app.state.knowledge_providers = {
        "weknora": FakeKnowledgeProvider(),
        "ragflow": FakeKnowledgeProvider("ragflow"),
        "openviking": FakeKnowledgeProvider("openviking"),
    }
    request_payload = {
        "schema_version": 1,
        "client_request_key": "knowledge-provider-test-001",
        "provider_keys": ["weknora", "ragflow", "openviking"],
        "top_k": 3,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        catalog = await client.get(
            "/api/v1/knowledge/provider-operations",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )
        denied = await client.post(
            "/api/v1/knowledge/provider-evaluations",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json=request_payload,
        )
        created = await client.post(
            "/api/v1/knowledge/provider-evaluations",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json=request_payload,
        )
        repeated = await client.post(
            "/api/v1/knowledge/provider-evaluations",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json=request_payload,
        )
        conflict = await client.post(
            "/api/v1/knowledge/provider-evaluations",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={**request_payload, "top_k": 2},
        )

    assert catalog.status_code == 200
    assert catalog.json()["benchmark_version"] == "enterprise-knowledge-retrieval-v1"
    assert catalog.json()["active_document_count"] >= 5
    assert catalog.json()["active_chunk_count"] >= 20
    assert len(catalog.json()["benchmark_cases"]) >= 6
    assert denied.status_code == 403
    assert created.status_code == 200
    run = created.json()
    assert run["status"] == "completed"
    assert run["actor_name"] == "林知远 / CEO"
    assert run["document_count"] >= 5
    assert run["chunk_count"] >= 20
    assert len(run["results"]) == 3
    assert all(item["recall_at_k"] == 1.0 for item in run["results"])
    assert all(item["mean_reciprocal_rank"] == 1.0 for item in run["results"])
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["id"] == run["id"]
    assert conflict.status_code == 409

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(KnowledgeProviderEvaluationRun.id))) == 1
        assert session.scalar(select(func.count(KnowledgeProviderEvaluationResult.id))) == 3


@pytest.mark.anyio
async def test_knowledge_provider_failure_is_isolated_and_persisted(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    app.state.knowledge_providers = {
        "weknora": FakeKnowledgeProvider(),
        "openviking": FailingKnowledgeProvider("openviking"),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/provider-evaluations",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={
                "schema_version": 1,
                "client_request_key": "knowledge-provider-partial-001",
                "provider_keys": ["weknora", "openviking"],
                "top_k": 3,
            },
        )

    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "partial"
    results = {item["provider_key"]: item for item in run["results"]}
    assert results["weknora"]["status"] == "succeeded"
    assert results["openviking"]["status"] == "failed"
    assert results["openviking"]["failure_reason"] == "openviking unavailable [redacted]"
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(KnowledgeProviderEvaluationRun.id))) == 1
        assert session.scalar(select(func.count(KnowledgeProviderEvaluationResult.id))) == 2
