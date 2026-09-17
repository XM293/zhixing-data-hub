from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4

from fastapi import Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from zhixing_api.auth_service import verify_password
from zhixing_api.data_models import (
    AccessDelegation,
    AccessRole,
    AccessRolePermission,
    AuthorizationDecision,
    AuthSession,
    Enterprise,
    EnterpriseMembership,
    Membership,
    OrgUnit,
    PermissionDefinition,
    Principal,
    RoleAssignment,
    ScopeGrant,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem

DEVELOPMENT_ACTOR_HEADER = "X-Zhixing-Demo-Actor"
AUTH_SESSION_COOKIE = "zhixing_session"
AUTH_SESSION_TTL_SECONDS = 8 * 60 * 60


def resolve_enterprise_id(database: Database, enterprise_id: str | None = None) -> str:
    """Resolve an explicit legal-entity scope for service-layer compatibility calls."""
    if enterprise_id:
        return enterprise_id
    with database.session() as session:
        resolved = list(session.scalars(select(Enterprise.id).order_by(Enterprise.id).limit(2)))
    if len(resolved) != 1:
        raise LookupError("explicit enterprise scope is required")
    return resolved[0]


@dataclass(frozen=True, slots=True)
class ActorScope:
    scope_type: str
    scope_ids: tuple[str, ...]
    effect: str

    def snapshot(self) -> dict[str, object]:
        return {
            "scope_type": self.scope_type,
            "scope_ids": list(self.scope_ids),
            "effect": self.effect,
        }


@dataclass(frozen=True, slots=True)
class ActorContext:
    enterprise_id: str
    principal_id: str
    actor_key: str
    user_account_id: str
    login_name: str
    display_name: str
    role_id: str
    access_role_keys: tuple[str, ...]
    membership_ids: tuple[str, ...]
    permissions: frozenset[str]
    scopes: tuple[ActorScope, ...]
    permission_set_version: str
    request_id: str
    run_id: str
    group_id: str | None = None
    authentication_method: str = "development-provider"
    scope_selection: dict[str, object] | None = None

    def snapshot(self) -> dict[str, object]:
        return {
            "enterprise_id": self.enterprise_id,
            "group_id": self.group_id,
            "principal_id": self.principal_id,
            "actor_key": self.actor_key,
            "user_account_id": self.user_account_id,
            "login_name": self.login_name,
            "display_name": self.display_name,
            "role_id": self.role_id,
            "access_role_keys": list(self.access_role_keys),
            "membership_ids": list(self.membership_ids),
            "permissions": sorted(self.permissions),
            "scopes": [scope.snapshot() for scope in self.scopes],
            "permission_set_version": self.permission_set_version,
            "authentication_method": self.authentication_method,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "scope_selection": self.scope_selection,
        }


def resolve_development_actor(request: Request) -> ActorContext:
    session_token = request_session_token(request)
    if session_token:
        return resolve_session_actor(request, session_token)

    if getattr(request.app.state.settings, "environment", "production") not in {
        "development",
        "test",
    }:
        raise ApiProblem(
            status_code=401,
            code="auth.session_required",
            message="当前请求需要有效的登录会话",
        )
    login_name = request.headers.get(DEVELOPMENT_ACTOR_HEADER, "").strip().casefold()
    if not login_name:
        raise ApiProblem(
            status_code=401,
            code="auth.development_actor_required",
            message="本地验收请求需要有效的数据库开发身份",
            details={"header": DEVELOPMENT_ACTOR_HEADER},
        )

    return resolve_database_actor(
        request.app.state.database,
        login_name=login_name,
        request_id=getattr(request.state, "request_id", "req_unavailable"),
        run_id=getattr(request.state, "run_id", "run_unavailable"),
        authentication_method="development-provider",
    )


def authenticate_local_actor(
    database: Database,
    *,
    login_name: str,
    password: str,
    request_id: str,
    run_id: str,
) -> ActorContext:
    normalized_login = login_name.strip().casefold()
    with database.session() as session:
        accounts = list(
            session.scalars(
                select(UserAccount).where(UserAccount.local_login_name == normalized_login)
            )
        )
        if len(accounts) > 1:
            raise ApiProblem(
                status_code=409,
                code="auth.login_ambiguous",
                message="登录名对应多个企业，请使用企业限定登录名",
            )
        account = accounts[0] if accounts else None
        if (
            account is None
            or account.status != "active"
            or not verify_password(password, account.password_hash)
        ):
            raise ApiProblem(
                status_code=401,
                code="auth.invalid_credentials",
                message="登录名或密码不正确",
            )
    return resolve_database_actor(
        database,
        login_name=normalized_login,
        request_id=request_id,
        run_id=run_id,
        authentication_method="local-password",
    )


def create_auth_session(
    database: Database,
    actor: ActorContext,
    *,
    ttl_seconds: int = AUTH_SESSION_TTL_SECONDS,
    authentication_method: str = "development-session",
) -> tuple[str, AuthSession]:
    now = datetime.now(UTC)
    raw_token = token_urlsafe(48)
    session = AuthSession(
        id=f"auth_session_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        user_account_id=actor.user_account_id,
        session_token_hash=sha256(raw_token.encode()).hexdigest(),
        authentication_method=authentication_method,
        issued_at=now,
        expires_at=datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=UTC),
        last_seen_at=now,
        revoked_at=None,
        request_id=actor.request_id,
        run_id=actor.run_id,
    )
    with database.session() as db_session:
        account = db_session.get(UserAccount, actor.user_account_id)
        if account is None or account.status != "active":
            raise ApiProblem(
                status_code=401,
                code="auth.account_inactive",
                message="当前账号不可建立会话",
            )
        account.last_login_at = now
        db_session.add(session)
        db_session.commit()
    return raw_token, session


