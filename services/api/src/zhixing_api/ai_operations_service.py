from __future__ import annotations

import re
import shutil
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from time import perf_counter
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import func, select
from zhixing_agent_runtime import AgentRunNotFound, AgentRuntime
from zhixing_codex_runtime import CodexAppServerRuntime

from zhixing_api.actor_context import ActorContext
from zhixing_api.ai_operations_schemas import (
    AgentRuntimeApprovalView,
    AgentRuntimeCancelResponse,
    AgentRuntimeConfigView,
    AgentRuntimeEventView,
    AgentRuntimeProbeRunView,
    AgentRuntimeSessionDetailResponse,
    AgentRuntimeSessionView,
    AgentRuntimeTurnView,
    AIDailyStat,
    AILatestRunView,
    AIModelStat,
    AIOperationsOverviewResponse,
    AIProviderConfigView,
    AIProviderProbeRunView,
    AIRuntimeStats,
    AIRunTypeStat,
)
from zhixing_api.ai_provider import AIProviderError, ResponsesAIProvider
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    AgentRunContextItem,
    AgentRunEvidence,
    AgentRuntimeApproval,
    AgentRuntimeEventRecord,
    AgentRuntimeProbeRun,
    AgentRuntimeSession,
    AgentRuntimeTurn,
    AIProviderProbeRun,
    BusinessAnalysisRun,
    CustomerOperationRun,
    EvaluationRun,
    Principal,
    RoleTwinProfile,
    RoleTwinVersion,
)
from zhixing_api.database import Database

PROVIDER_KEY = "openai-compatible-responses"
PROVIDER_PROTOCOL = "responses-v1"
RUNTIME_KEY = "codex-app-server"
RUNTIME_PROTOCOL = "app-server-json-rpc-v2"
PROBE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {"type": "string", "enum": ["ok"]},
        "message": {"type": "string"},
    },
    "required": ["status", "message"],
}
RUN_TYPE_LABELS = {
    "answer": "分身问答与评测",
    "meeting": "数字会议独立分析",
    "meeting-challenge": "数字会议交叉质询",
    "meeting-response": "数字会议回应",
    "meeting-risk_review": "数字会议风险审查",
    "meeting-moderator": "数字会议主持汇总",
    "customer-service-draft": "客服回复草稿",
    "business-analysis": "经营分析",
    "customer-operation": "单客运营方案",
}
_URL_PATTERN = re.compile(r"https?://[^\s，。；;]+", re.IGNORECASE)
_BEARER_PATTERN = re.compile(r"bearer\s+[a-z0-9._-]+", re.IGNORECASE)
_KEY_PATTERN = re.compile(r"(?:sk|key|token)[-_][a-z0-9_-]{8,}", re.IGNORECASE)


async def run_provider_probe(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    actor: ActorContext,
    *,
    model: str | None = None,
) -> AIProviderProbeRunView:
    effective_settings = replace(settings, ai_model=model or settings.ai_model)
    started = perf_counter()
    status = "failed"
    structured_output_supported = False
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    try:
        completion = await provider.generate(
            effective_settings,
            instructions="执行连接诊断，只返回符合给定结构的健康状态。",
            input_text="返回 status=ok，并用一句简短文本确认 Responses 协议可用。",
            run_id=actor.run_id,
            schema_name="zhixing_provider_probe",
            response_schema=PROBE_SCHEMA,
        )
        if completion.payload.get("status") != "ok":
            raise AIProviderError("AI Provider 探针返回了无效健康状态")
        status = "succeeded"
        structured_output_supported = completion.structured_output
        input_tokens = completion.input_tokens
        output_tokens = completion.output_tokens
    except AIProviderError as exc:
        error_code = (
            "provider_not_configured"
            if not effective_settings.ai_enabled or not effective_settings.ai_api_key
            else "provider_probe_failed"
        )
        error_message = _sanitize_error(str(exc))
    except Exception as exc:  # Provider adapters must fail closed and persist a diagnostic result.
        error_code = "provider_probe_failed"
        error_message = _sanitize_error(str(exc) or exc.__class__.__name__)

    item = AIProviderProbeRun(
        id=f"ai_probe_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        actor_principal_id=actor.principal_id,
        provider_key=PROVIDER_KEY,
        model=effective_settings.ai_model,
        protocol=PROVIDER_PROTOCOL,
        structured_output_supported=structured_output_supported,
        status=status,
        duration_ms=max(1, round((perf_counter() - started) * 1000)),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error_code=error_code,
        error_message=error_message,
        request_id=actor.request_id,
        run_id=actor.run_id,
        created_at=datetime.now(UTC),
    )
    with database.session() as session:
        session.add(item)
        session.commit()
        session.refresh(item)
    return _probe_view(item, actor.display_name)


