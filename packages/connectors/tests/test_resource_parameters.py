from datetime import UTC, datetime, timedelta

import pytest
from zhixing_connectors.catalog import (
    OFFICIAL_RAW_SPECS,
    ResourceSpec,
    materialize_request_parameters,
    materialize_window_parameters,
    page_parameters,
    resource_spec,
    validate_partition_parameters,
    validate_resource_parameters,
)


def test_listing_mapping_is_confirmed_but_requires_explicit_store_and_deletion_partition():
    from zhixing_connectors.catalog import can_project_to_core

    spec = resource_spec("listings")
    assert spec is not None and can_project_to_core(spec)
    assert spec.mapping_key == "listings"
    assert spec.required_parameters == ("sid", "is_delete")
    assert validate_resource_parameters(spec, {"sid": "23", "is_delete": "1"}) == {
        "sid": 23, "is_delete": 1}
    for parameters in ({}, {"sid": "23"}, {"sid": "23", "is_delete": "2"}):
        with pytest.raises(ValueError):
            validate_resource_parameters(spec, parameters)


@pytest.mark.parametrize("key,direction", [("inbound_orders", "inbound"),
                                          ("outbound_orders", "outbound")])
def test_warehouse_document_windows_use_confirmed_mapping(key, direction):
    from zhixing_connectors.catalog import can_project_to_core, resource_spec

    spec = resource_spec(key)
    assert spec is not None
    assert spec.path == f"/erp/sc/routing/storage/{direction}/getOrders"
    assert spec.parameters == (("search_field_time", "increment_time"),)
    assert spec.required_parameters == ("start_date", "end_date")
    assert can_project_to_core(spec) and spec.schema_status == "confirmed"


def test_source_date_window_is_explicit_and_reserved_auth_fields_cannot_be_injected():
    spec = resource_spec("purchases")
    assert spec is not None and spec.schema_status == "confirmed"
    dates = {"start_date": "2026-09-01", "end_date": "2026-09-08"}
    assert validate_resource_parameters(spec, dates) == dates
    for bad in ({}, {**dates, "access_token": "synthetic"},
                {**dates, "start_date": "2026-10-01"}, {**dates, "end_date": "not-a-date"}):
        with pytest.raises(ValueError):
            validate_resource_parameters(spec, bad)


def test_catalog_materializes_windows_without_persisting_moving_dates_in_partition_identity():
    after_sales = resource_spec("after_sales")
    fbm = resource_spec("fbm_orders")
    assert after_sales is not None and fbm is not None
    assert validate_partition_parameters(after_sales, {}) == {}
    assert validate_partition_parameters(fbm, {"sid": "23"}) == {"sid": "23"}
    start = datetime(2026, 9, 1, 8, 30, tzinfo=UTC)
    end = datetime(2026, 9, 2, 9, 45, tzinfo=UTC)
    assert materialize_window_parameters(after_sales, {}, start, end) == {
        "start_date": "2026-09-01", "end_date": "2026-09-02"}
    assert materialize_window_parameters(fbm, {"sid": "23"}, start, end) == {
        "sid": "23", "start_time": "2026-09-01 08:30:00",
        "end_time": "2026-09-02 09:45:00"}
    with pytest.raises(ValueError):
        validate_partition_parameters(after_sales, {"start_date": "2026-09-01"})
    with pytest.raises(ValueError):
        materialize_window_parameters(after_sales, {}, start.replace(tzinfo=None), end)

    purchases = resource_spec("purchases")
    midnight_end = datetime(2026, 9, 8, tzinfo=UTC)
    assert purchases is not None
    assert materialize_window_parameters(
        purchases, {}, datetime(2026, 9, 1, tzinfo=UTC), midnight_end
    )["end_date"] == "2026-09-07"


