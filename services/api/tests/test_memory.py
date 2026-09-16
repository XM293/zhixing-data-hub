from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRunContextItem,
    ApprovedMemory,
    ChatImportRun,
    ChatMessage,
    MemoryCandidate,
    MemoryReviewEvent,
)
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'memory_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


def chat_payload() -> dict[str, object]:
    return {
        "twin_key": "twin-ceo",
        "source_filename": "管理群-2026-08-27.txt",
        "source_channel": "feishu-export",
        "timezone": "Asia/Shanghai",
        "target_speakers": ["林知远"],
        "content": (
            "# 话题: 管理汇报\n"
            "[2026-08-27 09:00] 林知远: 以后管理汇报必须先给结论，再列证据、责任人和期限。\n"
            "[2026-08-27 09:02] 周岚: 收到，我会调整周报格式。\n"
            "# 话题: 绩效口径\n"
            "[2026-08-27 09:10] 林知远: 退款率考核仍按 10% 执行。\n"
            "# 话题: 客服管理\n"
            "[2026-08-27 09:15] 林知远: 以后客服回复应该先确认订单状态再给处理建议。"
        ),
    }


@pytest.mark.anyio
async def test_chat_import_preserves_messages_deduplicates_and_requires_permission(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/api/v1/memories/chat-imports",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json=chat_payload(),
        )
        created = await client.post(
            "/api/v1/memories/chat-imports",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=chat_payload(),
        )
        duplicate = await client.post(
            "/api/v1/memories/chat-imports",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=chat_payload(),
        )
        imports = await client.get(
            "/api/v1/memories/chat-imports",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )
        memories = await client.get(
            "/api/v1/memories",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )

    assert denied.status_code == 403
    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["duplicate"] is False
    assert created_payload["import_run"]["message_count"] == 4
    assert created_payload["import_run"]["topic_count"] == 3
    assert created_payload["import_run"]["candidate_count"] == 3
    assert len(created_payload["messages"]) == 4
    assert len(created_payload["candidates"]) == 3
    assert {item["conflict_status"] for item in created_payload["candidates"]} >= {
        "conflicted",
        "unverified",
    }
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["messages"] == []
    assert imports.status_code == 200
    assert imports.json()["status_counts"] == {"completed": 1, "duplicate": 1}
    assert memories.status_code == 200
    assert memories.json()["schema_version"] == 2
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(ChatImportRun.id))) == 2
        assert session.scalar(select(func.count(ChatMessage.id))) == 4
        assert session.scalar(
            select(func.count(MemoryCandidate.id)).where(
                MemoryCandidate.source_import_run_id.is_not(None)
            )
        ) == 3


@pytest.mark.anyio
async def test_memory_review_activation_conflict_and_retirement_state_machine(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/memories/chat-imports",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=chat_payload(),
        )
        candidates = created.json()["candidates"]
        clearable = next(item for item in candidates if item["conflict_status"] == "unverified")
        conflicted = next(item for item in candidates if item["conflict_status"] == "conflicted")
        rejectable = next(
            item
            for item in candidates
            if item["id"] not in {clearable["id"], conflicted["id"]}
        )

        denied = await client.post(
            f"/api/v1/memories/{clearable['id']}/review",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "decision": "approve",
                "reason": "管理员不应拥有业务记忆审核权",
                "conflict_resolution": "verified_clear",
            },
        )
        approved = await client.post(
            f"/api/v1/memories/{clearable['id']}/review",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={
                "decision": "approve",
                "reason": "已核对正式制度，该内容属于表达与管理偏好",
                "conflict_resolution": "verified_clear",
            },
        )
        activated = await client.post(
            f"/api/v1/memories/{clearable['id']}/activate",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"reason": "纳入 CEO 分身长期记忆上下文"},
        )
        answered = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"question": "经营异常汇报应该怎么组织？", "top_k": 5},
        )
        retired = await client.post(
            f"/api/v1/memories/{clearable['id']}/retire",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"reason": "管理表达规则已经被新版本替代"},
        )
        retired_again = await client.post(
            f"/api/v1/memories/{clearable['id']}/retire",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"reason": "重复退役必须幂等"},
        )
        conflict_approved = await client.post(
            f"/api/v1/memories/{conflicted['id']}/review",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={
                "decision": "approve",
                "reason": "仅作为历史判断保留，不进入当前回答",
                "conflict_resolution": "retain_conflict",
            },
        )
        conflict_activation = await client.post(
            f"/api/v1/memories/{conflicted['id']}/activate",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"reason": "冲突记忆不得激活"},
        )
        rejected = await client.post(
            f"/api/v1/memories/{rejectable['id']}/review",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"decision": "reject", "reason": "该句只是临时操作提醒"},
        )

    assert denied.status_code == 403
    assert approved.status_code == 200
    assert approved.json()["candidate"]["status"] == "approved"
    assert approved.json()["approved_memory"]["status"] == "approved"
    assert activated.status_code == 200
    assert activated.json()["candidate"]["status"] == "active"
    assert answered.status_code == 200
    assert answered.json()["schema_version"] == 3
    assert any(
        item["id"] == activated.json()["approved_memory"]["id"]
        for item in answered.json()["memory_context"]
    )
    assert retired.status_code == 200
    assert retired.json()["candidate"]["status"] == "retired"
    assert retired_again.status_code == 200
    assert retired_again.json()["idempotent"] is True
    assert retired_again.json()["event"]["id"] == retired.json()["event"]["id"]
    assert conflict_approved.status_code == 200
    assert conflict_approved.json()["candidate"]["conflict_status"] == "conflicted"
    assert conflict_activation.status_code == 409
    assert (
        conflict_activation.json()["error"]["code"]
        == "memory.conflicted_candidate_not_activatable"
    )
    assert rejected.status_code == 200
    assert rejected.json()["candidate"]["status"] == "rejected"
    with app.state.database.session() as session:
        assert session.scalar(
            select(func.count(ApprovedMemory.id)).where(
                ApprovedMemory.candidate_id.in_([clearable["id"], conflicted["id"]])
            )
        ) == 2
        assert session.scalar(
            select(func.count(MemoryReviewEvent.id)).where(
                MemoryReviewEvent.candidate_id == clearable["id"]
            )
        ) == 3
        assert session.scalar(
            select(func.count(AgentRunContextItem.id)).where(
                AgentRunContextItem.run_id == answered.json()["run_id"]
            )
        ) >= 3
