from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import FastAPI, HTTPException, status

from mock_commerce import __version__

Scenario = Literal["normal", "delayed", "partial", "failure"]
VolumeProfile = Literal["small", "standard", "large"]
MetricDomain = Literal["aggregate", "erp-oms", "crm", "advertising", "customer-service"]

VOLUME_COUNTS: dict[VolumeProfile, dict[str, int]] = {
    "small": {
        "shops": 3,
        "products": 12,
        "skus": 36,
        "warehouses": 2,
        "customers": 18,
        "customer_touchpoints": 108,
        "orders": 24,
        "ad_campaigns": 24,
        "service_conversations": 60,
    },
    "standard": {
        "shops": 6,
        "products": 36,
        "skus": 144,
        "warehouses": 5,
        "customers": 90,
        "customer_touchpoints": 540,
        "orders": 180,
        "ad_campaigns": 96,
        "service_conversations": 360,
    },
    "large": {
        "shops": 12,
        "products": 120,
        "skus": 600,
        "warehouses": 12,
        "customers": 600,
        "customer_touchpoints": 3600,
        "orders": 1200,
        "ad_campaigns": 480,
        "service_conversations": 2400,
    },
}

VOLUME_FACTORS: dict[VolumeProfile, float] = {
    "small": 0.25,
    "standard": 1.0,
    "large": 4.0,
}

METRIC_HISTORY_DAYS = 90
METRIC_HISTORY_END = date(2026, 8, 27)
COMMERCE_FACT_DATE = date(2026, 8, 25)
AD_PERFORMANCE_DAYS = 30

# Stable acceptance records link the customer-service sandbox to canonical commerce facts.
# One separate record (order 529) intentionally remains conflicting for reconciliation tests.
CUSTOMER_SERVICE_ORDER_OVERRIDES: dict[int, dict[str, int | str]] = {
    88: {"paid_amount_fen": 19_900, "item_count": 1, "order_state": "COMPLETED"},
    108: {"paid_amount_fen": 15_900, "item_count": 2, "order_state": "COMPLETED"},
    214: {"paid_amount_fen": 69_900, "item_count": 1, "order_state": "REFUNDED"},
    255: {"paid_amount_fen": 45_900, "item_count": 1, "order_state": "COMPLETED"},
    406: {"paid_amount_fen": 8_900, "item_count": 1, "order_state": "COMPLETED"},
    422: {"paid_amount_fen": 39_900, "item_count": 1, "order_state": "SHIPPED"},
    476: {"paid_amount_fen": 32_900, "item_count": 1, "order_state": "COMPLETED"},
    517: {"paid_amount_fen": 26_800, "item_count": 1, "order_state": "SHIPPED"},
    593: {"paid_amount_fen": 52_900, "item_count": 1, "order_state": "PAID"},
}

CUSTOMER_SERVICE_REFUND_OVERRIDES: dict[int, str | None] = {
    214: "COMPLETED",
    406: None,
    476: None,
}


def volume_count(volume: VolumeProfile, resource: str) -> int:
    return VOLUME_COUNTS[volume][resource]


def shop_items(volume: VolumeProfile) -> list[dict[str, object]]:
    templates = [
        ("TM", "天猫旗舰店", "tmall", "陈晓峰"),
        ("JD", "京东自营店", "jd", "周宁"),
        ("DY", "抖音品牌店", "douyin", "赵一帆"),
        ("PDD", "拼多多专营店", "pdd", "陆文博"),
        ("KS", "快手品牌店", "kuaishou", "苏晴"),
        ("WX", "微信小店", "wechat", "方可欣"),
        ("VIP", "唯品会旗舰店", "vip", "王越"),
        ("RED", "小红书品牌店", "xiaohongshu", "程露"),
        ("SN", "苏宁自营店", "suning", "马骏"),
        ("TB", "淘宝企业店", "taobao", "叶晓"),
        ("MT", "美团零售店", "meituan", "吴欢"),
        ("OFF", "品牌官方商城", "official", "沈舟"),
    ]
    return [
        {
            "shop_code": f"{code}-{index + 1:03d}",
            "shop_title": title,
            "channel": channel,
            "shop_state": "ACTIVE",
            "manager_name": manager,
        }
        for index, (code, title, channel, manager) in enumerate(
            templates[: volume_count(volume, "shops")]
        )
    ]


def product_items(volume: VolumeProfile) -> list[dict[str, object]]:
    categories = ["护肤", "个护", "家清", "食品", "家居", "母婴"]
    brands = ["知行", "澄光", "沐研", "简集"]
    teams = ["美妆事业部", "生活方式事业部", "新消费事业部"]
    return [
        {
            "product_code": f"SPU-{index:05d}",
            "product_name": (
                f"{brands[index % len(brands)]}"
                f"{categories[index % len(categories)]}系列 {index:03d}"
            ),
            "brand_name": brands[index % len(brands)],
            "category_name": categories[index % len(categories)],
            "owner_team": teams[index % len(teams)],
            "product_state": "ACTIVE" if index % 17 else "INACTIVE",
        }
        for index in range(1, volume_count(volume, "products") + 1)
    ]


