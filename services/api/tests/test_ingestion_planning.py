from datetime import UTC, datetime, timedelta

import pytest

from zhixing_api.ingestion.planning import ImportRequest, ScheduleRequest, plan_import


def test_history_is_bounded_partitioned_and_uses_exact_utc_boundaries():
    request = ImportRequest.model_validate({"client_request_key": "synthetic-history",
        "projection_mode": "deferred",
        "selections": [{"resource_key": "orders", "window_start": "2026-01-01T08:00:00+08:00",
                        "window_end": "2026-01-16T08:00:00+08:00"}, {"resource_key": "shops"}]})
    pieces = plan_import(request)
    assert len(pieces) == 4
    assert all(item.projection_mode == "deferred" for item in pieces)
    assert pieces[0].window_start == datetime(2026, 1, 1, tzinfo=UTC)
    assert pieces[0].window_end == pieces[1].window_start
    assert pieces[1].window_end == pieces[2].window_start
    assert pieces[2].window_end == datetime(2026, 1, 16, tzinfo=UTC)
    assert pieces[3].window_start is None
    assert all(item.window_end - item.window_start <= timedelta(days=7)
               for item in pieces[:3])
    with pytest.raises(ValueError, match="partition_limit"):
        plan_import(ImportRequest.model_validate({"client_request_key": "too-long", "selections": [
            {"resource_key": "orders", "window_start": "2020-01-01T00:00:00Z",
             "window_end": "2026-01-01T00:00:00Z"}]}))
    with pytest.raises(ValueError, match="partition_duplicate"):
        plan_import(ImportRequest(client_request_key="duplicate", selections=[
            {"resource_key": "shops"}, {"resource_key": "shops"}]))


def test_unconfirmed_incremental_fields_cannot_be_scheduled():
    with pytest.raises(ValueError):
        ScheduleRequest(name="Synthetic fees", resource_key="finance", strategy="updated_utc",
                        initial_start=datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError):
        ScheduleRequest(name="Synthetic orders", resource_key="orders", strategy="updated_utc",
                        initial_start=datetime(2026, 1, 1))
    assert ScheduleRequest(name="Synthetic inventory", resource_key="inventory",
                           strategy="snapshot").status == "paused"
    assert ScheduleRequest(name="Synthetic ERP directory", resource_key="erp_users",
                           strategy="snapshot").status == "paused"


def test_catalog_driven_windows_support_confirmed_and_raw_only_resources():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 9, tzinfo=UTC)
    request = ImportRequest.model_validate({"client_request_key": "windowed-resources",
        "selections": [
            {"resource_key": "after_sales", "window_start": start, "window_end": end},
            {"resource_key": "fulfillments", "window_start": start, "window_end": end},
            {"resource_key": "fbm_orders", "resource_parameters": {"sid": "23"},
             "window_start": start, "window_end": end},
        ]})
    pieces = plan_import(request)
    assert [item.resource_key for item in pieces] == [
        "after_sales", "after_sales", "fulfillments", "fulfillments",
        "fbm_orders", "fbm_orders"]
    assert all(item.window_start and item.window_end for item in pieces)
    assert ScheduleRequest(name="After sales", resource_key="after_sales",
        strategy="updated_utc", initial_start=start).status == "paused"
    assert ScheduleRequest(name="Raw finance", resource_key="finance",
        resource_parameters={"sid": "23"}, strategy="source_window",
        initial_start=start).status == "paused"
    with pytest.raises(ValueError):
        ScheduleRequest(name="Wrong semantic", resource_key="finance",
            strategy="updated_utc", initial_start=start)
    with pytest.raises(ValueError):
        ImportRequest.model_validate({"client_request_key": "missing-window",
            "selections": [{"resource_key": "after_sales"}]})


def test_import_partition_uses_documented_resource_limit(monkeypatch):
    from zhixing_connectors.catalog import ResourceSpec

    spec = ResourceSpec("history", "POST", "/readonly", "W8",
        required_parameters=("start", "end"),
        window_fields=("start", "end"), window_format="date",
        schedule_strategy="source_window", max_window_days=90)
    monkeypatch.setattr("zhixing_api.ingestion.planning.resource_spec", lambda _: spec)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    selection = {"resource_key": "history", "window_start": start,
                 "window_end": start + timedelta(days=180)}
    assert ImportRequest(client_request_key="documented", selections=[selection],
                         partition_days=90).partition_days == 90
    with pytest.raises(ValueError, match="source.partition_exceeds_contract"):
        ImportRequest(client_request_key="oversized", selections=[selection],
                      partition_days=91)
