from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal, cast

import httpx

from zhixing_api.connectors.contracts import (
    AuthoritativeFactType,
    CanonicalAdPerformanceFact,
    CanonicalCustomerProfile,
    CanonicalCustomerTouchpointFact,
    CanonicalEntity,
    CanonicalInventorySnapshotFact,
    CanonicalMetric,
    CanonicalOrderFact,
    CanonicalOrderLineFact,
    CanonicalRefundFact,
    CanonicalScopeMapping,
    ConnectorBatch,
    ConnectorError,
    ExternalRecord,
)

MAPPING_VERSION = "1.4.0"

ConnectorProfile = Literal["aggregate", "erp-oms", "crm", "advertising", "customer-service"]


@dataclass(frozen=True, slots=True)
class ConnectorProfileConfig:
    resources: tuple[str, ...]
    entity_types: frozenset[str]
    metric_keys: frozenset[str]
    mapping_version: str
    schema_key: str


LEGACY_RESOURCES = (
    "profile",
    "shops",
    "products",
    "skus",
    "warehouses",
    "customers",
    "orders/recent",
    "orders/summary",
    "inventory/summary",
    "ads/summary",
    "crm/summary",
    "metrics/daily",
)

CONNECTOR_PROFILES: dict[ConnectorProfile, ConnectorProfileConfig] = {
    "aggregate": ConnectorProfileConfig(
        resources=LEGACY_RESOURCES,
        entity_types=frozenset({"store", "product", "sku", "warehouse", "customer", "order"}),
        metric_keys=frozenset(
            {
                "gmv_today",
                "orders_today",
                "refund_rate",
                "low_stock_skus",
                "ad_roi",
                "active_members",
            }
        ),
        mapping_version="1.2.0",
        schema_key="aggregate",
    ),
    "erp-oms": ConnectorProfileConfig(
        resources=(
            "profile",
            "shops",
            "products",
            "skus",
            "warehouses",
            "orders/recent",
            "orders/lines",
            "refunds",
            "orders/summary",
            "inventory/snapshots",
            "inventory/summary",
            "metrics/daily",
        ),
        entity_types=frozenset({"store", "product", "sku", "warehouse", "order"}),
        metric_keys=frozenset(
            {
                "gmv_today",
                "orders_today",
                "refund_rate",
                "low_stock_skus",
                "gross_margin_rate",
                "fulfillment_rate",
                "inventory_turnover_days",
            }
        ),
        mapping_version=MAPPING_VERSION,
        schema_key="erp_oms",
    ),
    "crm": ConnectorProfileConfig(
        resources=(
            "profile",
            "shops",
            "customers",
            "crm/touchpoints",
            "crm/summary",
            "metrics/daily",
        ),
        entity_types=frozenset({"customer"}),
        metric_keys=frozenset(
            {
                "active_members",
                "new_members",
                "repeat_purchase_rate",
                "churn_risk_members",
            }
        ),
        mapping_version="1.2.0",
        schema_key="crm",
    ),
    "advertising": ConnectorProfileConfig(
        resources=(
            "profile",
            "ads/campaigns",
            "ads/performance",
            "ads/summary",
            "metrics/daily",
        ),
        entity_types=frozenset({"ad_campaign"}),
        metric_keys=frozenset(
            {
                "ad_roi",
                "ad_spend",
                "attributed_revenue",
                "ad_ctr",
                "ad_conversion_rate",
            }
        ),
        mapping_version="1.1.0",
        schema_key="advertising",
    ),
    "customer-service": ConnectorProfileConfig(
        resources=("profile", "service/conversations", "service/summary", "metrics/daily"),
        entity_types=frozenset({"service_conversation"}),
        metric_keys=frozenset(
            {
                "service_conversations",
                "first_response_minutes",
                "service_resolution_rate",
                "csat_score",
                "human_handoff_rate",
            }
        ),
        mapping_version="1.0.0",
        schema_key="customer_service",
    ),
}

