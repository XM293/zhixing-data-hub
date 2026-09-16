from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from zhixing_api.config import Settings
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://test",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'skills.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:9",
    )


def version_payload(summary: str = "建立新版本") -> dict[str, object]:
    return {
        "instructions": "先读取授权范围内的指标，再输出带证据的结构化结果，不得猜测口径。",
        "tool_keys": ["get_metric"],
        "input_schema": {
            "type": "object",
            "properties": {"scope_key": {"type": "string"}},
            "required": ["scope_key"],
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
            "additionalProperties": False,
        },
        "change_summary": summary,
    }


@pytest.mark.anyio
async def test_skill_registry_is_versioned_and_tool_governed(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    admin = {"X-Zhixing-Demo-Actor": "admin"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get(
            "/api/v1/skills/studio",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        studio = await client.get("/api/v1/skills/studio", headers=admin)
        created = await client.post(
            "/api/v1/skills",
            headers=admin,
            json={
                "skill_key": "metric-brief-test",
                "name": "指标简报测试",
                "description": "按授权范围生成指标简报。",
                **version_payload("首版指标简报"),
            },
        )
        published = await client.post(
            "/api/v1/skills/metric-brief-test/versions/1/publish",
            headers=admin,
            json={"reason": "通过工具引用校验"},
        )
        invalid = await client.post(
            "/api/v1/skills/metric-brief-test/versions",
            headers=admin,
            json={**version_payload(), "tool_keys": ["unregistered-tool"]},
        )
        second = await client.post(
            "/api/v1/skills/metric-brief-test/versions",
            headers=admin,
            json=version_payload("修正输出格式"),
        )
        republished = await client.post(
            "/api/v1/skills/metric-brief-test/versions/2/publish",
            headers=admin,
            json={"reason": "发布修正版"},
        )
        replay = await client.post(
            "/api/v1/skills/metric-brief-test/versions/2/publish",
            headers=admin,
            json={"reason": "发布修正版"},
        )

    assert denied.status_code == 403
    assert studio.status_code == 200
    assert {item["key"] for item in studio.json()["skills"]} >= {
        "policy-grounded-answer",
        "store-performance-brief",
    }
    assert created.status_code == 200
    assert published.status_code == 200
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "skill.tool_not_registered"
    assert second.status_code == 200
    assert republished.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True
    skill = next(
        item
        for item in republished.json()["studio"]["skills"]
        if item["key"] == "metric-brief-test"
    )
    assert skill["status"] == "published"
    assert skill["current_version_number"] == 2
    versions = {item["version_number"]: item for item in skill["versions"]}
    assert versions[1]["status"] == "retired"
    assert versions[2]["status"] == "published"
