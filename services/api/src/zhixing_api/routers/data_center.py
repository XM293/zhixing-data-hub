from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from zhixing_connectors.catalog import (
    CATALOG_VERSION,
    OFFICIAL_RAW_SPECS,
    effective_schema_status,
    official_raw_spec,
    partition_parameter_names,
    resource_contract_version,
    resource_spec,
)
from zhixing_connectors.official_contracts import (
    OFFICIAL_CONTRACT_VERSION,
    contract_summary,
    official_contract,
)
from zhixing_connectors.official_registry import (
    OFFICIAL_REGISTRY_VERSION,
    OfficialOperation,
    official_operations,
    registry_summary,
)

from zhixing_api.actor_context import (
    ActorContext,
    require_permission,
    resolve_development_actor,
)
from zhixing_api.connectors.lingxing.resource_catalog import RESOURCE_CATALOG, can_project_to_core
from zhixing_api.customer_360_schemas import Customer360Response, CustomerDetailResponse
from zhixing_api.customer_360_service import build_customer_360, build_customer_detail
from zhixing_api.data_center_schemas import (
    BusinessEntityListResponse,
    CommerceOperationsResponse,
    DataQualityResponse,
    LingxingOfficialOperationListResponse,
    LingxingOfficialOperationView,
    MappingConflictListResponse,
    MappingConflictReviewRequest,
    MappingConflictView,
    MeetingActionRequest,
    MeetingActionResponse,
    MetricCatalogResponse,
    MetricSeriesResponse,
    OfficialResourceActivationRequest,
    OfficialResourceMaterializationResponse,
    PageView,
    SourceAuthorityRuleRequest,
    SourceAuthorityRuleView,
    SourceBindingListResponse,
    SourceBindingRequest,
    SourceBindingReviewRequest,
    SourceBindingView,
    SourceProbeView,
    SourceRegistrationRequest,
    SourceRegistrationView,
    SourceResourceListResponse,
    SourceResourceUpdateRequest,
    SourceResourceValidationRequest,
    SourceResourceView,
    SourceUpdateRequest,
    SyncCheckpointListResponse,
    SyncCheckpointView,
    SyncRequest,
    SyncResponse,
    SyncRunListResponse,
    TwinOverviewResponse,
)
from zhixing_api.data_center_service import (
    SOURCE_KEY_ALIASES,
    _run_view,
    advance_meeting,
    build_commerce_operations,
    build_overview,
    list_business_entities,
    list_data_quality,
    list_metric_catalog,
    list_sync_runs,
    query_metric_series,
)
from zhixing_api.data_models import (
    BusinessUnit,
    ExternalSystem,
    MappingConflict,
    PlatformEvent,
    SourceAuthorityRule,
    SourceBackfillPlan,
    SourceBinding,
    SourceCoverageWindow,
    SourceResource,
    SourceSyncSchedule,
    SyncResourceRun,
    SyncRun,
)
from zhixing_api.data_selection import require_selected_data_scope
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.authority import (
    AuthorityRequest,
    AuthorityView,
    list_authorities,
    save_authority,
)
from zhixing_api.ingestion.backfills import (
    BackfillRequest,
    BackfillView,
    CoverageWindowList,
    CoverageWindowView,
    save_backfill,
)
from zhixing_api.ingestion.batches import cancel_import, enqueue_import
from zhixing_api.ingestion.bindings import review_binding
from zhixing_api.ingestion.conflicts import review_conflict
from zhixing_api.ingestion.dependencies import DependencyValueList, list_dependency_values
from zhixing_api.ingestion.mapping import MAPPING_VERSION
from zhixing_api.ingestion.mirror import (
    MirrorPageList,
    MirrorQuarantineRequest,
    list_mirror_pages,
    quarantine_mirror_page,
)
from zhixing_api.ingestion.operations import SourceOperationsView, source_operations
from zhixing_api.ingestion.planning import (
    ImportRequest,
    ScheduleRequest,
    plan_import,
    schedule_strategy,
)
from zhixing_api.ingestion.queue import enqueue_sync
from zhixing_api.ingestion.replay import ReplayRequest, enqueue_replay
from zhixing_api.ingestion.rollout import (
    OfficialBackfillRolloutRequest,
    OfficialBackfillRolloutView,
    OfficialScheduleRolloutRequest,
    OfficialScheduleRolloutView,
    rollout_validated_store_backfills,
    rollout_validated_store_schedules,
)
from zhixing_api.ingestion.schedules import ScheduleView, save_schedule
from zhixing_api.scope_context import build_scope_context

router = APIRouter(prefix="/api/v1/data-center", tags=["data-center"])


@router.post("/raw-manifests/{manifest_id}/replay", status_code=202)
async def replay_raw_manifest(request: Request, manifest_id: str,
                              payload: ReplayRequest) -> dict[str, object]:
    actor = resolve_development_actor(request)
    run = enqueue_replay(request.app.state.database, actor, manifest_id, payload)
    return {"id": run.id, "task_id": run.task_id, "status": run.status}


@router.post("/raw-manifests/{manifest_id}/quarantine")
async def quarantine_raw_manifest(request: Request, manifest_id: str,
                                  payload: MirrorQuarantineRequest) -> dict[str, str]:
    actor = resolve_development_actor(request)
    page = quarantine_mirror_page(request.app.state.database, actor, manifest_id, payload)
    return {"id": page.raw_manifest_id, "schema_status": page.schema_status}


@router.get("/authority-assignments", response_model=list[AuthorityView])
async def source_authority_assignments(request: Request) -> list[AuthorityView]:
    actor = resolve_development_actor(request)
    return list_authorities(request.app.state.database, actor)


@router.put("/authority-assignments", response_model=AuthorityView)
async def save_source_authority(request: Request, payload: AuthorityRequest) -> AuthorityView:
    actor = resolve_development_actor(request)
    return save_authority(request.app.state.database, actor, payload)


@router.get("/sources/{source_key}/mirror-pages", response_model=MirrorPageList)
async def source_mirror_pages(request: Request, source_key: str,
                              offset: int = Query(default=0, ge=0),
                              limit: int = Query(default=25, ge=1, le=100)) -> MirrorPageList:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    with request.app.state.database.session() as session:
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key))
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        return list_mirror_pages(session, enterprise_id=actor.enterprise_id,
                                 source_id=source.id, offset=offset, limit=limit)


@router.get("/sources/{source_key}/dependency-values", response_model=DependencyValueList)
async def source_dependency_values(
    request: Request,
    source_key: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    value_type: str | None = Query(default=None, min_length=1, max_length=64),
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(active|stale|rejected)$"),
    scope_kind: str | None = Query(default=None, pattern="^(source|store|warehouse)$"),
    resource_key: str | None = Query(default=None, min_length=1, max_length=120),
) -> DependencyValueList:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    with request.app.state.database.session() as session:
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key))
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        return list_dependency_values(
            session, enterprise_id=actor.enterprise_id, external_system_id=source.id,
            offset=offset, limit=limit, value_type=value_type, status=status_filter,
            scope_kind=scope_kind, resource_key=resource_key,
        )


@router.post("/sources/{source_key}/imports", status_code=202)
async def import_source(request: Request, source_key: str,
                         payload: ImportRequest) -> dict[str, object]:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    try:
        partitions = plan_import(payload)
    except ValueError as exc:
        raise ApiProblem(status_code=422, code=str(exc),
                         message="导入分区重复或超过 128 个") from None
    run = enqueue_import(request.app.state.database, enterprise_id=actor.enterprise_id,
        source_key=source_key, initiator_id=actor.principal_id,
        request_id=getattr(request.state, "request_id", "import-request"), payload=payload,
        scope_snapshot=build_scope_context(request.app.state.database, actor).snapshot(),
        actor_snapshot=actor.snapshot(),
        provider_enabled=request.app.state.settings.lingxing_enabled)
    return {"id": run.id, "status": run.status, "partitions": len(partitions)}


@router.get("/sources/{source_key}/schedules", response_model=list[ScheduleView])
async def source_schedules(request: Request, source_key: str) -> list[ScheduleView]:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    with request.app.state.database.session() as session:
        rows = session.scalars(select(SourceSyncSchedule).join(ExternalSystem).where(
            SourceSyncSchedule.enterprise_id == actor.enterprise_id,
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key).order_by(SourceSyncSchedule.created_at))
        return [ScheduleView.model_validate(row) for row in rows]


