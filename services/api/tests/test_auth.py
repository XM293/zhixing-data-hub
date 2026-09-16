from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from zhixing_api.config import Settings
from zhixing_api.data_models import AuthSession
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'auth_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
        auth_bootstrap_password="local-test-password-2026",
    )


@pytest.mark.anyio
async def test_development_session_is_cookie_backed_and_revocable(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/auth/development/session",
            json={"login_name": "admin"},
        )
        identity = await client.get(
            "/api/v1/identity/me",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        session_identity = await client.get("/api/v1/auth/session")
        logged_out = await client.post("/api/v1/auth/logout")
        missing = await client.get("/api/v1/identity/me")

    assert created.status_code == 200, created.text
    assert created.json()["authentication_method"] == "development-session"
    assert created.json()["identity"]["actor"]["login_name"] == "admin"
    assert "zhixing_session=" in created.headers.get("set-cookie", "")
    assert identity.status_code == 200
    assert identity.json()["actor"]["login_name"] == "admin"
    assert identity.json()["actor"]["authentication_method"] == "development-session"
    assert session_identity.status_code == 200
    assert session_identity.json()["actor"]["login_name"] == "admin"
    assert logged_out.status_code == 204
    assert missing.status_code == 401

    with app.state.database.session() as session:
        stored = session.scalar(select(AuthSession))
        assert stored is not None
        assert stored.revoked_at is not None


@pytest.mark.anyio
async def test_local_password_login_uses_same_actor_context_and_bearer_session(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        invalid = await client.post(
            "/api/v1/auth/login",
            json={"login_name": "admin", "password": "wrong-password-2026"},
        )
        logged_in = await client.post(
            "/api/v1/auth/login",
            json={"login_name": "admin", "password": "local-test-password-2026"},
        )
        token = client.cookies.get("zhixing_session")
        client.cookies.clear()
        bearer_identity = await client.get(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "auth.invalid_credentials"
    assert logged_in.status_code == 200
    assert logged_in.json()["authentication_method"] == "local-password"
    assert bearer_identity.status_code == 200
    assert bearer_identity.json()["actor"]["login_name"] == "admin"
    assert bearer_identity.json()["actor"]["authentication_method"] == "local-password"
