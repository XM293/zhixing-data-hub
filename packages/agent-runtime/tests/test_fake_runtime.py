from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from zhixing_agent_runtime import (
    AgentActor,
    AgentRunConflict,
    AgentRunSpec,
    FakeAgentRuntime,
)


def run_spec(run_id: str = "run-001") -> AgentRunSpec:
    return AgentRunSpec(
        run_id=run_id,
        actor=AgentActor(
            enterprise_id="enterprise-001",
            principal_id="principal-001",
            actor_key="ceo",
            permission_set_version="access-v1",
            authentication_method="session",
        ),
        input_text="分析本周经营情况",
        instructions="只依据已授权证据回答。",
        cwd=".",
        allowed_tool_keys=("get_metric",),
    )


async def _start_stream_and_resume() -> None:
    runtime = FakeAgentRuntime()
    handle = await runtime.start(run_spec())
    events = [event async for event in runtime.stream(handle.run_id)]

    assert handle.runtime_key == "fake"
    assert handle.runtime_session_id == handle.runtime_thread_id
    assert [event.event_type for event in events] == [
        "run.started",
        "turn.started",
        "message.delta",
        "message.completed",
        "run.completed",
    ]
    assert events[2].message == "ceo: 分析本周经营情况"

    resumed = await runtime.resume(handle.run_id, "只看旗舰店")
    resumed_events = [event async for event in runtime.stream(handle.run_id)]
    assert resumed.runtime_thread_id == handle.runtime_thread_id
    assert resumed.runtime_turn_id == "fake-turn-run-001-2"
    assert resumed_events[-1].event_type == "run.completed"


def test_fake_runtime_start_stream_and_resume() -> None:
    asyncio.run(_start_stream_and_resume())


async def _restore_fake_runtime() -> None:
    runtime = FakeAgentRuntime()
    spec = run_spec("run-restored")
    handle = await runtime.resume(
        spec.run_id,
        "恢复运行",
        runtime_thread_id="fake-thread-persisted",
        spec=spec,
    )
    events = [event async for event in runtime.stream(handle.run_id)]
    assert handle.runtime_thread_id == "fake-thread-persisted"
    assert handle.runtime_turn_id == "fake-turn-run-restored-1"
    assert events[-1].event_type == "run.completed"


def test_fake_runtime_can_restore_persisted_thread() -> None:
    asyncio.run(_restore_fake_runtime())


def test_scope_snapshot_is_optional_but_cannot_change_the_actor_legal_identity():
    original = run_spec()
    assert original.scope_context is None
    scope = {"schema_version": 2, "enterprise_id": "enterprise-001",
             "scope_level": "store", "store_ids": ["store-synthetic"]}
    scoped = replace(original, scope_context=scope)
    assert scoped.scope_context == scope
    with pytest.raises(ValueError):
        replace(original, scope_context={**scope, "enterprise_id": "another-legal"})
    with pytest.raises(ValueError):
        replace(original, scope_context={**scope, "schema_version": 1})


async def _reject_duplicate_and_cancel() -> None:
    runtime = FakeAgentRuntime(delay_seconds=1)
    await runtime.start(run_spec("run-cancel"))
    try:
        await runtime.start(run_spec("run-cancel"))
    except AgentRunConflict:
        pass
    else:
        raise AssertionError("重复运行应被拒绝")

    await asyncio.sleep(0)
    await runtime.cancel("run-cancel")
    events = [event async for event in runtime.stream("run-cancel")]
    assert events[-1].event_type == "run.cancelled"


def test_fake_runtime_rejects_duplicate_and_can_cancel() -> None:
    asyncio.run(_reject_duplicate_and_cancel())
