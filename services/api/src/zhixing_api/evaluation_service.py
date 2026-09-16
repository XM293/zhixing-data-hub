from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from sqlalchemy import select
from zhixing_agent_runtime import AgentRuntime

from zhixing_api.actor_context import ActorContext, require_permission, resolve_database_actor
from zhixing_api.ai_provider import ResponsesAIProvider
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentFeedbackEvent,
    AgentRun,
    AgentRunContextItem,
    AgentRunEvidence,
    EvaluationCandidate,
    EvaluationCase,
    EvaluationRun,
    EvaluationRunItem,
    EvaluationSuite,
    HumanHandoffCase,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    Principal,
    RoleTwinProfile,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.evaluation_schemas import (
    EvaluationCandidateActionRequest,
    EvaluationCandidateMutationResponse,
    EvaluationCandidateView,
    EvaluationCaseView,
    EvaluationCheckView,
    EvaluationRunItemView,
    EvaluationRunMutationResponse,
    EvaluationRunView,
    EvaluationStudioResponse,
    EvaluationStudioStats,
    EvaluationSuiteView,
)
from zhixing_api.knowledge_schemas import TwinAnswerResponse
from zhixing_api.knowledge_service import answer_with_twin


def list_evaluation_studio(database: Database, actor: ActorContext) -> EvaluationStudioResponse:
    with database.session() as session:
        suites = list(
            session.scalars(
                select(EvaluationSuite)
                .where(EvaluationSuite.enterprise_id == actor.enterprise_id)
                .order_by(EvaluationSuite.suite_key, EvaluationSuite.version_number.desc())
            )
        )
        suite_ids = [item.id for item in suites]
        cases = list(
            session.scalars(
                select(EvaluationCase)
                .where(EvaluationCase.suite_id.in_(suite_ids))
                .order_by(EvaluationCase.case_key)
            )
        ) if suite_ids else []
        runs = list(
            session.scalars(
                select(EvaluationRun)
                .where(EvaluationRun.suite_id.in_(suite_ids))
                .order_by(EvaluationRun.started_at.desc())
            )
        ) if suite_ids else []
        run_ids = [item.id for item in runs]
        items = list(
            session.scalars(
                select(EvaluationRunItem)
                .where(EvaluationRunItem.evaluation_run_id.in_(run_ids))
                .order_by(EvaluationRunItem.created_at, EvaluationRunItem.case_key)
            )
        ) if run_ids else []
        candidates = list(
            session.scalars(
                select(EvaluationCandidate)
                .where(EvaluationCandidate.enterprise_id == actor.enterprise_id)
                .order_by(EvaluationCandidate.created_at.desc())
            )
        )
        principal_ids = {
            *(item.initiated_by_principal_id for item in runs),
            *(item.actor_principal_id for item in items if item.actor_principal_id),
            *(item.proposed_by_principal_id for item in candidates),
            *(
                item.reviewed_by_principal_id
                for item in candidates
                if item.reviewed_by_principal_id
            ),
        }
        principals = list(
            session.scalars(select(Principal).where(Principal.id.in_(principal_ids)))
        ) if principal_ids else []

    case_by_id = {item.id: item for item in cases}
    suite_by_id = {item.id: item for item in suites}
    principal_by_id = {item.id: item for item in principals}
    items_by_run: dict[str, list[EvaluationRunItem]] = {}
    runs_by_suite: dict[str, list[EvaluationRun]] = {}
    cases_by_suite: dict[str, list[EvaluationCase]] = {}
    run_by_id = {item.id: item for item in runs}
    for run_item in items:
        items_by_run.setdefault(run_item.evaluation_run_id, []).append(run_item)
    for evaluation_run in runs:
        runs_by_suite.setdefault(evaluation_run.suite_id, []).append(evaluation_run)
    for evaluation_case in cases:
        cases_by_suite.setdefault(evaluation_case.suite_id, []).append(evaluation_case)
    run_views = {
        item.id: _run_view(
            item,
            suite_by_id[item.suite_id],
            items_by_run.get(item.id, []),
            case_by_id,
            principal_by_id,
            run_by_id,
        )
        for item in runs
    }
    suite_views: list[EvaluationSuiteView] = []
    for suite in suites:
        suite_runs = runs_by_suite.get(suite.id, [])
        suite_views.append(
            EvaluationSuiteView(
                key=suite.suite_key,
                version_number=suite.version_number,
                domain=suite.domain,
                title=suite.title,
                description=suite.description,
                status=suite.status,
                cases=[_case_view(item) for item in cases_by_suite.get(suite.id, [])],
                latest_run=run_views[suite_runs[0].id] if suite_runs else None,
                recent_runs=[run_views[item.id] for item in suite_runs],
            )
        )
    latest_run = runs[0] if runs else None
    return EvaluationStudioResponse(
        stats=EvaluationStudioStats(
            suite_count=len(suites),
            case_count=len(cases),
            run_count=len(runs),
            latest_pass_rate=latest_run.pass_rate if latest_run else None,
            pending_manual_review_count=(latest_run.review_required_count if latest_run else 0),
            candidate_count=len(candidates),
            pending_candidate_count=sum(item.status == "pending" for item in candidates),
        ),
        suites=suite_views,
        candidates=[_candidate_view(item, principal_by_id) for item in candidates],
        generated_at=datetime.now(UTC),
    )


