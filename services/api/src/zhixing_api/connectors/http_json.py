from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from zhixing_api.connectors.contracts import (
    ConnectorBatch,
    ConnectorCursor,
    ConnectorError,
    ConnectorResourceResult,
    ConnectorSyncRequest,
    ConnectorSyncResult,
    ExternalRecord,
    IncrementalDataConnector,
    validate_connector_batch,
)


@dataclass(frozen=True, slots=True)
class JsonResourceSpec:
    name: str
    path: str
    record_type: str
    items_key: str = "items"


class HttpJsonConnector(IncrementalDataConnector):
    """Vendor-neutral HTTP JSON connector; mapping stays in a customer adapter."""

    def __init__(
        self,
        base_url: str,
        *,
        source_schema_version: str,
        mapping_version: str,
        resources: tuple[JsonResourceSpec, ...],
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.source_schema_version = source_schema_version
        self.mapping_version = mapping_version
        self.resources = resources
        self.headers = headers or {}
        self.transport = transport

    async def fetch(self, scenario: str, volume_profile: str = "standard") -> ConnectorBatch:
        result = await self.sync(ConnectorSyncRequest(mode="full"))
        return result.batch

    async def sync(self, request: ConnectorSyncRequest) -> ConnectorSyncResult:
        previous = {cursor.resource: cursor for cursor in request.cursors}
        records: list[ExternalRecord] = []
        resource_results: list[ConnectorResourceResult] = []
        warnings: list[str] = []
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=20.0,
            transport=self.transport,
        ) as client:
            for spec in self.resources:
                cursor = previous.get(spec.name)
                params: dict[str, str | int] = {"limit": request.page_size}
                if cursor and cursor.value is not None:
                    params["cursor"] = cursor.value
                if request.window_start is not None:
                    params["updated_from"] = request.window_start.isoformat()
                if request.window_end is not None:
                    params["updated_to"] = request.window_end.isoformat()
                try:
                    response = await client.get(spec.path, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ConnectorError(f"{spec.name}: response must be an object")
                    items = payload.get(spec.items_key, [])
                    if not isinstance(items, list):
                        raise ConnectorError(f"{spec.name}: {spec.items_key} must be an array")
                    observed = datetime.now(UTC)
                    accepted = 0
                    for index, item in enumerate(items):
                        if not isinstance(item, dict):
                            warnings.append(f"{spec.name}: skipped non-object item {index}")
                            continue
                        external_id = str(item.get("id") or item.get("external_id") or index)
                        records.append(
                            ExternalRecord(spec.record_type, external_id, dict(item), observed)
                        )
                        accepted += 1
                    next_value = payload.get("next_cursor")
                    next_cursor = str(next_value) if next_value is not None else None
                    resource_results.append(ConnectorResourceResult(
                        resource=spec.name,
                        status="succeeded",
                        fetched_count=len(items),
                        accepted_count=accepted,
                        cursor=ConnectorCursor(
                            spec.name, next_cursor, next_cursor is not None, next_cursor
                        ),
                        source_schema_version=self.source_schema_version,
                        mapping_version=self.mapping_version,
                    ))
                except (httpx.HTTPError, ConnectorError) as exc:
                    error_code = (
                        "connector.request_failed"
                        if isinstance(exc, httpx.HTTPError)
                        else "connector.invalid_payload"
                    )
                    warnings.append(f"{spec.name}: {error_code}")
                    resource_results.append(ConnectorResourceResult(
                        resource=spec.name,
                        status="failed",
                        fetched_count=0,
                        accepted_count=0,
                        cursor=cursor,
                        source_schema_version=self.source_schema_version,
                        mapping_version=self.mapping_version,
                        error_code=error_code,
                        retryable=isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)),
                    ))
        batch = ConnectorBatch(
            source_schema_version=self.source_schema_version,
            mapping_version=self.mapping_version,
            records=tuple(records),
            entities=(),
            metrics=(),
            warnings=tuple(warnings),
        )
        validate_connector_batch(batch)
        completed = all(
            item.status == "succeeded" and (item.cursor is None or not item.cursor.has_more)
            for item in resource_results
        )
        return ConnectorSyncResult(
            batch=batch, resources=tuple(resource_results), completed=completed
        )
