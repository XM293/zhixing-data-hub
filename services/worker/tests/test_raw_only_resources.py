import json
from types import SimpleNamespace

import httpx
import pytest
from zhixing_jobs import JobContinuation, PermanentJobError

from zhixing_worker.config import WorkerSettings
from zhixing_worker.main import _execute_lingxing_sync


@pytest.mark.parametrize("resource,size,parameters", [
    ("listings", 1000, {"sid": "23", "is_delete": "1"}),
    ("warehouse_bins", 20, {}),
    ("product_attributes", 200, {}),
    ("fbm_orders", 100, {"sid": "23", "start_time": "2026-09-01 00:00:00",
                          "end_time": "2026-09-08 00:00:00"}),
    ("inbound_orders", 200, {"start_date": "2026-09-01", "end_date": "2026-09-08"}),
    ("outbound_orders", 200, {"start_date": "2026-09-01", "end_date": "2026-09-08"}),
    ("inventory_statements", 20, {"start_date": "2026-09-01", "end_date": "2026-09-08"}),
    ("fba_inventory", 200, {}),
    ("fba_shipments", 20, {"start_date": "2026-09-01", "end_date": "2026-09-08"}),
    ("purchases", 500, {"start_date": "2026-09-01", "end_date": "2026-09-08"}),
    ("advertising", 15, {"sid": "23"}),
    ("finance", 20, {"sid": "23", "start_date": "2026-09-01",
                     "end_date": "2026-09-08"}),
    ("customer_service", 200, {"sid": "23", "start_date": "2026-09-01",
                               "end_date": "2026-09-08"}),
    ("source_reports", 1000,
     {"sid": "23", "start_date": "2026-09-01", "end_date": "2026-09-08"}),
])
def test_raw_only_resources_use_official_pagination_and_headers(
    tmp_path, resource, size, parameters,
):
    calls, committed = [], []
    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic", "expires_in": 3600}})
        body = json.loads(request.content)
        offset = (body["page"] - 1) * size if resource == "fbm_orders" else body["offset"]
        if calls:
            assert committed == [1]  # Page 1 is persisted before the next external request.
        calls.append(offset)
        length_key = "limit" if resource == "warehouse_bins" else "length"
        assert body[length_key] == size
        if resource == "warehouse_bins":
            assert "length" not in body
        if resource == "listings":
            assert body['sid'] == '23' and body['is_delete'] == 1
        if resource == "fbm_orders":
            assert "offset" not in body and body["sid"] == "23"
        if resource == "advertising":
            assert request.headers["X-API-VERSION"] == "2" and body["sid"] == 23
        elif resource == "purchases":
            assert body["search_field_time"] == "update_time"
        elif resource in {"inbound_orders", "outbound_orders"}:
            assert body["search_field_time"] == "increment_time"
        elif resource == "fba_inventory":
            assert body["is_hide_zero_stock"] == "0" and body["is_parant_asin_merge"] == "0"
            assert body["is_contain_del_ls"] == "1"
            assert body["query_fba_storage_quantity_list"] is True
        elif resource == "fba_shipments":
            assert body["time_type"] == 4 and body["is_delete"] == 2
        rows = [
            {"synthetic_key": str(index + offset), "sid": 23}
            for index in range(size if not offset else 1)
        ]
        data = ({"records": rows, "total": size + 1} if resource == "finance" else
                {"list": rows, "total": size + 1}
                if resource in {"product_attributes", "fba_shipments"} else rows)
        return httpx.Response(200, json={"code": 0, "data": data})
    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic", lingxing_enabled=True,
        source_archive_path=str(tmp_path / "raw"))
    result = _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
        "provider": "lingxing", "resource_key": resource, "resource_parameters": parameters,
        "scope_snapshot": {"enterprise_id": "a"},
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        transport=httpx.MockTransport(respond),
        persist_page=lambda manifest, payload, parameters: committed.append(manifest["page"]))
    assert calls == [0, size] and committed == [1, 2]
    assert result["row_count"] == size + 1


@pytest.mark.parametrize("resource,path", [
    ("erp_users", "/erp/sc/data/account/lists"),
    ("product_tags", "/label/operation/v1/label/product/list"),
])
def test_erp_directory_uses_one_read_only_get_without_pagination(tmp_path, resource, path):
    calls, committed = [], []

    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic", "expires_in": 3600}})
        calls.append(request.url.path)
        assert request.method == "GET" and not request.content
        assert "offset" not in request.url.params and "length" not in request.url.params
        data = ({"list": [{"label_id": "42", "label_name": "Synthetic tag"}], "total": 1}
                if resource == "product_tags" else [
                    {"uid": 42, "realname": "Synthetic ERP user", "status": 1, "is_master": 0}])
        return httpx.Response(200, json={"code": 0, "data": data})

    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic", lingxing_enabled=True,
        source_archive_path=str(tmp_path / "raw"))
    result = _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
        "provider": "lingxing", "resource_key": resource, "resource_parameters": {},
        # Run-level bounds are retained for lineage even when a directory resource has
        # no source window parameters.
        "window_start": "2026-09-08T00:00:00+00:00",
        "window_end": "2026-09-10T00:00:00+00:00",
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        transport=httpx.MockTransport(respond),
        persist_page=lambda manifest, payload, parameters: committed.append(manifest["page"]))
    assert calls == [path] and committed == [1]
    assert result["row_count"] == 1