@router.post("/sources/{source_key}/schedules", response_model=ScheduleView, status_code=201)
async def create_source_schedule(request: Request, source_key: str,
                                 payload: ScheduleRequest) -> ScheduleView:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    row = save_schedule(request.app.state.database, actor=actor, source_key=source_key,
        payload=payload, scope=build_scope_context(request.app.state.database, actor).snapshot())
    return ScheduleView.model_validate(row)


@router.post("/sources/{source_key}/official-rollout/schedules",
             response_model=OfficialScheduleRolloutView)
async def rollout_source_official_schedules(
    request: Request,
    source_key: str,
    payload: OfficialScheduleRolloutRequest,
) -> OfficialScheduleRolloutView:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    scope = build_scope_context(request.app.state.database, actor)
    return rollout_validated_store_schedules(
        request.app.state.database, actor=actor, source_key=source_key,
        payload=payload, scope=scope,
    )


@router.post("/sources/{source_key}/official-rollout/backfills",
             response_model=OfficialBackfillRolloutView)
async def rollout_source_official_backfills(
    request: Request,
    source_key: str,
    payload: OfficialBackfillRolloutRequest,
) -> OfficialBackfillRolloutView:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    scope = build_scope_context(request.app.state.database, actor)
    return rollout_validated_store_backfills(
        request.app.state.database, actor=actor, source_key=source_key,
        payload=payload, scope=scope,
    )


@router.put("/sources/{source_key}/schedules/{schedule_id}", response_model=ScheduleView)
async def update_source_schedule(request: Request, source_key: str, schedule_id: str,
                                 payload: ScheduleRequest,
                                 version: int = Query(ge=1)) -> ScheduleView:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    row = save_schedule(request.app.state.database, actor=actor, source_key=source_key,
        payload=payload, schedule_id=schedule_id, expected_version=version,
        scope=build_scope_context(request.app.state.database, actor).snapshot())
    return ScheduleView.model_validate(row)


@router.get("/sources/{source_key}/backfills", response_model=list[BackfillView])
async def source_backfills(request: Request, source_key: str) -> list[BackfillView]:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    with request.app.state.database.session() as session:
        rows = session.scalars(select(SourceBackfillPlan).join(ExternalSystem).where(
            SourceBackfillPlan.enterprise_id == actor.enterprise_id,
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key).order_by(SourceBackfillPlan.created_at))
        return [BackfillView.model_validate(row) for row in rows]


@router.post("/sources/{source_key}/backfills", response_model=BackfillView, status_code=201)
async def create_source_backfill(request: Request, source_key: str,
                                 payload: BackfillRequest) -> BackfillView:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    row = save_backfill(request.app.state.database, actor=actor, source_key=source_key,
        payload=payload, scope=build_scope_context(request.app.state.database, actor).snapshot())
    return BackfillView.model_validate(row)


@router.put("/sources/{source_key}/backfills/{backfill_id}", response_model=BackfillView)
async def update_source_backfill(request: Request, source_key: str, backfill_id: str,
                                 payload: BackfillRequest,
                                 version: int = Query(ge=1)) -> BackfillView:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    row = save_backfill(request.app.state.database, actor=actor, source_key=source_key,
        payload=payload, backfill_id=backfill_id, expected_version=version,
        scope=build_scope_context(request.app.state.database, actor).snapshot())
    return BackfillView.model_validate(row)


@router.get("/sources/{source_key}/backfills/{backfill_id}/windows",
            response_model=CoverageWindowList)
async def source_backfill_windows(request: Request, source_key: str, backfill_id: str,
                                  offset: int = Query(default=0, ge=0),
                                  limit: int = Query(default=50, ge=1, le=200),
                                  ) -> CoverageWindowList:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    with request.app.state.database.session() as session:
        plan = session.scalar(select(SourceBackfillPlan).join(ExternalSystem).where(
            SourceBackfillPlan.id == backfill_id,
            SourceBackfillPlan.enterprise_id == actor.enterprise_id,
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key))
        if plan is None:
            raise ApiProblem(status_code=404, code="source.backfill_not_found",
                             message="历史回填计划不存在")
        query = select(SourceCoverageWindow).where(
            SourceCoverageWindow.backfill_plan_id == plan.id,
            SourceCoverageWindow.enterprise_id == actor.enterprise_id)
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(query.order_by(SourceCoverageWindow.window_start)
                               .offset(offset).limit(limit))
        return CoverageWindowList(items=[CoverageWindowView.model_validate(row) for row in rows],
                                  offset=offset, limit=limit, total=total)


def _check_lingxing_url(value: str) -> None:
    try:
        parsed = urlparse(value)
        invalid = (parsed.scheme != "https" or parsed.hostname != "openapi.lingxing.com"
                   or parsed.username or parsed.password or parsed.port
                   or parsed.path not in {"", "/"} or parsed.query or parsed.fragment)
    except ValueError:
        invalid = True
    if invalid:
        raise ApiProblem(status_code=422, code="source.host_blocked",
                         message="领星来源只允许官方 HTTPS Host")


@router.get("/sources", response_model=list[SourceRegistrationView])
async def list_sources(request: Request) -> list[SourceRegistrationView]:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key="source-list",
        scope_key="enterprise",
    )
    with request.app.state.database.session() as session:
        rows = session.scalars(
            select(ExternalSystem)
            .where(ExternalSystem.enterprise_id == actor.enterprise_id)
            .order_by(ExternalSystem.system_key)
        )
        return [SourceRegistrationView.model_validate(row, from_attributes=True) for row in rows]


@router.post("/sources/{source_key}/bindings", response_model=SourceBindingView, status_code=201)
async def create_source_binding(
    request: Request, source_key: str, payload: SourceBindingRequest
) -> SourceBindingView:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key=source_key,
        scope_key="enterprise",
    )
    with request.app.state.database.session() as session:
        source = session.scalar(
            select(ExternalSystem).where(
                ExternalSystem.enterprise_id == actor.enterprise_id,
                ExternalSystem.system_key == source_key,
            )
        )
        unit = session.scalar(
            select(BusinessUnit).where(
                BusinessUnit.id == payload.business_unit_id,
                BusinessUnit.enterprise_id == actor.enterprise_id,
            )
        )
        if source is None or unit is None:
            raise ApiProblem(
                status_code=404,
                code="source.binding_scope_not_found",
                message="来源或业务单元不存在",
            )
        now = datetime.now(UTC)
        binding = SourceBinding(
            id=f"binding_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            business_unit_id=unit.id,
            source_system_id=source.id,
            external_key=payload.external_key,
            canonical_type=payload.canonical_type,
            canonical_id=payload.canonical_id,
            mapping_version=payload.mapping_version,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        session.add(binding)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ApiProblem(
                status_code=409,
                code="source.binding_conflict",
                message="来源范围映射已存在",
            ) from exc
        return SourceBindingView.model_validate(binding, from_attributes=True)


@router.get("/sources/{source_key}/bindings", response_model=list[SourceBindingView])
async def list_source_bindings(request: Request, source_key: str) -> list[SourceBindingView]:
    actor = _authorize(
        request, "source.manage", resource_type="source", resource_key=source_key,
        scope_key="enterprise",
    )
    with request.app.state.database.session() as session:
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key,
        ))
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        rows = session.scalars(select(SourceBinding).where(
            SourceBinding.enterprise_id == actor.enterprise_id,
            SourceBinding.source_system_id == source.id,
        ).order_by(SourceBinding.external_key))
        return [SourceBindingView.model_validate(row, from_attributes=True) for row in rows]


@router.get(
    "/sources/{source_key}/binding-page", response_model=SourceBindingListResponse
)
async def source_binding_page(
    request: Request,
    source_key: str,
    canonical_type: str | None = Query(default=None, max_length=64),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    suggestion_only: bool = False,
    query: str | None = Query(default=None, max_length=120),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> SourceBindingListResponse:
    actor = _authorize(
        request, "source.manage", resource_type="source", resource_key=source_key,
        scope_key="enterprise",
    )
    if status_filter is not None and status_filter not in {"pending", "approved", "rejected"}:
        raise ApiProblem(status_code=422, code="source.binding_status_invalid",
                         message="来源归属状态无效")
    with request.app.state.database.session() as session:
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key,
        ))
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        filters = [SourceBinding.enterprise_id == actor.enterprise_id,
                   SourceBinding.source_system_id == source.id]
        if canonical_type:
            filters.append(SourceBinding.canonical_type == canonical_type)
        if status_filter:
            filters.append(SourceBinding.status == status_filter)
        if suggestion_only:
            filters.append(SourceBinding.suggested_business_unit_id.is_not(None))
        if query and query.strip():
            filters.append(SourceBinding.external_key.ilike(f"%{query.strip()}%"))
        total = session.scalar(select(func.count(SourceBinding.id)).where(*filters)) or 0
        rows = session.scalars(select(SourceBinding).where(*filters).order_by(
            SourceBinding.status, SourceBinding.suggested_business_unit_id.desc(),
            SourceBinding.external_key).offset(offset).limit(limit)).all()
        return SourceBindingListResponse(
            page=PageView(offset=offset, limit=limit, total=total),
            items=[SourceBindingView.model_validate(row, from_attributes=True) for row in rows],
        )


