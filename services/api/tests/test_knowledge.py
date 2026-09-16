from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from zhixing_agent_runtime import FakeAgentRuntime

from zhixing_api.ai_provider import AICompletion, ResponsesAIProvider
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    AgentRunContextItem,
    AgentRunEvidence,
    AgentRuntimeEventRecord,
    AgentRuntimeSession,
    AgentRuntimeTurn,
    KnowledgeIngestionRun,
    KnowledgeLifecycleEvent,
    MCPGatewaySession,
    MetricSnapshot,
)
from zhixing_api.knowledge_schemas import EvidenceView, TwinAnswerPayload
from zhixing_api.knowledge_service import _unsupported_numeric_claims
from zhixing_api.knowledge_text import chunk_document, lexical_terms
from zhixing_api.main import create_app


def make_settings(
    tmp_path: Path,
    *,
    ai_enabled: bool = False,
    ai_base_url: str = "https://api.openai.com/v1",
    ai_model: str = "test-model",
    ai_api_key: str = "",
) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'knowledge_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
        ai_enabled=ai_enabled,
        ai_base_url=ai_base_url,
        ai_api_key=ai_api_key or ("test-key" if ai_enabled else ""),
        ai_model=ai_model,
    )


def ingestion_payload(*, version: str = "v1", refund_weight: int = 10) -> dict[str, object]:
    return {
        "document_key": "policy-store-service",
        "title": "店铺服务质量制度",
        "document_type": "policy",
        "knowledge_space": "企业制度",
        "owner": "客户体验中心",
        "tags": ["客服", "退款率"],
        "source_filename": f"store-service-{version}.md",
        "version_label": version,
        "content": (
            "# 退款率考核\n"
            f"退款率指标权重为 {refund_weight}%，按月复核。\n"
            "# 执行要求\n异常店铺必须在两个工作日内提交复盘。"
        ),
        "change_summary": f"建立服务质量制度 {version}",
    }


def test_heading_chunker_preserves_locator_and_chinese_terms() -> None:
    chunks = chunk_document("# 退款率考核\n退款率权重为 20%。\n# 执行要求\n不得提前切换。")

    assert [item.heading for item in chunks] == ["退款率考核", "执行要求"]
    assert chunks[0].locator == "退款率考核 / 段落 1"
    assert "退款率" in lexical_terms("9 月退款率如何考核")
    assert "9月" in lexical_terms("9 月退款率如何考核")


def test_answer_guard_rejects_numbers_absent_from_evidence() -> None:
    evidence = EvidenceView(
        chunk_id="chunk-1",
        document_key="policy-kpi",
        document_title="绩效制度",
        version_id="version-3",
        version_label="v3",
        version_status="published",
        effective_from="2026-09-01T00:00:00+08:00",
        heading="退款率考核",
        locator="退款率考核 / 段落 2",
        excerpt="自 2026 年 9 月 1 日起，退款率权重为 20%。",
        score=1.0,
    )
    answer = TwinAnswerPayload(
        summary="9 月按 20% 考核，10 月开始执行。",
        facts=[],
        actions=[],
        caveats=[],
        confidence="high",
    )

    unsupported = _unsupported_numeric_claims(
        answer,
        [evidence],
        question="9 月退款率如何考核？",
        now=evidence.effective_from,
    )

    assert unsupported == {"10月"}

    normalized_evidence = evidence.model_copy(
        update={"excerpt": "v2 有效期至 2026 年 8 月 31 日，成交金额为 9545956 元。"}
    )
    normalized_answer = TwinAnswerPayload(
        summary="v2 有效期至 2026-08-31，成交金额为 9,545,956 元。",
        facts=[],
        actions=[],
        caveats=[],
        confidence="high",
    )
    assert not _unsupported_numeric_claims(
        normalized_answer,
        [normalized_evidence],
        question="v2 有效期和成交金额是什么？",
        now=evidence.effective_from,
    )