async def run_agent_runtime_probe(
    database: Database,
    settings: Settings,
    runtime: CodexAppServerRuntime,
    actor: ActorContext,
) -> AgentRuntimeProbeRunView:
    started = perf_counter()
    if settings.agent_runtime_enabled:
        probe = await runtime.probe()
        status = "succeeded" if probe.initialized else "failed"
        error_code = probe.error_code
        error_message = _sanitize_error(probe.error_message) if probe.error_message else None
    else:
        probe = None
        status = "failed"
        error_code = "agent_runtime_disabled"
        error_message = "Codex Runtime 未启用"
    item = AgentRuntimeProbeRun(
        id=f"agent_runtime_probe_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        actor_principal_id=actor.principal_id,
        runtime_key=RUNTIME_KEY,
        protocol=RUNTIME_PROTOCOL,
        command_version=probe.version if probe else None,
        initialized=bool(probe and probe.initialized),
        status=status,
        duration_ms=max(1, round((perf_counter() - started) * 1000)),
        error_code=error_code,
        error_message=error_message,
        request_id=actor.request_id,
        run_id=actor.run_id,
        created_at=datetime.now(UTC),
    )
    with database.session() as session:
        session.add(item)
        session.commit()
        session.refresh(item)
    return _runtime_probe_view(item, actor.display_name)


