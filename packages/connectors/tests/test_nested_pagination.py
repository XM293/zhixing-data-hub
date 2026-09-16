import pytest
from zhixing_connectors.catalog import page_parameters, resource_spec, validate_resource_parameters


def test_fbm_uses_page_and_single_string_store_with_explicit_source_time_window():
    spec = resource_spec("fbm_orders")
    assert spec is not None
    parameters = {"sid": "23", "start_time": "2026-09-01 00:00:00",
                  "end_time": "2026-09-08 00:00:00"}
    filters = validate_resource_parameters(spec, parameters)
    assert filters["sid"] == "23"
    assert page_parameters(spec, filters, 3) == {**parameters, "page": 3, "length": 100}
    for bad in ({**parameters, "sid": "23,24"}, {**parameters, "sid": True},
                {**parameters, "start_time": "2026-10-01 00:00:00"},
                {**parameters, "start_time": "2026-09-01T00:00:00Z"}):
        with pytest.raises(ValueError):
            validate_resource_parameters(spec, bad)


def test_logistics_filters_are_explicit_and_nested_pages_do_not_mutate_filters():
    spec = resource_spec("head_logistics_providers")
    assert spec is not None
    filters = validate_resource_parameters(spec, {"enabled": "0", "isAuth": "0", "payMethod": "2"})
    assert page_parameters(spec, filters, 3) == {
        "search": {"enabled": 0, "isAuth": 0, "payMethod": 2, "page": 3, "length": 20}}
    assert filters == {"enabled": 0, "isAuth": 0, "payMethod": 2}
    for bad in ({}, {**filters, "enabled": True}, {**filters, "payMethod": 0},
                {**filters, "isAuth": "01"}, {**filters, "search": {}}):
        with pytest.raises(ValueError):
            validate_resource_parameters(spec, bad)
    with pytest.raises(ValueError):
        page_parameters(spec, filters, 0)


def test_offset_and_nonpaged_contracts_are_unchanged():
    spec = resource_spec("products")
    assert spec is not None
    assert page_parameters(spec, {}, 2) == {"offset": 1000, "length": 1000}
    spec = resource_spec("shops")
    assert spec is not None
    assert page_parameters(spec, {}, 1) == {}


def test_warehouse_bin_uses_limit_and_exposes_strict_mapping_contract():
    from zhixing_connectors.catalog import can_project_to_core

    spec = resource_spec("warehouse_bins")
    assert spec is not None
    assert page_parameters(spec, {}, 3) == {"offset": 40, "limit": 20}
    # The shared catalog has a strict field-table mapper. A persisted source
    # registration may still remain schema_pending until its Raw preflight is approved.
    assert spec.schema_status == "confirmed" and can_project_to_core(spec)
