from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import select

from zhixing_api.actor_context import resolve_enterprise_id
from zhixing_api.customer_360_schemas import (
    Customer360Response,
    Customer360Summary,
    CustomerChannelView,
    CustomerDetailResponse,
    CustomerDetailSummary,
    CustomerLineageAssetView,
    CustomerOrderView,
    CustomerProfileView,
    CustomerRecommendationView,
    CustomerRefundView,
    CustomerSegmentView,
    CustomerTimelineEventView,
    CustomerTouchpointView,
    CustomerTrendPointView,
)
from zhixing_api.data_center_service import resolve_commerce_scope_keys
from zhixing_api.data_models import (
    BusinessEntity,
    CommerceOrderFact,
    CommerceRefundFact,
    CustomerProfile,
    CustomerTouchpointFact,
    ExternalSystem,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem

SEGMENT_LABELS = {
    "new": "新客培育",
    "growing": "成长客户",
    "mature": "成熟客户",
    "sleeping": "沉睡唤醒",
    "at_risk": "流失预警",
}

TOUCHPOINT_LABELS = {
    "visit": "访问店铺",
    "product_view": "浏览商品",
    "add_to_cart": "加入购物车",
    "campaign_click": "点击活动",
    "coupon_claim": "领取优惠券",
    "service": "咨询客服",
}

CUSTOMER_PLAYBOOK_VERSION = "customer-lifecycle-playbook-1.0.0"


def _yuan(value_fen: int) -> float:
    return round(value_fen / 100, 2)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def build_customer_360(
    database: Database,
    *,
    scope_key: str,
    enterprise_id: str | None = None,
    limit: int = 50,
) -> Customer360Response:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    external_store_keys = resolve_commerce_scope_keys(
        database,
        scope_key=scope_key,
        enterprise_id=enterprise_id,
    )
    with database.session() as session:
        profiles = list(
            session.scalars(
                select(CustomerProfile)
                .where(CustomerProfile.enterprise_id == enterprise_id)
                .order_by(CustomerProfile.churn_risk_score.desc(), CustomerProfile.customer_key)
            )
        )
        touchpoints = list(
            session.scalars(
                select(CustomerTouchpointFact)
                .where(CustomerTouchpointFact.enterprise_id == enterprise_id)
                .order_by(CustomerTouchpointFact.occurred_at.desc())
            )
        )
        orders = list(
            session.scalars(
                select(CommerceOrderFact).where(CommerceOrderFact.enterprise_id == enterprise_id)
            )
        )
        refunds = list(
            session.scalars(
                select(CommerceRefundFact).where(
                    CommerceRefundFact.enterprise_id == enterprise_id
                )
            )
        )
        stores = {
            item.canonical_key: item
            for item in session.scalars(
                select(BusinessEntity).where(
                    BusinessEntity.enterprise_id == enterprise_id,
                    BusinessEntity.entity_type == "store",
                )
            )
        }
        sources = {
            item.id: item
            for item in session.scalars(
                select(ExternalSystem).where(ExternalSystem.enterprise_id == enterprise_id)
            )
        }

    if external_store_keys is not None:
        profiles = [item for item in profiles if item.home_store_key in external_store_keys]
        touchpoints = [item for item in touchpoints if item.store_key in external_store_keys]
        orders = [item for item in orders if item.store_key in external_store_keys]
        refunds = [item for item in refunds if item.store_key in external_store_keys]

    profile_keys = {item.customer_key for item in profiles}
    orders = [item for item in orders if item.customer_key in profile_keys]
    refunds = [item for item in refunds if item.customer_key in profile_keys]
    touchpoints = [item for item in touchpoints if item.customer_key in profile_keys]

    orders_by_customer: dict[str, list[CommerceOrderFact]] = defaultdict(list)
    refunds_by_customer: dict[str, list[CommerceRefundFact]] = defaultdict(list)
    touchpoints_by_customer: dict[str, list[CustomerTouchpointFact]] = defaultdict(list)
    for order_item in orders:
        orders_by_customer[order_item.customer_key].append(order_item)
    for refund_item in refunds:
        refunds_by_customer[refund_item.customer_key].append(refund_item)
    for touchpoint_item in touchpoints:
        touchpoints_by_customer[touchpoint_item.customer_key].append(touchpoint_item)

    purchasing_keys = {key for key, rows in orders_by_customer.items() if rows}
    repeat_keys = {key for key, rows in orders_by_customer.items() if len(rows) >= 2}
    paid_gmv_fen = sum(item.paid_amount_fen for item in orders)
    summary = Customer360Summary(
        profile_count=len(profiles),
        active_customer_count=sum(item.status == "active" for item in profiles),
        consented_customer_count=sum(item.consent_status == "granted" for item in profiles),
        at_risk_customer_count=sum(
            item.lifecycle_stage == "at_risk" or item.churn_risk_score >= 0.7
            for item in profiles
        ),
        purchasing_customer_count=len(purchasing_keys),
        repeat_customer_count=len(repeat_keys),
        repeat_purchase_rate=_ratio(len(repeat_keys), len(purchasing_keys)),
        paid_gmv_yuan=_yuan(paid_gmv_fen),
        average_customer_value_yuan=_yuan(
            round(paid_gmv_fen / len(purchasing_keys)) if purchasing_keys else 0
        ),
        touchpoint_count=len(touchpoints),
    )

    segment_profiles: dict[str, list[CustomerProfile]] = defaultdict(list)
    channel_profiles: dict[str, list[CustomerProfile]] = defaultdict(list)
    for profile in profiles:
        segment_profiles[profile.lifecycle_stage].append(profile)
        channel_profiles[profile.acquisition_channel].append(profile)
    segments = []
    for key in ("new", "growing", "mature", "sleeping", "at_risk"):
        rows = segment_profiles.get(key, [])
        keys = {item.customer_key for item in rows}
        segment_orders = [item for item in orders if item.customer_key in keys]
        purchasing = {item.customer_key for item in segment_orders}
        segments.append(
            CustomerSegmentView(
                key=key,
                label=SEGMENT_LABELS[key],
                customer_count=len(rows),
                purchasing_customer_count=len(purchasing),
                paid_gmv_yuan=_yuan(sum(item.paid_amount_fen for item in segment_orders)),
                average_order_count=round(len(segment_orders) / len(rows), 2) if rows else 0,
                at_risk_customer_count=sum(
                    item.lifecycle_stage == "at_risk" or item.churn_risk_score >= 0.7
                    for item in rows
                ),
            )
        )

    channels = []
    for key, rows in channel_profiles.items():
        keys = {item.customer_key for item in rows}
        channel_orders = [item for item in orders if item.customer_key in keys]
        channel_touchpoints = [item for item in touchpoints if item.customer_key in keys]
        channels.append(
            CustomerChannelView(
                key=key,
                label=key,
                customer_count=len(rows),
                touchpoint_count=len(channel_touchpoints),
                purchasing_customer_count=len({item.customer_key for item in channel_orders}),
                paid_gmv_yuan=_yuan(sum(item.paid_amount_fen for item in channel_orders)),
            )
        )
    channels.sort(key=lambda item: (item.paid_gmv_yuan, item.customer_count), reverse=True)

    trend_counts: dict[date, list[CustomerTouchpointFact]] = defaultdict(list)
    for touchpoint_item in touchpoints:
        trend_counts[touchpoint_item.occurred_at.date()].append(touchpoint_item)
    touchpoint_trend = [
        CustomerTrendPointView(
            business_date=business_date,
            touchpoint_count=len(rows),
            active_customer_count=len({item.customer_key for item in rows}),
        )
        for business_date, rows in sorted(trend_counts.items())[-30:]
    ]

    profile_views = []
    for profile in profiles:
        customer_orders = sorted(
            orders_by_customer.get(profile.customer_key, []),
            key=lambda item: item.paid_at,
            reverse=True,
        )
        customer_touchpoints = touchpoints_by_customer.get(profile.customer_key, [])
        source = sources[profile.external_system_id]
        profile_views.append(
            CustomerProfileView(
                customer_key=profile.customer_key,
                display_name=profile.display_name,
                home_store_key=profile.home_store_key,
                home_store_name=(
                    stores[profile.home_store_key].display_name
                    if profile.home_store_key in stores
                    else profile.home_store_key
                ),
                member_level=profile.member_level,
                lifecycle_stage=profile.lifecycle_stage,
                status=profile.status,
                province=profile.province,
                acquisition_channel=profile.acquisition_channel,
                preferred_category=profile.preferred_category,
                churn_risk_score=round(profile.churn_risk_score, 4),
                consent_status=profile.consent_status,
                member_points=profile.member_points,
                growth_value=profile.growth_value,
                tags=list(profile.tags),
                registered_at=profile.registered_at,
                last_active_at=profile.last_active_at,
                order_count=len(customer_orders),
                paid_gmv_yuan=_yuan(sum(item.paid_amount_fen for item in customer_orders)),
                refund_amount_yuan=_yuan(
                    sum(
                        item.refund_amount_fen
                        for item in refunds_by_customer.get(profile.customer_key, [])
                    )
                ),
                last_order_at=customer_orders[0].paid_at if customer_orders else None,
                touchpoint_count=len(customer_touchpoints),
                last_touchpoint_at=(
                    max(item.occurred_at for item in customer_touchpoints)
                    if customer_touchpoints
                    else None
                ),
                source_key=source.system_key,
                sync_run_id=profile.sync_run_id,
            )
        )
    profile_views.sort(
        key=lambda item: (item.churn_risk_score, item.paid_gmv_yuan, item.touchpoint_count),
        reverse=True,
    )

    names = {item.customer_key: item.display_name for item in profiles}
    recent_touchpoints = [
        CustomerTouchpointView(
            touchpoint_key=item.touchpoint_key,
            customer_key=item.customer_key,
            customer_name=names.get(item.customer_key, item.customer_key),
            store_key=item.store_key,
            touchpoint_type=item.touchpoint_type,
            channel=item.channel,
            occurred_at=item.occurred_at,
            campaign_key=item.campaign_key,
            value_yuan=_yuan(item.value_fen),
            properties=item.properties,
            source_key=sources[item.external_system_id].system_key,
            sync_run_id=item.sync_run_id,
        )
        for item in touchpoints[:limit]
    ]
    lineage = _customer_lineage(profiles, touchpoints, orders, sources)
    return Customer360Response(
        scope_key=scope_key,
        summary=summary,
        segments=segments,
        channels=channels,
        touchpoint_trend=touchpoint_trend,
        customers=profile_views[:limit],
        recent_touchpoints=recent_touchpoints,
        lineage=lineage,
        generated_at=datetime.now(UTC),
    )


def build_customer_detail(
    database: Database,
    *,
    scope_key: str,
    customer_key: str,
    enterprise_id: str | None = None,
    limit: int = 50,
) -> CustomerDetailResponse:
    enterprise_id = resolve_enterprise_id(database, enterprise_id)
    external_store_keys = resolve_commerce_scope_keys(
        database,
        scope_key=scope_key,
        enterprise_id=enterprise_id,
    )
    with database.session() as session:
        profile = session.scalar(
            select(CustomerProfile).where(
                CustomerProfile.enterprise_id == enterprise_id,
                CustomerProfile.customer_key == customer_key,
            )
        )
        orders = list(
            session.scalars(
                select(CommerceOrderFact)
                .where(
                    CommerceOrderFact.enterprise_id == enterprise_id,
                    CommerceOrderFact.customer_key == customer_key,
                )
                .order_by(CommerceOrderFact.paid_at.desc())
            )
        )
        refunds = list(
            session.scalars(
                select(CommerceRefundFact)
                .where(
                    CommerceRefundFact.enterprise_id == enterprise_id,
                    CommerceRefundFact.customer_key == customer_key,
                )
                .order_by(CommerceRefundFact.requested_at.desc())
            )
        )
        touchpoints = list(
            session.scalars(
                select(CustomerTouchpointFact)
                .where(
                    CustomerTouchpointFact.enterprise_id == enterprise_id,
                    CustomerTouchpointFact.customer_key == customer_key,
                )
                .order_by(CustomerTouchpointFact.occurred_at.desc())
            )
        )
        stores = {
            item.canonical_key: item
            for item in session.scalars(
                select(BusinessEntity).where(
                    BusinessEntity.enterprise_id == enterprise_id,
                    BusinessEntity.entity_type == "store",
                )
            )
        }
        sources = {
            item.id: item
            for item in session.scalars(
                select(ExternalSystem).where(ExternalSystem.enterprise_id == enterprise_id)
            )
        }

    if profile is None or (
        external_store_keys is not None and profile.home_store_key not in external_store_keys
    ):
        raise ApiProblem(
            status_code=404,
            code="customer.profile_not_found",
            message="当前数据范围内没有找到该客户画像",
            details={"customer_key": customer_key, "scope_key": scope_key},
        )
    if external_store_keys is not None:
        orders = [item for item in orders if item.store_key in external_store_keys]
        refunds = [item for item in refunds if item.store_key in external_store_keys]
        touchpoints = [item for item in touchpoints if item.store_key in external_store_keys]

    paid_gmv_fen = sum(item.paid_amount_fen for item in orders)
    refund_amount_fen = sum(item.refund_amount_fen for item in refunds)
    now = datetime.now(UTC)
    last_order_at = orders[0].paid_at if orders else None
    risk_level: Literal["low", "medium", "high"] = (
        "high"
        if profile.lifecycle_stage == "at_risk" or profile.churn_risk_score >= 0.7
        else "medium"
        if profile.lifecycle_stage == "sleeping" or profile.churn_risk_score >= 0.45
        else "low"
    )
    summary = CustomerDetailSummary(
        lifetime_order_count=len(orders),
        paid_gmv_yuan=_yuan(paid_gmv_fen),
        average_order_value_yuan=_yuan(round(paid_gmv_fen / len(orders)) if orders else 0),
        refund_count=len(refunds),
        refund_amount_yuan=_yuan(refund_amount_fen),
        refund_rate=_ratio(refund_amount_fen, paid_gmv_fen),
        touchpoint_count=len(touchpoints),
        days_since_last_active=max((now - _aware(profile.last_active_at)).days, 0),
        days_since_last_order=(
            max((now - _aware(last_order_at)).days, 0) if last_order_at is not None else None
        ),
        engagement_eligible=profile.consent_status == "granted" and profile.status == "active",
        risk_level=risk_level,
    )
    profile_view = _customer_profile_view(
        profile,
        orders=orders,
        refunds=refunds,
        touchpoints=touchpoints,
        stores=stores,
        sources=sources,
    )
    order_views = [
        CustomerOrderView(
            order_key=item.order_key,
            store_key=item.store_key,
            store_name=(
                stores[item.store_key].display_name
                if item.store_key in stores
                else item.store_key
            ),
            channel=item.channel,
            status=item.status,
            business_date=item.business_date,
            paid_at=item.paid_at,
            shipped_at=item.shipped_at,
            paid_amount_yuan=_yuan(item.paid_amount_fen),
            gross_margin_yuan=_yuan(item.paid_amount_fen - item.cost_amount_fen),
            gross_margin_rate=_ratio(
                item.paid_amount_fen - item.cost_amount_fen, item.paid_amount_fen
            ),
            item_count=item.item_count,
            source_key=sources[item.external_system_id].system_key,
            sync_run_id=item.sync_run_id,
        )
        for item in orders[:limit]
    ]
    refund_views = [
        CustomerRefundView(
            refund_key=item.refund_key,
            order_key=item.order_key,
            sku_key=item.sku_key,
            reason_category=item.reason_category,
            status=item.status,
            requested_at=item.requested_at,
            completed_at=item.completed_at,
            refund_amount_yuan=_yuan(item.refund_amount_fen),
            quantity=item.quantity,
            source_key=sources[item.external_system_id].system_key,
            sync_run_id=item.sync_run_id,
        )
        for item in refunds[:limit]
    ]
    touchpoint_views = [
        _customer_touchpoint_view(item, profile.display_name, sources)
        for item in touchpoints[:limit]
    ]
    timeline = _customer_timeline(
        profile,
        orders=orders,
        refunds=refunds,
        touchpoints=touchpoints,
        sources=sources,
        limit=limit,
    )
    recommendations = _customer_recommendations(
        profile,
        summary=summary,
        orders=orders,
        refunds=refunds,
        touchpoints=touchpoints,
    )
    return CustomerDetailResponse(
        scope_key=scope_key,
        customer_key=customer_key,
        playbook_version=CUSTOMER_PLAYBOOK_VERSION,
        profile=profile_view,
        summary=summary,
        recommendations=recommendations,
        timeline=timeline,
        orders=order_views,
        refunds=refund_views,
        touchpoints=touchpoint_views,
        lineage=_customer_lineage([profile], touchpoints, orders, sources),
        generated_at=now,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _customer_profile_view(
    profile: CustomerProfile,
    *,
    orders: list[CommerceOrderFact],
    refunds: list[CommerceRefundFact],
    touchpoints: list[CustomerTouchpointFact],
    stores: dict[str, BusinessEntity],
    sources: dict[str, ExternalSystem],
) -> CustomerProfileView:
    sorted_orders = sorted(orders, key=lambda item: item.paid_at, reverse=True)
    return CustomerProfileView(
        customer_key=profile.customer_key,
        display_name=profile.display_name,
        home_store_key=profile.home_store_key,
        home_store_name=(
            stores[profile.home_store_key].display_name
            if profile.home_store_key in stores
            else profile.home_store_key
        ),
        member_level=profile.member_level,
        lifecycle_stage=profile.lifecycle_stage,
        status=profile.status,
        province=profile.province,
        acquisition_channel=profile.acquisition_channel,
        preferred_category=profile.preferred_category,
        churn_risk_score=round(profile.churn_risk_score, 4),
        consent_status=profile.consent_status,
        member_points=profile.member_points,
        growth_value=profile.growth_value,
        tags=list(profile.tags),
        registered_at=profile.registered_at,
        last_active_at=profile.last_active_at,
        order_count=len(sorted_orders),
        paid_gmv_yuan=_yuan(sum(item.paid_amount_fen for item in sorted_orders)),
        refund_amount_yuan=_yuan(sum(item.refund_amount_fen for item in refunds)),
        last_order_at=sorted_orders[0].paid_at if sorted_orders else None,
        touchpoint_count=len(touchpoints),
        last_touchpoint_at=(
            max(item.occurred_at for item in touchpoints) if touchpoints else None
        ),
        source_key=sources[profile.external_system_id].system_key,
        sync_run_id=profile.sync_run_id,
    )


def _customer_touchpoint_view(
    item: CustomerTouchpointFact,
    customer_name: str,
    sources: dict[str, ExternalSystem],
) -> CustomerTouchpointView:
    return CustomerTouchpointView(
        touchpoint_key=item.touchpoint_key,
        customer_key=item.customer_key,
        customer_name=customer_name,
        store_key=item.store_key,
        touchpoint_type=item.touchpoint_type,
        channel=item.channel,
        occurred_at=item.occurred_at,
        campaign_key=item.campaign_key,
        value_yuan=_yuan(item.value_fen),
        properties=item.properties,
        source_key=sources[item.external_system_id].system_key,
        sync_run_id=item.sync_run_id,
    )


def _customer_timeline(
    profile: CustomerProfile,
    *,
    orders: list[CommerceOrderFact],
    refunds: list[CommerceRefundFact],
    touchpoints: list[CustomerTouchpointFact],
    sources: dict[str, ExternalSystem],
    limit: int,
) -> list[CustomerTimelineEventView]:
    profile_source = sources[profile.external_system_id].system_key
    events = [
        CustomerTimelineEventView(
            event_key=f"profile:{profile.customer_key}",
            event_type="profile",
            occurred_at=profile.registered_at,
            title="客户注册",
            detail=f"通过 {profile.acquisition_channel} 进入客户主档",
            value_yuan=None,
            source_key=profile_source,
            sync_run_id=profile.sync_run_id,
            evidence_key=f"profile:{profile.customer_key}",
        )
    ]
    events.extend(
        CustomerTimelineEventView(
            event_key=f"order:{item.order_key}",
            event_type="order",
            occurred_at=item.paid_at,
            title="支付订单",
            detail=f"{item.channel} · {item.item_count} 件 · {item.status}",
            value_yuan=_yuan(item.paid_amount_fen),
            source_key=sources[item.external_system_id].system_key,
            sync_run_id=item.sync_run_id,
            evidence_key=f"order:{item.order_key}",
        )
        for item in orders
    )
    events.extend(
        CustomerTimelineEventView(
            event_key=f"refund:{item.refund_key}",
            event_type="refund",
            occurred_at=item.requested_at,
            title="发起退款",
            detail=f"{item.reason_category} · {item.status}",
            value_yuan=_yuan(item.refund_amount_fen),
            source_key=sources[item.external_system_id].system_key,
            sync_run_id=item.sync_run_id,
            evidence_key=f"refund:{item.refund_key}",
        )
        for item in refunds
    )
    events.extend(
        CustomerTimelineEventView(
            event_key=f"touchpoint:{item.touchpoint_key}",
            event_type="touchpoint",
            occurred_at=item.occurred_at,
            title=TOUCHPOINT_LABELS.get(item.touchpoint_type, item.touchpoint_type),
            detail=f"{item.channel} · {item.campaign_key or '自然行为'}",
            value_yuan=_yuan(item.value_fen) if item.value_fen else None,
            source_key=sources[item.external_system_id].system_key,
            sync_run_id=item.sync_run_id,
            evidence_key=f"touchpoint:{item.touchpoint_key}",
        )
        for item in touchpoints
    )
    events.sort(key=lambda item: _aware(item.occurred_at), reverse=True)
    return events[:limit]


def _customer_recommendations(
    profile: CustomerProfile,
    *,
    summary: CustomerDetailSummary,
    orders: list[CommerceOrderFact],
    refunds: list[CommerceRefundFact],
    touchpoints: list[CustomerTouchpointFact],
) -> list[CustomerRecommendationView]:
    profile_evidence = f"profile:{profile.customer_key}"
    latest_order_evidence = f"order:{orders[0].order_key}" if orders else profile_evidence
    latest_touchpoint_evidence = (
        f"touchpoint:{touchpoints[0].touchpoint_key}" if touchpoints else profile_evidence
    )
    recommendations: list[CustomerRecommendationView] = []
    lifecycle_label = SEGMENT_LABELS.get(profile.lifecycle_stage, profile.lifecycle_stage)
    if not summary.engagement_eligible:
        recommendations.append(
            CustomerRecommendationView(
                key="consent-boundary",
                title="先核验客户触达授权",
                priority="critical",
                rationale="客户当前未授权营销触达或主档已停用。",
                objective="恢复合规的客户联系边界",
                action_boundary="禁止自动发送营销消息、优惠券或调用外部 CRM 写入。",
                eligible=False,
                evidence_keys=[profile_evidence],
            )
        )
    if summary.risk_level == "high":
        recommendations.append(
            CustomerRecommendationView(
                key="retention-review",
                title="进入高风险客户人工复核队列",
                priority="high",
                rationale=(
                    f"生命周期为 {lifecycle_label}，"
                    f"流失风险分为 {profile.churn_risk_score:.0%}。"
                ),
                objective="确认流失原因并形成可审批的挽回方案",
                action_boundary="只生成方案；优惠、补偿和对外联系均需人工确认。",
                eligible=summary.engagement_eligible,
                evidence_keys=[profile_evidence, latest_order_evidence, latest_touchpoint_evidence],
            )
        )
    elif profile.lifecycle_stage == "sleeping" or summary.days_since_last_active >= 45:
        recommendations.append(
            CustomerRecommendationView(
                key="reactivation-review",
                title="评估沉睡客户唤醒方案",
                priority="medium",
                rationale=f"客户已 {summary.days_since_last_active} 天未活跃。",
                objective="用最近偏好和行为设计低打扰唤醒内容",
                action_boundary="仅在客户允许触达时进入人工审核，不自动发送。",
                eligible=summary.engagement_eligible,
                evidence_keys=[profile_evidence, latest_touchpoint_evidence],
            )
        )
    elif profile.lifecycle_stage == "new":
        recommendations.append(
            CustomerRecommendationView(
                key="new-customer-onboarding",
                title="完成新客首购与偏好培育",
                priority="medium",
                rationale="客户仍处于新客阶段，需要结合已浏览品类判断首购路径。",
                objective="缩短首次购买路径并补全有效偏好",
                action_boundary="不自动发券；先由运营确认人群规则和活动库存。",
                eligible=summary.engagement_eligible,
                evidence_keys=[profile_evidence, latest_touchpoint_evidence],
            )
        )
    elif summary.lifetime_order_count >= 2:
        recommendations.append(
            CustomerRecommendationView(
                key="loyalty-growth",
                title="纳入复购与会员成长观察",
                priority="low",
                rationale=(
                    f"客户累计 {summary.lifetime_order_count} 单，"
                    f"成交 {summary.paid_gmv_yuan:.2f} 元。"
                ),
                objective="围绕偏好品类提升复购质量而非单纯增加触达次数",
                action_boundary="建议只进入运营人群候选，外部动作仍需人工确认。",
                eligible=summary.engagement_eligible,
                evidence_keys=[profile_evidence, latest_order_evidence],
            )
        )
    if summary.refund_rate >= 0.15:
        refund_evidence = f"refund:{refunds[0].refund_key}" if refunds else latest_order_evidence
        recommendations.append(
            CustomerRecommendationView(
                key="refund-experience-review",
                title="复核退款原因与商品体验",
                priority="high",
                rationale=f"累计退款金额占成交金额 {summary.refund_rate:.1%}。",
                objective="识别商品、履约或服务问题，避免用营销掩盖体验缺口",
                action_boundary="补偿、退款承诺和工单变更必须转客服或人工审批。",
                eligible=True,
                evidence_keys=[latest_order_evidence, refund_evidence],
            )
        )
    return recommendations


def _customer_lineage(
    profiles: list[CustomerProfile],
    touchpoints: list[CustomerTouchpointFact],
    orders: list[CommerceOrderFact],
    sources: dict[str, ExternalSystem],
) -> list[CustomerLineageAssetView]:
    assets: list[tuple[str, str, str, list[object]]] = [
        ("profiles", "客户主档", "customer_profiles", list(profiles)),
        ("touchpoints", "客户触点事实", "customer_touchpoint_facts", list(touchpoints)),
        ("orders", "关联订单事实", "commerce_order_facts", list(orders)),
    ]
    result = []
    for key, label, table_name, rows in assets:
        first = rows[0] if rows else None
        source = sources.get(str(getattr(first, "external_system_id", ""))) if first else None
        result.append(
            CustomerLineageAssetView(
                key=key,
                label=label,
                table_name=table_name,
                record_count=len(rows),
                source_key=source.system_key if source else "not-synced",
                source_schema_version=source.source_schema_version if source else "unknown",
                mapping_version=source.mapping_version if source else "unknown",
                latest_sync_run_id=(
                    str(getattr(first, "sync_run_id", "")) if first is not None else None
                ),
            )
        )
    return result