@router.patch(
    "/sources/{source_key}/bindings/{binding_id}", response_model=SourceBindingView
)
async def review_source_binding(
    request: Request,
    source_key: str,
    binding_id: str,
    payload: SourceBindingReviewRequest,
) -> SourceBindingView:
    actor = _authorize(
        request, "source.manage", resource_type="source", resource_key=source_key,
        scope_key="enterprise",
    )
    context = build_scope_context(request.app.state.database, actor)
    if payload.business_unit_id and payload.business_unit_id not in context.business_unit_ids:
        raise ApiProblem(status_code=403, code="source.binding_scope_denied",
                         message="业务单元不在当前范围内")
    binding = review_binding(
        request.app.state.database, enterprise_id=actor.enterprise_id, source_key=source_key,
        binding_id=binding_id, principal_id=actor.principal_id, **payload.model_dump(),
    )
    return SourceBindingView.model_validate(binding, from_attributes=True)


@router.post(
    "/sources", response_model=SourceRegistrationView, status_code=status.HTTP_201_CREATED
)
async def register_source(
    request: Request, payload: SourceRegistrationRequest
) -> SourceRegistrationView:
    if payload.provider_key == "lingxing" or payload.system_type == "lingxing":
        _check_lingxing_url(payload.base_url)
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key="source-registration",
        scope_key="enterprise",
    )
    with request.app.state.database.session() as session:
        business_unit = None
        if payload.business_unit_id:
            business_unit = session.scalar(
                select(BusinessUnit).where(
                    BusinessUnit.id == payload.business_unit_id,
                    BusinessUnit.enterprise_id == actor.enterprise_id,
                )
            )
            if business_unit is None:
                raise ApiProblem(
                    status_code=422,
                    code="source.business_unit_scope_invalid",
                    message="业务单元不属于当前法人",
                )
        existing = session.scalar(
            select(ExternalSystem).where(
                ExternalSystem.enterprise_id == actor.enterprise_id,
                ExternalSystem.system_key == payload.system_key,
            )
        )
        if existing is not None:
            raise ApiProblem(status_code=409, code="source.already_exists", message="数据源已存在")
        source = ExternalSystem(
            id=f"src_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            business_unit_id=payload.business_unit_id,
            system_key=payload.system_key,
            name=payload.name,
            system_type=payload.system_type,
            base_url=payload.base_url,
            provider_key=payload.provider_key,
            credential_ref=payload.credential_ref,
            access_mode="read_only",
            status="configured",
            version=1,
            created_at=datetime.now(UTC),
        )
        session.add(source)
        session.flush()
        session.add_all(
            [
                SourceResource(
                    id=f"res_{uuid4().hex}",
                    external_system_id=source.id,
                    resource_key=item.key,
                    method=item.method,
                    path=item.path,
                    schema_status=item.schema_status,
                    enabled=item.schema_status == "confirmed",
                    display_name=item.key,
                    version="1",
                )
                for item in RESOURCE_CATALOG
            ]
        )
        session.commit()
        return SourceRegistrationView.model_validate(source, from_attributes=True)


@router.patch("/sources/{source_key}", response_model=SourceRegistrationView)
async def update_source(
    request: Request, source_key: str, payload: SourceUpdateRequest
) -> SourceRegistrationView:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key=source_key,
        scope_key="enterprise",
    )
    with request.app.state.database.session() as session:
        source = session.scalar(
            select(ExternalSystem).where(
                ExternalSystem.enterprise_id == actor.enterprise_id,
                ExternalSystem.system_key == source_key,
            ).with_for_update()
        )
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        if source.version != payload.expected_version:
            raise ApiProblem(status_code=409, code="source.version_conflict",
                             message="来源配置已更新，请刷新后重试")
        if payload.name is not None:
            source.name = payload.name
        if "business_unit_id" in payload.model_fields_set:
            if payload.business_unit_id is not None:
                business_unit = session.scalar(select(BusinessUnit).where(
                    BusinessUnit.id == payload.business_unit_id,
                    BusinessUnit.enterprise_id == actor.enterprise_id,
                ))
                if business_unit is None:
                    raise ApiProblem(
                        status_code=422,
                        code="source.business_unit_scope_invalid",
                        message="业务单元不属于当前法人",
                    )
            source.business_unit_id = payload.business_unit_id
        if payload.base_url is not None:
            if source.provider_key == "lingxing" or source.system_type == "lingxing":
                _check_lingxing_url(payload.base_url)
            source.base_url = payload.base_url
        if payload.status is not None:
            if payload.status not in {"configured", "disabled"}:
                raise ApiProblem(
                    status_code=422, code="source.status_invalid", message="来源状态无效"
                )
            source.status = payload.status
            source.disabled_at = datetime.now(UTC) if payload.status == "disabled" else None
        if payload.credential_ref is not None:
            source.credential_ref = payload.credential_ref
        source.updated_at = datetime.now(UTC)
        source.version += 1
        session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=actor.enterprise_id,
            event_type="source.configuration_updated", severity="info", title="来源配置已更新",
            detail=f"source_id={source.id}; version={source.version}; "
                   f"principal_id={actor.principal_id}", occurred_at=source.updated_at))
        session.commit()
        return SourceRegistrationView.model_validate(source, from_attributes=True)


@router.post("/sources/{source_key}/probe", response_model=SourceProbeView)
async def probe_source(request: Request, source_key: str) -> SourceProbeView:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key=source_key,
        scope_key="enterprise",
    )
    try:
        enqueue_sync(
            request.app.state.database, enterprise_id=actor.enterprise_id,
            source_key=source_key, initiator_id=actor.principal_id,
            request_id=getattr(request.state, "request_id", "probe-request"),
            payload=SyncRequest(resource_key="shops"), probe=True,
            provider_enabled=request.app.state.settings.lingxing_enabled,
            actor_snapshot=actor.snapshot(),
            scope_snapshot=build_scope_context(request.app.state.database, actor).snapshot(),
        )
    except LookupError as exc:
        raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在") from exc
    return SourceProbeView(
        source_key=source_key,
        status="queued",
        read_only=True,
        reachable=False,
        detail="已排队",
    )


@router.post("/sources/{source_key}/resources/{resource_key}/validate",
             response_model=SyncResponse, status_code=202)
async def validate_source_resource(request: Request, source_key: str, resource_key: str,
                                   payload: SourceResourceValidationRequest) -> SyncResponse:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    try:
        run = enqueue_sync(request.app.state.database, enterprise_id=actor.enterprise_id,
            source_key=SOURCE_KEY_ALIASES.get(source_key, source_key),
            initiator_id=actor.principal_id,
            request_id=getattr(request.state, "request_id", "resource-validation"),
            payload=SyncRequest(projection_mode="deferred",
                client_request_key=f"validate-{resource_key}-{uuid4().hex}",
                resource_key=resource_key,
                resource_parameters=payload.resource_parameters,
                window_start=payload.window_start, window_end=payload.window_end),
            probe=True, provider_enabled=request.app.state.settings.lingxing_enabled,
            actor_snapshot=actor.snapshot(),
            scope_snapshot=build_scope_context(request.app.state.database, actor).snapshot())
    except LookupError as exc:
        raise ApiProblem(status_code=404, code="source.not_found",
                         message="数据源不存在") from exc
    return SyncResponse(run=_run_view(run))