@pytest.mark.anyio
async def test_responses_provider_negotiates_unsupported_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, object]] = []

    class StubClient:
        async def __aenter__(self) -> StubClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> httpx.Response:
            del headers
            requests.append(json)
            request = httpx.Request("POST", url)
            if len(requests) == 1:
                return httpx.Response(
                    400,
                    json={"detail": "Unsupported parameter: metadata"},
                    request=request,
                )
            return httpx.Response(
                200,
                json={
                    "output_text": (
                        '{"summary":"有证据结论","facts":[],"actions":[],'
                        '"caveats":[],"confidence":"high"}'
                    ),
                    "usage": {"input_tokens": 12, "output_tokens": 8},
                },
                request=request,
            )

    stub_client = StubClient()
    monkeypatch.setattr(
        "zhixing_api.ai_provider.httpx.AsyncClient",
        lambda **_kwargs: stub_client,
    )

    completion = await ResponsesAIProvider().generate(
        make_settings(tmp_path, ai_enabled=True),
        instructions="只使用证据",
        input_text="证据 E1",
        run_id="agent_run_test",
    )

    assert completion.payload["summary"] == "有证据结论"
    assert completion.input_tokens == 12
    assert "metadata" in requests[0]
    assert "metadata" not in requests[1]
    assert "text" in requests[1]


@pytest.mark.anyio
async def test_responses_provider_chat_completions_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_requests: list[dict[str, object]] = []
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")

    class StubClient:
        async def __aenter__(self) -> StubClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, object],
        ) -> httpx.Response:
            del headers
            captured_requests.append({"url": url, "json": json})
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"summary":"DeepSeek回答","facts":["F1"],'
                                    '"actions":[],"caveats":[],"confidence":"high"}'
                                )
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 15, "completion_tokens": 10},
                },
                request=request,
            )

    monkeypatch.setattr(
        "zhixing_api.ai_provider.httpx.AsyncClient",
        lambda **_kwargs: StubClient(),
    )

    deepseek_settings = make_settings(
        tmp_path,
        ai_enabled=True,
        ai_base_url="https://api.deepseek.com",
        ai_api_key="sk-test-key",
        ai_model="deepseek-chat",
    )

    completion = await ResponsesAIProvider().generate(
        deepseek_settings,
        instructions="只使用证据",
        input_text="星云铁皮柜8月GMV",
        run_id="agent_run_deepseek",
    )

    assert completion.payload["summary"] == "DeepSeek回答"
    assert completion.input_tokens == 15
    assert completion.output_tokens == 10
    assert captured_requests[0]["url"] == "https://api.deepseek.com/chat/completions"
    assert "messages" in captured_requests[0]["json"]


@pytest.mark.anyio
async def test_database_knowledge_catalog_and_evidence_search(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        documents = await client.get(
            "/api/v1/knowledge/documents", headers={"X-Zhixing-Demo-Actor": "ceo"}
        )
        evidence = await client.get(
            "/api/v1/knowledge/evidence/search",
            params={"query": "9 月退款率如何考核", "limit": 6},
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )

    assert documents.status_code == 200
    catalog = documents.json()
    assert catalog["page"]["total"] == 6
    assert catalog["version_count"] == 7
    assert catalog["chunk_count"] >= 20
    kpi = next(item for item in catalog["items"] if item["key"] == "policy-commerce-kpi")
    assert [item["version_label"] for item in kpi["versions"]] == ["v3", "v2"]

    assert evidence.status_code == 200
    search = evidence.json()
    assert search["retrieval_provider"] == "local-lexical-v1"
    assert len(search["items"]) >= 2
    assert search["items"][0]["document_key"] == "policy-commerce-kpi"
    assert search["items"][0]["version_label"] == "v3"
    assert {item["version_label"] for item in search["items"]}.issuperset({"v2", "v3"})
    assert {item["document_key"] for item in search["items"]} == {"policy-commerce-kpi"}


@pytest.mark.anyio
async def test_knowledge_ingestion_is_authorized_deduplicated_and_conflict_aware(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    payload = ingestion_payload()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/api/v1/knowledge/ingestions",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json=payload,
        )
        created = await client.post(
            "/api/v1/knowledge/ingestions",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=payload,
        )
        duplicate = await client.post(
            "/api/v1/knowledge/ingestions",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=payload,
        )
        conflict = await client.post(
            "/api/v1/knowledge/ingestions",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=ingestion_payload(version="v2", refund_weight=20),
        )
        runs = await client.get(
            "/api/v1/knowledge/ingestions",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )
        version_id = created.json()["version"]["id"]
        version = await client.get(
            f"/api/v1/knowledge/versions/{version_id}",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.permission_denied"
    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["duplicate"] is False
    assert created_payload["version"]["status"] == "draft"
    assert created_payload["version"]["chunk_count"] == 2
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["version"]["id"] == version_id
    assert conflict.status_code == 200
    conflict_payload = conflict.json()
    assert conflict_payload["ingestion_run"]["warnings"]
    assert conflict_payload["ingestion_run"]["warnings"][0]["severity"] == "critical"
    assert runs.status_code == 200
    assert runs.json()["stats"] == {"completed": 2, "duplicate": 1}
    assert version.status_code == 200
    assert version.json()["content"].startswith("# 退款率考核")
    assert len(version.json()["chunks"]) == 2
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(KnowledgeIngestionRun.id))) == 3
        assert session.scalar(select(func.count(KnowledgeLifecycleEvent.id))) == 2


