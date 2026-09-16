from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any


async def pages(
    fetch: Callable[[int], Awaitable[dict[str, Any]]], *, start: int = 1
) -> AsyncIterator[dict[str, Any]]:
    page = start
    while True:
        payload = await fetch(page)
        yield payload
        data = payload.get("data") or {}
        if not data.get("has_more") and not data.get("next_page"):
            return
        page = int(data.get("next_page") or page + 1)