def propose_evaluation_candidate_from_resolution(
    database: Database,
    actor: ActorContext,
    *,
    handoff_case_id: str,
    feedback_event_id: str,
) -> None:
    with database.session() as session:
        existing = session.scalar(
            select(EvaluationCandidate).where(
                EvaluationCandidate.source_feedback_event_id == feedback_event_id
            )
        )
        if existing is not None:
            return
        handoff = session.get(HumanHandoffCase, handoff_case_id)
        event = session.get(AgentFeedbackEvent, feedback_event_id)
        if handoff is None or event is None or event.event_type != "resolved":
            return
        if handoff.resolution_type not in {"corrected_answer", "policy_update", "memory_update"}:
            return
        run = session.get(AgentRun, handoff.agent_run_id)
        if run is None:
            return
        profile = session.get(RoleTwinProfile, run.twin_profile_id)
        account = session.scalar(
            select(UserAccount).where(
                UserAccount.enterprise_id == handoff.enterprise_id,
                UserAccount.principal_id == handoff.opened_by_principal_id,
                UserAccount.status == "active",
            )
        )
        if profile is None or account is None or not handoff.resolution_summary:
            return
        case_hash = sha256(handoff.id.encode()).hexdigest()[:12]
        domain = "authorization" if handoff.category == "scope_issue" else "role-twin"
        risk_level = (
            "critical"
            if handoff.priority == "urgent" or handoff.category == "unsafe"
            else "high"
            if handoff.priority == "high"
            else "medium"
        )
        session.add(
            EvaluationCandidate(
                id=f"evaluation_candidate_{uuid4().hex}",
                enterprise_id=handoff.enterprise_id,
                source_handoff_case_id=handoff.id,
                source_feedback_event_id=event.id,
                source_agent_run_id=run.id,
                proposed_case_key=f"feedback-{case_hash}",
                proposed_title=f"反馈回归：{run.question[:180]}",
                domain=domain,
                risk_level=risk_level,
                actor_login_name=account.local_login_name,
                target_twin_key=profile.twin_key,
                input_payload={"question": run.question, "top_k": 5, "scope_key": None},
                expectations={
                    "minimum_evidence": 1,
                    "minimum_metric_context": 0,
                    "minimum_memory_context": 0,
                    "required_document_keys": [],
                    "required_terms": [],
                    "forbidden_terms": [],
                    "require_caveat": handoff.category in {"unsafe", "scope_issue"},
                    "expected_error_code": None,
                    "manual_review_required": True,
                    "reference_answer": handoff.resolution_summary,
                },
                resolution_summary=handoff.resolution_summary,
                status="pending",
                proposed_by_principal_id=actor.principal_id,
                reviewed_by_principal_id=None,
                accepted_case_id=None,
                review_reason=None,
                review_idempotency_key=None,
                created_at=datetime.now(UTC),
                reviewed_at=None,
            )
        )
        session.commit()


