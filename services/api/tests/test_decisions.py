from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from zhixing_agent_runtime import FakeAgentRuntime

from zhixing_api.ai_provider import AICompletion
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    AgentRuntimeSession,
    DecisionPackage,
    EvidenceSnapshot,
    EvidenceSnapshotItem,
    MeetingClaim,
    MeetingDeliberationTurn,
    MeetingRuntimeRun,
    MetricSnapshot,
    TwinMeeting,
    TwinMeetingParticipant,
)
from zhixing_api.decision_service import _evidence_text, _unsupported_numeric_output
from zhixing_api.main import create_app


def make_settings(tmp_path: Path, *, ai_enabled: bool = False) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'decision_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
        ai_enabled=ai_enabled,
        ai_api_key="test-key" if ai_enabled else "",
        ai_model="test-model",
    )


def test_evidence_text_exposes_auditable_business_number_formats() -> None:
    item = EvidenceSnapshotItem(
        id="item-1",
        snapshot_id="snapshot-1",
        item_type="metric",
        item_key="gmv_today",
        version_ref="v1",
        label="今日成交",
        payload={"value": 2_386_489.0, "unit": "元", "change_rate": -0.063},
        rank=1,
    )

    evidence = _evidence_text([item])

    assert "238.65万" in evidence
    assert "238.649万" in evidence
    assert "-6.3%" in evidence
    assert not _unsupported_numeric_output("成交 238.649万，变化 -6.3%", evidence)


@pytest.mark.anyio
async def test_role_twin_memory_and_meeting_catalogs_are_database_backed(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        twins = await client.get("/api/v1/twins", headers={"X-Zhixing-Demo-Actor": "ceo"})
        memories = await client.get("/api/v1/memories", headers={"X-Zhixing-Demo-Actor": "ceo"})
        meetings = await client.get(
            "/api/v1/decision-meetings", headers={"X-Zhixing-Demo-Actor": "ceo"}
        )
        detail = await client.get(
            "/api/v1/decision-meetings/mtg-budget-20260825",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )

    assert twins.status_code == 200
    assert twins.json()["stats"]["profile_count"] == 4
    assert {item["key"] for item in twins.json()["items"]} == {
        "twin-ceo",
        "twin-ops",
        "twin-finance",
        "twin-service",
    }
    assert memories.status_code == 200
    assert len(memories.json()["items"]) == 6
    assert memories.json()["status_counts"] == {"active": 4, "candidate": 1, "rejected": 1}
    assert meetings.status_code == 200
    assert meetings.json()["scopes"][0]["key"] == "enterprise"
    assert {item["key"] for item in meetings.json()["scopes"]} >= {"store-flagship"}
    assert meetings.json()["items"][0]["participant_count"] == 3
    assert detail.status_code == 200
    assert detail.json()["claims"] == []
    assert detail.json()["deliberation_turns"] == []
    assert detail.json()["decision_package"] is None


@pytest.mark.anyio
async def test_digital_meeting_fallback_freezes_evidence_and_is_repeatable(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/run",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"refresh_evidence": True},
        )
        second = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/run",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"refresh_evidence": False},
        )

    assert first.status_code == 200
    payload = first.json()
    assert set(payload["execution_modes"].values()) == {"evidence-fallback"}
    assert payload["detail"]["evidence"]["item_count"] >= 8
    assert len(payload["detail"]["claims"]) == 3
    turns = payload["detail"]["deliberation_turns"]
    assert len(turns) == 7
    assert [turn["turn_type"] for turn in turns].count("challenge") == 3
    assert [turn["turn_type"] for turn in turns].count("response") == 3
    assert [turn["turn_type"] for turn in turns].count("risk_review") == 1
    assert all(turn["new_evidence_refs"] for turn in turns)
    assert payload["detail"]["decision_package"]["actions"]
    assert payload["detail"]["meeting"]["protocol_status"] == "decision_drafted"
    assert second.status_code == 200
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(EvidenceSnapshot.id))) == 1
        assert session.scalar(select(func.count(MeetingClaim.id))) == 3
        assert session.scalar(select(func.count(MeetingDeliberationTurn.id))) == 7
        assert session.scalar(select(func.count(DecisionPackage.id))) == 1
        assert session.scalar(select(func.count(AgentRun.id))) == 22
        meeting = session.scalar(select(TwinMeeting))
        assert meeting is not None and meeting.status == "decision_ready"


