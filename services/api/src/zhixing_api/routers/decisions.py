from fastapi import APIRouter, HTTPException, Request, status

from zhixing_api.action_service import confirm_meeting_decision
from zhixing_api.actor_context import require_permission, resolve_development_actor
from zhixing_api.decision_schemas import (
    DigitalMeetingDetailResponse,
    MeetingConfirmRequest,
    MeetingConfirmResponse,
    MeetingCreateRequest,
    MeetingCreateResponse,
    MeetingListResponse,
    MeetingRunRequest,
    MeetingRunResponse,
    RoleTwinCatalogResponse,
)
from zhixing_api.decision_service import (
    create_digital_meeting,
    get_meeting_detail,
    get_meeting_scope,
    list_meetings,
    list_role_twins,
    run_digital_meeting,
)
from zhixing_api.workspace_service import resolve_workspace_for_actor

router = APIRouter(prefix="/api/v1", tags=["role-twin", "digital-meeting"])


@router.get("/twins", response_model=RoleTwinCatalogResponse)
async def role_twins(request: Request) -> RoleTwinCatalogResponse:
    actor = resolve_development_actor(request)
    return list_role_twins(request.app.state.database, actor.enterprise_id)


@router.get("/decision-meetings", response_model=MeetingListResponse)
async def decision_meetings(request: Request) -> MeetingListResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "meeting.read",
        request.app.state.database,
        resource_type="meeting-catalog",
        resource_key=actor.enterprise_id,
    )
    return list_meetings(request.app.state.database, actor)


@router.post("/decision-meetings", response_model=MeetingCreateResponse)
async def create_meeting(
    request: Request,
    payload: MeetingCreateRequest,
) -> MeetingCreateResponse:
    actor = resolve_development_actor(request)
    resolve_workspace_for_actor(actor, payload.workspace_key)
    scope_id = actor.enterprise_id if payload.scope_type == "enterprise" else payload.scope_key
    require_permission(
        actor,
        "meeting.start",
        request.app.state.database,
        resource_type="meeting",
        resource_key=payload.client_request_key,
        scope_type=payload.scope_type,
        scope_id=scope_id,
    )
    return create_digital_meeting(request.app.state.database, actor, payload)


@router.get(
    "/decision-meetings/{meeting_key}",
    response_model=DigitalMeetingDetailResponse,
)
async def decision_meeting(
    request: Request,
    meeting_key: str,
) -> DigitalMeetingDetailResponse:
    actor = resolve_development_actor(request)
    try:
        scope_type, scope_key = get_meeting_scope(
            request.app.state.database, meeting_key, actor.enterprise_id
        )
        require_permission(
            actor,
            "meeting.read",
            request.app.state.database,
            resource_type="meeting",
            resource_key=meeting_key,
            scope_type=scope_type,
            scope_id=actor.enterprise_id if scope_type == "enterprise" else scope_key,
        )
        return get_meeting_detail(request.app.state.database, meeting_key, actor.enterprise_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/decision-meetings/{meeting_key}/run",
    response_model=MeetingRunResponse,
)
async def run_meeting(
    request: Request,
    meeting_key: str,
    payload: MeetingRunRequest,
) -> MeetingRunResponse:
    actor = resolve_development_actor(request)
    try:
        scope_type, scope_key = get_meeting_scope(
            request.app.state.database, meeting_key, actor.enterprise_id
        )
        require_permission(
            actor,
            "meeting.start",
            request.app.state.database,
            resource_type="meeting",
            resource_key=meeting_key,
            scope_type=scope_type,
            scope_id=actor.enterprise_id if scope_type == "enterprise" else scope_key,
        )
        return await run_digital_meeting(
            request.app.state.database,
            request.app.state.settings,
            request.app.state.ai_provider,
            actor,
            meeting_key=meeting_key,
            refresh_evidence=payload.refresh_evidence,
            runtime=request.app.state.agent_runtime,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/decision-meetings/{meeting_key}/confirm",
    response_model=MeetingConfirmResponse,
)
async def confirm_meeting(
    request: Request,
    meeting_key: str,
    payload: MeetingConfirmRequest,
) -> MeetingConfirmResponse:
    actor = resolve_development_actor(request)
    try:
        _, _, created_count = confirm_meeting_decision(
            request.app.state.database,
            meeting_key=meeting_key,
            actor=actor,
            comment=payload.comment,
        )
        return MeetingConfirmResponse(
            detail=get_meeting_detail(
                request.app.state.database, meeting_key, actor.enterprise_id
            ),
            created_action_count=created_count,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
