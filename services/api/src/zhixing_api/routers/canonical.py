from datetime import date
from typing import Literal

from fastapi import APIRouter, Query, Request

from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.metrics import OrderSummary, summarize_orders
from zhixing_api.ingestion.queries import canonical_page
from zhixing_api.ingestion.read_models import CanonicalPage
from zhixing_api.ingestion.scope_twin import ScopeTwinProjection, project_scope_twin
from zhixing_api.scope_context import build_scope_context

router = APIRouter(prefix="/api/v1/data-center/canonical", tags=["canonical-facts"])


@router.get("/scope-twin", response_model=ScopeTwinProjection)
async def scope_twin(request: Request, offset: int = Query(default=0, ge=0),
                     limit: int = Query(default=100, ge=1, le=100)) -> ScopeTwinProjection:
    actor = resolve_development_actor(request)
    database = request.app.state.database
    require_permission(actor, "metric.query.execute", database,
                       resource_type="scope-twin", resource_key="locations")
    return project_scope_twin(database, build_scope_context(database, actor),
                              offset=offset, limit=limit)


@router.get("/orders/summary", response_model=OrderSummary)
async def order_summary(request: Request, date_from: date, date_to: date) -> OrderSummary:
    actor = resolve_development_actor(request)
    database = request.app.state.database
    require_permission(actor, "metric.query.execute", database,
                       resource_type="canonical-order-summary", resource_key="orders")
    if date_to <= date_from:
        raise ApiProblem(status_code=422, code="metric.date_range_invalid",
                         message="结束日期必须晚于开始日期")
    return summarize_orders(database, build_scope_context(database, actor), date_from, date_to)


@router.get("/{family}", response_model=CanonicalPage)
async def list_canonical_facts(
    request: Request,
    family: Literal["orders", "inventory", "after_sales", "fulfillments", "operational"],
    offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100),
    authoritative_only: bool = False,
    source_id: str | None = Query(default=None, min_length=1, max_length=64),
    business_unit_id: str | None = Query(default=None, min_length=1, max_length=64),
    resource_key: str | None = Query(default=None, min_length=1, max_length=120),
    schema_version: str | None = Query(default=None, min_length=1, max_length=64),
    mapping_version: str | None = Query(default=None, min_length=1, max_length=32),
    date_from: date | None = None, date_to: date | None = None,
) -> CanonicalPage:
    actor = resolve_development_actor(request)
    database = request.app.state.database
    require_permission(actor, "metric.query.execute", database,
                       resource_type="canonical-fact", resource_key=family)
    scope = build_scope_context(database, actor)
    if ((date_from and date_to and date_to <= date_from)
            or (family == "inventory" and (date_from or date_to))
            or (family == "operational" and authoritative_only)):
        raise ApiProblem(status_code=422, code="canonical.date_range_invalid",
                         message="业务日期区间不适用于当前查询")
    return canonical_page(database, scope, family, offset=offset, limit=limit,
                          authoritative_only=authoritative_only, source_id=source_id,
                          business_unit_id=business_unit_id, resource_key=resource_key,
                          schema_version=schema_version, mapping_version=mapping_version,
                          date_from=date_from, date_to=date_to)