def resolve_session_actor(request: Request, raw_token: str) -> ActorContext:
    token_hash = sha256(raw_token.encode()).hexdigest()
    now = datetime.now(UTC)
    with request.app.state.database.session() as db_session:
        session = db_session.scalar(
            select(AuthSession).where(AuthSession.session_token_hash == token_hash)
        )
        if session is None or session.revoked_at is not None:
            raise ApiProblem(
                status_code=401,
                code="auth.session_invalid",
                message="登录会话已失效，请重新登录",
            )
        expires_at = (
            session.expires_at.replace(tzinfo=UTC)
            if session.expires_at.tzinfo is None
            else session.expires_at
        )
        if expires_at <= now:
            raise ApiProblem(
                status_code=401,
                code="auth.session_invalid",
                message="登录会话已失效，请重新登录",
            )
        account = db_session.get(UserAccount, session.user_account_id)
        if account is None or account.status != "active":
            raise ApiProblem(
                status_code=401,
                code="auth.account_inactive",
                message="该账号已停用，无法继续使用当前会话",
            )
        session.last_seen_at = now
        db_session.commit()
        login_name = account.local_login_name
        context_enterprise_id = session.enterprise_id
        authentication_method = session.authentication_method
        selection = session.scope_selection
    actor = resolve_database_actor(
        request.app.state.database,
        login_name=login_name,
        enterprise_id=context_enterprise_id,
        user_account_id=account.id,
        request_id=getattr(request.state, "request_id", "req_unavailable"),
        run_id=getattr(request.state, "run_id", "run_unavailable"),
        authentication_method=authentication_method,
    )
    return replace(actor, scope_selection=selection)


def revoke_auth_session(database: Database, raw_token: str) -> bool:
    token_hash = sha256(raw_token.encode()).hexdigest()
    with database.session() as db_session:
        session = db_session.scalar(
            select(AuthSession).where(AuthSession.session_token_hash == token_hash)
        )
        if session is None or session.revoked_at is not None:
            return False
        session.revoked_at = datetime.now(UTC)
        db_session.commit()
        return True


def request_session_token(request: Request) -> str | None:
    cookie = request.cookies.get(AUTH_SESSION_COOKIE, "").strip()
    if cookie:
        return cookie
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() == "bearer" and token.strip():
        return token.strip()
    return None


