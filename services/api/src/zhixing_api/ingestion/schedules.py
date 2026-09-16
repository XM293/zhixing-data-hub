from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session
from zhixing_connectors.catalog import resource_spec
from zhixing_connectors.parameter_policies import PARAMETER_POLICY_VERSION

from zhixing_api.actor_context import ActorContext, require_permission, resolve_database_actor
from zhixing_api.data_models import (
    ExternalSystem,
    PlatformEvent,
    SourceResource,
    SourceSyncSchedule,
    SyncRun,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.scope_context import ScopeContext, build_scope_context

from .batches import TERMINAL, enqueue_import, refresh_batch
from .parameter_fanout import plan_parameter_fanout, validate_parameter_fanout_base
from .planning import ImportRequest, ImportSelection, ScheduleRequest, schedule_strategy


class ScheduleView(BaseModel):
    projection_mode: str
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    resource_key: str
    resource_version: str
    resource_parameters: dict[str, str]
    parameter_policy_version: str | None
    parameter_fanout_offset: int
    parameter_fanout_total: int
    parameter_waiting_code: str | None
    strategy: str
    status: str
    interval_seconds: int
    overlap_seconds: int
    safety_lag_seconds: int
    reconcile_days: int
    initial_start: datetime | None
    watermark: datetime | None
    active_run_id: str | None
    next_run_at: datetime
    last_success_at: datetime | None
    error_code: str | None
    version: int


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _audit(session: Session, row: SourceSyncSchedule, action: str, now: datetime) -> None:
    session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=row.enterprise_id,
        event_type=f"source.schedule_{action}", severity="warning" if row.error_code else "info",
        title="采集计划状态更新", detail=f"schedule_id={row.id}; status={row.status}; "
        f"version={row.version}; error_code={row.error_code or ''}", occurred_at=now))


def save_schedule(database: Database, *, actor: ActorContext, source_key: str,
                  payload: ScheduleRequest, scope: dict[str, object],
                  schedule_id: str | None = None, now: datetime | None = None,
                  expected_version: int | None = None,
                  transaction: Session | None = None,
                  allow_contract_rebind: bool = False) -> SourceSyncSchedule:
    now = now or datetime.now(UTC)
    require_permission(actor, "source.manage", database, resource_type="source",
                       resource_key=source_key, scope_type="enterprise",
                       scope_id=actor.enterprise_id, transaction=transaction)
    session_context = nullcontext(transaction) if transaction is not None else database.session()
    with session_context as session:
        assert session is not None
        row = (session.scalar(select(SourceSyncSchedule).where(
            SourceSyncSchedule.id == schedule_id,
            SourceSyncSchedule.enterprise_id == actor.enterprise_id).with_for_update())
            if schedule_id else None)
        if schedule_id and row is None:
            raise ApiProblem(status_code=404, code="source.schedule_not_found",
                             message="采集计划不存在")
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key).with_for_update())
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        if source.provider_key != "lingxing" and source.system_type != "lingxing":
            raise ApiProblem(status_code=422, code="source.provider_unsupported",
                             message="来源不支持采集计划")
        if row is not None and row.external_system_id != source.id:
            raise ApiProblem(status_code=404, code="source.schedule_not_found",
                             message="采集计划不存在")
        resource = session.scalar(select(SourceResource).where(
            SourceResource.external_system_id == source.id,
            SourceResource.resource_key == payload.resource_key))
        if resource is None or not resource.enabled or resource.schema_status == "schema_pending":
            raise ApiProblem(status_code=422, code="source.resource_disabled",
                             message="资源尚未具备受控采集条件")
        spec = resource_spec(payload.resource_key)
        if spec is not None and spec.mapping_key is None and (
                resource.validation_status != "validated"):
            raise ApiProblem(status_code=422, code="source.resource_not_validated",
                             message="Raw 资源必须先完成单页契约验证")
        if row is not None:
            if expected_version is not None and row.version != expected_version:
                raise ApiProblem(status_code=409, code="source.schedule_changed",
                                 message="采集计划已更新，请刷新")
            if row.active_run_id:
                raise ApiProblem(status_code=409, code="source.schedule_busy",
                                 message="采集批次正在运行，请先取消或等待结束")
            if row.resource_version != resource.version and not allow_contract_rebind:
                raise ApiProblem(status_code=409, code="source.schedule_contract_changed",
                                 message="资源契约已更新，请新建采集计划")
            if (row.resource_key != payload.resource_key or row.strategy != payload.strategy
                    or row.resource_parameters != payload.resource_parameters
                    or (utc(row.initial_start) if row.initial_start else None)
                    != payload.initial_start):
                raise ApiProblem(status_code=409, code="source.schedule_identity_changed",
                                 message="资源、策略或起点变更需要新建计划")
            row.version += 1
        else:
            row = SourceSyncSchedule(id=f"schedule_{uuid4().hex}",
                                     enterprise_id=actor.enterprise_id,
                                     external_system_id=source.id, created_at=now, version=1)
            session.add(row)
        previous_policy_version = row.parameter_policy_version
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        try:
            validate_parameter_fanout_base(payload.resource_key, payload.resource_parameters)
            row.parameter_policy_version = PARAMETER_POLICY_VERSION
        except ValueError:
            row.parameter_policy_version = None
        if previous_policy_version != row.parameter_policy_version:
            row.parameter_fanout_offset = 0
            row.parameter_pending_offset = None
            row.parameter_fanout_total = 1
            row.parameter_cycle_as_of = None
            row.parameter_waiting_code = None
        row.resource_version = resource.version
        row.actor_snapshot, row.scope_snapshot = actor.snapshot(), scope
        row.updated_at, row.next_run_at, row.error_code = now, now, None
        _audit(session, row, "saved", now)
        if transaction is None:
            session.commit()
        else:
            session.flush()
        return row


