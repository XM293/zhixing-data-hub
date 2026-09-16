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
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeProviderEvaluationResult,
    KnowledgeProviderEvaluationRun,
    KnowledgeVersion,
    Principal,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.knowledge_providers import (
    KnowledgeProvider,
    ProviderKnowledgeChunk,
    ProviderKnowledgeDocument,
    ProviderKnowledgeHit,
    ProviderKnowledgeIndex,
)
from zhixing_api.knowledge_schemas import (
    KnowledgeBenchmarkCaseView,
    KnowledgeProviderDescriptorView,
    KnowledgeProviderEvaluationRequest,
    KnowledgeProviderEvaluationResultView,
    KnowledgeProviderEvaluationRunView,
    KnowledgeProviderOperationsResponse,
    KnowledgeProviderQueryResultView,
)

BENCHMARK_VERSION = "enterprise-knowledge-retrieval-v1"
_BENCHMARK_DEFINITIONS = (
    (
        "diagnosis-order",
        "operating-diagnosis",
        "店铺成交异常时应该按什么顺序诊断？",
        "诊断顺序",
    ),
    (
        "budget-approval",
        "budget-governance",
        "单店新增广告预算超过 5 万元需要谁审批？",
        "预算分级",
    ),
    (
        "budget-stop",
        "budget-governance",
        "广告 ROI 和库存达到什么条件应该停止扩量？",
        "止损条件",
    ),
    (
        "refund-kpi",
        "performance-policy",
        "当前退款率指标占月度绩效多少，口径是什么？",
        "退款率考核",
    ),
    (
        "inventory-alert",
        "inventory-policy",
        "库存覆盖低于 3 天时应该如何处理？",
        "预警分级",
    ),
    (
        "service-compensation",
        "service-policy",
        "普通客服可以承诺的补偿范围是什么？",
        "普通补偿权限",
    ),
    (
        "service-handoff",
        "service-policy",
        "哪些高风险客户会话必须立即转人工？",
        "高风险会话",
    ),
    (
        "decision-guardrail",
        "decision-governance",
        "数字分身能否直接修改预算或自动执行？",
        "保留条件",
    ),
)
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
    indexed_document_count: int
    indexed_chunk_count: int
    query_count: int
    hit_count: int
    recall_at_k: float
    mean_reciprocal_rank: float
    average_latency_ms: int
    p95_latency_ms: int
    items: list[dict[str, object]]
    failure_reason: str | None


