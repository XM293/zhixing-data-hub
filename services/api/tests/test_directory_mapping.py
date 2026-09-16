import pytest
from zhixing_connectors.catalog import resource_spec, validate_resource_parameters

from zhixing_api.ingestion.mapping import map_concept_shop, map_marketplace, map_multiplatform_shop


def test_master_reference_identifiers_and_supplier_retirement_are_preserved():
    from zhixing_api.ingestion.mapping import map_brand, map_category, map_supplier
    brand = map_brand({"bid": 1, "title": "Synthetic brand", "brand_code": "SB"})
    category = map_category({"cid": 2, "title": "Synthetic category", "parent_cid": 0,
                             "category_code": "SC"})
    supplier = map_supplier({"supplier_id": 3, "supplier_name": "Synthetic supplier",
        "supplier_code": "SS", "is_delete": 1, "status": 1, "status_text": "启用",
        "bank_card_number": "synthetic-sensitive-field"})
    assert brand.external_key == "1" and not brand.requires_assignment
    assert category.attributes["parent_external_key"] is None
    assert supplier.external_key == "3" and supplier.status == "inactive"
    assert "bank_card_number" not in supplier.attributes


def test_store_catalogs_do_not_alias_different_source_identifiers():
    store = map_multiplatform_shop({"store_id": "321", "sid": "91", "store_name": "Synthetic",
        "platform_code": "10008", "platform_name": "Walmart", "currency": "USD",
        "is_sync": 1, "status": 1})
    assert store.external_key == "multiplatform:321" and store.entity_type == "store"
    assert store.attributes["amazon_sid"] == "91"
    assert store.requires_assignment and store.status == "active"
    concept = map_concept_shop({"id": "91", "name": "Synthetic concept", "mid": "2000",
        "seller_id": "SYNTHETICSELLER", "region": "NA", "country": "Synthetic shared region",
        "status": 1})
    assert concept.entity_type == "concept_store" and not concept.requires_assignment
    assert concept.external_key != store.external_key
    market = map_marketplace({"mid": 1, "region": "NA", "aws_region": "NA", "country": "Synthetic",
                              "code": "US", "marketplace_id": "SYNTHETICMARKET"})
    assert market.entity_type == "marketplace" and not market.requires_assignment
    assert market.external_key == "SYNTHETICMARKET"
    assert map_marketplace({"mid": 11, "region": "CN", "aws_region": "",
        "country": "Synthetic", "code": "CN", "marketplace_id": "SYNTHETIC-CN"\
        }).attributes["aws_region"] is None
    missing_currency = map_multiplatform_shop({"store_id": "322", "sid": "",
        "store_name": "Synthetic missing currency", "platform_code": "10008",
        "platform_name": "Walmart", "currency": "", "is_sync": 1, "status": 1})
    assert missing_currency.attributes["currency_code"] is None
    assert missing_currency.attributes["quality_flags"] == ["currency_pending"]
    with pytest.raises(ValueError):
        map_multiplatform_shop({"sid": "91", "store_name": "Invalid"})
    with pytest.raises(ValueError):
        map_multiplatform_shop({"store_id": "323", "sid": "", "store_name": "Invalid",
            "platform_code": "10008", "platform_name": "Walmart", "currency": {},
            "is_sync": 1, "status": 1})


def test_country_and_month_parameters_require_official_shapes():
    regions = resource_spec("country_subdivisions")
    assert regions is not None
    assert validate_resource_parameters(regions, {"country_code": "US"}) == {"country_code": "US"}
    with pytest.raises(ValueError):
        validate_resource_parameters(regions, {"country_code": "USA"})
    rates = resource_spec("monthly_exchange_rates")
    assert rates is not None and rates.schema_status == "confirmed"
    assert validate_resource_parameters(rates, {"date": "2026-09"}) == {"date": "2026-09"}
    with pytest.raises(ValueError):
        validate_resource_parameters(rates, {"date": "2026-13"})
