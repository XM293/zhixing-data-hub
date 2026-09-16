from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext
from zhixing_api.auth_service import hash_password
from zhixing_api.data_models import (
    AccessRole,
    IdentityManagementEvent,
    Membership,
    OrgUnit,
    Position,
    Principal,
    RoleAssignment,
    ScopeGrant,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.identity_schemas import (
    IdentityRoleAssignmentInput,
    IdentityUserCreateRequest,
    IdentityUserMutationResponse,
    IdentityUserUpdateRequest,
)
from zhixing_api.identity_service import identity_admin_overview


def create_identity_user(
    database: Database,
    *,
    actor: ActorContext,
    payload: IdentityUserCreateRequest,
) -> IdentityUserMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = datetime.now(UTC)
    with database.session() as session:
        replay = _idempotent_replay(
            session,
            actor=actor,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
        )
        if replay is not None:
            return _mutation_response(
                database,
                account_id=replay.target_account_id,
                event_id=replay.id,
                operation="created",
                replayed=True,
            )

        if session.scalar(
            select(UserAccount.id).where(
                UserAccount.enterprise_id == actor.enterprise_id,
                UserAccount.local_login_name == payload.login_name,
            )
        ):
            raise ApiProblem(
                status_code=409,
                code="identity.login_name_conflict",
                message="该登录名已被企业内其他账号使用",
                details={"login_name": payload.login_name},
            )

        org, position = _resolve_membership_catalog(
            session,
            enterprise_id=actor.enterprise_id,
            org_key=payload.org_key,
            position_key=payload.position_key,
        )
        roles = _resolve_access_roles(
            session,
            enterprise_id=actor.enterprise_id,
            assignments=payload.role_assignments,
        )
        account_key = _available_account_key(session, actor.enterprise_id, payload.login_name)
        principal_key = _available_principal_key(session, actor.enterprise_id, payload.login_name)
        principal = Principal(
            id=f"principal_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            principal_key=principal_key,
            principal_type="human",
            display_name=payload.display_name,
            status="active",
            created_at=now,
            updated_at=now,
        )
        account = UserAccount(
            id=f"account_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            principal_id=principal.id,
            account_key=account_key,
            local_login_name=payload.login_name,
            experience_role_key=payload.experience_role_key,
            email=payload.email,
            password_hash=(
                hash_password(payload.initial_password)
                if payload.initial_password
                else None
            ),
            authentication_source=(
                "local-password" if payload.initial_password else "unconfigured"
            ),
            status=payload.status,
            version=1,
            last_login_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add_all([principal, account])
        session.add(
            Membership(
                id=f"membership_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                principal_id=principal.id,
                org_unit_id=org.id,
                position_id=position.id,
                membership_type="primary",
                is_primary=True,
                status="active",
                valid_from=now,
                valid_to=None,
            )
        )
        normalized_assignments = _replace_access_assignments(
            session,
            enterprise_id=actor.enterprise_id,
            principal_id=principal.id,
            assignments=payload.role_assignments,
            roles=roles,
            now=now,
        )
        after_snapshot = _configuration_snapshot(
            account_key=account.account_key,
            login_name=account.local_login_name,
            display_name=principal.display_name,
            email=account.email,
            experience_role_key=account.experience_role_key,
            org_key=org.org_key,
            position_key=position.position_key,
            status=account.status,
            role_assignments=normalized_assignments,
            version=account.version,
        )
        event = _management_event(
            actor=actor,
            account=account,
            event_type="identity.user.created",
            before_snapshot={},
            after_snapshot=after_snapshot,
            changed_fields=[
                "account",
                "membership",
                "role_assignments",
                "scopes",
                "status",
            ],
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            now=now,
        )
        session.add(event)
        session.commit()

    return _mutation_response(
        database,
        account_id=account.id,
        event_id=event.id,
        operation="created",
        replayed=False,
    )


def configure_identity_user(
    database: Database,
    *,
    actor: ActorContext,
    account_key: str,
    payload: IdentityUserUpdateRequest,
) -> IdentityUserMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = datetime.now(UTC)
    with database.session() as session:
        replay = _idempotent_replay(
            session,
            actor=actor,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
        )
        if replay is not None:
            return _mutation_response(
                database,
                account_id=replay.target_account_id,
                event_id=replay.id,
                operation="configured",
                replayed=True,
            )

        account = session.scalar(
            select(UserAccount).where(
                UserAccount.enterprise_id == actor.enterprise_id,
                UserAccount.account_key == account_key,
            )
        )
        if account is None:
            raise ApiProblem(
                status_code=404,
                code="identity.user_not_found",
                message="目标企业账号不存在",
                details={"account_key": account_key},
            )
        if account.version != payload.expected_version:
            raise ApiProblem(
                status_code=409,
                code="identity.version_conflict",
                message="账号配置已被其他管理操作更新，请刷新后重试",
                details={
                    "account_key": account.account_key,
                    "expected_version": payload.expected_version,
                    "actual_version": account.version,
                },
            )
        principal = session.get(Principal, account.principal_id)
        if principal is None:
            raise ApiProblem(
                status_code=409,
                code="identity.principal_missing",
                message="账号关联的企业主体不存在",
            )

        org, position = _resolve_membership_catalog(
            session,
            enterprise_id=actor.enterprise_id,
            org_key=payload.org_key,
            position_key=payload.position_key,
        )
        roles = _resolve_access_roles(
            session,
            enterprise_id=actor.enterprise_id,
            assignments=payload.role_assignments,
        )
        before_snapshot = _current_configuration_snapshot(session, account, principal)
        desired_assignments = _normalized_assignments(
            payload.role_assignments,
            principal_id=principal.id,
            enterprise_id=actor.enterprise_id,
            role_names={key: value.name for key, value in roles.items()},
        )
        if account.principal_id == actor.principal_id and (
            payload.status != "active"
            or desired_assignments != before_snapshot["role_assignments"]
        ):
            raise ApiProblem(
                status_code=409,
                code="identity.self_lockout_denied",
                message="当前管理账号不能停用自身或修改自身访问角色与数据范围",
                details={"account_key": account.account_key},
            )

        desired_snapshot = _configuration_snapshot(
            account_key=account.account_key,
            login_name=account.local_login_name,
            display_name=payload.display_name,
            email=payload.email,
            experience_role_key=payload.experience_role_key,
            org_key=org.org_key,
            position_key=position.position_key,
            status=payload.status,
            role_assignments=desired_assignments,
            version=account.version + 1,
        )
        changed_fields = [
            field
            for field in (
                "display_name",
                "email",
                "experience_role_key",
                "org_key",
                "position_key",
                "status",
                "role_assignments",
            )
            if before_snapshot[field] != desired_snapshot[field]
        ]
        if not changed_fields:
            raise ApiProblem(
                status_code=409,
                code="identity.configuration_unchanged",
                message="账号配置没有发生变化",
                details={"account_key": account.account_key},
            )

        principal.display_name = payload.display_name
        principal.updated_at = now
        account.email = payload.email
        account.experience_role_key = payload.experience_role_key
        account.status = payload.status
        account.version += 1
        account.updated_at = now
        _replace_primary_membership(
            session,
            enterprise_id=actor.enterprise_id,
            principal_id=principal.id,
            org=org,
            position=position,
            now=now,
        )
        _replace_access_assignments(
            session,
            enterprise_id=actor.enterprise_id,
            principal_id=principal.id,
            assignments=payload.role_assignments,
            roles=roles,
            now=now,
        )
        event = _management_event(
            actor=actor,
            account=account,
            event_type="identity.user.configured",
            before_snapshot=before_snapshot,
            after_snapshot=desired_snapshot,
            changed_fields=changed_fields,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            now=now,
        )
        session.add(event)
        session.commit()

    return _mutation_response(
        database,
        account_id=account.id,
        event_id=event.id,
        operation="configured",
        replayed=False,
    )


def _idempotent_replay(
    session: Session,
    *,
    actor: ActorContext,
    idempotency_key: str,
    payload_hash: str,
) -> IdentityManagementEvent | None:
    event = session.scalar(
        select(IdentityManagementEvent).where(
            IdentityManagementEvent.enterprise_id == actor.enterprise_id,
            IdentityManagementEvent.idempotency_key == idempotency_key,
        )
    )
    if event is None:
        return None
    if event.payload_hash != payload_hash:
        raise ApiProblem(
            status_code=409,
            code="identity.idempotency_conflict",
            message="同一请求键已用于不同的身份管理操作",
            details={"client_request_key": idempotency_key},
        )
    return event


def _resolve_membership_catalog(
    session: Session,
    *,
    enterprise_id: str,
    org_key: str,
    position_key: str,
) -> tuple[OrgUnit, Position]:
    org = session.scalar(
        select(OrgUnit).where(
            OrgUnit.enterprise_id == enterprise_id,
            OrgUnit.org_key == org_key,
            OrgUnit.status == "active",
        )
    )
    position = session.scalar(
        select(Position).where(
            Position.enterprise_id == enterprise_id,
            Position.position_key == position_key,
            Position.status == "active",
        )
    )
    if org is None:
        raise ApiProblem(
            status_code=422,
            code="identity.org_not_found",
            message="所选组织不存在或未生效",
            details={"org_key": org_key},
        )
    if position is None:
        raise ApiProblem(
            status_code=422,
            code="identity.position_not_found",
            message="所选岗位不存在或未生效",
            details={"position_key": position_key},
        )
    if position.org_unit_id != org.id:
        raise ApiProblem(
            status_code=422,
            code="identity.position_org_mismatch",
            message="所选岗位不属于目标组织",
            details={"org_key": org_key, "position_key": position_key},
        )
    return org, position


def _resolve_access_roles(
    session: Session,
    *,
    enterprise_id: str,
    assignments: list[IdentityRoleAssignmentInput],
) -> dict[str, AccessRole]:
    role_keys = [item.role_key for item in assignments]
    if len(role_keys) != len(set(role_keys)):
        raise ApiProblem(
            status_code=422,
            code="identity.duplicate_role_assignment",
            message="同一个访问角色不能重复分配",
        )
    roles: dict[str, AccessRole] = {}
    for role_key in role_keys:
        role = session.scalar(
            select(AccessRole)
            .where(
                AccessRole.enterprise_id == enterprise_id,
                AccessRole.role_key == role_key,
                AccessRole.status == "active",
            )
            .order_by(AccessRole.created_at.desc())
        )
        if role is None:
            raise ApiProblem(
                status_code=422,
                code="identity.access_role_not_found",
                message="所选访问角色不存在或未生效",
                details={"role_key": role_key},
            )
        scope_types = [
            scope.scope_type
            for item in assignments
            if item.role_key == role_key
            for scope in item.scopes
        ]
        if len(scope_types) != len(set(scope_types)):
            raise ApiProblem(
                status_code=422,
                code="identity.duplicate_scope_type",
                message="同一角色分配中的数据范围类型不能重复",
                details={"role_key": role_key},
            )
        roles[role_key] = role
    return roles


def _replace_primary_membership(
    session: Session,
    *,
    enterprise_id: str,
    principal_id: str,
    org: OrgUnit,
    position: Position,
    now: datetime,
) -> None:
    memberships = list(
        session.scalars(
            select(Membership).where(
                Membership.enterprise_id == enterprise_id,
                Membership.principal_id == principal_id,
            )
        )
    )
    current = next(
        (item for item in memberships if item.is_primary and item.status == "active"),
        None,
    )
    if current and current.org_unit_id == org.id and current.position_id == position.id:
        return
    if current:
        current.is_primary = False
        current.status = "inactive"
        current.valid_to = now
    target = next(
        (
            item
            for item in memberships
            if item.org_unit_id == org.id and item.position_id == position.id
        ),
        None,
    )
    if target:
        target.membership_type = "primary"
        target.is_primary = True
        target.status = "active"
        target.valid_from = now
        target.valid_to = None
    else:
        session.add(
            Membership(
                id=f"membership_{uuid4().hex}",
                enterprise_id=enterprise_id,
                principal_id=principal_id,
                org_unit_id=org.id,
                position_id=position.id,
                membership_type="primary",
                is_primary=True,
                status="active",
                valid_from=now,
                valid_to=None,
            )
        )


def _replace_access_assignments(
    session: Session,
    *,
    enterprise_id: str,
    principal_id: str,
    assignments: list[IdentityRoleAssignmentInput],
    roles: dict[str, AccessRole],
    now: datetime,
) -> list[dict[str, object]]:
    existing = list(
        session.scalars(
            select(RoleAssignment).where(
                RoleAssignment.enterprise_id == enterprise_id,
                RoleAssignment.principal_id == principal_id,
            )
        )
    )
    existing_by_role_id = {item.access_role_id: item for item in existing}
    desired_role_ids = {roles[item.role_key].id for item in assignments}
    for item in existing:
        if item.access_role_id not in desired_role_ids and item.status == "active":
            item.status = "inactive"
            item.valid_to = now
            for grant in session.scalars(
                select(ScopeGrant).where(ScopeGrant.role_assignment_id == item.id)
            ):
                grant.valid_to = now

    for assignment_input in assignments:
        role = roles[assignment_input.role_key]
        assignment = existing_by_role_id.get(role.id)
        if assignment is None:
            assignment = RoleAssignment(
                id=f"role_assignment_{uuid4().hex}",
                enterprise_id=enterprise_id,
                principal_id=principal_id,
                access_role_id=role.id,
                status="active",
                valid_from=now,
                valid_to=None,
            )
            session.add(assignment)
            session.flush()
        else:
            assignment.status = "active"
            assignment.valid_from = now
            assignment.valid_to = None

        grants = {
            item.scope_type: item
            for item in session.scalars(
                select(ScopeGrant).where(ScopeGrant.role_assignment_id == assignment.id)
            )
        }
        desired_scope_types = {item.scope_type for item in assignment_input.scopes}
        for scope_type, grant in grants.items():
            if scope_type not in desired_scope_types:
                grant.valid_to = now
        for scope_input in assignment_input.scopes:
            scope_ids = _normalize_scope_ids(
                scope_type=scope_input.scope_type,
                scope_ids=scope_input.scope_ids,
                enterprise_id=enterprise_id,
                principal_id=principal_id,
            )
            existing_grant = grants.get(scope_input.scope_type)
            if existing_grant is None:
                session.add(
                    ScopeGrant(
                        id=f"scope_grant_{uuid4().hex}",
                        enterprise_id=enterprise_id,
                        role_assignment_id=assignment.id,
                        scope_type=scope_input.scope_type,
                        scope_ids=scope_ids,
                        effect=scope_input.effect,
                        valid_from=now,
                        valid_to=None,
                    )
                )
            else:
                existing_grant.scope_ids = scope_ids
                existing_grant.effect = scope_input.effect
                existing_grant.valid_from = now
                existing_grant.valid_to = None
    return _normalized_assignments(
        assignments,
        principal_id=principal_id,
        enterprise_id=enterprise_id,
        role_names={key: value.name for key, value in roles.items()},
    )


def _normalized_assignments(
    assignments: list[IdentityRoleAssignmentInput],
    *,
    principal_id: str,
    role_names: dict[str, str],
    enterprise_id: str | None = None,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for assignment in assignments:
        scopes = [
            {
                "scope_type": scope.scope_type,
                "scope_ids": _normalize_scope_ids(
                    scope_type=scope.scope_type,
                    scope_ids=scope.scope_ids,
                    enterprise_id=enterprise_id,
                    principal_id=principal_id,
                ),
                "effect": scope.effect,
            }
            for scope in assignment.scopes
        ]
        normalized.append(
            {
                "role_key": assignment.role_key,
                "role_name": role_names[assignment.role_key],
                "scopes": sorted(scopes, key=lambda item: str(item["scope_type"])),
            }
        )
    return sorted(normalized, key=lambda item: str(item["role_key"]))


def _normalize_scope_ids(
    *,
    scope_type: str,
    scope_ids: list[str],
    enterprise_id: str | None,
    principal_id: str,
) -> list[str]:
    if scope_type == "self":
        invalid = [value for value in scope_ids if value not in {"$self", principal_id}]
        if invalid:
            raise ApiProblem(
                status_code=422,
                code="identity.self_scope_invalid",
                message="本人范围只能指向目标账号主体",
            )
        return [principal_id]
    if scope_type == "enterprise" and enterprise_id is not None:
        invalid = [value for value in scope_ids if value not in {"$enterprise", enterprise_id}]
        if invalid:
            raise ApiProblem(
                status_code=422,
                code="identity.enterprise_scope_invalid",
                message="企业范围不能越过当前企业边界",
            )
        return [enterprise_id]
    return sorted(scope_ids)


def _current_configuration_snapshot(
    session: Session,
    account: UserAccount,
    principal: Principal,
) -> dict[str, object]:
    membership = session.scalar(
        select(Membership).where(
            Membership.enterprise_id == account.enterprise_id,
            Membership.principal_id == principal.id,
            Membership.is_primary.is_(True),
            Membership.status == "active",
        )
    )
    if membership is None:
        raise ApiProblem(
            status_code=409,
            code="identity.primary_membership_missing",
            message="目标账号缺少有效的主任职",
        )
    org = session.get(OrgUnit, membership.org_unit_id)
    position = session.get(Position, membership.position_id)
    assignments = list(
        session.scalars(
            select(RoleAssignment).where(
                RoleAssignment.enterprise_id == account.enterprise_id,
                RoleAssignment.principal_id == principal.id,
                RoleAssignment.status == "active",
                RoleAssignment.valid_to.is_(None),
            )
        )
    )
    role_ids = [item.access_role_id for item in assignments]
    roles = {
        item.id: item
        for item in session.scalars(select(AccessRole).where(AccessRole.id.in_(role_ids)))
    }
    role_snapshots: list[dict[str, object]] = []
    for assignment in assignments:
        role = roles[assignment.access_role_id]
        grants = list(
            session.scalars(
                select(ScopeGrant).where(
                    ScopeGrant.role_assignment_id == assignment.id,
                    ScopeGrant.valid_to.is_(None),
                )
            )
        )
        role_snapshots.append(
            {
                "role_key": role.role_key,
                "role_name": role.name,
                "scopes": sorted(
                    [
                        {
                            "scope_type": grant.scope_type,
                            "scope_ids": sorted(grant.scope_ids),
                            "effect": grant.effect,
                        }
                        for grant in grants
                    ],
                    key=lambda item: str(item["scope_type"]),
                ),
            }
        )
    return _configuration_snapshot(
        account_key=account.account_key,
        login_name=account.local_login_name,
        display_name=principal.display_name,
        email=account.email,
        experience_role_key=account.experience_role_key,
        org_key=org.org_key if org else "",
        position_key=position.position_key if position else "",
        status=account.status,
        role_assignments=sorted(role_snapshots, key=lambda item: str(item["role_key"])),
        version=account.version,
    )


def _configuration_snapshot(
    *,
    account_key: str,
    login_name: str,
    display_name: str,
    email: str | None,
    experience_role_key: str,
    org_key: str,
    position_key: str,
    status: str,
    role_assignments: list[dict[str, object]],
    version: int,
) -> dict[str, object]:
    return {
        "account_key": account_key,
        "login_name": login_name,
        "display_name": display_name,
        "email": email,
        "experience_role_key": experience_role_key,
        "org_key": org_key,
        "position_key": position_key,
        "status": status,
        "role_assignments": role_assignments,
        "version": version,
    }


def _management_event(
    *,
    actor: ActorContext,
    account: UserAccount,
    event_type: str,
    before_snapshot: dict[str, object],
    after_snapshot: dict[str, object],
    changed_fields: list[str],
    reason: str,
    idempotency_key: str,
    payload_hash: str,
    now: datetime,
) -> IdentityManagementEvent:
    return IdentityManagementEvent(
        id=f"identity_event_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        event_type=event_type,
        target_principal_id=account.principal_id,
        target_account_id=account.id,
        actor_principal_id=actor.principal_id,
        actor_snapshot=actor.snapshot(),
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        changed_fields=changed_fields,
        reason=reason,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        request_id=actor.request_id,
        run_id=actor.run_id,
        occurred_at=now,
    )


def _mutation_response(
    database: Database,
    *,
    account_id: str,
    event_id: str,
    operation: str,
    replayed: bool,
) -> IdentityUserMutationResponse:
    overview = identity_admin_overview(
        database,
        enterprise_id=_account_enterprise(database, account_id),
    )
    account = next((item for item in overview.users if item.account_id == account_id), None)
    if account is None:
        raise ApiProblem(
            status_code=500,
            code="identity.mutation_result_missing",
            message="身份管理操作已保存，但无法重建目标账号视图",
        )
    return IdentityUserMutationResponse(
        operation=operation,  # type: ignore[arg-type]
        account=account,
        event_id=event_id,
        replayed=replayed,
    )


def _account_enterprise(database: Database, account_id: str) -> str:
    with database.session() as session:
        account = session.get(UserAccount, account_id)
        if account is None:
            raise ApiProblem(
                status_code=404,
                code="identity.user_not_found",
                message="目标企业账号不存在",
            )
        return account.enterprise_id


def _available_account_key(session: Session, enterprise_id: str, login_name: str) -> str:
    base = f"account_{_key_fragment(login_name)}"
    if not session.scalar(
        select(UserAccount.id).where(
            UserAccount.enterprise_id == enterprise_id,
            UserAccount.account_key == base,
        )
    ):
        return base
    return f"{base}_{uuid4().hex[:8]}"


def _available_principal_key(session: Session, enterprise_id: str, login_name: str) -> str:
    base = f"principal-{_key_fragment(login_name).replace('_', '-')}"
    if not session.scalar(
        select(Principal.id).where(
            Principal.enterprise_id == enterprise_id,
            Principal.principal_key == base,
        )
    ):
        return base
    return f"{base}-{uuid4().hex[:8]}"


def _key_fragment(value: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in value)


def _payload_hash(payload: dict[str, object]) -> str:
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(material.encode()).hexdigest()
