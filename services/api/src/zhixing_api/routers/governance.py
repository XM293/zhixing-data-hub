from fastapi import APIRouter, Request

from zhixing_api.actor_context import resolve_development_actor
from zhixing_api.governance_schemas import (
    BusinessUnitRequest,
    ConsolidationRequest,
    MembershipRequest,
    OrganizationRequest,
)
from zhixing_api.governance_service import (
    governance_overview,
    save_business_unit,
    save_consolidation,
    save_enterprise,
    save_group,
    save_membership,
)

router = APIRouter(prefix="/api/v1/governance", tags=["group-governance"])


@router.get("")
async def overview(request: Request) -> dict[str, object]:
    return governance_overview(request.app.state.database, resolve_development_actor(request))


@router.put("/group")
async def group(request: Request, payload: OrganizationRequest) -> dict[str, object]:
    return save_group(request.app.state.database, resolve_development_actor(request), payload)


@router.post("/enterprises", status_code=201)
async def create_enterprise(request: Request, payload: OrganizationRequest) -> dict[str, object]:
    return save_enterprise(request.app.state.database, resolve_development_actor(request), payload)


@router.put("/enterprises/{enterprise_id}")
async def enterprise(request: Request, enterprise_id: str,
                     payload: OrganizationRequest) -> dict[str, object]:
    return save_enterprise(request.app.state.database, resolve_development_actor(request),
                           payload, enterprise_id=enterprise_id)


@router.post("/business-units", status_code=201)
async def create_business_unit(request: Request, payload: BusinessUnitRequest) -> dict[str, object]:
    return save_business_unit(request.app.state.database, resolve_development_actor(request),
                              payload)


@router.put("/business-units/{unit_id}")
async def unit(request: Request, unit_id: str, payload: BusinessUnitRequest) -> dict[str, object]:
    return save_business_unit(request.app.state.database, resolve_development_actor(request),
                              payload, unit_id=unit_id)


@router.put("/memberships")
async def membership(request: Request, payload: MembershipRequest) -> dict[str, object]:
    return save_membership(request.app.state.database, resolve_development_actor(request), payload)


@router.post("/consolidation-profiles", status_code=201)
async def consolidation(request: Request, payload: ConsolidationRequest) -> dict[str, object]:
    return save_consolidation(request.app.state.database, resolve_development_actor(request),
                              payload)