@pytest.mark.anyio
async def test_policy_publish_retire_and_effective_version_are_guarded_and_idempotent(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/knowledge/ingestions",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=ingestion_payload(),
        )
        version_id = created.json()["version"]["id"]
        publish_body = {
            "effective_from": "2030-09-01T00:00:00+08:00",
            "reason": "CEO 确认制度发布窗口",
        }
        denied = await client.post(
            f"/api/v1/knowledge/versions/{version_id}/publish",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=publish_body,
        )
        published = await client.post(
            f"/api/v1/knowledge/versions/{version_id}/publish",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json=publish_body,
        )
        repeated = await client.post(
            f"/api/v1/knowledge/versions/{version_id}/publish",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json=publish_body,
        )
        august = await client.get(
            "/api/v1/knowledge/policies/policy-commerce-kpi/effective",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            params={"as_of": "2026-08-30T12:00:00+08:00"},
        )
        september = await client.get(
            "/api/v1/knowledge/policies/policy-commerce-kpi/effective",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            params={"as_of": "2026-09-02T12:00:00+08:00"},
        )
        retired = await client.post(
            f"/api/v1/knowledge/versions/{version_id}/retire",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"reason": "测试退役并保留历史引用"},
        )
        retired_again = await client.post(
            f"/api/v1/knowledge/versions/{version_id}/retire",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"reason": "重复请求不得改变历史"},
        )

    assert denied.status_code == 403
    assert published.status_code == 200
    assert published.json()["version"]["status"] == "published"
    assert published.json()["idempotent"] is False
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["event_id"] == published.json()["event_id"]
    assert august.status_code == 200
    assert august.json()["version"]["version_label"] == "v2"
    assert september.status_code == 200
    assert september.json()["version"]["version_label"] == "v3"
    assert retired.status_code == 200
    assert retired.json()["version"]["status"] == "archived"
    assert retired_again.status_code == 200
    assert retired_again.json()["idempotent"] is True
    assert retired_again.json()["event_id"] == retired.json()["event_id"]


@pytest.mark.anyio
async def test_twin_answer_falls_back_to_persisted_evidence(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"question": "9 月退款率如何考核？", "top_k": 5, "workspace_key": "executive"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "evidence-fallback"
    assert payload["schema_version"] == 3
    assert payload["workspace_key"] == "executive"
    assert len(payload["memory_context"]) == 2
    assert payload["provider"] == "local-evidence"
    assert payload["answer"]["facts"]
    assert payload["evidence"]
    with app.state.database.session() as session:
        run = session.get(AgentRun, payload["run_id"])
        assert run is not None
        assert run.status == "degraded"
        assert session.scalar(
            select(func.count(AgentRunEvidence.id)).where(
                AgentRunEvidence.run_id == payload["run_id"]
            )
        ) == len(payload["evidence"])
        workspace_context = session.scalar(
            select(AgentRunContextItem).where(
                AgentRunContextItem.run_id == payload["run_id"],
                AgentRunContextItem.item_type == "workspace",
            )
        )
        assert workspace_context is not None
        assert workspace_context.item_id == "executive"


@pytest.mark.anyio
async def test_twin_answer_uses_replaceable_responses_provider(tmp_path: Path) -> None:
    class StubProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, *_args: object, **_kwargs: object) -> AICompletion:
            self.calls += 1
            if self.calls == 1:
                return AICompletion(
                    payload={
                        "summary": "10 月开始执行。",
                        "facts": [],
                        "actions": [],
                        "caveats": [],
                        "confidence": "low",
                    },
                    input_tokens=280,
                    output_tokens=40,
                )
            return AICompletion(
                payload={
                    "summary": "9 月 1 日起按 v3 执行，退款率权重调整为 20%。",
                    "facts": ["v2 在 8 月 31 日前仍有效。", "v3 于 9 月 1 日生效。"],
                    "actions": ["8 月底前完成团队宣导。"],
                    "caveats": ["生效前不得提前修改 8 月口径。"],
                    "confidence": "high",
                },
                input_tokens=320,
                output_tokens=96,
            )

    app = create_app(make_settings(tmp_path, ai_enabled=True))
    provider = StubProvider()
    app.state.ai_provider = provider
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"question": "9 月退款率如何考核？"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "model"
    assert payload["answer"]["confidence"] == "high"
    assert payload["answer"]["summary"].startswith("9 月 1 日")
    assert provider.calls == 2
    with app.state.database.session() as session:
        run = session.get(AgentRun, payload["run_id"])
        assert run is not None
        assert run.status == "completed"
        assert run.input_tokens == 320


