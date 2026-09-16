from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from zhixing_agent_runtime.contracts import (
    AgentRunConflict,
    AgentRunEvent,
    AgentRunHandle,
    AgentRunNotFound,
    AgentRunSpec,
    RuntimeCredentials,
    RuntimeEventType,
    RuntimeStatus,
)


@dataclass(slots=True)
class _FakeSession:
    spec: AgentRunSpec
    thread_id: str
    turn_number: int = 1
    status: RuntimeStatus = "starting"
    sequence: int = 0
    queue: asyncio.Queue[AgentRunEvent | None] = field(default_factory=asyncio.Queue)
    task: asyncio.Task[None] | None = None


class FakeAgentRuntime:
    runtime_key = "fake"

    def __init__(
        self,
        response_factory: Callable[[AgentRunSpec, str], str] | None = None,
        *,
        delay_seconds: float = 0,
    ) -> None:
        self._response_factory = response_factory or (
            lambda spec, value: f"{spec.actor.actor_key}: {value}"
        )
        self._delay_seconds = delay_seconds
        self._sessions: dict[str, _FakeSession] = {}

    async def start(
        self,
        spec: AgentRunSpec,
        credentials: RuntimeCredentials | None = None,
    ) -> AgentRunHandle:
        del credentials
        if spec.run_id in self._sessions:
            raise AgentRunConflict(f"运行已存在: {spec.run_id}")
        session = _FakeSession(spec=spec, thread_id=f"fake-thread-{spec.run_id}")
        self._sessions[spec.run_id] = session
        session.task = asyncio.create_task(self._execute(session, spec.input_text))
        return self._handle(session)

    async def resume(
        self,
        run_id: str,
        input_text: str,
        credentials: RuntimeCredentials | None = None,
        *,
        runtime_thread_id: str | None = None,
        spec: AgentRunSpec | None = None,
    ) -> AgentRunHandle:
        del credentials
        session = self._sessions.get(run_id)
        if session is None:
            if spec is None or not runtime_thread_id:
                raise AgentRunNotFound(f"没有找到运行: {run_id}")
            if spec.run_id != run_id:
                raise ValueError("恢复规格与运行标识不一致")
            session = _FakeSession(
                spec=spec,
                thread_id=runtime_thread_id,
                turn_number=0,
                status="completed",
            )
            self._sessions[run_id] = session
        if session.status in {"starting", "running", "waiting_approval"}:
            raise AgentRunConflict("运行仍在执行，不能开始下一轮")
        if not input_text.strip():
            raise ValueError("input_text 不能为空")
        session.turn_number += 1
        session.status = "starting"
        session.queue = asyncio.Queue()
        session.task = asyncio.create_task(self._execute(session, input_text))
        return self._handle(session)

    async def stream(self, run_id: str) -> AsyncIterator[AgentRunEvent]:
        session = self._session(run_id)
        while True:
            event = await session.queue.get()
            if event is None:
                break
            yield event

    async def cancel(self, run_id: str) -> None:
        session = self._session(run_id)
        if session.status not in {"starting", "running", "waiting_approval"}:
            return
        if session.task is not None:
            session.task.cancel()
        session.status = "cancelled"
        await self._emit(session, "run.cancelled", "cancelled")
        await session.queue.put(None)

    async def resolve_approval(self, run_id: str, decision: str) -> None:
        del run_id, decision
        raise AgentRunConflict("FakeRuntime 当前没有可审批的运行请求")

    async def release(self, run_id: str) -> None:
        session = self._sessions.pop(run_id, None)
        if session is None:
            return
        if session.task is not None and not session.task.done():
            session.task.cancel()
            await asyncio.gather(session.task, return_exceptions=True)

    async def close(self) -> None:
        await asyncio.gather(
            *(self.cancel(run_id) for run_id in list(self._sessions)),
            return_exceptions=True,
        )
        self._sessions.clear()

    async def _execute(self, session: _FakeSession, input_text: str) -> None:
        try:
            session.status = "running"
            await self._emit(session, "run.started", "running")
            await self._emit(
                session,
                "turn.started",
                "running",
                payload={"turn_number": session.turn_number},
            )
            if self._delay_seconds:
                await asyncio.sleep(self._delay_seconds)
            response = self._response_factory(session.spec, input_text)
            await self._emit(session, "message.delta", "running", message=response)
            await self._emit(session, "message.completed", "running", message=response)
            session.status = "completed"
            await self._emit(session, "run.completed", "completed")
            await session.queue.put(None)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            session.status = "failed"
            await self._emit(session, "run.failed", "failed", message=str(exc))
            await session.queue.put(None)

    async def _emit(
        self,
        session: _FakeSession,
        event_type: RuntimeEventType,
        status: RuntimeStatus,
        *,
        message: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> None:
        session.sequence += 1
        await session.queue.put(
            AgentRunEvent(
                run_id=session.spec.run_id,
                sequence=session.sequence,
                event_type=event_type,
                status=status,
                occurred_at=datetime.now(UTC),
                message=message,
                payload=payload or {},
            )
        )

    def _session(self, run_id: str) -> _FakeSession:
        try:
            return self._sessions[run_id]
        except KeyError as exc:
            raise AgentRunNotFound(f"没有找到运行: {run_id}") from exc

    def _handle(self, session: _FakeSession) -> AgentRunHandle:
        return AgentRunHandle(
            run_id=session.spec.run_id,
            runtime_key=self.runtime_key,
            runtime_thread_id=session.thread_id,
            runtime_session_id=session.thread_id,
            runtime_turn_id=f"fake-turn-{session.spec.run_id}-{session.turn_number}",
            status=session.status,
        )
