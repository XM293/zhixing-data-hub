from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import ceil
from time import perf_counter
from uuid import uuid4

from sqlalchemy import select

from zhixing_api.actor_context import ActorContext
from zhixing_api.data_models import (
    ApprovedMemory,
    MemoryProviderEvaluationResult,
    MemoryProviderEvaluationRun,
    Principal,
    RoleTwinProfile,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.memory_providers import MemoryProvider, ProviderHit, ProviderMemory
from zhixing_api.memory_schemas import (
    MemoryBenchmarkCaseView,
    MemoryProviderDescriptorView,
    MemoryProviderEvaluationRequest,
    MemoryProviderEvaluationResultView,
    MemoryProviderEvaluationRunView,
    MemoryProviderOperationsResponse,
    MemoryProviderQueryResultView,
)

BENCHMARK_VERSION = "role-memory-provider-smoke-v1"
_CATEGORY_QUERIES = {
    "communication-style": "管理汇报和会议表达应该如何组织结论、证据与责任？",
    "decision-rule": "新建议与现行制度冲突时，管理决策应该遵循什么优先级？",
    "risk-rule": "财务评审经营动作时应该设置哪些停止条件和风险边界？",
    "operating-rule": "运营试验应该如何控制范围、观察周期和复盘节奏？",
    "service-rule": "客服处理客户问题时应该遵循哪些顺序和承诺边界？",
}
_URL_PATTERN = re.compile(r"https?://[^\s，。；;]+", re.IGNORECASE)
_TOKEN_PATTERN = re.compile(r"bearer\s+[^\s]+|(?:sk|key|token)[-_][a-z0-9_-]{8,}", re.I)
_TEXT_TOKEN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    provider_key: str
    provider_mode: str
    protocol: str
    endpoint_fingerprint: str
    status: str
    indexed_memory_count: int
    query_count: int
    hit_count: int
    recall_at_k: float
    average_latency_ms: int
    p95_latency_ms: int
    items: list[dict[str, object]]
    failure_reason: str | None


def memory_provider_operations(
    database: Database,
    providers: dict[str, MemoryProvider],
    *,
    enterprise_id: str,
) -> MemoryProviderOperationsResponse:
    memories, cases = _active_memories_and_cases(database, enterprise_id)
    with database.session() as session:
        runs = list(
            session.scalars(
                select(MemoryProviderEvaluationRun)
                .where(MemoryProviderEvaluationRun.enterprise_id == enterprise_id)
                .order_by(MemoryProviderEvaluationRun.created_at.desc())
                .limit(12)
            )
        )
        run_ids = [item.id for item in runs]
        result_rows = (
            list(
                session.scalars(
                    select(MemoryProviderEvaluationResult)
                    .where(MemoryProviderEvaluationResult.evaluation_run_id.in_(run_ids))
                    .order_by(MemoryProviderEvaluationResult.created_at.asc())
                )
            )
            if run_ids
            else []
        )
        actor_ids = {item.actor_principal_id for item in runs}
        actors = {
            item.id: item.display_name
            for item in session.scalars(select(Principal).where(Principal.id.in_(actor_ids)))
        }

    results_by_run: dict[str, list[MemoryProviderEvaluationResult]] = {}
    for result in result_rows:
        results_by_run.setdefault(result.evaluation_run_id, []).append(result)
    return MemoryProviderOperationsResponse(
        benchmark_version=BENCHMARK_VERSION,
        active_memory_count=len(memories),
        benchmark_cases=cases,
        providers=[_provider_descriptor(item) for item in providers.values()],
        runs=[
            _run_view(
                item,
                results_by_run.get(item.id, []),
                actor_name=actors.get(item.actor_principal_id, "未知主体"),
            )
            for item in runs
        ],
        generated_at=datetime.now(UTC),
    )


async def run_memory_provider_evaluation(
    database: Database,
    providers: dict[str, MemoryProvider],
    actor: ActorContext,
    payload: MemoryProviderEvaluationRequest,
) -> MemoryProviderEvaluationRunView:
    provider_keys = list(dict.fromkeys(payload.provider_keys))
    missing = [key for key in provider_keys if key not in providers]
    if missing:
        raise ApiProblem(
            status_code=422,
            code="memory.provider_not_registered",
            message="请求包含未注册的记忆 Provider",
            details={"provider_keys": missing},
        )
    request_body = payload.model_dump(mode="json")
    request_hash = sha256(
        json.dumps(request_body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    with database.session() as session:
        existing = session.scalar(
            select(MemoryProviderEvaluationRun).where(
                MemoryProviderEvaluationRun.enterprise_id == actor.enterprise_id,
                MemoryProviderEvaluationRun.idempotency_key == payload.client_request_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ApiProblem(
                    status_code=409,
                    code="memory.provider_evaluation_idempotency_conflict",
                    message="该幂等键已经用于不同的记忆 Provider 评测请求",
                )
            results = list(
                session.scalars(
                    select(MemoryProviderEvaluationResult)
                    .where(MemoryProviderEvaluationResult.evaluation_run_id == existing.id)
                    .order_by(MemoryProviderEvaluationResult.created_at.asc())
                )
            )
            return _run_view(existing, results, actor_name=actor.display_name, idempotent=True)

    memories, cases = _active_memories_and_cases(database, actor.enterprise_id)
    if not memories or not cases:
        raise ApiProblem(
            status_code=409,
            code="memory.provider_evaluation_no_active_memory",
            message="当前没有足够的已激活角色记忆用于双跑评测",
        )

    now = datetime.now(UTC)
    evaluation = MemoryProviderEvaluationRun(
        id=f"mem_eval_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        actor_principal_id=actor.principal_id,
        evaluation_key=f"memory-provider-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
        benchmark_version=BENCHMARK_VERSION,
        status="running",
        provider_keys=provider_keys,
        benchmark_snapshot=[item.model_dump(mode="json") for item in cases],
        memory_count=len(memories),
        case_count=len(cases),
        actor_snapshot=actor.snapshot(),
        idempotency_key=payload.client_request_key,
        request_hash=request_hash,
        request_id=actor.request_id,
        run_id=actor.run_id,
        started_at=now,
        finished_at=None,
        created_at=now,
    )
    with database.session() as session:
        session.add(evaluation)
        session.commit()

    namespace = f"{actor.enterprise_id}:{evaluation.id}"
    outcomes = await asyncio.gather(
        *[
            _evaluate_provider(
                providers[key],
                namespace=namespace,
                memories=memories,
                cases=cases,
                top_k=payload.top_k,
            )
            for key in provider_keys
        ]
    )
    succeeded = sum(item.status == "succeeded" for item in outcomes)
    final_status = (
        "completed"
        if succeeded == len(outcomes)
        else "partial"
        if succeeded
        else "failed"
    )
    finished_at = datetime.now(UTC)
    with database.session() as session:
        stored_run = session.get(MemoryProviderEvaluationRun, evaluation.id)
        if stored_run is None:
            raise RuntimeError("记忆 Provider 评测运行在持久化期间丢失")
        stored_run.status = final_status
        stored_run.finished_at = finished_at
        for item in outcomes:
            session.add(
                MemoryProviderEvaluationResult(
                    id=f"mem_eval_result_{uuid4().hex}",
                    evaluation_run_id=evaluation.id,
                    provider_key=item.provider_key,
                    provider_mode=item.provider_mode,
                    protocol=item.protocol,
                    endpoint_fingerprint=item.endpoint_fingerprint,
                    status=item.status,
                    indexed_memory_count=item.indexed_memory_count,
                    query_count=item.query_count,
                    hit_count=item.hit_count,
                    recall_at_k=item.recall_at_k,
                    average_latency_ms=item.average_latency_ms,
                    p95_latency_ms=item.p95_latency_ms,
                    result_items=item.items,
                    failure_reason=item.failure_reason,
                    created_at=finished_at,
                )
            )
        session.commit()
        session.refresh(stored_run)
        results = list(
            session.scalars(
                select(MemoryProviderEvaluationResult)
                .where(MemoryProviderEvaluationResult.evaluation_run_id == evaluation.id)
                .order_by(MemoryProviderEvaluationResult.created_at.asc())
            )
        )
    return _run_view(stored_run, results, actor_name=actor.display_name)


async def _evaluate_provider(
    provider: MemoryProvider,
    *,
    namespace: str,
    memories: list[ProviderMemory],
    cases: list[MemoryBenchmarkCaseView],
    top_k: int,
) -> ProviderOutcome:
    try:
        await provider.health()
        indexed_count = await provider.index_memories(namespace, memories)
        items: list[dict[str, object]] = []
        latencies: list[int] = []
        hit_count = 0
        for case in cases:
            started = perf_counter()
            hits = await _search_with_retry(provider, namespace, case.query, top_k=top_k)
            latency_ms = max(1, round((perf_counter() - started) * 1000))
            returned_keys = _returned_memory_keys(hits, memories)
            hit = bool(set(case.expected_memory_keys) & set(returned_keys))
            hit_count += int(hit)
            latencies.append(latency_ms)
            items.append(
                {
                    "case_key": case.key,
                    "query": case.query,
                    "expected_memory_keys": case.expected_memory_keys,
                    "returned_memory_keys": returned_keys,
                    "hit": hit,
                    "latency_ms": latency_ms,
                    "top_score": round(hits[0].score, 6) if hits else 0.0,
                }
            )
        return ProviderOutcome(
            provider_key=provider.key,
            provider_mode=provider.mode,
            protocol=provider.protocol,
            endpoint_fingerprint=provider.endpoint_fingerprint,
            status="succeeded",
            indexed_memory_count=indexed_count,
            query_count=len(cases),
            hit_count=hit_count,
            recall_at_k=round(hit_count / len(cases), 4),
            average_latency_ms=round(sum(latencies) / len(latencies)),
            p95_latency_ms=_percentile_95(latencies),
            items=items,
            failure_reason=None,
        )
    except Exception as exc:  # Provider failures are isolated and retained for comparison.
        return ProviderOutcome(
            provider_key=provider.key,
            provider_mode=provider.mode,
            protocol=provider.protocol,
            endpoint_fingerprint=provider.endpoint_fingerprint,
            status="failed",
            indexed_memory_count=0,
            query_count=len(cases),
            hit_count=0,
            recall_at_k=0.0,
            average_latency_ms=0,
            p95_latency_ms=0,
            items=[],
            failure_reason=_sanitize_failure(str(exc) or exc.__class__.__name__),
        )


async def _search_with_retry(
    provider: MemoryProvider,
    namespace: str,
    query: str,
    *,
    top_k: int,
) -> list[ProviderHit]:
    hits = await provider.search(namespace, query, top_k=top_k)
    if hits:
        return hits
    await asyncio.sleep(0.25)
    return await provider.search(namespace, query, top_k=top_k)


def _active_memories_and_cases(
    database: Database,
    enterprise_id: str,
) -> tuple[list[ProviderMemory], list[MemoryBenchmarkCaseView]]:
    with database.session() as session:
        rows = list(
            session.execute(
                select(ApprovedMemory, RoleTwinProfile)
                .join(RoleTwinProfile, RoleTwinProfile.id == ApprovedMemory.twin_profile_id)
                .where(
                    ApprovedMemory.enterprise_id == enterprise_id,
                    ApprovedMemory.status == "active",
                )
                .order_by(ApprovedMemory.memory_key.asc())
            )
        )
    memories = [
        ProviderMemory(
            memory_key=memory.memory_key,
            content=memory.content,
            category=memory.category,
        )
        for memory, _ in rows
    ]
    grouped: dict[str, list[tuple[ApprovedMemory, RoleTwinProfile]]] = {}
    for memory, profile in rows:
        grouped.setdefault(memory.category, []).append((memory, profile))
    cases = [
        MemoryBenchmarkCaseView(
            key=f"{BENCHMARK_VERSION}:{category}",
            category=category,
            query=_CATEGORY_QUERIES.get(
                category,
                f"关于 {category} 的已审核角色经验是什么？",
            ),
            expected_memory_keys=sorted(item.memory_key for item, _ in category_rows),
            expected_twin_keys=sorted({profile.twin_key for _, profile in category_rows}),
        )
        for category, category_rows in sorted(grouped.items())
    ]
    return memories, cases


def _returned_memory_keys(
    hits: list[ProviderHit],
    memories: list[ProviderMemory],
) -> list[str]:
    known = {item.memory_key for item in memories}
    returned: list[str] = []
    for hit in hits:
        key = (
            hit.memory_key
            if hit.memory_key in known
            else _infer_memory_key(hit.content, memories)
        )
        if key and key not in returned:
            returned.append(key)
    return returned


def _infer_memory_key(content: str, memories: list[ProviderMemory]) -> str | None:
    content_tokens = set(_TEXT_TOKEN.findall(content.casefold()))
    scored: list[tuple[float, str]] = []
    for memory in memories:
        memory_tokens = set(_TEXT_TOKEN.findall(memory.content.casefold()))
        union = content_tokens | memory_tokens
        score = len(content_tokens & memory_tokens) / len(union) if union else 0.0
        scored.append((score, memory.memory_key))
    scored.sort(reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 0.35 else None


def _provider_descriptor(provider: MemoryProvider) -> MemoryProviderDescriptorView:
    return MemoryProviderDescriptorView(
        key=provider.key,
        label=provider.label,
        protocol=provider.protocol,
        mode=provider.mode,
        endpoint_fingerprint=provider.endpoint_fingerprint,
        authentication_configured=provider.authentication_configured,
    )


def _run_view(
    run: MemoryProviderEvaluationRun,
    results: list[MemoryProviderEvaluationResult],
    *,
    actor_name: str,
    idempotent: bool = False,
) -> MemoryProviderEvaluationRunView:
    return MemoryProviderEvaluationRunView(
        id=run.id,
        evaluation_key=run.evaluation_key,
        benchmark_version=run.benchmark_version,
        status=run.status,  # type: ignore[arg-type]
        provider_keys=run.provider_keys,
        memory_count=run.memory_count,
        case_count=run.case_count,
        actor_name=actor_name,
        idempotent=idempotent,
        request_id=run.request_id,
        run_id=run.run_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        results=[_result_view(item) for item in results],
    )


def _result_view(item: MemoryProviderEvaluationResult) -> MemoryProviderEvaluationResultView:
    return MemoryProviderEvaluationResultView(
        provider_key=item.provider_key,
        provider_mode=item.provider_mode,
        protocol=item.protocol,
        endpoint_fingerprint=item.endpoint_fingerprint,
        status=item.status,  # type: ignore[arg-type]
        indexed_memory_count=item.indexed_memory_count,
        query_count=item.query_count,
        hit_count=item.hit_count,
        recall_at_k=item.recall_at_k,
        average_latency_ms=item.average_latency_ms,
        p95_latency_ms=item.p95_latency_ms,
        items=[MemoryProviderQueryResultView.model_validate(value) for value in item.result_items],
        failure_reason=item.failure_reason,
    )


def _percentile_95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, ceil(len(ordered) * 0.95) - 1)]


def _sanitize_failure(value: str) -> str:
    sanitized = _URL_PATTERN.sub("[provider-endpoint]", value)
    sanitized = _TOKEN_PATTERN.sub("[redacted]", sanitized)
    return sanitized[:500]