def review_evaluation_candidate(
    database: Database,
    actor: ActorContext,
    *,
    candidate_id: str,
    payload: EvaluationCandidateActionRequest,
) -> EvaluationCandidateMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        request_owner = session.scalar(
            select(EvaluationCandidate).where(
                EvaluationCandidate.enterprise_id == actor.enterprise_id,
                EvaluationCandidate.review_idempotency_key == payload.client_request_key,
            )
        )
        if request_owner is not None and request_owner.id != candidate_id:
            raise ApiProblem(
                status_code=409,
                code="evaluation.idempotency_conflict",
                message="该审核请求键已用于其他评测候选",
            )
        candidate = session.get(EvaluationCandidate, candidate_id)
        if candidate is None or candidate.enterprise_id != actor.enterprise_id:
            raise ApiProblem(
                status_code=404,
                code="evaluation.candidate_not_found",
                message="评测候选不存在",
            )
        if candidate.status != "pending":
            expected_status = "accepted" if payload.action == "accept" else "rejected"
            if (
                candidate.review_idempotency_key == payload.client_request_key
                and candidate.status == expected_status
            ):
                duplicate = True
            else:
                raise ApiProblem(
                    status_code=409,
                    code="evaluation.candidate_already_reviewed",
                    message="评测候选已经形成不可变审核结论",
                )
        else:
            duplicate = False
            accepted_case_id: str | None = None
            if payload.action == "accept":
                suite = session.scalar(
                    select(EvaluationSuite)
                    .where(
                        EvaluationSuite.enterprise_id == actor.enterprise_id,
                        EvaluationSuite.suite_key == payload.suite_key,
                        EvaluationSuite.status == "active",
                    )
                    .order_by(EvaluationSuite.version_number.desc())
                )
                if suite is None:
                    raise ApiProblem(
                        status_code=404,
                        code="evaluation.suite_not_found",
                        message="目标评测套件不存在或尚未启用",
                    )
                prior_cases = list(
                    session.scalars(
                        select(EvaluationCase).where(
                            EvaluationCase.suite_id == suite.id,
                            EvaluationCase.case_key == candidate.proposed_case_key,
                        )
                    )
                )
                version_number = max((item.version_number for item in prior_cases), default=0) + 1
                for prior in prior_cases:
                    if prior.status == "active":
                        prior.status = "retired"
                accepted_case = EvaluationCase(
                    id=f"evaluation_case_{uuid4().hex}",
                    suite_id=suite.id,
                    case_key=candidate.proposed_case_key,
                    version_number=version_number,
                    domain=candidate.domain,
                    risk_level=candidate.risk_level,
                    title=candidate.proposed_title,
                    actor_login_name=candidate.actor_login_name,
                    target_twin_key=candidate.target_twin_key,
                    input_payload=candidate.input_payload,
                    expectations=candidate.expectations,
                    status="active",
                    created_at=now,
                )
                session.add(accepted_case)
                session.flush()
                accepted_case_id = accepted_case.id
            candidate.status = "accepted" if payload.action == "accept" else "rejected"
            candidate.reviewed_by_principal_id = actor.principal_id
            candidate.accepted_case_id = accepted_case_id
            candidate.review_reason = payload.reason
            candidate.review_idempotency_key = payload.client_request_key
            candidate.reviewed_at = now
            session.commit()
    studio = list_evaluation_studio(database, actor)
    candidate_view = next(item for item in studio.candidates if item.id == candidate_id)
    return EvaluationCandidateMutationResponse(
        idempotent=duplicate,
        candidate=candidate_view,
        studio=studio,
    )