def agent_runtime_session_detail(
    database: Database,
    *,
    enterprise_id: str,
    runtime_session_id: str,
) -> AgentRuntimeSessionDetailResponse:
    with database.session() as session:
        runtime_session = session.scalar(
            select(AgentRuntimeSession).where(
                AgentRuntimeSession.id == runtime_session_id,
                AgentRuntimeSession.enterprise_id == enterprise_id,
            )
        )
        if runtime_session is None:
            raise LookupError("没有找到 Agent Runtime 会话")
        turns = list(
            session.scalars(
                select(AgentRuntimeTurn)
                .where(AgentRuntimeTurn.runtime_session_id == runtime_session.id)
                .order_by(AgentRuntimeTurn.turn_number)
            )
        )
        events = list(
            session.scalars(
                select(AgentRuntimeEventRecord)
                .where(AgentRuntimeEventRecord.runtime_session_id == runtime_session.id)
                .order_by(AgentRuntimeEventRecord.sequence)
            )
        )
        root_run = session.get(AgentRun, runtime_session.agent_run_id)
        if root_run is None:
            raise LookupError("Runtime 会话缺少初始 AgentRun")
        principal = (
            session.get(Principal, root_run.actor_principal_id)
            if root_run.actor_principal_id
            else None
        )
        twin = session.get(RoleTwinProfile, root_run.twin_profile_id)
        role_version = (
            session.get(RoleTwinVersion, root_run.role_twin_version_id)
            if root_run.role_twin_version_id
            else None
        )
        agent_run_ids = {item.agent_run_id for item in turns}
        evidence_counts: dict[str, int] = {
            run_id: int(count)
            for run_id, count in session.execute(
                select(AgentRunEvidence.run_id, func.count(AgentRunEvidence.id))
                .where(AgentRunEvidence.run_id.in_(agent_run_ids))
                .group_by(AgentRunEvidence.run_id)
            ).all()
        } if agent_run_ids else {}
        context_counts: dict[str, int] = {
            run_id: int(count)
            for run_id, count in session.execute(
                select(AgentRunContextItem.run_id, func.count(AgentRunContextItem.id))
                .where(AgentRunContextItem.run_id.in_(agent_run_ids))
                .group_by(AgentRunContextItem.run_id)
            ).all()
        } if agent_run_ids else {}

    summary = _runtime_session_views([runtime_session], turns, events)[0]
    return AgentRuntimeSessionDetailResponse(
        session=summary,
        actor_name=principal.display_name if principal else "系统运行",
        twin_name=twin.display_name if twin else "未知分身",
        role_twin_version_number=role_version.version_number if role_version else None,
        turns=[
            AgentRuntimeTurnView(
                id=item.id,
                agent_run_id=item.agent_run_id,
                mcp_gateway_session_id=item.mcp_gateway_session_id,
                runtime_turn_id=item.runtime_turn_id,
                turn_number=item.turn_number,
                status=item.status,
                model=item.model,
                evidence_count=int(evidence_counts.get(item.agent_run_id, 0)),
                context_count=int(context_counts.get(item.agent_run_id, 0)),
                duration_ms=_runtime_turn_duration(item),
                failure_code=item.failure_code,
                failure_message=item.failure_message,
                request_id=item.request_id,
                run_id=item.run_id,
                started_at=_as_utc(item.started_at),
                completed_at=_as_utc(item.completed_at) if item.completed_at else None,
            )
            for item in turns
        ],
        events=[
            AgentRuntimeEventView(
                id=item.id,
                runtime_turn_id=item.runtime_turn_id,
                sequence=item.sequence,
                runtime_sequence=item.runtime_sequence,
                event_type=item.event_type,
                status=item.status,
                event_payload=item.event_payload,
                occurred_at=_as_utc(item.occurred_at),
            )
            for item in events
        ],
        generated_at=datetime.now(UTC),
    )


async def cancel_agent_runtime_session(
    database: Database,
    runtime: AgentRuntime,
    *,
    enterprise_id: str,
    runtime_session_id: str,
) -> AgentRuntimeCancelResponse:
    with database.session() as session:
        runtime_session = session.scalar(
            select(AgentRuntimeSession).where(
                AgentRuntimeSession.id == runtime_session_id,
                AgentRuntimeSession.enterprise_id == enterprise_id,
            )
        )
        if runtime_session is None:
            raise LookupError("没有找到 Agent Runtime 会话")
        if runtime_session.status not in {"starting", "running", "waiting_approval"}:
            raise ValueError("只有正在运行或等待审批的 Runtime 会话可以取消")
        active_turn = session.scalar(
            select(AgentRuntimeTurn)
            .where(AgentRuntimeTurn.runtime_session_id == runtime_session.id)
            .order_by(AgentRuntimeTurn.turn_number.desc())
            .limit(1)
        )
        if active_turn is None:
            raise ValueError("Runtime 会话没有可取消的 Turn")
        agent_run_id = active_turn.agent_run_id
    try:
        await runtime.cancel(agent_run_id)
    except AgentRunNotFound as exc:
        raise ValueError("Runtime 进程已不在当前 API 实例中") from exc
    return AgentRuntimeCancelResponse(
        session_id=runtime_session_id,
        agent_run_id=agent_run_id,
    )


