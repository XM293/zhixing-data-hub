from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from zhixing_connectors.catalog import resource_spec, validate_partition_parameters
from zhixing_connectors.parameter_policies import PARAMETER_POLICY_VERSION
from zhixing_jobs.models import BackgroundJob

from zhixing_api.actor_context import ActorContext, require_permission, resolve_database_actor
from zhixing_api.data_models import (
    ExternalSystem,
    PlatformEvent,
    RawPageManifest,
    SourceBackfillPlan,
    SourceCoverageWindow,
    SourceResource,
    SyncCheckpoint,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.scope_context import ScopeContext, build_scope_context

from .batches import TERMINAL, enqueue_import, refresh_batch
from .parameter_fanout import plan_parameter_fanout, validate_parameter_fanout_base
from .persistence import stable_key
from .planning import ImportRequest, ImportSelection

ACQUIRED = frozenset({"succeeded", "no_data", "succeeded_with_conflicts"})


class BackfillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    name: str = Field(min_length=1, max_length=120)
    resource_key: str = Field(min_length=1, max_length=120)
    resource_parameters: dict[str, str] = Field(default_factory=dict)
    projection_mode: Literal["inline", "deferred"] = "deferred"
    status: Literal["paused", "active"] = "paused"
    window_start: datetime
    window_end: datetime
    partition_days: int = Field(default=7, ge=1, le=366)
    batch_size: int = Field(default=16, ge=1, le=32)

    @model_validator(mode="after")
    def validate_window(self) -> BackfillRequest:
        spec = resource_spec(self.resource_key)
        if spec is None or not spec.path:
            raise ValueError("source.resource_unknown")
        if not spec.window_fields:
            raise ValueError("source.backfill_window_unsupported")
        if len(spec.window_fields) == 1 and self.partition_days != 1:
            raise ValueError("source.single_date_partition_requires_one_day")
        if self.partition_days > spec.max_window_days:
            raise ValueError("source.partition_exceeds_contract")
        try:
            validate_partition_parameters(spec, dict(self.resource_parameters))
        except ValueError:
            validate_parameter_fanout_base(self.resource_key, self.resource_parameters)
        if (self.window_start.tzinfo is None or self.window_end.tzinfo is None
                or self.window_start >= self.window_end):
            raise ValueError("source.window_required")
        if self.window_end - self.window_start > timedelta(days=366 * 40):
            raise ValueError("source.backfill_range_too_large")
        return self


class BackfillView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    resource_key: str
    resource_version: str
    resource_parameters: dict[str, str]
    parameter_policy_version: str | None
    parameter_waiting_code: str | None
    projection_mode: str
    status: str
    window_start: datetime
    window_end: datetime
    cursor: datetime
    partition_days: int
    batch_size: int
    active_run_id: str | None
    windows_total: int
    windows_succeeded: int
    windows_no_data: int
    windows_with_conflicts: int
    windows_failed: int
    records_read: int
    records_written: int
    error_code: str | None
    version: int


class CoverageWindowView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    resource_key: str
    resource_version: str
    window_start: datetime
    window_end: datetime
    sync_run_id: str | None
    status: str
    records_read: int
    records_written: int
    error_code: str | None
    attempt_count: int
    started_at: datetime | None
    finished_at: datetime | None
    parameter_fanout_offset: int
    parameter_fanout_total: int


class CoverageWindowList(BaseModel):
    items: list[CoverageWindowView]
    offset: int
    limit: int
    total: int


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _audit(session: Session, row: SourceBackfillPlan, action: str, now: datetime) -> None:
    session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=row.enterprise_id,
        event_type=f"source.backfill_{action}", severity="warning" if row.error_code else "info",
        title="历史回填计划状态更新",
        detail=f"backfill_id={row.id}; status={row.status}; version={row.version}; "
               f"error_code={row.error_code or ''}", occurred_at=now))