async def run_evaluation_suite(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    runtime: AgentRuntime,
    initiator: ActorContext,
    *,
    suite_key: str,
    client_request_key: str,
    case_keys: list[str],
) -> EvaluationRunMutationResponse:
    with database.session() as session:
        existing = session.scalar(
            select(EvaluationRun).where(
                EvaluationRun.enterprise_id == initiator.enterprise_id,
                EvaluationRun.client_request_key == client_request_key,
            )
        )
        existing_suite_key = (
            session.scalar(
                select(EvaluationSuite.suite_key).where(
                    EvaluationSuite.id == existing.suite_id
                )
            )
            if existing is not None
            else None
        )
    if existing is not None:
        if existing_suite_key != suite_key:
            raise ApiProblem(
                status_code=409,
                code="evaluation.idempotency_conflict",
                message="该请求键已用于其他评测套件",
                details={"client_request_key": client_request_key},
            )
        studio = list_evaluation_studio(database, initiator)
        run = next(
            run
            for suite in studio.suites
            for run in suite.recent_runs
            if run.id == existing.id
        )
        return EvaluationRunMutationResponse(idempotent=True, run=run, studio=studio)

    with database.session() as session:
        suite = session.scalar(
            select(EvaluationSuite)
            .where(
                EvaluationSuite.enterprise_id == initiator.enterprise_id,
                EvaluationSuite.suite_key == suite_key,
                EvaluationSuite.status == "active",
            )
            .order_by(EvaluationSuite.version_number.desc())
        )
        if suite is None:
            raise ApiProblem(
                status_code=404,
                code="evaluation.suite_not_found",
                message="评测套件不存在或尚未启用",
                details={"suite_key": suite_key},
            )
        query = select(EvaluationCase).where(
            EvaluationCase.suite_id == suite.id,
            EvaluationCase.status == "active",
        )
        if case_keys:
            query = query.where(EvaluationCase.case_key.in_(case_keys))
        cases = list(session.scalars(query.order_by(EvaluationCase.case_key)))
        if case_keys and len(cases) != len(set(case_keys)):
            raise ApiProblem(
                status_code=422,
                code="evaluation.case_selection_invalid",
                message="部分评测用例不存在或尚未启用",
            )
        if not cases:
            raise ApiProblem(
                status_code=409,
                code="evaluation.suite_empty",
                message="评测套件没有可运行的启用案例",
            )
        baseline = session.scalar(
            select(EvaluationRun)
            .where(
                EvaluationRun.suite_id == suite.id,
                EvaluationRun.status == "completed",
            )
            .order_by(EvaluationRun.completed_at.desc())
        )
        run_id = f"evaluation_run_{uuid4().hex}"
        started_at = datetime.now(UTC)
        run_row = EvaluationRun(
            id=run_id,
            enterprise_id=initiator.enterprise_id,
            suite_id=suite.id,
            initiated_by_principal_id=initiator.principal_id,
            baseline_run_id=baseline.id if baseline else None,
            client_request_key=client_request_key,
            status="running",
            provider="openai-compatible-responses" if settings.ai_enabled else "local-evidence",
            model=settings.ai_model if settings.ai_enabled else "deterministic-v1",
            code_version="evaluation-runner-v1",
            config_version=f"suite-v{suite.version_number}",
            total_count=len(cases),
            passed_count=0,
            failed_count=0,
            review_required_count=0,
            error_count=0,
            pass_rate=0,
            duration_ms=0,
            started_at=started_at,
            completed_at=None,
        )
        session.add(run_row)
        session.commit()

    outcomes: list[str] = []
    for index, case in enumerate(cases, start=1):
        item = await _execute_case(
            database,
            settings,
            provider,
            runtime,
            case,
            evaluation_run_id=run_id,
            ordinal=index,
        )
        outcomes.append(item.outcome)
        with database.session() as session:
            session.add(item)
            session.commit()

    completed_at = datetime.now(UTC)
    with database.session() as session:
        completed_run = session.get(EvaluationRun, run_id)
        if completed_run is None:
            raise RuntimeError("evaluation run disappeared")
        completed_run.status = "completed"
        completed_run.passed_count = outcomes.count("passed")
        completed_run.failed_count = outcomes.count("failed")
        completed_run.review_required_count = outcomes.count("review_required")
        completed_run.error_count = outcomes.count("error")
        completed_run.pass_rate = (
            round(completed_run.passed_count / len(outcomes), 4) if outcomes else 0
        )
        completed_run.duration_ms = max(
            1, round((completed_at - started_at).total_seconds() * 1000)
        )
        completed_run.completed_at = completed_at
        session.commit()
    studio = list_evaluation_studio(database, initiator)
    run = next(run for suite in studio.suites for run in suite.recent_runs if run.id == run_id)
    return EvaluationRunMutationResponse(idempotent=False, run=run, studio=studio)


