from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from zhixing_observability.context import current_trace_context


def structured_event(
    event: str,
    *,
    level: str = "info",
    message: str | None = None,
    **fields: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "event": event,
    }
    context = current_trace_context()
    if context is not None:
        payload["request_id"] = context.request_id
        payload["run_id"] = context.run_id
    if message:
        payload["message"] = message
    payload.update(fields)
    return payload


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    message: str | None = None,
    **fields: object,
) -> None:
    level_name = logging.getLevelName(level).lower()
    payload = structured_event(event, level=level_name, message=message, **fields)
    logger.log(level, json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":")))
