from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, or_, select

from zhixing_api.actor_context import ActorContext, require_permission
from zhixing_api.ai_provider import ResponsesAIProvider
from zhixing_api.config import Settings
from zhixing_api.customer_360_service import build_customer_360, build_customer_detail
from zhixing_api.data_center_service import build_commerce_operations, query_metric_series
from zhixing_api.data_models import (
    MetricDefinition,
    Principal,
    ToolDefinition,
    ToolInvocation,
)
from zhixing_api.data_selection import require_selected_data_scope
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.metrics import summarize_orders
from zhixing_api.knowledge_service import search_evidence
from zhixing_api.scope_context import build_scope_context
from zhixing_api.tool_schemas import (
    GetMetricInput,
    QueryAuthoritativeOrdersInput,
    QueryCommerceFactsInput,
    QueryCustomer360Input,
    ReadPolicyInput,
    SearchKnowledgeInput,
    ToolAdminOverviewResponse,
    ToolAdminStats,
    ToolCatalogResponse,
    ToolDefinitionView,
    ToolInvocationView,
    ToolInvokeResponse,
)

INPUT_MODELS: dict[str, type[BaseModel]] = {
    "read_policy": ReadPolicyInput,
    "search_knowledge": SearchKnowledgeInput,
    "get_metric": GetMetricInput,
    "query_commerce_facts": QueryCommerceFactsInput,
    "query_authoritative_orders": QueryAuthoritativeOrdersInput,
    "query_customer_360": QueryCustomer360Input,
}


def _definition_view(item: ToolDefinition) -> ToolDefinitionView:
    return ToolDefinitionView(
        key=item.tool_key,
        display_name=item.display_name,
        description=item.description,
        risk_level=cast(Literal["R0", "R1", "R2", "R3"], item.risk_level),
        permission_key=item.permission_key,
        resource_type=item.resource_type,
        scope_resolver=item.scope_resolver,
        input_schema=item.input_schema,
        output_schema=item.output_schema,
        provider=item.provider,
        version=item.version,
        timeout_seconds=item.timeout_seconds,
        status=item.status,
    )


def list_tool_catalog(
    database: Database,
    actor: ActorContext,
    *,
    allowed_tool_keys: frozenset[str] | None = None,
) -> ToolCatalogResponse:
    conditions = [
        ToolDefinition.enterprise_id == actor.enterprise_id,
        ToolDefinition.status == "active",
        ToolDefinition.permission_key.in_(actor.permissions),
    ]
    if allowed_tool_keys is not None:
        conditions.append(ToolDefinition.tool_key.in_(allowed_tool_keys))
    with database.session() as session:
        definitions = list(
            session.scalars(
                select(ToolDefinition)
                .where(*conditions)
                .order_by(ToolDefinition.risk_level, ToolDefinition.tool_key)
            )
        )
    return ToolCatalogResponse(
        actor_key=actor.actor_key,
        permission_set_version=actor.permission_set_version,
        items=[_definition_view(item) for item in definitions],
        generated_at=datetime.now(UTC),
    )