DAILY_METRIC_MAPPING: dict[str, tuple[str, str, str, float]] = {
    "PAID_GMV_FEN": ("gmv_today", "成交金额", "元", 0.01),
    "PAID_ORDER_COUNT": ("orders_today", "支付订单", "单", 1.0),
    "REFUND_RATE_BPS": ("refund_rate", "退款率", "%", 0.01),
    "AD_ROI_X100": ("ad_roi", "广告 ROI", "x", 0.01),
    "LOW_STOCK_SKU_COUNT": ("low_stock_skus", "低库存 SKU", "SKU", 1.0),
    "ACTIVE_MEMBER_COUNT": ("active_members", "活跃会员", "人", 1.0),
    "GROSS_MARGIN_RATE_BPS": ("gross_margin_rate", "毛利率", "%", 0.01),
    "FULFILLMENT_RATE_BPS": ("fulfillment_rate", "履约及时率", "%", 0.01),
    "INVENTORY_TURNOVER_DAYS_X100": (
        "inventory_turnover_days",
        "库存周转天数",
        "天",
        0.01,
    ),
    "NEW_MEMBER_COUNT": ("new_members", "新增会员", "人", 1.0),
    "REPEAT_PURCHASE_RATE_BPS": ("repeat_purchase_rate", "复购率", "%", 0.01),
    "CHURN_RISK_MEMBER_COUNT": ("churn_risk_members", "流失风险会员", "人", 1.0),
    "AD_SPEND_FEN": ("ad_spend", "广告消耗", "元", 0.01),
    "ATTRIBUTED_REVENUE_FEN": ("attributed_revenue", "广告归因成交", "元", 0.01),
    "AD_CTR_BPS": ("ad_ctr", "广告点击率", "%", 0.01),
    "AD_CONVERSION_RATE_BPS": ("ad_conversion_rate", "广告转化率", "%", 0.01),
    "SERVICE_CONVERSATION_COUNT": ("service_conversations", "客服会话", "次", 1.0),
    "FIRST_RESPONSE_SECONDS": (
        "first_response_minutes",
        "首次响应时长",
        "分钟",
        1 / 60,
    ),
    "SERVICE_RESOLUTION_RATE_BPS": (
        "service_resolution_rate",
        "一次解决率",
        "%",
        0.01,
    ),
    "CSAT_SCORE_X100": ("csat_score", "客户满意度", "分", 0.01),
    "HUMAN_HANDOFF_RATE_BPS": ("human_handoff_rate", "人工接管率", "%", 0.01),
}


