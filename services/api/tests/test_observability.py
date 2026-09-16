import json
import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from zhixing_observability import (
    TraceContext,
    bind_trace_context,
    current_trace_context,
    structured_event,
)

from zhixing_api.main import create_app

TRACE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{7,95}$")


@pytest.mark.anyio
async def test_trace_headers_are_propagated_and_invalid_values_are_replaced() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        propagated = await client.get(
            "/health/live",
            headers={"X-Request-ID": "req_external_1234", "X-Run-ID": "run_business_1234"},
        )
        replaced = await client.get(
            "/health/live",
            headers={"X-Request-ID": "invalid value\n", "X-Run-ID": "x"},
        )

    assert propagated.headers["x-request-id"] == "req_external_1234"
    assert propagated.headers["x-run-id"] == "run_business_1234"
    assert TRACE_ID_PATTERN.fullmatch(replaced.headers["x-request-id"])
    assert TRACE_ID_PATTERN.fullmatch(replaced.headers["x-run-id"])
    assert replaced.headers["x-request-id"] != "invalid value\n"
    assert current_trace_context() is None


@pytest.mark.anyio
async def test_401_and_403_use_the_same_versioned_error_envelope() -> None:
    app = create_app()

    async def unauthenticated() -> None:
        raise HTTPException(status_code=401, detail="需要登录")

    async def forbidden() -> None:
        raise HTTPException(status_code=403, detail="没有访问范围")

    app.add_api_route("/test/unauthenticated", unauthenticated)
    app.add_api_route("/test/forbidden", forbidden)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = [
            await client.get(
                "/test/unauthenticated",
                headers={"X-Request-ID": "req_auth_123456", "X-Run-ID": "run_auth_123456"},
            ),
            await client.get(
                "/test/forbidden",
                headers={"X-Request-ID": "req_deny_123456", "X-Run-ID": "run_deny_123456"},
            ),
        ]

    assert [response.status_code for response in responses] == [401, 403]
    assert [response.json()["error"]["code"] for response in responses] == [
        "auth.unauthenticated",
        "authorization.denied",
    ]
    for response in responses:
        payload = response.json()
        assert payload["schema_version"] == 1
        assert set(payload["error"]) == {
            "code",
            "message",
            "status",
            "request_id",
            "run_id",
            "retryable",
            "details",
        }
        assert payload["error"]["request_id"] == response.headers["x-request-id"]
        assert payload["error"]["run_id"] == response.headers["x-run-id"]
        assert payload["error"]["retryable"] is False


@pytest.mark.anyio
async def test_routing_validation_and_business_conflicts_share_error_contract(
    tmp_path: Path,
) -> None:
    from test_data_center import make_settings

    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        not_found = await client.get("/missing-route")
        validation = await client.post(
            "/api/v1/data-center/sources/mock-commerce/sync",
            json={"scenario": "unknown"},
        )
        conflict = await client.post(
            "/api/v1/data-center/meetings/mtg-budget-20260825/actions",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"action": "decide"},
        )

    assert not_found.json()["error"]["code"] == "resource.not_found"
    assert validation.json()["error"]["code"] == "request.validation_failed"
    assert validation.json()["error"]["details"]["issues"][0]["location"] == [
        "body",
        "scenario",
    ]
    assert conflict.json()["error"]["code"] == "resource.conflict"


def test_structured_event_contains_bound_trace_context() -> None:
    with bind_trace_context(TraceContext("req_event_1234", "run_event_1234")):
        payload = structured_event("agent.run.started", actor_id="principal_ceo")

    assert payload["request_id"] == "req_event_1234"
    assert payload["run_id"] == "run_event_1234"
    assert payload["event"] == "agent.run.started"
    assert payload["actor_id"] == "principal_ceo"
    json.dumps(payload)