@router.get("/sources/{source_key}/resources", response_model=SourceResourceListResponse)
async def source_resources(request: Request, source_key: str) -> SourceResourceListResponse:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key=source_key,
        scope_key="enterprise",
    )
    with request.app.state.database.session() as session:
        source = session.scalar(
            select(ExternalSystem).where(
                ExternalSystem.enterprise_id == actor.enterprise_id,
                ExternalSystem.system_key == source_key,
            )
        )
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        registered = {
            row.resource_key: row
            for row in session.scalars(
                select(SourceResource).where(SourceResource.external_system_id == source.id)
            )
        }
        enabled = {key: row.enabled for key, row in registered.items()}
        explicit_keys = {item.key for item in RESOURCE_CATALOG}
        catalog_items = [*RESOURCE_CATALOG, *(spec for key in registered
            if key not in explicit_keys and (spec := resource_spec(key)) is not None)]
        schemas = {
            item.key: effective_schema_status(
                item, registered[item.key].schema_status if item.key in registered else None
            )
            for item in catalog_items
        }
    return SourceResourceListResponse(
        catalog_version=CATALOG_VERSION,
        provider_enabled=request.app.state.settings.lingxing_enabled,
        items=[
            SourceResourceView(
                key=item.key,
                method=item.method,
                path=item.path,
                required_parameters=list(item.required_parameters),
                schedule_parameters=list(partition_parameter_names(item)),
                window_fields=list(item.window_fields),
                window_format=item.window_format,
                max_window_days=item.max_window_days,
                retention_days=item.retention_days,
                execution_mode=item.execution_mode,
                schedule_strategy=schedule_strategy(item.key),
                fact_family=item.mapping_key
                if item.mapping_key in {"orders", "after_sales", "inventory", "fulfillments"}
                else None,
                wave=item.wave,
                status="disabled" if not enabled.get(item.key, False) else schemas[item.key],
                schema_status=schemas[item.key],
                schema_confirmation_available=(
                    can_project_to_core(item) and schemas[item.key] != "confirmed"
                ),
                enabled=enabled.get(item.key, False),
                read_only=True,
                projectable=(
                    can_project_to_core(item)
                    and enabled.get(item.key, False)
                    and schemas[item.key] == "confirmed"
                ),
                can_execute=(
                    request.app.state.settings.lingxing_enabled
                    and source.status != "disabled"
                    and enabled.get(item.key, False)
                ),
                validation_status=(registered[item.key].validation_status
                                   if item.key in registered else "unregistered"),
                validation_run_id=(registered[item.key].validation_run_id
                                   if item.key in registered else None),
                validation_error_code=(registered[item.key].validation_error_code
                                        if item.key in registered else None),
                last_validated_at=(registered[item.key].last_validated_at
                                   if item.key in registered else None),
            )
            for item in catalog_items
        ],
    )


@router.get(
    "/sources/{source_key}/official-operations",
    response_model=LingxingOfficialOperationListResponse,
)
async def lingxing_official_operations(
    request: Request,
    source_key: str,
    execution_status: str | None = Query(default=None, max_length=32),
    wave: str | None = Query(default=None, max_length=2),
    query: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> LingxingOfficialOperationListResponse:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key=source_key,
        scope_key="enterprise",
    )
    if execution_status not in {
        None, "metadata_only", "runtime_raw_only", "runtime_projectable"
    }:
        raise ApiProblem(
            status_code=422,
            code="source.operation_status_invalid",
            message="官方操作执行状态无效",
        )
    if wave not in {None, *(f"W{index}" for index in range(9))}:
        raise ApiProblem(
            status_code=422, code="source.operation_wave_invalid", message="资源波次无效"
        )
    with request.app.state.database.session() as session:
        source = session.scalar(
            select(ExternalSystem).where(
                ExternalSystem.enterprise_id == actor.enterprise_id,
                ExternalSystem.system_key == source_key,
            )
        )
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        if source.system_type != "lingxing":
            raise ApiProblem(
                status_code=422,
                code="source.provider_unsupported",
                message="该数据源不使用领星官方资源目录",
            )
        registered = {
            row.resource_key: row.enabled
            for row in session.scalars(
                select(SourceResource).where(SourceResource.external_system_id == source.id)
            )
        }
    def execution(item: OfficialOperation) -> Literal[
        "metadata_only", "runtime_raw_only", "runtime_projectable"
    ]:
        current = item.execution_status
        return (current if current != "metadata_only" else
                "runtime_raw_only" if official_raw_spec(item.id) else
                "metadata_only")

    needle = query.strip().casefold() if query else None
    filtered = [
        item
        for item in official_operations()
        if (execution_status is None or execution(item) == execution_status)
        and (wave is None or item.wave == wave)
        and (
            needle is None
            or needle in item.title.casefold()
            or needle in item.document_path.casefold()
            or needle in item.path.casefold()
        )
    ]
    page_items = filtered[offset : offset + limit]
    source_executable = (
        request.app.state.settings.lingxing_enabled and source.status != "disabled"
    )
    summary = registry_summary()
    all_operations = official_operations()
    derived_statuses = [execution(item) for item in all_operations]
    extraction_statuses = contract_summary().get("extraction_statuses")
    confirmed_contracts = (
        extraction_statuses.get("confirmed", 0)
        if isinstance(extraction_statuses, dict)
        else 0
    )
    summary.update({
        "runtime_operations": sum(value != "metadata_only" for value in derived_statuses),
        "runtime_resources": len(RESOURCE_CATALOG) + len(OFFICIAL_RAW_SPECS),
        "metadata_only_operations": derived_statuses.count("metadata_only"),
        "runtime_raw_only_operations": derived_statuses.count("runtime_raw_only"),
        "runtime_projectable_operations": derived_statuses.count("runtime_projectable"),
        "official_contract_version": OFFICIAL_CONTRACT_VERSION,
        "official_contracts_confirmed": confirmed_contracts,
    })
    summary["source_enabled_runtime_resources"] = sum(
        1 for key, enabled in registered.items() if enabled and resource_spec(key) is not None
    )
    return LingxingOfficialOperationListResponse(
        registry_version=OFFICIAL_REGISTRY_VERSION,
        source="https://apidoc.lingxing.com/_sidebar.md",
        summary=summary,
        page=PageView(offset=offset, limit=limit, total=len(filtered)),
        items=[
            LingxingOfficialOperationView(
                id=item.id,
                title=item.title,
                document_path=item.document_path,
                documentation_url=item.documentation_url,
                method=item.method,
                path=item.path,
                wave=item.wave,
                review_status=item.review_status,
                execution_status=execution(item),
                schema_status=("confirmed" if official_raw_spec(item.id) is not None
                               else item.schema_status),
                resource_keys=(list(item.resource_keys) if item.resource_keys else
                               [spec.key] if (spec := official_raw_spec(item.id)) is not None
                               else []),
                document_sha256=item.document_sha256,
                can_execute=bool(
                    source_executable
                    and execution(item) != "metadata_only"
                    and any(registered.get(key, False) for key in (
                        item.resource_keys or ((spec.key,) if spec is not None else ())))
                ),
                contract_status=(contract.extraction_status if (
                    contract := official_contract(item.id)) is not None else "schema_pending"),
                required_fields=list(contract.required_fields) if contract else [],
                scope_fields=list(contract.scope_fields) if contract else [],
                pagination_mode=contract.pagination_mode if contract else "none",
                window_fields=list(contract.window_fields) if contract else [],
                raw_eligible=spec is not None or item.execution_status != "metadata_only",
                registered=any(key in registered for key in (
                    item.resource_keys or ((spec.key,) if spec is not None else ()))),
            )
            for item in page_items
        ],
    )


@router.put("/sources/{source_key}/official-operations/{operation_id}/resource",
            response_model=SourceResourceView)
