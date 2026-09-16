from datetime import UTC, datetime

import pytest

from zhixing_api.connectors.contracts import (
    ConnectorBatch,
    ConnectorCursor,
    ConnectorError,
    ConnectorResourceResult,
    ConnectorSyncRequest,
    validate_connector_batch,
)


def test_incremental_request_keeps_cursor_opaque() -> None:
    request = ConnectorSyncRequest(
        mode="incremental",
        cursors=(ConnectorCursor(resource="orders", value="vendor-token-42", has_more=True),),
        window_start=datetime(2026, 9, 1, tzinfo=UTC),
        page_size=200,
    )
    assert request.cursors[0].value == "vendor-token-42"
    assert request.page_size == 200


def test_resource_result_preserves_partial_failure_and_retry_semantics() -> None:
    result = ConnectorResourceResult(
        resource="ads/performance",
        status="partial",
        fetched_count=100,
        accepted_count=96,
        cursor=ConnectorCursor(resource="ads/performance", value="p-2", has_more=True),
        source_schema_version="vendor-7",
        mapping_version="2026.09.1",
        error_code="vendor.rate_limited",
        retryable=True,
    )
    assert result.status == "partial"
    assert result.retryable is True
    assert result.accepted_count < result.fetched_count


def test_batch_validation_rejects_unversioned_or_blank_external_records() -> None:
    batch = ConnectorBatch(
        source_schema_version="vendor-7",
        mapping_version="2026.09.1",
        records=(),
        entities=(),
        metrics=(),
        warnings=(),
    )
    validate_connector_batch(batch)
    invalid = ConnectorBatch(
        source_schema_version="",
        mapping_version="2026.09.1",
        records=(),
        entities=(),
        metrics=(),
        warnings=(),
    )
    with pytest.raises(ConnectorError):
        validate_connector_batch(invalid)