def resolve_database_actor(
    database: Database,
    *,
    login_name: str,
    request_id: str,
    run_id: str,
    enterprise_id: str | None = None,
    user_account_id: str | None = None,
    authentication_method: str = "trusted-internal-database",
) -> ActorContext:
    login_name = login_name.strip().casefold()
    now = datetime.now(UTC)
    with database.session() as session:
        account = session.get(UserAccount, user_account_id) if user_account_id else None
        if account is None:
            accounts = list(
                session.scalars(
                    select(UserAccount).where(UserAccount.local_login_name == login_name)
                )
            )
            if enterprise_id:
                accounts = [item for item in accounts if item.enterprise_id == enterprise_id]
            if len(accounts) > 1:
                raise ApiProblem(
                    status_code=409,
                    code="auth.login_ambiguous",
                    message="登录名对应多个企业账号，必须明确企业范围",
                )
            account = accounts[0] if accounts else None
        if account is None or account.status != "active":
            raise ApiProblem(
                status_code=401,
                code="auth.development_actor_unknown",
                message="数据库中不存在可用的开发身份",
                details={"actor": login_name},
            )
        principal = session.get(Principal, account.principal_id)
        if principal is None or principal.status != "active":
            raise ApiProblem(
                status_code=401,
                code="auth.principal_inactive",
                message="该账号关联的企业主体不可用",
            )
        target_enterprise_id = enterprise_id or account.enterprise_id
        if target_enterprise_id != account.enterprise_id:
            membership = session.scalar(
                select(EnterpriseMembership).where(
                    EnterpriseMembership.principal_id == principal.id,
                    EnterpriseMembership.enterprise_id == target_enterprise_id,
                    EnterpriseMembership.status == "active",
                    EnterpriseMembership.valid_from <= now,
                    or_(
                        EnterpriseMembership.valid_to.is_(None),
                        EnterpriseMembership.valid_to > now,
                    ),
                )
            )
            if membership is None:
                raise ApiProblem(
                    status_code=403,
                    code="auth.enterprise_membership_required",
                    message="当前主体没有目标企业的有效成员关系",
                )
        enterprise = session.get(Enterprise, target_enterprise_id)
        if enterprise is None:
            raise ApiProblem(
                status_code=401,
                code="auth.enterprise_unknown",
                message="该账号关联的企业边界不可用",
            )

        assignments = list(
            session.scalars(
                select(RoleAssignment).where(
                    RoleAssignment.enterprise_id == target_enterprise_id,
                    RoleAssignment.principal_id == principal.id,
                    RoleAssignment.status == "active",
                    RoleAssignment.valid_from <= now,
                    or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to > now),
                )
            )
        )
        role_ids = [assignment.access_role_id for assignment in assignments]
        roles = list(
            session.scalars(
                select(AccessRole).where(
                    AccessRole.id.in_(role_ids),
                    AccessRole.status == "active",
                )
            )
        )
        role_keys = tuple(sorted(role.role_key for role in roles))

        permission_rows = list(
            session.execute(
                select(PermissionDefinition.permission_key, AccessRolePermission.effect)
                .join(
                    AccessRolePermission,
                    AccessRolePermission.permission_id == PermissionDefinition.id,
                )
                .where(
                    AccessRolePermission.access_role_id.in_(role_ids),
                    PermissionDefinition.status == "active",
                )
            )
        )
        allowed = {key for key, effect in permission_rows if effect == "allow"}
        denied = {key for key, effect in permission_rows if effect == "deny"}
        if "platform-admin" in role_keys:
            all_active_keys = set(
                session.scalars(
                    select(PermissionDefinition.permission_key).where(
                        PermissionDefinition.status == "active"
                    )
                )
            )
            allowed.update(all_active_keys)
        permissions = frozenset(allowed - denied)

        assignment_ids = [assignment.id for assignment in assignments]
        grants = list(
            session.scalars(
                select(ScopeGrant).where(
                    ScopeGrant.role_assignment_id.in_(assignment_ids),
                    ScopeGrant.valid_from <= now,
                    or_(ScopeGrant.valid_to.is_(None), ScopeGrant.valid_to > now),
                )
            )
        )
        direct_scopes = tuple(
            ActorScope(
                scope_type=grant.scope_type,
                scope_ids=tuple(grant.scope_ids),
                effect=grant.effect,
            )
            for grant in sorted(grants, key=lambda item: (item.scope_type, item.id))
        )
        delegations = list(
            session.scalars(
                select(AccessDelegation).where(
                    AccessDelegation.enterprise_id == target_enterprise_id,
                    AccessDelegation.delegatee_principal_id == principal.id,
                    AccessDelegation.status.in_(("active", "scheduled")),
                    AccessDelegation.valid_from <= now,
                    AccessDelegation.valid_to > now,
                )
            )
        )
        delegated_permissions: set[str] = set()
        delegated_scopes: list[ActorScope] = []
        active_delegation_keys: list[str] = []
        for delegation in delegations:
            delegator_permissions, delegator_scopes = _delegator_current_access(
                session,
                enterprise_id=target_enterprise_id,
                principal_id=delegation.delegator_principal_id,
                now=now,
            )
            effective = set(delegation.permissions) & delegator_permissions
            if not effective:
                continue
            permitted_scopes = _intersect_delegated_scopes(
                list(delegation.scopes), delegator_scopes, target_enterprise_id
            )
            if delegation.scopes and not permitted_scopes:
                continue
            delegated_permissions.update(effective)
            delegated_scopes.extend(permitted_scopes)
            active_delegation_keys.append(delegation.delegation_key)
        permissions = frozenset(set(permissions) | delegated_permissions)
        scopes = tuple(
            sorted(
                {*direct_scopes, *delegated_scopes},
                key=lambda item: (item.scope_type, item.scope_ids, item.effect),
            )
        )
        role_keys = tuple(
            [*role_keys, *(f"delegation:{key}" for key in sorted(active_delegation_keys))]
        )
        membership_ids = tuple(
            session.scalars(
                select(Membership.id)
                .where(
                    Membership.enterprise_id == target_enterprise_id,
                    Membership.principal_id == principal.id,
                    Membership.status == "active",
                    Membership.valid_from <= now,
                    or_(Membership.valid_to.is_(None), Membership.valid_to > now),
                )
                .order_by(Membership.id)
            )
        )
        policy_material = "|".join(
            [
                *(
                    f"{role.role_key}@{role.version}"
                    for role in sorted(roles, key=lambda item: item.id)
                ),
                *sorted(permissions),
                *(str(scope.snapshot()) for scope in scopes),
            ]
        )
        permission_set_version = f"access-{sha256(policy_material.encode()).hexdigest()[:16]}"
        return ActorContext(
            enterprise_id=target_enterprise_id,
            principal_id=principal.id,
            actor_key=principal.principal_key,
            user_account_id=account.id,
            login_name=account.local_login_name,
            display_name=principal.display_name,
            role_id=account.experience_role_key,
            access_role_keys=role_keys,
            membership_ids=membership_ids,
            permissions=permissions,
            scopes=scopes,
            permission_set_version=permission_set_version,
            request_id=request_id,
            run_id=run_id,
            group_id=enterprise.group_id,
            authentication_method=authentication_method,
        )