async def activate_official_resource(request: Request, source_key: str, operation_id: str,
                                     payload: OfficialResourceActivationRequest,
                                     ) -> SourceResourceView:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    catalog_item = official_raw_spec(operation_id)
    if catalog_item is None:
        raise ApiProblem(status_code=422, code="source.official_resource_not_eligible",
                         message="官方接口尚不具备受控 Raw 采集条件")
    contract_version = resource_contract_version(catalog_item)
    with request.app.state.database.session() as session:
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key).with_for_update())
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        resource = session.scalar(select(SourceResource).where(
            SourceResource.external_system_id == source.id,
            SourceResource.resource_key == catalog_item.key))
        now = datetime.now(UTC)
        if resource is None:
            resource = SourceResource(id=f"res_{uuid4().hex}", external_system_id=source.id,
                resource_key=catalog_item.key, method=catalog_item.method, path=catalog_item.path,
                schema_status="confirmed", enabled=payload.enabled,
                display_name=catalog_item.key, version=contract_version, updated_at=now)
            session.add(resource)
        else:
            if resource.method != catalog_item.method or resource.path != catalog_item.path:
                raise ApiProblem(status_code=409, code="source.official_resource_changed",
                                 message="已登记资源与当前官方契约不一致")
            if resource.version != contract_version:
                resource.validation_status, resource.validation_run_id = "unvalidated", None
                resource.validation_error_code, resource.last_validated_at = None, None
            resource.enabled, resource.schema_status = payload.enabled, "confirmed"
            resource.version, resource.updated_at = contract_version, now
        session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=actor.enterprise_id,
            event_type="source.official_resource_activated", severity="info",
            title="官方只读资源已登记", detail=f"resource={catalog_item.key}; "
            f"enabled={payload.enabled}; contract={OFFICIAL_CONTRACT_VERSION}; "
            f"principal={actor.principal_id}", occurred_at=now))
        session.commit()
        return SourceResourceView(key=resource.resource_key, method=resource.method,
            path=resource.path, required_parameters=list(catalog_item.required_parameters),
            schedule_parameters=list(partition_parameter_names(catalog_item)),
            window_fields=list(catalog_item.window_fields),
            window_format=catalog_item.window_format,
            max_window_days=catalog_item.max_window_days,
            retention_days=catalog_item.retention_days,
            execution_mode=catalog_item.execution_mode,
            schedule_strategy=schedule_strategy(catalog_item.key), fact_family=None,
            wave=catalog_item.wave, status="confirmed" if resource.enabled else "disabled",
            schema_status="confirmed", schema_confirmation_available=False,
            enabled=resource.enabled, read_only=True, projectable=False,
            can_execute=(request.app.state.settings.lingxing_enabled
                         and source.status != "disabled" and resource.enabled),
            validation_status=resource.validation_status,
            validation_run_id=resource.validation_run_id,
            validation_error_code=resource.validation_error_code,
            last_validated_at=resource.last_validated_at)


@router.put("/sources/{source_key}/official-resources/materialize",
            response_model=OfficialResourceMaterializationResponse)
async def materialize_official_resources(
    request: Request, source_key: str,
) -> OfficialResourceMaterializationResponse:
    actor = _authorize(request, "source.manage", resource_type="source",
                       resource_key=source_key, scope_key="enterprise")
    with request.app.state.database.session() as session:
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == source_key).with_for_update())
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        if source.system_type != "lingxing":
            raise ApiProblem(status_code=422, code="source.provider_unsupported",
                             message="该数据源不使用领星官方资源目录")
        existing_rows = {row.resource_key: row for row in session.scalars(
            select(SourceResource).where(SourceResource.external_system_id == source.id))}
        now = datetime.now(UTC)
        eligible_keys = {item.key for item in OFFICIAL_RAW_SPECS}
        contract_versions = {
            item.key: resource_contract_version(item) for item in OFFICIAL_RAW_SPECS
        }
        retired_resources = [row for key, row in existing_rows.items()
                             if key.startswith("official_") and key not in eligible_keys]
        retired_keys = [row.resource_key for row in retired_resources]
        changed_keys = [item.key for item in OFFICIAL_RAW_SPECS
                        if (row := existing_rows.get(item.key)) is not None
                        and row.version != contract_versions[item.key]]
        affected_keys = [*retired_keys, *changed_keys]
        affected_ids = [existing_rows[key].id for key in affected_keys]
        if affected_ids:
            active_resource_runs = session.scalar(select(func.count()).select_from(
                SyncResourceRun).where(
                    SyncResourceRun.source_resource_id.in_(affected_ids),
                    SyncResourceRun.status.in_(["queued", "running"]))) or 0
            active_schedules = session.scalar(select(func.count()).select_from(
                SourceSyncSchedule).where(
                    SourceSyncSchedule.external_system_id == source.id,
                    SourceSyncSchedule.resource_key.in_(affected_keys),
                    SourceSyncSchedule.active_run_id.is_not(None))) or 0
            active_backfills = session.scalar(select(func.count()).select_from(
                SourceBackfillPlan).where(
                    SourceBackfillPlan.external_system_id == source.id,
                    SourceBackfillPlan.resource_key.in_(affected_keys),
                    SourceBackfillPlan.active_run_id.is_not(None))) or 0
            if active_resource_runs or active_schedules or active_backfills:
                raise ApiProblem(
                    status_code=409,
                    code="source.official_resource_transition_busy",
                    message="存在使用旧资源契约的活动任务，请先完成或取消后再更新目录",
                )
        for resource in retired_resources:
            resource.enabled = False
            resource.schema_status = "schema_pending"
            resource.validation_status = "needs_attention"
            resource.validation_error_code = "source.read_only_review_blocked"
            resource.updated_at = now
        if retired_keys:
            for schedule in session.scalars(select(SourceSyncSchedule).where(
                    SourceSyncSchedule.external_system_id == source.id,
                    SourceSyncSchedule.resource_key.in_(retired_keys))):
                schedule.status = "needs_attention" if schedule.active_run_id else "paused"
                schedule.error_code = "source.read_only_review_blocked"
                schedule.updated_at = now
                schedule.version += 1
            for backfill in session.scalars(select(SourceBackfillPlan).where(
                    SourceBackfillPlan.external_system_id == source.id,
                    SourceBackfillPlan.resource_key.in_(retired_keys),
                    SourceBackfillPlan.status.not_in(["completed", "cancelled"]))):
                backfill.status = "needs_attention"
                backfill.error_code = "source.read_only_review_blocked"
                backfill.updated_at = now
                backfill.version += 1
        if changed_keys:
            for schedule in session.scalars(select(SourceSyncSchedule).where(
                    SourceSyncSchedule.external_system_id == source.id,
                    SourceSyncSchedule.resource_key.in_(changed_keys))):
                schedule.status = "paused"
                schedule.error_code = "source.resource_contract_changed"
                schedule.updated_at = now
                schedule.version += 1
            for backfill in session.scalars(select(SourceBackfillPlan).where(
                    SourceBackfillPlan.external_system_id == source.id,
                    SourceBackfillPlan.resource_key.in_(changed_keys),
                    SourceBackfillPlan.status.not_in(["completed", "cancelled"]))):
                backfill.status = "paused"
                backfill.error_code = "source.resource_contract_changed"
                backfill.updated_at = now
                backfill.version += 1
        created = 0
        for catalog_item in OFFICIAL_RAW_SPECS:
            contract_version = contract_versions[catalog_item.key]
            resource = existing_rows.get(catalog_item.key)
            if resource is None:
                resource = SourceResource(id=f"res_{uuid4().hex}",
                    external_system_id=source.id, resource_key=catalog_item.key,
                    method=catalog_item.method, path=catalog_item.path,
                    schema_status="confirmed", enabled=False,
                    display_name=catalog_item.key, version=contract_version,
                    updated_at=now)
                session.add(resource)
                existing_rows[catalog_item.key] = resource
                created += 1
            elif resource.method != catalog_item.method or resource.path != catalog_item.path:
                raise ApiProblem(status_code=409, code="source.official_resource_changed",
                                 message="已登记资源与当前官方契约不一致")
            else:
                if resource.version != contract_version:
                    resource.enabled = False
                    resource.validation_status, resource.validation_run_id = "unvalidated", None
                    resource.validation_error_code, resource.last_validated_at = None, None
                resource.schema_status = "confirmed"
                resource.version = contract_version
                resource.updated_at = now
        session.add(PlatformEvent(id=f"event_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            event_type="source.official_resources_materialized", severity="info",
            title="官方只读资源目录已登记",
            detail=f"source_id={source.id}; eligible={len(OFFICIAL_RAW_SPECS)}; "
                   f"created={created}; retired={len(retired_resources)}; "
                   f"contract={OFFICIAL_CONTRACT_VERSION}; "
                   f"principal={actor.principal_id}", occurred_at=now))
        session.commit()
        return OfficialResourceMaterializationResponse(
            eligible=len(OFFICIAL_RAW_SPECS), created=created,
            existing=len(OFFICIAL_RAW_SPECS) - created,
            enabled=sum(bool(existing_rows[item.key].enabled) for item in OFFICIAL_RAW_SPECS),
            retired=len(retired_resources),
            contract_version=OFFICIAL_CONTRACT_VERSION)


