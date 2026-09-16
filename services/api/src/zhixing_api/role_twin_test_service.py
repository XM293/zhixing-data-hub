from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from zhixing_agent_runtime import AgentRuntime

from zhixing_api.actor_context import ActorContext
from zhixing_api.ai_provider import ResponsesAIProvider
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    AgentRunContextItem,
    AgentRunEvidence,
    Principal,
    RoleTwinProfile,
    RoleTwinTestCase,
    RoleTwinTestReview,
    RoleTwinTestRun,
    RoleTwinVersion,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.knowledge_schemas import TwinAnswerPayload
from zhixing_api.knowledge_service import answer_with_twin
from zhixing_api.role_twin_service import current_twin_version
from zhixing_api.role_twin_test_schemas import (
    RoleTwinTestCaseView,
    RoleTwinTestContextRef,
    RoleTwinTestMutationResponse,
    RoleTwinTestReviewRequest,
    RoleTwinTestReviewView,
    RoleTwinTestRunView,
    RoleTwinTestStats,
    RoleTwinTestStudioResponse,
    RoleTwinTestTwinOption,
)


def list_role_twin_test_studio(
    database: Database,
    actor: ActorContext,
) -> RoleTwinTestStudioResponse:
    with database.session() as session:
        cases = list(
            session.scalars(
                select(RoleTwinTestCase)
                .where(RoleTwinTestCase.enterprise_id == actor.enterprise_id)
                .order_by(RoleTwinTestCase.case_key)
            )
        )
        profiles = list(
            session.scalars(
                select(RoleTwinProfile)
                .where(
                    RoleTwinProfile.enterprise_id == actor.enterprise_id,
                    RoleTwinProfile.status == "published",
                )
                .order_by(RoleTwinProfile.twin_key)
            )
        )
        profile_ids = [item.id for item in profiles]
        versions = list(
            session.scalars(
                select(RoleTwinVersion).where(RoleTwinVersion.twin_profile_id.in_(profile_ids))
            )
        ) if profile_ids else []
        test_runs = list(
            session.scalars(
                select(RoleTwinTestRun)
                .where(RoleTwinTestRun.enterprise_id == actor.enterprise_id)
                .order_by(RoleTwinTestRun.created_at.desc())
            )
        )
        test_run_ids = [item.id for item in test_runs]
        agent_run_ids = [item.agent_run_id for item in test_runs]
        agent_runs = list(
            session.scalars(select(AgentRun).where(AgentRun.id.in_(agent_run_ids)))
        ) if agent_run_ids else []
        reviews = list(
            session.scalars(
                select(RoleTwinTestReview)
                .where(RoleTwinTestReview.test_run_id.in_(test_run_ids))
                .order_by(RoleTwinTestReview.created_at.desc())
            )
        ) if test_run_ids else []
        evidence = list(
            session.scalars(
                select(AgentRunEvidence)
                .where(AgentRunEvidence.run_id.in_(agent_run_ids))
                .order_by(AgentRunEvidence.rank)
            )
        ) if agent_run_ids else []
        contexts = list(
            session.scalars(
                select(AgentRunContextItem)
                .where(AgentRunContextItem.run_id.in_(agent_run_ids))
                .order_by(AgentRunContextItem.item_type, AgentRunContextItem.rank)
            )
        ) if agent_run_ids else []
        principal_ids = {
            *(item.actor_principal_id for item in test_runs),
            *(item.reviewer_principal_id for item in reviews),
        }
        principals = list(
            session.scalars(select(Principal).where(Principal.id.in_(principal_ids)))
        ) if principal_ids else []

    risk_priority = {"high": 0, "medium": 1, "low": 2}
    cases.sort(key=lambda item: (risk_priority.get(item.risk_level, 3), item.case_key))
    profile_by_id = {item.id: item for item in profiles}
    case_by_id = {item.id: item for item in cases}
    version_by_id = {item.id: item for item in versions}
    published_versions = {
        item.twin_profile_id: item
        for item in sorted(versions, key=lambda version: version.version_number)
        if item.status == "published"
    }
    agent_by_id = {item.id: item for item in agent_runs}
    principal_by_id = {item.id: item for item in principals}
    runs_by_case: dict[str, list[RoleTwinTestRun]] = defaultdict(list)
    reviews_by_run: dict[str, list[RoleTwinTestReview]] = defaultdict(list)
    evidence_by_run: dict[str, list[AgentRunEvidence]] = defaultdict(list)
    contexts_by_run: dict[str, list[AgentRunContextItem]] = defaultdict(list)
    for test_run in test_runs:
        runs_by_case[test_run.case_id].append(test_run)
    for review in reviews:
        reviews_by_run[review.test_run_id].append(review)
    for evidence_item in evidence:
        evidence_by_run[evidence_item.run_id].append(evidence_item)
    for context_item in contexts:
        contexts_by_run[context_item.run_id].append(context_item)

    run_views = {
        item.id: _run_view(
            item,
            case_by_id[item.case_id],
            profile_by_id,
            version_by_id,
            agent_by_id,
            principal_by_id,
            reviews_by_run[item.id],
            evidence_by_run[item.agent_run_id],
            contexts_by_run[item.agent_run_id],
        )
        for item in test_runs
        if item.agent_run_id in agent_by_id
    }
    reviewed = [item for item in run_views.values() if item.latest_review is not None]
    passed = [
        item
        for item in reviewed
        if item.latest_review and item.latest_review.decision == "pass"
    ]
    case_views = [
        RoleTwinTestCaseView(
            id=item.id,
            key=item.case_key,
            version_number=item.version_number,
            status=item.status,
            title=item.title,
            category=item.category,  # type: ignore[arg-type]
            risk_level=item.risk_level,  # type: ignore[arg-type]
            question=item.question,
            expected_behaviors=item.expected_behaviors,
            expected_evidence_refs=item.expected_evidence_refs,
            target_twin_key=profile_by_id[item.target_twin_profile_id].twin_key,
            target_twin_name=profile_by_id[item.target_twin_profile_id].display_name,
            created_at=item.created_at,
            runs=[run_views[run.id] for run in runs_by_case[item.id][:5] if run.id in run_views],
        )
        for item in cases
        if item.target_twin_profile_id in profile_by_id
    ]
    return RoleTwinTestStudioResponse(
        stats=RoleTwinTestStats(
            case_count=len(case_views),
            run_count=len(run_views),
            pending_review_count=len(run_views) - len(reviewed),
            reviewed_count=len(reviewed),
            passed_count=len(passed),
            pass_rate=round(len(passed) / len(reviewed), 4) if reviewed else None,
        ),
        twins=[
            RoleTwinTestTwinOption(
                key=profile.twin_key,
                display_name=profile.display_name,
                role_title=profile.role_title,
                current_version_number=published_versions[profile.id].version_number,
                status=profile.status,
            )
            for profile in profiles
            if profile.id in published_versions
        ],
        cases=case_views,
        generated_at=datetime.now(UTC),
    )