@pytest.mark.anyio
async def test_twin_answer_uses_runtime_with_bound_mcp_and_persisted_events(
    tmp_path: Path,
) -> None:
    settings = replace(
        make_settings(tmp_path),
        agent_runtime_enabled=True,
        codex_runtime_cwd=str(tmp_path),
    )
    app = create_app(settings)
    runtime = FakeAgentRuntime(
        response_factory=lambda _spec, _value: json.dumps(
            {
                "summary": "按现行制度执行。",
                "facts": ["退款率按月复核。"],
                "actions": ["按制度引用位置核对。"],
                "caveats": [],
                "confidence": "high",
            },
            ensure_ascii=False,
        )
    )
    app.state.agent_runtime = runtime

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"question": "退款率如何考核？", "top_k": 5},
        )
        operations = await client.get(
            "/api/v1/ai-operations/overview",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "model"
    assert payload["provider"] == "fake"
    assert payload["runtime_session_id"]
    assert payload["runtime_turn_id"]
    assert operations.status_code == 200
    runtime_view = operations.json()["runtime_sessions"][0]
    assert runtime_view["id"] == payload["runtime_session_id"]
    assert runtime_view["turn_count"] == 1
    assert runtime_view["event_count"] == 5
    assert runtime_view["latest_event_type"] == "run.completed"
    with app.state.database.session() as session:
        run = session.get(AgentRun, payload["run_id"])
        runtime_session = session.get(AgentRuntimeSession, payload["runtime_session_id"])
        runtime_turn = session.get(AgentRuntimeTurn, payload["runtime_turn_id"])
        assert run is not None and run.status == "completed"
        assert runtime_session is not None and runtime_session.status == "completed"
        assert runtime_turn is not None and runtime_turn.status == "completed"
        assert runtime_session.agent_run_id == run.id
        gateway = session.get(MCPGatewaySession, runtime_session.mcp_gateway_session_id)
        assert gateway is not None
        assert gateway.agent_run_id == run.id
        assert gateway.status == "revoked"
        events = list(
            session.scalars(
                select(AgentRuntimeEventRecord)
                .where(AgentRuntimeEventRecord.runtime_session_id == runtime_session.id)
                .order_by(AgentRuntimeEventRecord.sequence)
            )
        )
        assert [event.event_type for event in events] == [
            "run.started",
            "turn.started",
            "message.delta",
            "message.completed",
            "run.completed",
        ]
        assert all("按现行制度执行" not in json.dumps(event.event_payload) for event in events)


@pytest.mark.anyio
async def test_twin_runtime_followup_reuses_thread_with_new_run_and_mcp_session(
    tmp_path: Path,
) -> None:
    settings = replace(
        make_settings(tmp_path),
        agent_runtime_enabled=True,
        codex_runtime_cwd=str(tmp_path),
    )
    app = create_app(settings)
    app.state.agent_runtime = FakeAgentRuntime(
        response_factory=lambda _spec, value: json.dumps(
            {
                "summary": f"已回答：{value.splitlines()[-1][:24]}",
                "facts": ["退款率按月复核。"],
                "actions": [],
                "caveats": [],
                "confidence": "high",
            },
            ensure_ascii=False,
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"question": "退款率如何考核？", "top_k": 5},
        )
        assert first.status_code == 200
        first_payload = first.json()
        second = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={
                "question": "为什么要按月复核？",
                "top_k": 5,
                "runtime_session_id": first_payload["runtime_session_id"],
            },
        )
        detail = await client.get(
            f"/api/v1/ai-operations/runtime-sessions/{first_payload['runtime_session_id']}",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )
        denied = await client.get(
            f"/api/v1/ai-operations/runtime-sessions/{first_payload['runtime_session_id']}",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )

    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["run_id"] != first_payload["run_id"]
    assert second_payload["runtime_session_id"] == first_payload["runtime_session_id"]
    assert second_payload["runtime_turn_id"] != first_payload["runtime_turn_id"]
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["session"]["turn_count"] == 2
    assert detail_payload["session"]["event_count"] == 10
    assert detail_payload["session"]["can_cancel"] is False
    assert [item["agent_run_id"] for item in detail_payload["turns"]] == [
        first_payload["run_id"],
        second_payload["run_id"],
    ]
    assert denied.status_code == 403
    with app.state.database.session() as session:
        runtime_session = session.get(
            AgentRuntimeSession,
            first_payload["runtime_session_id"],
        )
        assert runtime_session is not None
        turns = list(
            session.scalars(
                select(AgentRuntimeTurn)
                .where(AgentRuntimeTurn.runtime_session_id == runtime_session.id)
                .order_by(AgentRuntimeTurn.turn_number)
            )
        )
        assert len({item.agent_run_id for item in turns}) == 2
        assert len({item.mcp_gateway_session_id for item in turns}) == 2
        gateways = [
            session.get(MCPGatewaySession, item.mcp_gateway_session_id)
            for item in turns
        ]
        assert all(item is not None and item.status == "revoked" for item in gateways)


