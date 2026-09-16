from fastapi import APIRouter, Request

from zhixing_api.actor_context import ActorContext, require_permission, resolve_development_actor
from zhixing_api.errors import ApiProblem
from zhixing_api.workspace_schemas import (
    WorkspaceCatalogResponse,
    WorkspaceProfileView,
    WorkspaceReadModelResponse,
)
from zhixing_api.workspace_service import (
    build_workspace_read_model,
    get_workspace_profile,
    list_workspaces,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


def _actor_for_workspace(request: Request) -> ActorContext:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "platform.navigation.read",
        request.app.state.database,
        resource_type="workspace",
        resource_key="workspace-catalog",
    )
    return actor


@router.get("/me", response_model=WorkspaceCatalogResponse)
async def get_my_workspaces(request: Request) -> WorkspaceCatalogResponse:
    actor = _actor_for_workspace(request)
    return list_workspaces(actor)


@router.get("/{workspace_key}", response_model=WorkspaceProfileView)
async def get_workspace_profile_view(
    workspace_key: str,
    request: Request,
) -> WorkspaceProfileView:
    actor = _actor_for_workspace(request)
    return get_workspace_profile(actor, workspace_key)


@router.get("/{workspace_key}/read-model", response_model=WorkspaceReadModelResponse)
async def get_workspace_read_model(
    workspace_key: str,
    request: Request,
) -> WorkspaceReadModelResponse:
    actor = _actor_for_workspace(request)
    try:
        return build_workspace_read_model(
            request.app.state.database,
            actor,
            workspace_key,
        )
    except KeyError as exc:
        raise ApiProblem(
            status_code=404,
            code="workspace.not_found",
            message="工作空间不存在",
            details={"workspace_key": workspace_key},
        ) from exc


@router.post("/{workspace_key}/refresh", response_model=WorkspaceReadModelResponse)
async def refresh_workspace(
    workspace_key: str,
    request: Request,
) -> WorkspaceReadModelResponse:
    actor = _actor_for_workspace(request)
    try:
        return build_workspace_read_model(
            request.app.state.database,
            actor,
            workspace_key,
        )
    except KeyError as exc:
        raise ApiProblem(
            status_code=404,
            code="workspace.not_found",
            message="工作空间不存在",
            details={"workspace_key": workspace_key},
        ) from exc
