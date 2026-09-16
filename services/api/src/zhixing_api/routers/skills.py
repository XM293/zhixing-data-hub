from fastapi import APIRouter, Request

from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.skill_schemas import (
    SkillCreateRequest,
    SkillPublishRequest,
    SkillStudioMutationResponse,
    SkillStudioResponse,
    SkillVersionCreateRequest,
)
from zhixing_api.skill_service import (
    create_skill,
    create_skill_version,
    list_skill_studio,
    publish_skill_version,
)

router = APIRouter(prefix="/api/v1", tags=["skills"])


def _authorize(request: Request, resource_key: str) -> None:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "skill.registry.manage",
        request.app.state.database,
        resource_type="agent-skill",
        resource_key=resource_key,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )


@router.get("/skills/studio", response_model=SkillStudioResponse)
async def skill_studio(request: Request) -> SkillStudioResponse:
    actor = resolve_development_actor(request)
    _authorize(request, "catalog")
    return list_skill_studio(request.app.state.database, actor)


@router.post("/skills", response_model=SkillStudioMutationResponse)
async def skill_create(
    request: Request,
    payload: SkillCreateRequest,
) -> SkillStudioMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, payload.skill_key)
    return create_skill(request.app.state.database, actor, payload)


@router.post(
    "/skills/{skill_key}/versions",
    response_model=SkillStudioMutationResponse,
)
async def skill_version_create(
    request: Request,
    skill_key: str,
    payload: SkillVersionCreateRequest,
) -> SkillStudioMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, skill_key)
    return create_skill_version(
        request.app.state.database,
        actor,
        skill_key=skill_key,
        payload=payload,
    )


@router.post(
    "/skills/{skill_key}/versions/{version_number}/publish",
    response_model=SkillStudioMutationResponse,
)
async def skill_version_publish(
    request: Request,
    skill_key: str,
    version_number: int,
    payload: SkillPublishRequest,
) -> SkillStudioMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, skill_key)
    return publish_skill_version(
        request.app.state.database,
        actor,
        skill_key=skill_key,
        version_number=version_number,
        payload=payload,
    )
