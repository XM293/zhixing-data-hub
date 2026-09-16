from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.channel_identity_service import resolve_channel_principal
from zhixing_api.config import Settings
from zhixing_api.data_models import ChannelIdentityEvent
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'channel_identity_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


@pytest.mark.anyio
async def test_channel_identity_overview_is_guarded_and_minimizes_external_ids(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get(
            "/api/v1/identity/admin/channel-identities",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        allowed = await client.get(
            "/api/v1/identity/admin/channel-identities",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.permission_denied"
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["stats"] == {
        "total": 3,
        "bound": 1,
        "unknown": 2,
        "suspended": 0,
        "seen_last_24h": 3,
        "channel_count": 1,
    }
    assert len(payload["accounts"]) == 6
    assert {item["binding_status"] for item in payload["items"]} == {"bound", "unknown"}
    assert all(len(item["external_identity_fingerprint"]) == 12 for item in payload["items"])
    assert "ou_ceo_demo" not in allowed.text
    assert "ou_unknown_31" not in allowed.text


@pytest.mark.anyio
async def test_channel_identity_binding_is_versioned_idempotent_and_resolvable(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        overview = await client.get(
            "/api/v1/identity/admin/channel-identities",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )
        payload = overview.json()
        target = next(
            item for item in payload["items"] if item["id"] == "channel_identity_feishu_unknown_31"
        )
        employee = next(
            item for item in payload["accounts"] if item["account_key"] == "account_employee"
        )
        finance = next(
            item for item in payload["accounts"] if item["account_key"] == "account_finance"
        )
        bind_payload = {
            "schema_version": 1,
            "client_request_key": "channel-bind-unknown-31-001",
            "expected_version": target["version"],
            "principal_id": employee["principal_id"],
            "status": "active",
            "reason": "核对员工通讯录后绑定",
        }
        bound = await client.put(
            f"/api/v1/identity/admin/channel-identities/{target['id']}/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=bind_payload,
        )
        replay = await client.put(
            f"/api/v1/identity/admin/channel-identities/{target['id']}/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json=bind_payload,
        )
        conflicting_replay = await client.put(
            f"/api/v1/identity/admin/channel-identities/{target['id']}/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={**bind_payload, "principal_id": finance["principal_id"]},
        )
        stale = await client.put(
            f"/api/v1/identity/admin/channel-identities/{target['id']}/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                **bind_payload,
                "client_request_key": "channel-bind-unknown-31-stale",
                "principal_id": finance["principal_id"],
            },
        )

    assert bound.status_code == 200, bound.text
    assert bound.json()["identity"]["binding_status"] == "bound"
    assert bound.json()["identity"]["principal_account_key"] == "account_employee"
    assert bound.json()["identity"]["version"] == 2
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["event_id"] == bound.json()["event_id"]
    assert conflicting_replay.status_code == 409
    assert conflicting_replay.json()["error"]["code"] == "identity.channel_idempotency_conflict"
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "identity.channel_version_conflict"
    assert resolve_channel_principal(
        app.state.database,
        enterprise_id="ent_zhixing_demo",
        channel_key="feishu",
        external_tenant_key="tenant-zhixing-sandbox",
        external_identity_key="ou_unknown_31",
    ) == employee["principal_id"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unbound = await client.put(
            f"/api/v1/identity/admin/channel-identities/{target['id']}/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "schema_version": 1,
                "client_request_key": "channel-unbind-unknown-31-002",
                "expected_version": 2,
                "principal_id": None,
                "status": "active",
                "reason": "人员映射核验不一致，解除绑定",
            },
        )
        audit = await client.get(
            "/api/v1/audit/events",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            params={"source": "identity", "query": "channel.identity"},
        )

    assert unbound.status_code == 200, unbound.text
    assert unbound.json()["identity"]["binding_status"] == "unknown"
    assert resolve_channel_principal(
        app.state.database,
        enterprise_id="ent_zhixing_demo",
        channel_key="feishu",
        external_tenant_key="tenant-zhixing-sandbox",
        external_identity_key="ou_unknown_31",
    ) is None
    assert audit.status_code == 200, audit.text
    assert {item["event_type"] for item in audit.json()["items"]} == {
        "channel.identity.bound",
        "channel.identity.unbound",
    }
    assert "ou_unknown_31" not in audit.text
    assert all(
        {attribute["key"] for attribute in item["attributes"]}
        == {"channel", "state_transition"}
        for item in audit.json()["items"]
    )
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(ChannelIdentityEvent.id))) == 2


@pytest.mark.anyio
async def test_channel_identity_rejects_duplicate_principal_and_supports_suspension(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        overview = await client.get(
            "/api/v1/identity/admin/channel-identities",
            headers={"X-Zhixing-Demo-Actor": "admin"},
        )
        payload = overview.json()
        ceo_identity = next(item for item in payload["items"] if item["binding_status"] == "bound")
        unknown = next(
            item for item in payload["items"] if item["id"] == "channel_identity_feishu_unknown_47"
        )
        duplicate = await client.put(
            f"/api/v1/identity/admin/channel-identities/{unknown['id']}/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "channel-duplicate-ceo-001",
                "expected_version": unknown["version"],
                "principal_id": ceo_identity["principal_id"],
                "status": "active",
                "reason": "重复绑定校验",
            },
        )
        suspended = await client.put(
            f"/api/v1/identity/admin/channel-identities/{ceo_identity['id']}/configuration",
            headers={"X-Zhixing-Demo-Actor": "admin"},
            json={
                "client_request_key": "channel-suspend-ceo-002",
                "expected_version": ceo_identity["version"],
                "principal_id": ceo_identity["principal_id"],
                "status": "suspended",
                "reason": "渠道账号异常，暂停解析",
            },
        )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "identity.channel_principal_conflict"
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["identity"]["binding_status"] == "suspended"
    assert resolve_channel_principal(
        app.state.database,
        enterprise_id="ent_zhixing_demo",
        channel_key="feishu",
        external_tenant_key="tenant-zhixing-sandbox",
        external_identity_key="ou_ceo_demo",
    ) is None