def _delegator_current_access(
    session: Session,
    *,
    enterprise_id: str,
    principal_id: str,
    now: datetime,
) -> tuple[set[str], tuple[ActorScope, ...]]:
    assignments = list(
        session.scalars(
            select(RoleAssignment).where(
                RoleAssignment.enterprise_id == enterprise_id,
                RoleAssignment.principal_id == principal_id,
                RoleAssignment.status == "active",
                RoleAssignment.valid_from <= now,
                or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to > now),
            )
        )
    )
    role_ids = [item.access_role_id for item in assignments]
    rows = (
        list(
            session.execute(
                select(PermissionDefinition.permission_key, AccessRolePermission.effect)
                .join(
                    AccessRolePermission,
                    AccessRolePermission.permission_id == PermissionDefinition.id,
                )
                .join(AccessRole, AccessRole.id == AccessRolePermission.access_role_id)
                .where(
                    AccessRolePermission.access_role_id.in_(role_ids),
                    AccessRole.status == "active",
                    PermissionDefinition.status == "active",
                )
            )
        )
        if role_ids
        else []
    )
    allowed = {key for key, effect in rows if effect == "allow"}
    denied = {key for key, effect in rows if effect == "deny"}
    assignment_ids = [item.id for item in assignments]
    grants = (
        list(
            session.scalars(
                select(ScopeGrant).where(
                    ScopeGrant.role_assignment_id.in_(assignment_ids),
                    ScopeGrant.valid_from <= now,
                    or_(ScopeGrant.valid_to.is_(None), ScopeGrant.valid_to > now),
                )
            )
        )
        if assignment_ids
        else []
    )
    scopes = tuple(
        ActorScope(
            scope_type=item.scope_type,
            scope_ids=tuple(item.scope_ids),
            effect=item.effect,
        )
        for item in grants
    )
    return allowed - denied, scopes


