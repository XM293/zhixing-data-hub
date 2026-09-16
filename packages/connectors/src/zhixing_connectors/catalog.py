import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from importlib.resources import files

from .official_contracts import (
    OFFICIAL_CONTRACT_VERSION,
    OfficialContract,
    official_contract,
    official_contracts,
)

CATALOG_VERSION = "lingxing-2026-09-14.37"


@dataclass(frozen=True)
class ResourceSpec:
    key: str
    method: str
    path: str
    wave: str
    schema_status: str = "confirmed"
    page_size: int = 1000
    paginated: bool = True
    parameters: tuple[tuple[str, object], ...] = ()
    mapping_key: str | None = None
    documentation: str = ""
    required_parameters: tuple[str, ...] = ()
    headers: tuple[tuple[str, str], ...] = ()
    rows_path: tuple[str, ...] = ("data",)
    total_path: tuple[str, ...] = ("total",)
    end_exclusive: bool = False
    execution_mode: str = "pages"
    pagination_mode: str = "offset"
    window_fields: tuple[str, ...] = ()
    window_format: str | None = None
    schedule_strategy: str | None = None
    scope_kind: str | None = None
    scope_parameter: str | None = None
    scope_parameter_mode: str | None = None
    max_window_days: int = 7
    retention_days: int | None = None
    parameter_paths: tuple[tuple[str, tuple[str, ...]], ...] = ()
    pagination_path: tuple[str, ...] = ()
    pagination_page_field: str | None = None
    pagination_size_field: str | None = None
    singleton_list_parameters: tuple[str, ...] = ()
    scope_namespace: str | None = None


