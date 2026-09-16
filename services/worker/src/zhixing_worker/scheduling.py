"""Database-only scheduling before claiming jobs; no external requests or API callbacks."""
from time import monotonic

from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import aliased
from zhixing_api.data_models import SyncRun
from zhixing_api.database import Database
from zhixing_api.ingestion.backfills import dispatch_backfills
from zhixing_api.ingestion.batches import TERMINAL, reconcile_terminal_runs, refresh_batch
from zhixing_api.ingestion.schedules import dispatch_due
from zhixing_jobs.models import BackgroundJob


class SourceScheduleTick:
    def __init__(self, engine: Engine, *, enabled: bool) -> None:
        self.database = Database.from_engine(engine)
        self.enabled = enabled
        self.next_tick = 0.0
        self.available = inspect(engine).has_table("source_sync_schedules")
        self.backfills_available = inspect(engine).has_table("source_backfill_plans")
        if enabled and not self.available:
            raise RuntimeError("来源调度需要先升级数据库至 0061 或更新版本")

    def __call__(self) -> None:
        if not self.available or monotonic() < self.next_tick:
            return
        self.next_tick = monotonic() + 30
        # Commit child reconciliation before taking parent locks (shared lock order).
        with self.database.engine.begin() as connection:
            reconcile_terminal_runs(connection)
        with self.database.engine.begin() as connection:
            parent = aliased(SyncRun)
            ids = connection.execute(select(parent.id).join(
                SyncRun, SyncRun.parent_run_id == parent.id).join(
                BackgroundJob, BackgroundJob.id == SyncRun.task_id).where(
                parent.status.not_in(TERMINAL), BackgroundJob.status.in_(["failed", "cancelled"])
            ).distinct().limit(100)).scalars().all()
            for identity in ids:
                refresh_batch(connection, identity)
        dispatch_due(self.database, provider_enabled=self.enabled)
        if self.backfills_available:
            dispatch_backfills(self.database, provider_enabled=self.enabled)