@pytest.mark.anyio
async def test_runtime_session_can_be_cancelled_without_provider_fallback(
    tmp_path: Path,
) -> None:
    settings = replace(
        make_settings(tmp_path),
        agent_runtime_enabled=True,
        codex_runtime_cwd=str(tmp_path),
    )
    app = create_app(settings)
    app.state.agent_runtime = FakeAgentRuntime(
        response_factory=lambda _spec, _value: json.dumps(
            {
                "summary": "不应返回",
                "facts": [],
                "actions": [],
                "caveats": [],
                "confidence": "low",
            },
            ensure_ascii=False,
        ),
        delay_seconds=1,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        answer_task = asyncio.create_task(
            client.post(
                "/api/v1/twins/twin-ceo/answers",
                headers={"X-Zhixing-Demo-Actor": "ceo"},
                json={"question": "退款率如何考核？", "top_k": 5},
            )
        )
        runtime_session: AgentRuntimeSession | None = None
        for _ in range(100):
            await asyncio.sleep(0.01)
            with app.state.database.session() as session:
                runtime_session = session.scalar(
                    select(AgentRuntimeSession).order_by(
                        AgentRuntimeSession.created_at.desc()
                    )
                )
            if runtime_session is not None:
                break
        assert runtime_session is not None
        cancelled = await client.post(
            f"/api/v1/ai-operations/runtime-sessions/{runtime_session.id}/cancel",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )
        answer_response = await answer_task
        detail = await client.get(
            f"/api/v1/ai-operations/runtime-sessions/{runtime_session.id}",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )
        repeated = await client.post(
            f"/api/v1/ai-operations/runtime-sessions/{runtime_session.id}/cancel",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "interrupt_requested"
    assert answer_response.status_code == 409
    assert detail.status_code == 200
    assert detail.json()["session"]["status"] == "cancelled"
    assert detail.json()["session"]["can_cancel"] is False
    assert repeated.status_code == 409
    with app.state.database.session() as session:
        saved_session = session.get(AgentRuntimeSession, runtime_session.id)
        assert saved_session is not None and saved_session.status == "cancelled"
        assert saved_session.runtime_spec["run_id"] == saved_session.agent_run_id
        assert saved_session.runtime_spec["allowed_tool_keys"]
        assert "credentials" not in saved_session.runtime_spec
        assert saved_session.runtime_spec["scope_context"]["schema_version"] == 2
        assert saved_session.runtime_spec["scope_context"]["enterprise_id"] == (
            saved_session.enterprise_id
        )
        run = session.get(AgentRun, saved_session.agent_run_id)
        assert run is not None
        assert run.status == "cancelled"
        assert run.provider == "fake"
        gateway = session.get(MCPGatewaySession, saved_session.mcp_gateway_session_id)
        assert gateway is not None and gateway.status == "revoked"


@pytest.mark.anyio
async def test_twin_answer_falls_back_to_provider_after_runtime_failure(
    tmp_path: Path,
) -> None:
    settings = replace(
        make_settings(tmp_path, ai_enabled=True),
        agent_runtime_enabled=True,
        codex_runtime_cwd=str(tmp_path),
    )
    app = create_app(settings)

    def fail_runtime(_spec: object, _value: str) -> str:
        raise RuntimeError("runtime unavailable")

    class StubProvider:
        async def generate(self, *_args: object, **_kwargs: object) -> AICompletion:
            return AICompletion(
                payload={
                    "summary": "已由 Provider 完成回答。",
                    "facts": ["退款率按月复核。"],
                    "actions": [],
                    "caveats": [],
                    "confidence": "high",
                },
                input_tokens=42,
                output_tokens=18,
            )

    app.state.agent_runtime = FakeAgentRuntime(response_factory=fail_runtime)
    app.state.ai_provider = StubProvider()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"question": "退款率如何考核？"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_mode"] == "model"
    assert payload["provider"] == "openai-compatible-responses"
    assert payload["runtime_session_id"] is None
    with app.state.database.session() as session:
        run = session.get(AgentRun, payload["run_id"])
        runtime_session = session.scalar(
            select(AgentRuntimeSession).where(
                AgentRuntimeSession.agent_run_id == payload["run_id"]
            )
        )
        assert run is not None
        assert run.status == "completed"
        assert run.input_tokens == 42
        assert "Agent Runtime 降级" in (run.fallback_reason or "")
        assert runtime_session is not None
        assert runtime_session.status == "failed"
        gateway = session.get(MCPGatewaySession, runtime_session.mcp_gateway_session_id)
        assert gateway is not None and gateway.status == "revoked"


@pytest.mark.anyio
async def test_twin_metric_context_is_authorized_scoped_and_recorded(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    with app.state.database.session() as session:
        for scope_key, values in (
            ("enterprise", (100.0, 120.0, 150.0)),
            ("store-flagship", (40.0, 45.0, 55.0)),
        ):
            for index, value in enumerate(values, start=1):
                session.add(
                    MetricSnapshot(
                        id=f"metric_answer_{scope_key}_{index}",
                        enterprise_id="ent_zhixing_demo",
                        source_system_id=None,
                        sync_run_id=None,
                        metric_key="gmv_today",
                        label="成交金额",
                        scope_key=scope_key,
                        value=value,
                        unit="万元",
                        change_rate=None,
                        as_of=datetime(2026, 8, 24 + index, tzinfo=UTC),
                    )
                )
        session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing_actor = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            json={"question": "近3天成交趋势如何？"},
        )
        enterprise = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"question": "近3天成交趋势如何？"},
        )
        employee = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={"question": "近3天成交趋势如何？"},
        )
        denied = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={"question": "近3天成交趋势如何？", "scope_key": "enterprise"},
        )

    assert missing_actor.status_code == 401
    assert missing_actor.json()["error"]["code"] == "auth.development_actor_required"
    assert enterprise.status_code == 200
    enterprise_payload = enterprise.json()
    enterprise_metric = enterprise_payload["metric_context"][0]
    assert enterprise_payload["schema_version"] == 3
    assert enterprise_metric["scope_key"] == "enterprise"
    assert [point["value"] for point in enterprise_metric["points"]] == [100, 120, 150]
    assert enterprise_metric["period_change_rate"] == pytest.approx(0.5)
    assert "经营数据 D1" in " ".join(enterprise_payload["answer"]["facts"])
    with app.state.database.session() as session:
        assert session.scalar(
            select(func.count(AgentRunContextItem.id)).where(
                AgentRunContextItem.run_id == enterprise_payload["run_id"],
                AgentRunContextItem.item_type == "metric-series",
            )
        ) == 1

    assert employee.status_code == 200
    assert employee.json()["metric_context"][0]["scope_key"] == "store-flagship"
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.scope_denied"
