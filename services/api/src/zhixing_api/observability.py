from __future__ import annotations

import logging
from time import perf_counter

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from zhixing_observability import (
    REQUEST_ID_HEADER,
    RUN_ID_HEADER,
    TraceContext,
    bind_trace_context,
    log_event,
    resolve_trace_id,
)

logger = logging.getLogger("zhixing.api")


class TraceContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        context = TraceContext(
            request_id=resolve_trace_id(headers.get(REQUEST_ID_HEADER), "req"),
            run_id=resolve_trace_id(headers.get(RUN_ID_HEADER), "run"),
        )
        state = scope.setdefault("state", {})
        state["request_id"] = context.request_id
        state["run_id"] = context.run_id
        started = perf_counter()
        status_code = 500

        async def send_with_trace(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = context.request_id
                response_headers[RUN_ID_HEADER] = context.run_id
            await send(message)

        with bind_trace_context(context):
            log_event(
                logger,
                "http.request.started",
                method=scope.get("method"),
                path=scope.get("path"),
            )
            try:
                await self.app(scope, receive, send_with_trace)
            except Exception:
                log_event(
                    logger,
                    "http.request.failed",
                    level=logging.ERROR,
                    method=scope.get("method"),
                    path=scope.get("path"),
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                raise
            finally:
                log_event(
                    logger,
                    "http.request.completed",
                    method=scope.get("method"),
                    path=scope.get("path"),
                    status=status_code,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
