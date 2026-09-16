from __future__ import annotations

import asyncio
import logging

from zhixing_api.data_center_service import reconcile_due_meetings
from zhixing_api.database import Database
from zhixing_api.redis_coordinator import NoopRedisCoordinator, RedisCoordinator

logger = logging.getLogger(__name__)


async def run_meeting_scheduler(
    database: Database,
    poll_seconds: float,
    coordinator: RedisCoordinator | NoopRedisCoordinator,
) -> None:
    while True:
        try:
            async with coordinator.lease(
                "meeting-scheduler",
                ttl_seconds=max(int(poll_seconds * 4), 2),
            ) as acquired:
                if acquired:
                    await asyncio.to_thread(reconcile_due_meetings, database)
        except Exception:
            logger.exception("meeting scheduler reconciliation failed")
        await asyncio.sleep(max(poll_seconds, 0.05))