def _trusted_scope(database: Database, row: SourceSyncSchedule,
                   source: ExternalSystem, session: Session) -> tuple[ActorContext, ScopeContext]:
    resource = session.scalar(select(SourceResource).where(
        SourceResource.external_system_id == source.id,
        SourceResource.resource_key == row.resource_key))
    if resource is None or resource.version != row.resource_version:
        raise ApiProblem(status_code=409, code="source.schedule_contract_changed",
                         message="资源契约已更新，请新建采集计划")
    account_id = row.actor_snapshot.get("user_account_id")
    if not account_id:
        raise ApiProblem(status_code=403, code="schedule.actor_missing", message="采集发起人不存在")
    actor = resolve_database_actor(database, login_name="", user_account_id=str(account_id),
                                   enterprise_id=row.enterprise_id,
                                   request_id=f"schedule-{row.id}", run_id=f"schedule-{row.id}")
    require_permission(actor, "source.manage", database, resource_type="source",
                       resource_key=source.system_key, scope_type="enterprise",
                       scope_id=row.enterprise_id, transaction=session)
    scope = build_scope_context(database, actor, selection=row.scope_snapshot)
    if row.enterprise_id not in scope.selected_enterprise_ids:
        raise ApiProblem(status_code=403, code="schedule.scope_revoked", message="采集范围已失效")
    return actor, scope


def dispatch_due(database: Database, *, provider_enabled: bool,
                 now: datetime | None = None, limit: int = 20) -> int:
    if not provider_enabled:
        return 0
    now = now or datetime.now(UTC)
    dispatched = 0
    with database.session() as session:
        # Reconciliation has its own budget. Otherwise long-running schedules can occupy
        # the whole limited query and indefinitely starve schedules that are ready to queue.
        running = list(session.scalars(select(SourceSyncSchedule).where(
            SourceSyncSchedule.next_run_at <= now,
            SourceSyncSchedule.active_run_id.is_not(None),
        ).order_by(SourceSyncSchedule.next_run_at).limit(max(100, limit * 10))
            .with_for_update(skip_locked=True)))
        for row in running:
            active_run_id = row.active_run_id
            if active_run_id is None:
                continue
            refresh_batch(session.connection(), active_run_id)
            parent = session.get(SyncRun, active_run_id, populate_existing=True)
            if parent is None or parent.status not in TERMINAL:
                row.next_run_at = now + timedelta(seconds=30)
                continue
            row.active_run_id = None
            if parent.status != "succeeded":
                row.status = "needs_attention"
                row.error_code = f"schedule.batch_{parent.status}"
                _audit(session, row, "blocked", now)
                continue
            if row.parameter_policy_version and row.parameter_pending_offset is not None:
                row.parameter_fanout_offset = row.parameter_pending_offset
                row.parameter_pending_offset = None
                row.next_run_at = now + timedelta(seconds=1)
                row.updated_at = now
                _audit(session, row, "fanout_advanced", now)
                continue
            row.watermark = (row.pending_end
                             if row.strategy in {"updated_utc", "source_window"} else None)
            row.last_success_at = now
            if row.pending_reconciliation or row.last_reconciled_at is None:
                row.last_reconciled_at = now
            row.pending_end, row.pending_reconciliation = None, False
            row.parameter_fanout_offset = 0
            row.parameter_pending_offset = None
            row.parameter_cycle_as_of = None
            row.parameter_waiting_code = None
            row.next_run_at = now + timedelta(seconds=row.interval_seconds)
            row.updated_at = now
            _audit(session, row, "succeeded", now)
        # One transaction owns each ready schedule until its activity marker and jobs commit.
        ready = list(session.scalars(select(SourceSyncSchedule).where(
            SourceSyncSchedule.next_run_at <= now,
            SourceSyncSchedule.active_run_id.is_(None),
            SourceSyncSchedule.status.in_(["active", "waiting_for_dependency"]),
        ).order_by(SourceSyncSchedule.next_run_at).limit(limit)
            .with_for_update(skip_locked=True)))
        for row in ready:
            source = session.get(ExternalSystem, row.external_system_id)
            try:
                if source is None or source.status == "disabled":
                    raise ApiProblem(status_code=409, code="source.disabled", message="来源已停用")
                actor, scope = _trusted_scope(database, row, source, session)
                request = _next_import(row, now, session=session)
                if request is None:
                    if row.parameter_waiting_code:
                        row.parameter_cycle_as_of = None
                        row.status = "waiting_for_dependency"
                        row.error_code = row.parameter_waiting_code
                        row.next_run_at = now + timedelta(
                            seconds=min(row.interval_seconds, 300))
                        row.updated_at = now
                        _audit(session, row, "waiting", now)
                    else:
                        row.next_run_at = now + timedelta(seconds=row.interval_seconds)
                    continue
                row.status = "active"
                row.error_code = None
                with session.begin_nested():
                    parent = enqueue_import(database, enterprise_id=row.enterprise_id,
                        source_key=source.system_key, initiator_id=actor.principal_id,
                        request_id=f"schedule-{uuid4().hex}", payload=request,
                        scope_snapshot=scope.snapshot(), actor_snapshot=actor.snapshot(),
                        provider_enabled=provider_enabled, transaction=session)
                    row.active_run_id = parent.id
                    row.next_run_at = now + timedelta(seconds=30)
                    row.pending_end = request.selections[0].window_end
                    row.updated_at = now
                    _audit(session, row, "queued", now)
                dispatched += 1
            except (ApiProblem, ValueError) as exc:
                row.status = "needs_attention"
                row.error_code = (exc.code if isinstance(exc, ApiProblem)
                                  else "schedule.plan_invalid")
                row.pending_end, row.pending_reconciliation = None, False
                row.updated_at = now
                _audit(session, row, "blocked", now)
        session.commit()
    return dispatched


