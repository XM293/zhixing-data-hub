# ruff: noqa: E501
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from zhixing_agent_runtime import AgentActor, AgentRunSpec, RuntimeCredentials

from zhixing_codex_runtime import CodexAppServerRuntime, CodexRuntimeSettings

FAKE_APP_SERVER = r'''
import json
import os
import sys

thread_id = "thread-token" if os.environ.get("ZHIXING_MCP_SESSION_TOKEN") else "thread-no-token"
turn_number = 0
for raw in sys.stdin:
    message = json.loads(raw)
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        print(json.dumps({"id": request_id, "result": {"platformFamily": "test"}}), flush=True)
    elif method == "initialized":
        continue
    elif method == "thread/start":
        print(json.dumps({"id": request_id, "result": {"thread": {"id": thread_id, "sessionId": "session-root"}}}), flush=True)
    elif method == "thread/resume":
        print(json.dumps({"id": request_id, "result": {"thread": {"id": message["params"]["threadId"], "sessionId": "session-root"}}}), flush=True)
    elif method == "turn/start":
        turn_number += 1
        turn_id = f"turn-{turn_number}"
        print(json.dumps({"id": request_id, "result": {"turn": {"id": turn_id, "status": "inProgress"}}}), flush=True)
        print(json.dumps({"method": "turn/started", "params": {"turn": {"id": turn_id, "status": "inProgress"}}}), flush=True)
        text = message["params"]["input"][0]["text"]
        if "hold-request" in text:
            continue
        print(json.dumps({"method": "item/started", "params": {"item": {"id": "tool-1", "type": "mcpToolCall", "server": "zhixing_enterprise", "tool": "get_metric", "status": "inProgress"}}}), flush=True)
        print(json.dumps({"method": "item/completed", "params": {"item": {"id": "tool-1", "type": "mcpToolCall", "server": "zhixing_enterprise", "tool": "get_metric", "status": "completed"}}}), flush=True)
        print(json.dumps({"method": "item/agentMessage/delta", "params": {"delta": "经营正常"}}), flush=True)
        print(json.dumps({"method": "item/completed", "params": {"item": {"id": "msg-1", "type": "agentMessage", "text": "经营正常", "phase": "final_answer"}}}), flush=True)
        print(json.dumps({"method": "turn/completed", "params": {"turn": {"id": turn_id, "status": "completed", "items": []}}}), flush=True)
    elif method == "turn/interrupt":
        print(json.dumps({"id": request_id, "result": {}}), flush=True)
        print(json.dumps({"method": "turn/completed", "params": {"turn": {"id": turn_id, "status": "interrupted", "items": []}}}), flush=True)
'''


def _write_server(tmp_path: Path) -> Path:
    script = tmp_path / "fake_app_server.py"
    script.write_text(FAKE_APP_SERVER, encoding="utf-8")
    return script


def _spec(tmp_path: Path, *, run_id: str, input_text: str = "分析经营情况") -> AgentRunSpec:
    return AgentRunSpec(
        run_id=run_id,
        actor=AgentActor(
            enterprise_id="enterprise-001",
            principal_id="principal-001",
            actor_key="ceo",
            permission_set_version="access-v1",
            authentication_method="session",
        ),
        input_text=input_text,
        instructions="只引用工具返回的证据。",
        cwd=str(tmp_path),
        model="test-model",
        allowed_tool_keys=("get_metric",),
    )


async def _start_and_stream(tmp_path: Path) -> None:
    script = _write_server(tmp_path)
    runtime = CodexAppServerRuntime(
        CodexRuntimeSettings(
            command=(sys.executable, "-u", str(script)),
            request_timeout_seconds=2,
        )
    )
    handle = await runtime.start(
        _spec(tmp_path, run_id="run-001"),
        RuntimeCredentials(mcp_session_token="secret", mcp_client_id="codex-project"),
    )
    events = [event async for event in runtime.stream(handle.run_id)]
    assert handle.runtime_thread_id == "thread-token"
    assert handle.runtime_session_id == "session-root"
    assert handle.runtime_turn_id == "turn-1"
    assert "tool.started" in [event.event_type for event in events]
    assert "tool.completed" in [event.event_type for event in events]
    assert events[-1].event_type == "run.completed"
    assert all("secret" not in repr(event) for event in events)

    resumed = await runtime.resume(handle.run_id, "继续分析")
    resumed_events = [event async for event in runtime.stream(handle.run_id)]
    assert resumed.runtime_turn_id == "turn-2"
    assert resumed_events[-1].event_type == "run.completed"
    await runtime.close()


def test_codex_runtime_maps_app_server_events_and_resumes(tmp_path: Path) -> None:
    asyncio.run(_start_and_stream(tmp_path))


async def _resume_after_process_restart(tmp_path: Path) -> None:
    script = _write_server(tmp_path)
    runtime = CodexAppServerRuntime(
        CodexRuntimeSettings(
            command=(sys.executable, "-u", str(script)),
            request_timeout_seconds=2,
        )
    )
    spec = _spec(tmp_path, run_id="run-restored")
    handle = await runtime.resume(
        spec.run_id,
        "恢复后继续分析",
        RuntimeCredentials(mcp_session_token="secret", mcp_client_id="codex-project"),
        runtime_thread_id="thread-persisted",
        spec=spec,
    )
    events = [event async for event in runtime.stream(handle.run_id)]
    assert handle.runtime_thread_id == "thread-persisted"
    assert handle.runtime_session_id == "session-root"
    assert handle.runtime_turn_id == "turn-1"
    assert any(event.payload.get("recovered") is True for event in events)
    assert events[-1].event_type == "run.completed"
    await runtime.close()


def test_codex_runtime_resumes_persisted_thread_after_restart(tmp_path: Path) -> None:
    asyncio.run(_resume_after_process_restart(tmp_path))


async def _cancel(tmp_path: Path) -> None:
    script = _write_server(tmp_path)
    runtime = CodexAppServerRuntime(
        CodexRuntimeSettings(
            command=(sys.executable, "-u", str(script)),
            request_timeout_seconds=2,
        )
    )
    handle = await runtime.start(
        _spec(tmp_path, run_id="run-cancel", input_text="hold-request"),
        RuntimeCredentials(mcp_session_token="secret", mcp_client_id="codex-project"),
    )
    await runtime.cancel(handle.run_id)
    events = [event async for event in runtime.stream(handle.run_id)]
    assert events[-1].event_type == "run.cancelled"
    await runtime.close()


def test_codex_runtime_interrupts_active_turn(tmp_path: Path) -> None:
    asyncio.run(_cancel(tmp_path))