RESOURCE_CATALOG = (
    ResourceSpec("listings", "POST", "/erp/sc/data/mws/listing", "W1", mapping_key="listings",
                 required_parameters=("sid", "is_delete"), documentation="Sale/Listing"),
    ResourceSpec("erp_users", "GET", "/erp/sc/data/account/lists", "W0", paginated=False,
                 mapping_key="erp_users", documentation="BasicData/AccoutLists"),
    ResourceSpec("shops", "GET", "/erp/sc/data/seller/lists", "W0", paginated=False,
                 mapping_key="shops", documentation="BasicData/SellerLists"),
    ResourceSpec("marketplaces", "GET", "/erp/sc/data/seller/allMarketplace", "W0",
                 paginated=False, mapping_key="marketplaces",
                 documentation="BasicData/AllMarketplace"),
    ResourceSpec("concept_shops", "GET", "/erp/sc/data/seller/conceptLists", "W0",
                 paginated=False, mapping_key="concept_shops",
                 documentation="BasicData/ConceptSellerLists"),
    ResourceSpec("multiplatform_shops", "POST", "/pb/mp/shop/v2/getSellerList", "W0",
                 page_size=200, mapping_key="multiplatform_shops", rows_path=("data", "list"),
                 total_path=("data", "total"), documentation="MultiPlatform/V2/StoreInfoV2"),
    ResourceSpec("country_subdivisions", "POST", "/erp/sc/data/worldState/lists", "W0",
                 paginated=False, mapping_key="country_subdivisions",
                 required_parameters=("country_code",), documentation="BasicData/WorldStateLists"),
    ResourceSpec("multiplatform_subdivisions", "POST",
                 "/basicOpen/multiplatform/profit/report/stateList", "W0", paginated=False,
                 mapping_key="multiplatform_subdivisions", required_parameters=("countryCode",),
                 rows_path=("data", "states"), documentation="BasicData/StateList"),
    ResourceSpec("monthly_exchange_rates", "POST", "/erp/sc/routing/finance/currency/currencyMonth",
                 "W0", paginated=False, required_parameters=("date",),
                 mapping_key="monthly_exchange_rates", documentation="BasicData/Currency"),
    ResourceSpec("products", "POST", "/erp/sc/routing/data/local_inventory/productList", "W1",
                 mapping_key="products", documentation="Product/ProductLists"),
    ResourceSpec("product_styles", "POST", "/erp/sc/routing/storage/spu/spuList", "W1",
                 page_size=200, mapping_key="product_styles", documentation="Product/spuList"),
    ResourceSpec("product_attributes", "POST", "/erp/sc/routing/storage/attribute/attributeList",
                 "W1", page_size=200, rows_path=("data", "list"),
                 total_path=("data", "total"), mapping_key="product_attributes",
                 documentation="Product/attributeList"),
    ResourceSpec("brands", "POST", "/erp/sc/data/local_inventory/brand", "W1",
                 mapping_key="brands", documentation="Product/Brand"),
    ResourceSpec("product_tags", "GET", "/label/operation/v1/label/product/list", "W1",
                 paginated=False, rows_path=("data", "list"), total_path=("data", "total"),
                 mapping_key="product_tags", documentation="Product/GetProductTag"),
    ResourceSpec("logistics_channels", "POST", "/erp/sc/data/local_inventory/channelList", "W1",
                 page_size=20, mapping_key="logistics_channels",
                 documentation="Logistics/ChannelList"),
    ResourceSpec("product_categories", "POST", "/erp/sc/routing/data/local_inventory/category",
                 "W1", mapping_key="product_categories", documentation="Product/Category"),
    ResourceSpec("suppliers", "POST", "/erp/sc/data/local_inventory/supplier", "W1",
                 mapping_key="suppliers", documentation="Purchase/Supplier"),
    ResourceSpec("head_logistics_providers", "POST",
                 "/basicOpen/logistics/headLogisticsProvider/query/list", "W1",
                 mapping_key="head_logistics_providers", page_size=20,
                 pagination_mode="search_page",
                 required_parameters=("enabled", "isAuth", "payMethod"),
                 rows_path=("data", "providers"), total_path=("data", "total"),
                 documentation="Logistics/QueryHeadLogisticsProvider"),
    *(ResourceSpec(f"warehouses_{key}", "POST", "/erp/sc/data/local_inventory/warehouse", "W1",
                   parameters=(("type", kind), ("is_delete", "0,1")), mapping_key="warehouses",
                   documentation="Warehouse/WarehouseLists")
      for key, kind in (("local", 1), ("overseas", 3), ("platform", 4), ("awd", 6))),
    ResourceSpec("orders", "POST", "/erp/sc/data/mws/orders", "W2", mapping_key="orders",
                 documentation="Sale/Orderlists", parameters=(("date_type", 3),),
                 required_parameters=("start_date", "end_date"),
                 window_fields=("start_date", "end_date"), window_format="datetime",
                 schedule_strategy="updated_utc"),
    ResourceSpec("fbm_orders", "POST", "/erp/sc/routing/order/Order/getOrderList", "W2",
                 page_size=100, pagination_mode="page", mapping_key="fbm_orders",
                 required_parameters=("sid", "start_time", "end_time"),
                 window_fields=("start_time", "end_time"), window_format="datetime",
                 schedule_strategy="source_window",
                 documentation="Sale/FBMOrderList"),
    ResourceSpec("warehouse_bins", "POST", "/erp/sc/routing/data/local_inventory/warehouseBin",
                 "W1", page_size=20, pagination_mode="offset_limit",
                 mapping_key="warehouse_bins", schema_status="confirmed",
                 documentation="Warehouse/warehouseBin"),
    ResourceSpec("after_sales", "POST", "/erp/sc/routing/amzod/order/afterSaleList", "W2",
                 mapping_key="after_sales", documentation="Sale/afterSaleList",
                 parameters=(("date_type", 3),), end_exclusive=True,
                 required_parameters=("start_date", "end_date"),
                 window_fields=("start_date", "end_date"), window_format="date",
                 schedule_strategy="updated_utc"),
    ResourceSpec("fulfillments", "POST", "/erp/sc/routing/wms/order/wmsOrderList", "W3",
                 page_size=200, pagination_mode="page_size", mapping_key="fulfillments",
                 parameters=(("time_type", "update_at"),),
                 required_parameters=("start_date", "end_date"),
                 window_fields=("start_date", "end_date"), window_format="date",
                 schedule_strategy="updated_utc",
                 documentation="Warehouse/WmsOrderList"),
    ResourceSpec("fba_shipments", "POST",
                 "/erp/sc/routing/storage/shipment/getInboundShipmentList", "W3",
                 page_size=20, mapping_key="fba_shipments",
                 parameters=(("time_type", 4), ("is_delete", 2)),
                 required_parameters=("start_date", "end_date"),
                 window_fields=("start_date", "end_date"), window_format="date",
                 schedule_strategy="source_window",
                 rows_path=("data", "list"), total_path=("data", "total"),
                 documentation="FBA/GetInboundShipmentList"),
    ResourceSpec("inventory", "POST", "/erp/sc/routing/data/local_inventory/inventoryDetails",
                 "W3", page_size=800, mapping_key="inventory",
                 documentation="Warehouse/InventoryDetails"),
    *(ResourceSpec(f"{direction}_orders", "POST",
                   f"/erp/sc/routing/storage/{direction}/getOrders", "W3",
                   page_size=200, mapping_key=f"{direction}_orders",
                   parameters=(("search_field_time", "increment_time"),),
                   required_parameters=("start_date", "end_date"),
                   window_fields=("start_date", "end_date"), window_format="date",
                   schedule_strategy="source_window",
                   documentation=f"Warehouse/{direction}getOrders")
      for direction in ("inbound", "outbound")),
    ResourceSpec("inventory_statements", "POST",
                 "/erp/sc/routing/inventoryLog/WareHouseInventory/wareHouseCenterStatement",
                 "W3", page_size=20, end_exclusive=True,
                 mapping_key="inventory_statements",
                 required_parameters=("start_date", "end_date"),
                 window_fields=("start_date", "end_date"), window_format="date",
                 schedule_strategy="source_window",
                 documentation="Warehouse/WarehouseStatementNew"),
    ResourceSpec("fba_inventory", "POST", "/basicOpen/openapi/storage/fbaWarehouseDetail",
                 "W3", page_size=200, mapping_key="fba_inventory",
                 parameters=(("is_hide_zero_stock", "0"), ("is_parant_asin_merge", "0"),
                             ("is_contain_del_ls", "1"), ("query_fba_storage_quantity_list", True)),
                 documentation="Warehouse/FBAStock_v2"),
    ResourceSpec("purchases", "POST", "/erp/sc/routing/data/local_inventory/purchaseOrderList",
                 "W4", page_size=500, mapping_key="purchases",
                 parameters=(("search_field_time", "update_time"),),
                 documentation="Purchase/PurchaseOrderList",
                 required_parameters=("start_date", "end_date"),
                 window_fields=("start_date", "end_date"), window_format="date",
                 schedule_strategy="source_window"),
    ResourceSpec("advertising", "POST", "/pb/openapi/newad/spCampaigns", "W5",
                 page_size=15, mapping_key="advertising",
                 documentation="newAd/baseData/spCampaigns",
                 required_parameters=("sid",), headers=(("X-API-VERSION", "2"),)),
    ResourceSpec("finance", "POST", "/bd/fee/management/open/feeManagement/otherFee/list",
                 "W6", page_size=20, parameters=(("date_type", "gmt_create"),),
                 mapping_key="finance",
                 documentation="Finance/feeManagementList",
                 required_parameters=("sid", "start_date", "end_date"),
                 window_fields=("start_date", "end_date"), window_format="date",
                 schedule_strategy="source_window",
                 rows_path=("data", "records"), total_path=("data", "total")),
    ResourceSpec("customer_service", "POST", "/basicOpen/openapi/service/v3/data/mws/reviews",
                 "W7", page_size=200, mapping_key="customer_service",
                 parameters=(("date_field", "last_update_time"),), documentation="Service/reviewV2",
                 required_parameters=("sid", "start_date", "end_date"),
                 window_fields=("start_date", "end_date"), window_format="date",
                 schedule_strategy="source_window"),
    ResourceSpec("source_reports", "POST", "/erp/sc/data/mws_report/allOrders",
                 "W8", parameters=(("date_type", 2),), mapping_key="source_reports",
                 documentation="SourceData/AllOrders", end_exclusive=True,
                 required_parameters=("sid", "start_date", "end_date"),
                 window_fields=("start_date", "end_date"), window_format="date",
                 schedule_strategy="source_window"),
    ResourceSpec("report_export_status", "POST", "/basicOpen/report/query/reportExportTask",
                 "W8", "schema_pending", paginated=False,
                 documentation="Statistics/reportQueryReportExportTask",
                 required_parameters=("seller_id", "task_id", "region"),
                 execution_mode="async_report"),
)
_EXPLICIT_OPERATIONS = frozenset((item.method, item.path) for item in RESOURCE_CATALOG)