def _next_import(row: SourceSyncSchedule, now: datetime,
                 *, session: Session | None = None) -> ImportRequest | None:
    start: datetime | None = None
    end: datetime | None = None
    spec = resource_spec(row.resource_key)
    single_date = bool(spec is not None and len(spec.window_fields) == 1)
    if row.strategy in {"updated_utc", "source_window"}:
        if row.initial_start is None or schedule_strategy(row.resource_key) != row.strategy:
            raise ValueError("schedule.strategy_invalid")
        floor = utc(row.initial_start)
        previous = utc(row.watermark) if row.watermark else floor
        if single_date:
            floor = floor.replace(hour=0, minute=0, second=0, microsecond=0)
            previous = previous.replace(hour=0, minute=0, second=0, microsecond=0)
            available = (now - timedelta(seconds=row.safety_lag_seconds)).replace(
                hour=0, minute=0, second=0, microsecond=0)
            start = max(floor, previous - (timedelta(days=1) if row.watermark else timedelta()))
            end = min(available, previous + timedelta(days=7))
        else:
            start = max(floor, previous - timedelta(seconds=row.overlap_seconds))
            end = min(now - timedelta(seconds=row.safety_lag_seconds),
                      previous + timedelta(days=7))
        reconcile = row.last_reconciled_at is not None and (
            now - utc(row.last_reconciled_at) >= timedelta(days=1))
        if reconcile:
            start = max(floor, previous - timedelta(days=row.reconcile_days))
        row.pending_reconciliation = reconcile
        if end <= start or end <= previous:
            return None
    parameters = [row.resource_parameters or {}]
    offset = 0
    parameter_policy_version = getattr(row, "parameter_policy_version", None)
    if parameter_policy_version:
        if parameter_policy_version != PARAMETER_POLICY_VERSION or session is None:
            raise ValueError("schedule.parameter_policy_changed")
        cycle_as_of = (utc(row.parameter_cycle_as_of) if row.parameter_cycle_as_of
                       else (end or now).astimezone(UTC))
        row.parameter_cycle_as_of = cycle_as_of
        offset = row.parameter_fanout_offset
        page = plan_parameter_fanout(session, external_system_id=row.external_system_id,
            resource_key=row.resource_key, base_parameters=row.resource_parameters or {},
            as_of=cycle_as_of, offset=offset, limit=32)
        row.parameter_fanout_total = page.total
        row.parameter_waiting_code = page.waiting_code
        if page.waiting_code:
            return None
        parameters = page.items
        row.parameter_pending_offset = page.next_offset
    selections = [ImportSelection(resource_key=row.resource_key,
        resource_parameters=item, window_start=start, window_end=end) for item in parameters]
    return ImportRequest(client_request_key=(
        f"{row.id}:{row.version}:{offset}:{uuid4().hex}"),
        partition_days=1 if single_date else 7,
        projection_mode=cast(Literal["inline", "deferred"], row.projection_mode),
        selections=selections)
