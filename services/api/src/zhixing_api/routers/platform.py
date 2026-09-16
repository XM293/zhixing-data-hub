from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response, status

from zhixing_api.actor_context import ActorContext, require_permission, resolve_development_actor
from zhixing_api.models import PlatformModulesResponse
from zhixing_api.modules import PLATFORM_MODULES
from zhixing_api.platform_admin_schemas import (
    AccessDelegationCreateRequest,
    AccessDelegationMutationResponse,
    AccessDelegationRevokeRequest,
    AccessGovernanceResponse,
    BulkExchangeCommitRequest,
    BulkExchangeDetailResponse,
    BulkExchangeExportRequest,
    BulkExchangeListResponse,
    BulkExchangeMutationResponse,
    BulkExchangePreflightRequest,
    DictionaryItemUpsertRequest,
    FileAssetListResponse,
    FileAssetMutationResponse,
    FileAssetUploadRequest,
    JobAdminResponse,
    JobDetailResponse,
    JobRetryRequest,
    JobRetryResponse,
    NotificationInboxResponse,
    NotificationMutationResponse,
    NotificationPublishRequest,
    NotificationReadRequest,
    ParameterUpdateRequest,
    PermissionExplanationResponse,
    PlatformConfigMutationResponse,
    PlatformConfigResponse,
)
from zhixing_api.platform_admin_service import (
    access_governance_overview,
    bulk_exchange_detail,
    commit_bulk_exchange,
    create_access_delegation,
    explain_principal_permissions,
    export_bulk_exchange,
    job_admin_overview,
    job_detail,
    list_bulk_exchanges,
    list_file_assets,
    notification_inbox,
    platform_config_overview,
    preflight_bulk_exchange,
    publish_notification,
    read_file_asset,
    retry_job,
    revoke_access_delegation,
    set_notification_read,
    update_parameter,
    upload_file_asset,
    upsert_dictionary_item,
)

router = APIRouter(prefix="/api/v1/platform", tags=["platform"])


@router.get("/modules", response_model=PlatformModulesResponse)
async def list_modules() -> PlatformModulesResponse:
    return PlatformModulesResponse(modules=list(PLATFORM_MODULES))


@router.get("/admin/jobs", response_model=JobAdminResponse)
async def get_jobs(
    request: Request,
    job_status: str | None = Query(default=None, alias="status"),
    job_type: str | None = None,
    query: str | None = None,
) -> JobAdminResponse:
    actor = _authorize(request, "operations.run.read", "background_job")
    return job_admin_overview(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        status=job_status,
        job_type=job_type,
        query=query,
    )