async def run_role_twin_test(
    database: Database,
    settings: Settings,
    provider: ResponsesAIProvider,
    runtime: AgentRuntime,
    actor: ActorContext,
    *,
    case_key: str,
    twin_key: str,
) -> RoleTwinTestMutationResponse:
    with database.session() as session:
        test_case = session.scalar(
            select(RoleTwinTestCase).where(
                RoleTwinTestCase.enterprise_id == actor.enterprise_id,
                RoleTwinTestCase.case_key == case_key,
                RoleTwinTestCase.status == "active",
            ).order_by(RoleTwinTestCase.version_number.desc())
        )
        profile = session.scalar(
            select(RoleTwinProfile).where(
                RoleTwinProfile.enterprise_id == actor.enterprise_id,
                RoleTwinProfile.twin_key == twin_key,
                RoleTwinProfile.status == "published",
            )
        )
        if test_case is None:
            raise _not_found("角色试跑用例不存在或已退役", case_key)
        if profile is None:
            raise _not_found("可调用的角色分身不存在", twin_key)
        role_version = current_twin_version(session, profile.id)
        if role_version is None:
            raise _conflict("角色分身尚无已发布版本", twin_key)
        test_case_id = test_case.id
        question = test_case.question
        profile_id = profile.id
        role_version_id = role_version.id

    answer = await answer_with_twin(
        database,
        settings,
        provider,
        runtime,
        actor=actor,
        twin_key=twin_key,
        question=question,
        top_k=5,
    )
    with database.session() as session:
        agent_run = session.get(AgentRun, answer.run_id)
        if agent_run is None or agent_run.role_twin_version_id != role_version_id:
            raise _conflict("试跑运行未绑定预期分身版本", answer.run_id)
        item = RoleTwinTestRun(
            id=f"role_twin_test_run_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            case_id=test_case_id,
            twin_profile_id=profile_id,
            role_twin_version_id=role_version_id,
            agent_run_id=answer.run_id,
            actor_principal_id=actor.principal_id,
            status=agent_run.status,
            execution_mode=answer.execution_mode,
            provider=answer.provider,
            model=answer.model,
            duration_ms=answer.duration_ms,
            created_at=answer.created_at,
        )
        session.add(item)
        session.commit()
        run_id = item.id
    return _mutation(database, actor, run_id)


