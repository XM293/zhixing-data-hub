from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

RuntimeStatus = Literal[
    "starting",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
]
RuntimeEventType = Literal[
    "run.started",
    "turn.started",
    "message.delta",
    "message.completed",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "approval.required",
    "approval.resolved",
    "run.warning",
    "run.completed",
    "run.failed",
    "run.cancelled",
]


class AgentRuntimeError(RuntimeError):
    pass


class AgentRunNotFound(AgentRuntimeError):
    pass


class AgentRunConflict(AgentRuntimeError):
    pass


class AgentRunCancelled(AgentRuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AgentActor:
    enterprise_id: str
    principal_id: str
    actor_key: str
    permission_set_version: str
    authentication_method: str


@dataclass(frozen=True, slots=True)
class AgentRunSpec:
    run_id: str
    actor: AgentActor
    input_text: str
    instructions: str
    cwd: str
    model: str | None = None
    allowed_tool_keys: tuple[str, ...] = ()
    output_schema: dict[str, object] | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    scope_context: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id 不能为空")
        if not self.input_text.strip():
            raise ValueError("input_text 不能为空")
        if not self.instructions.strip():
            raise ValueError("instructions 不能为空")
        if len(self.allowed_tool_keys) != len(set(self.allowed_tool_keys)):
            raise ValueError("allowed_tool_keys 不能重复")
        if self.scope_context is not None and (
            self.scope_context.get("schema_version") != 2
            or self.scope_context.get("enterprise_id") != self.actor.enterprise_id
        ):
            raise ValueError("ScopeContext v2 必须与当前 Actor 法人一致")


@dataclass(frozen=True, slots=True)
class RuntimeCredentials:
    mcp_session_token: str | None = field(default=None, repr=False, compare=False)
    mcp_client_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentRunHandle:
    run_id: str
    runtime_key: str
    runtime_thread_id: str
    runtime_session_id: str | None
    runtime_turn_id: str
    status: RuntimeStatus


@dataclass(frozen=True, slots=True)
class AgentRunEvent:
    run_id: str
    sequence: int
    event_type: RuntimeEventType
    status: RuntimeStatus
    occurred_at: datetime
    message: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


class AgentRuntime(Protocol):
    runtime_key: str

    async def start(
        self,
        spec: AgentRunSpec,
        credentials: RuntimeCredentials | None = None,
    ) -> AgentRunHandle: ...

    async def resume(
        self,
        run_id: str,
        input_text: str,
        credentials: RuntimeCredentials | None = None,
        *,
        runtime_thread_id: str | None = None,
        spec: AgentRunSpec | None = None,
    ) -> AgentRunHandle: ...

    def stream(self, run_id: str) -> AsyncIterator[AgentRunEvent]: ...

    async def cancel(self, run_id: str) -> None: ...

    async def resolve_approval(
        self, run_id: str, decision: Literal["approve", "decline"]
    ) -> None: ...

    async def release(self, run_id: str) -> None: ...

    async def close(self) -> None: ...
