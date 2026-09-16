from fastapi import APIRouter, HTTPException, Request, status

from zhixing_api import __version__
from zhixing_api.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", response_model=HealthResponse)
async def live(request: Request) -> HealthResponse:
    return HealthResponse(
        service="zhixing-api",
        status="live",
        version=__version__,
        environment=request.app.state.settings.environment,
    )


@router.get("/health/ready", response_model=HealthResponse)
async def ready(request: Request) -> HealthResponse:
    if not request.app.state.database.ready():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="database")
    if not request.app.state.database.migrations_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database-migrations",
        )
    if not request.app.state.object_storage.ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="object-storage",
        )
    if not await request.app.state.redis_coordinator.ready():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="redis")
    return HealthResponse(
        service="zhixing-api",
        status="ready",
        version=__version__,
        environment=request.app.state.settings.environment,
    )