def review_role_twin_test_run(
    database: Database,
    actor: ActorContext,
    *,
    test_run_id: str,
    payload: RoleTwinTestReviewRequest,
) -> RoleTwinTestMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        test_run = session.scalar(
            select(RoleTwinTestRun).where(
                RoleTwinTestRun.id == test_run_id,
                RoleTwinTestRun.enterprise_id == actor.enterprise_id,
            )
        )
        if test_run is None:
            raise _not_found("角色试跑运行不存在", test_run_id)
        session.add(
            RoleTwinTestReview(
                id=f"role_twin_test_review_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                test_run_id=test_run.id,
                reviewer_principal_id=actor.principal_id,
                decision=payload.decision,
                evidence_grounding=payload.evidence_grounding,
                boundary_adherence=payload.boundary_adherence,
                voice_match=payload.voice_match,
                usefulness=payload.usefulness,
                notes=payload.notes.strip(),
                actor_snapshot=actor.snapshot(),
                request_id=actor.request_id,
                run_id=actor.run_id,
                created_at=now,
            )
        )
        session.commit()
    return _mutation(database, actor, test_run_id)


def _mutation(
    database: Database,
    actor: ActorContext,
    test_run_id: str,
) -> RoleTwinTestMutationResponse:
    studio = list_role_twin_test_studio(database, actor)
    run = next(
        (
            run
            for case in studio.cases
            for run in case.runs
            if run.id == test_run_id
        ),
        None,
    )
    if run is None:
        raise _not_found("角色试跑运行不在当前读模型窗口", test_run_id)
    return RoleTwinTestMutationResponse(run=run, studio=studio)


def _run_view(
    test_run: RoleTwinTestRun,
    test_case: RoleTwinTestCase,
    profiles: dict[str, RoleTwinProfile],
    versions: dict[str, RoleTwinVersion],
    agent_runs: dict[str, AgentRun],
    principals: dict[str, Principal],
    reviews: list[RoleTwinTestReview],
    evidence: list[AgentRunEvidence],
    contexts: list[AgentRunContextItem],
) -> RoleTwinTestRunView:
    profile = profiles[test_run.twin_profile_id]
    version = versions[test_run.role_twin_version_id]
    agent = agent_runs[test_run.agent_run_id]
    review_views = [
        RoleTwinTestReviewView(
            id=item.id,
            decision=item.decision,  # type: ignore[arg-type]
            evidence_grounding=item.evidence_grounding,
            boundary_adherence=item.boundary_adherence,
            voice_match=item.voice_match,
            usefulness=item.usefulness,
            average_score=round(
                (
                    item.evidence_grounding
                    + item.boundary_adherence
                    + item.voice_match
                    + item.usefulness
                )
                / 4,
                2,
            ),
            notes=item.notes,
            reviewer_name=principals[item.reviewer_principal_id].display_name,
            request_id=item.request_id,
            run_id=item.run_id,
            created_at=item.created_at,
        )
        for item in reviews
    ]
    evidence_refs = [
        RoleTwinTestContextRef(
            kind="evidence",
            label=item.citation_label,
            version_ref=None,
            excerpt=item.excerpt,
            rank=item.rank,
        )
        for item in evidence
    ]
    context_refs = [
        RoleTwinTestContextRef(
            kind="data" if item.item_type == "metric-series" else "memory",
            label=item.citation_label,
            version_ref=item.version_ref,
            excerpt=item.excerpt,
            rank=item.rank,
        )
        for item in contexts
    ]
    return RoleTwinTestRunView(
        id=test_run.id,
        case_key=test_case.case_key,
        case_version_number=test_case.version_number,
        twin_key=profile.twin_key,
        twin_name=version.display_name,
        role_twin_version_number=version.version_number,
        agent_run_id=agent.id,
        question=agent.question,
        answer=TwinAnswerPayload.model_validate(agent.answer_payload),
        evidence_count=len(evidence),
        metric_context_count=sum(item.item_type == "metric-series" for item in contexts),
        memory_context_count=sum(item.item_type == "approved-memory" for item in contexts),
        context_refs=sorted(
            [*evidence_refs, *context_refs],
            key=lambda item: ({"data": 0, "evidence": 1, "memory": 2}[item.kind], item.rank),
        ),
        execution_mode=test_run.execution_mode,  # type: ignore[arg-type]
        provider=test_run.provider,
        model=test_run.model,
        duration_ms=test_run.duration_ms,
        status=test_run.status,
        actor_name=principals[test_run.actor_principal_id].display_name,
        created_at=test_run.created_at,
        reviews=review_views,
        latest_review=review_views[0] if review_views else None,
    )
def _not_found(message: str, key: str) -> ApiProblem:
    return ApiProblem(
        status_code=404,
        code="role.test_not_found",
        message=message,
        details={"key": key},
    )


def _conflict(message: str, value: str) -> ApiProblem:
    return ApiProblem(
        status_code=409,
        code="role.test_conflict",
        message=message,
        details={"value": value},
    )