def save_backfill(database: Database, *, actor: ActorContext, source_key: str,
                  payload: BackfillRequest, scope: dict[str, object],
                  backfill_id: str | None = None, expected_version: int | None = None,
                  now: datetime | None = None,
                  transaction: Session | None = None,
                  allow_contract_rebind: bool = False) -> SourceBackfillPlan:
    now = now or datetime.now(UTC)
    require_permission(actor, "source.manage", database, resource_type="source",
                       resource_key=source_key, scope_type="enterprise",
                       scope_id=actor.enterprise_id, transaction=transaction)
    session_context = nullcontext(transaction) if transaction is not None else database.session()
    with session_context as session:
        assert session is not None
        row = (session.scalar(select(SourceBackfillPlan).where(
            SourceBackfillPlan.id == backfill_id,
            SourceBackfillPlan.enterprise_id == actor.enterprise_id).with_for_update())
            if backfill_id else None)
        row_was_existing = row is not None
        if backfill_id and row is None:
            raise ApiProblem(status_code=404, code="source.backfill_not_found",
                             message="历史回填计划不存在")
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key).with_for_update())
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        if row is not None and row.external_system_id != source.id:
            raise ApiProblem(status_code=404, code="source.backfill_not_found",
                             message="历史回填计划不存在")
        resource = session.scalar(select(SourceResource).where(
            SourceResource.external_system_id == source.id,
            SourceResource.resource_key == payload.resource_key))
        if resource is None or not resource.enabled or resource.schema_status == "schema_pending":
            raise ApiProblem(status_code=422, code="source.resource_disabled",
                             message="资源尚未具备受控历史回填条件")
        if row is not None:
            if expected_version is not None and row.version != expected_version:
                raise ApiProblem(status_code=409, code="source.backfill_changed",
                                 message="历史回填计划已更新，请刷新")
            if row.active_run_id:
                raise ApiProblem(status_code=409, code="source.backfill_busy",
                                 message="历史回填批次正在运行")
            identity = (row.resource_key, row.resource_parameters, row.projection_mode,
                        _utc(row.window_start), _utc(row.window_end), row.partition_days)
            requested = (payload.resource_key, payload.resource_parameters, payload.projection_mode,
                         payload.window_start.astimezone(UTC), payload.window_end.astimezone(UTC),
                         payload.partition_days)
            if identity != requested:
                raise ApiProblem(status_code=409, code="source.backfill_identity_changed",
                                 message="资源、范围或分区变更需要新建回填计划")
            if row.resource_version != resource.version and not allow_contract_rebind:
                raise ApiProblem(status_code=409, code="source.backfill_contract_changed",
                                 message="资源契约已更新，请新建回填计划")
            row.resource_version = resource.version
            if row.status == "completed" and payload.status == "active":
                raise ApiProblem(status_code=409, code="source.backfill_completed",
                                 message="已完成回填不能重新启用")
            row.version += 1
        else:
            start, end = payload.window_start.astimezone(UTC), payload.window_end.astimezone(UTC)
            row = SourceBackfillPlan(id=f"backfill_{uuid4().hex}",
                enterprise_id=actor.enterprise_id, external_system_id=source.id,
                source_resource_id=resource.id, resource_version=resource.version, cursor=start,
                windows_total=ceil((end - start) / timedelta(days=payload.partition_days)),
                windows_succeeded=0, windows_no_data=0, windows_with_conflicts=0,
                windows_failed=0, records_read=0, records_written=0,
                created_at=now, version=1)
            session.add(row)
        previous_policy_version = row.parameter_policy_version
        try:
            validate_parameter_fanout_base(payload.resource_key, payload.resource_parameters)
            row.parameter_policy_version = PARAMETER_POLICY_VERSION
        except ValueError:
            row.parameter_policy_version = None
        if previous_policy_version != row.parameter_policy_version and row_was_existing:
            coverage_count = session.scalar(select(func.count()).select_from(
                SourceCoverageWindow).where(SourceCoverageWindow.backfill_plan_id == row.id)) or 0
            if coverage_count:
                raise ApiProblem(status_code=409,
                    code="source.backfill_parameter_policy_changed",
                    message="参数策略已更新，请新建历史回填计划")
        row.name = payload.name
        row.resource_key = payload.resource_key
        row.resource_parameters = payload.resource_parameters
        row.projection_mode = payload.projection_mode
        row.status = payload.status
        row.window_start = payload.window_start.astimezone(UTC)
        row.window_end = payload.window_end.astimezone(UTC)
        row.partition_days = payload.partition_days
        row.batch_size = payload.batch_size
        row.actor_snapshot, row.scope_snapshot = actor.snapshot(), scope
        row.error_code, row.parameter_waiting_code, row.updated_at = None, None, now
        _audit(session, row, "saved", now)
        if transaction is None:
            session.commit()
        else:
            session.flush()
        return row