@router.get("/admin/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: str, request: Request) -> JobDetailResponse:
    actor = _authorize(request, "operations.run.read", "background_job", job_id)
    return job_detail(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        job_id=job_id,
    )


@router.post("/admin/jobs/{job_id}/retry", response_model=JobRetryResponse)
async def retry_background_job(
    job_id: str, payload: JobRetryRequest, request: Request
) -> JobRetryResponse:
    actor = _authorize(request, "operations.run.manage", "background_job", job_id)
    return retry_job(request.app.state.database, actor=actor, job_id=job_id, payload=payload)


@router.get("/admin/config", response_model=PlatformConfigResponse)
async def get_platform_config(request: Request) -> PlatformConfigResponse:
    actor = _authorize(request, "platform.config.read", "platform_config")
    return platform_config_overview(request.app.state.database, enterprise_id=actor.enterprise_id)


@router.put(
    "/admin/config/parameters/{parameter_key}",
    response_model=PlatformConfigMutationResponse,
)
async def configure_platform_parameter(
    parameter_key: str, payload: ParameterUpdateRequest, request: Request
) -> PlatformConfigMutationResponse:
    actor = _authorize(request, "platform.config.manage", "platform_parameter", parameter_key)
    return update_parameter(
        request.app.state.database,
        actor=actor,
        parameter_key=parameter_key,
        payload=payload,
    )


@router.put(
    "/admin/config/dictionaries/{dictionary_key}/items/{item_key}",
    response_model=PlatformConfigMutationResponse,
)
async def configure_dictionary_item(
    dictionary_key: str,
    item_key: str,
    payload: DictionaryItemUpsertRequest,
    request: Request,
) -> PlatformConfigMutationResponse:
    actor = _authorize(request, "platform.config.manage", "platform_dictionary", dictionary_key)
    return upsert_dictionary_item(
        request.app.state.database,
        actor=actor,
        dictionary_key=dictionary_key,
        item_key=item_key,
        payload=payload,
    )


@router.get("/notifications", response_model=NotificationInboxResponse)
async def get_notifications(
    request: Request, notification_status: str | None = Query(default=None, alias="status")
) -> NotificationInboxResponse:
    actor = _authorize(
        request,
        "notification.read",
        "notification_inbox",
        "self",
        require_enterprise_scope=False,
    )
    return notification_inbox(request.app.state.database, actor=actor, status=notification_status)


@router.put(
    "/notifications/{notification_id}/read",
    response_model=NotificationMutationResponse,
)
async def configure_notification_read(
    notification_id: str, payload: NotificationReadRequest, request: Request
) -> NotificationMutationResponse:
    actor = _authorize(
        request,
        "notification.read",
        "notification",
        notification_id,
        require_enterprise_scope=False,
    )
    return set_notification_read(
        request.app.state.database,
        actor=actor,
        notification_id=notification_id,
        read=payload.read,
    )


@router.post(
    "/admin/notifications",
    response_model=NotificationMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification(
    payload: NotificationPublishRequest, request: Request
) -> NotificationMutationResponse:
    actor = _authorize(request, "notification.publish", "notification_batch")
    return publish_notification(request.app.state.database, actor=actor, payload=payload)


@router.get("/admin/files", response_model=FileAssetListResponse)
async def get_file_assets(request: Request) -> FileAssetListResponse:
    actor = _authorize(request, "file.asset.read", "file_asset")
    return list_file_assets(request.app.state.database, actor=actor)


@router.post(
    "/admin/files",
    response_model=FileAssetMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_file_asset(
    payload: FileAssetUploadRequest, request: Request
) -> FileAssetMutationResponse:
    actor = _authorize(request, "file.asset.manage", "file_asset", payload.asset_key)
    return upload_file_asset(
        request.app.state.database,
        actor=actor,
        payload=payload,
        storage=request.app.state.object_storage,
    )


@router.get("/admin/files/{asset_id}/content")
async def download_file_asset(asset_id: str, request: Request) -> Response:
    actor = _authorize(request, "file.asset.read", "file_asset", asset_id)
    asset, content = read_file_asset(
        request.app.state.database,
        actor=actor,
        asset_id=asset_id,
        storage=request.app.state.object_storage,
    )
    encoded_name = quote(asset.file_name)
    return Response(
        content=content,
        media_type=asset.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.get("/admin/bulk-exchanges", response_model=BulkExchangeListResponse)
async def get_bulk_exchanges(request: Request) -> BulkExchangeListResponse:
    actor = _authorize(request, "bulk.exchange.read", "bulk_exchange")
    return list_bulk_exchanges(request.app.state.database, enterprise_id=actor.enterprise_id)


@router.get("/admin/bulk-exchanges/{job_id}", response_model=BulkExchangeDetailResponse)
async def get_bulk_exchange(job_id: str, request: Request) -> BulkExchangeDetailResponse:
    actor = _authorize(request, "bulk.exchange.read", "bulk_exchange", job_id)
    return bulk_exchange_detail(
        request.app.state.database, enterprise_id=actor.enterprise_id, job_id=job_id
    )


@router.post(
    "/admin/bulk-exchanges/preflight",
    response_model=BulkExchangeMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bulk_exchange_preflight(
    payload: BulkExchangePreflightRequest, request: Request
) -> BulkExchangeMutationResponse:
    actor = _authorize(request, "bulk.exchange.manage", "bulk_exchange")
    return preflight_bulk_exchange(request.app.state.database, actor=actor, payload=payload)


@router.post(
    "/admin/bulk-exchanges/export",
    response_model=BulkExchangeMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bulk_exchange_export(
    payload: BulkExchangeExportRequest, request: Request
) -> BulkExchangeMutationResponse:
    actor = _authorize(request, "bulk.exchange.manage", "bulk_exchange")
    return export_bulk_exchange(
        request.app.state.database,
        actor=actor,
        payload=payload,
        storage=request.app.state.object_storage,
    )


@router.post(
    "/admin/bulk-exchanges/{job_id}/commit",
    response_model=BulkExchangeMutationResponse,
)
async def commit_bulk_exchange_job(
    job_id: str, payload: BulkExchangeCommitRequest, request: Request
) -> BulkExchangeMutationResponse:
    actor = _authorize(request, "bulk.exchange.manage", "bulk_exchange", job_id)
    return commit_bulk_exchange(
        request.app.state.database, actor=actor, job_id=job_id, payload=payload
    )


@router.get("/admin/access-governance", response_model=AccessGovernanceResponse)
async def get_access_governance(request: Request) -> AccessGovernanceResponse:
    actor = _authorize(request, "identity.delegation.manage", "access_governance")
    return access_governance_overview(request.app.state.database, enterprise_id=actor.enterprise_id)


@router.post(
    "/admin/access-governance/delegations",
    response_model=AccessDelegationMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_delegation(
    payload: AccessDelegationCreateRequest, request: Request
) -> AccessDelegationMutationResponse:
    actor = _authorize(request, "identity.delegation.manage", "access_delegation")
    return create_access_delegation(request.app.state.database, actor=actor, payload=payload)


@router.post(
    "/admin/access-governance/delegations/{delegation_id}/revoke",
    response_model=AccessDelegationMutationResponse,
)
async def revoke_delegation(
    delegation_id: str, payload: AccessDelegationRevokeRequest, request: Request
) -> AccessDelegationMutationResponse:
    actor = _authorize(request, "identity.delegation.manage", "access_delegation", delegation_id)
    return revoke_access_delegation(
        request.app.state.database,
        actor=actor,
        delegation_id=delegation_id,
        payload=payload,
    )


@router.get(
    "/admin/access-governance/permissions/{principal_id}",
    response_model=PermissionExplanationResponse,
)
async def explain_permissions(principal_id: str, request: Request) -> PermissionExplanationResponse:
    actor = _authorize(request, "identity.access.manage", "permission_explanation", principal_id)
    return explain_principal_permissions(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        principal_id=principal_id,
    )


def _authorize(
    request: Request,
    permission: str,
    resource_type: str,
    resource_key: str | None = None,
    require_enterprise_scope: bool = True,
) -> ActorContext:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        permission,
        request.app.state.database,
        resource_type=resource_type,
        resource_key=resource_key or actor.enterprise_id,
        scope_type="enterprise" if require_enterprise_scope else None,
        scope_id=actor.enterprise_id if require_enterprise_scope else None,
    )
    return actor
