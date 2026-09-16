from __future__ import annotations

import re

from zhixing_api.actor_context import ActorContext, require_permission
from zhixing_api.data_center_service import query_metric_series
from zhixing_api.data_selection import require_selected_data_scope
from zhixing_api.database import Database
from zhixing_api.knowledge_schemas import MetricContextPointView, MetricContextView

METRIC_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gmv_today", ("成交", "gmv", "销售额", "营收", "交易额")),
    ("orders_today", ("订单", "支付单量", "成交单量")),
    ("refund_rate", ("退款", "退款率", "售后率")),
    ("ad_roi", ("广告", "投放", "roi")),
    ("low_stock_skus", ("库存", "低库存", "缺货")),
    ("active_members", ("会员", "客户", "活跃用户")),
)
DEFAULT_OPERATING_METRICS = ("gmv_today", "orders_today", "refund_rate", "ad_roi")
OPERATING_INTENT_WORDS = ("经营", "指标", "趋势", "数据", "大盘", "表现", "分析", "环比")


def build_metric_context(
    database: Database,
    actor: ActorContext,
    *,
    question: str,
    requested_scope_key: str | None,
) -> list[MetricContextView]:
    metric_keys = detect_metric_keys(question)
    if not metric_keys:
        return []

    selection = actor.scope_selection or {}
    selected = selection.get("store_ids")
    if (requested_scope_key is None and selection.get("scope_level") == "store"
            and isinstance(selected, list) and len(selected) == 1
            and isinstance(selected[0], str)):
        requested_scope_key = selected[0]
    scope_key, scope_type, scope_id = resolve_metric_scope(actor, requested_scope_key)
    require_selected_data_scope(database, actor, scope_key)
    require_permission(
        actor,
        "metric.query.execute",
        database,
        resource_type="metric.series",
        resource_key=f"{scope_key}:{','.join(metric_keys)}",
        scope_type=scope_type,
        scope_id=scope_id,
    )
    response = query_metric_series(
        database,
        metric_keys=metric_keys,
        scope_key=scope_key,
        days=detect_window_days(question),
        enterprise_id=actor.enterprise_id,
    )
    return [
        MetricContextView(
            key=item.key,
            label=item.label,
            unit=item.unit,
            scope_key=item.scope_key,
            definition_version=item.definition_version,
            date_from=response.date_from,
            date_to=response.date_to,
            latest_value=item.latest_value,
            period_change_rate=item.period_change_rate,
            minimum=item.minimum,
            maximum=item.maximum,
            points=[
                MetricContextPointView(
                    as_of=point.as_of,
                    value=point.value,
                    change_rate=point.change_rate,
                )
                for point in item.points
            ],
        )
        for item in response.series
        if item.points
    ]


def detect_metric_keys(question: str) -> list[str]:
    normalized = question.casefold()
    matches = [
        metric_key
        for metric_key, aliases in METRIC_ALIASES
        if any(alias.casefold() in normalized for alias in aliases)
    ]
    if matches:
        return matches
    if any(word in normalized for word in OPERATING_INTENT_WORDS):
        return list(DEFAULT_OPERATING_METRICS)
    return []


def detect_window_days(question: str) -> int:
    explicit = re.search(r"(?:近|最近|过去)\s*(\d{1,3})\s*天", question)
    if explicit:
        return max(1, min(365, int(explicit.group(1))))
    if any(word in question for word in ("本周", "近一周", "最近一周", "过去一周")):
        return 7
    if any(word in question for word in ("本月", "近一个月", "最近一个月", "过去一个月")):
        return 30
    return 30


def resolve_metric_scope(
    actor: ActorContext,
    requested_scope_key: str | None,
) -> tuple[str, str, str]:
    if requested_scope_key:
        scope_key = requested_scope_key.strip()
        if scope_key == "enterprise":
            return scope_key, "enterprise", actor.enterprise_id
        return scope_key, "store", scope_key

    enterprise_granted = any(
        scope.effect == "allow"
        and scope.scope_type == "enterprise"
        and actor.enterprise_id in scope.scope_ids
        for scope in actor.scopes
    )
    if enterprise_granted:
        return "enterprise", "enterprise", actor.enterprise_id

    store_keys = sorted(
        scope_id
        for scope in actor.scopes
        if scope.effect == "allow" and scope.scope_type == "store"
        for scope_id in scope.scope_ids
    )
    if store_keys:
        return store_keys[0], "store", store_keys[0]
    return "enterprise", "enterprise", actor.enterprise_id