def _trusted_scope(database: Database, row: SourceBackfillPlan,
                   source: ExternalSystem, session: Session) -> tuple[ActorContext, ScopeContext]:
    resource = session.get(SourceResource, row.source_resource_id)
    if (resource is None or resource.external_system_id != source.id
            or resource.resource_key != row.resource_key
            or resource.version != row.resource_version):
        raise ApiProblem(status_code=409, code="source.backfill_contract_changed",
                         message="资源契约已更新，请新建回填计划")
    account_id = row.actor_snapshot.get("user_account_id")
    if not account_id:
        raise ApiProblem(status_code=403, code="backfill.actor_missing", message="回填发起人不存在")
    actor = resolve_database_actor(
        database, login_name="", user_account_id=str(account_id),
        enterprise_id=row.enterprise_id, request_id=f"backfill-{row.id}",
        run_id=f"backfill-{row.id}")
    require_permission(actor, "source.manage", database, resource_type="source",
        resource_key=source.system_key, scope_type="enterprise", scope_id=row.enterprise_id,
        transaction=session)
    scope = build_scope_context(database, actor, selection=row.scope_snapshot)
    if row.enterprise_id not in scope.selected_enterprise_ids:
        raise ApiProblem(status_code=403, code="backfill.scope_revoked", message="回填范围已失效")
    return actor, scope


def _ranges(session: Session, row: SourceBackfillPlan) -> list[tuple[datetime, datetime]]:
    start, end = _utc(row.cursor), _utc(row.window_end)
    result: list[tuple[datetime, datetime]] = []
    acquired = {(_utc(item.window_start), _utc(item.window_end))
                for item in session.scalars(select(SourceCoverageWindow).where(
                    SourceCoverageWindow.backfill_plan_id == row.id,
                    SourceCoverageWindow.status.in_(ACQUIRED)))}
    while start < end and len(result) < row.batch_size:
        upper = min(end, start + timedelta(days=row.partition_days))
        if (start, upper) not in acquired:
            result.append((start, upper))
        start = upper
    return result


def _recount(session: Session, row: SourceBackfillPlan) -> None:
    windows = list(session.scalars(select(SourceCoverageWindow).where(
        SourceCoverageWindow.backfill_plan_id == row.id).order_by(
            SourceCoverageWindow.window_start)))
    row.windows_succeeded = sum(item.status == "succeeded" for item in windows)
    row.windows_no_data = sum(item.status == "no_data" for item in windows)
    row.windows_with_conflicts = sum(item.status == "succeeded_with_conflicts" for item in windows)
    row.windows_failed = sum(item.status in {"failed", "cancelled"} for item in windows)
    row.records_read = sum(item.records_read for item in windows)
    row.records_written = sum(item.records_written for item in windows)
    cursor = _utc(row.window_start)
    for item in windows:
        if _utc(item.window_start) != cursor or item.status not in ACQUIRED:
            break
        cursor = _utc(item.window_end)
    row.cursor = cursor