async def _execute_case(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    runtime: AgentRuntime,
    case: EvaluationCase,
    *,
    evaluation_run_id: str,
    ordinal: int,
) -> EvaluationRunItem:
    started = perf_counter()
    created_at = datetime.now(UTC)
    actor_snapshot: dict[str, object] = {"login_name": case.actor_login_name}
    actor_principal_id: str | None = None
    agent_run_id: str | None = None
    checks: list[dict[str, object]] = []
    error_types: list[str] = []
    observed_error_code: str | None = None
    outcome = "error"
    expected_error = _optional_string(case.expectations.get("expected_error_code"))
    try:
        actor = resolve_database_actor(
            database,
            login_name=case.actor_login_name,
            request_id=f"req_eval_{evaluation_run_id}_{ordinal:02d}",
            run_id=f"run_eval_{evaluation_run_id}_{ordinal:02d}",
        )
        actor_snapshot = actor.snapshot()
        actor_principal_id = actor.principal_id
        require_permission(
            actor,
            "role-twin.invoke",
            database,
            resource_type="role-twin",
            resource_key=case.target_twin_key,
        )
        require_permission(
            actor,
            "knowledge.document.read",
            database,
            resource_type="knowledge.document",
            resource_key="evaluation-context",
        )
        answer = await answer_with_twin(
            database,
            settings,
            provider,
            runtime,
            actor=actor,
            twin_key=case.target_twin_key,
            question=str(case.input_payload["question"]),
            top_k=_integer(case.input_payload["top_k"]),
            scope_key=_optional_string(case.input_payload.get("scope_key")),
        )
        agent_run_id = answer.run_id
        if expected_error:
            checks.append(_check("expected-error", "预期拒绝", False, expected_error, "未拒绝"))
        checks.extend(_answer_checks(database, case, answer))
        passed = all(bool(item["passed"]) for item in checks)
        manual = bool(case.expectations.get("manual_review_required"))
        outcome = "review_required" if passed and manual else "passed" if passed else "failed"
    except ApiProblem as problem:
        observed_error_code = problem.code
        matched = bool(expected_error and problem.code == expected_error)
        checks.append(
            _check(
                "expected-error",
                "预期拒绝",
                matched,
                expected_error or "无错误",
                problem.code,
            )
        )
        if matched:
            outcome = "passed"
        else:
            outcome = "failed"
            error_types.append(problem.code)
    except Exception as exc:
        observed_error_code = "evaluation.case_execution_failed"
        error_types.append(type(exc).__name__)
        outcome = "error"
    snapshot = {
        "schema_version": 1,
        "case_key": case.case_key,
        "version_number": case.version_number,
        "domain": case.domain,
        "risk_level": case.risk_level,
        "actor_login_name": case.actor_login_name,
        "target_twin_key": case.target_twin_key,
        "input": case.input_payload,
        "expectations": case.expectations,
    }
    return EvaluationRunItem(
        id=f"evaluation_run_item_{uuid4().hex}",
        evaluation_run_id=evaluation_run_id,
        evaluation_case_id=case.id,
        actor_principal_id=actor_principal_id,
        agent_run_id=agent_run_id,
        case_key=case.case_key,
        case_version_number=case.version_number,
        case_snapshot=snapshot,
        actor_snapshot=actor_snapshot,
        outcome=outcome,
        checks=checks,
        error_types=error_types,
        observed_error_code=observed_error_code,
        duration_ms=max(1, round((perf_counter() - started) * 1000)),
        created_at=created_at,
    )