def _intersect_delegated_scopes(
    requested: list[dict[str, object]],
    delegator_scopes: tuple[ActorScope, ...],
    enterprise_id: str,
) -> list[ActorScope]:
    enterprise_allowed = any(
        scope.effect == "allow"
        and scope.scope_type == "enterprise"
        and enterprise_id in scope.scope_ids
        for scope in delegator_scopes
    )
    allowed_pairs = {
        (scope.scope_type, scope_id)
        for scope in delegator_scopes
        if scope.effect == "allow"
        for scope_id in scope.scope_ids
    }
    result: list[ActorScope] = []
    for item in requested:
        scope_type = str(item.get("scope_type", ""))
        scope_ids_value = item.get("scope_ids", [])
        if not scope_type or not isinstance(scope_ids_value, list):
            continue
        scope_ids = tuple(
            str(scope_id)
            for scope_id in scope_ids_value
            if enterprise_allowed or (scope_type, str(scope_id)) in allowed_pairs
        )
        if scope_ids:
            result.append(ActorScope(scope_type=scope_type, scope_ids=scope_ids, effect="allow"))
    return result


def require_permission(
    actor: ActorContext,
    permission: str,
    database: Database,
    *,
    resource_type: str,
    resource_key: str,
    scope_type: str | None = None,
    scope_id: str | None = None,
    transaction: Session | None = None,
) -> None:
    permission_allowed = permission in actor.permissions
    scope_allowed = _scope_allows(
        actor,
        scope_type=scope_type,
        scope_id=scope_id,
        database=database,
    )
    decision = "allow" if permission_allowed and scope_allowed else "deny"
    if not permission_allowed:
        reason = "permission_not_assigned"
    elif not scope_allowed:
        reason = "resource_scope_not_granted"
    else:
        reason = "permission_and_scope_granted"
    with nullcontext(transaction) if transaction is not None else database.session() as session:
        session.add(
            AuthorizationDecision(
                id=f"authorization_decision_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                request_id=actor.request_id,
                run_id=actor.run_id,
                actor_principal_id=actor.principal_id,
                permission_key=permission,
                resource_type=resource_type,
                resource_key=resource_key,
                decision=decision,
                reason=reason,
                policy_version=actor.permission_set_version,
                scope_snapshot=[scope.snapshot() for scope in actor.scopes],
                decided_at=datetime.now(UTC),
            )
        )
        if transaction is None:
            session.commit()
    if decision == "deny":
        code = (
            "authorization.permission_denied"
            if not permission_allowed
            else "authorization.scope_denied"
        )
        raise ApiProblem(
            status_code=403,
            code=code,
            message=(
                "当前数据库身份未获分配该权限"
                if not permission_allowed
                else "当前数据库身份的数据范围不包含目标资源"
            ),
            details={
                "actor_key": actor.actor_key,
                "permission": permission,
                "required_scope_type": scope_type or "none",
                "required_scope_id": scope_id or "none",
                "permission_set_version": actor.permission_set_version,
            },
        )


def _scope_allows(
    actor: ActorContext,
    *,
    scope_type: str | None,
    scope_id: str | None,
    database: Database | None = None,
) -> bool:
    if scope_type is None or scope_id is None:
        return True
    org_ancestor_ids = (
        _org_ancestor_ids(database, actor.enterprise_id, scope_id)
        if database is not None
        and scope_type in {"org_unit", "business_unit", "org_subtree"}
        else set()
    )
    matching = [
        scope
        for scope in actor.scopes
        if (
            (scope.scope_type == "enterprise" and actor.enterprise_id in scope.scope_ids
             and (scope_type != "enterprise" or scope_id == actor.enterprise_id))
            or (scope.scope_type == scope_type and scope_id in scope.scope_ids)
            or (
                scope.scope_type == "org_subtree"
                and any(root_id in org_ancestor_ids for root_id in scope.scope_ids)
            )
        )
    ]
    if any(scope.effect == "deny" for scope in matching):
        return False
    return any(scope.effect == "allow" for scope in matching)


def actor_scope_allows(
    actor: ActorContext,
    *,
    scope_type: str | None,
    scope_id: str | None,
    database: Database | None = None,
) -> bool:
    return _scope_allows(
        actor,
        scope_type=scope_type,
        scope_id=scope_id,
        database=database,
    )


def _org_ancestor_ids(
    database: Database, enterprise_id: str, org_unit_id: str
) -> set[str]:
    result: set[str] = set()
    current_id: str | None = org_unit_id
    with database.session() as session:
        while current_id and current_id not in result:
            org = session.scalar(
                select(OrgUnit).where(
                    OrgUnit.enterprise_id == enterprise_id,
                    OrgUnit.id == current_id,
                )
            )
            if org is None:
                break
            result.add(org.id)
            current_id = org.parent_org_unit_id
    return result