def _object(payload: object, context: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ConnectorError(f"{context} did not return an object")
    return cast(dict[str, object], payload)


def _items(payload: dict[str, object], context: str) -> list[dict[str, object]]:
    value = payload.get("items")
    if not isinstance(value, list):
        raise ConnectorError(f"{context}.items did not return a list")
    return [_object(item, context) for item in value]


def _timestamp(payload: dict[str, object]) -> datetime:
    raw = str(payload.get("generated_at", datetime.now(UTC).isoformat()))
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _number(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise ConnectorError(f"missing numeric field: {key}")
    return float(value)


def _integer(payload: dict[str, object], key: str) -> int:
    return int(_number(payload, key))


def _date(payload: dict[str, object], key: str) -> date:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ConnectorError(f"missing date field: {key}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConnectorError(f"invalid date field: {key}") from exc


def _datetime(payload: dict[str, object], key: str, *, optional: bool = False) -> datetime | None:
    value = payload.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ConnectorError(f"missing datetime field: {key}")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConnectorError(f"invalid datetime field: {key}") from exc


def _complete_customer_profile(item: dict[str, object]) -> bool:
    text_fields = (
        "customer_code",
        "customer_name",
        "home_shop_code",
        "registered_at",
        "last_active_at",
    )
    number_fields = ("member_points", "growth_value", "churn_risk_score_x10000")
    return all(isinstance(item.get(key), str) for key in text_fields) and all(
        isinstance(item.get(key), int | float) for key in number_fields
    )


def _complete_customer_touchpoint(item: dict[str, object]) -> bool:
    text_fields = (
        "touchpoint_code",
        "customer_code",
        "shop_code",
        "occurred_at",
    )
    return all(isinstance(item.get(key), str) for key in text_fields) and isinstance(
        item.get("value_fen"), int | float
    )


class MockCommerceConnector:
    def __init__(
        self,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        profile: ConnectorProfile = "aggregate",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.profile = profile
        self.profile_config = CONNECTOR_PROFILES[profile]

    async def fetch(
        self,
        scenario: str,
        volume_profile: str = "standard",
    ) -> ConnectorBatch:
        warnings: list[str] = []
        resources: dict[str, dict[str, object]] = {}
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=8.0,
            transport=self.transport,
        ) as client:
            for name in self.profile_config.resources:
                try:
                    params = {"scenario": scenario, "volume": volume_profile}
                    if name == "metrics/daily" and self.profile != "aggregate":
                        params["domain"] = self.profile
                    response = await client.get(
                        f"/api/v1/{name}",
                        params=params,
                    )
                    response.raise_for_status()
                    resources[name] = _object(response.json(), name)
                except (httpx.HTTPError, ConnectorError) as exc:
                    if name == "profile" or scenario == "failure":
                        raise ConnectorError(f"third-party sandbox unavailable: {exc}") from exc
                    warnings.append(f"{name}: {exc}")

        profile = resources["profile"]
        source_schemas = profile.get("source_schemas")
        schema_version = str(profile.get("schema_version", "unknown"))
        if isinstance(source_schemas, dict):
            schema_version = str(source_schemas.get(self.profile_config.schema_key, schema_version))
        records: list[ExternalRecord] = []
        for resource_name, payload in resources.items():
            observed_at = _timestamp(payload)
            resource_items = payload.get("items")
            if isinstance(resource_items, list):
                for index, raw_item in enumerate(resource_items):
                    item = _object(raw_item, resource_name)
                    external_id = str(
                        item.get("shop_code")
                        or item.get("external_id")
                        or item.get("line_code")
                        or item.get("refund_code")
                        or item.get("inventory_snapshot_code")
                        or item.get("performance_code")
                        or item.get("touchpoint_code")
                        or item.get("sku_code")
                        or item.get("product_code")
                        or item.get("warehouse_code")
                        or item.get("customer_code")
                        or item.get("order_code")
                        or item.get("metric_observation_key")
                        or index
                    )
                    records.append(ExternalRecord(resource_name, external_id, item, observed_at))
            else:
                external_id = str(payload.get("business_date", resource_name))
                records.append(ExternalRecord(resource_name, external_id, payload, observed_at))

        entities = [
            item
            for item in self._map_entities(resources)
            if item.entity_type in self.profile_config.entity_types
        ]
        metrics = [
            item
            for item in self._map_metrics(resources)
            if item.key in self.profile_config.metric_keys
        ]
        orders = self._map_orders(resources)
        order_lines = self._map_order_lines(resources)
        refunds = self._map_refunds(resources)
        inventory = self._map_inventory(resources)
        advertising = self._map_advertising(resources)
        customer_profile_payload = resources.get("customers")
        customer_profile_items = (
            _items(customer_profile_payload, "customers")
            if customer_profile_payload is not None and self.profile == "crm"
            else []
        )
        customer_profiles_authoritative = customer_profile_payload is not None and all(
            _complete_customer_profile(item) for item in customer_profile_items
        )
        customer_touchpoint_payload = resources.get("crm/touchpoints")
        customer_touchpoint_items = (
            _items(customer_touchpoint_payload, "crm/touchpoints")
            if customer_touchpoint_payload is not None and self.profile == "crm"
            else []
        )
        customer_touchpoints_authoritative = customer_touchpoint_payload is not None and all(
            _complete_customer_touchpoint(item) for item in customer_touchpoint_items
        )
        if customer_profile_payload is not None and not customer_profiles_authoritative:
            warnings.append("customers: incomplete customer profile fields; retained prior facts")
        if customer_touchpoint_payload is not None and not customer_touchpoints_authoritative:
            warnings.append("crm/touchpoints: incomplete touchpoint fields; retained prior facts")
        customer_profiles = self._map_customer_profiles(customer_profile_items)
        customer_touchpoints = self._map_customer_touchpoints(customer_touchpoint_items)
        scope_mappings = self._map_scope_mappings(resources)
        fact_resource_map: tuple[tuple[str, AuthoritativeFactType], ...] = (
            ("orders/recent", "orders"),
            ("orders/lines", "order_lines"),
            ("refunds", "refunds"),
            ("inventory/snapshots", "inventory"),
            ("ads/performance", "advertising"),
        )
        authoritative_fact_types_list = [
            fact_type
            for resource_name, fact_type in fact_resource_map
            if resource_name in resources
        ]
        if customer_profiles_authoritative:
            authoritative_fact_types_list.append("customer_profiles")
        if customer_touchpoints_authoritative:
            authoritative_fact_types_list.append("customer_touchpoints")
        authoritative_fact_types = tuple(authoritative_fact_types_list)
        return ConnectorBatch(
            source_schema_version=schema_version,
            mapping_version=self.profile_config.mapping_version,
            records=tuple(records),
            entities=tuple(entities),
            metrics=tuple(metrics),
            warnings=tuple(warnings),
            scope_mappings=tuple(scope_mappings),
            orders=tuple(orders),
            order_lines=tuple(order_lines),
            refunds=tuple(refunds),
            inventory=tuple(inventory),
            advertising=tuple(advertising),
            customer_profiles=tuple(customer_profiles),
            customer_touchpoints=tuple(customer_touchpoints),
            authoritative_fact_types=authoritative_fact_types,
        )

    def _map_scope_mappings(
        self,
        resources: dict[str, dict[str, object]],
    ) -> list[CanonicalScopeMapping]:
        shops = resources.get("shops")
        if shops is None:
            return []
        return [
            CanonicalScopeMapping(
                scope_type="store",
                scope_key=self._store_scope_key(resources, str(item["shop_code"])),
                external_scope_key=str(item["shop_code"]),
                label=str(item["shop_title"]),
                status="active" if item.get("shop_state") == "ACTIVE" else "inactive",
                attributes={
                    "channel": str(item.get("channel", "unknown")),
                    "manager": str(item.get("manager_name", "unassigned")),
                },
            )
            for item in _items(shops, "shops")
        ]

    def _map_orders(
        self,
        resources: dict[str, dict[str, object]],
    ) -> list[CanonicalOrderFact]:
        payload = resources.get("orders/recent")
        if payload is None or self.profile != "erp-oms":
            return []
        state_map = {
            "PAID": "paid",
            "SHIPPED": "shipped",
            "COMPLETED": "completed",
            "REFUNDING": "refunding",
            "REFUNDED": "refunded",
            "CANCELLED": "cancelled",
        }
        return [
            CanonicalOrderFact(
                order_key=str(item["order_code"]),
                store_key=str(item["shop_code"]),
                customer_key=str(item["customer_code"]),
                channel=str(item.get("channel", "unknown")),
                status=state_map.get(str(item.get("order_state")), "paid"),
                business_date=_date(item, "business_date"),
                paid_at=cast(datetime, _datetime(item, "paid_at")),
                shipped_at=_datetime(item, "shipped_at", optional=True),
                paid_amount_fen=_integer(item, "paid_amount_fen"),
                item_amount_fen=_integer(item, "item_amount_fen"),
                discount_amount_fen=_integer(item, "discount_amount_fen"),
                freight_amount_fen=_integer(item, "freight_amount_fen"),
                cost_amount_fen=_integer(item, "cost_amount_fen"),
                item_count=_integer(item, "item_count"),
                province=str(item.get("province_name", "unknown")),
            )
            for item in _items(payload, "orders/recent")
        ]

    def _map_order_lines(
        self,
        resources: dict[str, dict[str, object]],
    ) -> list[CanonicalOrderLineFact]:
        payload = resources.get("orders/lines")
        if payload is None:
            return []
        return [
            CanonicalOrderLineFact(
                line_key=str(item["line_code"]),
                order_key=str(item["order_code"]),
                product_key=str(item["product_code"]),
                sku_key=str(item["sku_code"]),
                quantity=_integer(item, "quantity"),
                unit_price_fen=_integer(item, "unit_price_fen"),
                paid_amount_fen=_integer(item, "paid_amount_fen"),
                cost_amount_fen=_integer(item, "cost_amount_fen"),
                refund_quantity=_integer(item, "refund_quantity"),
                refund_amount_fen=_integer(item, "refund_amount_fen"),
            )
            for item in _items(payload, "orders/lines")
        ]

    def _map_refunds(
        self,
        resources: dict[str, dict[str, object]],
    ) -> list[CanonicalRefundFact]:
        payload = resources.get("refunds")
        if payload is None:
            return []
        state_map = {
            "REQUESTED": "requested",
            "APPROVED": "approved",
            "COMPLETED": "completed",
            "REJECTED": "rejected",
        }
        return [
            CanonicalRefundFact(
                refund_key=str(item["refund_code"]),
                order_key=str(item["order_code"]),
                line_key=str(item["line_code"]),
                store_key=str(item["shop_code"]),
                customer_key=str(item["customer_code"]),
                sku_key=str(item["sku_code"]),
                reason_category=str(item.get("reason_category", "other")),
                status=state_map.get(str(item.get("refund_state")), "requested"),
                requested_at=cast(datetime, _datetime(item, "requested_at")),
                completed_at=_datetime(item, "completed_at", optional=True),
                refund_amount_fen=_integer(item, "refund_amount_fen"),
                quantity=_integer(item, "quantity"),
            )
            for item in _items(payload, "refunds")
        ]

    def _map_inventory(
        self,
        resources: dict[str, dict[str, object]],
    ) -> list[CanonicalInventorySnapshotFact]:
        payload = resources.get("inventory/snapshots")
        if payload is None:
            return []
        return [
            CanonicalInventorySnapshotFact(
                snapshot_key=str(item["inventory_snapshot_code"]),
                warehouse_key=str(item["warehouse_code"]),
                product_key=str(item["product_code"]),
                sku_key=str(item["sku_code"]),
                as_of=cast(datetime, _datetime(item, "as_of")),
                available_quantity=_integer(item, "available_quantity"),
                reserved_quantity=_integer(item, "reserved_quantity"),
                in_transit_quantity=_integer(item, "in_transit_quantity"),
                safety_quantity=_integer(item, "safety_quantity"),
                inventory_cost_fen=_integer(item, "inventory_cost_fen"),
                days_cover=_number(item, "days_cover"),
                status=str(item.get("inventory_state", "HEALTHY")).casefold(),
            )
            for item in _items(payload, "inventory/snapshots")
        ]

    def _map_advertising(
        self,
        resources: dict[str, dict[str, object]],
    ) -> list[CanonicalAdPerformanceFact]:
        payload = resources.get("ads/performance")
        if payload is None:
            return []
        return [
            CanonicalAdPerformanceFact(
                performance_key=str(item["performance_code"]),
                campaign_key=str(item["campaign_code"]),
                store_key=str(item["shop_code"]),
                product_key=str(item["product_code"]),
                channel=str(item.get("channel", "unknown")),
                business_date=_date(item, "business_date"),
                impressions=_integer(item, "impressions"),
                clicks=_integer(item, "clicks"),
                spend_fen=_integer(item, "spend_fen"),
                attributed_order_count=_integer(item, "attributed_order_count"),
                attributed_revenue_fen=_integer(item, "attributed_revenue_fen"),
            )
            for item in _items(payload, "ads/performance")
        ]

    def _map_customer_profiles(
        self,
        items: list[dict[str, object]],
    ) -> list[CanonicalCustomerProfile]:
        lifecycle_map = {
            "NEW": "new",
            "GROWING": "growing",
            "MATURE": "mature",
            "SLEEPING": "sleeping",
            "AT_RISK": "at_risk",
        }
        consent_map = {
            "GRANTED": "granted",
            "REVOKED": "revoked",
            "UNKNOWN": "unknown",
        }
        profiles: list[CanonicalCustomerProfile] = []
        for item in items:
            if not _complete_customer_profile(item):
                continue
            raw_tags = item.get("tags", [])
            tags = tuple(str(tag) for tag in raw_tags) if isinstance(raw_tags, list) else ()
            profiles.append(
                CanonicalCustomerProfile(
                    customer_key=str(item["customer_code"]),
                    display_name=str(item["customer_name"]),
                    home_store_key=str(item["home_shop_code"]),
                    member_level=str(item.get("member_level", "STANDARD")).casefold(),
                    lifecycle_stage=lifecycle_map.get(
                        str(item.get("lifecycle_stage", "NEW")), "new"
                    ),
                    status="active" if item.get("member_state") == "ACTIVE" else "inactive",
                    province=str(item.get("province_name", "unknown")),
                    acquisition_channel=str(item.get("acquisition_channel", "unknown")),
                    registered_at=cast(datetime, _datetime(item, "registered_at")),
                    last_active_at=cast(datetime, _datetime(item, "last_active_at")),
                    member_points=_integer(item, "member_points"),
                    growth_value=_integer(item, "growth_value"),
                    churn_risk_score=_number(item, "churn_risk_score_x10000") / 10_000,
                    preferred_category=str(item.get("preferred_category", "unknown")),
                    consent_status=consent_map.get(
                        str(item.get("consent_state", "UNKNOWN")), "unknown"
                    ),
                    tags=tags,
                )
            )
        return profiles

    def _map_customer_touchpoints(
        self,
        items: list[dict[str, object]],
    ) -> list[CanonicalCustomerTouchpointFact]:
        return [
            CanonicalCustomerTouchpointFact(
                touchpoint_key=str(item["touchpoint_code"]),
                customer_key=str(item["customer_code"]),
                store_key=str(item["shop_code"]),
                touchpoint_type=str(item.get("event_type", "VISIT")).casefold(),
                channel=str(item.get("channel", "unknown")),
                occurred_at=cast(datetime, _datetime(item, "occurred_at")),
                campaign_key=(
                    str(item["campaign_code"])
                    if item.get("campaign_code") is not None
                    else None
                ),
                value_fen=_integer(item, "value_fen"),
                properties={
                    "product_key": str(item.get("product_code", "unknown")),
                    "device_type": str(item.get("device_type", "unknown")).casefold(),
                    "session_key": str(item.get("session_code", "unknown")),
                },
            )
            for item in items
            if _complete_customer_touchpoint(item)
        ]

    def _map_entities(self, resources: dict[str, dict[str, object]]) -> list[CanonicalEntity]:
        entities: list[CanonicalEntity] = []
        shops = resources.get("shops")
        if shops is not None:
            entities.extend(
                CanonicalEntity(
                    entity_type="store",
                    canonical_key=str(item["shop_code"]),
                    display_name=str(item["shop_title"]),
                    status="active" if item.get("shop_state") == "ACTIVE" else "inactive",
                    attributes={
                        "channel": str(item.get("channel", "unknown")),
                        "manager": str(item.get("manager_name", "unassigned")),
                    },
                )
                for item in _items(shops, "shops")
            )

        products = resources.get("products")
        if products is not None:
            entities.extend(
                CanonicalEntity(
                    entity_type="product",
                    canonical_key=str(item["product_code"]),
                    display_name=str(item["product_name"]),
                    status="active" if item.get("product_state") == "ACTIVE" else "inactive",
                    attributes={
                        "brand": str(item.get("brand_name", "unknown")),
                        "category": str(item.get("category_name", "unknown")),
                        "owner_team": str(item.get("owner_team", "unassigned")),
                    },
                )
                for item in _items(products, "products")
            )

        skus = resources.get("skus")
        if skus is not None:
            entities.extend(
                CanonicalEntity(
                    entity_type="sku",
                    canonical_key=str(item["sku_code"]),
                    display_name=str(item["sku_name"]),
                    status="active" if item.get("sell_state") == "ACTIVE" else "inactive",
                    attributes={
                        "product_code": str(item.get("product_code", "unknown")),
                        "warehouse_code": str(item.get("warehouse_code", "unknown")),
                        "available_stock": _integer(item, "available_stock"),
                        "safety_stock": _integer(item, "safety_stock"),
                    },
                )
                for item in _items(skus, "skus")
            )

        warehouses = resources.get("warehouses")
        if warehouses is not None:
            entities.extend(
                CanonicalEntity(
                    entity_type="warehouse",
                    canonical_key=str(item["warehouse_code"]),
                    display_name=str(item["warehouse_name"]),
                    status="active" if item.get("warehouse_state") == "OPERATING" else "inactive",
                    attributes={
                        "region": str(item.get("region_name", "unknown")),
                        "manager": str(item.get("manager_name", "unassigned")),
                        "capacity": _integer(item, "capacity_units"),
                    },
                )
                for item in _items(warehouses, "warehouses")
            )

        customers = resources.get("customers")
        if customers is not None:
            entities.extend(
                CanonicalEntity(
                    entity_type="customer",
                    canonical_key=str(item["customer_code"]),
                    display_name=str(item["customer_name"]),
                    status="active" if item.get("member_state") == "ACTIVE" else "inactive",
                    attributes={
                        "segment": str(item.get("member_segment", "unknown")),
                        "province": str(item.get("province_name", "unknown")),
                        "total_orders": _integer(item, "total_order_count"),
                        "home_store_code": str(item.get("home_shop_code", "unknown")),
                        "member_level": str(item.get("member_level", "unknown")).casefold(),
                        "lifecycle_stage": str(
                            item.get("lifecycle_stage", "unknown")
                        ).casefold(),
                        "preferred_category": str(
                            item.get("preferred_category", "unknown")
                        ),
                    },
                )
                for item in _items(customers, "customers")
            )

        orders = resources.get("orders/recent")
        if orders is not None:
            entities.extend(
                CanonicalEntity(
                    entity_type="order",
                    canonical_key=str(item["order_code"]),
                    display_name=f"订单 {item['order_code']}",
                    status="active" if item.get("order_state") != "CANCELLED" else "inactive",
                    attributes={
                        "store_code": str(item.get("shop_code", "unknown")),
                        "customer_code": str(item.get("customer_code", "unknown")),
                        "paid_amount_fen": _integer(item, "paid_amount_fen"),
                        "order_state": str(item.get("order_state", "unknown")),
                    },
                )
                for item in _items(orders, "orders/recent")
            )

        campaigns = resources.get("ads/campaigns")
        if campaigns is not None:
            entities.extend(
                CanonicalEntity(
                    entity_type="ad_campaign",
                    canonical_key=str(item["campaign_code"]),
                    display_name=str(item["campaign_name"]),
                    status="active" if item.get("campaign_state") == "RUNNING" else "inactive",
                    attributes={
                        "store_code": str(item.get("shop_code", "unknown")),
                        "channel": str(item.get("channel", "unknown")),
                        "daily_budget_fen": _integer(item, "daily_budget_fen"),
                        "owner_team": str(item.get("owner_team", "unassigned")),
                    },
                )
                for item in _items(campaigns, "ads/campaigns")
            )

        conversations = resources.get("service/conversations")
        if conversations is not None:
            entities.extend(
                CanonicalEntity(
                    entity_type="service_conversation",
                    canonical_key=str(item["conversation_code"]),
                    display_name=f"客服会话 {item['conversation_code']}",
                    status="active" if item.get("conversation_state") == "OPEN" else "inactive",
                    attributes={
                        "store_code": str(item.get("shop_code", "unknown")),
                        "customer_code": str(item.get("customer_code", "unknown")),
                        "channel": str(item.get("channel", "unknown")),
                        "risk_level": str(item.get("risk_level", "normal")),
                        "order_code": str(item.get("order_code", "unknown")),
                    },
                )
                for item in _items(conversations, "service/conversations")
            )
        return entities

    def _map_metrics(self, resources: dict[str, dict[str, object]]) -> list[CanonicalMetric]:
        metrics: list[CanonicalMetric] = []
        daily = resources.get("metrics/daily")
        if daily is not None:
            for item in _items(daily, "metrics/daily"):
                indicator_code = str(item.get("indicator_code", ""))
                mapping = DAILY_METRIC_MAPPING.get(indicator_code)
                if mapping is None:
                    continue
                key, label, unit, divisor = mapping
                business_date = datetime.fromisoformat(str(item["business_date"])).replace(
                    tzinfo=UTC
                )
                scope_key = "enterprise"
                if item.get("scope_type") == "shop":
                    scope_key = self._store_scope_key(resources, str(item.get("shop_code", "")))
                metrics.append(
                    CanonicalMetric(
                        key=key,
                        label=label,
                        value=_number(item, "value") * divisor,
                        unit=unit,
                        change_rate=_number(item, "change_bps") / 10000,
                        as_of=business_date,
                        scope_key=scope_key,
                    )
                )
        orders = resources.get("orders/summary")
        if orders is not None:
            as_of = _timestamp(orders)
            metrics.extend(
                [
                    CanonicalMetric(
                        "gmv_today",
                        "今日成交",
                        _number(orders, "paid_gmv_fen") / 100,
                        "元",
                        _number(orders, "gmv_change_bps") / 10000,
                        as_of,
                    ),
                    CanonicalMetric(
                        "orders_today",
                        "支付订单",
                        _number(orders, "paid_order_count"),
                        "单",
                        _number(orders, "order_change_bps") / 10000,
                        as_of,
                    ),
                    CanonicalMetric(
                        "refund_rate",
                        "退款率",
                        _number(orders, "refund_rate_bps") / 100,
                        "%",
                        _number(orders, "refund_change_bps") / 10000,
                        as_of,
                    ),
                ]
            )
            if "gross_margin_rate_bps" in orders:
                metrics.append(
                    CanonicalMetric(
                        "gross_margin_rate",
                        "毛利率",
                        _number(orders, "gross_margin_rate_bps") / 100,
                        "%",
                        _number(orders, "gross_margin_change_bps") / 10000,
                        as_of,
                    )
                )
            if "fulfillment_rate_bps" in orders:
                metrics.append(
                    CanonicalMetric(
                        "fulfillment_rate",
                        "履约及时率",
                        _number(orders, "fulfillment_rate_bps") / 100,
                        "%",
                        _number(orders, "fulfillment_change_bps") / 10000,
                        as_of,
                    )
                )
        inventory = resources.get("inventory/summary")
        if inventory is not None:
            as_of = _timestamp(inventory)
            metrics.extend(
                [
                    CanonicalMetric(
                        "low_stock_skus",
                        "低库存 SKU",
                        _number(inventory, "low_stock_sku_count"),
                        "SKU",
                        None,
                        as_of,
                    ),
                ]
            )
            if "inventory_turnover_days_x100" in inventory:
                metrics.append(
                    CanonicalMetric(
                        "inventory_turnover_days",
                        "库存周转天数",
                        _number(inventory, "inventory_turnover_days_x100") / 100,
                        "天",
                        _number(inventory, "turnover_change_bps") / 10000,
                        as_of,
                    )
                )
        ads = resources.get("ads/summary")
        if ads is not None:
            as_of = _timestamp(ads)
            metrics.extend(
                [
                    CanonicalMetric(
                        "ad_roi",
                        "广告 ROI",
                        _number(ads, "roi_x100") / 100,
                        "x",
                        _number(ads, "roi_change_bps") / 10000,
                        as_of,
                    ),
                ]
            )
            if "spend_fen" in ads:
                metrics.append(
                    CanonicalMetric(
                        "ad_spend",
                        "广告消耗",
                        _number(ads, "spend_fen") / 100,
                        "元",
                        None,
                        as_of,
                    )
                )
            if "attributed_revenue_fen" in ads:
                metrics.append(
                    CanonicalMetric(
                        "attributed_revenue",
                        "广告归因成交",
                        _number(ads, "attributed_revenue_fen") / 100,
                        "元",
                        None,
                        as_of,
                    )
                )
            if "ctr_bps" in ads:
                metrics.append(
                    CanonicalMetric(
                        "ad_ctr",
                        "广告点击率",
                        _number(ads, "ctr_bps") / 100,
                        "%",
                        _number(ads, "ctr_change_bps") / 10000,
                        as_of,
                    )
                )
            if "conversion_rate_bps" in ads:
                metrics.append(
                    CanonicalMetric(
                        "ad_conversion_rate",
                        "广告转化率",
                        _number(ads, "conversion_rate_bps") / 100,
                        "%",
                        _number(ads, "conversion_change_bps") / 10000,
                        as_of,
                    )
                )
        crm = resources.get("crm/summary")
        if crm is not None:
            as_of = _timestamp(crm)
            metrics.extend(
                [
                    CanonicalMetric(
                        "active_members",
                        "活跃会员",
                        _number(crm, "active_member_count"),
                        "人",
                        _number(crm, "member_change_bps") / 10000,
                        as_of,
                    ),
                ]
            )
            if "new_member_count" in crm:
                metrics.append(
                    CanonicalMetric(
                        "new_members",
                        "新增会员",
                        _number(crm, "new_member_count"),
                        "人",
                        _number(crm, "new_member_change_bps") / 10000,
                        as_of,
                    )
                )
            if "repeat_purchase_rate_bps" in crm:
                metrics.append(
                    CanonicalMetric(
                        "repeat_purchase_rate",
                        "复购率",
                        _number(crm, "repeat_purchase_rate_bps") / 100,
                        "%",
                        _number(crm, "repeat_purchase_change_bps") / 10000,
                        as_of,
                    )
                )
            if "churn_risk_member_count" in crm:
                metrics.append(
                    CanonicalMetric(
                        "churn_risk_members",
                        "流失风险会员",
                        _number(crm, "churn_risk_member_count"),
                        "人",
                        _number(crm, "churn_risk_change_bps") / 10000,
                        as_of,
                    )
                )
        service = resources.get("service/summary")
        if service is not None:
            as_of = _timestamp(service)
            metrics.extend(
                [
                    CanonicalMetric(
                        "service_conversations",
                        "客服会话",
                        _number(service, "conversation_count"),
                        "次",
                        _number(service, "conversation_change_bps") / 10000,
                        as_of,
                    ),
                    CanonicalMetric(
                        "first_response_minutes",
                        "首次响应时长",
                        _number(service, "first_response_seconds") / 60,
                        "分钟",
                        _number(service, "response_change_bps") / 10000,
                        as_of,
                    ),
                    CanonicalMetric(
                        "service_resolution_rate",
                        "一次解决率",
                        _number(service, "resolution_rate_bps") / 100,
                        "%",
                        _number(service, "resolution_change_bps") / 10000,
                        as_of,
                    ),
                    CanonicalMetric(
                        "csat_score",
                        "客户满意度",
                        _number(service, "csat_score_x100") / 100,
                        "分",
                        _number(service, "csat_change_bps") / 10000,
                        as_of,
                    ),
                    CanonicalMetric(
                        "human_handoff_rate",
                        "人工接管率",
                        _number(service, "human_handoff_rate_bps") / 100,
                        "%",
                        _number(service, "handoff_change_bps") / 10000,
                        as_of,
                    ),
                ]
            )
        return metrics

    @staticmethod
    def _store_scope_key(resources: dict[str, dict[str, object]], shop_code: str) -> str:
        known_scopes = {"TM-001": "store-flagship", "JD-002": "store-outlet"}
        if shop_code in known_scopes:
            return known_scopes[shop_code]
        shops = resources.get("shops")
        shop_items = _items(shops, "shops") if shops is not None else []
        position = next(
            (index for index, item in enumerate(shop_items) if item.get("shop_code") == shop_code),
            None,
        )
        if position == 0:
            return "store-flagship"
        if position == 1:
            return "store-outlet"
        normalized = "".join(
            character.lower() if character.isalnum() else "-" for character in shop_code
        )
        return f"store-{normalized.strip('-')}"