def _answer_checks(
    database: Database,
    case: EvaluationCase,
    answer: TwinAnswerResponse,
) -> list[dict[str, object]]:
    run_id = answer.run_id
    evidence_count = len(answer.evidence)
    metric_count = len(answer.metric_context)
    memory_count = len(answer.memory_context)
    answer_payload = answer.answer
    answer_text = json.dumps(answer_payload.model_dump(mode="json"), ensure_ascii=False)
    with database.session() as session:
        document_keys = set(
            session.scalars(
                select(KnowledgeDocument.document_key)
                .join(KnowledgeVersion, KnowledgeVersion.document_id == KnowledgeDocument.id)
                .join(KnowledgeChunk, KnowledgeChunk.version_id == KnowledgeVersion.id)
                .join(AgentRunEvidence, AgentRunEvidence.chunk_id == KnowledgeChunk.id)
                .where(AgentRunEvidence.run_id == run_id)
            )
        )
        context_types = list(
            session.scalars(
                select(AgentRunContextItem.item_type).where(AgentRunContextItem.run_id == run_id)
            )
        )
        run = session.get(AgentRun, run_id)
    expectations = case.expectations
    checks = [
        _minimum_check(
            "evidence-count", "知识证据", evidence_count, expectations, "minimum_evidence"
        ),
        _minimum_check(
            "metric-count",
            "经营数据上下文",
            metric_count,
            expectations,
            "minimum_metric_context",
        ),
        _minimum_check(
            "memory-count",
            "角色记忆上下文",
            memory_count,
            expectations,
            "minimum_memory_context",
        ),
    ]
    required_docs = set(_string_list(expectations.get("required_document_keys")))
    checks.append(
        _check(
            "required-documents",
            "必需正式资料",
            required_docs.issubset(document_keys),
            "、".join(sorted(required_docs)) or "不限定",
            "、".join(sorted(document_keys)) or "无",
        )
    )
    required_terms = _string_list(expectations.get("required_terms"))
    checks.append(
        _check(
            "required-terms",
            "必需表述",
            all(item in answer_text for item in required_terms),
            "、".join(required_terms) or "不限定",
            "全部出现" if all(item in answer_text for item in required_terms) else "存在缺失",
        )
    )
    forbidden_terms = _string_list(expectations.get("forbidden_terms"))
    forbidden_detected = any(item in answer_text for item in forbidden_terms)
    checks.append(
        _check(
            "forbidden-terms",
            "禁止表述",
            not forbidden_detected,
            "不得出现：" + ("、".join(forbidden_terms) or "无"),
            "检测到禁止表述" if forbidden_detected else "未出现",
        )
    )
    caveats = list(answer_payload.caveats)
    require_caveat = bool(expectations.get("require_caveat"))
    checks.append(
        _check(
            "caveat",
            "边界与限制",
            bool(caveats) if require_caveat else True,
            "至少一条限制说明" if require_caveat else "不强制",
            f"{len(caveats)} 条",
        )
    )
    checks.append(
        _check(
            "run-persisted",
            "运行可追溯",
            run is not None and run.actor_principal_id is not None,
            "绑定身份和 AgentRun",
            f"{run_id} · {','.join(sorted(set(context_types))) or 'evidence-only'}",
        )
    )
    return checks


def _minimum_check(
    key: str,
    label: str,
    actual: int,
    expectations: dict[str, object],
    expectation_key: str,
) -> dict[str, object]:
    minimum = _integer(expectations.get(expectation_key, 0))
    return _check(key, label, actual >= minimum, f">= {minimum}", str(actual))


def _check(key: str, label: str, passed: bool, expected: str, actual: str) -> dict[str, object]:
    return {"key": key, "label": label, "passed": passed, "expected": expected, "actual": actual}


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None and str(value) else None