_PAGING_FIELDS = frozenset({
    "offset", "length", "limit", "page", "pagesize", "size", "current", "pageno",
    "pagenum",
})
_STORE_SCOPE_FIELDS = frozenset({
    "sid", "sids", "sidlist", "sellerid", "sellerids", "storeid", "storeids",
    "shopid", "shopids",
})
_WAREHOUSE_SCOPE_FIELDS = frozenset({
    "wid", "wids", "widlist", "warehouseid", "warehouseids",
})
_SINGLETON_LIST_PARAMETERS: dict[str, frozenset[str]] = {
    # The official contract accepts up to 100 MSKUs. Keep one Raw-derived MSKU per
    # immutable partition first; batching can be added without changing its scope.
    "official_4ce492e4cc82b516": frozenset({"msku"}),
    # Keep source-derived SKU identity immutable; only the provider request uses an array.
    "official_04957300fd9047e6": frozenset({"skus"}),
    "official_a2fa77b89b3172af": frozenset({"sku"}),
}
_ALTERNATIVE_REQUIRED_PARAMETERS: dict[str, dict[str, str]] = {
    # The official field table marks both identifiers required while its description
    # states that an approved sid or a profile_id is sufficient.
    "official_a2fa77b89b3172af": {
        "profile_id": "sid跟profile_id其中一个必填",
    },
}
_MONTH_WINDOW_CONTRACTS = frozenset({
    "official_72791537e588ec5e",  # FBA cost gather: provider requires Y-m
    "official_a681ef5b8dc2b61c",  # FBA cost detail: provider requires Y-m
})
_DATE_WINDOW_CONTRACTS = frozenset({
    # The promotion endpoints document date-only boundaries in live responses
    # even though the extracted catalog classified their fields as datetime.
    "official_29c2ecea89316017",
    "official_8b8601849b0f6be8",
    "official_96b436a7b7ce62d2",
    "official_ad32c4bc796136f3",
    "official_e798e99c2011756a",
})

