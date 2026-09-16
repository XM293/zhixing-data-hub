from contextlib import nullcontext
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import Connection, Table, select, update
from sqlalchemy.orm import Session
from zhixing_jobs.models import BackgroundJob
from zhixing_jobs.repository import JobRepository

from zhixing_api.data_models import ExternalSystem, PlatformEvent, SyncResourceRun, SyncRun
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem

from .persistence import stable_key
from .planning import ImportRequest, plan_import
from .queue import enqueue_sync

TERMINAL = frozenset({"succeeded", "failed", "partial_failed", "cancelled"})


def enqueue_import(database: Database, *, enterprise_id: str, source_key: str,
                   initiator_id: str, request_id: str, payload: ImportRequest,
                   scope_snapshot: dict[str, object], actor_snapshot: dict[str, object],
                   provider_enabled: bool = False, transaction: Session | None = None) -> SyncRun:
    pieces = plan_import(payload)
    fingerprint = stable_key(payload.model_dump_json(exclude={"client_request_key"}),
                             str(sorted(scope_snapshot.items())), initiator_id)
    now = datetime.now(UTC)
    with nullcontext(transaction) if transaction is not None else database.session() as session:
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == enterprise_id, ExternalSystem.system_key == source_key
        ).with_for_update())
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        if source.provider_key != "lingxing" and source.system_type != "lingxing":
            raise ApiProblem(status_code=422, code="source.provider_unsupported",
                             message="来源不支持分批导入")
        key = "batch:" + stable_key(enterprise_id, source.id, payload.client_request_key)
        existing = session.scalar(select(SyncRun).where(SyncRun.idempotency_key == key,
                                                        SyncRun.external_system_id == source.id))
        if existing is not None:
            if existing.command_fingerprint != fingerprint:
                raise ApiProblem(status_code=409, code="source.request_key_reused",
                                 message="请求标识已用于其他导入参数")
            return existing
        parent = SyncRun(id=f"sync_{uuid4().hex}", enterprise_id=enterprise_id,
            source_version=source.version,
            external_system_id=source.id, status="queued", started_at=now, scenario="import",
            volume_profile="standard", idempotency_key=key, command_fingerprint=fingerprint,
            request_id=request_id, trace_id=request_id, scope_snapshot=scope_snapshot)
        session.add(parent)
        session.flush()
        for ordinal, piece in enumerate(pieces):
            child = enqueue_sync(database, enterprise_id=enterprise_id, source_key=source_key,
                initiator_id=initiator_id, request_id=request_id,
                payload=piece.model_copy(update={"client_request_key": f"{parent.id}:{ordinal}"}),
                scope_snapshot=scope_snapshot, actor_snapshot=actor_snapshot,
                provider_enabled=provider_enabled, transaction=session)
            child.parent_run_id = parent.id
        session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=enterprise_id,
            event_type="source.import_queued", severity="info", title="导入批次已排队",
            detail=f"run_id={parent.id}; partitions={len(pieces)}; principal_id={initiator_id}",
            occurred_at=now))
        session.flush()
        if transaction is None:
            session.commit()
        return parent


def reconcile_terminal_runs(connection: Connection, *, limit: int = 100) -> None:
    """Close orphan ledgers from terminal jobs; callers refresh parents after this commits."""
    table = cast(Table, SyncRun.__table__)
    rows = connection.execute(select(table.c.id, table.c.enterprise_id, BackgroundJob.status,
        BackgroundJob.last_error_code).join(BackgroundJob,
            (BackgroundJob.id == table.c.task_id)
            & (BackgroundJob.enterprise_id == table.c.enterprise_id)
            & (BackgroundJob.run_id == table.c.id)).where(
        table.c.status.not_in(TERMINAL), BackgroundJob.job_type == "data-source.sync",
        BackgroundJob.status.in_(["failed", "cancelled"])
    ).order_by(table.c.started_at, table.c.id).limit(limit)
        .with_for_update(of=table, skip_locked=True)).all()
    now = datetime.now(UTC)
    for row in rows:
        connection.execute(update(table).where(table.c.id == row.id).values(
            status=row.status, finished_at=now))
        connection.execute(update(SyncResourceRun).where(
            SyncResourceRun.sync_run_id == row.id,
            SyncResourceRun.status.in_(["queued", "running"])
        ).values(status=row.status, finished_at=now,
                 error_code=row.last_error_code or f"job.{row.status}"))
        connection.execute(cast(Table, PlatformEvent.__table__).insert().values(
            id=f"event_{uuid4().hex}", enterprise_id=row.enterprise_id,
            event_type="source.sync_reconciled", severity="warning", title="同步状态已校正",
            detail=f"run_id={row.id}; status={row.status}", occurred_at=now))


def refresh_batch(connection: Connection, parent_id: str) -> None:
    table = cast(Table, SyncRun.__table__)
    parent = connection.execute(select(table).where(table.c.id == parent_id)
                                .with_for_update()).mappings().one_or_none()
    if parent is None or parent["status"] == "cancelled":
        return
    children = list(connection.execute(select(table).where(table.c.parent_run_id == parent_id))
                    .mappings())
    if not children:
        return
    # Recover terminal task outcomes even if a process exited before opening a resource run.
    jobs = {row.id: row.status for row in connection.execute(select(
        BackgroundJob.id, BackgroundJob.status).where(
        BackgroundJob.run_id.in_([child["id"] for child in children])
    ))}
    statuses = []
    for child in children:
        state = child["status"]
        if state not in TERMINAL and jobs.get(child["task_id"], "") in {"failed", "cancelled"}:
            state = jobs[child["task_id"]]
            connection.execute(update(table).where(table.c.id == child["id"]).values(
                status=state, finished_at=datetime.now(UTC)))
        statuses.append(state)
    active = any(state not in TERMINAL for state in statuses)
    state = ("running" if active else
             "succeeded" if all(state == "succeeded" for state in statuses) else
             "cancelled" if all(state == "cancelled" for state in statuses) else
             "failed" if all(state == "failed" for state in statuses) else "partial_failed")
    connection.execute(update(table).where(table.c.id == parent_id).values(
        status=state, records_read=sum(child["records_read"] for child in children),
        records_written=sum(child["records_written"] for child in children),
        finished_at=None if active else datetime.now(UTC)))


def cancel_import(database: Database, session: Session, run: SyncRun, *, principal_id: str) -> None:
    now = datetime.now(UTC)
    children = list(session.scalars(select(SyncRun).where(SyncRun.parent_run_id == run.id)))
    rows = [run, *children]
    # Use the same job -> run lock order as page completion to avoid cancellation deadlocks.
    for row in sorted(rows, key=lambda item: item.task_id or ""):
        if row.task_id:
            JobRepository(database.engine).cancel_in_session(
                session, row.task_id, row.enterprise_id)
    for row in rows:
        session.refresh(row, with_for_update=True)
        if row.status in TERMINAL:
            continue
        row.status, row.cancel_requested_at, row.finished_at = "cancelled", now, now
        session.execute(update(SyncResourceRun).where(
            SyncResourceRun.sync_run_id == row.id,
            SyncResourceRun.status.in_(["queued", "running"]),
        ).values(status="cancelled", finished_at=now))
    session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=run.enterprise_id,
        event_type="source.sync_cancelled", severity="info", title="同步已取消",
        detail=f"run_id={run.id}; principal_id={principal_id}", occurred_at=now))
