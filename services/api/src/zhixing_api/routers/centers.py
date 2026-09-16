from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import APIRouter, Request
from sqlalchemy import or_, select

from zhixing_api.actor_context import (
    request_session_token,
    require_permission,
    resolve_database_actor,
    resolve_development_actor,
)
from zhixing_api.center_schemas import (
    CenterCatalogResponse,
    ContextSwitchRequest,
    ContextSwitchResponse,
    ScopeContextResponse,
)
from zhixing_api.center_service import center_catalog, scope_context
from zhixing_api.data_models import AuthSession, EnterpriseMembership
from zhixing_api.errors import ApiProblem
from zhixing_api.identity_service import current_identity
from zhixing_api.scope_context import build_scope_context

router = APIRouter(prefix="/api/v1", tags=["centers"])


@router.get("/centers/me", response_model=CenterCatalogResponse)
async def get_center_catalog(request: Request) -> CenterCatalogResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "platform.navigation.read",
        request.app.state.database,
        resource_type="center_catalog",
        resource_key="me",
    )
    return center_catalog(request.app.state.database, actor)


@router.get("/context", response_model=ScopeContextResponse)
async def get_scope_context(request: Request) -> ScopeContextResponse:
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "platform.navigation.read",
        request.app.state.database,
        resource_type="scope_context",
        resource_key="me",
    )
    return scope_context(request.app.state.database, actor)


@router.post("/context/switch", response_model=ContextSwitchResponse)
async def switch_context(
    payload: ContextSwitchRequest,
    request: Request,
) -> ContextSwitchResponse:
    raw_token = request_session_token(request)
    if not raw_token:
        raise ApiProblem(
            status_code=401,
            code="auth.session_required",
            message="切换企业需要有效的登录会话",
        )
    actor = resolve_development_actor(request)
    require_permission(
        actor,
        "platform.navigation.read",
        request.app.state.database,
        resource_type="scope_context",
        resource_key=payload.enterprise_id,
    )
    now = datetime.now(UTC)
    token_hash = sha256(raw_token.encode()).hexdigest()
    with request.app.state.database.session() as session:
        auth_session = session.scalar(
            select(AuthSession).where(AuthSession.session_token_hash == token_hash)
        )
        membership = session.scalar(
            select(EnterpriseMembership).where(
                EnterpriseMembership.principal_id == actor.principal_id,
                EnterpriseMembership.enterprise_id == payload.enterprise_id,
                EnterpriseMembership.status == "active",
                EnterpriseMembership.valid_from <= now,
                or_(
                    EnterpriseMembership.valid_to.is_(None),
                    EnterpriseMembership.valid_to > now,
                ),
            )
        )
        if auth_session is None or auth_session.user_account_id != actor.user_account_id:
            raise ApiProblem(
                status_code=401,
                code="auth.session_invalid",
                message="登录会话已失效，请重新登录",
            )
        if membership is None:
            raise ApiProblem(
                status_code=403,
                code="auth.enterprise_membership_required",
                message="当前主体没有目标企业的有效成员关系",
            )
    switched_actor = resolve_database_actor(
        request.app.state.database,
        login_name=actor.login_name,
        enterprise_id=payload.enterprise_id,
        user_account_id=actor.user_account_id,
        request_id=getattr(request.state, "request_id", "req_unavailable"),
        run_id=getattr(request.state, "run_id", "run_unavailable"),
        authentication_method=actor.authentication_method,
    )
    selection = payload.model_dump(exclude={"enterprise_id"})
    build_scope_context(request.app.state.database, switched_actor, selection=selection)
    with request.app.state.database.session() as session:
        auth_session = session.scalar(select(AuthSession).where(
            AuthSession.session_token_hash == token_hash, AuthSession.revoked_at.is_(None)
        ).with_for_update())
        if auth_session is None:
            raise ApiProblem(status_code=401, code="auth.session_invalid", message="登录会话已失效")
        auth_session.enterprise_id = payload.enterprise_id
        auth_session.scope_selection = selection
        session.commit()
    switched_actor = replace(switched_actor, scope_selection=selection)
    identity = current_identity(request.app.state.database, switched_actor)
    return ContextSwitchResponse(
        context=scope_context(request.app.state.database, switched_actor),
        identity=identity,
    )