@router.patch(
    "/sources/{source_key}/resources/{resource_key}",
    response_model=SourceResourceView,
)
async def update_source_resource(
    request: Request,
    source_key: str,
    resource_key: str,
    payload: SourceResourceUpdateRequest,
) -> SourceResourceView:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key=source_key,
        scope_key="enterprise",
    )
    catalog_item = resource_spec(resource_key)
    if catalog_item is None:
        raise ApiProblem(
            status_code=404, code="source.resource_not_found", message="来源资源不存在"
        )
    if payload.confirm_catalog_version is not None and (
        payload.confirm_catalog_version != CATALOG_VERSION or not can_project_to_core(catalog_item)
    ):
        raise ApiProblem(status_code=409, code="source.schema_confirmation_unavailable",
                         message="目录版本已变化或规范映射尚未确认")
    with request.app.state.database.session() as session:
        source = session.scalar(
            select(ExternalSystem).where(
                ExternalSystem.enterprise_id == actor.enterprise_id,
                ExternalSystem.system_key == source_key,
            )
        )
        if source is None:
            raise ApiProblem(status_code=404, code="source.not_found", message="数据源不存在")
        session.refresh(source, with_for_update=True)
        resource = session.scalar(
            select(SourceResource).where(
                SourceResource.external_system_id == source.id,
                SourceResource.resource_key == resource_key,
            )
        )
        if resource is None:
            resource = SourceResource(
                id=f"res_{uuid4().hex}",
                external_system_id=source.id,
                resource_key=resource_key,
                method=catalog_item.method,
                path=catalog_item.path,
                # A resource added after source registration must pass the same explicit
                # catalog-version confirmation as an existing pending resource.
                schema_status="schema_pending",
                enabled=payload.enabled,
            )
            session.add(resource)
        else:
            resource.enabled = payload.enabled
        if payload.confirm_catalog_version is not None and resource.schema_status != "confirmed":
            resource.schema_status = "confirmed"
            resource.version = CATALOG_VERSION
            resource.updated_at = datetime.now(UTC)
            session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=actor.enterprise_id,
                event_type="source.resource_schema_confirmed", severity="info",
                title="来源资源契约确认", detail=f"resource={resource_key}; "
                f"catalog={CATALOG_VERSION}; principal={actor.principal_id}",
                occurred_at=resource.updated_at))
        session.commit()
        schema_status = effective_schema_status(catalog_item, resource.schema_status)
        return SourceResourceView(
            key=resource.resource_key,
            method=resource.method,
            path=resource.path,
            required_parameters=list(catalog_item.required_parameters),
            schedule_parameters=list(partition_parameter_names(catalog_item)),
            window_fields=list(catalog_item.window_fields),
            window_format=catalog_item.window_format,
            max_window_days=catalog_item.max_window_days,
            retention_days=catalog_item.retention_days,
            execution_mode=catalog_item.execution_mode,
            schedule_strategy=schedule_strategy(catalog_item.key),
            fact_family=catalog_item.mapping_key if catalog_item.mapping_key in {
                "orders", "after_sales", "inventory", "fulfillments"} else None,
            wave=catalog_item.wave,
            status=("disabled" if not resource.enabled else schema_status),
            schema_status=schema_status,
            schema_confirmation_available=(can_project_to_core(catalog_item)
                                           and schema_status != "confirmed"),
            enabled=resource.enabled,
            read_only=True,
            projectable=(can_project_to_core(catalog_item) and resource.enabled
                         and schema_status == "confirmed"),
            can_execute=(request.app.state.settings.lingxing_enabled
                         and source.status != "disabled" and resource.enabled),
            validation_status=resource.validation_status,
            validation_run_id=resource.validation_run_id,
            validation_error_code=resource.validation_error_code,
            last_validated_at=resource.last_validated_at,
        )


def _mapping_conflict_view(
    conflict: MappingConflict, source: ExternalSystem
) -> MappingConflictView:
    resolution = conflict.resolution if isinstance(conflict.resolution, dict) else {}
    error_code = resolution.get("error_code")
    resolved_manifest_id = resolution.get("resolved_manifest_id")
    return MappingConflictView(
        id=conflict.id,
        source_key=source.system_key,
        external_object_key=conflict.external_object_key,
        status=conflict.status,
        candidates=conflict.candidates if isinstance(conflict.candidates, list) else [],
        reviewed_by=conflict.reviewed_by,
        reviewed_at=conflict.reviewed_at,
        resource_key=conflict.resource_key,
        raw_manifest_id=conflict.raw_manifest_id,
        error_code=error_code if isinstance(error_code, str) else None,
        resolved_manifest_id=(
            resolved_manifest_id if isinstance(resolved_manifest_id, str) else None
        ),
    )


@router.get("/mapping-conflicts", response_model=list[MappingConflictView])
async def mapping_conflicts(request: Request) -> list[MappingConflictView]:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="mapping-conflict",
        resource_key="mapping-conflict-list",
        scope_key="enterprise",
    )
    with request.app.state.database.session() as session:
        rows = session.execute(
            select(MappingConflict, ExternalSystem)
            .join(ExternalSystem, ExternalSystem.id == MappingConflict.external_system_id)
            .where(ExternalSystem.enterprise_id == actor.enterprise_id)
            .order_by(MappingConflict.status, MappingConflict.external_object_key)
        ).all()
    return [_mapping_conflict_view(conflict, source) for conflict, source in rows]


@router.get("/mapping-conflicts/page", response_model=MappingConflictListResponse)
async def mapping_conflict_page(
    request: Request,
    source_key: str | None = Query(default=None, max_length=80),
    resource_key: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    query: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> MappingConflictListResponse:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="mapping-conflict",
        resource_key="mapping-conflict-page",
        scope_key="enterprise",
    )
    conditions = [ExternalSystem.enterprise_id == actor.enterprise_id]
    if source_key:
        conditions.append(ExternalSystem.system_key == source_key)
    if resource_key:
        conditions.append(MappingConflict.resource_key == resource_key)
    if status_filter:
        conditions.append(MappingConflict.status == status_filter)
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        conditions.append(or_(
            MappingConflict.external_object_key.ilike(pattern),
            MappingConflict.resource_key.ilike(pattern),
        ))
    with request.app.state.database.session() as session:
        total = int(session.scalar(select(func.count(MappingConflict.id)).join(
            ExternalSystem, ExternalSystem.id == MappingConflict.external_system_id
        ).where(*conditions)) or 0)
        rows = session.execute(select(MappingConflict, ExternalSystem).join(
            ExternalSystem, ExternalSystem.id == MappingConflict.external_system_id
        ).where(*conditions).order_by(
            MappingConflict.status, MappingConflict.external_object_key, MappingConflict.id
        ).offset(offset).limit(limit)).all()
        status_rows = session.execute(select(
            MappingConflict.status, func.count(MappingConflict.id)
        ).join(ExternalSystem, ExternalSystem.id == MappingConflict.external_system_id).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            *(tuple([ExternalSystem.system_key == source_key]) if source_key else ()),
        ).group_by(MappingConflict.status)).all()
    return MappingConflictListResponse(
        page=PageView(offset=offset, limit=limit, total=total),
        status_counts={str(key): int(count) for key, count in status_rows},
        items=[_mapping_conflict_view(conflict, source) for conflict, source in rows],
    )


@router.patch(
    "/mapping-conflicts/{conflict_id}", response_model=MappingConflictView
)
async def review_mapping_conflict(
    request: Request,
    conflict_id: str,
    payload: MappingConflictReviewRequest,
) -> MappingConflictView:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="mapping-conflict",
        resource_key=conflict_id,
        scope_key="enterprise",
    )
    with request.app.state.database.session() as session:
        row = session.execute(
            select(MappingConflict, ExternalSystem)
            .join(ExternalSystem, ExternalSystem.id == MappingConflict.external_system_id)
            .where(
                MappingConflict.id == conflict_id,
                ExternalSystem.enterprise_id == actor.enterprise_id,
            )
            .with_for_update(of=MappingConflict)
        ).first()
        if row is None:
            raise ApiProblem(
                status_code=404, code="mapping_conflict.not_found", message="映射冲突不存在"
            )
        conflict, source = row
        if payload.expected_manifest_id != conflict.raw_manifest_id:
            raise ApiProblem(status_code=409, code="mapping_conflict.version_conflict",
                             message="冲突已更新，请刷新后重试")
        review_conflict(session, conflict, status=payload.status, principal_id=actor.principal_id)
        session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=source.enterprise_id,
            event_type="source.conflict_reviewed", severity="info", title="映射冲突审核",
            detail=f"conflict_id={conflict.id}; principal_id={actor.principal_id}; "
                   f"status={payload.status}", occurred_at=datetime.now(UTC)))
        session.commit()
        return _mapping_conflict_view(conflict, source)


