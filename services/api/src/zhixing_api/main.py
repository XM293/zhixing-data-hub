import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from zhixing_codex_runtime import CodexAppServerRuntime, CodexRuntimeSettings

from zhixing_api.agent_runtime_service import reconcile_orphaned_runtime_sessions
from zhixing_api.ai_provider import ResponsesAIProvider
from zhixing_api.config import Settings, load_settings, validate_settings
from zhixing_api.database import Database
from zhixing_api.errors import (
    ApiProblem,
    api_problem_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from zhixing_api.knowledge_providers import build_knowledge_providers
from zhixing_api.meeting_scheduler import run_meeting_scheduler
from zhixing_api.memory_providers import build_memory_providers
from zhixing_api.object_storage import build_object_storage
from zhixing_api.observability import TraceContextMiddleware
from zhixing_api.redis_coordinator import build_redis_coordinator
from zhixing_api.review_schedule_service import run_review_schedule_dispatcher
from zhixing_api.routers.actions import router as actions_router
from zhixing_api.routers.agent_feedback import router as agent_feedback_router
from zhixing_api.routers.ai_operations import router as ai_operations_router
from zhixing_api.routers.analysis import router as analysis_router
from zhixing_api.routers.audit import router as audit_router
from zhixing_api.routers.auth import router as auth_router
from zhixing_api.routers.canonical import router as canonical_router
from zhixing_api.routers.centers import router as centers_router
from zhixing_api.routers.customer_operations import router as customer_operations_router
from zhixing_api.routers.customer_service import router as customer_service_router
from zhixing_api.routers.data_center import router as data_center_router
from zhixing_api.routers.decisions import router as decisions_router
from zhixing_api.routers.evaluations import router as evaluations_router
from zhixing_api.routers.governance import router as governance_router
from zhixing_api.routers.health import router as health_router
from zhixing_api.routers.identity import router as identity_router
from zhixing_api.routers.knowledge import router as knowledge_router
from zhixing_api.routers.mcp_sessions import router as mcp_sessions_router
from zhixing_api.routers.memories import router as memories_router
from zhixing_api.routers.platform import router as platform_router
from zhixing_api.routers.role_twin_tests import router as role_twin_tests_router
from zhixing_api.routers.role_twins import router as role_twins_router
from zhixing_api.routers.skills import router as skills_router
from zhixing_api.routers.tools import router as tools_router
from zhixing_api.routers.workspaces import router as workspaces_router
from zhixing_api.seed import seed_database


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    validate_settings(settings)
    database = Database(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout_seconds=settings.database_pool_timeout_seconds,
        pool_recycle_seconds=settings.database_pool_recycle_seconds,
    )
    if settings.database_auto_migrate:
        database.migrate()
    if settings.seed_enabled:
        seed_database(database, settings)
    object_storage = build_object_storage(
        provider=settings.file_asset_storage_provider,
        local_root=settings.file_asset_storage_path,
        s3_endpoint=settings.s3_endpoint,
        s3_region=settings.s3_region,
        s3_bucket=settings.s3_bucket,
        s3_access_key=settings.s3_access_key,
        s3_secret_key=settings.s3_secret_key,
        s3_force_path_style=settings.s3_force_path_style,
        s3_auto_create_bucket=settings.s3_auto_create_bucket,
    )
    redis_coordinator = build_redis_coordinator(
        enabled=settings.redis_enabled,
        url=settings.redis_url,
        key_prefix=settings.redis_key_prefix,
    )
    agent_runtime = CodexAppServerRuntime(
        CodexRuntimeSettings(
            command=(settings.codex_command, "app-server", "--listen", "stdio://"),
            request_timeout_seconds=settings.codex_runtime_timeout_seconds,
        )
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        reconcile_orphaned_runtime_sessions(database)
        scheduler = asyncio.create_task(
            run_meeting_scheduler(
                database,
                settings.meeting_scheduler_poll_seconds,
                redis_coordinator,
            )
        )
        review_scheduler = asyncio.create_task(
            run_review_schedule_dispatcher(
                database,
                settings.review_schedule_poll_seconds,
                redis_coordinator,
            )
        )
        try:
            yield
        finally:
            scheduler.cancel()
            review_scheduler.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler
            with suppress(asyncio.CancelledError):
                await review_scheduler
            await agent_runtime.close()
            await redis_coordinator.close()
            database.dispose()

    app = FastAPI(
        title="知行数枢 API",
        description="企业数据智能运营中枢模块化 API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.object_storage = object_storage
    app.state.redis_coordinator = redis_coordinator
    app.state.ai_provider = ResponsesAIProvider()
    app.state.agent_runtime = agent_runtime
    app.state.knowledge_providers = build_knowledge_providers(settings)
    app.state.memory_providers = build_memory_providers(settings)
    app.add_middleware(TraceContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Run-ID"],
    )
    app.add_exception_handler(ApiProblem, api_problem_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(audit_router)
    app.include_router(platform_router)
    app.include_router(data_center_router)
    app.include_router(canonical_router)
    app.include_router(knowledge_router)
    app.include_router(memories_router)
    app.include_router(identity_router)
    app.include_router(decisions_router)
    app.include_router(actions_router)
    app.include_router(ai_operations_router)
    app.include_router(analysis_router)
    app.include_router(customer_service_router)
    app.include_router(centers_router)
    app.include_router(governance_router)
    app.include_router(customer_operations_router)
    app.include_router(agent_feedback_router)
    app.include_router(mcp_sessions_router)
    app.include_router(tools_router)
    app.include_router(workspaces_router)
    app.include_router(role_twins_router)
    app.include_router(role_twin_tests_router)
    app.include_router(skills_router)
    app.include_router(evaluations_router)
    return app


app = create_app()
