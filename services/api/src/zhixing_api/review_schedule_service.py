from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from hmac import compare_digest
from typing import Literal, cast
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from zhixing_jobs import EnqueueJob, JobRepository
from zhixing_jobs.models import BackgroundJob

from zhixing_api.action_schemas import BusinessAnalysisActionProposalRequest
from zhixing_api.action_service import create_business_analysis_action_proposals
from zhixing_api.actor_context import (
    ActorContext,
    actor_scope_allows,
    require_permission,
    resolve_database_actor,
)
from zhixing_api.ai_provider import ResponsesAIProvider
from zhixing_api.analysis_schemas import AnalysisScopeView
from zhixing_api.analysis_service import available_analysis_scopes, run_business_analysis
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    ActionProposal,
    Principal,
    StoreReviewPlan,
    StoreReviewScheduleRun,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.redis_coordinator import NoopRedisCoordinator, RedisCoordinator
from zhixing_api.review_schedule_schemas import (
    AutoProposePriority,
    StoreReviewPlanActionRequest,
    StoreReviewPlanMutationResponse,
    StoreReviewPlanRequest,
    StoreReviewPlanView,
    StoreReviewScheduleResponse,
    StoreReviewScheduleRunView,
    StoreReviewScheduleStats,
)

JOB_TYPE = "analysis.daily-store-review"
PRIORITY_ORDER = {"normal": 0, "high": 1, "urgent": 2}


def calculate_next_run_at(
    *,
    timezone: str,
    local_time: str,
    weekdays: list[int],
    after: datetime,
) -> datetime:
    tz = ZoneInfo(timezone)
    current = _aware_utc(after).astimezone(tz)
    hour, minute = (int(part) for part in local_time.split(":"))
    for offset in range(8):
        target_date = current.date() + timedelta(days=offset)
        if target_date.isoweekday() not in weekdays:
            continue
        candidate = datetime.combine(target_date, time(hour, minute), tzinfo=tz)
        if candidate > current:
            return candidate.astimezone(UTC)
    raise ValueError("无法计算下次巡店时间")


def list_review_schedule(database: Database, actor: ActorContext) -> StoreReviewScheduleResponse:
    scopes = available_analysis_scopes(database, actor)
    allowed_scope_keys = {item.key for item in scopes}
    with database.session() as session:
        plans = list(
            session.scalars(
                select(StoreReviewPlan)
                .where(
                    StoreReviewPlan.enterprise_id == actor.enterprise_id,
                    StoreReviewPlan.scope_key.in_(allowed_scope_keys),
                )
                .order_by(StoreReviewPlan.status, StoreReviewPlan.next_run_at, StoreReviewPlan.name)
            )
        ) if allowed_scope_keys else []
        plan_ids = [item.id for item in plans]
        runs = list(
            session.scalars(
                select(StoreReviewScheduleRun)
                .where(StoreReviewScheduleRun.plan_id.in_(plan_ids))
                .order_by(StoreReviewScheduleRun.queued_at.desc())
                .limit(100)
            )
        ) if plan_ids else []
        principal_ids = {item.created_by_principal_id for item in plans}
        principals = {
            item.id: item
            for item in session.scalars(
                select(Principal).where(Principal.id.in_(principal_ids))
            )
        } if principal_ids else {}
        job_ids = [item.background_job_id for item in runs if item.background_job_id]
        jobs = {
            item.id: item
            for item in session.scalars(select(BackgroundJob).where(BackgroundJob.id.in_(job_ids)))
        } if job_ids else {}
        pending_proposal_count = int(
            session.scalar(
                select(func.count(ActionProposal.id)).where(
                    ActionProposal.enterprise_id == actor.enterprise_id,
                    ActionProposal.source_type == "business-analysis",
                    ActionProposal.status == "pending_approval",
                    ActionProposal.scope_key.in_(allowed_scope_keys),
                )
            ) or 0
        ) if allowed_scope_keys else 0
    plan_by_id = {item.id: item for item in plans}
    plan_views = [
        _plan_view(item, principals.get(item.created_by_principal_id)) for item in plans
    ]
    run_views = [
        _run_view(item, plan_by_id[item.plan_id], jobs.get(item.background_job_id or ""))
        for item in runs
    ]
    return StoreReviewScheduleResponse(
        actor_name=actor.display_name,
        can_manage="analysis.schedule.manage" in actor.permissions,
        available_scopes=scopes,
        stats=StoreReviewScheduleStats(
            plan_count=len(plans),
            active_plan_count=sum(item.status == "active" for item in plans),
            queued_or_running_count=sum(
                item.status in {"preparing", "queued", "running"} for item in run_views
            ),
            succeeded_count=sum(item.status == "succeeded" for item in run_views),
            failed_count=sum(item.status == "failed" for item in run_views),
            pending_proposal_count=pending_proposal_count,
        ),
        plans=plan_views,
        runs=run_views,
        generated_at=datetime.now(UTC),
    )