def test_nested_logistics_pages_resume_and_persist_before_next_request(tmp_path):
    calls, committed = [], []
    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic", "expires_in": 3600}})
        body = json.loads(request.content)
        assert set(body) == {"search"}
        search = body["search"]
        page = search.pop("page")
        assert search == {"enabled": 0, "isAuth": 0, "payMethod": 2, "length": 20}
        if calls:
            assert committed == [3]
        calls.append(page)
        rows = [{"providerId": f"synthetic-{page}-{index}"}
                for index in range(20 if page == 3 else 1)]
        return httpx.Response(200, json={"code": 0, "data": {"providers": rows, "total": 61}})
    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic", lingxing_enabled=True,
        source_archive_path=str(tmp_path / "raw"))
    result = _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
        "provider": "lingxing", "resource_key": "head_logistics_providers", "checkpoint": 3,
        "resource_parameters": {"enabled": "0", "isAuth": "0", "payMethod": "2"},
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        transport=httpx.MockTransport(respond),
        persist_page=lambda manifest, payload, parameters: committed.append(manifest["page"]))
    assert calls == committed == [3, 4]
    assert result["row_count"] == 21


def test_official_nested_request_uses_reviewed_object_shape(tmp_path, monkeypatch):
    calls, committed = [], []
    monkeypatch.setattr(
        "zhixing_worker.main.resolve_order_store_filter", lambda *args, **kwargs: [23, 24]
    )

    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic",
                "expires_in": 3600}})
        body = json.loads(request.content)
        assert body == {
            "period": {"startDate": "2026-09-01", "endDate": "2026-09-02"},
            "filter": {"storeIds": [23, 24]},
            "page": {"page": 1, "length": 20},
        }
        calls.append(request.url.path)
        return httpx.Response(200, json={"code": 0, "data": {
            "list": [{"synthetic_key": "one"}], "total": 1}})

    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic",
        lingxing_enabled=True, source_archive_path=str(tmp_path / "raw"))
    result = _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
        "provider": "lingxing", "resource_key": "official_cf524a2c99e5f5f6",
        "resource_parameters": {
            "startDate": "2026-09-01", "endDate": "2026-09-02", "storeIds": "23,24",
        },
        "source_id": "synthetic-source", "probe": True,
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        transport=httpx.MockTransport(respond),
        persist_page=lambda manifest, payload, parameters: committed.append(parameters))
    assert calls == ["/basicOpen/lazadaAd/audience/report/list"]
    assert committed == [{
        "period": {"startDate": "2026-09-01", "endDate": "2026-09-02"},
        "filter": {"storeIds": [23, 24]},
    }]
    assert result["row_count"] == 1


def test_official_dependency_scalar_is_sent_as_singleton_array(tmp_path, monkeypatch):
    committed = []
    monkeypatch.setattr(
        "zhixing_worker.main.resolve_order_store_filter", lambda *args, **kwargs: [23]
    )

    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic",
                "expires_in": 3600}})
        assert request.url.path == "/amzStaServer/openapi/inbound-packing/getPrepDetails"
        assert json.loads(request.content) == {"sid": 23, "msku": ["SYN-MSKU"]}
        return httpx.Response(200, json={"code": 0, "data": [
            {"sid": "23", "msku": "SYN-MSKU", "prepOwner": "NONE"}
        ]})

    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic",
        lingxing_enabled=True, source_archive_path=str(tmp_path / "raw"))
    result = _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
        "provider": "lingxing", "resource_key": "official_4ce492e4cc82b516",
        "resource_parameters": {"sid": "23", "msku": "SYN-MSKU"},
        "source_id": "synthetic-source", "probe": True,
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        transport=httpx.MockTransport(respond),
        persist_page=lambda manifest, payload, parameters: committed.append(parameters))
    assert committed == [{"sid": 23, "msku": ["SYN-MSKU"]}]
    assert result["row_count"] == 1


