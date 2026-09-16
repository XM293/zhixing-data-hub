from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query, Request

from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.audit_schemas import AuditSource, UnifiedAuditLedgerResponse
from zhixing_api.audit_service import unified_audit_ledger
from zhixing_api.errors import ApiProblem

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


@router.get("/events", response_model=UnifiedAuditLedgerResponse)
async def audit_events(
    request: Request,
    source: AuditSource | None = None,
    outcome: str | None = Query(default=None, max_length=48),
    actor_principal_id: str | None = Query(default=None, max_length=64),
    request_id: str | None = Query(default=None, max_length=96),
    run_id: str | None = Query(default=None, max_length=96),
    query: str | None = Query(default=None, max_length=160),
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> UnifiedAuditLedgerResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "audit.event.read",
        request.app.state.database,
        resource_type="audit-ledger",
        resource_key=actor.enterprise_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    if start_at and end_at and start_at > end_at:
        raise ApiProblem(
            status_code=422,
            code="audit.time_range_invalid",
            message="审计开始时间不能晚于结束时间",
        )
    return unified_audit_ledger(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        source=source,
        outcome=outcome,
        actor_principal_id=actor_principal_id,
        request_id=request_id,
        run_id=run_id,
        query=query,
        start_at=start_at,
        end_at=end_at,
        offset=offset,
        limit=limit,
    )
