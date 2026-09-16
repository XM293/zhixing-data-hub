from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.ai_provider import AICompletion
from zhixing_api.config import Settings
from zhixing_api.customer_service_reconciliation import (
    summarize_customer_service_reconciliation,
)
from zhixing_api.data_models import (
    AgentRun,
    AgentRunContextItem,
    AgentRunEvidence,
    CommerceOrderFact,
    CommerceRefundFact,
    CustomerServiceConversation,
    CustomerServiceEvent,
    CustomerServiceMessage,
    CustomerServiceReplyDraft,
    DataScopeMapping,
    EvidenceSnapshot,
    ExternalSystem,
    SyncRun,
)
from zhixing_api.main import create_app
from zhixing_api.seed import ENTERPRISE_ID


def make_settings(tmp_path: Path, *, ai_enabled: bool = False) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=(
            f"sqlite+pysqlite:///{(tmp_path / 'customer_service_test.db').as_posix()}"
        ),
        mock_commerce_url="http://127.0.0.1:8100",
        ai_enabled=ai_enabled,
        ai_api_key="test-key" if ai_enabled else "",
        ai_model="customer-service-test-model",
    )


@pytest.mark.anyio
async def test_customer_service_fallback_freezes_evidence_and_requires_handoff(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    service = {"X-Zhixing-Demo-Actor": "service"}
    draft_request = {"client_request_key": "service-high-risk-draft-001"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        studio = await client.get("/api/v1/customer-service/studio", headers=service)
        denied = await client.get(
            "/api/v1/customer-service/studio",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        created = await client.post(
            "/api/v1/customer-service/conversations/cnv-10086/drafts",
            headers=service,
            json=draft_request,
        )
        repeated = await client.post(
            "/api/v1/customer-service/conversations/cnv-10086/drafts",
            headers=service,
            json=draft_request,
        )
        draft_id = created.json()["studio"]["selected"]["drafts"][0]["id"]
        blocked_send = await client.post(
            f"/api/v1/customer-service/drafts/{draft_id}/sandbox-send",
            headers=service,
            json={
                "note": "人工确认尝试",
                "client_request_key": "service-high-risk-send-001",
            },
        )
        handed_off = await client.post(
            "/api/v1/customer-service/conversations/cnv-10086/handoffs",
            headers=service,
            json={
                "reason": "补偿金额超过授权上限，转交风险专员",
                "client_request_key": "service-high-risk-handoff-001",
            },
        )

    assert studio.status_code == 200
    studio_payload = studio.json()
    assert studio_payload["data_mode"] == "database"
    assert studio_payload["channel_mode"] == "commerce-sandbox"
    assert studio_payload["stats"]["total_count"] == 12
    assert len(studio_payload["conversations"]) == 12
    assert studio_payload["active_policy"]["document_key"] == (
        "policy-service-compensation"
    )
    assert studio_payload["twin"]["key"] == "twin-service"
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.permission_denied"
    assert created.status_code == 200
    selected = created.json()["studio"]["selected"]
    assert created.json()["idempotent"] is False
    assert selected["conversation"]["status"] == "review_required"
    draft = selected["drafts"][0]
    assert draft["execution_mode"] == "evidence-fallback"
    assert draft["safe_to_send"] is False
    assert draft["suggested_action"] == "handoff"
    assert "compensation_commitment" in draft["risk_flags"]
    assert "D1" in draft["evidence_refs"]
    assert any(item["ref"] == "K1" for item in draft["evidence"])
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["studio"]["selected"]["drafts"][0]["id"] == draft_id
    assert blocked_send.status_code == 409
    assert blocked_send.json()["error"]["code"] == (
        "customer_service.human_review_required"
    )
    assert handed_off.status_code == 200
    assert handed_off.json()["studio"]["selected"]["conversation"]["status"] == (
        "handed_off"
    )

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(CustomerServiceReplyDraft.id))) == 1
        assert session.scalar(select(func.count(AgentRun.id))) == 1
        assert session.scalar(select(func.count(EvidenceSnapshot.id))) == 1
        assert session.scalar(select(func.count(AgentRunEvidence.id))) >= 1
        assert session.scalar(select(func.count(AgentRunContextItem.id))) == 2
        assert session.scalar(select(func.count(CustomerServiceEvent.id))) == 2


@pytest.mark.anyio
async def test_safe_model_draft_can_be_human_confirmed_to_sandbox_once(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path, ai_enabled=True))

    class StubProvider:
        async def generate(self, *_args: object, **_kwargs: object) -> AICompletion:
            return AICompletion(
                payload={
                    "body": (
                        "您好，根据当前商品信息，日常叠穿抓绒可优先考虑 XL；"
                        "如果偏好合身版型可选 L，最终请结合详情页尺码表确认 [D1][K5]。"
                    ),
                    "risk_level": "low",
                    "risk_flags": [],
                    "safe_to_send": True,
                    "suggested_action": "reply",
                    "evidence_refs": ["D1", "K5"],
                    "confidence": "high",
                },
                input_tokens=180,
                output_tokens=72,
            )

    app.state.ai_provider = StubProvider()
    service = {"X-Zhixing-Demo-Actor": "service"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/customer-service/conversations/cnv-10052/drafts",
            headers=service,
            json={"client_request_key": "service-safe-draft-001"},
        )
        draft = created.json()["studio"]["selected"]["drafts"][0]
        send_payload = {
            "final_body": draft["body"] + " 感谢您的咨询。",
            "note": "客服人工复核尺码措辞后确认",
            "client_request_key": "service-safe-send-001",
        }
        sent = await client.post(
            f"/api/v1/customer-service/drafts/{draft['id']}/sandbox-send",
            headers=service,
            json=send_payload,
        )
        repeated = await client.post(
            f"/api/v1/customer-service/drafts/{draft['id']}/sandbox-send",
            headers=service,
            json=send_payload,
        )

    assert created.status_code == 200
    assert draft["execution_mode"] == "model"
    assert draft["safe_to_send"] is True
    assert draft["suggested_action"] == "reply"
    assert sent.status_code == 200
    sent_selected = sent.json()["studio"]["selected"]
    assert sent_selected["conversation"]["status"] == "resolved"
    assert sent_selected["drafts"][0]["status"] == "sandbox_sent"
    assert sent_selected["messages"][-1]["direction"] == "outbound"
    assert sent_selected["messages"][-1]["delivery_status"] == "sandbox-sent"
    assert sent_selected["events"][0]["details"]["human_confirmed"] is True
    assert sent_selected["events"][0]["details"]["edited"] is True
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    with app.state.database.session() as session:
        outbound = session.scalar(
            select(func.count(CustomerServiceMessage.id)).where(
                CustomerServiceMessage.direction == "outbound"
            )
        )
        assert outbound == 1
        assert session.scalar(select(func.count(AgentRun.id))) == 1