def test_single_date_window_materializes_one_day_without_an_end_field():
    spec = ResourceSpec("daily", "POST", "/readonly", "W8",
        required_parameters=("sid", "event_date"), window_fields=("event_date",),
        window_format="date", schedule_strategy="source_window")
    start = datetime(2026, 9, 1, tzinfo=UTC)
    assert validate_partition_parameters(spec, {"sid": "23"}) == {"sid": 23}
    assert materialize_window_parameters(
        spec, {"sid": "23"}, start, start + timedelta(days=1)
    ) == {"sid": 23, "event_date": "2026-09-01"}
    with pytest.raises(ValueError, match="resource.source_window_invalid"):
        materialize_window_parameters(
            spec, {"sid": "23"}, start, start + timedelta(days=2))


def test_auto_store_rollout_profiles_accept_only_approved_scope_parameters():
    tested = 0
    for spec in OFFICIAL_RAW_SPECS:
        extra = set(spec.required_parameters) - set(spec.window_fields) - {
            str(spec.scope_parameter)}
        if spec.scope_kind != "store" or extra:
            continue
        value = "23" if spec.scope_parameter_mode == "scalar" else "23,24"
        parameters = {str(spec.scope_parameter): value}
        if spec.window_fields:
            validate_partition_parameters(spec, parameters)
        else:
            validate_resource_parameters(spec, parameters)
        tested += 1
    assert tested == 173


def test_nested_object_parameters_and_pagination_preserve_official_shape():
    spec = ResourceSpec(
        "nested", "POST", "/readonly", "W8", page_size=50,
        required_parameters=("startDate", "endDate", "storeIds"),
        scope_kind="store", scope_parameter="storeIds", scope_parameter_mode="list",
        parameter_paths=(
            ("startDate", ("period", "startDate")),
            ("endDate", ("period", "endDate")),
            ("storeIds", ("filter", "storeIds")),
        ),
        pagination_mode="page", pagination_path=("page",),
        pagination_page_field="page", pagination_size_field="length",
    )
    shaped = materialize_request_parameters(spec, {
        "startDate": "2026-09-01", "endDate": "2026-09-02", "storeIds": "23,24",
    })
    assert shaped == {
        "period": {"startDate": "2026-09-01", "endDate": "2026-09-02"},
        "filter": {"storeIds": [23, 24]},
    }
    assert page_parameters(spec, shaped, 3) == {
        **shaped, "page": {"page": 3, "length": 50},
    }
    assert shaped["filter"] == {"storeIds": [23, 24]}


def test_official_scalar_dependency_is_wrapped_as_the_documented_request_array():
    spec = resource_spec("official_4ce492e4cc82b516")
    assert spec is not None
    assert spec.required_parameters == ("sid", "msku")
    assert validate_resource_parameters(spec, {"sid": "23", "msku": "SYN-MSKU"}) == {
        "sid": 23, "msku": "SYN-MSKU",
    }
    assert materialize_request_parameters(spec, {"sid": 23, "msku": "SYN-MSKU"}) == {
        "sid": 23, "msku": ["SYN-MSKU"],
    }


def test_amazon_seller_id_scope_preserves_opaque_provider_identifiers():
    spec = resource_spec("official_72791537e588ec5e")
    assert spec is not None and spec.scope_parameter == "seller_id"
    assert materialize_request_parameters(spec, {
        "seller_id": "SELLER-X,SELLER-Y", "offset": 0, "length": 20,
        "start_date": "2026-09-01", "end_date": "2026-09-02",
    })["seller_id"] == ["SELLER-X", "SELLER-Y"]


def test_legacy_customer_list_uses_one_based_offset_page_numbers():
    spec = resource_spec("official_873e47220cad4d3c")
    assert spec is not None
    assert spec.pagination_mode == "page"
    assert spec.pagination_page_field == "offset"
    filters = {"sids": [23], "time_search_type": 1,
               "start_date": "2026-09-01", "end_date": "2026-09-02"}
    assert page_parameters(spec, filters, 1)["offset"] == 1
    assert page_parameters(spec, filters, 2)["offset"] == 2