@router.get("/authority-rules", response_model=list[SourceAuthorityRuleView])
async def authority_rules(request: Request) -> list[SourceAuthorityRuleView]:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="authority-rule",
        resource_key="authority-rule-list",
        scope_key="enterprise",
    )
    with request.app.state.database.session() as session:
        rows = session.scalars(
            select(SourceAuthorityRule)
            .where(SourceAuthorityRule.enterprise_id == actor.enterprise_id)
            .order_by(SourceAuthorityRule.fact_family)
        ).all()
    return [SourceAuthorityRuleView.model_validate(row, from_attributes=True) for row in rows]


@router.put("/authority-rules", response_model=SourceAuthorityRuleView, deprecated=True)
async def put_authority_rule(
    request: Request, payload: SourceAuthorityRuleRequest
) -> SourceAuthorityRuleView:
    _authorize(
        request,
        "source.manage",
        resource_type="authority-rule",
        resource_key=payload.fact_family,
        scope_key="enterprise",
    )
    raise ApiProblem(status_code=410, code="authority.project_assignment_required",
                     message="权威规则需要明确业务单元和来源实例")


@router.get(
    "/sources/{source_key}/checkpoints",
    response_model=SyncCheckpointListResponse,
)
async def source_checkpoints(
    request: Request,
    source_key: str,
    resource_key: str | None = Query(default=None, max_length=120),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    query: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> SyncCheckpointListResponse:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key=source_key,
        scope_key="enterprise",
    )
    conditions = ["s.system_key = :source_key", "s.enterprise_id = :enterprise_id"]
    parameters: dict[str, object] = {
        "source_key": source_key,
        "enterprise_id": actor.enterprise_id,
        "offset": offset,
        "limit": limit,
    }
    if resource_key:
        conditions.append("r.resource_key = :resource_key")
        parameters["resource_key"] = resource_key
    if status_filter:
        conditions.append("c.status = :status")
        parameters["status"] = status_filter
    if query and query.strip():
        conditions.append(
            "(LOWER(r.resource_key) LIKE LOWER(:query) "
            "OR LOWER(c.partition_key) LIKE LOWER(:query))"
        )
        parameters["query"] = f"%{query.strip()}%"
    where_clause = " AND ".join(conditions)
    with request.app.state.database.engine.connect() as connection:
        total = int(connection.execute(text(
            "SELECT COUNT(*) FROM sync_checkpoints c "
            "JOIN source_resources r ON r.id = c.source_resource_id "
            "JOIN external_systems s ON s.id = r.external_system_id "
            f"WHERE {where_clause}"
        ), parameters).scalar_one())
        rows = connection.execute(
            text(
                """SELECT r.resource_key, c.partition_key, c.cursor, c.status, c.updated_at,
                          (SELECT MAX(m.page_number) FROM raw_page_manifests m
                            WHERE m.sync_resource_run_id = (
                              SELECT cr.id FROM sync_resource_runs cr
                               WHERE cr.source_resource_id = r.id
                                 AND cr.partition_key = c.partition_key
                               ORDER BY cr.started_at DESC, cr.id DESC LIMIT 1
                            )) AS page_number,
                          (SELECT cr.records_read FROM sync_resource_runs cr
                            WHERE cr.source_resource_id = r.id
                              AND cr.partition_key = c.partition_key
                            ORDER BY cr.started_at DESC, cr.id DESC LIMIT 1) AS records_read
                     FROM sync_checkpoints c
                     JOIN source_resources r ON r.id = c.source_resource_id
                     JOIN external_systems s ON s.id = r.external_system_id
                    WHERE """ + where_clause + """
                    ORDER BY r.resource_key, c.partition_key
                    LIMIT :limit OFFSET :offset"""
            ),
            parameters,
        ).mappings()
        items = [
            SyncCheckpointView(
                resource_key=str(row["resource_key"]),
                partition_key=str(row["partition_key"]),
                cursor=row["cursor"],
                page_number=row["page_number"],
                records_read=row["records_read"],
                updated_at=row["updated_at"],
                status=row["status"],
            )
            for row in rows
        ]
    return SyncCheckpointListResponse(
        page=PageView(offset=offset, limit=limit, total=total), items=items
    )
def _authorize(
    request: Request,
    permission: str,
    *,
    resource_type: str,
    resource_key: str,
    scope_key: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
) -> ActorContext:
    actor = resolve_development_actor(request)
    if scope_key is not None and resource_type in {
        "metric.series", "commerce.fact", "customer.profile", "data-center.overview",
    }:
        require_selected_data_scope(request.app.state.database, actor, scope_key)
    if scope_key is not None:
        scope_type = "enterprise" if scope_key == "enterprise" else "store"
        scope_id = actor.enterprise_id if scope_key == "enterprise" else scope_key
    require_permission(
        actor,
        permission,
        request.app.state.database,
        resource_type=resource_type,
        resource_key=resource_key,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    return actor


@router.get("/overview", response_model=TwinOverviewResponse)
async def overview(request: Request) -> TwinOverviewResponse:
    actor = _authorize(
        request,
        "platform.navigation.read",
        resource_type="data-center.overview",
        resource_key="enterprise-operational-twin",
        scope_key="enterprise",
    )
    return build_overview(request.app.state.database, enterprise_id=actor.enterprise_id)


@router.get("/source-operations", response_model=SourceOperationsView)
async def source_operations_overview(request: Request) -> SourceOperationsView:
    actor = _authorize(request, "source.manage", resource_type="source.operations",
                       resource_key="overview", scope_key="enterprise")
    database = request.app.state.database
    return source_operations(database, actor.enterprise_id, build_scope_context(database, actor))


@router.get("/sync-runs", response_model=SyncRunListResponse)
async def sync_runs(
    request: Request,
    source_key: str | None = Query(default=None, max_length=80),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    query: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> SyncRunListResponse:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="data-center.sync-run",
        resource_key="sync-run-list",
        scope_key="enterprise",
    )
    return list_sync_runs(
        request.app.state.database,
        source_key=source_key,
        enterprise_id=actor.enterprise_id,
        status=status_filter,
        query=query,
        offset=offset,
        limit=limit,
    )


@router.get("/sync-runs/{run_id}/resources", response_model=list[dict[str, object]])
async def sync_run_resources(request: Request, run_id: str) -> list[dict[str, object]]:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="data-center.sync-run",
        resource_key=run_id,
        scope_key="enterprise",
    )
    with request.app.state.database.engine.connect() as connection:
        rows = connection.execute(
            text(
                """SELECT rr.id, r.resource_key, rr.partition_key, rr.status,
                          rr.records_read, rr.records_written, rr.error_code
                     FROM sync_resource_runs rr
                     JOIN sync_runs sr ON sr.id = rr.sync_run_id
                     JOIN source_resources r ON r.id = rr.source_resource_id
                    WHERE (rr.sync_run_id = :run_id OR sr.parent_run_id = :run_id)
                      AND sr.enterprise_id = :enterprise_id
                    ORDER BY r.resource_key, rr.partition_key"""
            ),
            {"run_id": run_id, "enterprise_id": actor.enterprise_id},
        ).mappings()
    return [dict(row) for row in rows]


@router.post("/sync-runs/{run_id}/cancel")
async def cancel_sync_run(request: Request, run_id: str) -> dict[str, object]:
    actor = _authorize(request, "source.manage", resource_type="data-center.sync-run",
                       resource_key=run_id, scope_key="enterprise")
    with request.app.state.database.session() as session:
        run = session.scalar(select(SyncRun).where(
            SyncRun.id == run_id, SyncRun.enterprise_id == actor.enterprise_id
        ))
        if run is None:
            raise ApiProblem(status_code=404, code="source.run_not_found", message="同步运行不存在")
        if run.status in {"succeeded", "failed", "cancelled", "partial_failed"}:
            return {"id": run.id, "status": run.status}
        cancel_import(request.app.state.database, session, run, principal_id=actor.principal_id)
        session.commit()
        return {"id": run.id, "status": run.status}