@pytest.mark.anyio
async def test_deterministic_risk_overrides_unsafe_model_judgment(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, ai_enabled=True))

    class UnsafeStubProvider:
        async def generate(self, *_args: object, **_kwargs: object) -> AICompletion:
            return AICompletion(
                payload={
                    "body": "已经确认没有安全风险，可以继续使用 [D1][K5][K6]。",
                    "risk_level": "low",
                    "risk_flags": [],
                    "safe_to_send": True,
                    "suggested_action": "reply",
                    "evidence_refs": ["D1", "K5", "K6"],
                    "confidence": "high",
                },
                input_tokens=120,
                output_tokens=40,
            )

    app.state.ai_provider = UnsafeStubProvider()
    service = {"X-Zhixing-Demo-Actor": "service"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/customer-service/conversations/cnv-10204/drafts",
            headers=service,
            json={"client_request_key": "service-unsafe-model-001"},
        )

    assert response.status_code == 200
    draft = response.json()["studio"]["selected"]["drafts"][0]
    assert draft["execution_mode"] == "model"
    assert draft["risk_level"] == "critical"
    assert draft["safe_to_send"] is False
    assert draft["suggested_action"] == "handoff"
    assert "safety_or_complaint" in draft["risk_flags"]


@pytest.mark.anyio
async def test_model_reported_medium_risk_cannot_mark_draft_safe(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, ai_enabled=True))

    class MediumRiskStubProvider:
        async def generate(self, *_args: object, **_kwargs: object) -> AICompletion:
            return AICompletion(
                payload={
                    "body": "可以先参考商品尺码表，但该建议仍需要客服复核 [D1][K5]。",
                    "risk_level": "medium",
                    "risk_flags": ["other"],
                    "safe_to_send": True,
                    "suggested_action": "reply",
                    "evidence_refs": ["D1", "K5"],
                    "confidence": "medium",
                },
                input_tokens=100,
                output_tokens=35,
            )

    app.state.ai_provider = MediumRiskStubProvider()
    service = {"X-Zhixing-Demo-Actor": "service"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/customer-service/conversations/cnv-10052/drafts",
            headers=service,
            json={"client_request_key": "service-medium-risk-model-001"},
        )

    assert response.status_code == 200
    selected = response.json()["studio"]["selected"]
    draft = selected["drafts"][0]
    assert draft["execution_mode"] == "model"
    assert draft["risk_level"] == "medium"
    assert draft["safe_to_send"] is False
    assert draft["suggested_action"] == "investigate"
    assert selected["conversation"]["status"] == "review_required"


