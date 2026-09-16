import asyncio
from datetime import UTC, datetime, timedelta

from zhixing_api.connectors.lingxing.auth import AccessToken, TokenProvider


def test_lingxing_token_provider_uses_mock_transport_and_refreshes_business_failure() -> None:
    from httpx import MockTransport, Request, Response

    from zhixing_api.connectors.lingxing.auth import LingxingTokenProvider

    calls: list[str] = []

    async def handler(request: Request) -> Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/refresh"):
            return Response(200, json={"code": 401, "data": None})
        return Response(200, json={"code": 200, "data": {
            "access_token": "synthetic-token",
            "refresh_token": "synthetic-refresh",
            "expires_in": 7200,
        }})

    async def run():
        provider = LingxingTokenProvider(
            "synthetic-app-id", "synthetic-secret", "https://openapi.lingxing.com",
            transport=MockTransport(handler),
        )
        token = await provider.get()
        assert token.value == "synthetic-token"
        provider._access = AccessToken("expired-synthetic", datetime.now(UTC))
        refreshed = await provider.get()
        assert refreshed.value == "synthetic-token"
        return calls

    assert asyncio.run(run()) == ["/api/auth-server/oauth/access-token",
                                 "/api/auth-server/oauth/refresh",
                                 "/api/auth-server/oauth/access-token"]


def test_token_refreshes_before_expiry():
    calls = []

    async def fetch():
        calls.append(1)
        return AccessToken(f"t{len(calls)}", datetime.now(UTC) + timedelta(seconds=120))

    async def run():
        provider = TokenProvider(fetch)
        assert (await provider.get()).value == "t1"
        assert (await provider.get()).value == "t1"
        provider._token = AccessToken("old", datetime.now(UTC) + timedelta(seconds=1))
        assert (await provider.get()).value == "t2"

    asyncio.run(run())
    assert len(calls) == 2
