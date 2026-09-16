from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, inspect, select

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    RoleConfigurationEvent,
    RoleTemplate,
    RoleTemplateVersion,
    RoleTwinProfile,
    RoleTwinVersion,
)
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'role_twin_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


def template_payload(*, change_summary: str = "建立客服负责人岗位模板") -> dict[str, object]:
    return {
        "template_key": "template-service-leader",
        "name": "客服中心负责人",
        "description": "负责服务质量、升级处置、补偿边界和客户体验改进。",
        "role_title": "客服中心负责人分身",
        "responsibilities": ["服务质量分析", "高风险会话升级", "补偿边界审查"],
        "capability_boundaries": ["不自动承诺补偿", "不绕过人工升级", "不读取未授权会话"],
        "default_voice_guide": "先说明客户影响和风险等级，再给证据、负责人和处理期限。",
        "default_reasoning_guide": "先核对订单与会话事实，再核对现行客服制度和补偿授权边界。",
        "default_answer_policy": "高风险投诉必须转人工，未经审批不得承诺退款到账时间或补偿结果。",
        "change_summary": change_summary,
    }


def twin_payload(
    *,
    voice: str = "结论先行，明确客户影响、证据、责任人和处理时限。",
) -> dict[str, object]:
    return {
        "twin_key": "twin-service-leader",
        "template_key": "template-service-leader",
        "owner_principal_key": "principal-service-demo",
        "display_name": "许然负责人分身",
        "voice_guide": voice,
        "reasoning_guide": "按会话风险、订单事实、制度版本和补偿权限逐项核验后给出建议。",
        "answer_policy": "不虚构订单状态，不自动承诺补偿，高风险会话必须转人工确认。",
        "provider": "openai-compatible-responses",
        "model": "environment-configured",
        "capabilities": ["服务质量分析", "回复边界解释", "人工升级建议"],
        "change_summary": "建立客服负责人个人分身",
    }


