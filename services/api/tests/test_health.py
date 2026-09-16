import pytest
from httpx import ASGITransport, AsyncClient

from zhixing_api.main import create_app


@pytest.mark.anyio
async def test_live_and_ready_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("FILE_ASSET_STORAGE_PROVIDER", "local")
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {
        "service": "zhixing-api",
        "status": "live",
        "version": "0.1.0",
        "environment": "development",
    }
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


@pytest.mark.anyio
async def test_cors_allows_local_web() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        preflight = await client.options(
            "/health/live",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        response = await client.get(
            "/health/live",
            headers={"Origin": "http://127.0.0.1:3000"},
        )

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]
    assert "X-Run-ID" in response.headers["access-control-expose-headers"]
