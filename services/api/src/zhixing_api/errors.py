from __future__ import annotations

import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from zhixing_observability import TraceContext, current_trace_context, log_event, new_trace_id

logger = logging.getLogger("zhixing.api")


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,95}$")
    message: str = Field(min_length=1, max_length=1000)
    status: int = Field(ge=400, le=599)
    request_id: str
    run_id: str
    retryable: bool
    details: dict[str, object] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    error: ErrorDetail


class ApiProblem(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        retryable: bool | None = None,
        details: dict[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = status_code >= 500 if retryable is None else retryable
        self.details = details or {}
        self.headers = headers


def _trace_context(request: Request) -> TraceContext:
    context = current_trace_context()
    if context is not None:
        return context
    request_id = getattr(request.state, "request_id", None) or new_trace_id("req")
    run_id = getattr(request.state, "run_id", None) or new_trace_id("run")
    return TraceContext(request_id=request_id, run_id=run_id)


def _response(request: Request, problem: ApiProblem) -> JSONResponse:
    context = _trace_context(request)
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=problem.code,
            message=problem.message,
            status=problem.status_code,
            request_id=context.request_id,
            run_id=context.run_id,
            retryable=problem.retryable,
            details=problem.details,
        )
    )
    log_event(
        logger,
        "http.error.returned",
        level=logging.WARNING if problem.status_code < 500 else logging.ERROR,
        error_code=problem.code,
        status=problem.status_code,
        retryable=problem.retryable,
    )
    return JSONResponse(
        status_code=problem.status_code,
        content=envelope.model_dump(mode="json"),
        headers=problem.headers,
    )


async def api_problem_handler(request: Request, exc: ApiProblem) -> JSONResponse:
    return _response(request, exc)


def _http_code(status_code: int) -> str:
    return {
        400: "request.invalid",
        401: "auth.unauthenticated",
        403: "authorization.denied",
        404: "resource.not_found",
        405: "request.method_not_allowed",
        409: "resource.conflict",
        422: "request.validation_failed",
        429: "request.rate_limited",
        502: "upstream.bad_gateway",
        503: "service.unavailable",
    }.get(status_code, "request.failed" if status_code < 500 else "service.internal_error")


def _status_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "请求失败"


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    details: dict[str, object] = {}
    if isinstance(exc.detail, dict):
        message_value = exc.detail.get("message")
        message = str(message_value) if message_value else _status_phrase(exc.status_code)
        details = {str(key): value for key, value in exc.detail.items() if key != "message"}
    else:
        message = str(exc.detail or _status_phrase(exc.status_code))
    return _response(
        request,
        ApiProblem(
            status_code=exc.status_code,
            code=_http_code(exc.status_code),
            message=message,
            details=details,
            headers=exc.headers,
        ),
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    issues = [
        {
            "location": [str(part) for part in error["loc"]],
            "type": error["type"],
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return _response(
        request,
        ApiProblem(
            status_code=422,
            code="request.validation_failed",
            message="请求参数未通过验证",
            details={"issues": issues},
        ),
    )


async def unhandled_exception_handler(request: Request, _: Exception) -> JSONResponse:
    return _response(
        request,
        ApiProblem(
            status_code=500,
            code="service.internal_error",
            message="服务处理请求时发生内部错误",
            retryable=False,
        ),
    )
