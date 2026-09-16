import asyncio

from httpx import MockTransport, Request, Response

from zhixing_api.connectors.lingxing import LingxingClient, LingxingConfig
from zhixing_api.connectors.lingxing.auth import AccessToken, TokenProvider


def test_read_only_host_and_resource():
    async def handler(request: Request):
        return Response(200, json={"code": 0, "data": []})

    c = LingxingClient(
        LingxingConfig("synthetic-app-id", "synthetic-secret"), MockTransport(handler)
    )

    async def run():
        assert (await c.request("/erp/sc/data/seller/lists"))["code"] == 0
        try:
            await c.request("/write")
            raise AssertionError("write path unexpectedly allowed")
        except ValueError:
            pass
        await c.close()

    asyncio.run(run())


def test_retry_classification_does_not_retry_permanent():
    from zhixing_api.connectors.lingxing.errors import ErrorClass, classify

    assert classify(429) == ErrorClass.RETRYABLE
    assert classify(401) == ErrorClass.PERMANENT


def test_official_post_body_participates_in_request_signing() -> None:
    captured: list[dict[str, str]] = []

    async def handler(request: Request):
        captured.append(dict(request.url.params))
        return Response(200, json={"code": 0, "data": []})

    async def fetch():
        from datetime import UTC, datetime, timedelta
        return AccessToken("synthetic-token", datetime.now(UTC) + timedelta(minutes=5))

    async def run():
        client = LingxingClient(
            LingxingConfig("synthetic-app-id", "synthetic-secret"),
            MockTransport(handler), TokenProvider(fetch),
        )
        await client.request_json_post(
            "/erp/sc/routing/data/local_inventory/productList",
            body={"offset": 0, "sku_list": ["中文"]},
        )
        await client.close()

    asyncio.run(run())
    assert captured and captured[0]["sign"]
    assert "%25" not in str(captured[0])


def test_credential_provider_is_used_without_logging_secret():
    seen: list[str] = []

    async def handler(request: Request):
        seen.append(request.headers.get("authorization", ""))
        return Response(200, json={"code": 0, "data": []})

    async def fetch():
        from datetime import UTC, datetime, timedelta

        return AccessToken("synthetic-token", datetime.now(UTC) + timedelta(minutes=5))

    async def run():
        provider = TokenProvider(fetch)
        client = LingxingClient(
            LingxingConfig("synthetic-app-id", "synthetic-secret"), MockTransport(handler), provider
        )
        await client.request("/erp/sc/data/seller/lists")
        await client.close()

    asyncio.run(run())
    # Lingxing authenticates with signed public query params; bearer headers are not sent.
    assert seen == [""]
