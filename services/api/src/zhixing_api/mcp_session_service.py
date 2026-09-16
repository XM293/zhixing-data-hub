from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from typing import Literal, cast
from uuid import uuid4

from fastapi import Request
from sqlalchemy import select

from zhixing_api.actor_context import (
    ActorContext,
    ActorScope,
    actor_scope_allows,
    require_permission,
    resolve_database_actor,
    resolve_development_actor,
)
from zhixing_api.data_models import (
    AgentRun,
    MCPGatewaySession,
    MCPGatewaySessionEvent,
    ToolDefinition,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.mcp_schemas import (
    McpScopeConstraint,
    McpSessionCreateRequest,
    McpSessionCreateResponse,
    McpSessionListResponse,
    McpSessionRevokeRequest,
    McpSessionView,
)
from zhixing_api.scope_context import build_scope_context
from zhixing_api.workspace_service import actor_snapshot_with_workspace, resolve_workspace_for_actor

MCP_SESSION_HEADER = "X-Zhixing-MCP-Session"
MCP_CLIENT_ID_HEADER = "X-Zhixing-MCP-Client-ID"


@dataclass(frozen=True, slots=True)
class ToolRequestContext:
    actor: ActorContext
    gateway_session_id: str | None = None
    agent_run_id: str | None = None
    allowed_tool_keys: frozenset[str] | None = None
    session_permission_set_version: str | None = None


def create_mcp_session(
    database: Database,
    actor: ActorContext,
    payload: McpSessionCreateRequest,
) -> McpSessionCreateResponse:
    actor = _selected_session_actor(database, actor, actor.scope_selection)
    resolve_workspace_for_actor(actor, payload.workspace_key)
    require_permission(
        actor,
        "platform.navigation.read",
        database,
        resource_type="mcp.gateway_session",
        resource_key=actor.principal_id,
    )
    definitions = _session_tool_definitions(database, actor, payload.allowed_tool_keys)
    for permission_key in sorted({item.permission_key for item in definitions}):
        require_permission(
            actor,
            permission_key,
            database,
            resource_type="mcp.gateway_session",
            resource_key=f"{payload.client_id}:{permission_key}",
        )
    _validate_scope_constraints(actor, payload.scope_constraints)
    _validate_agent_run(database, actor, payload.agent_run_id)

    now = datetime.now(UTC)
    raw_token = token_urlsafe(48)
    gateway_session = MCPGatewaySession(
        id=f"mcp_session_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        user_account_id=actor.user_account_id,
        principal_id=actor.principal_id,
        client_id=payload.client_id,
        session_token_hash=sha256(raw_token.encode()).hexdigest(),
        allowed_tool_keys=payload.allowed_tool_keys,
        scope_constraints=[item.model_dump(mode="json") for item in payload.scope_constraints],
        issued_permission_set_version=actor.permission_set_version,
        actor_snapshot={
            **actor_snapshot_with_workspace(actor, payload.workspace_key),
            "scope_context": build_scope_context(database, actor).snapshot(),
        },
        agent_run_id=payload.agent_run_id,
        status="active",
        issued_at=now,
        expires_at=now + timedelta(seconds=payload.ttl_seconds),
        last_seen_at=None,
        revoked_at=None,
        revoked_by_principal_id=None,
        revoke_reason=None,
        request_id=actor.request_id,
        run_id=actor.run_id,
    )
    event = _session_event(
        gateway_session,
        actor,
        event_type="issued",
        reason="trusted_mcp_session_issued",
    )
    with database.session() as session:
        session.add(gateway_session)
        session.add(event)
        session.commit()
    return McpSessionCreateResponse(
        session_token=raw_token,
        session=_session_view(gateway_session, actor.permission_set_version),
    )


def list_mcp_sessions(database: Database, actor: ActorContext) -> McpSessionListResponse:
    require_permission(
        actor,
        "platform.navigation.read",
        database,
        resource_type="mcp.gateway_session",
        resource_key=actor.principal_id,
    )
    _expire_owned_sessions(database, actor)
    with database.session() as session:
        items = list(
            session.scalars(
                select(MCPGatewaySession)
                .where(
                    MCPGatewaySession.enterprise_id == actor.enterprise_id,
                    MCPGatewaySession.principal_id == actor.principal_id,
                )
                .order_by(MCPGatewaySession.issued_at.desc())
                .limit(100)
            )
        )
    return McpSessionListResponse(
        items=[_session_view(item, actor.permission_set_version) for item in items],
        generated_at=datetime.now(UTC),
    )


def revoke_mcp_session(
    database: Database,
    actor: ActorContext,
    session_id: str,
    payload: McpSessionRevokeRequest,
) -> McpSessionView:
    with database.session() as session:
        gateway_session = session.get(MCPGatewaySession, session_id)
        if gateway_session is None or gateway_session.enterprise_id != actor.enterprise_id:
            raise ApiProblem(
                status_code=404,
                code="mcp.session_not_found",
                message="没有找到 MCP 会话",
            )
        owns_session = gateway_session.principal_id == actor.principal_id
    require_permission(
        actor,
        "platform.navigation.read" if owns_session else "identity.access.manage",
        database,
        resource_type="mcp.gateway_session",
        resource_key=session_id,
        scope_type="enterprise" if not owns_session else None,
        scope_id=actor.enterprise_id if not owns_session else None,
    )
    with database.session() as session:
        gateway_session = session.get(MCPGatewaySession, session_id)
        assert gateway_session is not None
        if gateway_session.status == "active":
            gateway_session.status = "revoked"
            gateway_session.revoked_at = datetime.now(UTC)
            gateway_session.revoked_by_principal_id = actor.principal_id
            gateway_session.revoke_reason = payload.reason
            session.add(
                _session_event(
                    gateway_session,
                    actor,
                    event_type="revoked",
                    reason=payload.reason,
                )
            )
            session.commit()
        session.refresh(gateway_session)
        return _session_view(gateway_session, actor.permission_set_version)


def resolve_tool_request_context(request: Request) -> ToolRequestContext:
    raw_token = request.headers.get(MCP_SESSION_HEADER, "").strip()
    if not raw_token:
        return ToolRequestContext(actor=resolve_development_actor(request))
    client_id = request.headers.get(MCP_CLIENT_ID_HEADER, "").strip().casefold()
    if not client_id:
        raise _invalid_session()
    return resolve_mcp_session(
        request.app.state.database,
        raw_token=raw_token,
        client_id=client_id,
        request_id=getattr(request.state, "request_id", "req_unavailable"),
        run_id=getattr(request.state, "run_id", "run_unavailable"),
    )


def resolve_mcp_session(
    database: Database,
    *,
    raw_token: str,
    client_id: str,
    request_id: str,
    run_id: str,
) -> ToolRequestContext:
    token_hash = sha256(raw_token.encode()).hexdigest()
    now = datetime.now(UTC)
    with database.session() as session:
        gateway_session = session.scalar(
            select(MCPGatewaySession).where(
                MCPGatewaySession.session_token_hash == token_hash,
                MCPGatewaySession.client_id == client_id,
            )
        )
        if gateway_session is None:
            raise _invalid_session()
        if gateway_session.status != "active":
            raise _invalid_session()
        if _as_utc(gateway_session.expires_at) <= now:
            gateway_session.status = "expired"
            session.add(
                MCPGatewaySessionEvent(
                    id=f"mcp_session_event_{uuid4().hex}",
                    enterprise_id=gateway_session.enterprise_id,
                    gateway_session_id=gateway_session.id,
                    actor_principal_id=gateway_session.principal_id,
                    event_type="expired",
                    reason="session_ttl_elapsed",
                    permission_set_version=gateway_session.issued_permission_set_version,
                    request_id=request_id,
                    run_id=run_id,
                    occurred_at=now,
                )
            )
            session.commit()
            raise _invalid_session()
        account = session.get(UserAccount, gateway_session.user_account_id)
        if account is None:
            raise _invalid_session()
        login_name = account.local_login_name
        user_account_id = gateway_session.user_account_id
        session_id = gateway_session.id
        enterprise_id = gateway_session.enterprise_id
        principal_id = gateway_session.principal_id
        allowed_tool_keys = frozenset(gateway_session.allowed_tool_keys)
        scope_constraints = list(gateway_session.scope_constraints)
        issued_permission_set_version = gateway_session.issued_permission_set_version
        agent_run_id = gateway_session.agent_run_id
        snapshot = gateway_session.actor_snapshot or {}
        selection = snapshot.get("scope_selection")

    current_actor = resolve_database_actor(
        database,
        login_name=login_name,
        user_account_id=user_account_id,
        enterprise_id=enterprise_id,
        request_id=request_id,
        run_id=run_id,
        authentication_method="mcp-session",
    )
    if current_actor.enterprise_id != enterprise_id or current_actor.principal_id != principal_id:
        raise _invalid_session()
    current_actor = _selected_session_actor(
        database, current_actor, selection if isinstance(selection, dict) else None,
    )
    effective_actor = _constrain_actor(current_actor, scope_constraints)
    with database.session() as session:
        gateway_session = session.get(MCPGatewaySession, session_id)
        if gateway_session is None or gateway_session.status != "active":
            raise _invalid_session()
        gateway_session.last_seen_at = now
        session.commit()
    return ToolRequestContext(
        actor=effective_actor,
        gateway_session_id=session_id,
        agent_run_id=agent_run_id,
        allowed_tool_keys=allowed_tool_keys,
        session_permission_set_version=issued_permission_set_version,
    )


def _session_tool_definitions(
    database: Database,
    actor: ActorContext,
    tool_keys: list[str],
) -> list[ToolDefinition]:
    with database.session() as session:
        definitions = list(
            session.scalars(
                select(ToolDefinition).where(
                    ToolDefinition.enterprise_id == actor.enterprise_id,
                    ToolDefinition.tool_key.in_(tool_keys),
                    ToolDefinition.status == "active",
                )
            )
        )
    if {item.tool_key for item in definitions} != set(tool_keys):
        raise ApiProblem(
            status_code=422,
            code="mcp.tool_set_invalid",
            message="MCP 会话包含未发布的工具",
        )
    unsupported = sorted(
        item.tool_key for item in definitions if item.risk_level not in {"R0", "R1"}
    )
    if unsupported:
        raise ApiProblem(
            status_code=409,
            code="mcp.tool_risk_not_supported",
            message="当前 MCP 会话只允许只读和低风险工具",
            details={"tool_keys": unsupported},
        )
    return definitions


def _validate_scope_constraints(
    actor: ActorContext,
    constraints: list[McpScopeConstraint],
) -> None:
    for constraint in constraints:
        for scope_id in constraint.scope_ids:
            if constraint.scope_type == "enterprise" and scope_id != actor.enterprise_id:
                allowed = False
            elif constraint.scope_type == "self" and scope_id != actor.principal_id:
                allowed = False
            else:
                allowed = actor_scope_allows(
                    actor,
                    scope_type=constraint.scope_type,
                    scope_id=scope_id,
                )
            if not allowed:
                raise ApiProblem(
                    status_code=403,
                    code="authorization.scope_denied",
                    message="当前身份不能把该数据范围授予 MCP 会话",
                    details={"scope_type": constraint.scope_type, "scope_id": scope_id},
                )


def _validate_agent_run(database: Database, actor: ActorContext, agent_run_id: str | None) -> None:
    if agent_run_id is None:
        return
    with database.session() as session:
        agent_run = session.get(AgentRun, agent_run_id)
    if agent_run is None or agent_run.enterprise_id != actor.enterprise_id:
        raise ApiProblem(status_code=404, code="agent_run.not_found", message="没有找到智能体运行")
    if agent_run.actor_principal_id != actor.principal_id:
        raise ApiProblem(
            status_code=403,
            code="authorization.agent_run_denied",
            message="当前身份不能为该智能体运行签发 MCP 会话",
        )


def _selected_session_actor(
    database: Database, actor: ActorContext, selection: dict[str, object] | None,
) -> ActorContext:
    if not selection:
        return actor
    # Revalidate the issued selection against current membership and explicit denials.
    scope = build_scope_context(database, actor, selection=selection)
    selected_actor = replace(actor, scope_selection=selection)
    dimensions = {
        "business_unit": scope.business_unit_ids,
        "store": scope.store_ids,
        "warehouse": scope.warehouse_ids,
    }
    if scope.scope_level not in dimensions:
        return selected_actor
    kinds = dimensions if scope.scope_level == "business_unit" else {
        scope.scope_level: dimensions[scope.scope_level],
    }
    scopes = [item for item in actor.scopes if item.effect == "deny"]
    scopes.extend(ActorScope(kind, tuple(ids), "allow") for kind, ids in kinds.items() if ids)
    return replace(selected_actor, scopes=tuple(scopes))


def _constrain_actor(
    actor: ActorContext,
    constraints: list[dict[str, object]],
) -> ActorContext:
    if not constraints:
        return actor
    effective_scopes: list[ActorScope] = [scope for scope in actor.scopes if scope.effect == "deny"]
    for item in constraints:
        constraint = McpScopeConstraint.model_validate(item)
        scope_type = constraint.scope_type
        allowed_ids = tuple(
            scope_id
            for scope_id in constraint.scope_ids
            if actor_scope_allows(actor, scope_type=scope_type, scope_id=scope_id)
        )
        if allowed_ids:
            effective_scopes.append(
                ActorScope(scope_type=scope_type, scope_ids=allowed_ids, effect="allow")
            )
    return replace(actor, scopes=tuple(effective_scopes))


def _expire_owned_sessions(database: Database, actor: ActorContext) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        items = list(
            session.scalars(
                select(MCPGatewaySession).where(
                    MCPGatewaySession.enterprise_id == actor.enterprise_id,
                    MCPGatewaySession.principal_id == actor.principal_id,
                    MCPGatewaySession.status == "active",
                    MCPGatewaySession.expires_at <= now,
                )
            )
        )
        for item in items:
            item.status = "expired"
            session.add(
                _session_event(
                    item,
                    actor,
                    event_type="expired",
                    reason="session_ttl_elapsed",
                )
            )
        if items:
            session.commit()


def _session_view(item: MCPGatewaySession, current_version: str) -> McpSessionView:
    snapshot = item.actor_snapshot if isinstance(item.actor_snapshot, dict) else {}
    workspace_key = snapshot.get("workspace_key")
    return McpSessionView(
        session_id=item.id,
        client_id=item.client_id,
        principal_id=item.principal_id,
        agent_run_id=item.agent_run_id,
        workspace_key=workspace_key if isinstance(workspace_key, str) else None,
        allowed_tool_keys=list(item.allowed_tool_keys),
        scope_constraints=[
            McpScopeConstraint.model_validate(value) for value in item.scope_constraints
        ],
        issued_permission_set_version=item.issued_permission_set_version,
        current_permission_set_version=current_version,
        permission_set_version_changed=item.issued_permission_set_version != current_version,
        status=cast(Literal["active", "expired", "revoked"], item.status),
        issued_at=item.issued_at,
        expires_at=item.expires_at,
        last_seen_at=item.last_seen_at,
        revoked_at=item.revoked_at,
    )


def _session_event(
    item: MCPGatewaySession,
    actor: ActorContext,
    *,
    event_type: str,
    reason: str,
) -> MCPGatewaySessionEvent:
    return MCPGatewaySessionEvent(
        id=f"mcp_session_event_{uuid4().hex}",
        enterprise_id=item.enterprise_id,
        gateway_session_id=item.id,
        actor_principal_id=actor.principal_id,
        event_type=event_type,
        reason=reason,
        permission_set_version=actor.permission_set_version,
        request_id=actor.request_id,
        run_id=actor.run_id,
        occurred_at=datetime.now(UTC),
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _invalid_session() -> ApiProblem:
    return ApiProblem(
        status_code=401,
        code="mcp.session_invalid",
        message="MCP 会话无效或已失效",
    )