async def resolve_agent_runtime_approval(
    database: Database,
    runtime: AgentRuntime,
    *,
    enterprise_id: str,
    runtime_session_id: str,
    decision: str,
) -> AgentRuntimeCancelResponse:
    if decision not in {"approve", "decline"}:
        raise ValueError("审批决定必须是 approve 或 decline")
    with database.session() as session:
        runtime_session = session.scalar(
            select(AgentRuntimeSession).where(
                AgentRuntimeSession.id == runtime_session_id,
                AgentRuntimeSession.enterprise_id == enterprise_id,
            )
        )
        if runtime_session is None:
            raise LookupError("没有找到 Agent Runtime 会话")
        if runtime_session.status != "waiting_approval":
            raise ValueError("当前 Runtime 没有等待中的审批")
        agent_run_id = runtime_session.agent_run_id
    await runtime.resolve_approval(
        agent_run_id, cast(Literal["approve", "decline"], decision)
    )
    with database.session() as session:
        approval = session.scalar(
            select(AgentRuntimeApproval)
            .where(
                AgentRuntimeApproval.runtime_session_id == runtime_session_id,
                AgentRuntimeApproval.status == "pending",
            )
            .order_by(AgentRuntimeApproval.requested_at.desc())
            .limit(1)
        )
        if approval is not None:
            approval.status = "approved" if decision == "approve" else "declined"
            approval.decision = decision
            approval.decided_at = datetime.now(UTC)
            session.commit()
    return AgentRuntimeCancelResponse(session_id=runtime_session_id, agent_run_id=agent_run_id)