def sku_items(volume: VolumeProfile) -> list[dict[str, object]]:
    product_count = volume_count(volume, "products")
    warehouse_count = volume_count(volume, "warehouses")
    return [
        {
            "sku_code": f"SKU-{index:06d}",
            "sku_name": f"经营商品规格 {index:04d}",
            "product_code": f"SPU-{((index - 1) % product_count) + 1:05d}",
            "warehouse_code": f"WH-{((index - 1) % warehouse_count) + 1:03d}",
            "available_stock": (index * 17) % 320,
            "safety_stock": 40 + (index % 5) * 10,
            "sell_state": "ACTIVE" if index % 29 else "INACTIVE",
        }
        for index in range(1, volume_count(volume, "skus") + 1)
    ]


def warehouse_items(volume: VolumeProfile) -> list[dict[str, object]]:
    regions = ["华东", "华南", "华北", "西南", "华中", "东北"]
    managers = ["韩斌", "许文", "蒋琪", "邱野", "高岚", "潘哲"]
    return [
        {
            "warehouse_code": f"WH-{index:03d}",
            "warehouse_name": f"{regions[(index - 1) % len(regions)]}履约仓 {index:02d}",
            "region_name": regions[(index - 1) % len(regions)],
            "manager_name": managers[(index - 1) % len(managers)],
            "capacity_units": 80_000 + index * 12_500,
            "warehouse_state": "OPERATING",
        }
        for index in range(1, volume_count(volume, "warehouses") + 1)
    ]


def customer_items(volume: VolumeProfile) -> list[dict[str, object]]:
    segments = ["高价值", "成长", "新客", "沉睡", "流失预警"]
    provinces = ["浙江", "江苏", "广东", "山东", "四川", "湖北", "河南", "福建"]
    lifecycle_stages = ["MATURE", "GROWING", "NEW", "SLEEPING", "AT_RISK"]
    member_levels = ["STANDARD", "SILVER", "GOLD", "BLACK_GOLD"]
    categories = ["护肤", "个护", "家清", "食品", "家居", "母婴"]
    shops = shop_items(volume)
    reference_time = datetime(2026, 8, 27, 12, tzinfo=UTC)
    return [
        {
            "customer_code": f"CUS-{index:07d}",
            "customer_name": f"会员 {index:05d}",
            "member_segment": segments[index % len(segments)],
            "member_level": member_levels[(index * 3) % len(member_levels)],
            "lifecycle_stage": lifecycle_stages[index % len(lifecycle_stages)],
            "province_name": provinces[index % len(provinces)],
            "home_shop_code": str(shops[(index - 1) % len(shops)]["shop_code"]),
            "acquisition_channel": str(shops[(index - 1) % len(shops)]["channel"]),
            "registered_at": (
                reference_time - timedelta(days=45 + (index * 17) % 900)
            ).isoformat(),
            "last_active_at": (
                reference_time - timedelta(days=(index * 11) % 120, hours=index % 23)
            ).isoformat(),
            "member_points": (index * 137) % 18_000,
            "growth_value": 80 + (index * 193) % 9_000,
            "churn_risk_score_x10000": (
                8_200 if index % 5 == 0 else 1_100 + (index * 137) % 5_800
            ),
            "preferred_category": categories[(index * 5) % len(categories)],
            "consent_state": "REVOKED" if index % 43 == 0 else "GRANTED",
            "tags": [
                segments[index % len(segments)],
                categories[(index * 5) % len(categories)],
                "高互动" if index % 4 == 0 else "常规互动",
            ],
            "total_order_count": 1 + (index * 7) % 28,
            "member_state": "INACTIVE" if index % 37 == 0 else "ACTIVE",
        }
        for index in range(1, volume_count(volume, "customers") + 1)
    ]