# Some legacy Lingxing endpoints call their page-number field ``offset`` even
# though the provider requires 1, 2, ... rather than a zero-based row offset.
# Keep this provider quirk explicit instead of changing the default for the
# many endpoints that really use zero-based offsets.
_ONE_BASED_OFFSET_CONTRACTS = frozenset({
    "official_873e47220cad4d3c",  # legacy customer list: offset defaults to 1
})
_OFFICIAL_DEFAULT_PARAMETERS: dict[str, tuple[tuple[str, object], ...]] = {
    # The provider treats these documented-optional selectors as required at
    # runtime; defaults keep the read-only acquisition deterministic.
    "official_624fb6144182162d": (("time_type", 1),),
    "official_014323a3ca3de182": (("dateType", 0),),
}

# The export URL endpoint documents both fields as optional, but the provider
# rejects seller_id-only requests. The ID is emitted by settlement summary
# responses and must be supplied through the normal dependency fanout.
_ADDITIONAL_REQUIRED_PARAMETERS: dict[str, tuple[str, ...]] = {
    "official_ae7c34d7d1faf90a": ("financial_event_group_id",),
}
_MULTIPLATFORM_PATH_MARKERS = (
    "/multiplatform", "/pb/mp/", "lazada", "tiktok", "temu", "walmart",
    "shein", "shopify", "mercado", "aliexpress", "ebay", "/fbt", "/full/",
    # Lingxing FBC is the Cdiscount platform-warehouse service, not Amazon FBA.
    "/fbc/",
)


def _scope_namespace(contract: OfficialContract, kind: str) -> str | None:
    if kind != "store":
        return None
    contract_identity = f"{contract.path} {contract.documentation_url}".lower()
    return ("multiplatform" if any(
        marker in contract_identity for marker in _MULTIPLATFORM_PATH_MARKERS)
            else "amazon")


def _normalized_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _scope_profile(contract: OfficialContract) -> tuple[str, str, str] | None:
    fields = {field.name: field for field in contract.request_fields}
    for name in contract.scope_fields:
        normalized = _normalized_field(name)
        kind = ("store" if normalized in _STORE_SCOPE_FIELDS else
                "warehouse" if normalized in _WAREHOUSE_SCOPE_FIELDS else None)
        if kind is None:
            continue
        field = fields[name]
        description = field.description
        mode = ("list" if any(token in field.type for token in ("array", "list")) else
                "csv" if normalized.endswith(("ids", "list"))
                or any(token in description for token in ("多个", "逗号", "多选")) else "scalar")
        return kind, name, mode
    return None


def _newad_store_raw_spec(contract: OfficialContract) -> ResourceSpec | None:
    if (contract.extraction_status != "confirmed"
            or contract.method != "POST"
            or not contract.path.startswith("/pb/openapi/newad/")
            or contract.pagination_mode != "offset_length"
            or contract.rows_path != ("data",)
            or contract.total_path != ("total",)):
        return None
    fields = {field.name: field for field in contract.request_fields}
    sid = fields.get("sid")
    if sid is None or not sid.required or sid.path != ("sid",):
        return None
    profile = fields.get("profile_id")
    if profile is not None and profile.required:
        description = profile.description.replace(" ", "")
        if "sid跟profile_id其中一个必填" not in description:
            return None
    required = tuple(dict.fromkeys(
        field.name for field in contract.request_fields
        if field.required and field.name not in {"profile_id", "offset", "length"}
    ))
    if "sid" not in required:
        return None
    window_fields = (("report_date",) if "report_date" in required else
                     contract.window_fields if len(contract.window_fields) == 2 else ())
    return ResourceSpec(
        key=contract.runtime_key,
        method=contract.method,
        path=contract.path,
        wave=contract.wave,
        schema_status="confirmed",
        page_size=15,
        required_parameters=required,
        rows_path=contract.rows_path,
        total_path=contract.total_path,
        documentation=contract.documentation_url,
        pagination_mode="offset",
        window_fields=window_fields,
        window_format="date" if window_fields else None,
        schedule_strategy="source_window" if window_fields else None,
        scope_kind="store",
        scope_parameter="sid",
        scope_parameter_mode="scalar",
        scope_namespace="amazon",
        max_window_days=1 if len(window_fields) == 1 else contract.max_window_days or 7,
        headers=(("X-API-VERSION", "2"),),
    )