def knowledge_provider_operations(
    database: Database,
    providers: dict[str, KnowledgeProvider],
    *,
    enterprise_id: str,
) -> KnowledgeProviderOperationsResponse:
    documents, cases = _active_documents_and_cases(database, enterprise_id)
    with database.session() as session:
        runs = list(
            session.scalars(
                select(KnowledgeProviderEvaluationRun)
                .where(KnowledgeProviderEvaluationRun.enterprise_id == enterprise_id)
                .order_by(KnowledgeProviderEvaluationRun.created_at.desc())
                .limit(12)
            )
        )
        run_ids = [item.id for item in runs]
        results = (
            list(
                session.scalars(
                    select(KnowledgeProviderEvaluationResult)
                    .where(KnowledgeProviderEvaluationResult.evaluation_run_id.in_(run_ids))
                    .order_by(KnowledgeProviderEvaluationResult.created_at.asc())
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

    results_by_run: dict[str, list[KnowledgeProviderEvaluationResult]] = {}
    for result in results:
        results_by_run.setdefault(result.evaluation_run_id, []).append(result)
    return KnowledgeProviderOperationsResponse(
        benchmark_version=BENCHMARK_VERSION,
        active_document_count=len(documents),
        active_chunk_count=sum(len(item.chunks) for item in documents),
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


async def run_knowledge_provider_evaluation(
    database: Database,
    providers: dict[str, KnowledgeProvider],
    actor: ActorContext,
    payload: KnowledgeProviderEvaluationRequest,
) -> KnowledgeProviderEvaluationRunView:
    provider_keys = list(dict.fromkeys(payload.provider_keys))
    missing = [key for key in provider_keys if key not in providers]
    if missing:
        raise ApiProblem(
            status_code=422,
            code="knowledge.provider_not_registered",
            message="请求包含未注册的知识 Provider",
            details={"provider_keys": missing},
        )
    request_hash = sha256(
        json.dumps(
            payload.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    with database.session() as session:
        existing = session.scalar(
            select(KnowledgeProviderEvaluationRun).where(
                KnowledgeProviderEvaluationRun.enterprise_id == actor.enterprise_id,
                KnowledgeProviderEvaluationRun.idempotency_key == payload.client_request_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ApiProblem(
                    status_code=409,
                    code="knowledge.provider_evaluation_idempotency_conflict",
                    message="该幂等键已经用于不同的知识 Provider 评测请求",
                )
            results = list(
                session.scalars(
                    select(KnowledgeProviderEvaluationResult)
                    .where(KnowledgeProviderEvaluationResult.evaluation_run_id == existing.id)
                    .order_by(KnowledgeProviderEvaluationResult.created_at.asc())
                )
            )
            principal = session.get(Principal, existing.actor_principal_id)
            actor_name = principal.display_name if principal else "未知主体"
            return _run_view(
                existing,
                results,
                actor_name=actor_name,
                idempotent=True,
            )

    documents, cases = _active_documents_and_cases(database, actor.enterprise_id)
    if not documents or not cases:
        raise ApiProblem(
            status_code=409,
            code="knowledge.provider_evaluation_no_effective_knowledge",
            message="当前没有足够的生效知识切片用于双跑评测",
        )

    now = datetime.now(UTC)
    evaluation = KnowledgeProviderEvaluationRun(
        id=f"kno_eval_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        actor_principal_id=actor.principal_id,
        evaluation_key=f"knowledge-provider-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
        benchmark_version=BENCHMARK_VERSION,
        status="running",
        provider_keys=provider_keys,
        benchmark_snapshot=[item.model_dump(mode="json") for item in cases],
        document_count=len(documents),
        chunk_count=sum(len(item.chunks) for item in documents),
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
                documents=documents,
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
        stored_run = session.get(KnowledgeProviderEvaluationRun, evaluation.id)
        if stored_run is None:
            raise RuntimeError("知识 Provider 评测运行在持久化期间丢失")
        stored_run.status = final_status
        stored_run.finished_at = finished_at
        for item in outcomes:
            session.add(
                KnowledgeProviderEvaluationResult(
                    id=f"kno_eval_result_{uuid4().hex}",
                    evaluation_run_id=evaluation.id,
                    provider_key=item.provider_key,
                    provider_mode=item.provider_mode,
                    protocol=item.protocol,
                    endpoint_fingerprint=item.endpoint_fingerprint,
                    status=item.status,
                    indexed_document_count=item.indexed_document_count,
                    indexed_chunk_count=item.indexed_chunk_count,
                    query_count=item.query_count,
                    hit_count=item.hit_count,
                    recall_at_k=item.recall_at_k,
                    mean_reciprocal_rank=item.mean_reciprocal_rank,
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
                select(KnowledgeProviderEvaluationResult)
                .where(KnowledgeProviderEvaluationResult.evaluation_run_id == evaluation.id)
                .order_by(KnowledgeProviderEvaluationResult.created_at.asc())
            )
        )
    return _run_view(stored_run, results, actor_name=actor.display_name)


async def _evaluate_provider(
    provider: KnowledgeProvider,
    *,
    namespace: str,
    documents: list[ProviderKnowledgeDocument],
    cases: list[KnowledgeBenchmarkCaseView],
    top_k: int,
) -> ProviderOutcome:
    try:
        await provider.health()
        index = await provider.index_documents(namespace, documents)
        items: list[dict[str, object]] = []
        latencies: list[int] = []
        reciprocal_ranks: list[float] = []
        hit_count = 0
        for case in cases:
            started = perf_counter()
            hits = await _search_with_retry(provider, index, case.query, top_k=top_k)
            latency_ms = max(1, round((perf_counter() - started) * 1000))
            returned_keys = _returned_chunk_keys(hits, documents)
            expected = set(case.expected_chunk_keys)
            first_rank = next(
                (index + 1 for index, key in enumerate(returned_keys) if key in expected),
                None,
            )
            reciprocal_rank = round(1 / first_rank, 4) if first_rank else 0.0
            hit = first_rank is not None
            hit_count += int(hit)
            latencies.append(latency_ms)
            reciprocal_ranks.append(reciprocal_rank)
            items.append(
                {
                    "case_key": case.key,
                    "query": case.query,
                    "expected_chunk_keys": case.expected_chunk_keys,
                    "returned_chunk_keys": returned_keys,
                    "hit": hit,
                    "reciprocal_rank": reciprocal_rank,
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
            indexed_document_count=index.document_count,
            indexed_chunk_count=index.chunk_count,
            query_count=len(cases),
            hit_count=hit_count,
            recall_at_k=round(hit_count / len(cases), 4),
            mean_reciprocal_rank=round(sum(reciprocal_ranks) / len(cases), 4),
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
            indexed_document_count=0,
            indexed_chunk_count=0,
            query_count=len(cases),
            hit_count=0,
            recall_at_k=0.0,
            mean_reciprocal_rank=0.0,
            average_latency_ms=0,
            p95_latency_ms=0,
            items=[],
            failure_reason=_sanitize_failure(str(exc) or exc.__class__.__name__),
        )


async def _search_with_retry(
    provider: KnowledgeProvider,
    index: ProviderKnowledgeIndex,
    query: str,
    *,
    top_k: int,
) -> list[ProviderKnowledgeHit]:
    hits = await provider.search(index, query, top_k=top_k)
    if hits:
        return hits
    await asyncio.sleep(0.25)
    return await provider.search(index, query, top_k=top_k)


def _active_documents_and_cases(
    database: Database,
    enterprise_id: str,
) -> tuple[list[ProviderKnowledgeDocument], list[KnowledgeBenchmarkCaseView]]:
    with database.session() as session:
        rows = list(
            session.execute(
                select(KnowledgeDocument, KnowledgeVersion, KnowledgeChunk)
                .join(KnowledgeVersion, KnowledgeVersion.document_id == KnowledgeDocument.id)
                .join(KnowledgeChunk, KnowledgeChunk.version_id == KnowledgeVersion.id)
                .where(
                    KnowledgeDocument.enterprise_id == enterprise_id,
                    KnowledgeDocument.status == "active",
                    KnowledgeVersion.status.in_(("active", "published", "scheduled")),
                    KnowledgeChunk.index_status == "indexed",
                )
                .order_by(
                    KnowledgeDocument.document_key.asc(),
                    KnowledgeVersion.version_number.asc(),
                    KnowledgeChunk.sequence.asc(),
                )
            )
        )
    now = datetime.now(UTC)
    effective_rows = [row for row in rows if _is_effective(row[1], now)]
    grouped: dict[tuple[str, str], list[KnowledgeChunk]] = {}
    row_lookup: dict[tuple[str, str], tuple[KnowledgeDocument, KnowledgeVersion]] = {}
    for document, version, chunk in effective_rows:
        key = (document.id, version.id)
        grouped.setdefault(key, []).append(chunk)
        row_lookup[key] = (document, version)
    documents = [
        ProviderKnowledgeDocument(
            document_key=document.document_key,
            title=document.title,
            version_label=version.version_label,
            chunks=[
                ProviderKnowledgeChunk(
                    chunk_key=chunk.chunk_key,
                    heading=chunk.heading,
                    content=chunk.content,
                    locator=chunk.locator,
                )
                for chunk in chunks
            ],
        )
        for key, chunks in grouped.items()
        for document, version in [row_lookup[key]]
    ]
    cases = _benchmark_cases(documents)
    return documents, cases


def _is_effective(version: KnowledgeVersion, now: datetime) -> bool:
    start = _as_utc(version.effective_from)
    end = _as_utc(version.effective_until)
    return (start is None or start <= now) and (end is None or end > now)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _benchmark_cases(
    documents: list[ProviderKnowledgeDocument],
) -> list[KnowledgeBenchmarkCaseView]:
    chunks = [
        (document, chunk)
        for document in documents
        for chunk in document.chunks
    ]
    cases: list[KnowledgeBenchmarkCaseView] = []
    for case_key, category, query, heading in _BENCHMARK_DEFINITIONS:
        matches = [item for item in chunks if item[1].heading == heading]
        if not matches:
            continue
        cases.append(
            KnowledgeBenchmarkCaseView(
                key=f"{BENCHMARK_VERSION}:{case_key}",
                category=category,
                query=query,
                expected_chunk_keys=sorted({chunk.chunk_key for _, chunk in matches}),
                expected_document_keys=sorted(
                    {document.document_key for document, _ in matches}
                ),
            )
        )
    if cases:
        return cases
    return [
        KnowledgeBenchmarkCaseView(
            key=f"{BENCHMARK_VERSION}:fallback-{index + 1}",
            category="effective-knowledge",
            query=f"{chunk.heading} 的现行规则是什么？",
            expected_chunk_keys=[chunk.chunk_key],
            expected_document_keys=[document.document_key],
        )
        for index, (document, chunk) in enumerate(chunks[:8])
    ]


def _returned_chunk_keys(
    hits: list[ProviderKnowledgeHit],
    documents: list[ProviderKnowledgeDocument],
) -> list[str]:
    chunks = [item for document in documents for item in document.chunks]
    known = {item.chunk_key for item in chunks}
    returned: list[str] = []
    for hit in hits:
        key = hit.chunk_key if hit.chunk_key in known else _infer_chunk_key(hit.content, chunks)
        if key and key not in returned:
            returned.append(key)
    return returned


def _infer_chunk_key(
    content: str,
    chunks: list[ProviderKnowledgeChunk],
) -> str | None:
    content_tokens = set(_TEXT_TOKEN.findall(content.casefold()))
    scored: list[tuple[float, str]] = []
    for chunk in chunks:
        chunk_tokens = set(_TEXT_TOKEN.findall(chunk.content.casefold()))
        union = content_tokens | chunk_tokens
        score = len(content_tokens & chunk_tokens) / len(union) if union else 0.0
        scored.append((score, chunk.chunk_key))
    scored.sort(reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 0.35 else None


def _provider_descriptor(provider: KnowledgeProvider) -> KnowledgeProviderDescriptorView:
    return KnowledgeProviderDescriptorView(
        key=provider.key,
        label=provider.label,
        protocol=provider.protocol,
        mode=provider.mode,
        endpoint_fingerprint=provider.endpoint_fingerprint,
        authentication_configured=provider.authentication_configured,
    )


def _run_view(
    run: KnowledgeProviderEvaluationRun,
    results: list[KnowledgeProviderEvaluationResult],
    *,
    actor_name: str,
    idempotent: bool = False,
) -> KnowledgeProviderEvaluationRunView:
    return KnowledgeProviderEvaluationRunView(
        id=run.id,
        evaluation_key=run.evaluation_key,
        benchmark_version=run.benchmark_version,
        status=run.status,  # type: ignore[arg-type]
        provider_keys=run.provider_keys,
        document_count=run.document_count,
        chunk_count=run.chunk_count,
        case_count=run.case_count,
        actor_name=actor_name,
        idempotent=idempotent,
        request_id=run.request_id,
        run_id=run.run_id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        results=[_result_view(item) for item in results],
    )


def _result_view(
    item: KnowledgeProviderEvaluationResult,
) -> KnowledgeProviderEvaluationResultView:
    return KnowledgeProviderEvaluationResultView(
        provider_key=item.provider_key,
        provider_mode=item.provider_mode,
        protocol=item.protocol,
        endpoint_fingerprint=item.endpoint_fingerprint,
        status=item.status,  # type: ignore[arg-type]
        indexed_document_count=item.indexed_document_count,
        indexed_chunk_count=item.indexed_chunk_count,
        query_count=item.query_count,
        hit_count=item.hit_count,
        recall_at_k=item.recall_at_k,
        mean_reciprocal_rank=item.mean_reciprocal_rank,
        average_latency_ms=item.average_latency_ms,
        p95_latency_ms=item.p95_latency_ms,
        items=[
            KnowledgeProviderQueryResultView.model_validate(value)
            for value in item.result_items
        ],
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