@pytest.mark.anyio
async def test_customer_service_projects_only_scope_matched_canonical_order_facts(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    now = datetime.now(UTC)
    with app.state.database.session() as session:
        conversation = session.scalar(
            select(CustomerServiceConversation).where(
                CustomerServiceConversation.conversation_key == "cnv-10086"
            )
        )
        source = session.scalar(
            select(ExternalSystem).where(ExternalSystem.system_key == "jky-erp-oms")
        )
        assert conversation is not None
        assert source is not None
        conversation.topic = "退款到账与补偿咨询"
        session.add(
            SyncRun(
                id="sync_customer_fact_test",
                enterprise_id=conversation.enterprise_id,
                external_system_id=source.id,
                status="succeeded",
                scenario="healthy",
                volume_profile="standard",
                records_read=3,
                records_written=3,
                warning=None,
                error=None,
                started_at=now,
                finished_at=now,
            )
        )
        session.add(
            DataScopeMapping(
                id="scope_customer_fact_test",
                enterprise_id=conversation.enterprise_id,
                external_system_id=source.id,
                sync_run_id="sync_customer_fact_test",
                scope_type="store",
                scope_key="store-outlet",
                external_scope_key="JD-002",
                label="京东自营店",
                status="active",
                attributes={"test": True},
                source_schema_version="jky-test-v1",
                mapping_version="test-v1",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            CommerceOrderFact(
                id="commerce_order_customer_fact_test",
                enterprise_id=conversation.enterprise_id,
                external_system_id=source.id,
                sync_run_id="sync_customer_fact_test",
                order_key="ORD-20260825-000422",
                store_key="JD-002",
                customer_key="CUS-0000086",
                channel="jd",
                status="completed",
                business_date=date(2026, 8, 25),
                paid_at=now,
                shipped_at=now,
                paid_amount_fen=108718,
                item_amount_fen=112000,
                discount_amount_fen=3282,
                freight_amount_fen=0,
                cost_amount_fen=62000,
                item_count=3,
                province="上海",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            CommerceRefundFact(
                id="commerce_refund_customer_fact_test",
                enterprise_id=conversation.enterprise_id,
                external_system_id=source.id,
                sync_run_id="sync_customer_fact_test",
                refund_key="REF-CUSTOMER-FACT-TEST",
                order_key="ORD-20260825-000422",
                line_key="LINE-CUSTOMER-FACT-TEST",
                store_key="JD-002",
                customer_key="CUS-0000086",
                sku_key="SKU-CUSTOMER-FACT-TEST",
                reason_category="logistics",
                status="completed",
                requested_at=now,
                completed_at=now,
                refund_amount_fen=10000,
                quantity=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    service = {"X-Zhixing-Demo-Actor": "service"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        studio = await client.get(
            "/api/v1/customer-service/studio?conversation_key=cnv-10086",
            headers=service,
        )
        draft_response = await client.post(
            "/api/v1/customer-service/conversations/cnv-10086/drafts",
            headers=service,
            json={"client_request_key": "customer-canonical-fact-draft-001"},
        )

    assert studio.status_code == 200
    canonical = studio.json()["selected"]["canonical_order_fact"]
    assert canonical["match_status"] == "matched"
    assert canonical["consistency_status"] == "conflict"
    assert canonical["material_conflict"] is True
    assert {item["field"] for item in canonical["differences"]} == {
        "order_status",
        "paid_amount",
        "item_count",
        "refund_state",
    }
    assert canonical["external_store_key"] == "JD-002"
    assert canonical["paid_amount"] == 1087.18
    assert canonical["refund_count"] == 1
    assert canonical["refund_amount"] == 100.0
    assert canonical["sync_run_ids"] == ["sync_customer_fact_test"]
    assert draft_response.status_code == 200
    evidence = draft_response.json()["studio"]["selected"]["drafts"][0]["evidence"]
    evidence_refs = draft_response.json()["studio"]["selected"]["drafts"][0][
        "evidence_refs"
    ]
    assert any(item["item_type"] == "order-fact" and item["ref"] == "D3" for item in evidence)
    assert any(item["item_type"] == "refund-fact" and item["ref"] == "D4" for item in evidence)
    assert any(item["item_type"] == "reconciliation" and item["ref"] == "D5" for item in evidence)
    assert {"D3", "D4", "D5"}.issubset(evidence_refs)
    conflict_draft = draft_response.json()["studio"]["selected"]["drafts"][0]
    assert conflict_draft["safe_to_send"] is False
    assert "data_conflict" in conflict_draft["risk_flags"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        blocked_send = await client.post(
            f"/api/v1/customer-service/drafts/{conflict_draft['id']}/sandbox-send",
            headers=service,
            json={
                "note": "尝试人工确认冲突数据",
                "client_request_key": "customer-canonical-conflict-send-001",
            },
        )
    assert blocked_send.status_code == 409
    assert blocked_send.json()["error"]["code"] == (
        "customer_service.data_reconciliation_required"
    )

    with app.state.database.session() as session:
        reconciliation = summarize_customer_service_reconciliation(
            session,
            enterprise_id=ENTERPRISE_ID,
        )
    assert reconciliation.conversation_count == 12
    assert reconciliation.order_conversation_count == 10
    assert reconciliation.matched_count == 1
    assert reconciliation.consistent_count == 0
    assert reconciliation.conflict_count == 1
    assert reconciliation.missing_count == 9
    assert reconciliation.not_applicable_count == 2
    assert reconciliation.result_status == "failed"

    with app.state.database.session() as session:
        mapping = session.get(DataScopeMapping, "scope_customer_fact_test")
        assert mapping is not None
        mapping.scope_key = "store-flagship"
        session.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        mismatched = await client.get(
            "/api/v1/customer-service/studio?conversation_key=cnv-10086",
            headers=service,
        )
    mismatch_fact = mismatched.json()["selected"]["canonical_order_fact"]
    assert mismatch_fact["match_status"] == "scope_mismatch"
    assert mismatch_fact["consistency_status"] == "not_checked"
    assert mismatch_fact["paid_amount"] is None
    assert mismatch_fact["sync_run_ids"] == []
