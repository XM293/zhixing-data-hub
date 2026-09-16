from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from zhixing_api.config import Settings
from zhixing_api.connectors.contracts import ConnectorBatch, ConnectorError
from zhixing_api.connectors.registry import create_connector
from zhixing_api.customer_service_reconciliation import (
    summarize_customer_service_reconciliation,
)
from zhixing_api.data_center_schemas import (
    BusinessEntityListResponse,
    BusinessEntityView,
    CommerceExceptionView,
    CommerceFunnelStepView,
    CommerceLineageAssetView,
    CommerceOperationsResponse,
    CommerceOperationsSummary,
    CommerceOrderView,
    CommerceStorePerformanceView,
    DatabaseView,
    DataQualityResponse,
    DataQualityView,
    DataSourceView,
    EnterpriseView,
    EventView,
    MetricCatalogResponse,
    MetricCatalogView,
    MetricSeriesPointView,
    MetricSeriesResponse,
    MetricSeriesView,
    MetricView,
    PageView,
    SyncRunListItem,
    SyncRunListResponse,
    SyncRunView,
    TwinActorView,
    TwinDataLayerView,
    TwinEdgeView,
    TwinHotspotView,
    TwinInteractionView,
    TwinMeetingParticipantView,
    TwinMeetingSeatView,
    TwinMeetingView,
    TwinNodeView,
    TwinObjectActionView,
    TwinOverviewResponse,
    TwinRouteView,
    TwinSceneView,
    TwinSpaceView,
)
from zhixing_api.data_models import (
    AgentRun,
    BusinessEntity,
    CommerceAdPerformanceFact,
    CommerceInventorySnapshotFact,
    CommerceOrderFact,
    CommerceOrderLineFact,
    CommerceRefundFact,
    CustomerOperationRun,
    CustomerProfile,
    CustomerTouchpointFact,
    DataQualityResult,
    DataQualityRule,
    DataScopeMapping,
    Enterprise,
    ExternalSystem,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    MetricDefinition,
    MetricSnapshot,
    PlatformEvent,
    RawPageManifest,
    RoleTwinProfile,
    SourceRecord,
    SyncResourceRun,
    SyncRun,
    ToolDefinition,
    ToolInvocation,
    TwinActor,
    TwinDataLayer,
    TwinEdge,
    TwinHotspot,
    TwinInteractionProfile,
    TwinMeeting,
    TwinMeetingParticipant,
    TwinMeetingSeat,
    TwinNode,
    TwinRoute,
    TwinScene,
    TwinSpace,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem

SOURCE_KEY_ALIASES = {"mock-commerce": "jky-erp-oms"}


def _resolve_enterprise_id(database: Database, enterprise_id: str | None) -> str:
    """Resolve an omitted scope from persisted organization state, never a demo constant."""
    if enterprise_id:
        return enterprise_id
    with database.session() as session:
        resolved = list(session.scalars(select(Enterprise.id).order_by(Enterprise.id).limit(2)))
    if len(resolved) != 1:
        raise LookupError("enterprise scope is required")
    return resolved[0]


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _run_view(run: SyncRun, *, source_key: str | None = None) -> SyncRunView:
    return SyncRunView(
        id=run.id,
        source_key=source_key,
        source_version=run.source_version,
        status=run.status,
        scenario=run.scenario,
        volume_profile=run.volume_profile,
        records_read=run.records_read,
        records_written=run.records_written,
        warning=run.warning,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _duration_seconds(started_at: datetime, finished_at: datetime | None) -> float | None:
    if finished_at is None:
        return None
    return max((finished_at - started_at).total_seconds(), 0.0)


def list_sync_runs(
    database: Database,
    *,
    enterprise_id: str | None = None,
    status: str | None,
    query: str | None,
    offset: int,
    limit: int,
    source_key: str | None = None,
) -> SyncRunListResponse:
    enterprise_id = _resolve_enterprise_id(database, enterprise_id)
    conditions = [SyncRun.enterprise_id == enterprise_id, SyncRun.parent_run_id.is_(None)]
    if source_key:
        conditions.append(ExternalSystem.system_key == source_key)
    if status:
        conditions.append(SyncRun.status == status)
    if query:
        pattern = f"%{query.strip()}%"
        conditions.append(or_(SyncRun.id.ilike(pattern), ExternalSystem.name.ilike(pattern)))

    with database.session() as session:
        total = int(
            session.scalar(
                select(func.count(SyncRun.id))
                .select_from(SyncRun)
                .join(ExternalSystem, ExternalSystem.id == SyncRun.external_system_id)
                .where(*conditions)
            )
            or 0
        )
        rows = session.execute(
            select(SyncRun, ExternalSystem)
            .join(ExternalSystem, ExternalSystem.id == SyncRun.external_system_id)
            .where(*conditions)
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        status_rows = session.execute(
            select(SyncRun.status, func.count(SyncRun.id))
            .where(SyncRun.enterprise_id == enterprise_id)
            .group_by(SyncRun.status)
        ).all()

    return SyncRunListResponse(
        page=PageView(offset=offset, limit=limit, total=total),
        status_counts={str(key): int(count) for key, count in status_rows},
        items=[
            SyncRunListItem(
                id=run.id,
                source_key=source.system_key,
                source_name=source.name,
                source_version=run.source_version,
                status=run.status,
                scenario=run.scenario,
                volume_profile=run.volume_profile,
                records_read=run.records_read,
                records_written=run.records_written,
                warning=run.warning,
                error=run.error,
                started_at=run.started_at,
                finished_at=run.finished_at,
                duration_seconds=_duration_seconds(run.started_at, run.finished_at),
            )
            for run, source in rows
        ],
        generated_at=datetime.now(UTC),
    )


def list_business_entities(
    database: Database,
    *,
    enterprise_id: str | None = None,
    entity_type: str | None,
    status: str | None,
    query: str | None,
    offset: int,
    limit: int,
) -> BusinessEntityListResponse:
    enterprise_id = _resolve_enterprise_id(database, enterprise_id)
    conditions = [BusinessEntity.enterprise_id == enterprise_id]
    if entity_type:
        conditions.append(BusinessEntity.entity_type == entity_type)
    if status:
        conditions.append(BusinessEntity.status == status)
    if query:
        pattern = f"%{query.strip()}%"
        conditions.append(
            or_(
                BusinessEntity.canonical_key.ilike(pattern),
                BusinessEntity.display_name.ilike(pattern),
            )
        )

    with database.session() as session:
        total = int(session.scalar(select(func.count(BusinessEntity.id)).where(*conditions)) or 0)
        entities = list(
            session.scalars(
                select(BusinessEntity)
                .where(*conditions)
                .order_by(BusinessEntity.entity_type, BusinessEntity.display_name)
                .offset(offset)
                .limit(limit)
            )
        )
        type_rows = session.execute(
            select(BusinessEntity.entity_type, func.count(BusinessEntity.id))
            .where(BusinessEntity.enterprise_id == enterprise_id)
            .group_by(BusinessEntity.entity_type)
        ).all()

    return BusinessEntityListResponse(
        page=PageView(offset=offset, limit=limit, total=total),
        type_counts={str(key): int(count) for key, count in type_rows},
        items=[
            BusinessEntityView(
                id=item.id,
                entity_type=item.entity_type,
                canonical_key=item.canonical_key,
                display_name=item.display_name,
                status=item.status,
                attributes=item.attributes,
                attribute_count=len(item.attributes),
                updated_at=item.updated_at,
            )
            for item in entities
        ],
        generated_at=datetime.now(UTC),
    )


def list_metric_catalog(
    database: Database,
    *,
    enterprise_id: str | None = None,
    status: str | None,
    query: str | None,
    offset: int,
    limit: int,
) -> MetricCatalogResponse:
    enterprise_id = _resolve_enterprise_id(database, enterprise_id)
    conditions = [MetricDefinition.enterprise_id == enterprise_id]
    if status:
        conditions.append(MetricDefinition.status == status)
    if query:
        pattern = f"%{query.strip()}%"
        conditions.append(
            or_(
                MetricDefinition.metric_key.ilike(pattern),
                MetricDefinition.label.ilike(pattern),
                MetricDefinition.description.ilike(pattern),
            )
        )

    with database.session() as session:
        total = int(session.scalar(select(func.count(MetricDefinition.id)).where(*conditions)) or 0)
        definitions = list(
            session.scalars(
                select(MetricDefinition)
                .where(*conditions)
                .order_by(MetricDefinition.label, MetricDefinition.version.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        definition_keys = {item.metric_key for item in definitions}
        snapshots = (
            list(
                session.scalars(
                    select(MetricSnapshot)
                    .where(
                        MetricSnapshot.enterprise_id == enterprise_id,
                        MetricSnapshot.metric_key.in_(definition_keys),
                    )
                    .order_by(MetricSnapshot.as_of.desc(), MetricSnapshot.id.desc())
                )
            )
            if definition_keys
            else []
        )
        latest_by_key: dict[str, MetricSnapshot] = {}
        for snapshot in snapshots:
            latest_by_key.setdefault(snapshot.metric_key, snapshot)
        sources = {
            item.id: item.system_key
            for item in session.scalars(
                select(ExternalSystem).where(ExternalSystem.enterprise_id == enterprise_id)
            )
        }
        status_rows = session.execute(
            select(MetricDefinition.status, func.count(MetricDefinition.id))
            .where(MetricDefinition.enterprise_id == enterprise_id)
            .group_by(MetricDefinition.status)
        ).all()

    return MetricCatalogResponse(
        page=PageView(offset=offset, limit=limit, total=total),
        status_counts={str(key): int(count) for key, count in status_rows},
        items=[
            MetricCatalogView(
                id=item.id,
                key=item.metric_key,
                label=item.label,
                description=item.description,
                formula_expression=item.formula_expression,
                unit=item.unit,
                dimensions=item.dimensions,
                owner=item.owner,
                version=item.version,
                status=item.status,
                source_key=sources.get(item.source_system_id) if item.source_system_id else None,
                current_value=latest_by_key[item.metric_key].value
                if item.metric_key in latest_by_key
                else None,
                change_rate=latest_by_key[item.metric_key].change_rate
                if item.metric_key in latest_by_key
                else None,
                as_of=latest_by_key[item.metric_key].as_of
                if item.metric_key in latest_by_key
                else None,
                updated_at=item.updated_at,
            )
            for item in definitions
        ],
        generated_at=datetime.now(UTC),
    )


def query_metric_series(
    database: Database,
    *,
    metric_keys: list[str],
    scope_key: str,
    days: int,
    as_of: datetime | None = None,
    enterprise_id: str | None = None,
) -> MetricSeriesResponse:
    enterprise_id = _resolve_enterprise_id(database, enterprise_id)
    ordered_keys = list(dict.fromkeys(metric_keys))
    if not ordered_keys:
        return MetricSeriesResponse(
            scope_key=scope_key,
            date_from=None,
            date_to=None,
            series=[],
            generated_at=datetime.now(UTC),
        )

    with database.session() as session:
        definitions = list(
            session.scalars(
                select(MetricDefinition)
                .where(
                    MetricDefinition.enterprise_id == enterprise_id,
                    MetricDefinition.metric_key.in_(ordered_keys),
                    MetricDefinition.status.in_(("active", "published")),
                )
                .order_by(MetricDefinition.metric_key, MetricDefinition.version.desc())
            )
        )
        latest_definitions: dict[str, MetricDefinition] = {}
        for definition in definitions:
            latest_definitions.setdefault(definition.metric_key, definition)

        snapshot_conditions = (
            MetricSnapshot.enterprise_id == enterprise_id,
            MetricSnapshot.metric_key.in_(ordered_keys),
            MetricSnapshot.scope_key == scope_key,
        )
        date_to = as_of or session.scalar(
            select(func.max(MetricSnapshot.as_of)).where(*snapshot_conditions)
        )
        if date_to is None:
            snapshots: list[MetricSnapshot] = []
            date_from = None
        else:
            date_from = date_to.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
                days=days - 1
            )
            snapshots = list(
                session.scalars(
                    select(MetricSnapshot)
                    .where(
                        *snapshot_conditions,
                        MetricSnapshot.as_of >= date_from,
                        MetricSnapshot.as_of <= date_to,
                    )
                    .order_by(MetricSnapshot.as_of, MetricSnapshot.id)
                )
            )

    points_by_key: dict[str, dict[str, MetricSnapshot]] = {key: {} for key in ordered_keys}
    for snapshot in snapshots:
        day_key = snapshot.as_of.date().isoformat()
        current = points_by_key.setdefault(snapshot.metric_key, {}).get(day_key)
        if current is None or (snapshot.as_of, snapshot.id) >= (current.as_of, current.id):
            points_by_key[snapshot.metric_key][day_key] = snapshot

    series: list[MetricSeriesView] = []
    for key in ordered_keys:
        current_definition = latest_definitions.get(key)
        if current_definition is None:
            continue
        metric_points = sorted(
            points_by_key.get(key, {}).values(), key=lambda item: (item.as_of, item.id)
        )
        values = [item.value for item in metric_points]
        period_change_rate = None
        if len(values) > 1 and values[0] != 0:
            period_change_rate = values[-1] / values[0] - 1
        series.append(
            MetricSeriesView(
                key=key,
                label=current_definition.label,
                unit=current_definition.unit,
                scope_key=scope_key,
                definition_version=current_definition.version,
                latest_value=values[-1] if values else None,
                period_change_rate=period_change_rate,
                minimum=min(values) if values else None,
                maximum=max(values) if values else None,
                points=[
                    MetricSeriesPointView(
                        as_of=item.as_of,
                        value=item.value,
                        change_rate=item.change_rate,
                    )
                    for item in metric_points
                ],
            )
        )
    return MetricSeriesResponse(
        scope_key=scope_key,
        date_from=date_from,
        date_to=date_to,
        series=series,
        generated_at=datetime.now(UTC),
    )


def list_data_quality(
    database: Database,
    *,
    enterprise_id: str | None = None,
    category: str | None,
    status: str | None,
    query: str | None,
    offset: int,
    limit: int,
) -> DataQualityResponse:
    enterprise_id = _resolve_enterprise_id(database, enterprise_id)
    latest_result_id = (
        select(DataQualityResult.id)
        .where(DataQualityResult.rule_id == DataQualityRule.id)
        .order_by(DataQualityResult.checked_at.desc(), DataQualityResult.id.desc())
        .limit(1)
        .correlate(DataQualityRule)
        .scalar_subquery()
    )
    conditions = [DataQualityRule.enterprise_id == enterprise_id]
    if category:
        conditions.append(DataQualityRule.category == category)
    if status:
        conditions.append(
            DataQualityResult.id.is_(None)
            if status == "pending"
            else DataQualityResult.status == status
        )
    if query:
        pattern = f"%{query.strip()}%"
        conditions.append(
            or_(
                DataQualityRule.rule_key.ilike(pattern),
                DataQualityRule.name.ilike(pattern),
                DataQualityRule.asset_key.ilike(pattern),
            )
        )

    base = (
        select(DataQualityRule, DataQualityResult)
        .outerjoin(DataQualityResult, DataQualityResult.id == latest_result_id)
        .where(*conditions)
    )
    with database.session() as session:
        all_latest = session.execute(
            select(DataQualityRule, DataQualityResult)
            .outerjoin(DataQualityResult, DataQualityResult.id == latest_result_id)
            .where(DataQualityRule.enterprise_id == enterprise_id)
        ).all()
        total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        rows = session.execute(
            base.order_by(DataQualityRule.severity.desc(), DataQualityRule.name)
            .offset(offset)
            .limit(limit)
        ).all()

    result_counts: dict[str, int] = {}
    for _, result in all_latest:
        key = result.status if result is not None else "pending"
        result_counts[key] = result_counts.get(key, 0) + 1
    return DataQualityResponse(
        page=PageView(offset=offset, limit=limit, total=total),
        result_counts=result_counts,
        items=[
            DataQualityView(
                id=rule.id,
                key=rule.rule_key,
                name=rule.name,
                description=rule.description,
                category=rule.category,
                asset_type=rule.asset_type,
                asset_key=rule.asset_key,
                expectation=rule.expectation,
                severity=rule.severity,
                rule_status=rule.status,
                result_status=result.status if result is not None else "pending",
                observed_value=result.observed_value if result is not None else None,
                affected_records=result.affected_records if result is not None else 0,
                details=result.details if result is not None else {},
                sync_run_id=result.sync_run_id if result is not None else None,
                checked_at=result.checked_at if result is not None else None,
            )
            for rule, result in rows
        ],
        generated_at=datetime.now(UTC),
    )


def build_commerce_operations(
    database: Database,
    *,
    scope_key: str = "enterprise",
    enterprise_id: str | None = None,
) -> CommerceOperationsResponse:
    enterprise_id = _resolve_enterprise_id(database, enterprise_id)
    external_store_keys = resolve_commerce_scope_keys(
        database,
        scope_key=scope_key,
        enterprise_id=enterprise_id,
    )
    with database.session() as session:
        all_orders = list(
            session.scalars(
                select(CommerceOrderFact)
                .where(CommerceOrderFact.enterprise_id == enterprise_id)
                .order_by(CommerceOrderFact.paid_at.desc())
            )
        )
        all_refunds = list(
            session.scalars(
                select(CommerceRefundFact).where(
                    CommerceRefundFact.enterprise_id == enterprise_id
                )
            )
        )
        all_inventory = list(
            session.scalars(
                select(CommerceInventorySnapshotFact).where(
                    CommerceInventorySnapshotFact.enterprise_id == enterprise_id
                )
            )
        )
        all_advertising = list(
            session.scalars(
                select(CommerceAdPerformanceFact).where(
                    CommerceAdPerformanceFact.enterprise_id == enterprise_id
                )
            )
        )
        entities = list(
            session.scalars(
                select(BusinessEntity).where(
                    BusinessEntity.enterprise_id == enterprise_id,
                    BusinessEntity.entity_type == "store",
                )
            )
        )
        sources = {
            item.id: item
            for item in session.scalars(
                select(ExternalSystem).where(
                    ExternalSystem.enterprise_id == enterprise_id
                )
            )
        }

    if external_store_keys is not None:
        orders = [item for item in all_orders if item.store_key in external_store_keys]
        refunds = [item for item in all_refunds if item.store_key in external_store_keys]
        advertising = [item for item in all_advertising if item.store_key in external_store_keys]
        inventory: list[CommerceInventorySnapshotFact] = []
    else:
        orders = all_orders
        refunds = all_refunds
        advertising = all_advertising
        inventory = all_inventory
    order_keys = {item.order_key for item in orders}
    with database.session() as session:
        order_lines = (
            list(
                session.scalars(
                    select(CommerceOrderLineFact).where(
                        CommerceOrderLineFact.enterprise_id == enterprise_id,
                        CommerceOrderLineFact.order_key.in_(order_keys),
                    )
                )
            )
            if order_keys
            else []
        )

    paid_gmv_fen = sum(item.paid_amount_fen for item in orders)
    cost_fen = sum(item.cost_amount_fen for item in orders)
    refund_amount_fen = sum(item.refund_amount_fen for item in refunds)
    inventory_value_fen = sum(item.inventory_cost_fen for item in inventory)
    ad_spend_fen = sum(item.spend_fen for item in advertising)
    ad_revenue_fen = sum(item.attributed_revenue_fen for item in advertising)
    low_stock = [item for item in inventory if item.status == "low"]

    store_entities = {item.canonical_key: item for item in entities}
    store_keys = sorted(
        {
            *(item.store_key for item in orders),
            *(item.store_key for item in refunds),
            *(item.store_key for item in advertising),
        }
    )
    stores = [
        _commerce_store_view(
            store_key,
            store_entities.get(store_key),
            orders,
            refunds,
            advertising,
        )
        for store_key in store_keys
    ]
    stores.sort(key=lambda item: item.paid_gmv_yuan, reverse=True)

    active_orders = [item for item in orders if item.status != "cancelled"]
    shipped_orders = [
        item for item in active_orders if item.status in {"shipped", "completed", "refunding"}
    ]
    completed_orders = [item for item in active_orders if item.status == "completed"]
    funnel = [
        _funnel_step("paid", "已支付", active_orders, len(active_orders)),
        _funnel_step("shipped", "已发货", shipped_orders, len(active_orders)),
        _funnel_step("completed", "已完成", completed_orders, len(active_orders)),
        CommerceFunnelStepView(
            key="refunded",
            label="退款申请",
            count=len(refunds),
            amount_yuan=_yuan(refund_amount_fen),
            conversion_rate=_ratio(len(refunds), len(active_orders)),
        ),
    ]

    exceptions = _commerce_exceptions(
        orders,
        refunds,
        inventory,
        advertising,
        sources,
    )
    business_dates = [
        *(item.business_date for item in orders),
        *(item.business_date for item in advertising),
    ]
    recent_orders = [
        _commerce_order_view(item, store_entities.get(item.store_key), sources)
        for item in orders[:24]
    ]
    lineage = _commerce_lineage(
        orders,
        order_lines,
        refunds,
        inventory,
        advertising,
        sources,
    )
    return CommerceOperationsResponse(
        scope_key=scope_key,
        business_date_from=min(business_dates) if business_dates else None,
        business_date_to=max(business_dates) if business_dates else None,
        summary=CommerceOperationsSummary(
            order_count=len(orders),
            order_line_count=len(order_lines),
            paid_gmv_yuan=_yuan(paid_gmv_fen),
            gross_margin_rate=_ratio(paid_gmv_fen - cost_fen, paid_gmv_fen),
            refund_count=len(refunds),
            refund_amount_yuan=_yuan(refund_amount_fen),
            refund_rate=_ratio(refund_amount_fen, paid_gmv_fen),
            inventory_sku_count=len(inventory),
            inventory_value_yuan=_yuan(inventory_value_fen),
            low_stock_sku_count=len(low_stock),
            advertising_spend_yuan=_yuan(ad_spend_fen),
            attributed_revenue_yuan=_yuan(ad_revenue_fen),
            advertising_roi=_ratio(ad_revenue_fen, ad_spend_fen),
        ),
        funnel=funnel,
        stores=stores,
        exceptions=exceptions,
        recent_orders=recent_orders,
        lineage=lineage,
        generated_at=datetime.now(UTC),
    )


def resolve_commerce_scope_keys(
    database: Database,
    *,
    scope_key: str,
    enterprise_id: str,
) -> set[str] | None:
    if scope_key == "enterprise":
        return None
    with database.session() as session:
        mappings = list(
            session.scalars(
                select(DataScopeMapping).where(
                    DataScopeMapping.enterprise_id == enterprise_id,
                    DataScopeMapping.scope_type == "store",
                    DataScopeMapping.scope_key == scope_key,
                    DataScopeMapping.status == "active",
                )
            )
        )
    if not mappings:
        raise ApiProblem(
            status_code=409,
            code="commerce.scope_mapping_missing",
            message="目标数据范围尚未映射到来源系统业务键，请先同步来源目录",
            details={"scope_key": scope_key},
        )
    return {item.external_scope_key for item in mappings}


def _yuan(value_fen: int) -> float:
    return round(value_fen / 100, 2)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _funnel_step(
    key: str,
    label: str,
    orders: list[CommerceOrderFact],
    base_count: int,
) -> CommerceFunnelStepView:
    return CommerceFunnelStepView(
        key=key,
        label=label,
        count=len(orders),
        amount_yuan=_yuan(sum(item.paid_amount_fen for item in orders)),
        conversion_rate=_ratio(len(orders), base_count),
    )


def _commerce_store_view(
    store_key: str,
    entity: BusinessEntity | None,
    orders: list[CommerceOrderFact],
    refunds: list[CommerceRefundFact],
    advertising: list[CommerceAdPerformanceFact],
) -> CommerceStorePerformanceView:
    store_orders = [item for item in orders if item.store_key == store_key]
    store_refunds = [item for item in refunds if item.store_key == store_key]
    store_ads = [item for item in advertising if item.store_key == store_key]
    gmv = sum(item.paid_amount_fen for item in store_orders)
    cost = sum(item.cost_amount_fen for item in store_orders)
    refund_amount = sum(item.refund_amount_fen for item in store_refunds)
    spend = sum(item.spend_fen for item in store_ads)
    revenue = sum(item.attributed_revenue_fen for item in store_ads)
    channel = (
        str(entity.attributes.get("channel", "unknown"))
        if entity is not None
        else next((item.channel for item in store_orders), "unknown")
    )
    return CommerceStorePerformanceView(
        store_key=store_key,
        store_name=entity.display_name if entity is not None else store_key,
        channel=channel,
        order_count=len(store_orders),
        paid_gmv_yuan=_yuan(gmv),
        gross_margin_rate=_ratio(gmv - cost, gmv),
        refund_count=len(store_refunds),
        refund_rate=_ratio(refund_amount, gmv),
        advertising_spend_yuan=_yuan(spend),
        attributed_revenue_yuan=_yuan(revenue),
        advertising_roi=_ratio(revenue, spend),
    )


def _commerce_order_view(
    item: CommerceOrderFact,
    entity: BusinessEntity | None,
    sources: dict[str, ExternalSystem],
) -> CommerceOrderView:
    return CommerceOrderView(
        order_key=item.order_key,
        store_key=item.store_key,
        store_name=entity.display_name if entity is not None else item.store_key,
        customer_key=item.customer_key,
        channel=item.channel,
        status=item.status,
        business_date=item.business_date,
        paid_amount_yuan=_yuan(item.paid_amount_fen),
        gross_margin_yuan=_yuan(item.paid_amount_fen - item.cost_amount_fen),
        item_count=item.item_count,
        province=item.province,
        source_key=sources[item.external_system_id].system_key,
        sync_run_id=item.sync_run_id,
    )


def _commerce_exceptions(
    orders: list[CommerceOrderFact],
    refunds: list[CommerceRefundFact],
    inventory: list[CommerceInventorySnapshotFact],
    advertising: list[CommerceAdPerformanceFact],
    sources: dict[str, ExternalSystem],
) -> list[CommerceExceptionView]:
    result: list[CommerceExceptionView] = []
    for inventory_item in sorted(inventory, key=lambda row: row.days_cover):
        if inventory_item.status != "low":
            continue
        severity: Literal["warning", "critical"] = (
            "critical"
            if inventory_item.available_quantity <= inventory_item.safety_quantity * 0.5
            else "warning"
        )
        result.append(
            CommerceExceptionView(
                key=f"inventory:{inventory_item.snapshot_key}",
                exception_type="inventory",
                severity=severity,
                title=f"{inventory_item.sku_key} 库存低于安全线",
                detail=(
                    f"{inventory_item.warehouse_key} 可售 {inventory_item.available_quantity}，"
                    f"安全库存 {inventory_item.safety_quantity}，"
                    f"在途 {inventory_item.in_transit_quantity}。"
                ),
                value=inventory_item.days_cover,
                unit="天覆盖",
                related_keys=[
                    inventory_item.sku_key,
                    inventory_item.product_key,
                    inventory_item.warehouse_key,
                ],
                source_key=sources[inventory_item.external_system_id].system_key,
                sync_run_id=inventory_item.sync_run_id,
            )
        )

    refund_groups: dict[str, list[CommerceRefundFact]] = defaultdict(list)
    for refund_item in refunds:
        refund_groups[refund_item.sku_key].append(refund_item)
    for sku_key, refund_rows in refund_groups.items():
        amount = sum(row.refund_amount_fen for row in refund_rows)
        if len(refund_rows) < 2:
            continue
        first_refund = refund_rows[0]
        result.append(
            CommerceExceptionView(
                key=f"refund:{sku_key}",
                exception_type="refund",
                severity="critical" if len(refund_rows) >= 4 else "warning",
                title=f"{sku_key} 出现集中退款",
                detail=f"{len(refund_rows)} 笔退款，合计 {_yuan(amount):,.2f} 元。",
                value=_yuan(amount),
                unit="元",
                related_keys=[
                    sku_key,
                    *sorted({row.order_key for row in refund_rows})[:3],
                ],
                source_key=sources[first_refund.external_system_id].system_key,
                sync_run_id=first_refund.sync_run_id,
            )
        )

    campaign_groups: dict[str, list[CommerceAdPerformanceFact]] = defaultdict(list)
    for ad_item in advertising:
        campaign_groups[ad_item.campaign_key].append(ad_item)
    for campaign_key, ad_rows in campaign_groups.items():
        spend = sum(row.spend_fen for row in ad_rows)
        revenue = sum(row.attributed_revenue_fen for row in ad_rows)
        roi = _ratio(revenue, spend)
        if roi >= 2.5:
            continue
        first_ad = ad_rows[0]
        result.append(
            CommerceExceptionView(
                key=f"advertising:{campaign_key}",
                exception_type="advertising",
                severity="critical" if roi < 2 else "warning",
                title=f"{campaign_key} 投放回报偏低",
                detail=f"近 {len(ad_rows)} 个日绩效记录，消耗 {_yuan(spend):,.2f} 元。",
                value=roi,
                unit="ROI",
                related_keys=[campaign_key, first_ad.store_key, first_ad.product_key],
                source_key=sources[first_ad.external_system_id].system_key,
                sync_run_id=first_ad.sync_run_id,
            )
        )

    for order_item in orders:
        margin = order_item.paid_amount_fen - order_item.cost_amount_fen
        if margin >= 0:
            continue
        result.append(
            CommerceExceptionView(
                key=f"margin:{order_item.order_key}",
                exception_type="margin",
                severity="critical",
                title=f"{order_item.order_key} 订单毛利为负",
                detail=(
                    f"实付 {_yuan(order_item.paid_amount_fen):,.2f} 元，"
                    f"成本 {_yuan(order_item.cost_amount_fen):,.2f} 元。"
                ),
                value=_yuan(margin),
                unit="元",
                related_keys=[
                    order_item.order_key,
                    order_item.store_key,
                    order_item.customer_key,
                ],
                source_key=sources[order_item.external_system_id].system_key,
                sync_run_id=order_item.sync_run_id,
            )
        )
    result.sort(key=lambda item: (item.severity != "critical", item.exception_type, item.value))
    return result[:30]


def _commerce_lineage(
    orders: list[CommerceOrderFact],
    order_lines: list[CommerceOrderLineFact],
    refunds: list[CommerceRefundFact],
    inventory: list[CommerceInventorySnapshotFact],
    advertising: list[CommerceAdPerformanceFact],
    sources: dict[str, ExternalSystem],
) -> list[CommerceLineageAssetView]:
    assets: list[tuple[str, str, str, list[object]]] = [
        ("orders", "订单事实", "commerce_order_facts", list(orders)),
        ("order-lines", "订单行事实", "commerce_order_line_facts", list(order_lines)),
        ("refunds", "退款事实", "commerce_refund_facts", list(refunds)),
        (
            "inventory",
            "库存快照事实",
            "commerce_inventory_snapshot_facts",
            list(inventory),
        ),
        (
            "advertising",
            "广告日绩效事实",
            "commerce_ad_performance_facts",
            list(advertising),
        ),
    ]
    result: list[CommerceLineageAssetView] = []
    for key, label, table_name, rows in assets:
        first = rows[0] if rows else None
        source_id = str(getattr(first, "external_system_id", "")) if first else ""
        source = sources.get(source_id)
        result.append(
            CommerceLineageAssetView(
                key=key,
                label=label,
                table_name=table_name,
                record_count=len(rows),
                source_key=source.system_key if source is not None else "not-synced",
                source_schema_version=(
                    source.source_schema_version if source is not None else "unknown"
                ),
                mapping_version=source.mapping_version if source is not None else "unknown",
                latest_sync_run_id=(
                    str(getattr(first, "sync_run_id", "")) if first is not None else None
                ),
            )
        )
    return result


def _vector3(values: list[float]) -> tuple[float, float, float]:
    return cast(tuple[float, float, float], tuple(float(value) for value in values))


def _meeting_view(
    meeting: TwinMeeting,
    participants: list[TwinMeetingParticipant],
    seats: list[TwinMeetingSeat],
) -> TwinMeetingView:
    return TwinMeetingView(
        key=meeting.meeting_key,
        title=meeting.title,
        topic=meeting.topic,
        status=meeting.status,
        evidence_snapshot=meeting.evidence_snapshot,
        decision=meeting.decision,
        room_space_key=meeting.room_space_key,
        next_transition_at=meeting.next_transition_at,
        updated_at=meeting.updated_at,
        participants=[
            TwinMeetingParticipantView(
                actor_key=item.actor_key,
                seat_key=item.seat_key,
                position=item.position,
                finding=item.finding,
                status=item.status,
                speaking_order=item.speaking_order,
            )
            for item in participants
        ],
        seats=[
            TwinMeetingSeatView(
                key=item.seat_key,
                label=item.label,
                layout_key=item.layout_key,
                position=_vector3(item.position),
                rotation_y=item.rotation_y,
                status=item.status,
            )
            for item in seats
        ],
    )


def _interaction_view(profile: TwinInteractionProfile) -> TwinInteractionView:
    return TwinInteractionView.model_validate(
        {
            "entity_key": profile.entity_key,
            "entity_type": profile.entity_type,
            "detail_route": profile.detail_route,
            "enter_space_key": profile.enter_space_key,
            "actions": [TwinObjectActionView.model_validate(item) for item in profile.actions],
        }
    )


def _scene_view(scene: TwinScene) -> TwinSceneView:
    return TwinSceneView(
        key=scene.scene_key,
        name=scene.name,
        version=scene.version,
        status=scene.status,
        description=scene.description,
        parent_scene_key=scene.parent_scene_key,
        scene_level=scene.scene_level,
        entry_space_key=scene.entry_space_key,
        asset_bundle_key=scene.asset_bundle_key,
        camera_preset=scene.camera_preset,
        updated_at=scene.updated_at,
    )


def _hotspot_details(hotspot: TwinHotspot, meeting: TwinMeeting | None) -> dict[str, object]:
    if hotspot.hotspot_key != "meeting-decision-package":
        return hotspot.details
    if meeting is None or meeting.status != "decision_ready":
        return {"state": "等待会议生成"}
    return {"state": "已生成", "decision": meeting.decision}


def build_overview(
    database: Database,
    *,
    enterprise_id: str | None = None,
) -> TwinOverviewResponse:
    enterprise_id = _resolve_enterprise_id(database, enterprise_id)
    with database.session() as session:
        enterprise = session.get(Enterprise, enterprise_id)
        if enterprise is None:
            raise RuntimeError("enterprise seed is missing")
        sources = list(
            session.scalars(
                select(ExternalSystem)
                .where(ExternalSystem.enterprise_id == enterprise_id)
                .order_by(ExternalSystem.name)
            )
        )
        source_record_counts = {
            str(source_id): int(count)
            for source_id, count in session.execute(
                select(SourceRecord.external_system_id, func.count(SourceRecord.id))
                .where(SourceRecord.enterprise_id == enterprise_id)
                .group_by(SourceRecord.external_system_id)
            )
        }
        for source_id, count in session.execute(
            select(SyncRun.external_system_id, func.sum(RawPageManifest.row_count))
            .select_from(RawPageManifest)
            .join(SyncResourceRun, SyncResourceRun.id == RawPageManifest.sync_resource_run_id)
            .join(SyncRun, SyncRun.id == SyncResourceRun.sync_run_id)
            .where(SyncRun.enterprise_id == enterprise_id, SyncRun.scenario != "raw_replay")
            .group_by(SyncRun.external_system_id)
        ):
            key = str(source_id)
            source_record_counts[key] = source_record_counts.get(key, 0) + int(count or 0)
        source_run_counts = {
            str(source_id): int(count)
            for source_id, count in session.execute(
                select(SyncRun.external_system_id, func.count(SyncRun.id))
                .where(SyncRun.enterprise_id == enterprise_id, SyncRun.parent_run_id.is_(None),
                       SyncRun.scenario != "raw_replay")
                .group_by(SyncRun.external_system_id)
            )
        }
        nodes = list(
            session.scalars(
                select(TwinNode)
                .where(TwinNode.enterprise_id == enterprise_id)
                .order_by(TwinNode.id)
            )
        )
        edges = list(
            session.scalars(
                select(TwinEdge)
                .where(TwinEdge.enterprise_id == enterprise_id)
                .order_by(TwinEdge.id)
            )
        )
        snapshots = list(
            session.scalars(
                select(MetricSnapshot)
                .where(MetricSnapshot.enterprise_id == enterprise_id)
                .order_by(MetricSnapshot.as_of.desc(), MetricSnapshot.id.desc())
            )
        )
        latest_by_key: dict[str, MetricSnapshot] = {}
        for snapshot in snapshots:
            latest_by_key.setdefault(snapshot.metric_key, snapshot)
        events = list(
            session.scalars(
                select(PlatformEvent)
                .where(PlatformEvent.enterprise_id == enterprise_id)
                .order_by(PlatformEvent.occurred_at.desc())
                .limit(8)
            )
        )
        latest_sync = session.scalar(
            select(SyncRun)
            .where(SyncRun.enterprise_id == enterprise_id, SyncRun.parent_run_id.is_(None),
                   SyncRun.scenario != "raw_replay")
            .order_by(SyncRun.started_at.desc())
            .limit(1)
        )
        entity_count = int(
            session.scalar(
                select(func.count(BusinessEntity.id)).where(
                    BusinessEntity.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        record_count = sum(source_record_counts.values())
        commerce_fact_count = sum(
            int(
                session.scalar(
                    select(func.count(model.id)).where(model.enterprise_id == enterprise_id)
                )
                or 0
            )
            for model in (
                CommerceOrderFact,
                CommerceOrderLineFact,
                CommerceRefundFact,
                CommerceInventorySnapshotFact,
                CommerceAdPerformanceFact,
            )
        )
        customer_profile_count = int(
            session.scalar(
                select(func.count(CustomerProfile.id)).where(
                    CustomerProfile.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        customer_touchpoint_count = int(
            session.scalar(
                select(func.count(CustomerTouchpointFact.id)).where(
                    CustomerTouchpointFact.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        metric_definition_count = int(
            session.scalar(
                select(func.count(MetricDefinition.id)).where(
                    MetricDefinition.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        knowledge_document_count = int(
            session.scalar(
                select(func.count(KnowledgeDocument.id)).where(
                    KnowledgeDocument.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        knowledge_version_count = int(
            session.scalar(
                select(func.count(KnowledgeVersion.id))
                .join(KnowledgeDocument, KnowledgeVersion.document_id == KnowledgeDocument.id)
                .where(KnowledgeDocument.enterprise_id == enterprise_id)
            )
            or 0
        )
        knowledge_chunk_count = int(
            session.scalar(
                select(func.count(KnowledgeChunk.id))
                .join(KnowledgeVersion, KnowledgeChunk.version_id == KnowledgeVersion.id)
                .join(KnowledgeDocument, KnowledgeVersion.document_id == KnowledgeDocument.id)
                .where(KnowledgeDocument.enterprise_id == enterprise_id)
            )
            or 0
        )
        role_twin_profile_count = int(
            session.scalar(
                select(func.count(RoleTwinProfile.id)).where(
                    RoleTwinProfile.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        agent_run_count = int(
            session.scalar(
                select(func.count(AgentRun.id)).where(AgentRun.enterprise_id == enterprise_id)
            )
            or 0
        )
        customer_operation_run_count = int(
            session.scalar(
                select(func.count(CustomerOperationRun.id)).where(
                    CustomerOperationRun.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        tool_definition_count = int(
            session.scalar(
                select(func.count(ToolDefinition.id)).where(
                    ToolDefinition.enterprise_id == enterprise_id,
                    ToolDefinition.status == "active",
                )
            )
            or 0
        )
        tool_invocation_count = int(
            session.scalar(
                select(func.count(ToolInvocation.id)).where(
                    ToolInvocation.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        scenes = list(
            session.scalars(
                select(TwinScene)
                .where(TwinScene.enterprise_id == enterprise_id)
                .order_by(TwinScene.scene_level, TwinScene.scene_key)
            )
        )
        scene = next((item for item in scenes if item.parent_scene_key is None), None)
        scene_id = scene.id if scene else None
        meeting = session.scalar(
            select(TwinMeeting).where(
                TwinMeeting.enterprise_id == enterprise_id,
            ).order_by(TwinMeeting.updated_at.desc(), TwinMeeting.id).limit(1)
        )
        spaces = list(
            session.scalars(
                select(TwinSpace)
                .where(TwinSpace.scene_id == scene_id)
                .order_by(TwinSpace.sort_order)
            )
        )
        actors = list(
            session.scalars(
                select(TwinActor)
                .where(TwinActor.enterprise_id == enterprise_id)
                .order_by(TwinActor.sort_order)
            )
        )
        routes = list(
            session.scalars(
                select(TwinRoute).where(TwinRoute.scene_id == scene_id).order_by(TwinRoute.id)
            )
        )
        scene_keys_by_id = {item.id: item.scene_key for item in scenes}
        scene_ids = list(scene_keys_by_id)
        hotspots = list(
            session.scalars(
                select(TwinHotspot)
                .where(TwinHotspot.scene_id.in_(scene_ids))
                .order_by(TwinHotspot.scene_id, TwinHotspot.sort_order)
            )
        )
        data_layers = list(
            session.scalars(
                select(TwinDataLayer)
                .where(TwinDataLayer.scene_id.in_(scene_ids))
                .order_by(TwinDataLayer.scene_id, TwinDataLayer.sort_order)
            )
        )
        participants = list(
            session.scalars(
                select(TwinMeetingParticipant)
                .where(TwinMeetingParticipant.meeting_id == (meeting.id if meeting else None))
                .order_by(TwinMeetingParticipant.speaking_order)
            )
        )
        seats = list(
            session.scalars(
                select(TwinMeetingSeat)
                .where(TwinMeetingSeat.scene_id == (meeting.scene_id if meeting else None))
                .order_by(TwinMeetingSeat.sort_order)
            )
        )
        interactions = list(
            session.scalars(
                select(TwinInteractionProfile)
                .where(TwinInteractionProfile.enterprise_id == enterprise_id)
                .order_by(TwinInteractionProfile.sort_order)
            )
        )

    return TwinOverviewResponse(
        enterprise=EnterpriseView(
            id=enterprise.id,
            code=enterprise.code,
            name=enterprise.name,
            timezone=enterprise.timezone,
        ),
        database=DatabaseView(
            engine=database.engine_name,
            persistent=database.url != "sqlite+pysqlite:///:memory:",
            schema_revision=database.revision(),
        ),
        sources=[
            DataSourceView(
                key=item.system_key,
                name=item.name,
                system_type=item.system_type,
                status=item.status,
                connection_status=item.connection_status,
                source_schema_version=item.source_schema_version,
                mapping_version=item.mapping_version,
                last_sync_at=item.last_sync_at,
                source_record_count=source_record_counts.get(item.id, 0),
                sync_run_count=source_run_counts.get(item.id, 0),
            )
            for item in sources
        ],
        metrics=[
            MetricView(
                key=item.metric_key,
                label=item.label,
                value=item.value,
                unit=item.unit,
                change_rate=item.change_rate,
                as_of=item.as_of,
            )
            for item in latest_by_key.values()
        ],
        nodes=[
            TwinNodeView(
                key=item.node_key,
                label=item.label,
                node_type=item.node_type,
                status=item.status,
                health=item.health,
                position=(item.position_x, item.position_y, item.position_z),
                description=item.description,
            )
            for item in nodes
        ],
        edges=[
            TwinEdgeView(
                key=item.edge_key,
                source=item.source_key,
                target=item.target_key,
                flow_type=item.flow_type,
                status=item.status,
                traffic=item.traffic,
            )
            for item in edges
        ],
        events=[
            EventView(
                id=item.id,
                event_type=item.event_type,
                severity=item.severity,
                title=item.title,
                detail=item.detail,
                occurred_at=item.occurred_at,
            )
            for item in events
        ],
        scene=_scene_view(scene) if scene else None,
        scenes=[_scene_view(item) for item in scenes],
        spaces=[
            TwinSpaceView(
                key=item.space_key,
                label=item.label,
                space_type=item.space_type,
                parent_space_key=item.parent_space_key,
                status=item.status,
                health=item.health,
                alert_level=item.alert_level,
                metric_key=item.metric_key,
                position=_vector3(item.position),
                size=_vector3(item.size),
                description=item.description,
            )
            for item in spaces
        ],
        actors=[
            TwinActorView(
                key=item.actor_key,
                display_name=item.display_name,
                role_title=item.role_title,
                status=item.status,
                home_space_key=item.home_space_key,
                current_space_key=item.current_space_key,
                avatar_style=item.avatar_style,
                color=item.color,
                position=_vector3(item.position),
                capabilities=list(item.capabilities),
            )
            for item in actors
        ],
        routes=[
            TwinRouteView(
                key=item.route_key,
                source_space_key=item.source_space_key,
                target_space_key=item.target_space_key,
                route_type=item.route_type,
                path=[_vector3(point) for point in item.path],
            )
            for item in routes
        ],
        hotspots=[
            TwinHotspotView(
                key=item.hotspot_key,
                scene_key=scene_keys_by_id[item.scene_id],
                label=item.label,
                hotspot_type=item.hotspot_type,
                status=item.status,
                severity=item.severity,
                business_ref=item.business_ref,
                metric_key=item.metric_key,
                position=_vector3(item.position),
                details=_hotspot_details(item, meeting),
            )
            for item in hotspots
        ],
        data_layers=[
            TwinDataLayerView(
                key=item.layer_key,
                scene_key=scene_keys_by_id[item.scene_id],
                label=item.label,
                category=item.category,
                enabled_default=item.enabled_default,
                style=item.style,
            )
            for item in data_layers
        ],
        interactions=[_interaction_view(item) for item in interactions],
        meeting=_meeting_view(meeting, participants, seats) if meeting else None,
        latest_sync=_run_view(latest_sync, source_key=next(
            (source.system_key for source in sources
             if source.id == latest_sync.external_system_id), None)
        ) if latest_sync is not None else None,
        entity_count=entity_count,
        source_record_count=record_count,
        commerce_fact_count=commerce_fact_count,
        customer_profile_count=customer_profile_count,
        customer_touchpoint_count=customer_touchpoint_count,
        metric_definition_count=metric_definition_count,
        knowledge_document_count=knowledge_document_count,
        knowledge_version_count=knowledge_version_count,
        knowledge_chunk_count=knowledge_chunk_count,
        role_twin_profile_count=role_twin_profile_count,
        agent_run_count=agent_run_count,
        customer_operation_run_count=customer_operation_run_count,
        tool_definition_count=tool_definition_count,
        tool_invocation_count=tool_invocation_count,
        generated_at=datetime.now(UTC),
    )


def _apply_meeting_transition(
    session: Session,
    meeting: TwinMeeting,
    action: str,
    now: datetime,
    auto_start_seconds: float,
) -> list[TwinMeetingParticipant]:
    target_by_action = {
        "convene": "convening",
        "start": "in_session",
        "decide": "decision_ready",
        "reset": "scheduled",
    }
    allowed = {
        "scheduled": "convene",
        "convening": "start",
        "in_session": "decide",
        "decision_ready": "reset",
    }
    target = target_by_action.get(action)
    if target is None:
        raise ValueError(f"unknown meeting action: {action}")

    if meeting.status != target and allowed.get(meeting.status) != action:
        raise ValueError(f"cannot {action} meeting from {meeting.status}")
    participants = list(
        session.scalars(
            select(TwinMeetingParticipant)
            .where(TwinMeetingParticipant.meeting_id == meeting.id)
            .order_by(TwinMeetingParticipant.speaking_order)
        )
    )
    actors = {
        item.actor_key: item
        for item in session.scalars(
            select(TwinActor).where(TwinActor.enterprise_id == meeting.enterprise_id)
        )
    }
    meeting.status = target
    meeting.next_transition_at = (
        now + timedelta(seconds=auto_start_seconds) if action == "convene" else None
    )
    meeting.updated_at = now
    for participant in participants:
        actor = actors.get(participant.actor_key)
        if action == "convene":
            participant.status = "traveling"
            if actor is not None:
                actor.status = "in_transit"
        elif action == "start":
            participant.status = "present"
            if actor is not None:
                actor.status = "in_meeting"
                actor.current_space_key = meeting.room_space_key
        elif action == "decide":
            participant.status = "completed"
            if actor is not None:
                actor.status = "available"
        else:
            participant.status = "invited"
            if actor is not None:
                actor.status = "available"
                actor.current_space_key = actor.home_space_key

    event_copy = {
        "convene": ("meeting.convening", "info", "数字分身正在前往会议室"),
        "start": ("meeting.started", "success", "数字经营会议已开始"),
        "decide": ("meeting.decision-ready", "success", "数字会议已形成决策包"),
        "reset": ("meeting.reset", "info", "数字会议体验已复位"),
    }[action]
    _append_event(
        session,
        meeting.enterprise_id,
        event_copy[0],
        event_copy[1],
        event_copy[2],
        meeting.title,
    )
    return participants


def advance_meeting(
    database: Database,
    meeting_key: str,
    action: str,
    auto_start_seconds: float = 4.8,
    enterprise_id: str | None = None,
) -> TwinMeetingView:
    resolved_enterprise_id = _resolve_enterprise_id(database, enterprise_id)
    with database.session() as session:
        meeting = session.scalar(
            select(TwinMeeting).where(
                TwinMeeting.enterprise_id == resolved_enterprise_id,
                TwinMeeting.meeting_key == meeting_key,
            )
        )
        if meeting is None:
            raise LookupError(f"meeting not found: {meeting_key}")
        participants = _apply_meeting_transition(
            session,
            meeting,
            action,
            datetime.now(UTC),
            auto_start_seconds,
        )
        seats = list(
            session.scalars(
                select(TwinMeetingSeat)
                .where(TwinMeetingSeat.scene_id == meeting.scene_id)
                .order_by(TwinMeetingSeat.sort_order)
            )
        )
        session.commit()
        return _meeting_view(meeting, participants, seats)


def reconcile_due_meetings(database: Database, now: datetime | None = None) -> int:
    current_time = now or datetime.now(UTC)
    with database.session() as session:
        due_meetings = list(
            session.scalars(
                select(TwinMeeting)
                .where(
                    TwinMeeting.status == "convening",
                    TwinMeeting.next_transition_at.is_not(None),
                    TwinMeeting.next_transition_at <= current_time,
                )
                .with_for_update(skip_locked=True)
            )
        )
        for meeting in due_meetings:
            _apply_meeting_transition(session, meeting, "start", current_time, 0)
        if due_meetings:
            session.commit()
        return len(due_meetings)


async def synchronize(
    database: Database,
    settings: Settings,
    scenario: str,
    volume_profile: str = "standard",
    source_key: str = "jky-erp-oms",
    enterprise_id: str | None = None,
    execute: bool = True,
    idempotency_key: str | None = None,
    request_id: str | None = None,
    scope_snapshot: dict[str, object] | None = None,
) -> SyncRun:
    now = datetime.now(UTC)
    resolved_source_key = SOURCE_KEY_ALIASES.get(source_key, source_key)
    resolved_enterprise_id = _resolve_enterprise_id(database, enterprise_id)
    with database.session() as session:
        if idempotency_key:
            existing_run = session.scalar(
                select(SyncRun).where(
                    SyncRun.enterprise_id == resolved_enterprise_id,
                    SyncRun.idempotency_key == idempotency_key,
                )
            )
            if existing_run is not None:
                return existing_run
        source = session.scalar(
            select(ExternalSystem).where(
                ExternalSystem.enterprise_id == resolved_enterprise_id,
                ExternalSystem.system_key == resolved_source_key,
            )
        )
        if source is None:
            raise LookupError(f"unknown data source: {source_key}")
        source_id = source.id
        source_name = source.name
        source_type = source.system_type
        source_base_url = source.base_url or settings.mock_commerce_url

    if execute and source_type == "lingxing":
        # Real Lingxing traffic is Worker-owned. Keeping this guard at the
        # domain boundary prevents legacy callers from issuing external I/O
        # inside an API request lifecycle.
        raise RuntimeError("lingxing synchronization must be queued for Worker execution")

    run = SyncRun(
        id=_id("sync"),
        enterprise_id=resolved_enterprise_id,
        external_system_id=source_id,
        status="running" if execute else "queued",
        scenario=scenario,
        volume_profile=volume_profile,
        records_read=0,
        records_written=0,
        started_at=now,
        idempotency_key=idempotency_key,
        request_id=request_id,
        scope_snapshot=scope_snapshot or {"enterprise_id": resolved_enterprise_id},
        selected_enterprise_ids=(scope_snapshot or {}).get("selected_enterprise_ids"),
        business_unit_ids=(scope_snapshot or {}).get("business_unit_ids"),
        store_ids=(scope_snapshot or {}).get("store_ids"),
        warehouse_ids=(scope_snapshot or {}).get("warehouse_ids"),
    )
    with database.session() as session:
        session.add(run)
        session.commit()

    if not execute:
        return run

    connector = create_connector(source_type, source_base_url)
    try:
        batch = await connector.fetch(scenario, volume_profile)
    except ConnectorError as exc:
        with database.session() as session:
            failed_run = session.get(SyncRun, run.id)
            if failed_run is None:
                raise RuntimeError("sync run disappeared") from exc
            failed_run.status = "failed"
            failed_run.error = str(exc)
            failed_run.finished_at = datetime.now(UTC)
            failed_source = session.get(ExternalSystem, source_id)
            if failed_source is not None:
                failed_source.status = "failed"
            _append_event(
                session,
                failed_run.enterprise_id,
                "integration.failed",
                "critical",
                f"{source_name}同步失败",
                f"来源 {resolved_source_key}：{exc}",
            )
            _record_quality_results(session, failed_run, None)
            _set_pipeline_state(session, failed_run.enterprise_id, "failed", 0.28)
            session.commit()
            return failed_run

    with database.session() as session:
        persisted_run = session.get(SyncRun, run.id)
        source = session.get(ExternalSystem, source_id)
        if persisted_run is None or source is None:
            raise RuntimeError("sync configuration disappeared")
        written = _persist_batch(session, persisted_run, batch)
        finished_at = datetime.now(UTC)
        persisted_run.status = "partial" if batch.warnings else "succeeded"
        persisted_run.records_read = len(batch.records)
        persisted_run.records_written = written
        persisted_run.warning = " | ".join(batch.warnings) or None
        persisted_run.finished_at = finished_at
        source.status = "degraded" if batch.warnings else "connected"
        source.source_schema_version = batch.source_schema_version
        source.mapping_version = batch.mapping_version
        source.last_sync_at = finished_at
        _record_quality_results(session, persisted_run, batch)
        _set_pipeline_state(
            session,
            persisted_run.enterprise_id,
            persisted_run.status,
            0.68 if batch.warnings else 0.97,
        )
        _append_event(
            session,
            persisted_run.enterprise_id,
            "integration.partial" if batch.warnings else "integration.succeeded",
            "warning" if batch.warnings else "success",
            f"{source_name}部分同步" if batch.warnings else f"{source_name}已同步",
            (
                f"来源 {resolved_source_key} 读取 {len(batch.records)} 条原始记录，"
                f"写入 {written} 个标准化对象。"
            ),
        )
        session.commit()
        return persisted_run


def _persist_batch(session: Session, run: SyncRun, batch: ConnectorBatch) -> int:
    now = datetime.now(UTC)
    enterprise_id = run.enterprise_id
    written = 0
    existing_record_keys = {
        (item.record_type, item.external_id, item.content_hash)
        for item in session.scalars(
            select(SourceRecord).where(SourceRecord.external_system_id == run.external_system_id)
        )
    }
    for record in batch.records:
        serialized = json.dumps(record.payload, ensure_ascii=False, sort_keys=True)
        content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        record_key = (record.record_type, record.external_id, content_hash)
        if record_key in existing_record_keys:
            continue
        session.add(
            SourceRecord(
                id=_id("raw"),
                enterprise_id=enterprise_id,
                external_system_id=run.external_system_id,
                sync_run_id=run.id,
                record_type=record.record_type,
                external_id=record.external_id,
                source_schema_version=batch.source_schema_version,
                mapping_version=batch.mapping_version,
                content_hash=content_hash,
                payload=record.payload,
                observed_at=record.observed_at,
                ingested_at=now,
            )
        )
        existing_record_keys.add(record_key)
        written += 1

    entities_by_identity = {
        (item.entity_type, item.canonical_key): item
        for item in session.scalars(
            select(BusinessEntity).where(BusinessEntity.enterprise_id == enterprise_id)
        )
    }
    for entity in batch.entities:
        entity_identity = (entity.entity_type, entity.canonical_key)
        current = entities_by_identity.get(entity_identity)
        if current is None:
            current = BusinessEntity(
                id=_id("entity"),
                enterprise_id=enterprise_id,
                entity_type=entity.entity_type,
                canonical_key=entity.canonical_key,
                display_name=entity.display_name,
                status=entity.status,
                attributes=entity.attributes,
                updated_at=now,
            )
            session.add(current)
            entities_by_identity[entity_identity] = current
        else:
            current.display_name = entity.display_name
            current.status = entity.status
            current.attributes = entity.attributes
            current.updated_at = now
        written += 1

    metric_keys = {metric.key for metric in batch.metrics}
    metric_scopes = {metric.scope_key for metric in batch.metrics}
    existing_metrics = (
        list(
            session.scalars(
                select(MetricSnapshot).where(
                    MetricSnapshot.enterprise_id == enterprise_id,
                    MetricSnapshot.source_system_id == run.external_system_id,
                    MetricSnapshot.metric_key.in_(metric_keys),
                    MetricSnapshot.scope_key.in_(metric_scopes),
                )
            )
        )
        if metric_keys and metric_scopes
        else []
    )

    def metric_identity(
        metric_key: str, scope_key: str, as_of: datetime
    ) -> tuple[str, str, datetime]:
        normalized = (
            as_of.astimezone(UTC).replace(tzinfo=None) if as_of.tzinfo is not None else as_of
        )
        return metric_key, scope_key, normalized

    metrics_by_identity = {
        metric_identity(item.metric_key, item.scope_key, item.as_of): item
        for item in existing_metrics
    }
    for metric in batch.metrics:
        identity = metric_identity(metric.key, metric.scope_key, metric.as_of)
        snapshot = metrics_by_identity.get(identity)
        if snapshot is None:
            snapshot = MetricSnapshot(
                id=_id("metric"),
                enterprise_id=enterprise_id,
                source_system_id=run.external_system_id,
                sync_run_id=run.id,
                metric_key=metric.key,
                label=metric.label,
                scope_key=metric.scope_key,
                value=metric.value,
                unit=metric.unit,
                change_rate=metric.change_rate,
                as_of=metric.as_of,
            )
            session.add(snapshot)
            metrics_by_identity[identity] = snapshot
        else:
            snapshot.sync_run_id = run.id
            snapshot.label = metric.label
            snapshot.value = metric.value
            snapshot.unit = metric.unit
            snapshot.change_rate = metric.change_rate
        written += 1
    written += _persist_scope_mappings(session, run, batch, now)
    written += _persist_commerce_facts(session, run, batch, now)
    written += _persist_customer_facts(session, run, batch, now)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise
    return written


def _persist_scope_mappings(
    session: Session,
    run: SyncRun,
    batch: ConnectorBatch,
    now: datetime,
) -> int:
    enterprise_id = run.enterprise_id
    existing = {
        (item.scope_type, item.external_scope_key): item
        for item in session.scalars(
            select(DataScopeMapping).where(
                DataScopeMapping.enterprise_id == enterprise_id,
                DataScopeMapping.external_system_id == run.external_system_id,
            )
        )
    }
    for mapping_input in batch.scope_mappings:
        identity = (mapping_input.scope_type, mapping_input.external_scope_key)
        current = existing.get(identity)
        if current is None:
            current = DataScopeMapping(
                id=_id("scope_mapping"),
                enterprise_id=enterprise_id,
                external_system_id=run.external_system_id,
                sync_run_id=run.id,
                scope_type=mapping_input.scope_type,
                scope_key=mapping_input.scope_key,
                external_scope_key=mapping_input.external_scope_key,
                label=mapping_input.label,
                status=mapping_input.status,
                attributes=mapping_input.attributes,
                source_schema_version=batch.source_schema_version,
                mapping_version=batch.mapping_version,
                created_at=now,
                updated_at=now,
            )
            session.add(current)
            existing[identity] = current
        else:
            current.sync_run_id = run.id
            current.scope_key = mapping_input.scope_key
            current.label = mapping_input.label
            current.status = mapping_input.status
            current.attributes = mapping_input.attributes
            current.source_schema_version = batch.source_schema_version
            current.mapping_version = batch.mapping_version
            current.updated_at = now
    return len(batch.scope_mappings)


def _persist_commerce_facts(
    session: Session,
    run: SyncRun,
    batch: ConnectorBatch,
    now: datetime,
) -> int:
    enterprise_id = run.enterprise_id
    written = 0
    authoritative = set(batch.authoritative_fact_types)
    orders = {
        item.order_key: item
        for item in session.scalars(
            select(CommerceOrderFact).where(
                CommerceOrderFact.enterprise_id == enterprise_id
            )
        )
    }
    for order_input in batch.orders:
        current_order = orders.get(order_input.order_key)
        if current_order is None:
            current_order = CommerceOrderFact(
                id=_id("order_fact"),
                enterprise_id=enterprise_id,
                external_system_id=run.external_system_id,
                sync_run_id=run.id,
                order_key=order_input.order_key,
                store_key=order_input.store_key,
                customer_key=order_input.customer_key,
                channel=order_input.channel,
                status=order_input.status,
                business_date=order_input.business_date,
                paid_at=order_input.paid_at,
                shipped_at=order_input.shipped_at,
                paid_amount_fen=order_input.paid_amount_fen,
                item_amount_fen=order_input.item_amount_fen,
                discount_amount_fen=order_input.discount_amount_fen,
                freight_amount_fen=order_input.freight_amount_fen,
                cost_amount_fen=order_input.cost_amount_fen,
                item_count=order_input.item_count,
                province=order_input.province,
                created_at=now,
                updated_at=now,
            )
            session.add(current_order)
            orders[order_input.order_key] = current_order
        else:
            current_order.sync_run_id = run.id
            current_order.external_system_id = run.external_system_id
            current_order.store_key = order_input.store_key
            current_order.customer_key = order_input.customer_key
            current_order.channel = order_input.channel
            current_order.status = order_input.status
            current_order.business_date = order_input.business_date
            current_order.paid_at = order_input.paid_at
            current_order.shipped_at = order_input.shipped_at
            current_order.paid_amount_fen = order_input.paid_amount_fen
            current_order.item_amount_fen = order_input.item_amount_fen
            current_order.discount_amount_fen = order_input.discount_amount_fen
            current_order.freight_amount_fen = order_input.freight_amount_fen
            current_order.cost_amount_fen = order_input.cost_amount_fen
            current_order.item_count = order_input.item_count
            current_order.province = order_input.province
            current_order.updated_at = now
        written += 1

    lines = {
        item.line_key: item
        for item in session.scalars(
            select(CommerceOrderLineFact).where(
                CommerceOrderLineFact.enterprise_id == enterprise_id
            )
        )
    }
    for line_input in batch.order_lines:
        order = orders.get(line_input.order_key)
        if order is None:
            raise ValueError(f"order line references unknown order: {line_input.order_key}")
        current_line = lines.get(line_input.line_key)
        if current_line is None:
            current_line = CommerceOrderLineFact(
                id=_id("order_line_fact"),
                enterprise_id=enterprise_id,
                external_system_id=run.external_system_id,
                sync_run_id=run.id,
                order_id=order.id,
                line_key=line_input.line_key,
                order_key=line_input.order_key,
                product_key=line_input.product_key,
                sku_key=line_input.sku_key,
                quantity=line_input.quantity,
                unit_price_fen=line_input.unit_price_fen,
                paid_amount_fen=line_input.paid_amount_fen,
                cost_amount_fen=line_input.cost_amount_fen,
                refund_quantity=line_input.refund_quantity,
                refund_amount_fen=line_input.refund_amount_fen,
                created_at=now,
                updated_at=now,
            )
            session.add(current_line)
            lines[line_input.line_key] = current_line
        else:
            current_line.sync_run_id = run.id
            current_line.external_system_id = run.external_system_id
            current_line.order_id = order.id
            current_line.order_key = line_input.order_key
            current_line.product_key = line_input.product_key
            current_line.sku_key = line_input.sku_key
            current_line.quantity = line_input.quantity
            current_line.unit_price_fen = line_input.unit_price_fen
            current_line.paid_amount_fen = line_input.paid_amount_fen
            current_line.cost_amount_fen = line_input.cost_amount_fen
            current_line.refund_quantity = line_input.refund_quantity
            current_line.refund_amount_fen = line_input.refund_amount_fen
            current_line.updated_at = now
        written += 1

    refunds = {
        item.refund_key: item
        for item in session.scalars(
            select(CommerceRefundFact).where(
                CommerceRefundFact.enterprise_id == enterprise_id
            )
        )
    }
    for refund_input in batch.refunds:
        current_refund = refunds.get(refund_input.refund_key)
        if current_refund is None:
            current_refund = CommerceRefundFact(
                id=_id("refund_fact"),
                enterprise_id=enterprise_id,
                external_system_id=run.external_system_id,
                sync_run_id=run.id,
                refund_key=refund_input.refund_key,
                order_key=refund_input.order_key,
                line_key=refund_input.line_key,
                store_key=refund_input.store_key,
                customer_key=refund_input.customer_key,
                sku_key=refund_input.sku_key,
                reason_category=refund_input.reason_category,
                status=refund_input.status,
                requested_at=refund_input.requested_at,
                completed_at=refund_input.completed_at,
                refund_amount_fen=refund_input.refund_amount_fen,
                quantity=refund_input.quantity,
                created_at=now,
                updated_at=now,
            )
            session.add(current_refund)
            refunds[refund_input.refund_key] = current_refund
        else:
            current_refund.sync_run_id = run.id
            current_refund.external_system_id = run.external_system_id
            current_refund.order_key = refund_input.order_key
            current_refund.line_key = refund_input.line_key
            current_refund.store_key = refund_input.store_key
            current_refund.customer_key = refund_input.customer_key
            current_refund.sku_key = refund_input.sku_key
            current_refund.reason_category = refund_input.reason_category
            current_refund.status = refund_input.status
            current_refund.requested_at = refund_input.requested_at
            current_refund.completed_at = refund_input.completed_at
            current_refund.refund_amount_fen = refund_input.refund_amount_fen
            current_refund.quantity = refund_input.quantity
            current_refund.updated_at = now
        written += 1

    inventory = {
        item.snapshot_key: item
        for item in session.scalars(
            select(CommerceInventorySnapshotFact).where(
                CommerceInventorySnapshotFact.enterprise_id == enterprise_id
            )
        )
    }
    for inventory_input in batch.inventory:
        current_inventory = inventory.get(inventory_input.snapshot_key)
        if current_inventory is None:
            current_inventory = CommerceInventorySnapshotFact(
                id=_id("inventory_fact"),
                enterprise_id=enterprise_id,
                external_system_id=run.external_system_id,
                sync_run_id=run.id,
                snapshot_key=inventory_input.snapshot_key,
                warehouse_key=inventory_input.warehouse_key,
                product_key=inventory_input.product_key,
                sku_key=inventory_input.sku_key,
                as_of=inventory_input.as_of,
                available_quantity=inventory_input.available_quantity,
                reserved_quantity=inventory_input.reserved_quantity,
                in_transit_quantity=inventory_input.in_transit_quantity,
                safety_quantity=inventory_input.safety_quantity,
                inventory_cost_fen=inventory_input.inventory_cost_fen,
                days_cover=inventory_input.days_cover,
                status=inventory_input.status,
                created_at=now,
                updated_at=now,
            )
            session.add(current_inventory)
            inventory[inventory_input.snapshot_key] = current_inventory
        else:
            current_inventory.sync_run_id = run.id
            current_inventory.external_system_id = run.external_system_id
            current_inventory.warehouse_key = inventory_input.warehouse_key
            current_inventory.product_key = inventory_input.product_key
            current_inventory.sku_key = inventory_input.sku_key
            current_inventory.as_of = inventory_input.as_of
            current_inventory.available_quantity = inventory_input.available_quantity
            current_inventory.reserved_quantity = inventory_input.reserved_quantity
            current_inventory.in_transit_quantity = inventory_input.in_transit_quantity
            current_inventory.safety_quantity = inventory_input.safety_quantity
            current_inventory.inventory_cost_fen = inventory_input.inventory_cost_fen
            current_inventory.days_cover = inventory_input.days_cover
            current_inventory.status = inventory_input.status
            current_inventory.updated_at = now
        written += 1

    advertising = {
        item.performance_key: item
        for item in session.scalars(
            select(CommerceAdPerformanceFact).where(
                CommerceAdPerformanceFact.enterprise_id == enterprise_id
            )
        )
    }
    for ad_input in batch.advertising:
        current_ad = advertising.get(ad_input.performance_key)
        if current_ad is None:
            current_ad = CommerceAdPerformanceFact(
                id=_id("ad_fact"),
                enterprise_id=enterprise_id,
                external_system_id=run.external_system_id,
                sync_run_id=run.id,
                performance_key=ad_input.performance_key,
                campaign_key=ad_input.campaign_key,
                store_key=ad_input.store_key,
                product_key=ad_input.product_key,
                channel=ad_input.channel,
                business_date=ad_input.business_date,
                impressions=ad_input.impressions,
                clicks=ad_input.clicks,
                spend_fen=ad_input.spend_fen,
                attributed_order_count=ad_input.attributed_order_count,
                attributed_revenue_fen=ad_input.attributed_revenue_fen,
                created_at=now,
                updated_at=now,
            )
            session.add(current_ad)
            advertising[ad_input.performance_key] = current_ad
        else:
            current_ad.sync_run_id = run.id
            current_ad.external_system_id = run.external_system_id
            current_ad.campaign_key = ad_input.campaign_key
            current_ad.store_key = ad_input.store_key
            current_ad.product_key = ad_input.product_key
            current_ad.channel = ad_input.channel
            current_ad.business_date = ad_input.business_date
            current_ad.impressions = ad_input.impressions
            current_ad.clicks = ad_input.clicks
            current_ad.spend_fen = ad_input.spend_fen
            current_ad.attributed_order_count = ad_input.attributed_order_count
            current_ad.attributed_revenue_fen = ad_input.attributed_revenue_fen
            current_ad.updated_at = now
        written += 1

    refund_keys = {item.refund_key for item in batch.refunds}
    if "refunds" in authoritative:
        for refund_key, refund in refunds.items():
            if (
                refund.external_system_id == run.external_system_id
                and refund_key not in refund_keys
            ):
                session.delete(refund)
                written += 1

    line_keys = {item.line_key for item in batch.order_lines}
    if "order_lines" in authoritative:
        for line_key, line in lines.items():
            if line.external_system_id == run.external_system_id and line_key not in line_keys:
                session.delete(line)
                written += 1

    order_keys = {item.order_key for item in batch.orders}
    if {"orders", "order_lines", "refunds"}.issubset(authoritative):
        for order_key, order in orders.items():
            if order.external_system_id == run.external_system_id and order_key not in order_keys:
                session.delete(order)
                written += 1

    inventory_keys = {item.snapshot_key for item in batch.inventory}
    if "inventory" in authoritative:
        for snapshot_key, snapshot in inventory.items():
            if (
                snapshot.external_system_id == run.external_system_id
                and snapshot_key not in inventory_keys
            ):
                session.delete(snapshot)
                written += 1

    advertising_keys = {item.performance_key for item in batch.advertising}
    if "advertising" in authoritative:
        for performance_key, performance in advertising.items():
            if (
                performance.external_system_id == run.external_system_id
                and performance_key not in advertising_keys
            ):
                session.delete(performance)
                written += 1
    return written


def _persist_customer_facts(
    session: Session,
    run: SyncRun,
    batch: ConnectorBatch,
    now: datetime,
) -> int:
    enterprise_id = run.enterprise_id
    written = 0
    authoritative = set(batch.authoritative_fact_types)
    profiles = {
        item.customer_key: item
        for item in session.scalars(
            select(CustomerProfile).where(CustomerProfile.enterprise_id == enterprise_id)
        )
    }
    for profile_input in batch.customer_profiles:
        current = profiles.get(profile_input.customer_key)
        if current is None:
            current = CustomerProfile(
                id=_id("customer_profile"),
                enterprise_id=enterprise_id,
                external_system_id=run.external_system_id,
                sync_run_id=run.id,
                customer_key=profile_input.customer_key,
                display_name=profile_input.display_name,
                home_store_key=profile_input.home_store_key,
                member_level=profile_input.member_level,
                lifecycle_stage=profile_input.lifecycle_stage,
                status=profile_input.status,
                province=profile_input.province,
                acquisition_channel=profile_input.acquisition_channel,
                registered_at=profile_input.registered_at,
                last_active_at=profile_input.last_active_at,
                member_points=profile_input.member_points,
                growth_value=profile_input.growth_value,
                churn_risk_score=profile_input.churn_risk_score,
                preferred_category=profile_input.preferred_category,
                consent_status=profile_input.consent_status,
                tags=list(profile_input.tags),
                created_at=now,
                updated_at=now,
            )
            session.add(current)
            profiles[profile_input.customer_key] = current
        else:
            current.external_system_id = run.external_system_id
            current.sync_run_id = run.id
            current.display_name = profile_input.display_name
            current.home_store_key = profile_input.home_store_key
            current.member_level = profile_input.member_level
            current.lifecycle_stage = profile_input.lifecycle_stage
            current.status = profile_input.status
            current.province = profile_input.province
            current.acquisition_channel = profile_input.acquisition_channel
            current.registered_at = profile_input.registered_at
            current.last_active_at = profile_input.last_active_at
            current.member_points = profile_input.member_points
            current.growth_value = profile_input.growth_value
            current.churn_risk_score = profile_input.churn_risk_score
            current.preferred_category = profile_input.preferred_category
            current.consent_status = profile_input.consent_status
            current.tags = list(profile_input.tags)
            current.updated_at = now
        written += 1

    touchpoints = {
        item.touchpoint_key: item
        for item in session.scalars(
            select(CustomerTouchpointFact).where(
                CustomerTouchpointFact.enterprise_id == enterprise_id
            )
        )
    }
    for touchpoint_input in batch.customer_touchpoints:
        current_touchpoint = touchpoints.get(touchpoint_input.touchpoint_key)
        if current_touchpoint is None:
            current_touchpoint = CustomerTouchpointFact(
                id=_id("customer_touchpoint"),
                enterprise_id=enterprise_id,
                external_system_id=run.external_system_id,
                sync_run_id=run.id,
                touchpoint_key=touchpoint_input.touchpoint_key,
                customer_key=touchpoint_input.customer_key,
                store_key=touchpoint_input.store_key,
                touchpoint_type=touchpoint_input.touchpoint_type,
                channel=touchpoint_input.channel,
                occurred_at=touchpoint_input.occurred_at,
                campaign_key=touchpoint_input.campaign_key,
                value_fen=touchpoint_input.value_fen,
                properties=touchpoint_input.properties,
                created_at=now,
                updated_at=now,
            )
            session.add(current_touchpoint)
            touchpoints[touchpoint_input.touchpoint_key] = current_touchpoint
        else:
            current_touchpoint.external_system_id = run.external_system_id
            current_touchpoint.sync_run_id = run.id
            current_touchpoint.customer_key = touchpoint_input.customer_key
            current_touchpoint.store_key = touchpoint_input.store_key
            current_touchpoint.touchpoint_type = touchpoint_input.touchpoint_type
            current_touchpoint.channel = touchpoint_input.channel
            current_touchpoint.occurred_at = touchpoint_input.occurred_at
            current_touchpoint.campaign_key = touchpoint_input.campaign_key
            current_touchpoint.value_fen = touchpoint_input.value_fen
            current_touchpoint.properties = touchpoint_input.properties
            current_touchpoint.updated_at = now
        written += 1

    profile_keys = {item.customer_key for item in batch.customer_profiles}
    if "customer_profiles" in authoritative:
        for customer_key, profile in profiles.items():
            if (
                profile.external_system_id == run.external_system_id
                and customer_key not in profile_keys
            ):
                session.delete(profile)
                written += 1

    touchpoint_keys = {item.touchpoint_key for item in batch.customer_touchpoints}
    if "customer_touchpoints" in authoritative:
        for touchpoint_key, touchpoint in touchpoints.items():
            if (
                touchpoint.external_system_id == run.external_system_id
                and touchpoint_key not in touchpoint_keys
            ):
                session.delete(touchpoint)
                written += 1
    return written


def _record_quality_results(
    session: Session,
    run: SyncRun,
    batch: ConnectorBatch | None,
) -> None:
    enterprise_id = run.enterprise_id
    rules = {
        item.rule_key: item
        for item in session.scalars(
            select(DataQualityRule).where(
                DataQualityRule.enterprise_id == enterprise_id,
                DataQualityRule.status == "active",
            )
        )
    }
    if not rules:
        return

    total_records = len(batch.records) if batch is not None else 0
    complete_records = (
        sum(1 for record in batch.records if bool(record.payload)) if batch is not None else 0
    )
    entity_count = len(batch.entities) if batch is not None else 0
    metric_count = len(batch.metrics) if batch is not None else 0
    warning_count = len(batch.warnings) if batch is not None else 0
    evaluations: dict[str, tuple[str, str, int, dict[str, object]]] = {
        "source-contract": (
            "passed"
            if batch is not None and batch.source_schema_version != "unknown"
            else "failed",
            batch.source_schema_version if batch is not None else "unavailable",
            0 if batch is not None and batch.source_schema_version != "unknown" else 1,
            {"mapping_version": batch.mapping_version if batch is not None else None},
        ),
        "record-completeness": (
            "passed" if total_records > 0 and complete_records == total_records else "failed",
            f"{complete_records}/{total_records} payloads complete",
            max(total_records - complete_records, 0),
            {"records_read": total_records, "complete_records": complete_records},
        ),
        "entity-mapping": (
            "passed" if entity_count >= 1 else "warning",
            f"{entity_count} canonical entities",
            0 if entity_count >= 1 else 1,
            {"entity_count": entity_count},
        ),
        "metric-coverage": (
            "passed" if metric_count >= 6 else "warning" if metric_count > 0 else "failed",
            f"{metric_count}/6 metrics available",
            max(6 - metric_count, 0),
            {"metric_count": metric_count, "expected_count": 6},
        ),
        "sync-health": (
            "failed" if batch is None else "warning" if warning_count else "passed",
            run.status,
            warning_count if batch is not None else 1,
            {"warnings": list(batch.warnings) if batch is not None else [], "error": run.error},
        ),
    }
    if batch is not None and {
        "orders",
        "order_lines",
        "refunds",
    }.issubset(batch.authoritative_fact_types):
        reconciliation = summarize_customer_service_reconciliation(
            session,
            enterprise_id=run.enterprise_id,
        )
        evaluations["customer-service-order-reconciliation"] = (
            reconciliation.result_status,
            reconciliation.observed_value,
            reconciliation.affected_records,
            reconciliation.details(),
        )
    checked_at = datetime.now(UTC)
    for rule_key, evaluation in evaluations.items():
        rule = rules.get(rule_key)
        if rule is None:
            continue
        result_status, observed_value, affected_records, details = evaluation
        session.add(
            DataQualityResult(
                id=_id("quality"),
                enterprise_id=enterprise_id,
                rule_id=rule.id,
                sync_run_id=run.id,
                status=result_status,
                observed_value=observed_value,
                affected_records=affected_records,
                details=details,
                checked_at=checked_at,
            )
        )


def _set_pipeline_state(
    session: Session, enterprise_id: str, status: str, health: float
) -> None:
    node_keys = {"source-commerce", "integration", "data-hub", "analysis"}
    nodes = session.scalars(
        select(TwinNode).where(
            TwinNode.enterprise_id == enterprise_id, TwinNode.node_key.in_(node_keys)
        )
    )
    for node in nodes:
        node.status = status
        node.health = health
    edges = session.scalars(select(TwinEdge).where(TwinEdge.enterprise_id == enterprise_id))
    for edge in edges:
        if edge.source_key in node_keys or edge.target_key in node_keys:
            edge.status = status
            edge.traffic = health


def _append_event(
    session: Session,
    enterprise_id: str,
    event_type: str,
    severity: str,
    title: str,
    detail: str,
) -> None:
    session.add(
        PlatformEvent(
            id=_id("event"),
            enterprise_id=enterprise_id,
            event_type=event_type,
            severity=severity,
            title=title,
            detail=detail,
            occurred_at=datetime.now(UTC),
        )
    )
