from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"
RUN_ID_HEADER = "X-Run-ID"

_TRACE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{7,95}$")
_request_id: ContextVar[str | None] = ContextVar("zhixing_request_id", default=None)
_run_id: ContextVar[str | None] = ContextVar("zhixing_run_id", default=None)


@dataclass(frozen=True, slots=True)
class TraceContext:
    request_id: str
    run_id: str


def new_trace_id(prefix: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,15}", prefix):
        raise ValueError("trace ID prefix is invalid")
    return f"{prefix}_{uuid4().hex}"


def resolve_trace_id(value: str | None, prefix: str) -> str:
    candidate = value.strip().lower() if value else ""
    if _TRACE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return new_trace_id(prefix)


def current_trace_context() -> TraceContext | None:
    request_id = _request_id.get()
    run_id = _run_id.get()
    if request_id is None or run_id is None:
        return None
    return TraceContext(request_id=request_id, run_id=run_id)


@contextmanager
def bind_trace_context(context: TraceContext) -> Iterator[TraceContext]:
    request_token = _request_id.set(context.request_id)
    run_token = _run_id.set(context.run_id)
    try:
        yield context
    finally:
        _run_id.reset(run_token)
        _request_id.reset(request_token)