def _reconcile(session: Session, row: SourceBackfillPlan, now: datetime) -> bool:
    if not row.active_run_id:
        return True
    refresh_batch(session.connection(), row.active_run_id)
    parent = session.get(SyncRun, row.active_run_id, populate_existing=True)
    if parent is None or parent.status not in TERMINAL:
        changed = False
        windows = list(session.scalars(select(SourceCoverageWindow).where(
            SourceCoverageWindow.backfill_plan_id == row.id,
            SourceCoverageWindow.sync_run_id.is_not(None),
            SourceCoverageWindow.status.in_(["queued", "running"]))))
        for window in windows:
            child = session.get(SyncRun, window.sync_run_id, populate_existing=True)
            if child is not None and child.status == "running" and window.status != "running":
                window.status = "running"
                window.started_at = child.started_at or now
                window.updated_at = now
                changed = True
        if changed:
            row.version += 1
        row.updated_at = now
        return False
    windows = list(session.scalars(select(SourceCoverageWindow).where(
        SourceCoverageWindow.backfill_plan_id == row.id,
        SourceCoverageWindow.sync_run_id.is_not(None),
        SourceCoverageWindow.status.in_(["queued", "running"]))))
    for window in windows:
        child = session.get(SyncRun, window.sync_run_id)
        if child is None or child.status not in TERMINAL:
            return False
        if row.parameter_policy_version:
            if child.status == "succeeded":
                window.records_read += child.records_read
                window.records_written += child.records_written
        else:
            window.records_read, window.records_written = child.records_read, child.records_written
        window.finished_at, window.updated_at = now, now
        if child.status == "succeeded":
            if row.parameter_policy_version and window.parameter_pending_offset is not None:
                window.parameter_fanout_offset = window.parameter_pending_offset
                window.parameter_pending_offset = None
                window.sync_run_id = None
                window.status = "fanout_pending"
                window.finished_at = None
            else:
                window.status = "no_data" if window.records_read == 0 else "succeeded"
                window.parameter_fanout_offset = 0
                window.parameter_pending_offset = None
                window.parameter_cycle_as_of = None
            window.error_code = None
        elif child.status == "partial_failed":
            if row.parameter_policy_version:
                window.status, window.error_code = "failed", "backfill.acquisition_incomplete"
                continue
            resource_runs = list(session.scalars(select(SyncResourceRun).where(
                SyncResourceRun.sync_run_id == child.id)))
            raw_count = session.scalar(select(func.count()).select_from(RawPageManifest).join(
                SyncResourceRun, RawPageManifest.sync_resource_run_id == SyncResourceRun.id).where(
                    SyncResourceRun.sync_run_id == child.id)) or 0
            checkpoint_complete = bool(len(resource_runs) == 1 and session.scalar(
                select(func.count()).select_from(SyncCheckpoint).where(
                    SyncCheckpoint.source_resource_id == resource_runs[0].source_resource_id,
                    SyncCheckpoint.partition_key == resource_runs[0].partition_key,
                    SyncCheckpoint.status == "completed")))
            if raw_count and resource_runs[0].status == "partial_failed" and checkpoint_complete:
                window.status, window.error_code = "succeeded_with_conflicts", "mapping.conflicts"
            else:
                window.status, window.error_code = "failed", "backfill.acquisition_incomplete"
        else:
            window.status = child.status
            window.error_code = f"backfill.child_{child.status}"
    row.active_run_id = None
    _recount(session, row)
    row.version += 1
    if row.windows_failed:
        row.status, row.error_code = "needs_attention", "backfill.window_failed"
        _audit(session, row, "blocked", now)
    elif _utc(row.cursor) >= _utc(row.window_end):
        row.status, row.error_code = "completed", None
        _audit(session, row, "completed", now)
    row.updated_at = now
    return True