def customer_touchpoint_items(volume: VolumeProfile) -> list[dict[str, object]]:
    customers = customer_items(volume)
    event_types = [
        "VISIT",
        "PRODUCT_VIEW",
        "ADD_TO_CART",
        "CAMPAIGN_CLICK",
        "COUPON_CLAIM",
        "SERVICE",
    ]
    reference_time = datetime(2026, 8, 27, 12, tzinfo=UTC)
    items: list[dict[str, object]] = []
    for index in range(1, volume_count(volume, "customer_touchpoints") + 1):
        customer = customers[(index * 7 - 1) % len(customers)]
        event_type = event_types[(index - 1) % len(event_types)]
        campaign_code = (
            f"CRM-CAM-{((index * 13 - 1) % 24) + 1:04d}"
            if event_type in {"CAMPAIGN_CLICK", "COUPON_CLAIM"}
            else None
        )
        items.append(
            {
                "touchpoint_code": f"CRM-EVT-{index:08d}",
                "customer_code": customer["customer_code"],
                "shop_code": customer["home_shop_code"],
                "event_type": event_type,
                "channel": customer["acquisition_channel"],
                "occurred_at": (
                    reference_time - timedelta(hours=(index * 13) % (24 * 120))
                ).isoformat(),
                "campaign_code": campaign_code,
                "value_fen": 2_000 + (index * 379) % 28_000
                if event_type in {"ADD_TO_CART", "COUPON_CLAIM"}
                else 0,
                "product_code": (
                    f"SPU-{((index * 11 - 1) % volume_count(volume, 'products')) + 1:05d}"
                ),
                "device_type": "MOBILE" if index % 5 else "DESKTOP",
                "session_code": f"CRM-SES-{((index - 1) // 3) + 1:07d}",
            }
        )
    return items


def order_items(volume: VolumeProfile) -> list[dict[str, object]]:
    shop_count = volume_count(volume, "shops")
    customer_count = volume_count(volume, "customers")
    shop_codes = [str(item["shop_code"]) for item in shop_items(volume)]
    states = ["PAID", "SHIPPED", "COMPLETED", "COMPLETED", "REFUNDING"]
    provinces = ["浙江", "江苏", "广东", "山东", "四川", "湖北", "河南", "福建"]
    channels_by_shop = {str(item["shop_code"]): str(item["channel"]) for item in shop_items(volume)}
    return [
        _order_item(
            index,
            shop_codes[(index - 1) % shop_count],
            channels_by_shop,
            customer_count,
            states,
            provinces,
        )
        for index in range(1, volume_count(volume, "orders") + 1)
    ]


