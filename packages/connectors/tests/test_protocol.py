import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from zhixing_connectors import LingxingBusinessError, LingxingClient, LingxingConfig
from zhixing_connectors.auth import AccessToken, LingxingTokenProvider, TokenProvider
from zhixing_connectors.signing import build_signature


def test_worker_token_cache_reuses_across_event_loops_and_rotates_credentials():
    from zhixing_connectors.auth import LingxingTokenCache

    requests = []

    def respond(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={"code": 200, "data": {
            "access_token": "synthetic-cached-token", "refresh_token": "synthetic-refresh",
            "expires_in": 3600,
        }})

    cache = LingxingTokenCache(transport=httpx.MockTransport(respond))
    first = cache.provider("synthetic-app-id", "synthetic-secret", "https://openapi.lingxing.com")
    assert asyncio.run(first.get()).value == "synthetic-cached-token"
    second = cache.provider("synthetic-app-id", "synthetic-secret", "https://openapi.lingxing.com")
    assert asyncio.run(second.get()).value == "synthetic-cached-token"
    assert len(requests) == 1
    changed = cache.provider("synthetic-app-id", "synthetic-rotated", "https://openapi.lingxing.com")
    asyncio.run(changed.get())
    assert len(requests) == 2


def test_http_debug_logs_do_not_expose_signed_requests(caplog):
    caplog.set_level(logging.DEBUG)

    async def token():
        return AccessToken("synthetic-log-private-token", datetime.now(UTC) + timedelta(hours=1))

    async def run():
        def respond(request):
            logging.getLogger("httpcore.http11").debug("request headers %r", request.url)
            return httpx.Response(200, json={"code": 0, "data": []})
        client = LingxingClient(
            LingxingConfig("synthetic-app-16", "synthetic-log-private-secret"),
            httpx.MockTransport(respond), TokenProvider(token),
        )
        try:
            await client.request("/erp/sc/data/seller/lists")
        finally:
            await client.close()
    asyncio.run(run())
    assert "synthetic-log-private" not in caplog.text
    assert "synthetic-app-16" not in caplog.text
    assert "access_token=" not in caplog.text


@pytest.mark.parametrize("status,classification", [(429, "rate_limited"),
    (503, "external_retryable"), (401, "external_permanent")])
def test_non_json_http_failures_are_classified_before_parsing(status, classification):
    with pytest.raises(RuntimeError, match=classification):
        LingxingClient._parse_response(httpx.Response(status, text="synthetic non-JSON error"))


def test_token_and_configuration_representations_do_not_expose_credentials():
    token = AccessToken("synthetic-private-token", datetime.now(UTC))
    config = LingxingConfig("synthetic-private-id", "synthetic-private-secret")
    assert "synthetic-private" not in repr(token) + repr(config)


@pytest.mark.parametrize("host", ["http://openapi.lingxing.com",
    "https://openapi.lingxing.com@elsewhere.test", "https://openapi.lingxing.com/path",
    "https://openapi.lingxing.com?access_token=synthetic", "https://elsewhere.test"])
def test_credentials_cannot_be_sent_to_untrusted_hosts(host):
    with pytest.raises(ValueError):
        LingxingTokenProvider("synthetic-id", "synthetic-secret", host)
    with pytest.raises(ValueError):
        LingxingClient(LingxingConfig("synthetic-id", "synthetic-secret", host))


def test_http_errors_never_expose_signed_url_or_raw_response():
    async def token():
        return AccessToken("synthetic-private-token", datetime.now(UTC) + timedelta(hours=1))

    async def run():
        def response(request):
            return httpx.Response(403, request=request, json={
                "code": 403, "message": "synthetic-private-response"})
        client = LingxingClient(LingxingConfig("synthetic-app-16", "synthetic-private-secret"),
                                 httpx.MockTransport(response), TokenProvider(token))
        try:
            with pytest.raises(RuntimeError) as error:
                await client.request("/erp/sc/data/seller/lists")
            assert "synthetic-private" not in str(error.value)
            assert str(error.value) == "external_permanent"
        finally:
            await client.close()
    asyncio.run(run())


def test_signed_get_array_uses_compact_json_on_wire():
    async def token():
        return AccessToken("synthetic-private-token", datetime.now(UTC) + timedelta(hours=1))

    async def run():
        seen = []

        def response(request):
            seen.append(request)
            return httpx.Response(200, json={"code": 0, "data": [], "total": 0})

        client = LingxingClient(
            LingxingConfig("synthetic-app-16", "synthetic-secret"),
            httpx.MockTransport(response), TokenProvider(token),
        )
        try:
            await client.request("/erp/sc/v2/cs/reviewReport/lists", params={
                "start_date": "2026-09-09", "end_date": "2026-09-10",
                "sid": [12134, 12135], "offset": 0, "length": 20,
            })
        finally:
            await client.close()
        request = seen[0]
        query = request.url.params
        assert query["sid"] == "[12134,12135]"
        signed = {
            "start_date": "2026-09-09", "end_date": "2026-09-10",
            "sid": [12134, 12135], "offset": 0, "length": 20,
            "access_token": "synthetic-private-token", "app_key": "synthetic-app-16",
            "timestamp": query["timestamp"],
        }
        assert query["sign"] == build_signature(signed, "synthetic-app-16")

    asyncio.run(run())


def test_business_error_exposes_only_bounded_machine_code():
    with pytest.raises(LingxingBusinessError) as error:
        LingxingClient._parse_response(httpx.Response(200, json={
            "code": "SYNTHETIC_410", "message": "synthetic-private-response"}))
    assert error.value.code == "SYNTHETIC_410"
    assert str(error.value) == "lingxing_business_error"
    with pytest.raises(LingxingBusinessError) as unsafe:
        LingxingClient._parse_response(httpx.Response(200, json={
            "code": "unsafe token value", "message": "synthetic-private-response"}))
    assert unsafe.value.code == "unknown"


def test_newer_amazon_code_one_success_requires_positive_envelope_marker():
    success = LingxingClient._parse_response(httpx.Response(200, json={
        "code": 1, "msg": "成功", "data": []}))
    assert success["code"] == 1
    success_with_flag = LingxingClient._parse_response(httpx.Response(200, json={
        "code": 1, "msg": "操作成功", "success": True, "data": []}))
    assert success_with_flag["success"] is True
    with pytest.raises(LingxingBusinessError) as error:
        LingxingClient._parse_response(httpx.Response(200, json={
            "code": 1, "msg": "币种不能为空"}))
    assert error.value.code == "1"


def test_method_allowlist_rejects_unknown_post_override_and_wrong_method():
    async def run():
        requests = []
        client = LingxingClient(LingxingConfig("synthetic-app-16", "synthetic-secret",
                    read_only_post_paths=frozenset({"/dangerous/write"})),
                    httpx.MockTransport(lambda request: requests.append(request)))
        try:
            with pytest.raises(ValueError):
                await client.request_json_post("/dangerous/write")
            with pytest.raises(ValueError):
                await client.request_json_post("/erp/sc/data/seller/lists")
            with pytest.raises(ValueError):
                await client.request("/erp/sc/data/mws/orders")
            assert requests == []
        finally:
            await client.close()
    asyncio.run(run())
