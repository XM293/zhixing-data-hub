from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from zhixing_connectors.catalog import OFFICIAL_RAW_SPECS, ResourceSpec
from zhixing_connectors.parameter_policies import (
    PARAMETER_POLICY_VERSION,
    parameter_policy,
)

from zhixing_api.actor_context import ActorContext, require_permission
from zhixing_api.data_models import (
    ExternalSystem,
    SourceBackfillPlan,
    SourceBinding,
    SourceResource,
    SourceSyncSchedule,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.scope_context import ScopeContext

from .backfills import BackfillRequest, save_backfill
from .planning import ScheduleRequest, schedule_strategy
from .schedules import save_schedule, utc


class OfficialScheduleRolloutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    business_unit_id: str | None = Field(default=None, min_length=1, max_length=64)
    status: Literal["paused", "active"] = "paused"
    incremental_start: datetime
    window_interval_seconds: int = Field(default=3600, ge=60, le=86400)
    snapshot_interval_seconds: int = Field(default=86400, ge=60, le=86400)
    overlap_seconds: int = Field(default=300, ge=1, le=86400)
    safety_lag_seconds: int = Field(default=300, ge=0, le=3600)
    reconcile_days: int = Field(default=7, ge=1, le=30)

    @model_validator(mode="after")
    def require_utc_start(self) -> OfficialScheduleRolloutRequest:
        if self.incremental_start.tzinfo is None:
            raise ValueError("source.rollout_start_timezone_required")
        return self


class OfficialScheduleRolloutView(BaseModel):
    business_unit_id: str
    approved_store_count: int
    validated_resource_count: int
    planned_schedule_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    status: Literal["paused", "active"]


class OfficialBackfillRolloutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    business_unit_id: str | None = Field(default=None, min_length=1, max_length=64)
    status: Literal["paused", "active"] = "paused"
    history_start: datetime
    history_end: datetime
    batch_size: int = Field(default=16, ge=1, le=32)

    @model_validator(mode="after")
    def validate_history_window(self) -> OfficialBackfillRolloutRequest:
        if (self.history_start.tzinfo is None or self.history_end.tzinfo is None
                or self.history_start >= self.history_end):
            raise ValueError("source.rollout_history_window_required")
        if self.history_end - self.history_start > timedelta(days=366 * 40):
            raise ValueError("source.backfill_range_too_large")
        return self


class OfficialBackfillRolloutView(BaseModel):
    business_unit_id: str
    approved_store_count: int
    validated_resource_count: int
    planned_backfill_count: int
    planned_window_count: int
    created_count: int
    updated_count: int
    unchanged_count: int
    retention_clamped_count: int
    status: Literal["paused", "active"]


def _extra_parameters(spec: ResourceSpec) -> set[str]:
    return (set(spec.required_parameters) - set(spec.window_fields)
            - ({str(spec.scope_parameter)} if spec.scope_parameter else set()))


def _parameter_policy_version(spec: ResourceSpec) -> str | None:
    if not _extra_parameters(spec):
        return None
    policy = parameter_policy(spec.key)
    return (PARAMETER_POLICY_VERSION
            if policy is not None and policy.status == "ready_for_bounded_fanout" else None)


def _schedule_name(spec: ResourceSpec, parameters: dict[str, str]) -> str:
    digest = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()[:10]
    return f"official-{spec.wave.lower()}-{spec.key[:88]}-{digest}"


def _backfill_name(spec: ResourceSpec, parameters: dict[str, str]) -> str:
    digest = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()[:10]
    return f"official-history-{spec.wave.lower()}-{spec.key[:80]}-{digest}"


def _schedule_matches(row: SourceSyncSchedule, payload: ScheduleRequest) -> bool:
    current_start = utc(row.initial_start) if row.initial_start else None
    return (
        row.name == payload.name
        and row.projection_mode == payload.projection_mode
        and row.strategy == payload.strategy
        and row.status == payload.status
        and row.interval_seconds == payload.interval_seconds
        and row.overlap_seconds == payload.overlap_seconds
        and row.safety_lag_seconds == payload.safety_lag_seconds
        and row.reconcile_days == payload.reconcile_days
        and current_start == payload.initial_start
    )


def _backfill_matches(row: SourceBackfillPlan, payload: BackfillRequest) -> bool:
    return (
        row.name == payload.name
        and row.projection_mode == payload.projection_mode
        and row.status == payload.status
        and row.batch_size == payload.batch_size
    )


def _resolve_store_rollout_context(
    session: Session,
    *,
    actor: ActorContext,
    source_key: str,
    business_unit_id: str | None,
    scope: ScopeContext,
) -> tuple[ExternalSystem, str, tuple[SourceBinding, ...], dict[str, SourceResource]]:
    source = session.scalar(select(ExternalSystem).where(
        ExternalSystem.enterprise_id == actor.enterprise_id,
        ExternalSystem.system_key == source_key).with_for_update())
    if source is None:
        raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
    if source.provider_key != "lingxing" and source.system_type != "lingxing":
        raise ApiProblem(status_code=422, code="source.provider_unsupported",
                         message="来源不支持官方资源计划")
    resolved_business_unit_id = business_unit_id or source.business_unit_id
    if resolved_business_unit_id is None:
        raise ApiProblem(status_code=422, code="source.business_unit_required",
                         message="数据源必须归属于业务单元")
    if source.business_unit_id not in {None, resolved_business_unit_id}:
        raise ApiProblem(status_code=409, code="source.business_unit_mismatch",
                         message="数据源与业务单元不一致")
    if resolved_business_unit_id not in scope.business_unit_ids:
        raise ApiProblem(status_code=403, code="scope.business_unit_denied",
                         message="业务单元不在当前授权范围内")

    bindings = list(session.scalars(select(SourceBinding).where(
        SourceBinding.enterprise_id == actor.enterprise_id,
        SourceBinding.source_system_id == source.id,
        SourceBinding.business_unit_id == resolved_business_unit_id,
        SourceBinding.canonical_type == "store",
        SourceBinding.status == "approved").order_by(SourceBinding.external_key)))
    if not bindings:
        raise ApiProblem(status_code=422, code="source.approved_store_required",
                         message="业务单元尚无已审核店铺")

    resources = {row.resource_key: row for row in session.scalars(
        select(SourceResource).where(
            SourceResource.external_system_id == source.id,
            SourceResource.enabled.is_(True),
            SourceResource.schema_status == "confirmed",
            SourceResource.validation_status == "validated",
        ))}
    return source, resolved_business_unit_id, tuple(bindings), resources


def _store_ids_for_resource(spec: ResourceSpec,
                            bindings: tuple[SourceBinding, ...]) -> tuple[str, ...]:
    namespace = spec.scope_namespace or "amazon"
    values: list[str] = []
    for row in bindings:
        value = row.external_key.removeprefix("store:").strip()
        if namespace == "multiplatform":
            value = value.removeprefix("multiplatform:") if value.startswith(
                "multiplatform:") else ""
        elif value.startswith("multiplatform:"):
            value = ""
        if value.isascii() and value.isdecimal() and int(value) > 0:
            values.append(str(int(value)))
    return tuple(dict.fromkeys(values))


def rollout_validated_store_schedules(
    database: Database,
    *,
    actor: ActorContext,
    source_key: str,
    payload: OfficialScheduleRolloutRequest,
    scope: ScopeContext,
    now: datetime | None = None,
) -> OfficialScheduleRolloutView:
    """Atomically create or update schedules for validated, parameter-complete store resources."""
    now = now or datetime.now(UTC)
    require_permission(actor, "source.manage", database, resource_type="source",
                       resource_key=source_key, scope_type="enterprise",
                       scope_id=actor.enterprise_id)
    with database.session() as session:
        source, business_unit_id, store_bindings, resources = (
            _resolve_store_rollout_context(
                session, actor=actor, source_key=source_key,
                business_unit_id=payload.business_unit_id, scope=scope))
        candidates: list[tuple[ResourceSpec, dict[str, str], ScheduleRequest]] = []
        for spec in sorted(OFFICIAL_RAW_SPECS, key=lambda item: (item.wave, item.key)):
            resource = resources.get(spec.key)
            if (resource is None or spec.scope_kind != "store" or not spec.scope_parameter
                    or (_extra_parameters(spec) and _parameter_policy_version(spec) is None)):
                continue
            external_store_ids = _store_ids_for_resource(spec, store_bindings)
            if not external_store_ids:
                continue
            partitions = (external_store_ids if spec.scope_parameter_mode == "scalar"
                          else (",".join(external_store_ids),))
            for value in partitions:
                parameters = {spec.scope_parameter: value}
                strategy = schedule_strategy(spec.key)
                if strategy is None:
                    continue
                request = ScheduleRequest(
                    name=_schedule_name(spec, parameters),
                    resource_key=spec.key,
                    resource_parameters=parameters,
                    projection_mode="deferred",
                    strategy=cast(Literal["updated_utc", "source_window", "snapshot"], strategy),
                    status=payload.status,
                    interval_seconds=(payload.window_interval_seconds
                                      if spec.window_fields else payload.snapshot_interval_seconds),
                    overlap_seconds=payload.overlap_seconds,
                    safety_lag_seconds=payload.safety_lag_seconds,
                    reconcile_days=payload.reconcile_days,
                    initial_start=(payload.incremental_start if spec.window_fields else None),
                )
                candidates.append((spec, parameters, request))
        if not candidates:
            raise ApiProblem(status_code=422, code="source.validated_resources_required",
                             message="没有可安全编排的已验证店铺资源")

        existing_rows = list(session.scalars(select(SourceSyncSchedule).where(
            SourceSyncSchedule.enterprise_id == actor.enterprise_id,
            SourceSyncSchedule.external_system_id == source.id)))
        existing: dict[tuple[str, str], list[SourceSyncSchedule]] = {}
        for row in existing_rows:
            identity = (row.resource_key,
                        json.dumps(row.resource_parameters or {}, sort_keys=True))
            existing.setdefault(identity, []).append(row)

        planned: list[tuple[SourceResource, ScheduleRequest, SourceSyncSchedule | None]] = []
        for spec, parameters, request in candidates:
            identity = (spec.key, json.dumps(parameters, sort_keys=True))
            matches = existing.get(identity, [])
            if len(matches) > 1:
                raise ApiProblem(status_code=409, code="source.rollout_duplicate_schedule",
                                 message="已有重复的官方资源计划")
            current = matches[0] if matches else None
            resource = resources[spec.key]
            if current is not None and (
                    current.strategy != request.strategy
                    or (utc(current.initial_start) if current.initial_start else None)
                    != request.initial_start):
                raise ApiProblem(status_code=409, code="source.rollout_identity_conflict",
                                 message="已有计划的契约或历史起点不同")
            if (current is not None and current.active_run_id
                    and (current.resource_version != resource.version
                         or current.parameter_policy_version != _parameter_policy_version(spec)
                         or not _schedule_matches(current, request))):
                raise ApiProblem(status_code=409, code="source.rollout_schedule_busy",
                                 message="已有计划正在运行")
            planned.append((resource, request, current))

        created = updated = unchanged = 0
        snapshot = scope.snapshot()
        for resource, request, current in planned:
            spec = next(item for item in OFFICIAL_RAW_SPECS
                        if item.key == request.resource_key)
            if (current is not None and current.resource_version == resource.version
                    and current.parameter_policy_version == _parameter_policy_version(spec)
                    and _schedule_matches(current, request)):
                unchanged += 1
                continue
            save_schedule(database, actor=actor, source_key=source_key, payload=request,
                scope=snapshot, schedule_id=current.id if current else None,
                expected_version=current.version if current else None, now=now,
                transaction=session, allow_contract_rebind=True)
            if current is None:
                created += 1
            else:
                updated += 1
        session.commit()
        return OfficialScheduleRolloutView(
            business_unit_id=business_unit_id,
            approved_store_count=len(store_bindings),
            validated_resource_count=len({spec.key for spec, _, _ in candidates}),
            planned_schedule_count=len(planned), created_count=created,
            updated_count=updated, unchanged_count=unchanged, status=payload.status,
        )


def rollout_validated_store_backfills(
    database: Database,
    *,
    actor: ActorContext,
    source_key: str,
    payload: OfficialBackfillRolloutRequest,
    scope: ScopeContext,
    now: datetime | None = None,
) -> OfficialBackfillRolloutView:
    """Atomically plan history for validated store resources without issuing provider calls."""
    now = now or datetime.now(UTC)
    require_permission(actor, "source.manage", database, resource_type="source",
                       resource_key=source_key, scope_type="enterprise",
                       scope_id=actor.enterprise_id)
    with database.session() as session:
        source, business_unit_id, store_bindings, resources = (
            _resolve_store_rollout_context(
                session, actor=actor, source_key=source_key,
                business_unit_id=payload.business_unit_id, scope=scope))
        requested_start = payload.history_start.astimezone(UTC)
        history_end = payload.history_end.astimezone(UTC)
        candidates: list[tuple[ResourceSpec, BackfillRequest, int, bool]] = []
        for spec in sorted(OFFICIAL_RAW_SPECS, key=lambda item: (item.wave, item.key)):
            resource = resources.get(spec.key)
            if (resource is None or spec.scope_kind != "store" or not spec.scope_parameter
                    or not spec.window_fields
                    or (_extra_parameters(spec) and _parameter_policy_version(spec) is None)):
                continue
            external_store_ids = _store_ids_for_resource(spec, store_bindings)
            if not external_store_ids:
                continue
            partitions = (external_store_ids if spec.scope_parameter_mode == "scalar"
                          else (",".join(external_store_ids),))
            retention_start = (history_end - timedelta(days=spec.retention_days)
                               if spec.retention_days is not None else requested_start)
            effective_start = max(requested_start, retention_start)
            if effective_start >= history_end:
                continue
            partition_days = 1 if len(spec.window_fields) == 1 else spec.max_window_days
            for value in partitions:
                parameters = {str(spec.scope_parameter): value}
                request = BackfillRequest(
                    name=_backfill_name(spec, parameters),
                    resource_key=spec.key,
                    resource_parameters=parameters,
                    projection_mode="deferred",
                    status=payload.status,
                    window_start=effective_start,
                    window_end=history_end,
                    partition_days=partition_days,
                    batch_size=payload.batch_size,
                )
                windows = ceil((history_end - effective_start)
                               / timedelta(days=partition_days))
                candidates.append((spec, request, windows, effective_start > requested_start))
        if not candidates:
            raise ApiProblem(status_code=422, code="source.validated_history_resources_required",
                             message="没有可安全编排的已验证历史资源")

        existing_rows = list(session.scalars(select(SourceBackfillPlan).where(
            SourceBackfillPlan.enterprise_id == actor.enterprise_id,
            SourceBackfillPlan.external_system_id == source.id)))
        existing: dict[tuple[object, ...], list[SourceBackfillPlan]] = {}
        for row in existing_rows:
            identity = (
                row.resource_key,
                json.dumps(row.resource_parameters or {}, sort_keys=True),
                utc(row.window_start),
                utc(row.window_end),
                row.partition_days,
            )
            existing.setdefault(identity, []).append(row)

        planned: list[tuple[BackfillRequest, SourceBackfillPlan | None]] = []
        for spec, request, _, _ in candidates:
            resource = resources[spec.key]
            identity = (
                spec.key,
                json.dumps(request.resource_parameters, sort_keys=True),
                request.window_start,
                request.window_end,
                request.partition_days,
            )
            matches = existing.get(identity, [])
            if len(matches) > 1:
                raise ApiProblem(status_code=409, code="source.rollout_duplicate_backfill",
                                 message="已有重复的官方历史回填计划")
            current = matches[0] if matches else None
            if current is not None and current.status == "completed":
                planned.append((request, current))
                continue
            if (current is not None and current.active_run_id
                    and (current.parameter_policy_version != _parameter_policy_version(spec)
                         or not _backfill_matches(current, request))):
                raise ApiProblem(status_code=409, code="source.rollout_backfill_busy",
                                 message="已有历史回填计划正在运行")
            planned.append((request, current))

        created = updated = unchanged = 0
        snapshot = scope.snapshot()
        for request, current in planned:
            if current is not None and (current.status == "completed"
                                        or (
                                            current.resource_version
                                            == resources[request.resource_key].version
                                            and current.parameter_policy_version
                                            == _parameter_policy_version(next(
                                                spec for spec in OFFICIAL_RAW_SPECS
                                                if spec.key == request.resource_key))
                                            and _backfill_matches(current, request)
                                        )):
                unchanged += 1
                continue
            save_backfill(database, actor=actor, source_key=source_key, payload=request,
                scope=snapshot, backfill_id=current.id if current else None,
                expected_version=current.version if current else None, now=now,
                transaction=session, allow_contract_rebind=True)
            if current is None:
                created += 1
            else:
                updated += 1
        session.commit()
        return OfficialBackfillRolloutView(
            business_unit_id=business_unit_id,
            approved_store_count=len(store_bindings),
            validated_resource_count=len({spec.key for spec, _, _, _ in candidates}),
            planned_backfill_count=len(planned),
            planned_window_count=sum(windows for _, _, windows, _ in candidates),
            created_count=created,
            updated_count=updated,
            unchanged_count=unchanged,
            retention_clamped_count=sum(clamped for _, _, _, clamped in candidates),
            status=payload.status,
        )
