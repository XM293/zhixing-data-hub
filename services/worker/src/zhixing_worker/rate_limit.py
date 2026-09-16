"""Database-atomic request slots shared by all workers for an AppID and resource."""
from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from typing import cast

from sqlalchemy import Engine, Table, case, extract, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.postgresql.dml import Insert as PostgresInsert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.sqlite.dml import Insert as SQLiteInsert
from zhixing_api.data_models import SourceRequestBudget


class SourceRateLimiter:
    def __init__(self, engine: Engine, account_key: str, *,
                 clock: Callable[[], datetime] | None = None,
                 ensure_active: Callable[[], object] | None = None,
                 minimum_interval: float = 1.0, maximum_wait: float = 30.0):
        if not account_key or minimum_interval < 1 or not 0 < maximum_wait <= 60:
            raise ValueError("invalid request budget")
        self._engine, self._account_key = engine, account_key
        self._clock, self._ensure_active = clock, ensure_active
        self._interval, self._maximum_wait = Decimal(str(minimum_interval)), maximum_wait

    def reserve(self, path: str) -> float:
        key = hashlib.sha256(json.dumps([self._account_key, path]).encode()).hexdigest()
        table = cast(Table, SourceRequestBudget.__table__)
        with self._engine.begin() as connection:
            if self._clock is not None:
                now = self._clock()
                epoch = Decimal(str(now.timestamp()))
            elif connection.dialect.name == "postgresql":
                epoch = Decimal(str(connection.scalar(
                    select(extract("epoch", func.clock_timestamp())),
                )))
                now = datetime.fromtimestamp(float(epoch), UTC)
            else:
                now = datetime.now(UTC)
                epoch = Decimal(str(now.timestamp()))
            insert: PostgresInsert | SQLiteInsert
            if connection.dialect.name == "postgresql":
                insert = pg_insert(table)
            elif connection.dialect.name == "sqlite":
                insert = sqlite_insert(table)
            else:
                raise RuntimeError("request budget database unsupported")
            next_epoch = case(
                (table.c.next_allowed_epoch > epoch, table.c.next_allowed_epoch), else_=epoch,
            ) + self._interval
            reserved = connection.execute(insert.values(
                id=key, next_allowed_epoch=epoch + self._interval, updated_at=now,
            ).on_conflict_do_update(index_elements=[table.c.id], set_={
                "next_allowed_epoch": next_epoch, "updated_at": now,
            }).returning(table.c.next_allowed_epoch)).scalar_one()
            delay = max(0.0, float(reserved - self._interval - epoch))
            if delay > self._maximum_wait:
                # Roll back the reservation; do not accumulate unbounded future slots.
                raise RuntimeError("rate_limited")
        return delay

    async def acquire(self, path: str) -> None:
        if self._ensure_active:
            self._ensure_active()
        delay = self.reserve(path)
        deadline = monotonic() + delay
        while monotonic() < deadline:
            if self._ensure_active:
                self._ensure_active()
            await asyncio.sleep(min(0.25, max(0.0, deadline - monotonic())))
        if self._ensure_active:
            self._ensure_active()