def test_official_sku_dependency_is_sent_as_singleton_array(tmp_path, monkeypatch):
    committed = []
    monkeypatch.setattr(
        "zhixing_worker.main.resolve_order_store_filter", lambda *args, **kwargs: [23]
    )

    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic",
                "expires_in": 3600}})
        assert request.url.path == "/listing/publish/openapi/amazon/product/search"
        assert json.loads(request.content) == {"store_id": 23, "skus": ["SYN-SKU"]}
        return httpx.Response(200, json={"code": 0, "data": [{
            "store_id": 23, "sku": "SYN-SKU",
        }]})

    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-17", lingxing_app_secret="synthetic",
        lingxing_enabled=True, source_archive_path=str(tmp_path / "raw"))
    result = _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
        "provider": "lingxing", "resource_key": "official_04957300fd9047e6",
        "resource_parameters": {"store_id": "23", "skus": "SYN-SKU"},
        "source_id": "synthetic-source", "probe": True,
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        transport=httpx.MockTransport(respond),
        persist_page=lambda manifest, payload, parameters: committed.append(parameters))
    assert committed == [{"store_id": 23, "skus": ["SYN-SKU"]}]
    assert result["row_count"] == 1


def test_large_page_sequence_yields_only_after_committed_progress(tmp_path, monkeypatch):
    monkeypatch.setattr("zhixing_worker.main.SYNC_PAGES_PER_TURN", 2)
    committed = []
    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic", "expires_in": 3600}})
        body = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "data": [{"synthetic": body["offset"]}],
                                        "total": 999999})
    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic", lingxing_enabled=True,
        source_archive_path=str(tmp_path / "raw"))
    with pytest.raises(JobContinuation) as yielded:
        _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
            "provider": "lingxing", "resource_key": "products", "checkpoint": 7,
        }), SimpleNamespace(ensure_active=lambda: None), settings,
            transport=httpx.MockTransport(respond),
            persist_page=lambda manifest, payload, parameters: committed.append(manifest["page"]))
    assert committed == [7, 8] and yielded.value.progress == 8


def test_probe_archives_exactly_one_page_even_when_more_rows_exist(tmp_path):
    offsets, committed = [], []
    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic", "expires_in": 3600}})
        body = json.loads(request.content)
        offsets.append(body["offset"])
        return httpx.Response(200, json={"code": 0,
            "data": [{"synthetic": index} for index in range(1000)], "total": 2000})
    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic",
        lingxing_enabled=True, source_archive_path=str(tmp_path / "raw"))
    result = _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
        "provider": "lingxing", "resource_key": "products", "resource_parameters": {},
        "probe": True,
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        transport=httpx.MockTransport(respond),
        persist_page=lambda manifest, payload, parameters: committed.append(manifest["page"]))
    assert offsets == [0] and committed == [1]
    assert result["row_count"] == 1000


def test_response_shape_mismatch_is_archived_as_schema_pending(tmp_path):
    committed = []

    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic",
                "expires_in": 3600}})
        return httpx.Response(200, json={"code": 0, "data": {"unexpected": []}})

    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic",
        lingxing_enabled=True, source_archive_path=str(tmp_path / "raw"))
    with pytest.raises(PermanentJobError) as error:
        _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
            "provider": "lingxing", "resource_key": "product_attributes",
            "resource_parameters": {}, "probe": True,
        }), SimpleNamespace(ensure_active=lambda: None), settings,
            transport=httpx.MockTransport(respond),
            persist_page=lambda manifest, payload, parameters: committed.append(manifest))
    assert error.value.code == "sync.schema_pending"
    assert len(committed) == 1
    assert committed[0]["schema_status"] == "schema_pending"


def test_successful_explicit_null_collection_is_an_empty_confirmed_page(tmp_path):
    committed = []

    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic",
                "expires_in": 3600}})
        return httpx.Response(200, json={"code": 0, "data": None})

    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic",
        lingxing_enabled=True, source_archive_path=str(tmp_path / "raw"))
    result = _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
        "provider": "lingxing", "resource_key": "product_attributes",
        "resource_parameters": {}, "probe": True,
    }), SimpleNamespace(ensure_active=lambda: None), settings,
        transport=httpx.MockTransport(respond),
        persist_page=lambda manifest, payload, parameters: committed.append(manifest))
    assert result["row_count"] == 0
    assert len(committed) == 1
    assert committed[0]["schema_status"] == "confirmed"


def test_provider_business_code_is_preserved_without_response_message(tmp_path):
    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic",
                "expires_in": 3600}})
        return httpx.Response(200, json={"code": "SYNTHETIC_403",
                                        "message": "synthetic-private-response"})
    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic",
        lingxing_enabled=True, source_archive_path=str(tmp_path / "raw"))
    with pytest.raises(PermanentJobError) as error:
        _execute_lingxing_sync(SimpleNamespace(enterprise_id="a", payload={
            "provider": "lingxing", "resource_key": "head_logistics_providers",
            "resource_parameters": {"enabled": "0", "isAuth": "0", "payMethod": "2"},
        }), SimpleNamespace(ensure_active=lambda: None), settings,
            transport=httpx.MockTransport(respond))
    assert error.value.code == "sync.external_business.SYNTHETIC_403"
    assert "synthetic-private" not in str(error.value)
