from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class SyncPageResult:
    pages: int
    records: int
    checkpoint: int


class Lease:
    def __init__(self, ttl_seconds: int = 60):
        self.ttl_seconds = ttl_seconds
        self.expires_at: datetime | None = None

    def acquire(self) -> None:
        self.expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)

    def renew(self) -> None:
        if self.is_expired:
            raise RuntimeError("lease_expired")
        self.acquire()

    @property
    def is_expired(self) -> bool:
        return self.expires_at is None or self.expires_at <= datetime.now(UTC)


def aggregate_status(statuses: list[str]) -> str:
    if not statuses:
        return "queued"
    if all(item == "succeeded" for item in statuses):
        return "succeeded"
    if all(item in {"failed", "cancelled"} for item in statuses):
        return "failed"
    if any(item == "failed" for item in statuses):
        return "partial_failed"
    if any(item == "running" for item in statuses):
        return "running"
    return "queued"


async def execute_pages(
    fetch: Callable[[int], Awaitable[dict[str, Any]]],
    persist: Callable[[dict[str, Any]], Awaitable[int]],
    *,
    checkpoint: int = 0,
) -> SyncPageResult:
    page, total = checkpoint + 1, 0
    while True:
        payload = await fetch(page)
        total += await persist(payload)
        more = (payload.get("data") or {}).get("has_more", False)
        if not more:
            return SyncPageResult(page - checkpoint, total, page)
        page += 1
