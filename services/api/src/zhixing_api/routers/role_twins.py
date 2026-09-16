from fastapi import APIRouter, Request

from zhixing_api.actor_context import ActorContext, require_permission, resolve_development_actor
from zhixing_api.role_twin_schemas import (
    RoleStudioMutationResponse,
    RoleStudioResponse,
    RoleTemplateCreateRequest,
    RoleTemplateVersionCreateRequest,
    RoleTwinCreateRequest,
    RoleTwinVersionCreateRequest,
    RoleVersionPublishRequest,
)
from zhixing_api.role_twin_service import (
    create_role_template,
    create_role_template_version,
    create_role_twin,
    create_role_twin_version,
    list_role_studio,
    publish_role_template_version,
    publish_role_twin_version,
)

router = APIRouter(prefix="/api/v1", tags=["role-twin-studio"])


@router.get("/role-studio", response_model=RoleStudioResponse)
async def role_studio(request: Request) -> RoleStudioResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "role-twin.read", "role-studio", "catalog")
    return list_role_studio(request.app.state.database, actor)


@router.post("/role-templates", response_model=RoleStudioMutationResponse)
async def role_template_create(
    request: Request,
    payload: RoleTemplateCreateRequest,
) -> RoleStudioMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "role-twin.configure", "role-template", payload.template_key)
    return create_role_template(request.app.state.database, actor, payload)


@router.post(
    "/role-templates/{template_key}/versions",
    response_model=RoleStudioMutationResponse,
)
async def role_template_version_create(
    request: Request,
    template_key: str,
    payload: RoleTemplateVersionCreateRequest,
) -> RoleStudioMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "role-twin.configure", "role-template", template_key)
    return create_role_template_version(
        request.app.state.database,
        actor,
        template_key=template_key,
        payload=payload,
    )


@router.post(
    "/role-templates/{template_key}/versions/{version_number}/publish",
    response_model=RoleStudioMutationResponse,
)
async def role_template_version_publish(
    request: Request,
    template_key: str,
    version_number: int,
    payload: RoleVersionPublishRequest,
) -> RoleStudioMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "role-twin.configure", "role-template", template_key)
    return publish_role_template_version(
        request.app.state.database,
        actor,
        template_key=template_key,
        version_number=version_number,
        reason=payload.reason,
    )


@router.post("/role-twins", response_model=RoleStudioMutationResponse)
async def role_twin_create(
    request: Request,
    payload: RoleTwinCreateRequest,
) -> RoleStudioMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "role-twin.configure", "role-twin", payload.twin_key)
    return create_role_twin(request.app.state.database, actor, payload)


@router.post(
    "/role-twins/{twin_key}/versions",
    response_model=RoleStudioMutationResponse,
)
async def role_twin_version_create(
    request: Request,
    twin_key: str,
    payload: RoleTwinVersionCreateRequest,
) -> RoleStudioMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "role-twin.configure", "role-twin", twin_key)
    return create_role_twin_version(
        request.app.state.database,
        actor,
        twin_key=twin_key,
        payload=payload,
    )


@router.post(
    "/role-twins/{twin_key}/versions/{version_number}/publish",
    response_model=RoleStudioMutationResponse,
)
async def role_twin_version_publish(
    request: Request,
    twin_key: str,
    version_number: int,
    payload: RoleVersionPublishRequest,
) -> RoleStudioMutationResponse:
    actor = resolve_development_actor(request)
    _authorize(request, actor, "role-twin.configure", "role-twin", twin_key)
    return publish_role_twin_version(
        request.app.state.database,
        actor,
        twin_key=twin_key,
        version_number=version_number,
        reason=payload.reason,
    )


def _authorize(
    request: Request,
    actor: ActorContext,
    permission: str,
    resource_type: str,
    resource_key: str,
) -> None:
    require_permission(
        actor,
        permission,
        request.app.state.database,
        resource_type=resource_type,
        resource_key=resource_key,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
