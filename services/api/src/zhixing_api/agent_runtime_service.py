from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from zhixing_agent_runtime import AgentRunEvent, AgentRunHandle, AgentRunSpec

from zhixing_api.actor_context import ActorContext
from zhixing_api.data_models import (
    AgentRuntimeApproval,
    AgentRuntimeEventRecord,
    AgentRuntimeSession,
    AgentRuntimeTurn,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem

_URL_PATTERN = re.compile(r"https?://[^\s，。；;]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"bearer\s+[a-z0-9._-]+", re.IGNORECASE)
_SECRET_PATTERN = re.compile(
    r"(?:sk|key|token|secret|password)[-_=:\s]+[a-z0-9._/-]{8,}",
    re.IGNORECASE,
)
_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "run.started": frozenset(
        {
            "runtime_thread_id",
            "recovered",
            "allowed_tool_keys",
            "permission_set_version",
        }
    ),
    "turn.started": frozenset({"threadId", "turnId", "turn_id", "turn_status"}),
    "tool.started": frozenset({"item_id", "server", "tool", "status"}),
    "tool.completed": frozenset({"item_id", "server", "tool", "status"}),
    "tool.failed": frozenset({"item_id", "server", "tool", "status"}),
    "approval.required": frozenset({"method", "item_id"}),
    "approval.resolved": frozenset({"method", "decision"}),
}
_TERMINAL_EVENTS = frozenset({"run.completed", "run.failed", "run.cancelled"})


def validate_runtime_scope_for_resume(
    stored_spec: dict[str, object], current_scope: dict[str, object],
) -> None:
    saved = stored_spec.get("scope_context")
    if (not isinstance(saved, dict)
            or saved.get("schema_version") != 2
            or saved.get("enterprise_id") != current_scope.get("enterprise_id")
            or not saved.get("scope_version")
            or saved.get("scope_version") != current_scope.get("scope_version")):
        raise ApiProblem(status_code=409, code="runtime.scope_changed",
                         message="数据范围或权限已变化，请新建会话")


def create_runtime_session(
    database: Database,
    actor: ActorContext,
    *,
    agent_run_id: str,
    handle: AgentRunHandle,
    spec: AgentRunSpec,
    mcp_gateway_session_id: str | None,
    model: str | None,
) -> tuple[AgentRuntimeSession, AgentRuntimeTurn]:
    now = datetime.now(UTC)
    runtime_session = AgentRuntimeSession(
        id=f"agent_runtime_session_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        agent_run_id=agent_run_id,
        runtime_key=handle.runtime_key,
        runtime_thread_id=handle.runtime_thread_id,
        runtime_session_id=handle.runtime_session_id,
        runtime_spec=_serialize_runtime_spec(spec),
        mcp_gateway_session_id=mcp_gateway_session_id,
        status="running",
        version=1,
        last_event_sequence=0,
        failure_code=None,
        failure_message=None,
        request_id=actor.request_id,
        run_id=actor.run_id,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )
    runtime_turn = _new_turn(
        runtime_session,
        agent_run_id=agent_run_id,
        mcp_gateway_session_id=mcp_gateway_session_id,
        runtime_turn_id=handle.runtime_turn_id,
        turn_number=1,
        model=model,
        request_id=actor.request_id,
        run_id=actor.run_id,
        started_at=now,
    )
    with database.session() as session:
        session.add(runtime_session)
        session.add(runtime_turn)
        session.commit()
        session.refresh(runtime_session)
        session.refresh(runtime_turn)
    return runtime_session, runtime_turn


def begin_runtime_turn(
    database: Database,
    actor: ActorContext,
    *,
    runtime_session_id: str,
    agent_run_id: str,
    mcp_gateway_session_id: str | None,
    handle: AgentRunHandle,
    model: str | None,
) -> AgentRuntimeTurn:
    now = datetime.now(UTC)
    with database.session() as session:
        runtime_session = session.get(AgentRuntimeSession, runtime_session_id)
        if runtime_session is None:
            raise LookupError("没有找到 Agent Runtime 会话")
        if runtime_session.enterprise_id != actor.enterprise_id:
            raise LookupError("没有找到 Agent Runtime 会话")
        next_turn_number = int(
            session.scalar(
                select(func.max(AgentRuntimeTurn.turn_number)).where(
                    AgentRuntimeTurn.runtime_session_id == runtime_session_id
                )
            )
            or 0
        ) + 1
        runtime_turn = _new_turn(
            runtime_session,
            agent_run_id=agent_run_id,
            mcp_gateway_session_id=mcp_gateway_session_id,
            runtime_turn_id=handle.runtime_turn_id,
            turn_number=next_turn_number,
            model=model,
            request_id=actor.request_id,
            run_id=actor.run_id,
            started_at=now,
        )
        runtime_session.status = "running"
        runtime_session.failure_code = None
        runtime_session.failure_message = None
        runtime_session.completed_at = None
        runtime_session.updated_at = now
        runtime_session.version += 1
        session.add(runtime_turn)
        session.commit()
        session.refresh(runtime_turn)
        return runtime_turn


def _serialize_runtime_spec(spec: AgentRunSpec) -> dict[str, object]:
    """Persist only data needed to construct a future resume request.

    Credentials are intentionally excluded. They are short-lived and must be
    re-issued after a restart from the current ActorContext.
    """
    return {
        "run_id": spec.run_id,
        "actor": {
            "enterprise_id": spec.actor.enterprise_id,
            "principal_id": spec.actor.principal_id,
            "actor_key": spec.actor.actor_key,
            "permission_set_version": spec.actor.permission_set_version,
            "authentication_method": spec.actor.authentication_method,
        },
        "input_text": spec.input_text,
        "instructions": spec.instructions,
        "cwd": spec.cwd,
        "model": spec.model,
        "allowed_tool_keys": list(spec.allowed_tool_keys),
        "output_schema": spec.output_schema,
        "metadata": dict(spec.metadata),
        "scope_context": spec.scope_context,
    }


def append_runtime_event(
    database: Database,
    *,
    runtime_session_id: str,
    runtime_turn_id: str,
    event: AgentRunEvent,
) -> AgentRuntimeEventRecord:
    with database.session() as session:
        runtime_session = session.get(AgentRuntimeSession, runtime_session_id)
        runtime_turn = session.get(AgentRuntimeTurn, runtime_turn_id)
        if runtime_session is None or runtime_turn is None:
            raise LookupError("没有找到 Agent Runtime 运行映射")
        if runtime_turn.runtime_session_id != runtime_session.id:
            raise ValueError("Runtime Turn 不属于指定会话")

        runtime_session.last_event_sequence += 1
        runtime_session.updated_at = event.occurred_at
        runtime_session.version += 1
        record = AgentRuntimeEventRecord(
            id=f"agent_runtime_event_{uuid4().hex}",
            enterprise_id=runtime_session.enterprise_id,
            runtime_session_id=runtime_session.id,
            runtime_turn_id=runtime_turn.id,
            sequence=runtime_session.last_event_sequence,
            runtime_sequence=event.sequence,
            event_type=event.event_type,
            status=event.status,
            event_payload=_normalized_payload(event),
            occurred_at=event.occurred_at,
        )
        _apply_event_status(runtime_session, runtime_turn, event)
        session.add(record)
        if event.event_type == "approval.required":
            allowed_tools = event.payload.get("allowed_tool_keys", [])
            session.add(AgentRuntimeApproval(
                id=f"agent_runtime_approval_{uuid4().hex}",
                enterprise_id=runtime_session.enterprise_id,
                runtime_session_id=runtime_session.id,
                runtime_turn_id=runtime_turn.id,
                agent_run_id=runtime_turn.agent_run_id,
                request_method=str(event.payload.get("method", "unknown")),
                item_id=str(event.payload.get("item_id", "")) or None,
                skill_key=None,
                skill_version=None,
                tool_keys=(
                    [str(item) for item in allowed_tools]
                    if isinstance(allowed_tools, list)
                    else []
                ),
                status="pending",
                decision=None,
                requested_at=event.occurred_at,
                decided_at=None,
                decided_by_principal_id=None,
                request_id=runtime_session.request_id,
                run_id=runtime_session.run_id,
            ))
        session.commit()
        session.refresh(record)
        return record


def mark_runtime_session_failed(
    database: Database,
    *,
    runtime_session_id: str,
    runtime_turn_id: str,
    error_code: str,
    error_message: str,
) -> None:
    now = datetime.now(UTC)
    with database.session() as session:
        runtime_session = session.get(AgentRuntimeSession, runtime_session_id)
        runtime_turn = session.get(AgentRuntimeTurn, runtime_turn_id)
        if runtime_session is None or runtime_turn is None:
            return
        if runtime_session.status == "cancelled" or runtime_turn.status == "cancelled":
            return
        message = sanitize_runtime_error(error_message)
        runtime_session.status = "failed"
        runtime_session.failure_code = error_code[:120]
        runtime_session.failure_message = message
        runtime_session.updated_at = now
        runtime_session.completed_at = now
        runtime_session.version += 1
        runtime_turn.status = "failed"
        runtime_turn.failure_code = error_code[:120]
        runtime_turn.failure_message = message
        runtime_turn.completed_at = now
        session.commit()


def reconcile_orphaned_runtime_sessions(database: Database) -> int:
    """Close Runtime records whose owning API process disappeared.

    Codex approval requests are backed by an in-process Future. After an API
    restart that Future and the child process no longer exist, so keeping the
    database row in ``running`` or ``waiting_approval`` would be misleading.
    This reconciliation is deliberately fail-closed; a later explicit resume
    flow can create a new Runtime turn from the persisted thread.
    """
    now = datetime.now(UTC)
    with database.session() as session:
        orphaned = list(
            session.scalars(
                select(AgentRuntimeSession).where(
                    AgentRuntimeSession.status.in_(
                        ("starting", "running", "waiting_approval")
                    )
                )
            )
        )
        if not orphaned:
            return 0
        session_ids = [item.id for item in orphaned]
        turns = list(
            session.scalars(
                select(AgentRuntimeTurn).where(
                    AgentRuntimeTurn.runtime_session_id.in_(session_ids),
                    AgentRuntimeTurn.status.in_(
                        ("starting", "running", "waiting_approval")
                    ),
                )
            )
        )
        approvals = list(
            session.scalars(
                select(AgentRuntimeApproval).where(
                    AgentRuntimeApproval.runtime_session_id.in_(session_ids),
                    AgentRuntimeApproval.status == "pending",
                )
            )
        )
        for runtime_session in orphaned:
            runtime_session.status = "failed"
            runtime_session.failure_code = "runtime_process_restarted"
            runtime_session.failure_message = (
                "API 重启后原 Runtime 进程已退出，需要人工恢复或重新运行"
            )
            runtime_session.updated_at = now
            runtime_session.completed_at = now
            runtime_session.version += 1
        for runtime_turn in turns:
            runtime_turn.status = "failed"
            runtime_turn.failure_code = "runtime_process_restarted"
            runtime_turn.failure_message = (
                "API 重启后原 Runtime 进程已退出，需要人工恢复或重新运行"
            )
            runtime_turn.completed_at = now
        for approval in approvals:
            approval.status = "expired"
            approval.decision = "expired"
            approval.decided_at = now
        session.commit()
        return len(orphaned)


def sanitize_runtime_error(value: str) -> str:
    redacted = _URL_PATTERN.sub("[redacted-url]", value)
    redacted = _BEARER_PATTERN.sub("Bearer [redacted]", redacted)
    redacted = _SECRET_PATTERN.sub("[redacted-secret]", redacted)
    return redacted[:500]


def _new_turn(
    runtime_session: AgentRuntimeSession,
    *,
    agent_run_id: str,
    mcp_gateway_session_id: str | None,
    runtime_turn_id: str,
    turn_number: int,
    model: str | None,
    request_id: str,
    run_id: str,
    started_at: datetime,
) -> AgentRuntimeTurn:
    return AgentRuntimeTurn(
        id=f"agent_runtime_turn_{uuid4().hex}",
        enterprise_id=runtime_session.enterprise_id,
        runtime_session_id=runtime_session.id,
        agent_run_id=agent_run_id,
        mcp_gateway_session_id=mcp_gateway_session_id,
        runtime_turn_id=runtime_turn_id,
        turn_number=turn_number,
        status="running",
        model=model,
        failure_code=None,
        failure_message=None,
        request_id=request_id,
        run_id=run_id,
        started_at=started_at,
        completed_at=None,
    )


def _normalized_payload(event: AgentRunEvent) -> dict[str, object]:
    allowed_keys = _PAYLOAD_KEYS.get(event.event_type, frozenset())
    payload = {
        key: value
        for key, value in event.payload.items()
        if key in allowed_keys and _safe_payload_value(value)
    }
    if event.event_type in {"run.failed", "run.warning"} and event.message:
        payload["error" if event.event_type == "run.failed" else "warning"] = (
            sanitize_runtime_error(event.message)
        )
    return payload


def _safe_payload_value(value: object) -> bool:
    if value is None or isinstance(value, (bool, int, float)):
        return True
    if isinstance(value, str):
        return len(value) <= 500
    if isinstance(value, list):
        return len(value) <= 32 and all(
            isinstance(item, str) and len(item) <= 160 for item in value
        )
    return False


def _apply_event_status(
    runtime_session: AgentRuntimeSession,
    runtime_turn: AgentRuntimeTurn,
    event: AgentRunEvent,
) -> None:
    if event.event_type in {"run.started", "turn.started"}:
        runtime_session.status = "running"
        runtime_turn.status = "running"
        return
    if event.event_type == "approval.required":
        runtime_session.status = "waiting_approval"
        runtime_turn.status = "waiting_approval"
        return
    if event.event_type == "approval.resolved":
        runtime_session.status = "running"
        runtime_turn.status = "running"
        return
    if event.event_type not in _TERMINAL_EVENTS:
        return
    runtime_session.status = event.status
    runtime_session.completed_at = event.occurred_at
    runtime_turn.status = event.status
    runtime_turn.completed_at = event.occurred_at
    if event.event_type == "run.failed":
        message = sanitize_runtime_error(event.message or "Codex Runtime 运行失败")
        runtime_session.failure_code = "runtime_turn_failed"
        runtime_session.failure_message = message
        runtime_turn.failure_code = "runtime_turn_failed"
        runtime_turn.failure_message = message