def _coverage_for_range(session: Session, row: SourceBackfillPlan, *,
                        start: datetime, end: datetime,
                        now: datetime) -> SourceCoverageWindow:
    coverage = session.scalar(select(SourceCoverageWindow).where(
        SourceCoverageWindow.backfill_plan_id == row.id,
        SourceCoverageWindow.window_start == start,
        SourceCoverageWindow.window_end == end).with_for_update())
    if coverage is None:
        coverage = SourceCoverageWindow(id=f"coverage_{uuid4().hex}",
            enterprise_id=row.enterprise_id, backfill_plan_id=row.id,
            external_system_id=row.external_system_id,
            source_resource_id=row.source_resource_id,
            resource_version=row.resource_version, resource_key=row.resource_key,
            partition_key=stable_key(
                row.resource_key, json.dumps(row.resource_parameters or {}, sort_keys=True),
                start.isoformat(), end.isoformat()),
            resource_parameters=row.resource_parameters or {},
            window_start=start, window_end=end, status="fanout_pending",
            created_at=now, updated_at=now)
        session.add(coverage)
        session.flush()
    return coverage


def _queue_parameter_batch(database: Database, session: Session, row: SourceBackfillPlan,
                           source: ExternalSystem, actor: ActorContext, scope: ScopeContext,
                           now: datetime,
                           ranges: list[tuple[datetime, datetime]]) -> bool:
    if row.parameter_policy_version != PARAMETER_POLICY_VERSION:
        raise ValueError("source.backfill_parameter_policy_changed")
    start, end = ranges[0]
    coverage = _coverage_for_range(session, row, start=start, end=end, now=now)
    cycle_as_of = (_utc(coverage.parameter_cycle_as_of)
                   if coverage.parameter_cycle_as_of else now.astimezone(UTC))
    coverage.parameter_cycle_as_of = cycle_as_of
    offset = coverage.parameter_fanout_offset
    page = plan_parameter_fanout(session,
        external_system_id=row.external_system_id,
        resource_key=row.resource_key,
        base_parameters=row.resource_parameters or {},
        as_of=end,
        dependency_as_of=cycle_as_of,
        offset=offset,
        limit=32)
    coverage.parameter_fanout_total = page.total
    row.parameter_waiting_code = page.waiting_code
    if page.waiting_code:
        coverage.parameter_cycle_as_of = None
        coverage.status = "fanout_pending"
        coverage.error_code = page.waiting_code
        coverage.updated_at = now
        row.status = "waiting_for_dependency"
        row.error_code = page.waiting_code
        row.updated_at = now
        row.version += 1
        _audit(session, row, "waiting", now)
        return False
    if not page.items:
        raise ValueError("source.parameter_fanout_cursor_invalid")
    selections = [ImportSelection(resource_key=row.resource_key,
        resource_parameters=parameters, window_start=start, window_end=end)
        for parameters in page.items]
    attempt = (coverage.attempt_count or 0) + 1
    parent = enqueue_import(database, enterprise_id=row.enterprise_id,
        source_key=source.system_key, initiator_id=actor.principal_id,
        request_id=f"backfill-{uuid4().hex}", payload=ImportRequest(
            client_request_key=f"{row.id}:{coverage.id}:{offset}:{attempt}",
            projection_mode=cast(Literal["inline", "deferred"], row.projection_mode),
            selections=selections, partition_days=row.partition_days),
        scope_snapshot=scope.snapshot(), actor_snapshot=actor.snapshot(),
        provider_enabled=True, transaction=session)
    coverage.sync_run_id = parent.id
    coverage.status = "queued"
    coverage.parameter_pending_offset = page.next_offset
    coverage.error_code, coverage.finished_at = None, None
    coverage.attempt_count = attempt
    coverage.started_at, coverage.updated_at = None, now
    row.active_run_id = parent.id
    row.status = "active"
    row.error_code = row.parameter_waiting_code = None
    row.updated_at = now
    row.version += 1
    _audit(session, row, "queued", now)
    return True