@router.get("/sync-runs/{run_id}/raw-manifests", response_model=list[dict[str, object]])
async def sync_run_raw_manifests(request: Request, run_id: str) -> list[dict[str, object]]:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="data-center.sync-run",
        resource_key=run_id,
        scope_key="enterprise",
    )
    with request.app.state.database.engine.connect() as connection:
        rows = connection.execute(
            text(
                """SELECT m.id, r.resource_key, rr.partition_key, m.storage_key,
                          m.content_hash, m.compression, m.bytes, m.row_count,
                          m.page_number, m.cursor, m.schema_status, m.fetched_at,
                          r.enabled AS resource_enabled, r.schema_status AS resource_schema,
                          es.status AS source_status, mp.schema_status AS mirror_schema_status
                     FROM raw_page_manifests m
                     JOIN sync_resource_runs rr ON rr.id = m.sync_resource_run_id
                     JOIN sync_runs sr ON sr.id = rr.sync_run_id
                     JOIN source_resources r ON r.id = rr.source_resource_id
                     JOIN external_systems es ON es.id = r.external_system_id
                     LEFT JOIN source_mirror_pages mp ON mp.raw_manifest_id = m.id
                    WHERE (rr.sync_run_id = :run_id OR sr.parent_run_id = :run_id)
                      AND sr.enterprise_id = :enterprise_id
                    ORDER BY m.id"""
            ),
            {"run_id": run_id, "enterprise_id": actor.enterprise_id},
        ).mappings().all()
    result = []
    for row in rows:
        item = dict(row)
        spec = resource_spec(str(item["resource_key"]))
        enabled = item.pop("resource_enabled")
        schema = item.pop("resource_schema")
        source_status = item.pop("source_status")
        mirror_schema = item.pop("mirror_schema_status")
        if mirror_schema in {"scope_invalid", "schema_invalid"}:
            item["schema_status"] = mirror_schema
        item["mapping_version"] = MAPPING_VERSION
        item["replay_eligible"] = bool(spec and can_project_to_core(spec) and enabled
            and schema == "confirmed" and source_status != "disabled" and item["fetched_at"]
            and mirror_schema not in {"scope_invalid", "schema_invalid"}
            and str(item["storage_key"]).endswith(".json.gz"))
        result.append(item)
    return result


@router.get("/entities", response_model=BusinessEntityListResponse)
async def entities(
    request: Request,
    entity_type: str | None = Query(default=None, max_length=80),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    query: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> BusinessEntityListResponse:
    actor = _authorize(
        request,
        "metric.definition.read",
        resource_type="data-center.business-entity",
        resource_key="business-entity-list",
        scope_key="enterprise",
    )
    return list_business_entities(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        entity_type=entity_type,
        status=status_filter,
        query=query,
        offset=offset,
        limit=limit,
    )


@router.get("/metrics", response_model=MetricCatalogResponse)
async def metrics(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    query: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> MetricCatalogResponse:
    actor = _authorize(
        request,
        "metric.definition.read",
        resource_type="metric.definition",
        resource_key="metric-catalog",
        scope_key="enterprise",
    )
    return list_metric_catalog(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        status=status_filter,
        query=query,
        offset=offset,
        limit=limit,
    )


@router.get("/metric-series", response_model=MetricSeriesResponse)
async def metric_series(
    request: Request,
    metric_keys: str = Query(min_length=1, max_length=1200),
    scope_key: str = Query(default="enterprise", min_length=1, max_length=160),
    days: int = Query(default=30, ge=1, le=365),
    as_of: datetime | None = None,
) -> MetricSeriesResponse:
    keys = [key.strip() for key in metric_keys.split(",") if key.strip()]
    if not keys or len(keys) > 20:
        raise ApiProblem(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="metric.query_invalid",
            message="metric_keys 必须包含 1 到 20 个指标键",
        )
    actor = _authorize(
        request,
        "metric.query.execute",
        resource_type="metric.series",
        resource_key=f"metric-series:{scope_key}",
        scope_key=scope_key,
    )
    return query_metric_series(
        request.app.state.database,
        metric_keys=keys,
        scope_key=scope_key,
        days=days,
        as_of=as_of,
        enterprise_id=actor.enterprise_id,
    )


@router.get("/quality", response_model=DataQualityResponse)
async def quality(
    request: Request,
    category: str | None = Query(default=None, max_length=48),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    query: str | None = Query(default=None, max_length=160),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> DataQualityResponse:
    actor = _authorize(
        request,
        "metric.definition.read",
        resource_type="data-center.quality",
        resource_key="data-quality-list",
        scope_key="enterprise",
    )
    return list_data_quality(
        request.app.state.database,
        enterprise_id=actor.enterprise_id,
        category=category,
        status=status_filter,
        query=query,
        offset=offset,
        limit=limit,
    )


@router.get("/commerce-operations", response_model=CommerceOperationsResponse)
async def commerce_operations(
    request: Request,
    scope_key: str = Query(default="enterprise", min_length=1, max_length=160),
) -> CommerceOperationsResponse:
    actor = _authorize(
        request,
        "metric.query.execute",
        resource_type="commerce.fact",
        resource_key=f"commerce-operations:{scope_key}",
        scope_key=scope_key,
    )
    return build_commerce_operations(
        request.app.state.database,
        scope_key=scope_key,
        enterprise_id=actor.enterprise_id,
    )


@router.get("/customer-360", response_model=Customer360Response)
async def customer_360(
    request: Request,
    scope_key: str = Query(default="enterprise", min_length=1, max_length=160),
    limit: int = Query(default=50, ge=1, le=100),
) -> Customer360Response:
    actor = _authorize(
        request,
        "customer.profile.read",
        resource_type="customer.profile",
        resource_key=f"customer-360:{scope_key}",
        scope_key=scope_key,
    )
    return build_customer_360(
        request.app.state.database,
        scope_key=scope_key,
        enterprise_id=actor.enterprise_id,
        limit=limit,
    )


@router.get("/customer-360/{customer_key}", response_model=CustomerDetailResponse)
async def customer_360_detail(
    request: Request,
    customer_key: str,
    scope_key: str = Query(default="enterprise", min_length=1, max_length=160),
    limit: int = Query(default=50, ge=1, le=100),
) -> CustomerDetailResponse:
    actor = _authorize(
        request,
        "customer.profile.read",
        resource_type="customer.profile",
        resource_key=f"customer:{scope_key}:{customer_key}",
        scope_key=scope_key,
    )
    return build_customer_detail(
        request.app.state.database,
        scope_key=scope_key,
        customer_key=customer_key,
        enterprise_id=actor.enterprise_id,
        limit=limit,
    )


@router.post("/sources/{source_key}/sync", response_model=SyncResponse)
async def sync_source(
    request: Request,
    source_key: str,
    payload: SyncRequest,
) -> SyncResponse:
    actor = _authorize(
        request,
        "source.manage",
        resource_type="source",
        resource_key=source_key,
        scope_key="enterprise",
    )
    try:
        run = enqueue_sync(
            request.app.state.database, enterprise_id=actor.enterprise_id,
            source_key=SOURCE_KEY_ALIASES.get(source_key, source_key),
            initiator_id=actor.principal_id,
            request_id=getattr(request.state, "request_id", "sync-request"), payload=payload,
            provider_enabled=request.app.state.settings.lingxing_enabled,
            actor_snapshot=actor.snapshot(),
            scope_snapshot=build_scope_context(
                request.app.state.database, actor
            ).snapshot(),
        )
    except LookupError as exc:
        raise ApiProblem(
            status_code=status.HTTP_404_NOT_FOUND,
            code="source.not_found",
            message=str(exc),
        ) from exc
    if run.status == "failed":
        raise ApiProblem(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="source.sync_failed",
            message=run.error or "数据源同步失败",
            retryable=True,
            details={"sync_run_id": run.id},
        )
    return SyncResponse(run=_run_view(run))


@router.post(
    "/meetings/{meeting_key}/actions",
    response_model=MeetingActionResponse,
)
async def meeting_action(
    request: Request,
    meeting_key: str,
    payload: MeetingActionRequest,
) -> MeetingActionResponse:
    _authorize(
        request,
        "platform.navigation.read",
        resource_type="data-center.overview",
        resource_key="enterprise-operational-twin",
        scope_key="enterprise",
    )
    actor = _authorize(
        request,
        "meeting.start",
        resource_type="meeting.scene",
        resource_key=meeting_key,
        scope_type="object",
        scope_id=meeting_key,
    )
    try:
        meeting = advance_meeting(
            request.app.state.database,
            meeting_key,
            payload.action,
            request.app.state.settings.meeting_auto_start_seconds,
            enterprise_id=actor.enterprise_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return MeetingActionResponse(
        meeting=meeting,
        overview=build_overview(
            request.app.state.database,
            enterprise_id=actor.enterprise_id,
        ),
    )
