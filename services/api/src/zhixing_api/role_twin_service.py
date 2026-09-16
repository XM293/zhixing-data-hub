from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext
from zhixing_api.data_models import (
    AgentRun,
    Principal,
    RoleConfigurationEvent,
    RoleTemplate,
    RoleTemplateVersion,
    RoleTwinProfile,
    RoleTwinVersion,
    TwinActor,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.role_twin_schemas import (
    RoleConfigurationEventView,
    RoleOwnerOption,
    RoleStudioMutationResponse,
    RoleStudioResponse,
    RoleStudioStats,
    RoleTemplateCreateRequest,
    RoleTemplateVersionCreateRequest,
    RoleTemplateVersionView,
    RoleTemplateView,
    RoleTwinCreateRequest,
    RoleTwinInstanceView,
    RoleTwinVersionCreateRequest,
    RoleTwinVersionView,
)

T = TypeVar("T")
K = TypeVar("K")


def list_role_studio(database: Database, actor: ActorContext) -> RoleStudioResponse:
    with database.session() as session:
        templates = list(
            session.scalars(
                select(RoleTemplate)
                .where(RoleTemplate.enterprise_id == actor.enterprise_id)
                .order_by(RoleTemplate.name, RoleTemplate.template_key)
            )
        )
        template_ids = [item.id for item in templates]
        profiles = list(
            session.scalars(
                select(RoleTwinProfile)
                .where(RoleTwinProfile.enterprise_id == actor.enterprise_id)
                .order_by(RoleTwinProfile.role_title, RoleTwinProfile.twin_key)
            )
        )
        profile_ids = [item.id for item in profiles]
        template_versions = list(
            session.scalars(
                select(RoleTemplateVersion)
                .where(RoleTemplateVersion.template_id.in_(template_ids))
                .order_by(
                    RoleTemplateVersion.template_id,
                    RoleTemplateVersion.version_number.desc(),
                )
            )
        ) if template_ids else []
        twin_versions = list(
            session.scalars(
                select(RoleTwinVersion)
                .where(RoleTwinVersion.twin_profile_id.in_(profile_ids))
                .order_by(RoleTwinVersion.twin_profile_id, RoleTwinVersion.version_number.desc())
            )
        ) if profile_ids else []
        principals = {
            item.id: item
            for item in session.scalars(
                select(Principal).where(Principal.enterprise_id == actor.enterprise_id)
            )
        }
        owner_options = [
            RoleOwnerOption(
                key=item.principal_key,
                display_name=item.display_name,
                status=item.status,
            )
            for item in sorted(
                principals.values(),
                key=lambda principal: (principal.status != "active", principal.display_name),
            )
        ]
        run_counts: dict[str, int] = {
            profile_id: int(count)
            for profile_id, count in session.execute(
                select(AgentRun.twin_profile_id, func.count(AgentRun.id))
                .where(AgentRun.enterprise_id == actor.enterprise_id)
                .group_by(AgentRun.twin_profile_id)
            ).all()
        }

    versions_by_template = _group_by(template_versions, lambda item: item.template_id)
    versions_by_twin = _group_by(twin_versions, lambda item: item.twin_profile_id)
    templates_by_id = {item.id: item for item in templates}
    template_version_by_id = {item.id: item for item in template_versions}
    twin_count_by_template: dict[str, int] = {}
    for profile in profiles:
        if profile.role_template_id:
            twin_count_by_template[profile.role_template_id] = (
                twin_count_by_template.get(profile.role_template_id, 0) + 1
            )

    template_views = [
        _template_view(
            item,
            versions_by_template.get(item.id, []),
            principals,
            twin_count_by_template.get(item.id, 0),
        )
        for item in templates
    ]
    twin_views = [
        _twin_view(
            item,
            templates_by_id,
            versions_by_twin.get(item.id, []),
            template_version_by_id,
            principals,
            int(run_counts.get(item.id, 0)),
        )
        for item in profiles
    ]
    draft_version_count = sum(item.status == "draft" for item in template_versions)
    draft_version_count += sum(item.status == "draft" for item in twin_versions)
    return RoleStudioResponse(
        stats=RoleStudioStats(
            template_count=len(templates),
            instance_count=len(profiles),
            published_template_count=sum(item.status == "published" for item in templates),
            published_instance_count=sum(item.status == "published" for item in profiles),
            draft_version_count=draft_version_count,
            run_count=sum(run_counts.values(), 0),
        ),
        owners=owner_options,
        templates=template_views,
        twins=twin_views,
        generated_at=datetime.now(UTC),
    )


def create_role_template(
    database: Database,
    actor: ActorContext,
    payload: RoleTemplateCreateRequest,
) -> RoleStudioMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        existing = session.scalar(
            select(RoleTemplate).where(
                RoleTemplate.enterprise_id == actor.enterprise_id,
                RoleTemplate.template_key == payload.template_key,
            )
        )
        if existing is not None:
            raise _conflict("岗位模板键已存在", payload.template_key)
        template = RoleTemplate(
            id=f"role_template_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            template_key=payload.template_key,
            name=payload.name,
            description=payload.description,
            status="draft",
            created_at=now,
            updated_at=now,
        )
        version = _new_template_version(
            template,
            actor,
            payload,
            version_number=1,
            now=now,
        )
        session.add_all([template, version])
        event = _add_event(
            session,
            actor,
            configuration_type="template",
            configuration_key=template.template_key,
            version_id=version.id,
            version_number=1,
            event_type="created",
            reason=payload.change_summary,
            now=now,
        )
        session.commit()
    return _mutation(database, actor, event, idempotent=False)


def create_role_template_version(
    database: Database,
    actor: ActorContext,
    *,
    template_key: str,
    payload: RoleTemplateVersionCreateRequest,
) -> RoleStudioMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        template = _require_template(session, actor.enterprise_id, template_key)
        version_number = int(
            session.scalar(
                select(func.max(RoleTemplateVersion.version_number)).where(
                    RoleTemplateVersion.template_id == template.id
                )
            ) or 0
        ) + 1
        version = _new_template_version(
            template,
            actor,
            payload,
            version_number=version_number,
            now=now,
        )
        session.add(version)
        template.updated_at = now
        event = _add_event(
            session,
            actor,
            configuration_type="template",
            configuration_key=template.template_key,
            version_id=version.id,
            version_number=version_number,
            event_type="version-created",
            reason=payload.change_summary,
            now=now,
        )
        session.commit()
    return _mutation(database, actor, event, idempotent=False)


def publish_role_template_version(
    database: Database,
    actor: ActorContext,
    *,
    template_key: str,
    version_number: int,
    reason: str,
) -> RoleStudioMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        template = _require_template(session, actor.enterprise_id, template_key)
        version = session.scalar(
            select(RoleTemplateVersion).where(
                RoleTemplateVersion.template_id == template.id,
                RoleTemplateVersion.version_number == version_number,
            )
        )
        if version is None:
            raise _not_found("岗位模板版本不存在", f"{template_key}:v{version_number}")
        existing_event = _published_event(
            session,
            actor.enterprise_id,
            "template",
            template_key,
            version.id,
        )
        if version.status == "published" and existing_event is not None:
            return _mutation(database, actor, existing_event, idempotent=True)
        if version.status != "draft":
            raise _conflict("只有草稿岗位模板版本可以发布", version.status)
        version.status = "published"
        version.published_at = now
        template.status = "published"
        template.updated_at = now
        event = _add_event(
            session,
            actor,
            configuration_type="template",
            configuration_key=template.template_key,
            version_id=version.id,
            version_number=version.version_number,
            event_type="published",
            reason=reason,
            now=now,
        )
        session.commit()
    return _mutation(database, actor, event, idempotent=False)


def create_role_twin(
    database: Database,
    actor: ActorContext,
    payload: RoleTwinCreateRequest,
) -> RoleStudioMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        if session.scalar(
            select(RoleTwinProfile.id).where(
                RoleTwinProfile.enterprise_id == actor.enterprise_id,
                RoleTwinProfile.twin_key == payload.twin_key,
            )
        ):
            raise _conflict("分身实例键已存在", payload.twin_key)
        template = _require_template(session, actor.enterprise_id, payload.template_key)
        template_version = _current_template_version(session, template.id)
        if template_version is None:
            raise _conflict("岗位模板尚无已发布版本", payload.template_key)
        owner = _optional_owner(session, actor.enterprise_id, payload.owner_principal_key)
        profile = RoleTwinProfile(
            id=f"role_twin_profile_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            role_template_id=template.id,
            owner_principal_id=owner.id if owner else None,
            twin_key=payload.twin_key,
            display_name=payload.display_name,
            role_title=template_version.role_title,
            voice_guide=payload.voice_guide,
            reasoning_guide=payload.reasoning_guide,
            answer_policy=payload.answer_policy,
            provider=payload.provider,
            model=payload.model,
            status="draft",
            published_at=None,
            updated_at=now,
        )
        version = _new_twin_version(
            profile,
            template_version,
            actor,
            payload,
            version_number=1,
            now=now,
        )
        session.add_all([profile, version])
        event = _add_event(
            session,
            actor,
            configuration_type="twin",
            configuration_key=profile.twin_key,
            version_id=version.id,
            version_number=1,
            event_type="created",
            reason=payload.change_summary,
            now=now,
        )
        session.commit()
    return _mutation(database, actor, event, idempotent=False)


def create_role_twin_version(
    database: Database,
    actor: ActorContext,
    *,
    twin_key: str,
    payload: RoleTwinVersionCreateRequest,
) -> RoleStudioMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        profile = _require_twin(session, actor.enterprise_id, twin_key)
        if profile.role_template_id is None:
            raise _conflict("分身实例尚未绑定岗位模板", twin_key)
        template_version = _current_template_version(session, profile.role_template_id)
        if template_version is None:
            raise _conflict("岗位模板尚无已发布版本", twin_key)
        version_number = int(
            session.scalar(
                select(func.max(RoleTwinVersion.version_number)).where(
                    RoleTwinVersion.twin_profile_id == profile.id
                )
            ) or 0
        ) + 1
        version = _new_twin_version(
            profile,
            template_version,
            actor,
            payload,
            version_number=version_number,
            now=now,
        )
        session.add(version)
        event = _add_event(
            session,
            actor,
            configuration_type="twin",
            configuration_key=profile.twin_key,
            version_id=version.id,
            version_number=version_number,
            event_type="version-created",
            reason=payload.change_summary,
            now=now,
        )
        session.commit()
    return _mutation(database, actor, event, idempotent=False)


def publish_role_twin_version(
    database: Database,
    actor: ActorContext,
    *,
    twin_key: str,
    version_number: int,
    reason: str,
) -> RoleStudioMutationResponse:
    now = datetime.now(UTC)
    with database.session() as session:
        profile = _require_twin(session, actor.enterprise_id, twin_key)
        version = session.scalar(
            select(RoleTwinVersion).where(
                RoleTwinVersion.twin_profile_id == profile.id,
                RoleTwinVersion.version_number == version_number,
            )
        )
        if version is None:
            raise _not_found("分身配置版本不存在", f"{twin_key}:v{version_number}")
        existing_event = _published_event(
            session,
            actor.enterprise_id,
            "twin",
            twin_key,
            version.id,
        )
        if version.status == "published" and existing_event is not None:
            return _mutation(database, actor, existing_event, idempotent=True)
        if version.status != "draft":
            raise _conflict("只有草稿分身配置版本可以发布", version.status)
        template_version = session.get(RoleTemplateVersion, version.template_version_id)
        if template_version is None or template_version.status != "published":
            raise _conflict("分身配置引用的岗位模板版本不可发布", version.template_version_id)
        version.status = "published"
        version.published_at = now
        profile.display_name = version.display_name
        profile.role_title = template_version.role_title
        profile.voice_guide = version.voice_guide
        profile.reasoning_guide = version.reasoning_guide
        profile.answer_policy = version.answer_policy
        profile.provider = version.provider
        profile.model = version.model
        profile.status = "published"
        profile.published_at = now
        profile.updated_at = now
        twin_actor = session.scalar(
            select(TwinActor).where(
                TwinActor.enterprise_id == actor.enterprise_id,
                TwinActor.actor_key == profile.twin_key,
            )
        )
        if twin_actor is not None:
            twin_actor.display_name = version.display_name
            twin_actor.role_title = template_version.role_title
            twin_actor.capabilities = version.capabilities
        event = _add_event(
            session,
            actor,
            configuration_type="twin",
            configuration_key=profile.twin_key,
            version_id=version.id,
            version_number=version.version_number,
            event_type="published",
            reason=reason,
            now=now,
        )
        session.commit()
    return _mutation(database, actor, event, idempotent=False)


def current_twin_version(session: Session, profile_id: str) -> RoleTwinVersion | None:
    return session.scalar(
        select(RoleTwinVersion)
        .where(
            RoleTwinVersion.twin_profile_id == profile_id,
            RoleTwinVersion.status == "published",
        )
        .order_by(RoleTwinVersion.version_number.desc())
        .limit(1)
    )


def _new_template_version(
    template: RoleTemplate,
    actor: ActorContext,
    payload: RoleTemplateVersionCreateRequest | RoleTemplateCreateRequest,
    *,
    version_number: int,
    now: datetime,
) -> RoleTemplateVersion:
    return RoleTemplateVersion(
        id=f"role_template_version_{uuid4().hex}",
        template_id=template.id,
        version_number=version_number,
        status="draft",
        role_title=payload.role_title,
        responsibilities=_clean_list(payload.responsibilities),
        capability_boundaries=_clean_list(payload.capability_boundaries),
        default_voice_guide=payload.default_voice_guide.strip(),
        default_reasoning_guide=payload.default_reasoning_guide.strip(),
        default_answer_policy=payload.default_answer_policy.strip(),
        change_summary=payload.change_summary.strip(),
        created_by_principal_id=actor.principal_id,
        created_at=now,
        published_at=None,
    )


def _new_twin_version(
    profile: RoleTwinProfile,
    template_version: RoleTemplateVersion,
    actor: ActorContext,
    payload: RoleTwinVersionCreateRequest | RoleTwinCreateRequest,
    *,
    version_number: int,
    now: datetime,
) -> RoleTwinVersion:
    return RoleTwinVersion(
        id=f"role_twin_version_{uuid4().hex}",
        twin_profile_id=profile.id,
        template_version_id=template_version.id,
        version_number=version_number,
        status="draft",
        display_name=payload.display_name.strip(),
        voice_guide=payload.voice_guide.strip(),
        reasoning_guide=payload.reasoning_guide.strip(),
        answer_policy=payload.answer_policy.strip(),
        provider=payload.provider.strip(),
        model=payload.model.strip(),
        capabilities=_clean_list(payload.capabilities),
        change_summary=payload.change_summary.strip(),
        created_by_principal_id=actor.principal_id,
        created_at=now,
        published_at=None,
    )


def _template_view(
    template: RoleTemplate,
    versions: list[RoleTemplateVersion],
    principals: dict[str, Principal],
    twin_count: int,
) -> RoleTemplateView:
    current = next((item for item in versions if item.status == "published"), None)
    return RoleTemplateView(
        id=template.id,
        key=template.template_key,
        name=template.name,
        description=template.description,
        status=template.status,
        current_version_number=current.version_number if current else None,
        twin_count=twin_count,
        versions=[
            RoleTemplateVersionView(
                id=item.id,
                version_number=item.version_number,
                status=item.status,
                role_title=item.role_title,
                responsibilities=item.responsibilities,
                capability_boundaries=item.capability_boundaries,
                default_voice_guide=item.default_voice_guide,
                default_reasoning_guide=item.default_reasoning_guide,
                default_answer_policy=item.default_answer_policy,
                change_summary=item.change_summary,
                created_by=(principals[item.created_by_principal_id].display_name
                            if item.created_by_principal_id in principals else None),
                created_at=item.created_at,
                published_at=item.published_at,
            )
            for item in versions
        ],
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _twin_view(
    profile: RoleTwinProfile,
    templates: dict[str, RoleTemplate],
    versions: list[RoleTwinVersion],
    template_versions: dict[str, RoleTemplateVersion],
    principals: dict[str, Principal],
    run_count: int,
) -> RoleTwinInstanceView:
    template = templates.get(profile.role_template_id or "")
    owner = principals.get(profile.owner_principal_id or "")
    current = next((item for item in versions if item.status == "published"), None)
    return RoleTwinInstanceView(
        id=profile.id,
        key=profile.twin_key,
        template_key=template.template_key if template else "unbound",
        template_name=template.name if template else "未绑定岗位模板",
        owner_principal_key=owner.principal_key if owner else None,
        owner_name=owner.display_name if owner else None,
        role_title=profile.role_title,
        status=profile.status,
        current_version_number=current.version_number if current else None,
        run_count=run_count,
        versions=[
            RoleTwinVersionView(
                id=item.id,
                version_number=item.version_number,
                template_version_number=template_versions[item.template_version_id].version_number,
                status=item.status,
                display_name=item.display_name,
                voice_guide=item.voice_guide,
                reasoning_guide=item.reasoning_guide,
                answer_policy=item.answer_policy,
                provider=item.provider,
                model=item.model,
                capabilities=item.capabilities,
                change_summary=item.change_summary,
                created_by=(principals[item.created_by_principal_id].display_name
                            if item.created_by_principal_id in principals else None),
                created_at=item.created_at,
                published_at=item.published_at,
            )
            for item in versions
        ],
        published_at=profile.published_at,
        updated_at=profile.updated_at,
    )


def _require_template(session: Session, enterprise_id: str, key: str) -> RoleTemplate:
    item = session.scalar(
        select(RoleTemplate).where(
            RoleTemplate.enterprise_id == enterprise_id,
            RoleTemplate.template_key == key,
        )
    )
    if item is None:
        raise _not_found("岗位模板不存在", key)
    return item


def _require_twin(session: Session, enterprise_id: str, key: str) -> RoleTwinProfile:
    item = session.scalar(
        select(RoleTwinProfile).where(
            RoleTwinProfile.enterprise_id == enterprise_id,
            RoleTwinProfile.twin_key == key,
        )
    )
    if item is None:
        raise _not_found("分身实例不存在", key)
    return item


def _current_template_version(
    session: Session,
    template_id: str,
) -> RoleTemplateVersion | None:
    return session.scalar(
        select(RoleTemplateVersion)
        .where(
            RoleTemplateVersion.template_id == template_id,
            RoleTemplateVersion.status == "published",
        )
        .order_by(RoleTemplateVersion.version_number.desc())
        .limit(1)
    )


def _optional_owner(
    session: Session,
    enterprise_id: str,
    principal_key: str | None,
) -> Principal | None:
    if not principal_key:
        return None
    owner = session.scalar(
        select(Principal).where(
            Principal.enterprise_id == enterprise_id,
            Principal.principal_key == principal_key,
            Principal.status == "active",
        )
    )
    if owner is None:
        raise _not_found("分身归属主体不存在或不可用", principal_key)
    return owner


def _add_event(
    session: Session,
    actor: ActorContext,
    *,
    configuration_type: str,
    configuration_key: str,
    version_id: str,
    version_number: int,
    event_type: str,
    reason: str,
    now: datetime,
) -> RoleConfigurationEvent:
    event = RoleConfigurationEvent(
        id=f"role_configuration_event_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        actor_principal_id=actor.principal_id,
        configuration_type=configuration_type,
        configuration_key=configuration_key,
        version_id=version_id,
        version_number=version_number,
        event_type=event_type,
        reason=reason.strip(),
        actor_snapshot=actor.snapshot(),
        request_id=actor.request_id,
        run_id=actor.run_id,
        occurred_at=now,
    )
    session.add(event)
    return event


def _published_event(
    session: Session,
    enterprise_id: str,
    configuration_type: str,
    configuration_key: str,
    version_id: str,
) -> RoleConfigurationEvent | None:
    return session.scalar(
        select(RoleConfigurationEvent).where(
            RoleConfigurationEvent.enterprise_id == enterprise_id,
            RoleConfigurationEvent.configuration_type == configuration_type,
            RoleConfigurationEvent.configuration_key == configuration_key,
            RoleConfigurationEvent.version_id == version_id,
            RoleConfigurationEvent.event_type == "published",
        )
    )


def _mutation(
    database: Database,
    actor: ActorContext,
    event: RoleConfigurationEvent,
    *,
    idempotent: bool,
) -> RoleStudioMutationResponse:
    return RoleStudioMutationResponse(
        idempotent=idempotent,
        event=RoleConfigurationEventView(
            id=event.id,
            configuration_type=event.configuration_type,  # type: ignore[arg-type]
            configuration_key=event.configuration_key,
            version_id=event.version_id,
            version_number=event.version_number,
            event_type=event.event_type,  # type: ignore[arg-type]
            actor_name=actor.display_name,
            reason=event.reason,
            request_id=event.request_id,
            run_id=event.run_id,
            occurred_at=event.occurred_at,
        ),
        studio=list_role_studio(database, actor),
    )


def _group_by(items: list[T], key: Callable[[T], K]) -> dict[K, list[T]]:
    grouped: dict[K, list[T]] = {}
    for item in items:
        grouped.setdefault(key(item), []).append(item)
    return grouped


def _clean_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


def _not_found(message: str, key: str) -> ApiProblem:
    return ApiProblem(status_code=404, code="role.not_found", message=message, details={"key": key})


def _conflict(message: str, value: str) -> ApiProblem:
    return ApiProblem(
        status_code=409,
        code="role.configuration_conflict",
        message=message,
        details={"value": value},
    )