@pytest.mark.anyio
async def test_role_studio_is_database_backed_and_authorized(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/api/v1/role-studio")
        denied = await client.get(
            "/api/v1/role-studio",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        allowed = await client.get(
            "/api/v1/role-studio",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )

    assert missing.status_code == 401
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.permission_denied"
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["stats"]["template_count"] == 4
    assert payload["stats"]["instance_count"] == 4
    assert len(payload["owners"]) >= 4
    assert {item["key"] for item in payload["owners"]} >= {
        "principal-ceo-lin",
        "principal-ops-manager-zhou",
        "principal-finance-chen",
        "principal-service-demo",
    }
    assert {item["current_version_number"] for item in payload["templates"]} == {1}
    assert {item["current_version_number"] for item in payload["twins"]} == {1}
    columns = {item["name"] for item in inspect(app.state.database.engine).get_columns(
        "role_twin_profiles"
    )}
    assert "access_role_id" not in columns
    assert "role_template_id" in columns
    assert "owner_principal_id" in columns


@pytest.mark.anyio
async def test_role_template_and_twin_versions_publish_without_overwriting_history(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    admin = {"X-Zhixing-Demo-Actor": "admin"}
    ceo = {"X-Zhixing-Demo-Actor": "ceo"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created_template = await client.post(
            "/api/v1/role-templates",
            headers=admin,
            json=template_payload(),
        )
        duplicate_template = await client.post(
            "/api/v1/role-templates",
            headers=admin,
            json=template_payload(),
        )
        twin_before_template_publish = await client.post(
            "/api/v1/role-twins",
            headers=admin,
            json=twin_payload(),
        )
        published_template_v1 = await client.post(
            "/api/v1/role-templates/template-service-leader/versions/1/publish",
            headers=admin,
            json={"reason": "客服负责人确认岗位基线"},
        )
        template_v2_payload = template_payload(change_summary="增加服务质量复盘职责")
        template_v2_payload.pop("template_key")
        template_v2_payload.pop("name")
        template_v2_payload.pop("description")
        template_v2_payload["responsibilities"] = [
            "服务质量分析",
            "高风险会话升级",
            "补偿边界审查",
            "月度服务复盘",
        ]
        created_template_v2 = await client.post(
            "/api/v1/role-templates/template-service-leader/versions",
            headers=admin,
            json=template_v2_payload,
        )
        published_template_v2 = await client.post(
            "/api/v1/role-templates/template-service-leader/versions/2/publish",
            headers=admin,
            json={"reason": "发布包含月度复盘的新岗位版本"},
        )
        created_twin = await client.post(
            "/api/v1/role-twins",
            headers=admin,
            json=twin_payload(),
        )
        draft_answer = await client.post(
            "/api/v1/twins/twin-service-leader/answers",
            headers=ceo,
            json={"question": "高风险客服会话应该如何处理？"},
        )
        published_twin_v1 = await client.post(
            "/api/v1/role-twins/twin-service-leader/versions/1/publish",
            headers=admin,
            json={"reason": "客服负责人审核通过个人配置"},
        )
        repeated_publish = await client.post(
            "/api/v1/role-twins/twin-service-leader/versions/1/publish",
            headers=admin,
            json={"reason": "重复请求不得新增发布事件"},
        )
        v2_payload = twin_payload(
            voice="先给风险等级，再给客户影响、证据、责任人、时限和升级节点。"
        )
        for key in ("twin_key", "template_key", "owner_principal_key"):
            v2_payload.pop(key)
        v2_payload["change_summary"] = "强化风险等级表达"
        created_twin_v2 = await client.post(
            "/api/v1/role-twins/twin-service-leader/versions",
            headers=admin,
            json=v2_payload,
        )
        published_twin_v2 = await client.post(
            "/api/v1/role-twins/twin-service-leader/versions/2/publish",
            headers=admin,
            json={"reason": "发布客服负责人分身v2"},
        )
        answer = await client.post(
            "/api/v1/twins/twin-service-leader/answers",
            headers=ceo,
            json={"question": "高风险客服会话应该如何处理？"},
        )

    assert created_template.status_code == 200
    assert duplicate_template.status_code == 409
    assert twin_before_template_publish.status_code == 409
    assert published_template_v1.status_code == 200
    assert created_template_v2.status_code == 200
    assert published_template_v2.status_code == 200
    assert created_twin.status_code == 200
    assert draft_answer.status_code == 404
    assert published_twin_v1.status_code == 200
    assert repeated_publish.status_code == 200
    assert repeated_publish.json()["idempotent"] is True
    assert repeated_publish.json()["event"]["id"] == published_twin_v1.json()["event"]["id"]
    assert created_twin_v2.status_code == 200
    assert published_twin_v2.status_code == 200
    assert answer.status_code == 200

    studio = published_twin_v2.json()["studio"]
    template = next(
        item for item in studio["templates"] if item["key"] == "template-service-leader"
    )
    twin = next(item for item in studio["twins"] if item["key"] == "twin-service-leader")
    assert template["current_version_number"] == 2
    assert twin["current_version_number"] == 2
    assert twin["template_key"] == template["key"]
    assert twin["owner_principal_key"] == "principal-service-demo"
    assert twin["versions"][0]["voice_guide"].startswith("先给风险等级")
    assert twin["versions"][1]["voice_guide"].startswith("结论先行")
    assert {item["version_number"] for item in twin["versions"]} == {1, 2}
    with app.state.database.session() as session:
        profile = session.scalar(
            select(RoleTwinProfile).where(RoleTwinProfile.twin_key == "twin-service-leader")
        )
        assert profile is not None
        versions = list(
            session.scalars(
                select(RoleTwinVersion)
                .where(RoleTwinVersion.twin_profile_id == profile.id)
                .order_by(RoleTwinVersion.version_number)
            )
        )
        assert len(versions) == 2
        assert versions[0].voice_guide.startswith("结论先行")
        assert versions[1].voice_guide.startswith("先给风险等级")
        run = session.get(AgentRun, answer.json()["run_id"])
        assert run is not None
        assert run.role_twin_version_id == versions[1].id
        assert session.scalar(select(func.count(RoleTemplate.id))) == 5
        assert session.scalar(select(func.count(RoleTemplateVersion.id))) == 6
        assert session.scalar(select(func.count(RoleTwinVersion.id))) == 6
        assert session.scalar(select(func.count(RoleConfigurationEvent.id))) == 8