async def invoke_tool(
    database: Database,
    settings: Settings,
    ai_provider: ResponsesAIProvider,
    actor: ActorContext,
    *,
    tool_key: str,
    parameters: dict[str, object],
    gateway_session_id: str | None = None,
    agent_run_id: str | None = None,
    session_permission_set_version: str | None = None,
    allowed_tool_keys: frozenset[str] | None = None,
) -> ToolInvokeResponse:
    del settings, ai_provider
    definition = _active_definition(database, actor.enterprise_id, tool_key)
    started_at = datetime.now(UTC)
    started = perf_counter()
    try:
        if allowed_tool_keys is not None and tool_key not in allowed_tool_keys:
            raise ApiProblem(
                status_code=403,
                code="mcp.tool_not_allowed",
                message="当前 MCP 会话未授权该工具",
                details={"tool_key": tool_key, "gateway_session_id": gateway_session_id},
            )
        parsed = _validate_input(definition.tool_key, parameters)
        if isinstance(parsed, (GetMetricInput, QueryCommerceFactsInput, QueryCustomer360Input)):
            require_selected_data_scope(database, actor, parsed.scope_key)
        scope_type, scope_id, resource_key = _authorization_target(definition, parsed, actor)
        require_permission(
            actor,
            definition.permission_key,
            database,
            resource_type=definition.resource_type,
            resource_key=resource_key,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        output = _dispatch_tool(
            database,
            definition.tool_key,
            parsed,
            enterprise_id=actor.enterprise_id,
            actor=actor,
        )
    except ApiProblem as exc:
        status = "denied" if exc.status_code == 403 else "failed"
        _record_invocation(
            database,
            definition,
            actor,
            parameters=parameters,
            output={},
            status=status,
            error_code=exc.code,
            started_at=started_at,
            duration_ms=_duration_ms(started),
            gateway_session_id=gateway_session_id,
            agent_run_id=agent_run_id,
            session_permission_set_version=session_permission_set_version,
        )
        raise
    except ValidationError as exc:
        problem = ApiProblem(
            status_code=422,
            code="tool.input_invalid",
            message="工具输入未通过已登记 Schema 验证",
            details={
                "tool_key": definition.tool_key,
                "issues": [
                    {
                        "location": [str(part) for part in issue["loc"]],
                        "type": issue["type"],
                        "message": issue["msg"],
                    }
                    for issue in exc.errors()
                ],
            },
        )
        _record_invocation(
            database,
            definition,
            actor,
            parameters=parameters,
            output={},
            status="failed",
            error_code=problem.code,
            started_at=started_at,
            duration_ms=_duration_ms(started),
            gateway_session_id=gateway_session_id,
            agent_run_id=agent_run_id,
            session_permission_set_version=session_permission_set_version,
        )
        raise problem from exc

    duration_ms = _duration_ms(started)
    invocation_id, finished_at = _record_invocation(
        database,
        definition,
        actor,
        parameters=parameters,
        output=output,
        status="succeeded",
        error_code=None,
        started_at=started_at,
        duration_ms=duration_ms,
        gateway_session_id=gateway_session_id,
        agent_run_id=agent_run_id,
        session_permission_set_version=session_permission_set_version,
    )
    return ToolInvokeResponse(
        invocation_id=invocation_id,
        tool=_definition_view(definition),
        actor_key=actor.actor_key,
        authentication_method=actor.authentication_method,
        permission_set_version=actor.permission_set_version,
        session_permission_set_version=session_permission_set_version,
        permission_set_version_changed=(
            session_permission_set_version is not None
            and session_permission_set_version != actor.permission_set_version
        ),
        gateway_session_id=gateway_session_id,
        agent_run_id=agent_run_id,
        status="succeeded",
        output=output,
        duration_ms=duration_ms,
        request_id=actor.request_id,
        run_id=actor.run_id,
        finished_at=finished_at,
    )


def tool_admin_overview(database: Database, *, enterprise_id: str) -> ToolAdminOverviewResponse:
    with database.session() as session:
        definitions = list(
            session.scalars(
                select(ToolDefinition)
                .where(ToolDefinition.enterprise_id == enterprise_id)
                .order_by(ToolDefinition.risk_level, ToolDefinition.tool_key)
            )
        )
        definition_by_id = {item.id: item for item in definitions}
        invocations = list(
            session.scalars(
                select(ToolInvocation)
                .where(ToolInvocation.enterprise_id == enterprise_id)
                .order_by(ToolInvocation.started_at.desc())
                .limit(100)
            )
        )
        principals = {
            item.id: item
            for item in session.scalars(select(Principal).where(
                Principal.id.in_({event.actor_principal_id for event in invocations})
            ))
        }
        status_rows = session.execute(
            select(ToolInvocation.status, func.count(ToolInvocation.id))
            .where(ToolInvocation.enterprise_id == enterprise_id)
            .group_by(ToolInvocation.status)
        ).all()
    counts = {str(key): int(value) for key, value in status_rows}
    return ToolAdminOverviewResponse(
        enterprise_id=enterprise_id,
        stats=ToolAdminStats(
            active_tools=sum(item.status == "active" for item in definitions),
            r0_tools=sum(item.risk_level == "R0" for item in definitions),
            invocations=sum(counts.values()),
            succeeded=counts.get("succeeded", 0),
            denied=counts.get("denied", 0),
            failed=counts.get("failed", 0),
        ),
        tools=[_definition_view(item) for item in definitions],
        recent_invocations=[
            ToolInvocationView(
                id=item.id,
                tool_key=item.tool_key,
                tool_version=item.tool_version,
                actor_name=(principals[item.actor_principal_id].display_name
                            if item.actor_principal_id in principals else "未知主体"),
                risk_level=definition_by_id[item.tool_definition_id].risk_level,
                permission_key=definition_by_id[item.tool_definition_id].permission_key,
                authentication_method=item.authentication_method,
                permission_set_version=item.permission_set_version,
                session_permission_set_version=item.session_permission_set_version,
                permission_set_version_changed=(
                    item.session_permission_set_version is not None
                    and item.session_permission_set_version != item.permission_set_version
                ),
                gateway_session_id=item.gateway_session_id,
                agent_run_id=item.agent_run_id,
                status=cast(Literal["succeeded", "denied", "failed"], item.status),
                error_code=item.error_code,
                duration_ms=item.duration_ms,
                request_id=item.request_id,
                run_id=item.run_id,
                input_parameters=item.input_parameters,
                output_summary=item.output_summary,
                started_at=item.started_at,
                finished_at=item.finished_at,
            )
            for item in invocations
        ],
        generated_at=datetime.now(UTC),
    )


def _active_definition(database: Database, enterprise_id: str, tool_key: str) -> ToolDefinition:
    with database.session() as session:
        definition = session.scalar(
            select(ToolDefinition)
            .where(
                ToolDefinition.enterprise_id == enterprise_id,
                ToolDefinition.tool_key == tool_key,
                ToolDefinition.status == "active",
            )
            .order_by(ToolDefinition.version.desc())
        )
    if definition is None:
        raise ApiProblem(
            status_code=404,
            code="tool.not_found",
            message="没有找到可调用的已登记工具",
            details={"tool_key": tool_key},
        )
    return definition


def _validate_input(tool_key: str, parameters: dict[str, object]) -> BaseModel:
    model = INPUT_MODELS.get(tool_key)
    if model is None:
        raise ApiProblem(
            status_code=409,
            code="tool.handler_unavailable",
            message="工具已登记但当前版本没有可用处理器",
            details={"tool_key": tool_key},
        )
    return model.model_validate(parameters)


def _authorization_target(
    definition: ToolDefinition,
    parsed: BaseModel,
    actor: ActorContext,
) -> tuple[str | None, str | None, str]:
    if definition.scope_resolver == "metric_snapshot_scope_key":
        metric_input = cast(GetMetricInput, parsed)
        selector = metric_input.metric_key or metric_input.query
        if metric_input.scope_key == "enterprise":
            return "enterprise", actor.enterprise_id, f"metric:enterprise:{selector}"
        return "store", metric_input.scope_key, f"metric:{metric_input.scope_key}:{selector}"
    if definition.scope_resolver == "commerce_scope_mapping":
        fact_input = cast(QueryCommerceFactsInput, parsed)
        if fact_input.scope_key == "enterprise":
            return "enterprise", actor.enterprise_id, "commerce-facts:enterprise"
        return "store", fact_input.scope_key, f"commerce-facts:{fact_input.scope_key}"
    if definition.scope_resolver == "customer_scope_mapping":
        customer_input = cast(QueryCustomer360Input, parsed)
        customer_suffix = (
            f":{customer_input.customer_key}" if customer_input.customer_key else ""
        )
        if customer_input.scope_key == "enterprise":
            return (
                "enterprise",
                actor.enterprise_id,
                f"customer-360:enterprise{customer_suffix}",
            )
        return (
            "store",
            customer_input.scope_key,
            f"customer-360:{customer_input.scope_key}{customer_suffix}",
        )
    query = str(getattr(parsed, "query", ""))
    return None, None, f"{definition.tool_key}:{query[:120]}"


def _dispatch_tool(
    database: Database,
    tool_key: str,
    parsed: BaseModel,
    *,
    enterprise_id: str,
    actor: ActorContext | None = None,
) -> dict[str, object]:
    if tool_key == "query_authoritative_orders":
        if actor is None or actor.enterprise_id != enterprise_id:
            raise ApiProblem(status_code=403, code="tool.scope_missing", message="缺少可信范围")
        order_input = cast(QueryAuthoritativeOrdersInput, parsed)
        return summarize_orders(database, build_scope_context(database, actor),
            order_input.date_from, order_input.date_to).model_dump(mode="json")
    if tool_key == "search_knowledge":
        knowledge_input = cast(SearchKnowledgeInput, parsed)
        response = search_evidence(
            database,
            knowledge_input.query,
            limit=knowledge_input.limit,
            enterprise_id=enterprise_id,
        )
        return response.model_dump(mode="json")
    if tool_key == "read_policy":
        policy_input = cast(ReadPolicyInput, parsed)
        response = search_evidence(
            database,
            policy_input.query,
            limit=policy_input.limit,
            enterprise_id=enterprise_id,
        )
        payload = response.model_dump(mode="json")
        if policy_input.policy_key:
            payload["items"] = [
                item
                for item in cast(list[dict[str, object]], payload["items"])
                if item.get("document_key") == policy_input.policy_key
            ]
        payload["policy_key"] = policy_input.policy_key
        return payload
    if tool_key == "get_metric":
        return _query_metrics(database, cast(GetMetricInput, parsed), enterprise_id=enterprise_id)
    if tool_key == "query_commerce_facts":
        fact_input = cast(QueryCommerceFactsInput, parsed)
        commerce_response = build_commerce_operations(
            database,
            scope_key=fact_input.scope_key,
            enterprise_id=enterprise_id,
        )
        payload = commerce_response.model_dump(mode="json")
        payload["exceptions"] = cast(list[object], payload["exceptions"])[: fact_input.limit]
        payload["recent_orders"] = cast(list[object], payload["recent_orders"])[
            : fact_input.limit
        ]
        return payload
    if tool_key == "query_customer_360":
        customer_input = cast(QueryCustomer360Input, parsed)
        if customer_input.customer_key:
            customer_detail = build_customer_detail(
                database,
                scope_key=customer_input.scope_key,
                customer_key=customer_input.customer_key,
                enterprise_id=enterprise_id,
                limit=customer_input.limit,
            )
            return customer_detail.model_dump(mode="json")
        customer_response = build_customer_360(
            database,
            scope_key=customer_input.scope_key,
            enterprise_id=enterprise_id,
            limit=customer_input.limit,
        )
        return customer_response.model_dump(mode="json")
    raise ApiProblem(
        status_code=409,
        code="tool.handler_unavailable",
        message="工具已登记但当前版本没有可用处理器",
        details={"tool_key": tool_key},
    )


def _query_metrics(
    database: Database,
    payload: GetMetricInput,
    *,
    enterprise_id: str,
) -> dict[str, object]:
    definition_conditions = [
        MetricDefinition.enterprise_id == enterprise_id,
        MetricDefinition.status.in_(("active", "published")),
    ]
    if payload.metric_key:
        definition_conditions.append(MetricDefinition.metric_key == payload.metric_key)
    if payload.query:
        pattern = f"%{payload.query.strip()}%"
        definition_conditions.append(
            or_(
                MetricDefinition.metric_key.ilike(pattern),
                MetricDefinition.label.ilike(pattern),
                MetricDefinition.description.ilike(pattern),
            )
        )
    with database.session() as session:
        definitions = list(
            session.scalars(
                select(MetricDefinition)
                .where(*definition_conditions)
                .order_by(MetricDefinition.label, MetricDefinition.version.desc())
                .limit(payload.limit)
            )
        )
    metric_keys = [item.metric_key for item in definitions]
    queried = query_metric_series(
        database,
        metric_keys=metric_keys,
        scope_key=payload.scope_key,
        days=payload.days,
        enterprise_id=enterprise_id,
    )
    series_by_key = {item.key: item for item in queried.series}
    return {
        "scope_key": payload.scope_key,
        "time_range": {
            "days": payload.days,
            "date_from": queried.date_from.isoformat() if queried.date_from else None,
            "date_to": queried.date_to.isoformat() if queried.date_to else None,
            "granularity": queried.granularity,
        },
        "items": [
            {
                "key": item.metric_key,
                "label": item.label,
                "description": item.description,
                "formula": item.formula_expression,
                "unit": item.unit,
                "dimensions": item.dimensions,
                "owner": item.owner,
                "version": item.version,
                "value": series_by_key[item.metric_key].latest_value
                if item.metric_key in series_by_key
                else None,
                "change_rate": (
                    series_by_key[item.metric_key].points[-1].change_rate
                    if item.metric_key in series_by_key and series_by_key[item.metric_key].points
                    else None
                ),
                "period_change_rate": series_by_key[item.metric_key].period_change_rate
                if item.metric_key in series_by_key
                else None,
                "as_of": (
                    series_by_key[item.metric_key].points[-1].as_of.isoformat()
                    if item.metric_key in series_by_key and series_by_key[item.metric_key].points
                    else None
                ),
                "series": [
                    point.model_dump(mode="json")
                    for point in series_by_key[item.metric_key].points
                ]
                if item.metric_key in series_by_key
                else [],
            }
            for item in definitions
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _duration_ms(started: float) -> int:
    return max(1, round((perf_counter() - started) * 1000))


def _record_invocation(
    database: Database,
    definition: ToolDefinition,
    actor: ActorContext,
    *,
    parameters: dict[str, object],
    output: dict[str, object],
    status: str,
    error_code: str | None,
    started_at: datetime,
    duration_ms: int,
    gateway_session_id: str | None,
    agent_run_id: str | None,
    session_permission_set_version: str | None,
) -> tuple[str, datetime]:
    invocation_id = f"tool_invocation_{uuid4().hex}"
    finished_at = datetime.now(UTC)
    serialized = json.dumps(output, ensure_ascii=False, sort_keys=True, default=str)
    items = output.get("items")
    item_count = len(items) if isinstance(items, list) else None
    summary: dict[str, object] = {
        "keys": sorted(output),
        "serialized_bytes": len(serialized.encode("utf-8")),
    }
    if item_count is not None:
        summary["item_count"] = item_count
    snapshot = actor.snapshot()
    used_scope = output.get("scope_snapshot")
    if (definition.tool_key == "query_authoritative_orders" and isinstance(used_scope, dict)
            and used_scope.get("schema_version") == 2):
        snapshot["scope_context"] = used_scope
        summary["definition_version"] = output.get("definition_version")
        summary["quality_flags"] = output.get("quality_flags")
    with database.session() as session:
        session.add(
            ToolInvocation(
                id=invocation_id,
                enterprise_id=actor.enterprise_id,
                tool_definition_id=definition.id,
                tool_key=definition.tool_key,
                tool_version=definition.version,
                actor_principal_id=actor.principal_id,
                actor_snapshot=snapshot,
                gateway_session_id=gateway_session_id,
                agent_run_id=agent_run_id,
                authentication_method=actor.authentication_method,
                permission_set_version=actor.permission_set_version,
                session_permission_set_version=session_permission_set_version,
                request_id=actor.request_id,
                run_id=actor.run_id,
                input_parameters=parameters,
                output_summary=summary,
                status=status,
                error_code=error_code,
                duration_ms=duration_ms,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
        session.commit()
    return invocation_id, finished_at