def _integer(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        return int(value)
    raise TypeError("evaluation value is not an integer")


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _case_view(item: EvaluationCase) -> EvaluationCaseView:
    return EvaluationCaseView(
        key=item.case_key,
        version_number=item.version_number,
        domain=item.domain,
        risk_level=item.risk_level,
        title=item.title,
        actor_login_name=item.actor_login_name,
        target_twin_key=item.target_twin_key,
        input=item.input_payload,
        expectations=item.expectations,
        status=item.status,
    )


def _candidate_view(
    item: EvaluationCandidate,
    principal_by_id: dict[str, Principal],
) -> EvaluationCandidateView:
    proposer = principal_by_id.get(item.proposed_by_principal_id)
    reviewer = principal_by_id.get(item.reviewed_by_principal_id or "")
    return EvaluationCandidateView(
        id=item.id,
        source_handoff_case_id=item.source_handoff_case_id,
        source_feedback_event_id=item.source_feedback_event_id,
        source_agent_run_id=item.source_agent_run_id,
        proposed_case_key=item.proposed_case_key,
        proposed_title=item.proposed_title,
        domain=item.domain,
        risk_level=item.risk_level,
        actor_login_name=item.actor_login_name,
        target_twin_key=item.target_twin_key,
        input=item.input_payload,
        expectations=item.expectations,
        resolution_summary=item.resolution_summary,
        status=item.status,  # type: ignore[arg-type]
        proposed_by_name=proposer.display_name if proposer else "未知提议人",
        reviewed_by_name=reviewer.display_name if reviewer else None,
        accepted_case_id=item.accepted_case_id,
        review_reason=item.review_reason,
        created_at=item.created_at,
        reviewed_at=item.reviewed_at,
    )


def _run_view(
    run: EvaluationRun,
    suite: EvaluationSuite,
    items: list[EvaluationRunItem],
    case_by_id: dict[str, EvaluationCase],
    principal_by_id: dict[str, Principal],
    run_by_id: dict[str, EvaluationRun],
) -> EvaluationRunView:
    baseline = run_by_id.get(run.baseline_run_id or "")
    initiator = principal_by_id.get(run.initiated_by_principal_id)
    item_views: list[EvaluationRunItemView] = []
    for item in items:
        case = case_by_id[item.evaluation_case_id]
        principal = principal_by_id.get(item.actor_principal_id or "")
        item_views.append(
            EvaluationRunItemView(
                id=item.id,
                case_key=item.case_key,
                case_version_number=item.case_version_number,
                case_title=case.title,
                domain=case.domain,
                risk_level=case.risk_level,
                actor_name=principal.display_name if principal else case.actor_login_name,
                actor_principal_id=item.actor_principal_id,
                agent_run_id=item.agent_run_id,
                case_snapshot=item.case_snapshot,
                actor_snapshot=item.actor_snapshot,
                outcome=item.outcome,  # type: ignore[arg-type]
                checks=[EvaluationCheckView.model_validate(check) for check in item.checks],
                error_types=item.error_types,
                observed_error_code=item.observed_error_code,
                duration_ms=item.duration_ms,
                created_at=item.created_at,
            )
        )
    return EvaluationRunView(
        id=run.id,
        suite_key=suite.suite_key,
        suite_version_number=suite.version_number,
        status=run.status,  # type: ignore[arg-type]
        provider=run.provider,
        model=run.model,
        code_version=run.code_version,
        config_version=run.config_version,
        baseline_run_id=run.baseline_run_id,
        pass_rate_delta=round(run.pass_rate - baseline.pass_rate, 4) if baseline else None,
        total_count=run.total_count,
        passed_count=run.passed_count,
        failed_count=run.failed_count,
        review_required_count=run.review_required_count,
        error_count=run.error_count,
        pass_rate=run.pass_rate,
        duration_ms=run.duration_ms,
        initiated_by_name=initiator.display_name if initiator else "未知发起人",
        started_at=run.started_at,
        completed_at=run.completed_at,
        items=item_views,
    )
