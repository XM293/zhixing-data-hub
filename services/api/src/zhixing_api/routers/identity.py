from fastapi import APIRouter, HTTPException, Request, status

from zhixing_api.actor_context import ActorContext, require_permission, resolve_development_actor
from zhixing_api.channel_identity_schemas import (
    ChannelIdentityAdminResponse,
    ChannelIdentityConfigureRequest,
    ChannelIdentityMutationResponse,
)
from zhixing_api.channel_identity_service import (
    channel_identity_admin_overview,
    configure_channel_identity,
)
from zhixing_api.identity_catalog_service import (
    create_access_role,
    create_org_unit,
    create_position,
    update_access_role,
    update_org_unit,
    update_position,
)
from zhixing_api.identity_management_service import (
    configure_identity_user,
    create_identity_user,
)
from zhixing_api.identity_schemas import (
    CurrentIdentityResponse,
    IdentityAccessRoleCreateRequest,
    IdentityAccessRoleUpdateRequest,
    IdentityAdminOverviewResponse,
    IdentityCatalogMutationResponse,
    IdentityOrgUnitCreateRequest,
    IdentityOrgUnitUpdateRequest,
    IdentityPositionCreateRequest,
    IdentityPositionUpdateRequest,
    IdentityUserCreateRequest,
    IdentityUserMutationResponse,
    IdentityUserUpdateRequest,
)
from zhixing_api.identity_service import current_identity, identity_admin_overview

router = APIRouter(prefix="/api/v1/identity", tags=["identity"])


@router.get("/me", response_model=CurrentIdentityResponse)
async def get_current_identity(request: Request) -> CurrentIdentityResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "platform.navigation.read",
        request.app.state.database,
        resource_type="platform_navigation",
        resource_key="console",
    )
    try:
        return current_identity(request.app.state.database, actor)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/admin/overview", response_model=IdentityAdminOverviewResponse)
async def get_identity_admin_overview(request: Request) -> IdentityAdminOverviewResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "identity.user.manage",
        request.app.state.database,
        resource_type="identity_catalog",
        resource_key=actor.enterprise_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
    try:
        return identity_admin_overview(
            request.app.state.database,
            enterprise_id=actor.enterprise_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/admin/channel-identities",
    response_model=ChannelIdentityAdminResponse,
)
async def get_channel_identities(request: Request) -> ChannelIdentityAdminResponse:
    actor = resolve_development_actor(request)
    _require_catalog_permission(request, actor, "identity.user.manage")
    return channel_identity_admin_overview(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
    )


@router.put(
    "/admin/channel-identities/{identity_id}/configuration",
    response_model=ChannelIdentityMutationResponse,
)
async def configure_channel_identity_binding(
    identity_id: str,
    payload: ChannelIdentityConfigureRequest,
    request: Request,
) -> ChannelIdentityMutationResponse:
    actor = resolve_development_actor(request)
    _require_catalog_permission(request, actor, "identity.user.manage")
    return configure_channel_identity(
        request.app.state.database,
        actor=actor,
        identity_id=identity_id,
        payload=payload,
    )


@router.post(
    "/admin/users",
    response_model=IdentityUserMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: IdentityUserCreateRequest,
    request: Request,
) -> IdentityUserMutationResponse:
    actor = resolve_development_actor(request)
    _require_identity_management_permissions(request, actor)
    return create_identity_user(
        request.app.state.database,
        actor=actor,
        payload=payload,
    )


@router.put(
    "/admin/users/{account_key}/configuration",
    response_model=IdentityUserMutationResponse,
)
async def configure_user(
    account_key: str,
    payload: IdentityUserUpdateRequest,
    request: Request,
) -> IdentityUserMutationResponse:
    actor = resolve_development_actor(request)
    _require_identity_management_permissions(request, actor)
    return configure_identity_user(
        request.app.state.database,
        actor=actor,
        account_key=account_key,
        payload=payload,
    )


@router.post(
    "/admin/org-units",
    response_model=IdentityCatalogMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_org(
    payload: IdentityOrgUnitCreateRequest, request: Request
) -> IdentityCatalogMutationResponse:
    actor = resolve_development_actor(request)
    _require_catalog_permission(request, actor, "identity.user.manage")
    return create_org_unit(request.app.state.database, actor=actor, payload=payload)


@router.put("/admin/org-units/{org_key}", response_model=IdentityCatalogMutationResponse)
async def update_org(
    org_key: str, payload: IdentityOrgUnitUpdateRequest, request: Request
) -> IdentityCatalogMutationResponse:
    actor = resolve_development_actor(request)
    _require_catalog_permission(request, actor, "identity.user.manage")
    return update_org_unit(
        request.app.state.database, actor=actor, org_key=org_key, payload=payload
    )


@router.post(
    "/admin/positions",
    response_model=IdentityCatalogMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_position_catalog(
    payload: IdentityPositionCreateRequest, request: Request
) -> IdentityCatalogMutationResponse:
    actor = resolve_development_actor(request)
    _require_catalog_permission(request, actor, "identity.user.manage")
    return create_position(request.app.state.database, actor=actor, payload=payload)


@router.put("/admin/positions/{position_key}", response_model=IdentityCatalogMutationResponse)
async def update_position_catalog(
    position_key: str, payload: IdentityPositionUpdateRequest, request: Request
) -> IdentityCatalogMutationResponse:
    actor = resolve_development_actor(request)
    _require_catalog_permission(request, actor, "identity.user.manage")
    return update_position(
        request.app.state.database, actor=actor, position_key=position_key, payload=payload
    )


@router.post(
    "/admin/access-roles",
    response_model=IdentityCatalogMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_role(
    payload: IdentityAccessRoleCreateRequest, request: Request
) -> IdentityCatalogMutationResponse:
    actor = resolve_development_actor(request)
    _require_catalog_permission(request, actor, "identity.access.manage")
    return create_access_role(request.app.state.database, actor=actor, payload=payload)


@router.put("/admin/access-roles/{role_key}", response_model=IdentityCatalogMutationResponse)
async def update_role(
    role_key: str, payload: IdentityAccessRoleUpdateRequest, request: Request
) -> IdentityCatalogMutationResponse:
    actor = resolve_development_actor(request)
    _require_catalog_permission(request, actor, "identity.access.manage")
    return update_access_role(
        request.app.state.database, actor=actor, role_key=role_key, payload=payload
    )


def _require_identity_management_permissions(request: Request, actor: ActorContext) -> None:
    database = request.app.state.database
    for permission in ("identity.user.manage", "identity.access.manage"):
        require_permission(
            actor,
            permission,
            database,
            resource_type="identity_catalog",
            resource_key=actor.enterprise_id,
            scope_type="enterprise",
            scope_id=actor.enterprise_id,
        )


def _require_catalog_permission(request: Request, actor: ActorContext, permission: str) -> None:
    require_permission(
        actor,
        permission,
        request.app.state.database,
        resource_type="identity_catalog",
        resource_key=actor.enterprise_id,
        scope_type="enterprise",
        scope_id=actor.enterprise_id,
    )