@pytest.mark.anyio
async def test_digital_meeting_uses_structured_provider_for_roles_and_moderator(
    tmp_path: Path,
) -> None:
    requested_schemas: list[str] = []
    cross_calls = 0

    class StubProvider:
        async def generate(self, *_args: object, **kwargs: object) -> AICompletion:
            nonlocal cross_calls
            schema_name = str(kwargs["schema_name"])
            requested_schemas.append(schema_name)
            if schema_name == "meeting_role_analysis":
                payload: dict[str, object] = {
                    "stance": "conditional",
                    "summary": "基于 E1 和 E7，建议只形成有停止条件的试验方案。",
                    "claims": [
                        {
                            "statement": "现有证据支持条件性试验。",
                            "evidence_refs": ["E1"],
                            "assumption": "数据时间在会议期间不变。",
                            "confidence": "high",
                        }
                    ],
                    "risks": ["历史窗口仍有限。"],
                    "unknowns": ["需要补充长期趋势。"],
                    "recommendation": "人工确认预算边界后再进入行动审批。",
                    "confidence": "high",
                }
            elif schema_name == "meeting_cross_examination":
                cross_calls += 1
                new_ref = "E1" if cross_calls == 1 else "E2" if cross_calls <= 4 else "E3"
                payload = {
                    "summary": "质询补充了新的证据边界，并保留一个待确认问题。",
                    "challenges": [
                        {
                            "statement": "当前方案需要补充验证。",
                            "target_claim": "受控试验可行。",
                            "evidence_refs": ["E1"],
                            "new_evidence_refs": [new_ref],
                            "question": "是否接受新增证据所限定的停止条件？",
                            "confidence": "high",
                        },
                        {
                            "statement": "同一轮内的后续质询可以沿用已有证据。",
                            "target_claim": "受控试验可行。",
                            "evidence_refs": ["E1"],
                            "new_evidence_refs": [],
                            "question": "是否接受在同一证据上继续核对假设？",
                            "confidence": "medium",
                        },
                    ],
                    "position_after": "conditional",
                    "position_changed": False,
                    "unresolved": ["长期趋势仍需补充。"],
                    "confidence": "high",
                }
            elif schema_name == "meeting_risk_review":
                payload = {
                    "summary": "反方审查识别了短期指标误导风险。",
                    "failure_modes": [
                        {
                            "risk": "短期变化不可持续。",
                            "mechanism": "当前只有有限快照。",
                            "evidence_refs": ["E4"],
                            "trigger": "约束条件失效。",
                            "mitigation": "缩小试验并人工复核。",
                        }
                    ],
                    "counterfactuals": ["自然流量可能解释变化。"],
                    "incentive_risks": ["只看成交会忽略履约。"],
                    "unresolved": ["仍需历史对照。"],
                    "confidence": "high",
                }
            else:
                payload = {
                    "summary": "三个角色形成条件性共识。",
                    "consensus": ["先试验再扩量。"],
                    "disagreements": ["运营和财务对试验节奏存在分歧。"],
                    "risks": ["历史窗口有限。"],
                    "decision": "等待人类负责人确认受控试验。",
                    "actions": [
                        {
                            "title": "提交受控试验",
                            "owner": "林知远 / CEO",
                            "due_hint": "人工确认后",
                            "kpi": "以 E7 指标口径复盘",
                            "stop_condition": "指标不满足时停止",
                            "evidence_refs": ["E5"],
                        }
                    ],
                    "confidence": "high",
                }
            return AICompletion(payload=payload, input_tokens=100, output_tokens=50)

    app = create_app(make_settings(tmp_path, ai_enabled=True))
    app.state.ai_provider = StubProvider()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/run",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"refresh_evidence": True},
        )

    assert response.status_code == 200
    assert requested_schemas.count("meeting_role_analysis") == 3
    assert requested_schemas.count("meeting_cross_examination") == 7
    assert requested_schemas.count("meeting_risk_review") == 1
    assert requested_schemas.count("meeting_decision_package") == 1
    assert set(response.json()["execution_modes"].values()) == {"model"}, response.json()
    assert response.json()["detail"]["decision_package"]["confidence"] == "high"
    with app.state.database.session() as session:
        assert (
            session.scalar(select(func.count(AgentRun.id)).where(AgentRun.status == "completed"))
            == 11
        )
        assert session.scalar(select(func.count(MeetingDeliberationTurn.id))) == 7


