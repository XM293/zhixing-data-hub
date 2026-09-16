from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext
from zhixing_api.data_models import (
    AgentSkill,
    AgentSkillEvent,
    AgentSkillVersion,
    Principal,
    ToolDefinition,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.skill_schemas import (
    SkillConfigurationEventView,
    SkillCreateRequest,
    SkillPublishRequest,
    SkillStudioMutationResponse,
    SkillStudioResponse,
    SkillStudioStats,
    SkillVersionCreateRequest,
    SkillVersionView,
    SkillView,
)


def list_skill_studio(database: Database, actor: ActorContext) -> SkillStudioResponse:
    with database.session() as session:
        skills = list(
            session.scalars(
                select(AgentSkill)
                .where(AgentSkill.enterprise_id == actor.enterprise_id)
                .order_by(AgentSkill.name, AgentSkill.skill_key)
            )
        )
        skill_ids = [item.id for item in skills]
        versions = (
            list(
                session.scalars(
                    select(AgentSkillVersion)
                    .where(AgentSkillVersion.skill_id.in_(skill_ids))
                    .order_by(
                        AgentSkillVersion.skill_id,
                        AgentSkillVersion.version_number.desc(),
                    )
                )
            )
            if skill_ids
            else []
        )
        principals = {
            item.id: item.display_name
            for item in session.scalars(
                select(Principal).where(Principal.enterprise_id == actor.enterprise_id)
            )
        }
        available_tools = list(
            session.scalars(
                select(ToolDefinition.tool_key)
                .where(
                    ToolDefinition.enterprise_id == actor.enterprise_id,
                    ToolDefinition.status == "active",
                )
                .distinct()
                .order_by(ToolDefinition.tool_key)
            )
        )

    versions_by_skill: dict[str, list[AgentSkillVersion]] = {}
    for version in versions:
        versions_by_skill.setdefault(version.skill_id, []).append(version)
    views = [
        _skill_view(item, versions_by_skill.get(item.id, []), principals)
        for item in skills
    ]
    return SkillStudioResponse(
        stats=SkillStudioStats(
            skill_count=len(skills),
            published_skill_count=sum(item.status == "published" for item in skills),
            draft_version_count=sum(item.status == "draft" for item in versions),
            published_version_count=sum(item.status == "published" for item in versions),
            registered_tool_count=len(available_tools),
        ),
        skills=views,
        available_tools=available_tools,
        generated_at=datetime.now(UTC),
    )


def create_skill(
    database: Database,
    actor: ActorContext,
    payload: SkillCreateRequest,
) -> SkillStudioMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        existing = session.scalar(
            select(AgentSkill).where(
                AgentSkill.enterprise_id == actor.enterprise_id,
                AgentSkill.skill_key == payload.skill_key,
            )
        )
        if existing is not None:
            raise _conflict("Skill 键已存在", payload.skill_key)
        _validate_tools(session, actor.enterprise_id, payload.tool_keys)
        skill = AgentSkill(
            id=f"agent_skill_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            skill_key=payload.skill_key,
            name=payload.name,
            description=payload.description,
            status="draft",
            current_version_number=None,
            created_by_principal_id=actor.principal_id,
            created_at=now,
            updated_at=now,
        )
        version = _new_version(skill, actor, payload, version_number=1, now=now)
        session.add_all([skill, version])
        session.flush()
        event = _add_event(
            session,
            actor,
            skill=skill,
            version=version,
            event_type="created",
            reason=payload.change_summary,
            now=now,
        )
        session.commit()
    return _mutation(database, actor, event, idempotent=False)


def create_skill_version(
    database: Database,
    actor: ActorContext,
    *,
    skill_key: str,
    payload: SkillVersionCreateRequest,
) -> SkillStudioMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        skill = _require_skill(session, actor.enterprise_id, skill_key)
        _validate_tools(session, actor.enterprise_id, payload.tool_keys)
        version_number = int(
            session.scalar(
                select(func.max(AgentSkillVersion.version_number)).where(
                    AgentSkillVersion.skill_id == skill.id
                )
            )
            or 0
        ) + 1
        version = _new_version(skill, actor, payload, version_number=version_number, now=now)
        skill.updated_at = now
        session.add(version)
        session.flush()
        event = _add_event(
            session,
            actor,
            skill=skill,
            version=version,
            event_type="version-created",
            reason=payload.change_summary,
            now=now,
        )
        session.commit()
    return _mutation(database, actor, event, idempotent=False)


def publish_skill_version(
    database: Database,
    actor: ActorContext,
    *,
    skill_key: str,
    version_number: int,
    payload: SkillPublishRequest,
) -> SkillStudioMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        skill = _require_skill(session, actor.enterprise_id, skill_key)
        version = session.scalar(
            select(AgentSkillVersion).where(
                AgentSkillVersion.skill_id == skill.id,
                AgentSkillVersion.version_number == version_number,
            )
        )
        if version is None:
            raise _not_found("Skill 版本不存在", f"{skill_key}:v{version_number}")
        existing_event = session.scalar(
            select(AgentSkillEvent).where(
                AgentSkillEvent.enterprise_id == actor.enterprise_id,
                AgentSkillEvent.skill_id == skill.id,
                AgentSkillEvent.version_id == version.id,
                AgentSkillEvent.event_type == "published",
            )
        )
        if version.status == "published" and existing_event is not None:
            return _mutation(database, actor, existing_event, idempotent=True)
        if version.status != "draft":
            raise _conflict("只有草稿 Skill 版本可以发布", version.status)
        # Keep exactly one published version for a Skill. Older versions remain
        # immutable and are retained as retired history.
        published_versions = list(
            session.scalars(
                select(AgentSkillVersion).where(
                    AgentSkillVersion.skill_id == skill.id,
                    AgentSkillVersion.status == "published",
                )
            )
        )
        for previous in published_versions:
            previous.status = "retired"
        version.status = "published"
        version.published_at = now
        skill.status = "published"
        skill.current_version_number = version.version_number
        skill.updated_at = now
        event = _add_event(
            session,
            actor,
            skill=skill,
            version=version,
            event_type="published",
            reason=payload.reason,
            now=now,
        )
        session.commit()
    return _mutation(database, actor, event, idempotent=False)


def _new_version(
    skill: AgentSkill,
    actor: ActorContext,
    payload: SkillVersionCreateRequest | SkillCreateRequest,
    *,
    version_number: int,
    now: datetime,
) -> AgentSkillVersion:
    return AgentSkillVersion(
        id=f"agent_skill_version_{uuid4().hex}",
        enterprise_id=skill.enterprise_id,
        skill_id=skill.id,
        version_number=version_number,
        status="draft",
        instructions=payload.instructions,
        tool_keys=list(payload.tool_keys),
        input_schema=dict(payload.input_schema),
        output_schema=dict(payload.output_schema),
        change_summary=payload.change_summary,
        created_by_principal_id=actor.principal_id,
        created_at=now,
        published_at=None,
    )


def _add_event(
    session: object,
    actor: ActorContext,
    *,
    skill: AgentSkill,
    version: AgentSkillVersion,
    event_type: str,
    reason: str,
    now: datetime,
) -> AgentSkillEvent:
    event = AgentSkillEvent(
        id=f"agent_skill_event_{uuid4().hex}",
        enterprise_id=skill.enterprise_id,
        skill_id=skill.id,
        version_id=version.id,
        actor_principal_id=actor.principal_id,
        event_type=event_type,
        reason=reason,
        request_id=actor.request_id,
        run_id=actor.run_id,
        occurred_at=now,
    )
    session.add(event)  # type: ignore[attr-defined]
    return event


def _validate_tools(session: object, enterprise_id: str, tool_keys: Iterable[str]) -> None:
    requested = sorted(set(tool_keys))
    definitions = list(
        session.scalars(  # type: ignore[attr-defined]
            select(ToolDefinition.tool_key).where(
                ToolDefinition.enterprise_id == enterprise_id,
                ToolDefinition.status == "active",
                ToolDefinition.tool_key.in_(requested),
            )
        )
    )
    missing = sorted(set(requested) - set(definitions))
    if missing:
        raise ApiProblem(
            status_code=422,
            code="skill.tool_not_registered",
            message="Skill 引用的工具未登记或已停用",
            details={"tool_keys": missing},
        )


def _require_skill(session: Session, enterprise_id: str, skill_key: str) -> AgentSkill:
    skill = session.scalar(
        select(AgentSkill).where(
            AgentSkill.enterprise_id == enterprise_id,
            AgentSkill.skill_key == skill_key,
        )
    )
    if skill is None:
        raise _not_found("Skill 不存在", skill_key)
    return skill


def _skill_view(
    skill: AgentSkill,
    versions: list[AgentSkillVersion],
    principals: dict[str, str],
) -> SkillView:
    return SkillView(
        id=skill.id,
        key=skill.skill_key,
        name=skill.name,
        description=skill.description,
        status=skill.status,  # type: ignore[arg-type]
        current_version_number=skill.current_version_number,
        versions=[
            SkillVersionView(
                id=item.id,
                version_number=item.version_number,
                status=item.status,  # type: ignore[arg-type]
                instructions=item.instructions,
                tool_keys=list(item.tool_keys),
                input_schema=dict(item.input_schema),
                output_schema=dict(item.output_schema),
                change_summary=item.change_summary,
                created_by=principals.get(item.created_by_principal_id or ""),
                created_at=item.created_at,
                published_at=item.published_at,
            )
            for item in versions
        ],
        created_by=principals.get(skill.created_by_principal_id or ""),
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


def _mutation(
    database: Database,
    actor: ActorContext,
    event: AgentSkillEvent,
    *,
    idempotent: bool,
) -> SkillStudioMutationResponse:
    with database.session() as session:
        skill = session.get(AgentSkill, event.skill_id)
        version = session.get(AgentSkillVersion, event.version_id)
        principal = session.get(Principal, event.actor_principal_id)
        if skill is None or version is None or principal is None:
            raise LookupError("Skill 变更记录不完整")
        event_view = SkillConfigurationEventView(
            id=event.id,
            skill_key=skill.skill_key,
            version_number=version.version_number,
            event_type=event.event_type,  # type: ignore[arg-type]
            actor_name=principal.display_name,
            reason=event.reason,
            request_id=event.request_id,
            run_id=event.run_id,
            occurred_at=event.occurred_at,
        )
    return SkillStudioMutationResponse(
        idempotent=idempotent,
        event=event_view,
        studio=list_skill_studio(database, actor),
    )


def _conflict(message: str, detail: str) -> ApiProblem:
    return ApiProblem(
        status_code=409,
        code="skill.configuration_conflict",
        message=message,
        details={"value": detail},
    )


def _not_found(message: str, detail: str) -> ApiProblem:
    return ApiProblem(
        status_code=404,
        code="skill.not_found",
        message=message,
        details={"value": detail},
    )