def _unreviewed_official_raw_spec(contract: OfficialContract) -> ResourceSpec | None:
    if contract.path.startswith("/pb/openapi/newad/"):
        return _newad_store_raw_spec(contract)
    scope = _scope_profile(contract)
    if (contract.extraction_status != "confirmed" or contract.pagination_mode == "unknown"
            or scope is None or (contract.method, contract.path) in _EXPLICIT_OPERATIONS):
        return None
    rows_path = contract.rows_path
    if not rows_path and any(field.path == ("data",) for field in contract.response_fields):
        rows_path = ("data",)
    if not rows_path:
        return None
    pagination = {"offset_length": "offset", "offset_limit": "offset_limit",
                  "none": "offset"}.get(contract.pagination_mode)
    if contract.runtime_key in _ONE_BASED_OFFSET_CONTRACTS:
        pagination = "page"
    if contract.pagination_mode == "page":
        names = {_normalized_field(field.name) for field in contract.request_fields}
        pagination = "page_size" if names.intersection({"pagesize", "size"}) else "page"
    if pagination is None:
        return None
    window_format = ("month" if contract.runtime_key in _MONTH_WINDOW_CONTRACTS else
                     "date" if contract.runtime_key in _DATE_WINDOW_CONTRACTS else
                     contract.window_format)
    window_fields = (contract.window_fields if len(contract.window_fields) in {1, 2}
                     and window_format in {"date", "datetime", "month"} else ())
    kind, parameter, mode = scope
    if contract.runtime_key == "official_014323a3ca3de182":
        # This endpoint rejects the catalog's scalar/csv representation and
        # requires a JSON array of numeric store ids.
        mode = "list"
    namespace = _scope_namespace(contract, kind)
    fields_by_path = {field.path: field for field in contract.request_fields}
    alternative_required = _ALTERNATIVE_REQUIRED_PARAMETERS.get(
        contract.runtime_key, {})
    for name, evidence in alternative_required.items():
        matches = [field for field in contract.request_fields if field.name == name]
        if (len(matches) != 1 or not matches[0].required or matches[0].path != (name,)
                or evidence not in matches[0].description.replace(" ", "")):
            return None
    required_fields = [field for field in contract.request_fields
                       if field.required and field.name not in alternative_required and not any(
        (ancestor := fields_by_path.get(field.path[:length])) is not None
        and not ancestor.required
        and any(token in ancestor.type.lower() for token in ("array", "list", "object"))
        for length in range(1, len(field.path))
    )]
    container_paths = {field.path for field in required_fields if any(
        other.path[:len(field.path)] == field.path and len(other.path) > len(field.path)
        for other in required_fields)}
    leaf_required = [field.name for field in required_fields
                     if field.path not in container_paths
                     and _normalized_field(field.name) not in _PAGING_FIELDS]
    required = tuple(dict.fromkeys([
        *leaf_required, *window_fields, parameter,
        *_ADDITIONAL_REQUIRED_PARAMETERS.get(contract.runtime_key, ()),
    ]))
    selected: dict[str, tuple[str, ...]] = {}
    singleton_lists = _SINGLETON_LIST_PARAMETERS.get(contract.runtime_key, frozenset())
    for name in required:
        choices = [field for field in contract.request_fields if field.name == name]
        required_choices = [field for field in choices if field.required]
        if len(required_choices) == 1:
            choices = required_choices
        if len(choices) != 1:
            return None
        field = choices[0]
        marker = field.type.lower()
        if (name != parameter and any(token in marker for token in ("array", "list"))
                and (name not in singleton_lists or field.path != (name,))):
            return None
        for length in range(1, len(field.path)):
            ancestor = fields_by_path.get(field.path[:length])
            if ancestor is not None and any(
                    token in ancestor.type.lower() for token in ("array", "list")):
                return None
        selected[name] = field.path

    pagination_path: tuple[str, ...] = ()
    pagination_page_field: str | None = None
    pagination_size_field: str | None = None
    if contract.pagination_mode != "none":
        page_names = ({"offset"} if contract.pagination_mode.startswith("offset_") else
                      {"page", "pageno", "pagenum", "current"})
        size_names = ({"length"} if contract.pagination_mode == "offset_length" else
                      {"limit"} if contract.pagination_mode == "offset_limit" else
                      {"pagesize", "length", "size"})
        page_fields = [field for field in contract.request_fields
                       if _normalized_field(field.name) in page_names
                       and not any(token in field.type.lower() for token in ("object", "array"))]
        size_fields = [field for field in contract.request_fields
                       if _normalized_field(field.name) in size_names
                       and not any(token in field.type.lower() for token in ("object", "array"))]
        if len(page_fields) != 1 or len(size_fields) != 1:
            return None
        page_field, size_field = page_fields[0], size_fields[0]
        if page_field.path[:-1] != size_field.path[:-1]:
            return None
        pagination_path = page_field.path[:-1]
        pagination_page_field = page_field.name
        pagination_size_field = size_field.name
    return ResourceSpec(key=contract.runtime_key, method=contract.method, path=contract.path,
        wave=contract.wave, schema_status="confirmed", page_size=20,
        parameters=_OFFICIAL_DEFAULT_PARAMETERS.get(contract.runtime_key, ()),
        paginated=contract.pagination_mode != "none", required_parameters=required,
        rows_path=rows_path, total_path=contract.total_path, mapping_key=None,
        documentation=contract.documentation_url, pagination_mode=pagination,
        window_fields=window_fields,
        window_format=window_format if window_fields else None,
        schedule_strategy="source_window" if window_fields else None,
        scope_kind=kind, scope_parameter=parameter, scope_parameter_mode=mode,
        max_window_days=contract.max_window_days or 7,
        retention_days=contract.retention_days,
        parameter_paths=tuple(sorted(
            (name, path) for name, path in selected.items() if len(path) > 1)),
        pagination_path=pagination_path,
        pagination_page_field=pagination_page_field,
        pagination_size_field=pagination_size_field,
        singleton_list_parameters=tuple(sorted(singleton_lists)),
        scope_namespace=namespace)


