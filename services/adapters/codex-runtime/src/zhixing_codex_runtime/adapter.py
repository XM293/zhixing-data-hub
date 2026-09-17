from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from zhixing_agent_runtime import (
    AgentRunConflict,
    AgentRunEvent,
    AgentRunHandle,
    AgentRunNotFound,
    AgentRunSpec,
    AgentRuntimeError,
    RuntimeCredentials,
    RuntimeEventType,
    RuntimeStatus,
)

JsonObject = dict[str, object]
NotificationHandler = Callable[[str, JsonObject], Awaitable[None]]
RequestHandler = Callable[[int, str, JsonObject], Awaitable[object]]


@dataclass(frozen=True, slots=True)
class CodexRuntimeSettings:
    command: tuple[str, ...] = ("codex", "app-server", "--listen", "stdio://")
    client_name: str = "zhixing_data_hub"
    client_title: str = "Zhixing Data Hub"
    client_version: str = "0.1.0"
    request_timeout_seconds: float = 20.0
    mcp_token_env: str = "ZHIXING_MCP_SESSION_TOKEN"
    mcp_client_id_env: str = "ZHIXING_MCP_CLIENT_ID"
    mcp_run_id_env: str = "ZHIXING_MCP_RUN_ID"


@dataclass(frozen=True, slots=True)
class CodexRuntimeProbe:
    available: bool
    initialized: bool
    command: str
    version: str | None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class _RuntimeSession:
    spec: AgentRunSpec
    connection: _JsonRpcConnection
    thread_id: str = ""
    session_id: str | None = None
    turn_id: str = ""
    status: RuntimeStatus = "starting"
    sequence: int = 0
    queue: asyncio.Queue[AgentRunEvent | None] = field(default_factory=asyncio.Queue)
    approval_future: asyncio.Future[str] | None = None


