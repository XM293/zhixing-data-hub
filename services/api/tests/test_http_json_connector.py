import httpx
import pytest

from zhixing_api.connectors.contracts import ConnectorCursor, ConnectorSyncRequest
from zhixing_api.connectors.http_json import HttpJsonConnector, JsonResourceSpec


@pytest.mark.anyio
async def test_http_json_connector_preserves_cursor_and_vendor_payload() -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(
            200,
            json={"items": [{"id": "ORD-1", "vendor_state": "PAID"}], "next_cursor": "p2"},
        )

    connector = HttpJsonConnector(
        "http://vendor.test",
        source_schema_version="vendor-2026-09",
        mapping_version="customer-map-1",
        resources=(JsonResourceSpec("orders", "/orders", "orders"),),
        transport=httpx.MockTransport(handler),
    )
    result = await connector.sync(ConnectorSyncRequest(
        mode="incremental",
        cursors=(ConnectorCursor("orders", "p1"),),
        page_size=100,
    ))
    assert calls == [{"limit": "100", "cursor": "p1"}]
    assert result.completed is False
    assert result.resources[0].cursor is not None
    assert result.resources[0].cursor.next_value == "p2"
    assert result.batch.records[0].payload["vendor_state"] == "PAID"


@pytest.mark.anyio
async def test_http_json_connector_marks_transport_failure_retryable() -> None:
    connector = HttpJsonConnector(
        "http://vendor.test",
        source_schema_version="vendor-1",
        mapping_version="map-1",
        resources=(JsonResourceSpec("orders", "/orders", "orders"),),
        transport=httpx.MockTransport(
            lambda _: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))
        ),
    )
    result = await connector.sync(ConnectorSyncRequest(mode="full"))
    assert result.resources[0].status == "failed"
    assert result.resources[0].retryable is True