def _load_readonly_allowlist() -> tuple[str, dict[str, dict[str, object]]]:
    path = files("zhixing_connectors").joinpath(
        "lingxing_official_readonly_allowlist.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (payload.get("schema_version") != 1
            or payload.get("official_contract_version") != OFFICIAL_CONTRACT_VERSION):
        raise RuntimeError("lingxing.readonly_allowlist_stale")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError("lingxing.readonly_allowlist_invalid")
    indexed = {str(item["operation_id"]): item for item in entries
               if isinstance(item, dict) and "operation_id" in item}
    if len(indexed) != len(entries):
        raise RuntimeError("lingxing.readonly_allowlist_duplicate")
    return str(payload["allowlist_version"]), indexed


OFFICIAL_READONLY_ALLOWLIST_VERSION, _READONLY_DECISIONS = _load_readonly_allowlist()


def _official_raw_spec(contract: OfficialContract) -> ResourceSpec | None:
    decision = _READONLY_DECISIONS.get(contract.id)
    if decision is None:
        return None
    if (decision.get("method") != contract.method
            or decision.get("path") != contract.path
            or decision.get("document_sha256") != contract.document_sha256):
        raise RuntimeError("lingxing.readonly_allowlist_contract_changed")
    if decision.get("decision") != "read_only":
        return None
    return _unreviewed_official_raw_spec(contract)


OFFICIAL_RAW_SPECS = tuple(spec for contract in official_contracts()
                           if (spec := _official_raw_spec(contract)) is not None)
_OFFICIAL_RAW_BY_KEY = {item.key: item for item in OFFICIAL_RAW_SPECS}


def resource_spec(key: str) -> ResourceSpec | None:
    key = "shops" if key == "catalog.shop" else key
    return (next((item for item in RESOURCE_CATALOG if item.key == key), None)
            or _OFFICIAL_RAW_BY_KEY.get(key))


def official_raw_spec(identity: str) -> ResourceSpec | None:
    contract = official_contract(identity)
    return _official_raw_spec(contract) if contract is not None else None


def resource_contract_version(spec: ResourceSpec) -> str:
    payload = {
        "method": spec.method, "path": spec.path, "schema_status": spec.schema_status,
        "page_size": spec.page_size, "paginated": spec.paginated,
        "parameters": spec.parameters, "required_parameters": spec.required_parameters,
        "headers": spec.headers, "rows_path": spec.rows_path, "total_path": spec.total_path,
        "end_exclusive": spec.end_exclusive, "execution_mode": spec.execution_mode,
        "pagination_mode": spec.pagination_mode, "window_fields": spec.window_fields,
        "window_format": spec.window_format, "scope_kind": spec.scope_kind,
        "scope_parameter": spec.scope_parameter,
        "scope_parameter_mode": spec.scope_parameter_mode,
        "max_window_days": spec.max_window_days, "retention_days": spec.retention_days,
    }
    # Keep legacy fingerprints stable while binding dynamically shaped requests to
    # the exact nesting extracted from the reviewed official contract.
    if spec.parameter_paths:
        payload["parameter_paths"] = spec.parameter_paths
    if spec.singleton_list_parameters:
        payload["singleton_list_parameters"] = spec.singleton_list_parameters
    if spec.scope_namespace == "multiplatform":
        payload["scope_namespace"] = spec.scope_namespace
    if spec.pagination_path:
        payload["pagination_path"] = spec.pagination_path
    if spec.pagination_page_field is not None:
        payload["pagination_page_field"] = spec.pagination_page_field
    if spec.pagination_size_field is not None:
        payload["pagination_size_field"] = spec.pagination_size_field
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
    return f"lx-{digest}"


def can_project_to_core(spec: ResourceSpec) -> bool:
    return spec.schema_status == "confirmed" and spec.mapping_key is not None


def effective_schema_status(spec: ResourceSpec | None, stored_status: str | None = None) -> str:
    return ("confirmed" if spec is not None and spec.schema_status == "confirmed"
            and stored_status in {None, "confirmed"} else "schema_pending")


def _merge_request_object(target: dict[str, object], path: tuple[str, ...],
                          values: Mapping[str, object]) -> None:
    current = target
    for part in path:
        existing = current.get(part)
        if existing is None:
            nested: dict[str, object] = {}
            current[part] = nested
            current = nested
        elif isinstance(existing, dict):
            current = existing
        else:
            raise ValueError("resource.request_shape_conflict")
    for key, value in values.items():
        if key in current and current[key] != value:
            raise ValueError("resource.request_shape_conflict")
        current[key] = value