def _queue_batch(database: Database, session: Session, row: SourceBackfillPlan,
                 source: ExternalSystem, actor: ActorContext, scope: ScopeContext,
                 now: datetime) -> bool:
    ranges = _ranges(session, row)
    if not ranges:
        row.status, row.error_code, row.updated_at = "completed", None, now
        row.version += 1
        _audit(session, row, "completed", now)
        return False
    if row.parameter_policy_version:
        return _queue_parameter_batch(
            database, session, row, source, actor, scope, now, ranges)
    selections = [ImportSelection(resource_key=row.resource_key,
        resource_parameters=row.resource_parameters or {}, window_start=start, window_end=end)
        for start, end in ranges]
    attempt = max((session.scalar(select(func.max(SourceCoverageWindow.attempt_count)).where(
        SourceCoverageWindow.backfill_plan_id == row.id)) or 0) + 1, 1)
    parent = enqueue_import(database, enterprise_id=row.enterprise_id,
        source_key=source.system_key, initiator_id=actor.principal_id,
        request_id=f"backfill-{uuid4().hex}", payload=ImportRequest(
            client_request_key=f"{row.id}:{row.version}:{attempt}:{ranges[0][0].isoformat()}",
            projection_mode=cast(Literal["inline", "deferred"], row.projection_mode),
            selections=selections, partition_days=row.partition_days),
        scope_snapshot=scope.snapshot(), actor_snapshot=actor.snapshot(),
        provider_enabled=True, transaction=session)
    children = list(session.scalars(select(SyncRun).where(SyncRun.parent_run_id == parent.id)))
    jobs = {child.id: session.get(BackgroundJob, child.task_id) for child in children}
    child_by_range = {(_utc(datetime.fromisoformat(str(job.payload["window_start"]))),
                       _utc(datetime.fromisoformat(str(job.payload["window_end"])))): child
                      for child in children if (job := jobs[child.id]) is not None}
    for start, end in ranges:
        coverage = _coverage_for_range(session, row, start=start, end=end, now=now)
        child = child_by_range[(start, end)]
        coverage.sync_run_id, coverage.status = child.id, "queued"
        coverage.records_read = coverage.records_written = 0
        coverage.error_code, coverage.finished_at = None, None
        coverage.attempt_count = (coverage.attempt_count or 0) + 1
        coverage.started_at, coverage.updated_at = None, now
    row.active_run_id, row.updated_at = parent.id, now
    row.version += 1
    _audit(session, row, "queued", now)
    return True


def dispatch_backfills(database: Database, *, provider_enabled: bool,
                       now: datetime | None = None, limit: int = 10) -> int:
    if not provider_enabled:
        return 0
    now = now or datetime.now(UTC)
    dispatched = 0
    with database.session() as session:
        running = list(session.scalars(select(SourceBackfillPlan).where(
            SourceBackfillPlan.active_run_id.is_not(None),
        ).order_by(SourceBackfillPlan.updated_at).limit(max(100, limit * 10))
            .with_for_update(skip_locked=True)))
        for row in running:
            try:
                _reconcile(session, row, now)
            except (ApiProblem, ValueError) as exc:
                row.status = "needs_attention"
                row.error_code = exc.code if isinstance(exc, ApiProblem) else str(exc)
                row.active_run_id, row.updated_at = None, now
                _audit(session, row, "blocked", now)
        rows = list(session.scalars(select(SourceBackfillPlan).where(
            SourceBackfillPlan.status.in_(["active", "waiting_for_dependency"]),
            SourceBackfillPlan.active_run_id.is_(None),
        ).order_by(SourceBackfillPlan.updated_at).limit(limit).with_for_update(skip_locked=True)))
        for row in rows:
            try:
                source = session.get(ExternalSystem, row.external_system_id)
                if source is None or source.status == "disabled":
                    raise ApiProblem(status_code=409, code="source.disabled", message="来源已停用")
                actor, scope = _trusted_scope(database, row, source, session)
                if _queue_batch(database, session, row, source, actor, scope, now):
                    dispatched += 1
            except (ApiProblem, ValueError) as exc:
                row.status = "needs_attention"
                row.error_code = exc.code if isinstance(exc, ApiProblem) else str(exc)
                row.active_run_id, row.updated_at = None, now
                _audit(session, row, "blocked", now)
        session.commit()
    return dispatched
