"""Remove signed HTTP details before any log handler can receive a record."""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from typing import Any

_sensitive_io: ContextVar[bool] = ContextVar("connector_sensitive_io", default=False)
_factory_lock = Lock()
_installed_factory: Callable[..., logging.LogRecord] | None = None


def _install() -> None:
    global _installed_factory
    with _factory_lock:
        previous = logging.getLogRecordFactory()
        if previous is _installed_factory:
            return

        def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = previous(*args, **kwargs)
            if _sensitive_io.get() and record.name.split(".", 1)[0] in {"httpx", "httpcore"}:
                record.msg = "External HTTP request details redacted"
                record.args = ()
                record.exc_info = None
                record.exc_text = None
                record.stack_info = None
            return record

        _installed_factory = factory
        logging.setLogRecordFactory(factory)


@contextmanager
def redact_transport_logs() -> Iterator[None]:
    _install()
    token = _sensitive_io.set(True)
    try:
        yield
    finally:
        _sensitive_io.reset(token)