@pytest.mark.anyio
async def test_digital_meeting_role_analysis_uses_governed_runtime(
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
                "stance": "conditional",
                "summary": "基于 E1 建议采用有停止条件的试验。",
                "claims": [
                    {
                        "statement": "冻结证据支持条件性试验。",
                        "evidence_refs": ["E1"],
                        "assumption": "会议期间证据快照不变。",
                        "confidence": "high",
                    }
                ],
                "risks": ["历史窗口有限。"],
                "unknowns": ["仍需长期趋势。"],
                "recommendation": "由决策负责人确认后执行。",
                "confidence": "high",
            },
            ensure_ascii=False,
        )
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/run",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"refresh_evidence": True},
        )
        replay = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/run",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"refresh_evidence": False},
        )

    assert response.status_code == 200
    assert replay.status_code == 200
    modes = response.json()["execution_modes"]
    assert {modes[key] for key in ("twin-ceo", "twin-ops", "twin-finance")} == {"model"}
    with app.state.database.session() as session:
        mappings = list(session.scalars(select(MeetingRuntimeRun)))
        assert len(mappings) == 6
        assert all(item.status == "completed" for item in mappings)
        assert all(item.skill_key == "policy-grounded-answer" for item in mappings)
        assert all(item.runtime_session_id for item in mappings)
        sessions = list(session.scalars(select(AgentRuntimeSession)))
        assert len(sessions) == 22
        assert all(item.status == "completed" for item in sessions)
        runs = list(
            session.scalars(select(AgentRun).where(AgentRun.phase == "independent_analysis"))
        )
        assert len(runs) == 6
        assert all(item.provider == "codex-runtime" for item in runs)


