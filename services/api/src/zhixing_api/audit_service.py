from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import Integer, String, case, func, literal, or_, select, union_all
from sqlalchemy import cast as sql_cast
from sqlalchemy.orm import Session
from zhixing_jobs.models import BackgroundJob

from zhixing_api.audit_schemas import (
    AuditActorFacetView,
    AuditAttributeView,
    AuditCountFacetView,
    AuditEventView,
    AuditFacetsView,
    AuditFiltersView,
    AuditPaginationView,
    AuditSeverity,
    AuditSource,
    AuditStatsView,
    UnifiedAuditLedgerResponse,
)
from zhixing_api.data_models import (
    ActionWorkEvent,
    ActionWorkItem,
    AgentRun,
    AuthorizationDecision,
    ChannelIdentity,
    ChannelIdentityEvent,
    IdentityCatalogEvent,
    IdentityManagementEvent,
    MCPGatewaySession,
    MCPGatewaySessionEvent,
    PlatformOperationEvent,
    Principal,
    ToolInvocation,
    UserAccount,
)
from zhixing_api.database import Database

ATTENTION_OUTCOMES = frozenset(
    {"deny", "denied", "failed", "blocked", "expired", "cancelled", "degraded"}
)
CRITICAL_OUTCOMES = frozenset({"deny", "denied", "failed", "expired"})


