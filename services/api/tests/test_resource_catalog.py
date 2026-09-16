from zhixing_api.connectors.lingxing.resource_catalog import RESOURCE_CATALOG, can_project_to_core


def test_later_waves_are_raw_only_until_schema_confirmed():
    assert all(
        can_project_to_core(item)
        for item in RESOURCE_CATALOG
        if item.wave in {"W0", "W1", "W2", "W3"} and item.schema_status == "confirmed"
    )
    assert all(
        not can_project_to_core(item)
        for item in RESOURCE_CATALOG
        if item.schema_status == "schema_pending"
    )


def test_fulfillment_page_size_and_fba_nested_raw_contract():
    from zhixing_connectors.catalog import page_parameters, resource_spec, response_value

    fulfillment = resource_spec("fulfillments")
    assert fulfillment.mapping_key == "fulfillments"
    assert page_parameters(fulfillment, {"time_type": "update_at"}, 2) == {
        "time_type": "update_at", "page": 2, "page_size": 200}
    fba = resource_spec("fba_shipments")
    assert can_project_to_core(fba)
    assert page_parameters(fba, {}, 2) == {"offset": 20, "length": 20}
    assert response_value({"data": {"list": [{"id": "synthetic"}]}}, fba.rows_path) == [
        {"id": "synthetic"}]


def test_official_raw_profiles_require_explicit_approved_source_scope():
    from zhixing_connectors.catalog import OFFICIAL_RAW_SPECS, official_raw_spec, page_parameters
    from zhixing_connectors.official_contracts import official_contracts

    assert len(OFFICIAL_RAW_SPECS) == 265
    assert all(item.scope_kind in {"store", "warehouse"} for item in OFFICIAL_RAW_SPECS)
    assert all(item.scope_parameter in item.required_parameters for item in OFFICIAL_RAW_SPECS)
    assert all(item.mapping_key is None and item.schema_status == "confirmed"
               for item in OFFICIAL_RAW_SPECS)
    daily = next(item for item in official_contracts()
                 if item.path == "/erp/sc/data/mws_report/dailyInventory")
    spec = official_raw_spec(daily.id)
    assert spec is not None and spec.scope_parameter == "sid"
    assert set(spec.required_parameters) == {"sid", "event_date"}
    assert page_parameters(spec, {"sid": 23, "event_date": "2026-01-01"}, 2) == {
        "sid": 23, "event_date": "2026-01-01", "offset": 20, "length": 20}
    windowed = next(item for item in OFFICIAL_RAW_SPECS if item.window_fields)
    assert len(windowed.window_fields) == 2
    assert windowed.schedule_strategy == "source_window"
