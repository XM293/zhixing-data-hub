from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status

from zhixing_api.action_schemas import (
    ActionDecisionRequest,
    ActionDecisionResponse,
    ActionProposalListResponse,
    ActionWorkEventRequest,
    ActionWorkEventResponse,
    ActionWorkListResponse,
)
from zhixing_api.action_service import (
    decide_action_proposal,
    list_action_proposals,
    list_action_work_items,
    transition_action_work_item,
)
from zhixing_api.actor_context import resolve_development_actor

router = APIRouter(prefix="/api/v1", tags=["action-center"])


@router.get("/action-proposals", response_model=ActionProposalListResponse)
async def action_proposals(
    request: Request,
    status_filter: Literal["pending_approval", "approved", "rejected"] | None = Query(
        default=None,
        alias="status",
    ),
    meeting_key: str | None = None,
) -> ActionProposalListResponse:
    actor = resolve_development_actor(request)
    return list_action_proposals(
        request.app.state.database,
        actor,
        status=status_filter,
        meeting_key=meeting_key,
    )


@router.post(
    "/action-proposals/{proposal_key}/decision",
    response_model=ActionDecisionResponse,
)
async def decide_action(
    request: Request,
    proposal_key: str,
    payload: ActionDecisionRequest,
) -> ActionDecisionResponse:
    actor = resolve_development_actor(request)
    try:
        item = decide_action_proposal(
            request.app.state.database,
            proposal_key=proposal_key,
            actor=actor,
            payload=payload,
        )
        return ActionDecisionResponse(item=item)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/action-work-items", response_model=ActionWorkListResponse)
async def action_work_items(
    request: Request,
    status_filter: Literal["ready", "claimed", "in_progress", "blocked", "completed"]
    | None = Query(default=None, alias="status"),
) -> ActionWorkListResponse:
    actor = resolve_development_actor(request)
    return list_action_work_items(
        request.app.state.database,
        actor,
        status=status_filter,
    )


@router.post(
    "/action-work-items/{work_key}/events",
    response_model=ActionWorkEventResponse,
)
async def update_action_work_item(
    request: Request,
    work_key: str,
    payload: ActionWorkEventRequest,
) -> ActionWorkEventResponse:
    actor = resolve_development_actor(request)
    try:
        return transition_action_work_item(
            request.app.state.database,
            work_key=work_key,
            actor=actor,
            payload=payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