def test_fba_cost_contracts_materialize_provider_month_windows():
    spec = resource_spec("official_72791537e588ec5e")
    assert spec is not None and spec.window_format == "month"
    assert materialize_window_parameters(
        spec, {"seller_id": "SELLER-X"},
        datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 8, 2, tzinfo=UTC)
    )["start_date"] == "2026-08"
    with pytest.raises(ValueError, match="resource.source_month_window_invalid"):
        materialize_window_parameters(
            spec, {"seller_id": "SELLER-X"},
            datetime(2026, 8, 31, tzinfo=UTC), datetime(2026, 9, 2, tzinfo=UTC)
        )


def test_live_promotions_and_purchase_contracts_use_provider_defaults():
    promotion = resource_spec("official_29c2ecea89316017")
    assert promotion is not None and promotion.window_format == "date"
    assert materialize_window_parameters(
        promotion, {"sellerSku": "SYN-SKU", "storeId": "23",
                    "sortField": "startTime", "sortType": "asc"},
        datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 8, 2, tzinfo=UTC)
    )["startTime"] == "2026-08-01"
    purchase = resource_spec("official_624fb6144182162d")
    assert purchase is not None and purchase.parameters == (("time_type", 1),)
    settlement = resource_spec("official_014323a3ca3de182")
    assert settlement is not None and settlement.scope_parameter_mode == "list"
    assert settlement.parameters == (("dateType", 0),)
    assert materialize_request_parameters(settlement, {
        "startDate": "2026-08-01", "endDate": "2026-08-02", "sids": "23"
    })["sids"] == [23]


def test_required_children_of_an_omitted_optional_filter_are_not_top_level_required():
    spec = resource_spec("official_2dbe32f66db9cd5b")
    assert spec is not None
    assert spec.required_parameters == ("startDate", "endDate", "sids")
    parameters = {"startDate": "2026-09-01", "endDate": "2026-09-02", "sids": "23"}
    assert validate_resource_parameters(spec, parameters) == parameters
    assert materialize_request_parameters(spec, parameters) == {
        "startDate": "2026-09-01", "endDate": "2026-09-02", "sids": [23],
    }
    assert spec.scope_namespace == "multiplatform"
    newad = resource_spec("official_271a3c2c8d3dfc09")
    assert newad is not None and newad.scope_namespace == "amazon"
    wfs = resource_spec("official_a6bb9e464ef861a1")
    assert wfs is not None and wfs.scope_namespace == "multiplatform"
    fbc = resource_spec("official_2d9184aadf4f348d")
    assert fbc is not None and fbc.scope_namespace == "multiplatform"


def test_request_shape_conflicts_fail_closed():
    spec = ResourceSpec(
        "nested", "POST", "/readonly", "W8",
        parameter_paths=(("value", ("filter", "value")),),
    )
    with pytest.raises(ValueError, match="resource.request_shape_conflict"):
        materialize_request_parameters(spec, {"filter": "invalid", "value": "safe"})


def test_reviewed_string_arrays_use_single_dependency_partitions() -> None:
    products = resource_spec("official_04957300fd9047e6")
    analysis = resource_spec("official_a2fa77b89b3172af")

    assert products is not None
    assert products.required_parameters == ("store_id", "skus")
    assert products.singleton_list_parameters == ("skus",)
    assert materialize_request_parameters(
        products, {"store_id": "23", "skus": "SYN-SKU"}
    ) == {"store_id": "23", "skus": ["SYN-SKU"]}
    assert analysis is not None
    assert analysis.required_parameters == (
        "sid", "sku", "start_date", "end_date", "group_type"
    )
    assert analysis.singleton_list_parameters == ("sku",)
    assert materialize_request_parameters(analysis, {
        "sid": "23", "sku": "SYN-MSKU", "start_date": "2026-09-01",
        "end_date": "2026-09-01", "group_type": "hourly",
    }) == {
        "sid": "23", "sku": ["SYN-MSKU"], "start_date": "2026-09-01",
        "end_date": "2026-09-01", "group_type": "hourly",
    }
