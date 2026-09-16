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
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'workspace_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


@pytest.mark.anyio
async def test_workspace_catalog_is_resolved_from_database_actor(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ceo = await client.get(
            "/api/v1/workspaces/me",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )
        employee = await client.get(
            "/api/v1/workspaces/me",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )

    assert ceo.status_code == 200, ceo.text
    ceo_payload = ceo.json()
    assert ceo_payload["default_workspace_key"] == "executive"
    assert [item["key"] for item in ceo_payload["workspaces"]] == ["executive"]
    assert ceo_payload["scope"]["kind"] == "enterprise"
    assert employee.status_code == 200, employee.text
    assert employee.json()["default_workspace_key"] == "operator"


@pytest.mark.anyio
async def test_workspace_read_model_reuses_authorized_metrics_and_navigation(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/workspaces/executive/read-model",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["workspace"]["key"] == "executive"
    assert payload["actor_position"]
    assert payload["actor_organization"]
    assert {item["key"] for item in payload["navigation"]} >= {
        "home",
        "cockpit",
        "data",
        "analysis",
        "meetings",
        "actions",
    }
    assert isinstance(payload["metrics"], list)
    if payload["metrics"]:
        assert {item["key"] for item in payload["metrics"]}.issubset(
            {
                "gmv_today",
                "orders_today",
                "refund_rate",
                "ad_roi",
                "active_members",
                "low_stock_skus",
            }
        )
    assert payload["quick_actions"]
    assert payload["scene"]["key"] == "enterprise-campus"


@pytest.mark.anyio
async def test_workspace_profile_and_refresh_reuse_the_same_authorized_projection(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    headers = {"X-Zhixing-Demo-Actor": "ceo"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        profile = await client.get("/api/v1/workspaces/executive", headers=headers)
        refreshed = await client.post("/api/v1/workspaces/executive/refresh", headers=headers)

    assert profile.status_code == 200, profile.text
    assert profile.json()["key"] == "executive"
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["workspace"]["key"] == profile.json()["key"]


@pytest.mark.anyio
async def test_workspace_cannot_be_used_to_escalate_role_or_scope(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        employee = await client.get(
            "/api/v1/workspaces/executive/read-model",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        unknown = await client.get(
            "/api/v1/workspaces/not-a-workspace/read-model",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )

    assert employee.status_code == 403
    assert employee.json()["error"]["code"] == "workspace.not_allowed"
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "workspace.not_found"