@pytest.mark.anyio
async def test_meeting_creation_enforces_permission_scope_and_idempotency(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    store_payload = {
        "schema_version": 1,
        "client_request_key": "manager-store-meeting-001",
        "template_key": "inventory-clearance-review",
        "title": "旗舰店库存清理与广告节奏研判",
        "topic": "旗舰店低库存与滞销库存同时存在，是否调整清仓折扣并收缩广告投放？",
        "scope_type": "store",
        "scope_key": "store-flagship",
        "success_metric": "14 天内降低滞销库存，同时保持退款率和广告 ROI 在可接受范围",
        "deadline_at": "2026-09-05T10:00:00+08:00",
        "participant_keys": ["twin-ceo", "twin-ops", "twin-finance"],
    }
    enterprise_payload = {
        **store_payload,
        "client_request_key": "ceo-enterprise-meeting-001",
        "template_key": "kpi-incentive-review",
        "title": "全公司经营 KPI 激励机制研判",
        "topic": "当前经营 KPI 是否造成只追求成交而忽视退款、履约与客户体验的问题？",
        "scope_type": "enterprise",
        "scope_key": "enterprise",
        "success_metric": "形成兼顾成交、退款、履约和客户体验的可复盘 KPI 方案",
        "workspace_key": "executive",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        employee = await client.post(
            "/api/v1/decision-meetings",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json=store_payload,
        )
        admin = await client.post(
            "/api/v1/decision-meetings",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=store_payload,
        )
        manager_enterprise = await client.post(
            "/api/v1/decision-meetings",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json={**enterprise_payload, "workspace_key": "manager"},
        )
        manager_store = await client.post(
            "/api/v1/decision-meetings",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json=store_payload,
        )
        ceo_enterprise = await client.post(
            "/api/v1/decision-meetings",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json=enterprise_payload,
        )
        repeated = await client.post(
            "/api/v1/decision-meetings",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json=enterprise_payload,
        )
        changed = await client.post(
            "/api/v1/decision-meetings",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={**enterprise_payload, "title": "同一请求键不得改写标题"},
        )
        manager_read_enterprise = await client.get(
            f"/api/v1/decision-meetings/{ceo_enterprise.json()['meeting']['key']}",
            headers={"X-Zhixing-Demo-Actor": "manager"},
        )

    assert employee.status_code == 403
    assert employee.json()["error"]["code"] == "authorization.permission_denied"
    assert admin.status_code == 403
    assert admin.json()["error"]["code"] == "authorization.permission_denied"
    assert manager_enterprise.status_code == 403
    assert manager_enterprise.json()["error"]["code"] == "authorization.scope_denied"
    assert manager_store.status_code == 200
    assert manager_store.json()["idempotent"] is False
    assert manager_store.json()["meeting"]["scope_label"] == "旗舰店"
    assert ceo_enterprise.status_code == 200
    assert ceo_enterprise.json()["meeting"]["workspace_key"] == "executive"
    assert ceo_enterprise.json()["meeting"]["initiated_by_name"] == "林知远 / CEO"
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["meeting"]["key"] == ceo_enterprise.json()["meeting"]["key"]
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "meeting.idempotency_conflict"
    assert manager_read_enterprise.status_code == 403

    with app.state.database.session() as session:
        meetings = list(
            session.scalars(select(TwinMeeting).where(TwinMeeting.idempotency_key.is_not(None)))
        )
        assert len(meetings) == 2
        assert all(item.actor_snapshot["scope_context"]["schema_version"] == 2 for item in meetings)
        store_meeting = next(item for item in meetings if item.scope_type == "store")
        participants = list(
            session.scalars(
                select(TwinMeetingParticipant)
                .where(TwinMeetingParticipant.meeting_id == store_meeting.id)
                .order_by(TwinMeetingParticipant.speaking_order)
            )
        )
        assert [item.actor_key for item in participants] == store_payload["participant_keys"]
        assert all(item.seat_key for item in participants)


@pytest.mark.anyio
async def test_new_store_meeting_freezes_only_scope_and_tracks_run_actor(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    with app.state.database.session() as session:
        for scope_key, value in (("enterprise", 9_546_000.0), ("store-flagship", 3_180_000.0)):
            session.add(
                MetricSnapshot(
                    id=f"meeting_metric_{scope_key}",
                    enterprise_id="ent_zhixing_demo",
                    source_system_id=None,
                    sync_run_id=None,
                    metric_key="gmv_today",
                    label="今日成交",
                    scope_key=scope_key,
                    value=value,
                    unit="元",
                    change_rate=0.083,
                    as_of=datetime(2026, 8, 29, tzinfo=UTC),
                )
            )
        session.commit()
    payload = {
        "schema_version": 1,
        "client_request_key": "manager-store-run-001",
        "template_key": "budget-inventory-review",
        "title": "旗舰店预算与库存协同复盘",
        "topic": "旗舰店广告投入增长但库存覆盖下降，下一周期预算和补货节奏应如何调整？",
        "scope_type": "store",
        "scope_key": "store-flagship",
        "success_metric": "保持广告 ROI、退款率与库存覆盖在可复盘的联合约束内",
        "participant_keys": ["twin-ceo", "twin-ops", "twin-finance"],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/decision-meetings",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json=payload,
        )
        meeting_key = created.json()["meeting"]["key"]
        run = await client.post(
            f"/api/v1/decision-meetings/{meeting_key}/run",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json={"refresh_evidence": True},
        )

    assert created.status_code == 200
    assert run.status_code == 200
    evidence_items = run.json()["detail"]["evidence"]["items"]
    metric_items = [item for item in evidence_items if item["type"] == "metric"]
    assert metric_items
    assert {item["payload"]["scope_key"] for item in metric_items} == {"store-flagship"}
    assert all("许然客服分身" not in item["label"] for item in evidence_items)

    with app.state.database.session() as session:
        meeting = session.scalar(select(TwinMeeting).where(TwinMeeting.meeting_key == meeting_key))
        assert meeting is not None
        runs = list(session.scalars(select(AgentRun).where(AgentRun.meeting_id == meeting.id)))
        assert len(runs) == 11
        assert {item.actor_principal_id for item in runs} == {"principal-ops-manager-zhou"}