class CodexAppServerRuntime:
    runtime_key = "codex-app-server"

    def __init__(self, settings: CodexRuntimeSettings | None = None) -> None:
        self.settings = settings or CodexRuntimeSettings()
        self._sessions: dict[str, _RuntimeSession] = {}

    async def probe(self) -> CodexRuntimeProbe:
        command_name = self.settings.command[0]
        resolved = shutil.which(command_name)
        if resolved is None and not _is_file(command_name):
            return CodexRuntimeProbe(
                available=False,
                initialized=False,
                command=command_name,
                version=None,
                error_code="codex_command_not_found",
                error_message="没有找到 Codex CLI",
            )
        version = await _command_version(command_name)
        connection = _JsonRpcConnection(
            self.settings,
            environment={},
            notification_handler=_ignore_notification,
            request_handler=_decline_server_request,
        )
        try:
            await connection.open()
            await connection.initialize()
            return CodexRuntimeProbe(
                available=True,
                initialized=True,
                command=command_name,
                version=version,
            )
        except AgentRuntimeError as exc:
            return CodexRuntimeProbe(
                available=True,
                initialized=False,
                command=command_name,
                version=version,
                error_code="codex_app_server_initialize_failed",
                error_message=str(exc)[:500],
            )
        finally:
            await connection.close()

    async def start(
        self,
        spec: AgentRunSpec,
        credentials: RuntimeCredentials | None = None,
    ) -> AgentRunHandle:
        if spec.run_id in self._sessions:
            raise AgentRunConflict(f"运行已存在: {spec.run_id}")
        environment = self._runtime_environment(spec, credentials)
        session: _RuntimeSession

        async def notification_handler(method: str, params: JsonObject) -> None:
            await self._handle_notification(session, method, params)

        async def request_handler(request_id: int, method: str, params: JsonObject) -> object:
            return await self._handle_server_request(session, request_id, method, params)

        connection = _JsonRpcConnection(
            self.settings,
            environment=environment,
            notification_handler=notification_handler,
            request_handler=request_handler,
        )
        session = _RuntimeSession(spec=spec, connection=connection)
        self._sessions[spec.run_id] = session
        try:
            await connection.open()
            await connection.initialize()
            thread_params: JsonObject = {
                "cwd": _absolute_path(spec.cwd),
                "approvalPolicy": "unlessTrusted",
                "sandbox": "readOnly",
                "serviceName": "zhixing-agent-runtime",
            }
            if spec.model:
                thread_params["model"] = spec.model
            thread_result = await connection.request("thread/start", thread_params)
            session.thread_id = _nested_string(thread_result, "thread", "id")
            if not session.thread_id:
                raise AgentRuntimeError("Codex app-server 未返回 thread id")
            session.session_id = _nested_string(thread_result, "thread", "sessionId") or None
            session.status = "running"
            await self._emit(
                session,
                "run.started",
                "running",
                payload={
                    "runtime_thread_id": session.thread_id,
                    "allowed_tool_keys": list(spec.allowed_tool_keys),
                    "permission_set_version": spec.actor.permission_set_version,
                },
            )
            await self._start_turn(session, spec.input_text)
            return self._handle(session)
        except Exception:
            self._sessions.pop(spec.run_id, None)
            await connection.close()
            raise

    async def resume(
        self,
        run_id: str,
        input_text: str,
        credentials: RuntimeCredentials | None = None,
        *,
        runtime_thread_id: str | None = None,
        spec: AgentRunSpec | None = None,
    ) -> AgentRunHandle:
        recovered = False
        session = self._sessions.get(run_id)
        if session is None:
            if spec is None or not runtime_thread_id:
                raise AgentRunNotFound(f"没有找到运行: {run_id}")
            if spec.run_id != run_id:
                raise ValueError("恢复规格与运行标识不一致")
            environment = self._runtime_environment(spec, credentials)
            restored_session: _RuntimeSession

            async def notification_handler(method: str, params: JsonObject) -> None:
                await self._handle_notification(restored_session, method, params)

            async def request_handler(
                request_id: int,
                method: str,
                params: JsonObject,
            ) -> object:
                return await self._handle_server_request(
                    restored_session,
                    request_id,
                    method,
                    params,
                )

            connection = _JsonRpcConnection(
                self.settings,
                environment=environment,
                notification_handler=notification_handler,
                request_handler=request_handler,
            )
            restored_session = _RuntimeSession(
                spec=spec,
                connection=connection,
                thread_id=runtime_thread_id,
                status="completed",
            )
            session = restored_session
            self._sessions[run_id] = session
            try:
                await connection.open()
                await connection.initialize()
                resume_params: JsonObject = {
                    "threadId": runtime_thread_id,
                    "cwd": _absolute_path(spec.cwd),
                    "approvalPolicy": "unlessTrusted",
                    "sandbox": "readOnly",
                }
                if spec.model:
                    resume_params["model"] = spec.model
                thread_result = await connection.request("thread/resume", resume_params)
                session.thread_id = _nested_string(thread_result, "thread", "id")
                if not session.thread_id:
                    raise AgentRuntimeError("Codex app-server 未返回恢复后的 thread id")
                session.session_id = (
                    _nested_string(thread_result, "thread", "sessionId") or None
                )
                recovered = True
            except Exception:
                self._sessions.pop(run_id, None)
                await connection.close()
                raise
        if session.status in {"starting", "running", "waiting_approval"}:
            raise AgentRunConflict("运行仍在执行，不能开始下一轮")
        if not input_text.strip():
            raise ValueError("input_text 不能为空")
        session.queue = asyncio.Queue()
        session.status = "starting"
        if recovered:
            await self._emit(
                session,
                "run.started",
                "running",
                payload={
                    "runtime_thread_id": session.thread_id,
                    "recovered": True,
                    "allowed_tool_keys": list(session.spec.allowed_tool_keys),
                    "permission_set_version": session.spec.actor.permission_set_version,
                },
            )
        await self._start_turn(session, input_text)
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
        if session.thread_id and session.turn_id:
            await session.connection.request(
                "turn/interrupt",
                {"threadId": session.thread_id, "turnId": session.turn_id},
            )

    async def release(self, run_id: str) -> None:
        session = self._sessions.pop(run_id, None)
        if session is not None:
            await session.connection.close()

    async def close(self) -> None:
        sessions = list(self._sessions.values())
        self._sessions.clear()
        await asyncio.gather(
            *(session.connection.close() for session in sessions),
            return_exceptions=True,
        )

    async def _start_turn(self, session: _RuntimeSession, input_text: str) -> None:
        params: JsonObject = {
            "threadId": session.thread_id,
            "input": [
                {
                    "type": "text",
                    "text": _runtime_input(session.spec, input_text),
                }
            ],
            "cwd": _absolute_path(session.spec.cwd),
            "approvalPolicy": "unlessTrusted",
            "sandboxPolicy": {
                "type": "readOnly",
                "access": {
                    "type": "restricted",
                    "includePlatformDefaults": True,
                    "readableRoots": [_absolute_path(session.spec.cwd)],
                },
            },
        }
        if session.spec.model:
            params["model"] = session.spec.model
        if session.spec.output_schema is not None:
            params["outputSchema"] = session.spec.output_schema
        session.status = "running"
        result = await session.connection.request("turn/start", params)
        session.turn_id = _nested_string(result, "turn", "id")
        if not session.turn_id:
            raise AgentRuntimeError("Codex app-server 未返回 turn id")

    def _runtime_environment(
        self,
        spec: AgentRunSpec,
        credentials: RuntimeCredentials | None,
    ) -> dict[str, str]:
        if spec.allowed_tool_keys and (
            credentials is None
            or not credentials.mcp_session_token
            or not credentials.mcp_client_id
        ):
            raise AgentRuntimeError("启用企业工具的运行必须提供受限 MCP 会话")
        environment: dict[str, str] = {}
        if credentials and credentials.mcp_session_token:
            environment[self.settings.mcp_token_env] = credentials.mcp_session_token
        if credentials and credentials.mcp_client_id:
            environment[self.settings.mcp_client_id_env] = credentials.mcp_client_id
        environment[self.settings.mcp_run_id_env] = spec.run_id
        return environment

    async def _handle_notification(
        self,
        session: _RuntimeSession,
        method: str,
        params: JsonObject,
    ) -> None:
        if method == "turn/started":
            await self._emit(session, "turn.started", "running", payload=_safe_payload(params))
            return
        if method == "item/agentMessage/delta":
            delta = params.get("delta")
            await self._emit(
                session,
                "message.delta",
                "running",
                message=delta if isinstance(delta, str) else None,
            )
            return
        if method in {"warning", "configWarning"}:
            message = params.get("message") or params.get("summary")
            await self._emit(
                session,
                "run.warning",
                session.status,
                message=str(message) if message else "Codex 运行警告",
            )
            return
        if method in {"item/started", "item/completed"}:
            await self._handle_item(session, method, params)
            return
        if method == "turn/completed":
            turn = params.get("turn")
            turn_payload = turn if isinstance(turn, dict) else {}
            raw_status = turn_payload.get("status")
            if raw_status == "completed":
                session.status = "completed"
                await self._emit(session, "run.completed", "completed")
            elif raw_status == "interrupted":
                session.status = "cancelled"
                await self._emit(session, "run.cancelled", "cancelled")
            else:
                session.status = "failed"
                error = turn_payload.get("error")
                await self._emit(
                    session,
                    "run.failed",
                    "failed",
                    message=_error_message(error),
                )
        await session.queue.put(None)

    async def resolve_approval(self, run_id: str, decision: str) -> None:
        if decision not in {"approve", "decline"}:
            raise ValueError("审批决定必须是 approve 或 decline")
        session = self._sessions.get(run_id)
        if session is None or session.approval_future is None or session.approval_future.done():
            raise AgentRunConflict("当前运行没有等待中的审批")
        session.approval_future.set_result(decision)

    async def _handle_item(
        self,
        session: _RuntimeSession,
        method: str,
        params: JsonObject,
    ) -> None:
        item = params.get("item")
        if not isinstance(item, dict):
            return
        item_type = item.get("type")
        if item_type == "agentMessage" and method == "item/completed":
            text = item.get("text")
            await self._emit(
                session,
                "message.completed",
                "running",
                message=text if isinstance(text, str) else None,
            )
            return
        if item_type != "mcpToolCall":
            return
        payload: dict[str, object] = {
            "item_id": str(item.get("id", "")),
            "server": str(item.get("server", "")),
            "tool": str(item.get("tool", "")),
            "status": str(item.get("status", "")),
        }
        if method == "item/started":
            event_type: RuntimeEventType = "tool.started"
        elif item.get("status") in {"completed", "succeeded"}:
            event_type = "tool.completed"
        else:
            event_type = "tool.failed"
        await self._emit(session, event_type, "running", payload=payload)

    async def _handle_server_request(
        self,
        session: _RuntimeSession,
        request_id: int,
        method: str,
        params: JsonObject,
    ) -> object:
        del request_id
        session.status = "waiting_approval"
        await self._emit(
            session,
            "approval.required",
            "waiting_approval",
            payload={
                "method": method,
                "item_id": str(params.get("itemId", "")),
                "reason": str(params.get("reason", "")),
            },
        )
        session.approval_future = asyncio.get_running_loop().create_future()
        try:
            decision = await asyncio.wait_for(session.approval_future, timeout=900)
        except TimeoutError:
            decision = "decline"
        finally:
            session.approval_future = None
        result = await _resolve_server_request(0, method, params, decision)
        session.status = "running"
        await self._emit(
            session,
            "approval.resolved",
            "running",
            payload={"method": method, "decision": "decline"},
        )
        return result

    async def _emit(
        self,
        session: _RuntimeSession,
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

    def _session(self, run_id: str) -> _RuntimeSession:
        try:
            return self._sessions[run_id]
        except KeyError as exc:
            raise AgentRunNotFound(f"没有找到运行: {run_id}") from exc

    def _handle(self, session: _RuntimeSession) -> AgentRunHandle:
        return AgentRunHandle(
            run_id=session.spec.run_id,
            runtime_key=self.runtime_key,
            runtime_thread_id=session.thread_id,
            runtime_session_id=session.session_id,
            runtime_turn_id=session.turn_id,
            status=session.status,
        )


class _JsonRpcConnection:
    def __init__(
        self,
        settings: CodexRuntimeSettings,
        *,
        environment: Mapping[str, str],
        notification_handler: NotificationHandler,
        request_handler: RequestHandler,
    ) -> None:
        self.settings = settings
        self.environment = dict(environment)
        self.notification_handler = notification_handler
        self.request_handler = request_handler
        self.process: asyncio.subprocess.Process | None = None
        self.reader_task: asyncio.Task[None] | None = None
        self.stderr_task: asyncio.Task[None] | None = None
        self.pending: dict[int, asyncio.Future[JsonObject]] = {}
        self.next_request_id = 1
        self.write_lock = asyncio.Lock()
        self.stderr_lines: list[str] = []

    async def open(self) -> None:
        if self.process is not None:
            return
        environment = os.environ.copy()
        environment.update(self.environment)
        cmd = _resolve_subprocess_command(self.settings.command)
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=environment,
            )
        except OSError as exc:
            raise AgentRuntimeError("无法启动 Codex app-server") from exc
        self.reader_task = asyncio.create_task(self._read_stdout())
        self.stderr_task = asyncio.create_task(self._read_stderr())

    async def initialize(self) -> None:
        await self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": self.settings.client_name,
                    "title": self.settings.client_title,
                    "version": self.settings.client_version,
                }
            },
        )
        await self.notify("initialized", {})

    async def request(self, method: str, params: JsonObject) -> JsonObject:
        if self.process is None:
            raise AgentRuntimeError("Codex app-server 尚未启动")
        request_id = self.next_request_id
        self.next_request_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[JsonObject] = loop.create_future()
        self.pending[request_id] = future
        await self._send({"method": method, "id": request_id, "params": params})
        try:
            return await asyncio.wait_for(
                future,
                timeout=self.settings.request_timeout_seconds,
            )
        except TimeoutError as exc:
            self.pending.pop(request_id, None)
            raise AgentRuntimeError(f"Codex app-server 请求超时: {method}") from exc

    async def notify(self, method: str, params: JsonObject) -> None:
        await self._send({"method": method, "params": params})

    async def close(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()
        current = asyncio.current_task()
        tasks = [
            task
            for task in (self.reader_task, self.stderr_task)
            if task is not None and task is not current
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        error = AgentRuntimeError("Codex app-server 连接已关闭")
        for future in self.pending.values():
            if not future.done():
                future.set_exception(error)
        self.pending.clear()

    async def _send(self, message: JsonObject) -> None:
        process = self.process
        if process is None or process.stdin is None or process.returncode is not None:
            raise AgentRuntimeError("Codex app-server 连接不可用")
        data = (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        async with self.write_lock:
            process.stdin.write(data)
            await process.stdin.drain()

    async def _read_stdout(self) -> None:
        process = self.process
        assert process is not None and process.stdout is not None
        try:
            while line := await process.stdout.readline():
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                await self._dispatch(cast(JsonObject, message))
        finally:
            if self.process is not None:
                detail = self.stderr_lines[-1] if self.stderr_lines else "进程已退出"
                error = AgentRuntimeError(f"Codex app-server 连接中断: {detail[:300]}")
                for future in self.pending.values():
                    if not future.done():
                        future.set_exception(error)

    async def _read_stderr(self) -> None:
        process = self.process
        assert process is not None and process.stderr is not None
        while line := await process.stderr.readline():
            text = line.decode(errors="replace").strip()
            if text:
                self.stderr_lines.append(text)
                del self.stderr_lines[:-20]

    async def _dispatch(self, message: JsonObject) -> None:
        raw_id = message.get("id")
        method = message.get("method")
        if isinstance(raw_id, int) and not isinstance(method, str):
            future = self.pending.pop(raw_id, None)
            if future is None or future.done():
                return
            error = message.get("error")
            if error is not None:
                future.set_exception(AgentRuntimeError(_error_message(error)))
                return
            result = message.get("result")
            future.set_result(result if isinstance(result, dict) else {})
            return
        params = message.get("params")
        safe_params = params if isinstance(params, dict) else {}
        if isinstance(raw_id, int) and isinstance(method, str):
            try:
                result = await self.request_handler(raw_id, method, cast(JsonObject, safe_params))
                await self._send({"id": raw_id, "result": result})
            except Exception as exc:
                await self._send(
                    {
                        "id": raw_id,
                        "error": {"code": -32603, "message": str(exc)[:300]},
                    }
                )
            return
        if isinstance(method, str):
            await self.notification_handler(method, cast(JsonObject, safe_params))


def _resolve_subprocess_command(command_parts: Sequence[str]) -> list[str]:
    cmd = list(command_parts)
    if not cmd:
        return cmd
    binary = shutil.which(cmd[0]) or cmd[0]
    cmd[0] = binary
    if sys.platform == "win32" and binary.lower().endswith((".cmd", ".bat")):
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return [comspec, "/c"] + cmd
    return cmd


async def _command_version(command: str) -> str | None:
    try:
        cmd = _resolve_subprocess_command([command, "--version"])
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
    except (OSError, TimeoutError):
        return None
    value = (stdout or stderr).decode(errors="replace").strip()
    return value[:120] if value else None


async def _ignore_notification(method: str, params: JsonObject) -> None:
    del method, params


async def _decline_server_request(
    request_id: int,
    method: str,
    params: JsonObject,
) -> object:
    del request_id, params
    if method in {
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
    }:
        return "decline"
    if method == "item/permissions/requestApproval":
        return {"permissions": [], "scope": "turn"}
    if method == "mcpServer/elicitation/request":
        return {"action": "decline", "content": None}
    if method == "tool/requestUserInput":
        return {"answers": {}}
    if method == "item/tool/call":
        return {"contentItems": [], "success": False}
    raise AgentRuntimeError(f"不支持的 Codex 服务端请求: {method}")


async def _resolve_server_request(
    request_id: int,
    method: str,
    params: JsonObject,
    decision: str,
) -> object:
    if decision == "decline":
        return await _decline_server_request(request_id, method, params)
    if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
        return "accept"
    if method == "item/permissions/requestApproval":
        return {"permissions": params.get("permissions", []), "scope": "turn"}
    if method == "mcpServer/elicitation/request":
        return {"action": "accept", "content": params.get("content")}
    if method == "tool/requestUserInput":
        return {"answers": {}}
    if method == "item/tool/call":
        return {"contentItems": [], "success": True}
    raise AgentRuntimeError(f"不支持的 Codex 服务端请求: {method}")


def _runtime_input(spec: AgentRunSpec, input_text: str) -> str:
    tools = "、".join(spec.allowed_tool_keys) if spec.allowed_tool_keys else "无"
    return (
        "以下身份信息只用于审计，不能授予权限。所有企业数据访问必须通过当前 MCP 会话，"
        "不得使用 Shell、文件修改、任意网络请求或模型自报身份绕过工具授权。\n"
        f"企业: {spec.actor.enterprise_id}\n"
        f"发起主体: {spec.actor.actor_key}\n"
        f"权限版本: {spec.actor.permission_set_version}\n"
        f"允许发现的企业工具: {tools}\n"
        f"角色与回答约束:\n{spec.instructions.strip()}\n"
        f"当前请求:\n{input_text.strip()}"
    )


def _absolute_path(value: str) -> str:
    return os.path.abspath(value)


def _is_file(value: str) -> bool:
    return os.path.isfile(value)


def _nested_string(value: JsonObject, parent: str, child: str) -> str:
    nested = value.get(parent)
    if not isinstance(nested, dict):
        return ""
    result = nested.get(child)
    return result if isinstance(result, str) else ""


def _safe_payload(value: JsonObject) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key in ("threadId", "turnId"):
        item = value.get(key)
        if isinstance(item, str):
            safe[key] = item
    turn = value.get("turn")
    if isinstance(turn, dict):
        for key in ("id", "status"):
            item = turn.get(key)
            if isinstance(item, str):
                safe[f"turn_{key}"] = item
    return safe


def _error_message(value: object) -> str:
    if isinstance(value, dict):
        message = value.get("message")
        if isinstance(message, str):
            return message[:500]
    return str(value)[:500] if value else "Codex 运行失败"