def unified_audit_ledger(
    database: Database,
    *,
    enterprise_id: str,
    source: AuditSource | None = None,
    outcome: str | None = None,
    actor_principal_id: str | None = None,
    request_id: str | None = None,
    run_id: str | None = None,
    query: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> UnifiedAuditLedgerResponse:
    normalized = AuditFiltersView(
        source=source,
        outcome=_clean(outcome),
        actor_principal_id=_clean(actor_principal_id),
        request_id=_clean(request_id),
        run_id=_clean(run_id),
        query=_clean(query),
        start_at=_as_utc(start_at),
        end_at=_as_utc(end_at),
    )
    now = datetime.now(UTC)
    events = _audit_union().subquery("unified_audit_events")
    conditions = _conditions(events.c, enterprise_id, normalized)

    with database.session() as session:
        total = int(
            session.scalar(select(func.count()).select_from(events).where(*conditions)) or 0
        )
        rows = [
            dict(row._mapping)
            for row in session.execute(
                select(events)
                .where(*conditions)
                .order_by(events.c.occurred_at.desc(), events.c.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ]
        source_rows = list(
            session.execute(
                select(events.c.source, func.count().label("count"))
                .where(
                    *_conditions(
                        events.c,
                        enterprise_id,
                        normalized,
                        include_source=False,
                    )
                )
                .group_by(events.c.source)
                .order_by(func.count().desc(), events.c.source)
            )
        )
        outcome_rows = list(
            session.execute(
                select(events.c.outcome, func.count().label("count"))
                .where(
                    *_conditions(
                        events.c,
                        enterprise_id,
                        normalized,
                        include_outcome=False,
                    )
                )
                .group_by(events.c.outcome)
                .order_by(func.count().desc(), events.c.outcome)
            )
        )
        actor_rows = list(
            session.execute(
                select(events.c.actor_principal_id, func.count().label("count"))
                .where(
                    *_conditions(
                        events.c,
                        enterprise_id,
                        normalized,
                        include_actor=False,
                    ),
                    events.c.actor_principal_id.is_not(None),
                )
                .group_by(events.c.actor_principal_id)
                .order_by(func.count().desc(), events.c.actor_principal_id)
                .limit(100)
            )
        )
        actor_ids = {
            str(value)
            for value in [
                *(row.actor_principal_id for row in actor_rows),
                *(row.get("actor_principal_id") for row in rows),
            ]
            if value
        }
        principals = (
            {
                item.id: item.display_name
                for item in session.scalars(
                    select(Principal).where(
                        Principal.enterprise_id == enterprise_id,
                        Principal.id.in_(actor_ids),
                    )
                )
            }
            if actor_ids
            else {}
        )
        attributes = _load_attributes(session, rows)
        attention_events = int(
            session.scalar(
                select(func.count())
                .select_from(events)
                .where(*conditions, events.c.outcome.in_(ATTENTION_OUTCOMES))
            )
            or 0
        )
        events_last_24h = int(
            session.scalar(
                select(func.count())
                .select_from(events)
                .where(*conditions, events.c.occurred_at >= now - timedelta(hours=24))
            )
            or 0
        )
        unique_actors = int(
            session.scalar(
                select(
                    func.count(
                        func.distinct(
                            func.coalesce(
                                events.c.actor_principal_id,
                                events.c.actor_name_hint,
                            )
                        )
                    )
                )
                .select_from(events)
                .where(*conditions)
            )
            or 0
        )
        correlated_runs = int(
            session.scalar(
                select(
                    func.count(func.distinct(func.coalesce(events.c.run_id, events.c.agent_run_id)))
                )
                .select_from(events)
                .where(*conditions)
            )
            or 0
        )

    return UnifiedAuditLedgerResponse(
        enterprise_id=enterprise_id,
        filters=normalized,
        stats=AuditStatsView(
            total_events=total,
            events_last_24h=events_last_24h,
            attention_events=attention_events,
            unique_actors=unique_actors,
            correlated_runs=correlated_runs,
        ),
        facets=AuditFacetsView(
            sources=[
                AuditCountFacetView(key=str(row[0]), count=int(row[1])) for row in source_rows
            ],
            outcomes=[
                AuditCountFacetView(key=str(row[0]), count=int(row[1])) for row in outcome_rows
            ],
            actors=[
                AuditActorFacetView(
                    principal_id=str(row[0]),
                    display_name=principals.get(str(row[0]), "未知主体"),
                    count=int(row[1]),
                )
                for row in actor_rows
            ],
        ),
        items=[
            _event_view(
                row,
                principals,
                attributes.get((str(row["record_type"]), str(row["id"])), []),
            )
            for row in rows
        ],
        pagination=AuditPaginationView(
            offset=offset,
            limit=limit,
            total=total,
            has_more=offset + len(rows) < total,
        ),
        generated_at=now,
    )


def _audit_union() -> Any:
    null_string = literal(None, type_=String())
    null_integer = literal(None, type_=Integer())
    return union_all(
        select(
            AuthorizationDecision.id.label("id"),
            AuthorizationDecision.enterprise_id.label("enterprise_id"),
            literal("authorization_decision").label("record_type"),
            literal("authorization").label("source"),
            literal("authorization.decision").label("event_type"),
            AuthorizationDecision.decision.label("outcome"),
            AuthorizationDecision.actor_principal_id.label("actor_principal_id"),
            null_string.label("actor_name_hint"),
            AuthorizationDecision.resource_type.label("subject_type"),
            AuthorizationDecision.resource_key.label("subject_key"),
            AuthorizationDecision.reason.label("summary"),
            AuthorizationDecision.request_id.label("request_id"),
            AuthorizationDecision.run_id.label("run_id"),
            null_string.label("agent_run_id"),
            null_integer.label("duration_ms"),
            AuthorizationDecision.decided_at.label("occurred_at"),
        ),
        select(
            IdentityManagementEvent.id,
            IdentityManagementEvent.enterprise_id,
            literal("identity_management"),
            literal("identity"),
            IdentityManagementEvent.event_type,
            literal("succeeded"),
            IdentityManagementEvent.actor_principal_id,
            null_string,
            literal("user-account"),
            IdentityManagementEvent.target_account_id,
            IdentityManagementEvent.reason,
            IdentityManagementEvent.request_id,
            IdentityManagementEvent.run_id,
            null_string,
            null_integer,
            IdentityManagementEvent.occurred_at,
        ),
        select(
            IdentityCatalogEvent.id,
            IdentityCatalogEvent.enterprise_id,
            literal("identity_catalog"),
            literal("identity"),
            IdentityCatalogEvent.event_type,
            literal("succeeded"),
            IdentityCatalogEvent.actor_principal_id,
            null_string,
            IdentityCatalogEvent.target_type,
            IdentityCatalogEvent.target_key,
            IdentityCatalogEvent.reason,
            IdentityCatalogEvent.request_id,
            IdentityCatalogEvent.run_id,
            null_string,
            null_integer,
            IdentityCatalogEvent.occurred_at,
        ),
        select(
            ChannelIdentityEvent.id,
            ChannelIdentityEvent.enterprise_id,
            literal("channel_identity"),
            literal("identity"),
            ChannelIdentityEvent.event_type,
            literal("succeeded"),
            ChannelIdentityEvent.actor_principal_id,
            null_string,
            literal("channel-identity"),
            ChannelIdentityEvent.channel_identity_id,
            ChannelIdentityEvent.reason,
            ChannelIdentityEvent.request_id,
            ChannelIdentityEvent.run_id,
            null_string,
            null_integer,
            ChannelIdentityEvent.occurred_at,
        ),
        select(
            MCPGatewaySessionEvent.id,
            MCPGatewaySessionEvent.enterprise_id,
            literal("mcp_session"),
            literal("mcp"),
            MCPGatewaySessionEvent.event_type,
            MCPGatewaySessionEvent.event_type,
            MCPGatewaySessionEvent.actor_principal_id,
            null_string,
            literal("mcp-session"),
            MCPGatewaySessionEvent.gateway_session_id,
            MCPGatewaySessionEvent.reason,
            MCPGatewaySessionEvent.request_id,
            MCPGatewaySessionEvent.run_id,
            MCPGatewaySession.agent_run_id,
            null_integer,
            MCPGatewaySessionEvent.occurred_at,
        ).join(
            MCPGatewaySession,
            MCPGatewaySession.id == MCPGatewaySessionEvent.gateway_session_id,
        ),
        select(
            ToolInvocation.id,
            ToolInvocation.enterprise_id,
            literal("tool_invocation"),
            literal("tool"),
            literal("tool.invocation"),
            ToolInvocation.status,
            ToolInvocation.actor_principal_id,
            null_string,
            literal("tool"),
            ToolInvocation.tool_key,
            func.coalesce(ToolInvocation.error_code, ToolInvocation.tool_key),
            ToolInvocation.request_id,
            ToolInvocation.run_id,
            ToolInvocation.agent_run_id,
            ToolInvocation.duration_ms,
            ToolInvocation.started_at,
        ),
        select(
            BackgroundJob.id,
            BackgroundJob.enterprise_id,
            literal("background_job"),
            literal("worker"),
            BackgroundJob.job_type,
            BackgroundJob.status,
            case(
                (
                    BackgroundJob.initiator_type == "principal",
                    BackgroundJob.initiator_id,
                ),
                else_=None,
            ),
            case(
                (
                    BackgroundJob.initiator_type != "principal",
                    BackgroundJob.initiator_id,
                ),
                else_=None,
            ),
            literal("background-job"),
            BackgroundJob.id,
            func.coalesce(BackgroundJob.last_error_code, BackgroundJob.job_type),
            BackgroundJob.request_id,
            BackgroundJob.run_id,
            null_string,
            null_integer,
            BackgroundJob.created_at,
        ),
        select(
            AgentRun.id,
            AgentRun.enterprise_id,
            literal("agent_run"),
            literal("agent"),
            AgentRun.run_type,
            AgentRun.status,
            AgentRun.actor_principal_id,
            null_string,
            literal("agent-run"),
            AgentRun.id,
            func.coalesce(AgentRun.fallback_reason, AgentRun.run_type),
            null_string,
            AgentRun.id,
            AgentRun.id,
            AgentRun.duration_ms,
            AgentRun.created_at,
        ),
        select(
            ActionWorkEvent.id,
            ActionWorkEvent.enterprise_id,
            literal("action_work"),
            literal("action"),
            ActionWorkEvent.event_type,
            ActionWorkEvent.to_status,
            ActionWorkEvent.actor_principal_id,
            ActionWorkEvent.actor_name,
            literal("action-work-item"),
            ActionWorkEvent.work_item_id,
            ActionWorkEvent.event_type,
            null_string,
            null_string,
            null_string,
            null_integer,
            ActionWorkEvent.created_at,
        ),
        select(
            PlatformOperationEvent.id,
            PlatformOperationEvent.enterprise_id,
            literal("platform_operation"),
            literal("platform"),
            PlatformOperationEvent.event_type,
            literal("succeeded"),
            PlatformOperationEvent.actor_principal_id,
            null_string,
            PlatformOperationEvent.target_type,
            PlatformOperationEvent.target_id,
            PlatformOperationEvent.reason,
            PlatformOperationEvent.request_id,
            PlatformOperationEvent.run_id,
            null_string,
            null_integer,
            PlatformOperationEvent.occurred_at,
        ),
    )


def _conditions(
    columns: Any,
    enterprise_id: str,
    filters: AuditFiltersView,
    *,
    include_source: bool = True,
    include_outcome: bool = True,
    include_actor: bool = True,
) -> list[Any]:
    conditions: list[Any] = [columns.enterprise_id == enterprise_id]
    if include_source and filters.source:
        conditions.append(columns.source == filters.source)
    if include_outcome and filters.outcome:
        conditions.append(columns.outcome == filters.outcome)
    if include_actor and filters.actor_principal_id:
        conditions.append(columns.actor_principal_id == filters.actor_principal_id)
    if filters.request_id:
        conditions.append(columns.request_id == filters.request_id)
    if filters.run_id:
        conditions.append(
            or_(columns.run_id == filters.run_id, columns.agent_run_id == filters.run_id)
        )
    if filters.start_at:
        conditions.append(columns.occurred_at >= filters.start_at)
    if filters.end_at:
        conditions.append(columns.occurred_at <= filters.end_at)
    if filters.query:
        needle = f"%{filters.query.casefold()}%"
        conditions.append(
            or_(
                func.lower(sql_cast(columns.event_type, String)).like(needle),
                func.lower(sql_cast(columns.subject_type, String)).like(needle),
                func.lower(sql_cast(columns.subject_key, String)).like(needle),
                func.lower(sql_cast(columns.summary, String)).like(needle),
                func.lower(sql_cast(columns.request_id, String)).like(needle),
                func.lower(sql_cast(columns.run_id, String)).like(needle),
                func.lower(sql_cast(columns.agent_run_id, String)).like(needle),
            )
        )
    return conditions


def _event_view(
    row: Mapping[str, object],
    principals: Mapping[str, str],
    attributes: list[AuditAttributeView],
) -> AuditEventView:
    actor_id = _optional_text(row.get("actor_principal_id"))
    actor_hint = _optional_text(row.get("actor_name_hint"))
    outcome = str(row["outcome"])
    duration_value = row.get("duration_ms")
    return AuditEventView(
        id=str(row["id"]),
        source=cast(AuditSource, str(row["source"])),
        event_type=str(row["event_type"]),
        outcome=outcome,
        severity=_severity(outcome),
        actor_principal_id=actor_id,
        actor_name=(
            principals.get(actor_id, actor_hint or "系统") if actor_id else actor_hint or "系统"
        ),
        subject_type=str(row["subject_type"]),
        subject_key=str(row["subject_key"]),
        summary=str(row.get("summary") or "")[:500],
        request_id=_optional_text(row.get("request_id")),
        run_id=_optional_text(row.get("run_id")),
        agent_run_id=_optional_text(row.get("agent_run_id")),
        duration_ms=(int(cast(int, duration_value)) if duration_value is not None else None),
        occurred_at=_as_utc(cast(datetime, row["occurred_at"])) or datetime.now(UTC),
        attributes=attributes,
    )


def _load_attributes(
    session: Session,
    rows: list[dict[str, object]],
) -> dict[tuple[str, str], list[AuditAttributeView]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        grouped[str(row["record_type"])].add(str(row["id"]))
    result: dict[tuple[str, str], list[AuditAttributeView]] = {}

    decisions = (
        {
            item.id: item
            for item in session.scalars(
                select(AuthorizationDecision).where(
                    AuthorizationDecision.id.in_(grouped["authorization_decision"])
                )
            )
        }
        if grouped["authorization_decision"]
        else {}
    )
    for decision in decisions.values():
        result[("authorization_decision", decision.id)] = [
            _attribute("permission_key", "权限", decision.permission_key),
            _attribute("policy_version", "策略版本", decision.policy_version),
            _attribute("resource", "资源", f"{decision.resource_type} / {decision.resource_key}"),
        ]

    management = (
        {
            item.id: item
            for item in session.scalars(
                select(IdentityManagementEvent).where(
                    IdentityManagementEvent.id.in_(grouped["identity_management"])
                )
            )
        }
        if grouped["identity_management"]
        else {}
    )
    account_ids = {item.target_account_id for item in management.values()}
    accounts = (
        {
            item.id: item
            for item in session.scalars(select(UserAccount).where(UserAccount.id.in_(account_ids)))
        }
        if account_ids
        else {}
    )
    for management_event in management.values():
        account = accounts.get(management_event.target_account_id)
        result[("identity_management", management_event.id)] = [
            _attribute(
                "target_account",
                "目标账号",
                account.account_key if account else management_event.target_account_id,
            ),
            _attribute("changed_fields", "变更字段", ", ".join(management_event.changed_fields)),
        ]

    catalogs = (
        {
            item.id: item
            for item in session.scalars(
                select(IdentityCatalogEvent).where(
                    IdentityCatalogEvent.id.in_(grouped["identity_catalog"])
                )
            )
        }
        if grouped["identity_catalog"]
        else {}
    )
    for catalog_event in catalogs.values():
        result[("identity_catalog", catalog_event.id)] = [
            _attribute(
                "target",
                "目录对象",
                f"{catalog_event.target_type} / {catalog_event.target_key}",
            ),
            _attribute("changed_fields", "变更字段", ", ".join(catalog_event.changed_fields)),
        ]

    channel_events = (
        {
            item.id: item
            for item in session.scalars(
                select(ChannelIdentityEvent).where(
                    ChannelIdentityEvent.id.in_(grouped["channel_identity"])
                )
            )
        }
        if grouped["channel_identity"]
        else {}
    )
    channel_identity_ids = {item.channel_identity_id for item in channel_events.values()}
    channel_identities = (
        {
            item.id: item
            for item in session.scalars(
                select(ChannelIdentity).where(ChannelIdentity.id.in_(channel_identity_ids))
            )
        }
        if channel_identity_ids
        else {}
    )
    for channel_event in channel_events.values():
        channel_identity = channel_identities.get(channel_event.channel_identity_id)
        result[("channel_identity", channel_event.id)] = [
            _attribute(
                "channel",
                "渠道",
                channel_identity.channel_key if channel_identity else "unknown",
            ),
            _attribute(
                "state_transition",
                "状态变化",
                f"{channel_event.before_status} -> {channel_event.after_status}",
            ),
        ]

    mcp_events = (
        {
            item.id: item
            for item in session.scalars(
                select(MCPGatewaySessionEvent).where(
                    MCPGatewaySessionEvent.id.in_(grouped["mcp_session"])
                )
            )
        }
        if grouped["mcp_session"]
        else {}
    )
    gateway_ids = {item.gateway_session_id for item in mcp_events.values()}
    gateways = (
        {
            item.id: item
            for item in session.scalars(
                select(MCPGatewaySession).where(MCPGatewaySession.id.in_(gateway_ids))
            )
        }
        if gateway_ids
        else {}
    )
    for mcp_event in mcp_events.values():
        gateway = gateways.get(mcp_event.gateway_session_id)
        result[("mcp_session", mcp_event.id)] = [
            _attribute("client_id", "客户端", gateway.client_id if gateway else ""),
            _attribute("permission_set_version", "权限版本", mcp_event.permission_set_version),
        ]

    invocations = (
        {
            item.id: item
            for item in session.scalars(
                select(ToolInvocation).where(ToolInvocation.id.in_(grouped["tool_invocation"]))
            )
        }
        if grouped["tool_invocation"]
        else {}
    )
    for invocation in invocations.values():
        result[("tool_invocation", invocation.id)] = [
            _attribute("tool_version", "工具版本", invocation.tool_version),
            _attribute("authentication_method", "认证方式", invocation.authentication_method),
            _attribute("permission_set_version", "权限版本", invocation.permission_set_version),
            _attribute("error_code", "错误码", invocation.error_code or ""),
        ]

    jobs = (
        {
            item.id: item
            for item in session.scalars(
                select(BackgroundJob).where(BackgroundJob.id.in_(grouped["background_job"]))
            )
        }
        if grouped["background_job"]
        else {}
    )
    for job in jobs.values():
        result[("background_job", job.id)] = [
            _attribute("attempt", "执行轮次", str(job.attempt)),
            _attribute("continuation_count", "正常续跑", str(job.continuation_count)),
            _attribute("failure_attempt", "故障预算占用",
                       f"{job.attempt - job.continuation_count} / {job.max_attempts}"),
            _attribute("scope", "数据范围", f"{job.scope_type} / {job.scope_id}"),
            _attribute("worker_id", "Worker", job.worker_id or ""),
            _attribute("error_code", "错误码", job.last_error_code or ""),
        ]

    agent_runs = (
        {
            item.id: item
            for item in session.scalars(
                select(AgentRun).where(AgentRun.id.in_(grouped["agent_run"]))
            )
        }
        if grouped["agent_run"]
        else {}
    )
    for agent_run in agent_runs.values():
        token_total = (agent_run.input_tokens or 0) + (agent_run.output_tokens or 0)
        result[("agent_run", agent_run.id)] = [
            _attribute("run_type", "运行类型", agent_run.run_type),
            _attribute("phase", "阶段", agent_run.phase or ""),
            _attribute("provider", "Provider", agent_run.provider),
            _attribute("model", "模型", agent_run.model),
            _attribute("tokens", "Token", str(token_total) if token_total else ""),
        ]

    work_events = (
        {
            item.id: item
            for item in session.scalars(
                select(ActionWorkEvent).where(ActionWorkEvent.id.in_(grouped["action_work"]))
            )
        }
        if grouped["action_work"]
        else {}
    )
    work_ids = {item.work_item_id for item in work_events.values()}
    work_items = (
        {
            item.id: item
            for item in session.scalars(
                select(ActionWorkItem).where(ActionWorkItem.id.in_(work_ids))
            )
        }
        if work_ids
        else {}
    )
    for work_event in work_events.values():
        work_item = work_items.get(work_event.work_item_id)
        result[("action_work", work_event.id)] = [
            _attribute(
                "work_item",
                "工作项",
                work_item.title if work_item else work_event.work_item_id,
            ),
            _attribute(
                "transition",
                "状态变化",
                f"{work_event.from_status or '-'} -> {work_event.to_status}",
            ),
            _attribute("evidence_count", "结果证据", str(len(work_event.evidence_refs))),
        ]

    platform_events = (
        {
            item.id: item
            for item in session.scalars(
                select(PlatformOperationEvent).where(
                    PlatformOperationEvent.id.in_(grouped["platform_operation"])
                )
            )
        }
        if grouped["platform_operation"]
        else {}
    )
    for platform_event in platform_events.values():
        result[("platform_operation", platform_event.id)] = [
            _attribute(
                "target",
                "目标对象",
                f"{platform_event.target_type} / {platform_event.target_id}",
            ),
            _attribute("idempotency_key", "请求键", platform_event.idempotency_key),
        ]
    return result


def _attribute(key: str, label: str, value: str) -> AuditAttributeView:
    return AuditAttributeView(key=key, label=label, value=value)


def _severity(outcome: str) -> AuditSeverity:
    normalized = outcome.casefold()
    if normalized in CRITICAL_OUTCOMES:
        return "critical"
    if normalized in ATTENTION_OUTCOMES or normalized in {"revoked", "cancelled"}:
        return "warning"
    return "normal"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None and str(value) else None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