def materialize_request_parameters(spec: ResourceSpec,
                                   parameters: Mapping[str, object]) -> dict[str, object]:
    """Build the provider request object from validated flat partition parameters."""
    nested_paths = dict(spec.parameter_paths)
    result: dict[str, object] = {}
    for key, value in parameters.items():
        path = nested_paths.get(key)
        if (key == spec.scope_parameter and spec.scope_parameter_mode == "list"
                and not isinstance(value, list)):
            values = str(value).split(",")
            cleaned = [item.strip() for item in values if item.strip()]
            if not cleaned:
                raise ValueError("resource.request_scope_invalid")
            # Numeric sid/sellerId scopes are sent as integers, while newer
            # Amazon contracts use opaque seller_id strings.  Preserve the
            # latter instead of forcing every list-valued scope through int().
            normalized_scope = _normalized_field(str(spec.scope_parameter or ""))
            if normalized_scope in _STORE_SCOPE_FIELDS - {"sellerid"}:
                try:
                    value = [int(item) for item in cleaned]
                except ValueError:
                    raise ValueError("resource.request_scope_invalid") from None
            else:
                value = cleaned
        if key in spec.singleton_list_parameters:
            if isinstance(value, (dict, list)):
                raise ValueError("resource.request_shape_invalid")
            value = [value]
        if path is None:
            if key in result:
                raise ValueError("resource.request_shape_conflict")
            result[key] = value
            continue
        if path[-1] != key:
            raise ValueError("resource.request_path_invalid")
        _merge_request_object(result, path[:-1], {path[-1]: value})
    return result


def page_parameters(spec: ResourceSpec, filters: dict[str, object], page: int) -> dict[str, object]:
    if isinstance(page, bool) or page < 1:
        raise ValueError("resource.page_invalid")
    if not spec.paginated:
        return dict(filters)
    if spec.pagination_page_field is not None or spec.pagination_size_field is not None:
        if spec.pagination_page_field is None or spec.pagination_size_field is None:
            raise ValueError("resource.pagination_unsupported")
        result = deepcopy(filters)
        page_value = ((page - 1) * spec.page_size
                      if spec.pagination_mode in {"offset", "offset_limit"} else page)
        _merge_request_object(result, spec.pagination_path, {
            spec.pagination_page_field: page_value,
            spec.pagination_size_field: spec.page_size,
        })
        return result
    if spec.pagination_mode == "search_page":
        return {"search": {**filters, "page": page, "length": spec.page_size}}
    if spec.pagination_mode == "offset_limit":
        return {**filters, "offset": (page - 1) * spec.page_size, "limit": spec.page_size}
    if spec.pagination_mode == "page":
        return {**filters, "page": page, "length": spec.page_size}
    if spec.pagination_mode == "page_size":
        return {**filters, "page": page, "page_size": spec.page_size}
    if spec.pagination_mode != "offset":
        raise ValueError("resource.pagination_unsupported")
    return {**filters, "offset": (page - 1) * spec.page_size, "length": spec.page_size}


def validate_resource_parameters(spec: ResourceSpec,
                                 parameters: dict[str, object]) -> dict[str, object]:
    if set(parameters) != set(spec.required_parameters):
        raise ValueError("resource.parameters_invalid")
    if any(isinstance(value, (dict, list)) or len(str(value)) > 500
           for value in parameters.values()):
        raise ValueError("resource.parameters_invalid")
    result = dict(parameters)
    for key, choices in (("is_delete", {"0", "1"}),
                         ("enabled", {"0", "1"}), ("isAuth", {"0", "1"}),
                         ("payMethod", {"1", "2"})):
        if key in spec.required_parameters:
            value = parameters[key]
            if (isinstance(value, bool) or not isinstance(value, (str, int))
                    or str(value) not in choices):
                raise ValueError("resource.logistics_filter_invalid")
            result[key] = int(str(value))
    for key in ("country_code", "countryCode"):
        if key in spec.required_parameters and not re.fullmatch(r"[A-Z]{2}", str(parameters[key])):
            raise ValueError("resource.country_code_invalid")
    if "date" in spec.required_parameters:
        month_value = str(parameters["date"])
        if not re.fullmatch(r"\d{4}-\d{2}", month_value):
            raise ValueError("resource.month_invalid")
        try:
            date.fromisoformat(f"{month_value}-01")
        except ValueError:
            raise ValueError("resource.month_invalid") from None
    if "region" in spec.required_parameters and (
        not isinstance(parameters["region"], str) or parameters["region"] not in {"na", "eu", "fe"}
    ):
        raise ValueError("resource.region_invalid")
    for key in ("seller_id", "task_id"):
        if key in spec.required_parameters:
            value = parameters[key]
            report_values = (value.split(",") if isinstance(value, str)
                             and spec.scope_parameter == key
                             and spec.scope_parameter_mode in {"list", "csv"} else [value])
            if not report_values or any(not isinstance(item, str)
                                 or not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", item)
                                 for item in report_values):
                raise ValueError("resource.report_parameter_invalid")
    if spec.window_format == "date" and set(spec.window_fields).issubset(parameters):
        try:
            date_values = [date.fromisoformat(str(parameters[key]))
                           for key in spec.window_fields]
            if len(date_values) == 2:
                start, end = date_values
                if (start > end or (spec.end_exclusive and start == end)
                        or (end - start).days > spec.max_window_days):
                    raise ValueError("window invalid")
        except (ValueError, TypeError):
            raise ValueError("resource.source_date_window_invalid") from None
    if spec.window_format == "month" and set(spec.window_fields).issubset(parameters):
        try:
            month_values = [str(parameters[key]) for key in spec.window_fields]
            if any(not re.fullmatch(r"\d{4}-\d{2}", value) for value in month_values):
                raise ValueError("month format")
            parsed = [date.fromisoformat(f"{value}-01") for value in month_values]
            if len(parsed) == 2 and parsed[0] > parsed[1]:
                raise ValueError("month order")
        except (ValueError, TypeError):
            raise ValueError("resource.source_month_window_invalid") from None
    if spec.window_format == "datetime" and set(spec.window_fields).issubset(parameters):
        try:
            datetime_values = [str(parameters[key]) for key in spec.window_fields]
            if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value)
                   for value in datetime_values):
                raise ValueError("timestamp format")
            parsed = [datetime.fromisoformat(value) for value in datetime_values]
            if len(parsed) == 2:
                start_time, end_time = parsed
                if (start_time >= end_time
                        or (end_time - start_time).total_seconds()
                        > spec.max_window_days * 86400):
                    raise ValueError("window invalid")
        except (ValueError, TypeError):
            raise ValueError("resource.source_time_window_invalid") from None
    if "sid" in spec.required_parameters:
        value = parameters["sid"]
        multiple = (spec.scope_parameter == "sid"
                    and spec.scope_parameter_mode in {"list", "csv"})
        values = str(value).split(",") if multiple else [str(value)]
        if (isinstance(value, bool) or not values
                or any(len(item) > 20 or not item.isdigit() or int(item) <= 0
                       for item in values)):
            raise ValueError("resource.store_invalid")
        result["sid"] = (",".join(str(int(item)) for item in values) if multiple else
                         str(int(str(value))) if spec.key == "fbm_orders" else int(str(value)))
    return result