def _order_item(
    index: int,
    shop_code: str,
    channels_by_shop: dict[str, str],
    customer_count: int,
    states: list[str],
    provinces: list[str],
) -> dict[str, object]:
    paid_amount = 6_900 + (index * 7_919) % 180_000
    discount_amount = (index * 137) % min(12_000, paid_amount)
    freight_amount = 0 if index % 5 else 800
    item_amount = paid_amount + discount_amount - freight_amount
    cost_amount = round(item_amount * (0.52 + (index % 9) * 0.018))
    status_value = states[index % len(states)]
    item_count = 1 + index % 3
    override = CUSTOMER_SERVICE_ORDER_OVERRIDES.get(index)
    if override is not None:
        paid_amount = int(override["paid_amount_fen"])
        discount_amount = min(discount_amount, paid_amount // 10)
        freight_amount = 0 if index % 5 else 800
        item_amount = paid_amount + discount_amount - freight_amount
        cost_amount = round(item_amount * (0.52 + (index % 9) * 0.018))
        status_value = str(override["order_state"])
        item_count = int(override["item_count"])
    paid_at = datetime(2026, 8, 25, 8 + index % 13, index % 60, tzinfo=UTC)
    shipped_at = paid_at + timedelta(hours=4 + index % 28)
    return {
        "order_code": f"ORD-20260825-{index:06d}",
        "shop_code": shop_code,
        "customer_code": f"CUS-{((index * 13 - 1) % customer_count) + 1:07d}",
        "channel": channels_by_shop[shop_code],
        "paid_amount_fen": paid_amount,
        "item_amount_fen": item_amount,
        "discount_amount_fen": discount_amount,
        "freight_amount_fen": freight_amount,
        "cost_amount_fen": cost_amount,
        "item_count": item_count,
        "order_state": status_value,
        "business_date": COMMERCE_FACT_DATE.isoformat(),
        "paid_at": paid_at.isoformat().replace("+00:00", "Z"),
        "shipped_at": (
            shipped_at.isoformat().replace("+00:00", "Z")
            if status_value in {"SHIPPED", "COMPLETED", "REFUNDING", "REFUNDED"}
            else None
        ),
        "province_name": provinces[index % len(provinces)],
    }


def order_line_items(volume: VolumeProfile) -> list[dict[str, object]]:
    product_count = volume_count(volume, "products")
    sku_count = volume_count(volume, "skus")
    lines: list[dict[str, object]] = []
    for order_index, order in enumerate(order_items(volume), start=1):
        line_count = int(str(order["item_count"]))
        paid_total = int(str(order["paid_amount_fen"]))
        cost_total = int(str(order["cost_amount_fen"]))
        for line_index in range(1, line_count + 1):
            sku_index = ((order_index * 7 + line_index * 11 - 1) % sku_count) + 1
            product_index = ((sku_index - 1) % product_count) + 1
            quantity = 1 + (order_index + line_index) % 3
            paid_amount = paid_total // line_count + (
                paid_total % line_count if line_index == 1 else 0
            )
            cost_amount = cost_total // line_count + (
                cost_total % line_count if line_index == 1 else 0
            )
            refund_quantity = (
                1 if _refund_state(order_index) is not None and line_index == 1 else 0
            )
            refund_amount = paid_amount // quantity if refund_quantity else 0
            lines.append(
                {
                    "line_code": f"{order['order_code']}-L{line_index:02d}",
                    "order_code": order["order_code"],
                    "product_code": f"SPU-{product_index:05d}",
                    "sku_code": f"SKU-{sku_index:06d}",
                    "quantity": quantity,
                    "unit_price_fen": max(1, paid_amount // quantity),
                    "paid_amount_fen": paid_amount,
                    "cost_amount_fen": cost_amount,
                    "refund_quantity": refund_quantity,
                    "refund_amount_fen": refund_amount,
                }
            )
    return lines


def refund_items(volume: VolumeProfile) -> list[dict[str, object]]:
    orders = order_items(volume)
    lines_by_order: dict[str, dict[str, object]] = {}
    for line in order_line_items(volume):
        lines_by_order.setdefault(str(line["order_code"]), line)
    reasons = ["商品质量", "尺码规格", "描述不符", "物流时效", "七天无理由"]
    refunds: list[dict[str, object]] = []
    for index, order in enumerate(orders, start=1):
        refund_status = _refund_state(index)
        if refund_status is None:
            continue
        line = lines_by_order[str(order["order_code"])]
        requested_at = datetime(2026, 8, 26, 9 + index % 10, index % 60, tzinfo=UTC)
        refunds.append(
            {
                "refund_code": f"RFD-20260826-{index:06d}",
                "order_code": order["order_code"],
                "line_code": line["line_code"],
                "shop_code": order["shop_code"],
                "customer_code": order["customer_code"],
                "sku_code": line["sku_code"],
                "reason_category": reasons[index % len(reasons)],
                "refund_state": refund_status,
                "requested_at": requested_at.isoformat().replace("+00:00", "Z"),
                "completed_at": (
                    (requested_at + timedelta(hours=6 + index % 12))
                    .isoformat()
                    .replace("+00:00", "Z")
                    if refund_status == "COMPLETED"
                    else None
                ),
                "refund_amount_fen": int(str(line["refund_amount_fen"])),
                "quantity": int(str(line["refund_quantity"])),
            }
        )
    return refunds


def _refund_state(index: int) -> str | None:
    if index in CUSTOMER_SERVICE_REFUND_OVERRIDES:
        return CUSTOMER_SERVICE_REFUND_OVERRIDES[index]
    if index % 7 != 0:
        return None
    return "COMPLETED" if index % 3 else "APPROVED"


def inventory_snapshot_items(volume: VolumeProfile) -> list[dict[str, object]]:
    snapshots: list[dict[str, object]] = []
    as_of = datetime(2026, 8, 27, 0, 0, tzinfo=UTC)
    for index, sku in enumerate(sku_items(volume), start=1):
        available = int(str(sku["available_stock"]))
        safety = int(str(sku["safety_stock"]))
        reserved = (index * 5) % 31
        in_transit = (index * 13) % 90
        daily_sales = 1 + (index * 7) % 18
        days_cover = round(available / daily_sales, 2)
        state = "inactive" if sku["sell_state"] != "ACTIVE" else (
            "low" if available < safety else "overstock" if days_cover > 45 else "healthy"
        )
        unit_cost = 2_600 + (index * 919) % 18_000
        snapshots.append(
            {
                "inventory_snapshot_code": (
                    f"{sku['warehouse_code']}:{sku['sku_code']}:{COMMERCE_FACT_DATE.isoformat()}"
                ),
                "warehouse_code": sku["warehouse_code"],
                "product_code": sku["product_code"],
                "sku_code": sku["sku_code"],
                "as_of": as_of.isoformat().replace("+00:00", "Z"),
                "available_quantity": available,
                "reserved_quantity": reserved,
                "in_transit_quantity": in_transit,
                "safety_quantity": safety,
                "inventory_cost_fen": available * unit_cost,
                "days_cover": days_cover,
                "inventory_state": state.upper(),
            }
        )
    return snapshots


def advertising_performance_items(volume: VolumeProfile) -> list[dict[str, object]]:
    campaigns = advertising_campaign_items(volume)
    product_count = volume_count(volume, "products")
    start = COMMERCE_FACT_DATE - timedelta(days=AD_PERFORMANCE_DAYS - 1)
    items: list[dict[str, object]] = []
    for campaign_index, campaign in enumerate(campaigns, start=1):
        for day_index in range(AD_PERFORMANCE_DAYS):
            business_date = start + timedelta(days=day_index)
            impressions = 8_000 + (campaign_index * 977 + day_index * 1_103) % 180_000
            ctr = 0.014 + (campaign_index % 8) * 0.0021
            clicks = round(impressions * ctr)
            spend = 18_000 + (campaign_index * 13_711 + day_index * 8_303) % 680_000
            attributed_orders = round(clicks * (0.025 + (campaign_index % 7) * 0.005))
            roi = 1.65 + (campaign_index % 9) * 0.31 + (day_index % 5) * 0.07
            revenue = round(spend * roi)
            items.append(
                {
                    "performance_code": f"{campaign['campaign_code']}:{business_date.isoformat()}",
                    "campaign_code": campaign["campaign_code"],
                    "shop_code": campaign["shop_code"],
                    "product_code": f"SPU-{((campaign_index - 1) % product_count) + 1:05d}",
                    "channel": campaign["channel"],
                    "business_date": business_date.isoformat(),
                    "impressions": impressions,
                    "clicks": clicks,
                    "spend_fen": spend,
                    "attributed_order_count": attributed_orders,
                    "attributed_revenue_fen": revenue,
                }
            )
    return items


def advertising_campaign_items(volume: VolumeProfile) -> list[dict[str, object]]:
    shops = shop_items(volume)
    channels = ["万相台", "京准通", "巨量千川", "磁力金牛", "腾讯广告"]
    teams = ["品牌投放组", "效果增长组", "内容商业化组"]
    return [
        {
            "campaign_code": f"ADP-{index:06d}",
            "campaign_name": f"{channels[index % len(channels)]}经营计划 {index:04d}",
            "shop_code": shops[index % len(shops)]["shop_code"],
            "channel": channels[index % len(channels)],
            "daily_budget_fen": 80_000 + (index * 37_100) % 3_200_000,
            "owner_team": teams[index % len(teams)],
            "campaign_state": "PAUSED" if index % 23 == 0 else "RUNNING",
        }
        for index in range(1, volume_count(volume, "ad_campaigns") + 1)
    ]


def service_conversation_items(volume: VolumeProfile) -> list[dict[str, object]]:
    shops = shop_items(volume)
    customer_count = volume_count(volume, "customers")
    order_count = volume_count(volume, "orders")
    channels = ["天猫旺旺", "京东咚咚", "抖音飞鸽", "微信客服"]
    topics = ["物流催促", "商品咨询", "售后退款", "活动规则", "使用指导"]
    return [
        {
            "conversation_code": f"CSV-{index:07d}",
            "shop_code": shops[index % len(shops)]["shop_code"],
            "customer_code": f"CUS-{((index * 11 - 1) % customer_count) + 1:07d}",
            "order_code": f"ORD-20260825-{((index * 7 - 1) % order_count) + 1:06d}",
            "channel": channels[index % len(channels)],
            "topic": topics[index % len(topics)],
            "risk_level": "high" if index % 29 == 0 else "medium" if index % 11 == 0 else "normal",
            "conversation_state": "CLOSED" if index % 4 == 0 else "OPEN",
            "message_count": 2 + (index * 3) % 19,
        }
        for index in range(1, volume_count(volume, "service_conversations") + 1)
    ]


def _demand_index(day_index: int, business_date: date) -> float:
    weekday_factor = (0.88, 0.94, 1.0, 1.04, 1.1, 1.2, 1.08)[business_date.weekday()]
    campaign_factor = 1.24 if day_index % 28 in (20, 21) else 1.0
    return (0.86 + day_index * 0.0025) * weekday_factor * campaign_factor


def _daily_indicator_value(
    indicator_code: str,
    day_index: int,
    business_date: date,
    factor: float,
) -> int:
    demand = _demand_index(day_index, business_date)
    if indicator_code == "PAID_GMV_FEN":
        return round(218_000_000 * factor * demand)
    if indicator_code == "PAID_ORDER_COUNT":
        return round(11_800 * factor * demand)
    if indicator_code == "REFUND_RATE_BPS":
        return max(360, round(590 - day_index * 0.62 + (business_date.weekday() - 2) * 7))
    if indicator_code == "AD_ROI_X100":
        return round(278 + day_index * 0.52 + (day_index % 9 - 4) * 3)
    if indicator_code == "LOW_STOCK_SKU_COUNT":
        return max(1, round((66 - day_index * 0.22 + business_date.weekday() * 1.4) * factor))
    if indicator_code == "ACTIVE_MEMBER_COUNT":
        return round(158_000 * factor * (0.91 + day_index * 0.0023))
    if indicator_code == "GROSS_MARGIN_RATE_BPS":
        return round(3540 + day_index * 1.7 + (day_index % 11 - 5) * 8)
    if indicator_code == "FULFILLMENT_RATE_BPS":
        return min(9950, round(9560 + day_index * 2.1 - business_date.weekday() * 12))
    if indicator_code == "INVENTORY_TURNOVER_DAYS_X100":
        return max(1200, round(3480 - day_index * 6.2 + business_date.weekday() * 18))
    if indicator_code == "NEW_MEMBER_COUNT":
        return round(2480 * factor * demand)
    if indicator_code == "REPEAT_PURCHASE_RATE_BPS":
        return round(2780 + day_index * 2.8 + (day_index % 8 - 4) * 9)
    if indicator_code == "CHURN_RISK_MEMBER_COUNT":
        return max(1, round((18_600 - day_index * 33) * factor))
    if indicator_code == "AD_SPEND_FEN":
        return round(46_800_000 * factor * demand)
    if indicator_code == "ATTRIBUTED_REVENUE_FEN":
        return round(151_600_000 * factor * demand * (0.96 + day_index * 0.0009))
    if indicator_code == "AD_CTR_BPS":
        return round(238 + day_index * 0.28 + (day_index % 7 - 3) * 3)
    if indicator_code == "AD_CONVERSION_RATE_BPS":
        return round(412 + day_index * 0.36 + (day_index % 10 - 5) * 4)
    if indicator_code == "SERVICE_CONVERSATION_COUNT":
        return round(3_460 * factor * demand)
    if indicator_code == "FIRST_RESPONSE_SECONDS":
        return max(38, round(138 - day_index * 0.52 + business_date.weekday() * 7))
    if indicator_code == "SERVICE_RESOLUTION_RATE_BPS":
        return min(9800, round(8420 + day_index * 4.1 - business_date.weekday() * 9))
    if indicator_code == "CSAT_SCORE_X100":
        return min(500, round(438 + day_index * 0.24 - business_date.weekday() * 1.2))
    if indicator_code == "HUMAN_HANDOFF_RATE_BPS":
        return max(300, round(1460 - day_index * 3.4 + business_date.weekday() * 11))
    raise ValueError(f"unsupported indicator: {indicator_code}")


def _change_bps(value: int, previous: int) -> int:
    if previous == 0:
        return 0
    return round((value / previous - 1) * 10_000)


DOMAIN_ENTERPRISE_INDICATORS: dict[MetricDomain, tuple[str, ...]] = {
    "erp-oms": (
        "PAID_GMV_FEN",
        "PAID_ORDER_COUNT",
        "REFUND_RATE_BPS",
        "LOW_STOCK_SKU_COUNT",
        "GROSS_MARGIN_RATE_BPS",
        "FULFILLMENT_RATE_BPS",
        "INVENTORY_TURNOVER_DAYS_X100",
    ),
    "crm": (
        "ACTIVE_MEMBER_COUNT",
        "NEW_MEMBER_COUNT",
        "REPEAT_PURCHASE_RATE_BPS",
        "CHURN_RISK_MEMBER_COUNT",
    ),
    "advertising": (
        "AD_ROI_X100",
        "AD_SPEND_FEN",
        "ATTRIBUTED_REVENUE_FEN",
        "AD_CTR_BPS",
        "AD_CONVERSION_RATE_BPS",
    ),
    "customer-service": (
        "SERVICE_CONVERSATION_COUNT",
        "FIRST_RESPONSE_SECONDS",
        "SERVICE_RESOLUTION_RATE_BPS",
        "CSAT_SCORE_X100",
        "HUMAN_HANDOFF_RATE_BPS",
    ),
    "aggregate": (),
}

DOMAIN_STORE_INDICATORS: dict[MetricDomain, tuple[str, ...]] = {
    "erp-oms": (
        "PAID_GMV_FEN",
        "PAID_ORDER_COUNT",
        "REFUND_RATE_BPS",
        "GROSS_MARGIN_RATE_BPS",
        "FULFILLMENT_RATE_BPS",
    ),
    "crm": ("ACTIVE_MEMBER_COUNT", "NEW_MEMBER_COUNT", "REPEAT_PURCHASE_RATE_BPS"),
    "advertising": (
        "AD_ROI_X100",
        "AD_SPEND_FEN",
        "ATTRIBUTED_REVENUE_FEN",
        "AD_CTR_BPS",
        "AD_CONVERSION_RATE_BPS",
    ),
    "customer-service": (
        "SERVICE_CONVERSATION_COUNT",
        "FIRST_RESPONSE_SECONDS",
        "SERVICE_RESOLUTION_RATE_BPS",
        "CSAT_SCORE_X100",
        "HUMAN_HANDOFF_RATE_BPS",
    ),
    "aggregate": (),
}


def _domain_indicators(
    domain: MetricDomain, source: dict[MetricDomain, tuple[str, ...]]
) -> tuple[str, ...]:
    if domain != "aggregate":
        return source[domain]
    return tuple(
        indicator for key, values in source.items() if key != "aggregate" for indicator in values
    )


def daily_metric_items(
    volume: VolumeProfile,
    domain: MetricDomain = "aggregate",
) -> list[dict[str, object]]:
    start = METRIC_HISTORY_END - timedelta(days=METRIC_HISTORY_DAYS - 1)
    enterprise_indicators = _domain_indicators(domain, DOMAIN_ENTERPRISE_INDICATORS)
    shop_indicators = _domain_indicators(domain, DOMAIN_STORE_INDICATORS)
    factor = VOLUME_FACTORS[volume]
    shops = shop_items(volume)
    shop_weight_total = sum(1 / (index + 1) ** 0.42 for index in range(len(shops)))
    items: list[dict[str, object]] = []

    for day_index in range(METRIC_HISTORY_DAYS):
        business_date = start + timedelta(days=day_index)
        previous_date = business_date - timedelta(days=1)
        for indicator_code in enterprise_indicators:
            value = _daily_indicator_value(indicator_code, day_index, business_date, factor)
            previous = _daily_indicator_value(
                indicator_code,
                day_index - 1,
                previous_date,
                factor,
            )
            items.append(
                {
                    "metric_observation_key": (
                        f"enterprise:{indicator_code}:{business_date.isoformat()}"
                    ),
                    "scope_type": "enterprise",
                    "shop_code": None,
                    "indicator_code": indicator_code,
                    "business_date": business_date.isoformat(),
                    "value": value,
                    "change_bps": _change_bps(value, previous),
                }
            )

        for shop_index, shop in enumerate(shops):
            shop_code = str(shop["shop_code"])
            weight = (1 / (shop_index + 1) ** 0.42) / shop_weight_total
            performance = 0.94 + (shop_index % 5) * 0.035
            for indicator_code in shop_indicators:
                enterprise_value = _daily_indicator_value(
                    indicator_code,
                    day_index,
                    business_date,
                    factor,
                )
                previous_enterprise = _daily_indicator_value(
                    indicator_code,
                    day_index - 1,
                    previous_date,
                    factor,
                )
                if indicator_code in {
                    "PAID_GMV_FEN",
                    "PAID_ORDER_COUNT",
                    "ACTIVE_MEMBER_COUNT",
                    "NEW_MEMBER_COUNT",
                    "AD_SPEND_FEN",
                    "ATTRIBUTED_REVENUE_FEN",
                    "SERVICE_CONVERSATION_COUNT",
                }:
                    value = max(1, round(enterprise_value * weight * performance))
                    previous = max(1, round(previous_enterprise * weight * performance))
                elif indicator_code == "REFUND_RATE_BPS":
                    value = round(enterprise_value * (0.92 + shop_index * 0.018))
                    previous = round(previous_enterprise * (0.92 + shop_index * 0.018))
                else:
                    value = round(enterprise_value * (0.96 + shop_index * 0.012))
                    previous = round(previous_enterprise * (0.96 + shop_index * 0.012))
                items.append(
                    {
                        "metric_observation_key": (
                            f"{shop_code}:{indicator_code}:{business_date.isoformat()}"
                        ),
                        "scope_type": "shop",
                        "shop_code": shop_code,
                        "indicator_code": indicator_code,
                        "business_date": business_date.isoformat(),
                        "value": value,
                        "change_bps": _change_bps(value, previous),
                    }
                )
    return items


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


async def apply_scenario(scenario: Scenario, resource: str) -> None:
    if scenario == "delayed":
        await asyncio.sleep(0.8)
    if scenario == "failure" or (
        scenario == "partial" and resource in {"ads", "service", "crm-touchpoints"}
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"sandbox scenario rejected resource: {resource}",
        )


def create_app() -> FastAPI:
    app = FastAPI(
        title="第三方电商测试沙箱",
        description="模拟客户现场吉客云、CRM、广告和库存接口",
        version=__version__,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"service": "mock-commerce", "status": "ready", "version": __version__}

    @app.get("/api/v1/profile")
    async def profile(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "profile")
        return {
            "provider_code": "MOCK-JKY-CRM",
            "tenant_code": "CUST-DEMO-001",
            "schema_version": "2026.08",
            "source_schemas": {
                "aggregate": "2026.08",
                "erp_oms": "JKY-ERP-2026.08",
                "crm": "CRM-2026.08",
                "advertising": "ADS-2026.07",
                "customer_service": "CS-2026.05",
            },
            "volume_profile": volume,
            "estimated_detail_records": sum(VOLUME_COUNTS[volume].values()),
            "generated_at": now_iso(),
        }

    @app.get("/api/v1/shops")
    async def shops(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "shops")
        return {"generated_at": now_iso(), "items": shop_items(volume)}

    @app.get("/api/v1/products")
    async def products(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "products")
        return {"generated_at": now_iso(), "items": product_items(volume)}

    @app.get("/api/v1/skus")
    async def skus(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "skus")
        return {"generated_at": now_iso(), "items": sku_items(volume)}

    @app.get("/api/v1/warehouses")
    async def warehouses(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "warehouses")
        return {"generated_at": now_iso(), "items": warehouse_items(volume)}

    @app.get("/api/v1/customers")
    async def customers(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "customers")
        return {"generated_at": now_iso(), "items": customer_items(volume)}

    @app.get("/api/v1/orders/recent")
    async def recent_orders(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "orders")
        return {"generated_at": now_iso(), "items": order_items(volume)}

    @app.get("/api/v1/orders/lines")
    async def order_lines(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "orders")
        return {"generated_at": now_iso(), "items": order_line_items(volume)}

    @app.get("/api/v1/refunds")
    async def refunds(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "orders")
        return {"generated_at": now_iso(), "items": refund_items(volume)}

    @app.get("/api/v1/orders/summary")
    async def order_summary(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "orders")
        factor = VOLUME_FACTORS[volume]
        return {
            "business_date": "2026-08-25",
            "generated_at": now_iso(),
            "paid_order_count": round(12846 * factor),
            "paid_gmv_fen": round(238648900 * factor),
            "refund_rate_bps": 541,
            "gmv_change_bps": 832,
            "order_change_bps": 617,
            "refund_change_bps": 121,
            "gross_margin_rate_bps": 3670,
            "gross_margin_change_bps": 148,
            "fulfillment_rate_bps": 9710,
            "fulfillment_change_bps": 62,
        }

    @app.get("/api/v1/inventory/summary")
    async def inventory_summary(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "inventory")
        factor = VOLUME_FACTORS[volume]
        return {
            "business_date": "2026-08-25",
            "generated_at": now_iso(),
            "sku_count": round(2184 * factor),
            "low_stock_sku_count": round(42 * factor),
            "stock_value_fen": round(1265032200 * factor),
            "inventory_turnover_days_x100": 2860,
            "turnover_change_bps": -312,
        }

    @app.get("/api/v1/inventory/snapshots")
    async def inventory_snapshots(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "inventory")
        return {"generated_at": now_iso(), "items": inventory_snapshot_items(volume)}

    @app.get("/api/v1/ads/summary")
    async def ads_summary(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "ads")
        factor = VOLUME_FACTORS[volume]
        return {
            "business_date": "2026-08-25",
            "generated_at": now_iso(),
            "spend_fen": round(48632000 * factor),
            "attributed_revenue_fen": round(157567680 * factor),
            "roi_x100": 324,
            "roi_change_bps": -630,
            "ctr_bps": 286,
            "ctr_change_bps": 184,
            "conversion_rate_bps": 472,
            "conversion_change_bps": 96,
        }

    @app.get("/api/v1/ads/campaigns")
    async def advertising_campaigns(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "ads")
        return {"generated_at": now_iso(), "items": advertising_campaign_items(volume)}

    @app.get("/api/v1/ads/performance")
    async def advertising_performance(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "ads")
        return {"generated_at": now_iso(), "items": advertising_performance_items(volume)}

    @app.get("/api/v1/crm/summary")
    async def crm_summary(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "crm")
        factor = VOLUME_FACTORS[volume]
        return {
            "business_date": "2026-08-25",
            "generated_at": now_iso(),
            "active_member_count": round(183420 * factor),
            "new_member_count": round(2681 * factor),
            "member_change_bps": 437,
            "new_member_change_bps": 582,
            "repeat_purchase_rate_bps": 3120,
            "repeat_purchase_change_bps": 116,
            "churn_risk_member_count": round(16480 * factor),
            "churn_risk_change_bps": -248,
        }

    @app.get("/api/v1/crm/touchpoints")
    async def crm_touchpoints(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "crm-touchpoints")
        return {"generated_at": now_iso(), "items": customer_touchpoint_items(volume)}

    @app.get("/api/v1/service/conversations")
    async def service_conversations(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "service")
        return {"generated_at": now_iso(), "items": service_conversation_items(volume)}

    @app.get("/api/v1/service/summary")
    async def service_summary(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "service")
        factor = VOLUME_FACTORS[volume]
        return {
            "business_date": "2026-08-25",
            "generated_at": now_iso(),
            "conversation_count": round(3460 * factor),
            "conversation_change_bps": 396,
            "first_response_seconds": 76,
            "response_change_bps": -1180,
            "resolution_rate_bps": 8870,
            "resolution_change_bps": 214,
            "csat_score_x100": 462,
            "csat_change_bps": 88,
            "human_handoff_rate_bps": 1120,
            "handoff_change_bps": -136,
        }

    @app.get("/api/v1/metrics/daily")
    async def daily_metrics(
        scenario: Scenario = "normal",
        volume: VolumeProfile = "standard",
        domain: MetricDomain = "aggregate",
    ) -> dict[str, object]:
        await apply_scenario(scenario, "metrics")
        return {
            "history_days": METRIC_HISTORY_DAYS,
            "business_date_from": (
                METRIC_HISTORY_END - timedelta(days=METRIC_HISTORY_DAYS - 1)
            ).isoformat(),
            "business_date_to": METRIC_HISTORY_END.isoformat(),
            "generated_at": now_iso(),
            "domain": domain,
            "items": daily_metric_items(volume, domain),
        }

    return app


app = create_app()
