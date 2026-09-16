from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from zhixing_api.actor_context import (
    AUTH_SESSION_COOKIE,
    authenticate_local_actor,
    create_auth_session,
    request_session_token,
    resolve_database_actor,
    resolve_development_actor,
    revoke_auth_session,
)
from zhixing_api.data_models import BusinessEntity, BusinessUnit, Enterprise
from zhixing_api.errors import ApiProblem
from zhixing_api.identity_schemas import (
    AuthSessionResponse,
    CurrentIdentityResponse,
    DevelopmentSessionRequest,
    LocalLoginRequest,
    ScopeOptionsResponse,
    ScopeOptionView,
)
from zhixing_api.identity_service import current_identity
from zhixing_api.scope_context import build_scope_context

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    payload: LocalLoginRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    actor = authenticate_local_actor(
        request.app.state.database,
        login_name=payload.login_name,
        password=payload.password,
        request_id=getattr(request.state, "request_id", "req_unavailable"),
        run_id=getattr(request.state, "run_id", "run_unavailable"),
    )
    session_token, session = create_auth_session(
        request.app.state.database,
        actor,
        ttl_seconds=request.app.state.settings.auth_session_ttl_seconds,
        authentication_method="local-password",
    )
    response.set_cookie(
        key=AUTH_SESSION_COOKIE,
        value=session_token,
        max_age=request.app.state.settings.auth_session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.environment == "production",
        path="/",
    )
    return AuthSessionResponse(
        session_id=session.id,
        authentication_method=session.authentication_method,
        expires_at=session.expires_at,
        identity=current_identity(request.app.state.database, actor),
    )


@router.post("/development/session", response_model=AuthSessionResponse)
async def create_development_session(
    payload: DevelopmentSessionRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    settings = request.app.state.settings
    if settings.environment not in {"development", "test"}:
        raise ApiProblem(
            status_code=status.HTTP_404_NOT_FOUND,
            code="auth.provider_unavailable",
            message="当前运行环境未启用本地开发认证提供者",
        )
    actor = resolve_database_actor(
        request.app.state.database,
        login_name=payload.login_name,
        request_id=getattr(request.state, "request_id", "req_unavailable"),
        run_id=getattr(request.state, "run_id", "run_unavailable"),
        authentication_method="development-session",
    )
    raw_token, session = create_auth_session(
        request.app.state.database,
        actor,
        ttl_seconds=settings.auth_session_ttl_seconds,
    )
    response.set_cookie(
        key=AUTH_SESSION_COOKIE,
        value=raw_token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        path="/",
    )
    return AuthSessionResponse(
        session_id=session.id,
        authentication_method=session.authentication_method,
        expires_at=session.expires_at,
        identity=current_identity(request.app.state.database, actor),
    )


@router.get("/session", response_model=CurrentIdentityResponse)
async def get_current_session(request: Request) -> CurrentIdentityResponse:
    actor = resolve_development_actor(request)
    return current_identity(request.app.state.database, actor)


@router.get("/scope-options", response_model=ScopeOptionsResponse)
async def get_scope_options(request: Request) -> ScopeOptionsResponse:
    actor = resolve_development_actor(request)
    context = build_scope_context(request.app.state.database, actor,
                                  selection={"scope_level": "group"})
    enterprise_ids = context.allowed_enterprise_ids
    with request.app.state.database.session() as session:
        enterprises = session.scalars(
            select(Enterprise).where(Enterprise.id.in_(enterprise_ids)).order_by(Enterprise.name)
        ).all()
        units = session.scalars(
            select(BusinessUnit)
            .where(BusinessUnit.enterprise_id.in_(enterprise_ids),
                   BusinessUnit.id.in_(context.business_unit_ids))
            .order_by(BusinessUnit.name)
        ).all()
        entities = {row.canonical_key: row for row in session.scalars(select(BusinessEntity).where(
            BusinessEntity.enterprise_id.in_(enterprise_ids),
            BusinessEntity.canonical_key.in_((*context.store_ids, *context.warehouse_ids)),
        ))}
    return ScopeOptionsResponse(
        group_id=actor.group_id,
        current_enterprise_id=actor.enterprise_id,
        groups=[ScopeOptionView(key=context.group_id, label=context.group_name or context.group_id,
                                scope_type="group")] if context.group_id else [],
        enterprises=[
            ScopeOptionView(key=item.id, label=item.name, scope_type="enterprise",
                            enterprise_id=item.id)
            for item in enterprises
        ],
        business_units=[
            ScopeOptionView(key=item.id, label=item.name, scope_type="business_unit",
                            enterprise_id=item.enterprise_id, business_unit_id=item.id)
            for item in units
        ],
        stores=[
            ScopeOptionView(key=key, label=entities[key].display_name if key in entities else key,
                            scope_type="store",
                            enterprise_id=entities[key].enterprise_id if key in entities else None)
            for key in context.store_ids
        ],
        warehouses=[
            ScopeOptionView(key=key, label=entities[key].display_name if key in entities else key,
                            scope_type="warehouse",
                            enterprise_id=entities[key].enterprise_id if key in entities else None)
            for key in context.warehouse_ids
        ],
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response) -> Response:
    token = request_session_token(request)
    if token:
        revoke_auth_session(request.app.state.database, token)
    response.delete_cookie(AUTH_SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