def partition_parameter_names(spec: ResourceSpec) -> tuple[str, ...]:
    return tuple(key for key in spec.required_parameters if key not in spec.window_fields)


def validate_partition_parameters(spec: ResourceSpec,
                                  parameters: dict[str, object]) -> dict[str, object]:
    """Validate the immutable part of a resource partition.

    Moving time-window fields are derived by the scheduler/worker and are deliberately
    excluded from the schedule identity.
    """
    static_required = partition_parameter_names(spec)
    if set(parameters) != set(static_required):
        raise ValueError("resource.parameters_invalid")
    if not spec.window_fields:
        return validate_resource_parameters(spec, parameters)
    placeholder_values = (("2000-01-01 00:00:00", "2000-01-02 00:00:00")
                          if spec.window_format == "datetime" else
                          ("2000-01", "2000-01") if spec.window_format == "month" else
                          ("2000-01-01", "2000-01-02"))
    placeholders = {name: placeholder_values[index]
                    for index, name in enumerate(spec.window_fields)}
    normalized = validate_resource_parameters(spec, {**parameters, **placeholders})
    return {key: value for key, value in normalized.items() if key not in spec.window_fields}


def materialize_window_parameters(spec: ResourceSpec, parameters: dict[str, object],
                                  start: datetime, end: datetime) -> dict[str, object]:
    if len(spec.window_fields) not in {1, 2} or spec.window_format not in {
        "date", "datetime", "month"
    }:
        raise ValueError("resource.window_unsupported")
    max_days = 1 if len(spec.window_fields) == 1 else spec.max_window_days
    if (start.tzinfo is None or end.tzinfo is None or start >= end
            or end - start > timedelta(days=max_days)):
        raise ValueError("resource.source_window_invalid")
    result = validate_partition_parameters(spec, parameters)
    start_utc, end_utc = start.astimezone(UTC), end.astimezone(UTC)
    if spec.window_format == "datetime":
        values = (start_utc.strftime("%Y-%m-%d %H:%M:%S"),
                  end_utc.strftime("%Y-%m-%d %H:%M:%S"))
    elif spec.window_format == "month":
        inclusive_end = end_utc - timedelta(microseconds=1)
        values = (start_utc.strftime("%Y-%m"), inclusive_end.strftime("%Y-%m"))
        if values[0] != values[1]:
            raise ValueError("resource.source_month_window_invalid")
    else:
        inclusive_end = (end_utc if spec.end_exclusive or len(spec.window_fields) == 1
                         else end_utc - timedelta(microseconds=1))
        values = (start_utc.date().isoformat(), inclusive_end.date().isoformat())
    if len(spec.window_fields) == 1:
        return validate_resource_parameters(spec, {
            **result, spec.window_fields[0]: values[0]})
    return validate_resource_parameters(spec, {
        **result, spec.window_fields[0]: values[0], spec.window_fields[1]: values[1]})


def response_value(payload: Mapping[str, object], path: tuple[str, ...]) -> object:
    value: object = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


READ_ONLY_OPERATIONS = frozenset(
    (item.method, item.path) for item in (*RESOURCE_CATALOG, *OFFICIAL_RAW_SPECS) if item.path)
OPERATION_HEADERS = {(item.method, item.path): dict(item.headers)
                     for item in (*RESOURCE_CATALOG, *OFFICIAL_RAW_SPECS) if item.path}