def create_review_plan(
    database: Database,
    actor: ActorContext,
    scope: AnalysisScopeView,
    payload: StoreReviewPlanRequest,
) -> StoreReviewPlanMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        existing = session.scalar(
            select(StoreReviewPlan).where(
                StoreReviewPlan.enterprise_id == actor.enterprise_id,
                StoreReviewPlan.idempotency_key == payload.client_request_key,
            )
        )
        if existing is not None:
            if not _plan_matches(existing, payload, scope):
                raise ApiProblem(
                    status_code=409,
                    code="analysis.schedule.idempotency_conflict",
                    message="该幂等键已用于不同的巡店计划",
                )
            return StoreReviewPlanMutationResponse(
                idempotent=True,
                schedule=list_review_schedule(database, actor),
            )
        plan = StoreReviewPlan(
            id=f"store_review_plan_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            plan_key=f"review-{scope.key}-{uuid4().hex[:10]}",
            name=payload.name.strip(),
            scope_type=scope.type,
            scope_key=scope.key,
            scope_label=scope.label,
            window_days=payload.window_days,
            timezone=payload.timezone,
            local_time=payload.local_time,
            weekdays=payload.weekdays,
            auto_propose_min_priority=payload.auto_propose_min_priority,
            status="active",
            next_run_at=calculate_next_run_at(
                timezone=payload.timezone,
                local_time=payload.local_time,
                weekdays=payload.weekdays,
                after=now,
            ),
            last_enqueued_at=None,
            created_by_principal_id=actor.principal_id,
            actor_snapshot=actor.snapshot(),
            idempotency_key=payload.client_request_key,
            last_action=None,
            last_action_idempotency_key=None,
            version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(plan)
        session.commit()
    return StoreReviewPlanMutationResponse(
        idempotent=False,
        schedule=list_review_schedule(database, actor),
    )


def act_on_review_plan(
    database: Database,
    actor: ActorContext,
    *,
    plan_key: str,
    payload: StoreReviewPlanActionRequest,
) -> StoreReviewPlanMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        plan = session.scalar(
            select(StoreReviewPlan).where(
                StoreReviewPlan.enterprise_id == actor.enterprise_id,
                StoreReviewPlan.plan_key == plan_key,
            )
        )
        if plan is None or not _plan_scope_allowed(actor, plan):
            raise ApiProblem(
                status_code=404,
                code="analysis.schedule.plan_not_found",
                message="巡店计划不存在或不在当前授权范围",
            )
        if (
            plan.last_action_idempotency_key == payload.idempotency_key
            and plan.last_action == payload.action
        ):
            return StoreReviewPlanMutationResponse(
                idempotent=True,
                schedule=list_review_schedule(database, actor),
            )
        if plan.last_action_idempotency_key == payload.idempotency_key:
            raise ApiProblem(
                status_code=409,
                code="analysis.schedule.action_idempotency_conflict",
                message="该幂等键已用于不同的计划操作",
            )
        if payload.action in {"pause", "resume"}:
            if payload.expected_version != plan.version:
                raise ApiProblem(
                    status_code=409,
                    code="analysis.schedule.version_conflict",
                    message="巡店计划已被其他操作更新，请刷新后重试",
                    details={"current_version": plan.version},
                )
            plan.status = "paused" if payload.action == "pause" else "active"
            plan.next_run_at = None if payload.action == "pause" else calculate_next_run_at(
                timezone=plan.timezone,
                local_time=plan.local_time,
                weekdays=list(plan.weekdays),
                after=now,
            )
            plan.version += 1
            plan.last_action = payload.action
            plan.last_action_idempotency_key = payload.idempotency_key
            plan.updated_at = now
            session.commit()
        else:
            plan_id = plan.id
            session.expunge(plan)
            _enqueue_plan_run(
                database,
                plan_id=plan_id,
                trigger_type="manual",
                idempotency_key=f"manual:{plan_key}:{payload.idempotency_key}",
                now=now,
                initiator_actor=actor,
            )
            with database.session() as update_session:
                update_plan = update_session.get(StoreReviewPlan, plan_id)
                if update_plan is not None:
                    update_plan.last_action = payload.action
                    update_plan.last_action_idempotency_key = payload.idempotency_key
                    update_plan.updated_at = now
                    update_session.commit()
    return StoreReviewPlanMutationResponse(
        idempotent=False,
        schedule=list_review_schedule(database, actor),
    )


def dispatch_due_review_plans(database: Database, *, now: datetime | None = None) -> int:
    current = _aware_utc(now or datetime.now(UTC))
    with database.session() as session:
        due_plan_ids = list(
            session.scalars(
                select(StoreReviewPlan.id).where(
                    StoreReviewPlan.status == "active",
                    StoreReviewPlan.next_run_at.is_not(None),
                    StoreReviewPlan.next_run_at <= current,
                )
            )
        )
    dispatched = 0
    for plan_id in due_plan_ids:
        with database.session() as session:
            plan = session.get(StoreReviewPlan, plan_id)
            if plan is None or plan.status != "active" or plan.next_run_at is None:
                continue
            scheduled_at = _aware_utc(plan.next_run_at)
            business_date = scheduled_at.astimezone(ZoneInfo(plan.timezone)).date()
            run_key = f"scheduled:{plan.plan_key}:{business_date.isoformat()}"
        _enqueue_plan_run(
            database,
            plan_id=plan_id,
            trigger_type="scheduled",
            idempotency_key=run_key,
            now=current,
            business_date=business_date,
        )
        with database.session() as session:
            plan = session.get(StoreReviewPlan, plan_id)
            if plan is not None:
                plan.last_enqueued_at = current
                plan.next_run_at = calculate_next_run_at(
                    timezone=plan.timezone,
                    local_time=plan.local_time,
                    weekdays=list(plan.weekdays),
                    after=current,
                )
                plan.updated_at = current
                session.commit()
        dispatched += 1
    return dispatched


async def run_review_schedule_dispatcher(
    database: Database,
    poll_seconds: float,
    coordinator: RedisCoordinator | NoopRedisCoordinator,
) -> None:
    while True:
        async with coordinator.lease(
            "review-schedule-dispatcher",
            ttl_seconds=max(int(poll_seconds * 3), 5),
        ) as acquired:
            if acquired:
                dispatch_due_review_plans(database)
        await asyncio.sleep(max(poll_seconds, 1.0))


async def execute_review_job(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    *,
    job_id: str,
    worker_id: str | None,
    execution_token: str | None,
    request_id: str,
    run_id: str,
) -> dict[str, object]:
    with database.session() as session:
        job = session.get(BackgroundJob, job_id)
        if job is None or job.job_type != JOB_TYPE or job.status != "running":
            raise ApiProblem(
                status_code=409,
                code="analysis.schedule.job_not_running",
                message="巡店任务不存在或不处于 Worker 运行状态",
            )
        _validate_worker_execution_claim(
            job,
            worker_id=worker_id,
            execution_token=execution_token,
            request_id=request_id,
            run_id=run_id,
        )
        schedule_run = session.scalar(
            select(StoreReviewScheduleRun).where(
                StoreReviewScheduleRun.background_job_id == job.id
            )
        )
        if schedule_run is None:
            raise ApiProblem(
                status_code=409,
                code="analysis.schedule.run_missing",
                message="后台任务缺少对应的巡店运行",
            )
        plan = session.get(StoreReviewPlan, schedule_run.plan_id)
        if plan is None:
            raise ApiProblem(
                status_code=409,
                code="analysis.schedule.plan_missing",
                message="巡店运行关联的计划不存在",
            )
        _validate_review_job_context(job, plan)
        if schedule_run.status == "succeeded":
            return _execution_result(schedule_run)
        account = session.scalar(
            select(UserAccount).where(
                UserAccount.enterprise_id == job.enterprise_id,
                UserAccount.principal_id == job.initiator_id,
                UserAccount.status == "active",
            )
        )
        if account is None:
            raise ApiProblem(
                status_code=409,
                code="analysis.schedule.initiator_unavailable",
                message="计划创建人的当前账号不可用",
            )
        actor_login = account.local_login_name
        scope = AnalysisScopeView(
            type=cast(Literal["enterprise", "store"], plan.scope_type),
            key=plan.scope_key,
            label=plan.scope_label,
        )
        window_days = plan.window_days
        threshold = cast(AutoProposePriority, plan.auto_propose_min_priority)
        queued_permission_set_version = job.permission_set_version
        required_permissions = tuple(job.required_permissions)
        schedule_run_id = schedule_run.id
        schedule_run.status = "running"
        schedule_run.started_at = datetime.now(UTC)
        schedule_run.error_code = None
        schedule_run.error_message = None
        session.commit()
    actor = resolve_database_actor(
        database,
        login_name=actor_login,
        request_id=job.request_id,
        run_id=job.run_id,
        authentication_method="background-job",
    )
    scope_id = actor.enterprise_id if scope.type == "enterprise" else scope.key
    try:
        require_permission(
            actor,
            "analysis.run",
            database,
            resource_type="business-analysis",
            resource_key=scope.key,
            scope_type=scope.type,
            scope_id=scope_id,
        )
        require_permission(
            actor,
            "metric.query.execute",
            database,
            resource_type="metric-query",
            resource_key=f"scheduled-analysis:{scope.key}",
            scope_type=scope.type,
            scope_id=scope_id,
        )
        if "action.propose" in required_permissions:
            require_permission(
                actor,
                "action.propose",
                database,
                resource_type="action-proposal",
                resource_key=f"scheduled-analysis:{scope.key}",
                scope_type=scope.type,
                scope_id=scope_id,
            )
        response = await run_business_analysis(
            database,
            settings,
            provider,
            actor,
            scope=scope,
            window_days=window_days,
            client_request_key=f"scheduled-analysis:{schedule_run_id}",
        )
        proposal_count = 0
        if threshold != "off":
            minimum = PRIORITY_ORDER[threshold]
            indexes = [
                index
                for index, item in enumerate(response.run.result.recommendations)
                if PRIORITY_ORDER[item.priority] >= minimum
            ]
            if indexes:
                proposals = create_business_analysis_action_proposals(
                    database,
                    analysis_run_id=response.run.id,
                    actor=actor,
                    payload=BusinessAnalysisActionProposalRequest(
                        recommendation_indexes=indexes,
                        due_hint="未来 1 个工作日内完成",
                        idempotency_key=f"scheduled-proposals:{schedule_run_id}",
                    ),
                )
                proposal_count = len(proposals.items)
        with database.session() as session:
            persisted = session.get(StoreReviewScheduleRun, schedule_run_id)
            if persisted is None:
                raise RuntimeError("巡店运行在执行完成前丢失")
            persisted.status = "succeeded"
            persisted.analysis_run_id = response.run.id
            persisted.brief_id = response.brief.id
            persisted.proposal_count = proposal_count
            persisted.execution_mode = response.run.execution_mode
            persisted.completed_at = datetime.now(UTC)
            session.commit()
            result = _execution_result(persisted)
            result["authorization"] = {
                "revalidated": True,
                "queued_permission_set_version": queued_permission_set_version,
                "executed_permission_set_version": actor.permission_set_version,
                "permission_set_changed": (
                    queued_permission_set_version != actor.permission_set_version
                ),
                "required_permissions": list(required_permissions),
                "scope_type": scope.type,
                "scope_id": scope_id,
                "actor_principal_id": actor.principal_id,
            }
            return result
    except Exception as exc:
        with database.session() as session:
            persisted = session.get(StoreReviewScheduleRun, schedule_run_id)
            if persisted is not None and persisted.status != "succeeded":
                persisted.status = "failed"
                persisted.error_code = getattr(exc, "code", "analysis.schedule.execution_failed")
                persisted.error_message = str(exc)[:1000]
                persisted.completed_at = datetime.now(UTC)
                session.commit()
        raise


def _validate_worker_execution_claim(
    job: BackgroundJob,
    *,
    worker_id: str | None,
    execution_token: str | None,
    request_id: str,
    run_id: str,
) -> None:
    if not worker_id or not execution_token:
        raise ApiProblem(
            status_code=401,
            code="auth.worker_execution_context_required",
            message="内部任务执行需要有效的 Worker 领取上下文",
        )
    supplied_hash = sha256(execution_token.encode("utf-8")).hexdigest()
    matches = (
        job.worker_id == worker_id
        and job.execution_token_hash is not None
        and compare_digest(job.execution_token_hash, supplied_hash)
        and job.request_id == request_id
        and job.run_id == run_id
    )
    if not matches:
        raise ApiProblem(
            status_code=403,
            code="authorization.worker_execution_context_denied",
            message="Worker 领取上下文与当前运行任务不一致",
            details={"job_id": job.id, "worker_id": worker_id},
        )


def _validate_review_job_context(job: BackgroundJob, plan: StoreReviewPlan) -> None:
    expected_scope_id = (
        plan.enterprise_id if plan.scope_type == "enterprise" else plan.scope_key
    )
    expected_permissions = {"analysis.run", "metric.query.execute"}
    if plan.auto_propose_min_priority != "off":
        expected_permissions.add("action.propose")
    snapshot_principal_id = job.actor_snapshot.get("principal_id")
    matches = (
        job.enterprise_id == plan.enterprise_id
        and job.initiator_type == "principal"
        and snapshot_principal_id == job.initiator_id
        and job.scope_type == plan.scope_type
        and job.scope_id == expected_scope_id
        and set(job.required_permissions) == expected_permissions
    )
    if not matches:
        raise ApiProblem(
            status_code=403,
            code="authorization.job_context_mismatch",
            message="后台任务声明的主体、权限或范围与巡店计划不一致",
            details={"job_id": job.id, "plan_key": plan.plan_key},
        )


def _enqueue_plan_run(
    database: Database,
    *,
    plan_id: str,
    trigger_type: Literal["scheduled", "manual"],
    idempotency_key: str,
    now: datetime,
    business_date: date | None = None,
    initiator_actor: ActorContext | None = None,
) -> StoreReviewScheduleRun:
    current = _aware_utc(now)
    with database.session() as session:
        plan = session.get(StoreReviewPlan, plan_id)
        if plan is None:
            raise LookupError("巡店计划不存在")
        existing = session.scalar(
            select(StoreReviewScheduleRun).where(
                StoreReviewScheduleRun.enterprise_id == plan.enterprise_id,
                StoreReviewScheduleRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
        schedule_run = StoreReviewScheduleRun(
            id=f"store_review_run_{uuid4().hex}",
            enterprise_id=plan.enterprise_id,
            plan_id=plan.id,
            business_date=business_date or current.astimezone(ZoneInfo(plan.timezone)).date(),
            trigger_type=trigger_type,
            idempotency_key=idempotency_key,
            status="preparing",
            background_job_id=None,
            analysis_run_id=None,
            brief_id=None,
            proposal_count=0,
            execution_mode=None,
            request_id=f"req_store_review_{uuid4().hex}",
            run_id=f"run_store_review_{uuid4().hex}",
            error_code=None,
            error_message=None,
            queued_at=current,
            started_at=None,
            completed_at=None,
        )
        session.add(schedule_run)
        session.commit()
        run_id = schedule_run.id
        enterprise_id = plan.enterprise_id
        principal_id = (
            initiator_actor.principal_id
            if initiator_actor is not None
            else plan.created_by_principal_id
        )
        actor_snapshot = (
            initiator_actor.snapshot()
            if initiator_actor is not None
            else dict(plan.actor_snapshot)
        )
        if not actor_snapshot:
            actor_snapshot = {
                "principal_id": principal_id,
                "enterprise_id": enterprise_id,
                "authentication_method": "scheduled-plan-snapshot",
            }
        permission_set_version = str(
            actor_snapshot.get("permission_set_version") or "unavailable"
        )
        scope_type = plan.scope_type
        scope_id = enterprise_id if scope_type == "enterprise" else plan.scope_key
        required_permissions = ["analysis.run", "metric.query.execute"]
        if plan.auto_propose_min_priority != "off":
            required_permissions.append("action.propose")
    enqueued = JobRepository(database.engine).enqueue(
        EnqueueJob(
            enterprise_id=enterprise_id,
            job_type=JOB_TYPE,
            payload={"schedule_run_id": run_id},
            idempotency_key=idempotency_key,
            initiator_type="principal",
            initiator_id=principal_id,
            actor_snapshot=actor_snapshot,
            permission_set_version=permission_set_version,
            required_permissions=tuple(required_permissions),
            scope_type=scope_type,
            scope_id=scope_id,
            request_id=f"req_store_review_{run_id[-16:]}",
            run_id=f"run_store_review_{run_id[-16:]}",
            priority=20,
            max_attempts=3,
            timeout_seconds=120.0,
        )
    )
    with database.session() as session:
        persisted = session.get(StoreReviewScheduleRun, run_id)
        if persisted is None:
            raise RuntimeError("巡店运行入队后丢失")
        persisted.background_job_id = enqueued.job.id
        persisted.status = "queued"
        persisted.request_id = enqueued.job.request_id
        persisted.run_id = enqueued.job.run_id
        session.commit()
        session.refresh(persisted)
        return persisted


def _plan_view(plan: StoreReviewPlan, principal: Principal | None) -> StoreReviewPlanView:
    return StoreReviewPlanView(
        key=plan.plan_key,
        name=plan.name,
        scope=AnalysisScopeView(
            type=cast(Literal["enterprise", "store"], plan.scope_type),
            key=plan.scope_key,
            label=plan.scope_label,
        ),
        window_days=plan.window_days,
        timezone=plan.timezone,
        local_time=plan.local_time,
        weekdays=list(plan.weekdays),
        auto_propose_min_priority=cast(AutoProposePriority, plan.auto_propose_min_priority),
        status=cast(Literal["active", "paused"], plan.status),
        next_run_at=_aware_utc(plan.next_run_at) if plan.next_run_at else None,
        last_enqueued_at=_aware_utc(plan.last_enqueued_at) if plan.last_enqueued_at else None,
        created_by_name=principal.display_name if principal else plan.created_by_principal_id,
        version=plan.version,
        created_at=_aware_utc(plan.created_at),
        updated_at=_aware_utc(plan.updated_at),
    )


def _run_view(
    run: StoreReviewScheduleRun,
    plan: StoreReviewPlan,
    job: BackgroundJob | None,
) -> StoreReviewScheduleRunView:
    status = run.status
    if status not in {"succeeded", "failed"} and job is not None:
        status = {
            "running": "running",
            "succeeded": "succeeded",
            "failed": "failed",
            "queued": "queued",
            "retry_wait": "queued",
        }.get(job.status, status)
    projected_started_at = run.started_at or (job.started_at if job else None)
    projected_completed_at = run.completed_at or (
        job.finished_at if job and status in {"succeeded", "failed"} else None
    )
    return StoreReviewScheduleRunView(
        id=run.id,
        plan_key=plan.plan_key,
        plan_name=plan.name,
        scope=AnalysisScopeView(
            type=cast(Literal["enterprise", "store"], plan.scope_type),
            key=plan.scope_key,
            label=plan.scope_label,
        ),
        business_date=run.business_date,
        trigger_type=cast(Literal["scheduled", "manual"], run.trigger_type),
        status=cast(
            Literal["preparing", "queued", "running", "succeeded", "failed"], status
        ),
        background_job_id=run.background_job_id,
        background_job_attempt=job.attempt if job else 0,
        analysis_run_id=run.analysis_run_id,
        brief_id=run.brief_id,
        proposal_count=run.proposal_count,
        execution_mode=cast(
            Literal["model", "evidence-fallback"] | None, run.execution_mode
        ),
        error_code=run.error_code or (job.last_error_code if job else None),
        error_message=run.error_message or (job.last_error_message if job else None),
        queued_at=_aware_utc(run.queued_at),
        started_at=_aware_utc(projected_started_at) if projected_started_at else None,
        completed_at=_aware_utc(projected_completed_at) if projected_completed_at else None,
    )


def _plan_matches(
    plan: StoreReviewPlan,
    payload: StoreReviewPlanRequest,
    scope: AnalysisScopeView,
) -> bool:
    return (
        plan.name == payload.name.strip()
        and plan.scope_key == scope.key
        and plan.window_days == payload.window_days
        and plan.timezone == payload.timezone
        and plan.local_time == payload.local_time
        and list(plan.weekdays) == payload.weekdays
        and plan.auto_propose_min_priority == payload.auto_propose_min_priority
    )


def _plan_scope_allowed(actor: ActorContext, plan: StoreReviewPlan) -> bool:
    scope_id = actor.enterprise_id if plan.scope_type == "enterprise" else plan.scope_key
    return actor_scope_allows(actor, scope_type=plan.scope_type, scope_id=scope_id)


def _execution_result(run: StoreReviewScheduleRun) -> dict[str, object]:
    return {
        "schedule_run_id": run.id,
        "status": run.status,
        "analysis_run_id": run.analysis_run_id or "",
        "brief_id": run.brief_id or "",
        "proposal_count": run.proposal_count,
        "execution_mode": run.execution_mode or "",
    }


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