def ai_operations_overview(
    database: Database,
    settings: Settings,
    *,
    enterprise_id: str,
) -> AIOperationsOverviewResponse:
    now = datetime.now(UTC)
    trend_start = now - timedelta(days=13)
    with database.session() as session:
        agent_rows = list(
            session.execute(
                select(
                    AgentRun.id,
                    AgentRun.run_type,
                    AgentRun.status,
                    AgentRun.provider,
                    AgentRun.model,
                    AgentRun.duration_ms,
                    AgentRun.input_tokens,
                    AgentRun.output_tokens,
                    AgentRun.created_at,
                ).where(AgentRun.enterprise_id == enterprise_id)
            )
        )
        analysis_rows = list(
            session.execute(
                select(
                    BusinessAnalysisRun.id,
                    BusinessAnalysisRun.analysis_type,
                    BusinessAnalysisRun.status,
                    BusinessAnalysisRun.provider,
                    BusinessAnalysisRun.model,
                    BusinessAnalysisRun.execution_mode,
                    BusinessAnalysisRun.created_at,
                    BusinessAnalysisRun.completed_at,
                ).where(BusinessAnalysisRun.enterprise_id == enterprise_id)
            )
        )
        customer_operation_rows = list(
            session.execute(
                select(
                    CustomerOperationRun.id,
                    CustomerOperationRun.status,
                    CustomerOperationRun.provider,
                    CustomerOperationRun.model,
                    CustomerOperationRun.execution_mode,
                    CustomerOperationRun.duration_ms,
                    CustomerOperationRun.input_tokens,
                    CustomerOperationRun.output_tokens,
                    CustomerOperationRun.created_at,
                ).where(CustomerOperationRun.enterprise_id == enterprise_id)
            )
        )
        evaluation_batches = int(
            session.scalar(
                select(func.count(EvaluationRun.id)).where(
                    EvaluationRun.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        probes = list(
            session.scalars(
                select(AIProviderProbeRun)
                .where(AIProviderProbeRun.enterprise_id == enterprise_id)
                .order_by(AIProviderProbeRun.created_at.desc())
                .limit(20)
            )
        )
        runtime_probes = list(
            session.scalars(
                select(AgentRuntimeProbeRun)
                .where(AgentRuntimeProbeRun.enterprise_id == enterprise_id)
                .order_by(AgentRuntimeProbeRun.created_at.desc())
                .limit(20)
            )
        )
        runtime_sessions = list(
            session.scalars(
                select(AgentRuntimeSession)
                .where(AgentRuntimeSession.enterprise_id == enterprise_id)
                .order_by(AgentRuntimeSession.created_at.desc())
                .limit(30)
            )
        )
        runtime_approvals = list(
            session.scalars(
                select(AgentRuntimeApproval)
                .where(AgentRuntimeApproval.enterprise_id == enterprise_id)
                .order_by(AgentRuntimeApproval.requested_at.desc())
                .limit(30)
            )
        )
        runtime_session_ids = [item.id for item in runtime_sessions]
        runtime_turns = (
            list(
                session.scalars(
                    select(AgentRuntimeTurn)
                    .where(AgentRuntimeTurn.runtime_session_id.in_(runtime_session_ids))
                    .order_by(
                        AgentRuntimeTurn.runtime_session_id,
                        AgentRuntimeTurn.turn_number,
                    )
                )
            )
            if runtime_session_ids
            else []
        )
        runtime_events = (
            list(
                session.scalars(
                    select(AgentRuntimeEventRecord)
                    .where(
                        AgentRuntimeEventRecord.runtime_session_id.in_(runtime_session_ids)
                    )
                    .order_by(
                        AgentRuntimeEventRecord.runtime_session_id,
                        AgentRuntimeEventRecord.sequence,
                    )
                )
            )
            if runtime_session_ids
            else []
        )
        principals = {
            item.id: item.display_name
            for item in session.scalars(
                select(Principal).where(Principal.enterprise_id == enterprise_id)
            )
        }

    type_buckets: dict[str, dict[str, int]] = defaultdict(_empty_bucket)
    model_buckets: dict[tuple[str, str], dict[str, int]] = defaultdict(_empty_bucket)
    daily_buckets: dict[date, dict[str, int]] = defaultdict(_empty_bucket)
    latest_runs: list[AILatestRunView] = []
    durations: list[int] = []
    successful_runs = 0
    degraded_runs = 0
    input_tokens = 0
    output_tokens = 0
    tokenized_runs = 0
    runs_last_24h = 0

    for agent_row in agent_rows:
        created_at = _as_utc(agent_row.created_at)
        succeeded = agent_row.status == "completed"
        duration_ms = int(agent_row.duration_ms)
        bucket = type_buckets[agent_row.run_type]
        model_bucket = model_buckets[(agent_row.provider, agent_row.model)]
        _add_run(
            bucket,
            succeeded,
            duration_ms,
            agent_row.input_tokens,
            agent_row.output_tokens,
        )
        _add_run(
            model_bucket,
            succeeded,
            duration_ms,
            agent_row.input_tokens,
            agent_row.output_tokens,
        )
        if created_at >= trend_start:
            _add_run(
                daily_buckets[created_at.date()],
                succeeded,
                duration_ms,
                agent_row.input_tokens,
                agent_row.output_tokens,
            )
        successful_runs += int(succeeded)
        degraded_runs += int(not succeeded)
        durations.append(duration_ms)
        input_tokens += agent_row.input_tokens or 0
        output_tokens += agent_row.output_tokens or 0
        tokenized_runs += int(
            agent_row.input_tokens is not None or agent_row.output_tokens is not None
        )
        runs_last_24h += int(created_at >= now - timedelta(hours=24))
        latest_runs.append(
            AILatestRunView(
                id=agent_row.id,
                category="agent",
                run_type=agent_row.run_type,
                label=RUN_TYPE_LABELS.get(agent_row.run_type, agent_row.run_type),
                status=agent_row.status,
                execution_mode="model" if succeeded else "evidence-fallback",
                provider=agent_row.provider,
                model=agent_row.model,
                duration_ms=duration_ms,
                input_tokens=agent_row.input_tokens,
                output_tokens=agent_row.output_tokens,
                created_at=created_at,
            )
        )

    for analysis_row in analysis_rows:
        created_at = _as_utc(analysis_row.created_at)
        duration_ms = _duration_ms(analysis_row.created_at, analysis_row.completed_at)
        succeeded = (
            analysis_row.status == "completed" and analysis_row.execution_mode == "model"
        )
        bucket = type_buckets["business-analysis"]
        model_bucket = model_buckets[(analysis_row.provider, analysis_row.model)]
        _add_run(bucket, succeeded, duration_ms, None, None)
        _add_run(model_bucket, succeeded, duration_ms, None, None)
        if created_at >= trend_start:
            _add_run(daily_buckets[created_at.date()], succeeded, duration_ms, None, None)
        successful_runs += int(succeeded)
        degraded_runs += int(not succeeded)
        durations.append(duration_ms)
        runs_last_24h += int(created_at >= now - timedelta(hours=24))
        latest_runs.append(
            AILatestRunView(
                id=analysis_row.id,
                category="analysis",
                run_type="business-analysis",
                label=RUN_TYPE_LABELS["business-analysis"],
                status=analysis_row.status,
                execution_mode=analysis_row.execution_mode,
                provider=analysis_row.provider,
                model=analysis_row.model,
                duration_ms=duration_ms,
                input_tokens=None,
                output_tokens=None,
                created_at=created_at,
            )
        )

    for operation_row in customer_operation_rows:
        created_at = _as_utc(operation_row.created_at)
        duration_ms = int(operation_row.duration_ms)
        succeeded = (
            operation_row.status == "completed" and operation_row.execution_mode == "model"
        )
        bucket = type_buckets["customer-operation"]
        model_bucket = model_buckets[(operation_row.provider, operation_row.model)]
        _add_run(
            bucket,
            succeeded,
            duration_ms,
            operation_row.input_tokens,
            operation_row.output_tokens,
        )
        _add_run(
            model_bucket,
            succeeded,
            duration_ms,
            operation_row.input_tokens,
            operation_row.output_tokens,
        )
        if created_at >= trend_start:
            _add_run(
                daily_buckets[created_at.date()],
                succeeded,
                duration_ms,
                operation_row.input_tokens,
                operation_row.output_tokens,
            )
        successful_runs += int(succeeded)
        degraded_runs += int(not succeeded)
        durations.append(duration_ms)
        input_tokens += operation_row.input_tokens or 0
        output_tokens += operation_row.output_tokens or 0
        tokenized_runs += int(
            operation_row.input_tokens is not None or operation_row.output_tokens is not None
        )
        runs_last_24h += int(created_at >= now - timedelta(hours=24))
        latest_runs.append(
            AILatestRunView(
                id=operation_row.id,
                category="customer-operation",
                run_type="customer-operation",
                label=RUN_TYPE_LABELS["customer-operation"],
                status=operation_row.status,
                execution_mode=operation_row.execution_mode,
                provider=operation_row.provider,
                model=operation_row.model,
                duration_ms=duration_ms,
                input_tokens=operation_row.input_tokens,
                output_tokens=operation_row.output_tokens,
                created_at=created_at,
            )
        )

    total_runs = len(agent_rows) + len(analysis_rows) + len(customer_operation_rows)
    latest_runs.sort(key=lambda item: item.created_at, reverse=True)
    daily = []
    for offset in range(13, -1, -1):
        business_date = (now - timedelta(days=offset)).date()
        bucket = daily_buckets[business_date]
        daily.append(
            AIDailyStat(
                business_date=business_date,
                total_runs=bucket["total"],
                successful_runs=bucket["successful"],
                degraded_runs=bucket["degraded"],
                input_tokens=bucket["input_tokens"],
                output_tokens=bucket["output_tokens"],
            )
        )

    return AIOperationsOverviewResponse(
        enterprise_id=enterprise_id,
        provider=_provider_config(settings),
        runtime=_runtime_config(settings),
        stats=AIRuntimeStats(
            total_runs=total_runs,
            successful_runs=successful_runs,
            degraded_runs=degraded_runs,
            success_rate=successful_runs / total_runs if total_runs else 0,
            average_duration_ms=round(sum(durations) / len(durations)) if durations else 0,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            token_coverage_rate=tokenized_runs / total_runs if total_runs else 0,
            runs_last_24h=runs_last_24h,
            meeting_runs=sum(
                bucket["total"] for key, bucket in type_buckets.items() if key.startswith("meeting")
            ),
            answer_runs=type_buckets["answer"]["total"],
            customer_service_runs=type_buckets["customer-service-draft"]["total"],
            customer_operation_runs=type_buckets["customer-operation"]["total"],
            evaluation_batches=evaluation_batches,
            probe_runs=len(probes),
        ),
        run_types=[
            AIRunTypeStat(
                run_type=key,
                label=RUN_TYPE_LABELS.get(key, key),
                total_runs=bucket["total"],
                successful_runs=bucket["successful"],
                degraded_runs=bucket["degraded"],
                average_duration_ms=_bucket_average(bucket),
                input_tokens=bucket["input_tokens"],
                output_tokens=bucket["output_tokens"],
            )
            for key, bucket in sorted(
                type_buckets.items(), key=lambda item: item[1]["total"], reverse=True
            )
        ],
        models=[
            AIModelStat(
                provider=provider,
                model=model,
                total_runs=bucket["total"],
                successful_runs=bucket["successful"],
                degraded_runs=bucket["degraded"],
                average_duration_ms=_bucket_average(bucket),
                input_tokens=bucket["input_tokens"],
                output_tokens=bucket["output_tokens"],
            )
            for (provider, model), bucket in sorted(
                model_buckets.items(), key=lambda item: item[1]["total"], reverse=True
            )
        ],
        daily=daily,
        latest_runs=latest_runs[:30],
        probes=[
            _probe_view(item, principals.get(item.actor_principal_id, "未知主体"))
            for item in probes
        ],
        runtime_probes=[
            _runtime_probe_view(item, principals.get(item.actor_principal_id, "未知主体"))
            for item in runtime_probes
        ],
        runtime_sessions=_runtime_session_views(
            runtime_sessions,
            runtime_turns,
            runtime_events,
        ),
        runtime_approvals=[
            AgentRuntimeApprovalView(
                id=item.id,
                runtime_session_id=item.runtime_session_id,
                agent_run_id=item.agent_run_id,
                request_method=item.request_method,
                item_id=item.item_id,
                skill_key=item.skill_key,
                skill_version=item.skill_version,
                tool_keys=list(item.tool_keys),
                status=item.status,  # type: ignore[arg-type]
                decision=item.decision,
                requested_at=_as_utc(item.requested_at),
                decided_at=_as_utc(item.decided_at) if item.decided_at else None,
            )
            for item in runtime_approvals
        ],
        generated_at=now,
    )


def _provider_config(settings: Settings) -> AIProviderConfigView:
    official = "api.openai.com" in settings.ai_base_url.casefold()
    return AIProviderConfigView(
        provider_key=PROVIDER_KEY,
        label="OpenAI 兼容 Responses Provider",
        protocol=PROVIDER_PROTOCOL,
        endpoint_kind="official" if official else "private-compatible",
        enabled=settings.ai_enabled,
        configured=bool(settings.ai_enabled and settings.ai_api_key),
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
        capabilities=["responses", "json-schema", "usage-tokens", "no-store"],
    )


def _runtime_config(settings: Settings) -> AgentRuntimeConfigView:
    command_available = bool(
        shutil.which(settings.codex_command) or _is_file(settings.codex_command)
    )
    return AgentRuntimeConfigView(
        runtime_key=RUNTIME_KEY,
        label="Codex 开源 Harness",
        protocol=RUNTIME_PROTOCOL,
        enabled=settings.agent_runtime_enabled,
        command_available=command_available,
        model=settings.codex_runtime_model or None,
        timeout_seconds=settings.codex_runtime_timeout_seconds,
        capabilities=["start", "resume", "stream", "cancel", "mcp", "approvals"],
        default_sandbox="read-only",
        approval_policy="fail-closed",
    )


def _probe_view(item: AIProviderProbeRun, actor_name: str) -> AIProviderProbeRunView:
    return AIProviderProbeRunView(
        id=item.id,
        provider_key=item.provider_key,
        model=item.model,
        protocol=item.protocol,
        structured_output_supported=item.structured_output_supported,
        status=cast(Literal["succeeded", "failed"], item.status),
        duration_ms=item.duration_ms,
        input_tokens=item.input_tokens,
        output_tokens=item.output_tokens,
        error_code=item.error_code,
        error_message=item.error_message,
        actor_name=actor_name,
        request_id=item.request_id,
        run_id=item.run_id,
        created_at=_as_utc(item.created_at),
    )


def _runtime_probe_view(
    item: AgentRuntimeProbeRun,
    actor_name: str,
) -> AgentRuntimeProbeRunView:
    return AgentRuntimeProbeRunView(
        id=item.id,
        runtime_key=item.runtime_key,
        protocol=item.protocol,
        command_version=item.command_version,
        initialized=item.initialized,
        status=cast(Literal["succeeded", "failed"], item.status),
        duration_ms=item.duration_ms,
        error_code=item.error_code,
        error_message=item.error_message,
        actor_name=actor_name,
        request_id=item.request_id,
        run_id=item.run_id,
        created_at=_as_utc(item.created_at),
    )


def _runtime_session_views(
    runtime_sessions: list[AgentRuntimeSession],
    runtime_turns: list[AgentRuntimeTurn],
    runtime_events: list[AgentRuntimeEventRecord],
) -> list[AgentRuntimeSessionView]:
    turns_by_session: dict[str, list[AgentRuntimeTurn]] = defaultdict(list)
    events_by_session: dict[str, list[AgentRuntimeEventRecord]] = defaultdict(list)
    for turn in runtime_turns:
        turns_by_session[turn.runtime_session_id].append(turn)
    for event in runtime_events:
        events_by_session[event.runtime_session_id].append(event)
    return [
        AgentRuntimeSessionView(
            id=item.id,
            agent_run_id=item.agent_run_id,
            runtime_key=item.runtime_key,
            runtime_thread_id=item.runtime_thread_id,
            runtime_session_id=item.runtime_session_id,
            mcp_gateway_session_id=item.mcp_gateway_session_id,
            status=item.status,
            model=(
                turns_by_session[item.id][-1].model
                if turns_by_session[item.id]
                else None
            ),
            turn_count=len(turns_by_session[item.id]),
            event_count=len(events_by_session[item.id]),
            latest_event_type=(
                events_by_session[item.id][-1].event_type
                if events_by_session[item.id]
                else None
            ),
            can_cancel=item.status in {"starting", "running", "waiting_approval"},
            failure_code=item.failure_code,
            failure_message=item.failure_message,
            request_id=item.request_id,
            run_id=item.run_id,
            created_at=_as_utc(item.created_at),
            completed_at=_as_utc(item.completed_at) if item.completed_at else None,
        )
        for item in runtime_sessions
    ]


def _is_file(value: str) -> bool:
    from pathlib import Path

    return Path(value).is_file()


def _empty_bucket() -> dict[str, int]:
    return {
        "total": 0,
        "successful": 0,
        "degraded": 0,
        "duration_ms": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _add_run(
    bucket: dict[str, int],
    succeeded: bool,
    duration_ms: int,
    input_tokens: int | None,
    output_tokens: int | None,
) -> None:
    bucket["total"] += 1
    bucket["successful" if succeeded else "degraded"] += 1
    bucket["duration_ms"] += duration_ms
    bucket["input_tokens"] += input_tokens or 0
    bucket["output_tokens"] += output_tokens or 0


def _bucket_average(bucket: dict[str, int]) -> int:
    return round(bucket["duration_ms"] / bucket["total"]) if bucket["total"] else 0


def _duration_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, round((_as_utc(completed_at) - _as_utc(started_at)).total_seconds() * 1000))


def _runtime_turn_duration(item: AgentRuntimeTurn) -> int:
    end = item.completed_at or datetime.now(UTC)
    return _duration_ms(item.started_at, end)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _sanitize_error(value: str) -> str:
    redacted = _URL_PATTERN.sub("[redacted-url]", value)
    redacted = _BEARER_PATTERN.sub("Bearer [redacted]", redacted)
    redacted = _KEY_PATTERN.sub("[redacted-key]", redacted)
    return redacted[:500]
