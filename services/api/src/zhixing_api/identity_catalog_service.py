from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal, cast
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext
from zhixing_api.data_models import (
    AccessRole,
    AccessRolePermission,
    IdentityCatalogEvent,
    Membership,
    OrgUnit,
    PermissionDefinition,
    Position,
    RoleAssignment,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.identity_schemas import (
    IdentityAccessRoleCreateRequest,
    IdentityAccessRoleUpdateRequest,
    IdentityCatalogMutationResponse,
    IdentityOrgUnitCreateRequest,
    IdentityOrgUnitUpdateRequest,
    IdentityPositionCreateRequest,
    IdentityPositionUpdateRequest,
)
from zhixing_api.identity_seed import role_permission_id


def create_org_unit(
    database: Database,
    *,
    actor: ActorContext,
    payload: IdentityOrgUnitCreateRequest,
) -> IdentityCatalogMutationResponse:
    return _mutate_org_unit(database, actor=actor, payload=payload, target=None)


def update_org_unit(
    database: Database,
    *,
    actor: ActorContext,
    org_key: str,
    payload: IdentityOrgUnitUpdateRequest,
) -> IdentityCatalogMutationResponse:
    return _mutate_org_unit(database, actor=actor, payload=payload, target=org_key)


def create_position(
    database: Database,
    *,
    actor: ActorContext,
    payload: IdentityPositionCreateRequest,
) -> IdentityCatalogMutationResponse:
    return _mutate_position(database, actor=actor, payload=payload, target=None)


def update_position(
    database: Database,
    *,
    actor: ActorContext,
    position_key: str,
    payload: IdentityPositionUpdateRequest,
) -> IdentityCatalogMutationResponse:
    return _mutate_position(database, actor=actor, payload=payload, target=position_key)


def create_access_role(
    database: Database,
    *,
    actor: ActorContext,
    payload: IdentityAccessRoleCreateRequest,
) -> IdentityCatalogMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = datetime.now(UTC)
    with database.session() as session:
        replay = _catalog_replay(
            session,
            actor=actor,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
        )
        if replay is not None:
            return _response("created", "access_role", replay.target_key, replay.id, True)
        permissions = _validate_permissions(session, payload.permissions)
        if session.scalar(
            select(AccessRole.id).where(
                AccessRole.enterprise_id == actor.enterprise_id,
                AccessRole.role_key == payload.role_key,
            )
        ):
            raise ApiProblem(
                status_code=409,
                code="identity.access_role_conflict",
                message="该访问角色标识已存在",
                details={"role_key": payload.role_key},
            )
        role = AccessRole(
            id=f"role_{uuid4().hex}",
            enterprise_id=actor.enterprise_id,
            role_key=payload.role_key,
            name=payload.name.strip(),
            description=payload.description.strip(),
            version="1.0.0",
            revision=1,
            status="active",
            created_at=now,
        )
        session.add(role)
        session.flush()
        _replace_role_permissions(session, role.id, permissions)
        after = _role_snapshot(role, permissions)
        event = _catalog_event(
            actor=actor,
            event_type="identity.access_role.created",
            target_type="access_role",
            target_key=role.role_key,
            before={},
            after=after,
            changed_fields=["role", "permissions"],
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            now=now,
        )
        session.add(event)
        session.commit()
        return _response("created", "access_role", role.role_key, event.id, False)


def update_access_role(
    database: Database,
    *,
    actor: ActorContext,
    role_key: str,
    payload: IdentityAccessRoleUpdateRequest,
) -> IdentityCatalogMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = datetime.now(UTC)
    with database.session() as session:
        replay = _catalog_replay(
            session,
            actor=actor,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
        )
        if replay is not None:
            return _response("updated", "access_role", replay.target_key, replay.id, True)
        role = _find_role(session, actor.enterprise_id, role_key)
        if role.revision != payload.expected_revision:
            raise ApiProblem(
                status_code=409,
                code="identity.access_role_version_conflict",
                message="访问角色已被其他操作更新，请刷新后重试",
                details={
                    "role_key": role_key,
                    "expected_revision": payload.expected_revision,
                    "actual_revision": role.revision,
                },
            )
        permissions = _validate_permissions(session, payload.permissions)
        before_permissions = _role_permissions(session, role.id)
        before = _role_snapshot(role, before_permissions)
        actor_assignment = session.scalar(
            select(RoleAssignment.id).where(
                RoleAssignment.enterprise_id == actor.enterprise_id,
                RoleAssignment.principal_id == actor.principal_id,
                RoleAssignment.access_role_id == role.id,
                RoleAssignment.status == "active",
            )
        )
        if actor_assignment is not None and (
            payload.status != "active" or "identity.access.manage" not in permissions
        ):
            raise ApiProblem(
                status_code=409,
                code="identity.self_lockout_denied",
                message="当前管理账号不能停用或削弱自身正在使用的访问角色",
                details={"role_key": role.role_key},
            )
        role.name = payload.name.strip()
        role.description = payload.description.strip()
        role.status = payload.status
        role.revision += 1
        _replace_role_permissions(session, role.id, permissions)
        after = _role_snapshot(role, permissions)
        changed_fields = [
            field
            for field in ("name", "description", "status", "permissions")
            if before[field] != after[field]
        ]
        if not changed_fields:
            raise ApiProblem(
                status_code=409,
                code="identity.access_role_unchanged",
                message="访问角色没有发生变化",
                details={"role_key": role_key},
            )
        event = _catalog_event(
            actor=actor,
            event_type="identity.access_role.updated",
            target_type="access_role",
            target_key=role.role_key,
            before=before,
            after=after,
            changed_fields=changed_fields,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            now=now,
        )
        session.add(event)
        session.commit()
        return _response("updated", "access_role", role.role_key, event.id, False)


def _mutate_org_unit(
    database: Database,
    *,
    actor: ActorContext,
    payload: IdentityOrgUnitCreateRequest | IdentityOrgUnitUpdateRequest,
    target: str | None,
) -> IdentityCatalogMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = datetime.now(UTC)
    with database.session() as session:
        replay = _catalog_replay(
            session,
            actor=actor,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
        )
        if replay is not None:
            return _response(
                "created" if target is None else "updated",
                "org_unit",
                replay.target_key,
                replay.id,
                True,
            )
        parent = _resolve_parent(session, actor.enterprise_id, payload.parent_org_key)
        if target is None:
            create_payload = cast(IdentityOrgUnitCreateRequest, payload)
            if session.scalar(
                select(OrgUnit.id).where(
                    OrgUnit.enterprise_id == actor.enterprise_id,
                    OrgUnit.org_key == create_payload.org_key,
                )
            ):
                raise ApiProblem(
                    status_code=409, code="identity.org_key_conflict", message="该组织标识已存在"
                )
            org = OrgUnit(
                id=f"org_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                org_key=create_payload.org_key,
                name=create_payload.name.strip(),
                unit_type=create_payload.unit_type.strip(),
                parent_org_unit_id=parent.id if parent else None,
                status="active",
                version=1,
                valid_from=now,
                valid_to=None,
            )
            session.add(org)
            session.flush()
            before: dict[str, object] = {}
            operation = "created"
            changed_fields = ["org_unit"]
        else:
            update_payload = cast(IdentityOrgUnitUpdateRequest, payload)
            org = _find_org(session, actor.enterprise_id, target)
            if org.version != update_payload.expected_version:
                raise ApiProblem(
                    status_code=409,
                    code="identity.org_version_conflict",
                    message="组织已被其他操作更新，请刷新后重试",
                )
            _ensure_parent_safe(session, org, parent)
            if update_payload.status == "suspended" and org.status == "active":
                active_positions = int(
                    session.scalar(
                        select(func.count(Position.id)).where(
                            Position.org_unit_id == org.id,
                            Position.status == "active",
                        )
                    )
                    or 0
                )
                if active_positions:
                    raise ApiProblem(
                        status_code=409,
                        code="identity.org_has_active_positions",
                        message="组织仍有生效岗位，请先停用或迁移岗位",
                    )
                active_children = int(
                    session.scalar(
                        select(func.count(OrgUnit.id)).where(
                            OrgUnit.parent_org_unit_id == org.id,
                            OrgUnit.status == "active",
                        )
                    )
                    or 0
                )
                if active_children:
                    raise ApiProblem(
                        status_code=409,
                        code="identity.org_has_active_children",
                        message="组织仍有生效下级组织，请先停用或迁移下级组织",
                    )
            before = _org_snapshot(org)
            org.name = update_payload.name.strip()
            org.unit_type = update_payload.unit_type.strip()
            org.parent_org_unit_id = parent.id if parent else None
            org.status = update_payload.status
            org.version += 1
            operation = "updated"
            after_preview = _org_snapshot(org)
            changed_fields = [
                field
                for field in ("name", "unit_type", "parent_org_unit_id", "status")
                if before[field] != after_preview[field]
            ]
            if not changed_fields:
                raise ApiProblem(
                    status_code=409, code="identity.org_unchanged", message="组织没有发生变化"
                )
        after = _org_snapshot(org)
        event = _catalog_event(
            actor=actor,
            event_type=f"identity.org_unit.{operation}",
            target_type="org_unit",
            target_key=org.org_key,
            before=before,
            after=after,
            changed_fields=changed_fields,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            now=now,
        )
        session.add(event)
        session.commit()
        return _response(operation, "org_unit", org.org_key, event.id, False)


def _mutate_position(
    database: Database,
    *,
    actor: ActorContext,
    payload: IdentityPositionCreateRequest | IdentityPositionUpdateRequest,
    target: str | None,
) -> IdentityCatalogMutationResponse:
    payload_hash = _payload_hash(payload.model_dump(mode="json"))
    now = datetime.now(UTC)
    with database.session() as session:
        replay = _catalog_replay(
            session,
            actor=actor,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
        )
        if replay is not None:
            return _response(
                "created" if target is None else "updated",
                "position",
                replay.target_key,
                replay.id,
                True,
            )
        org = _find_org(session, actor.enterprise_id, payload.org_key)
        if org.status != "active":
            raise ApiProblem(
                status_code=422, code="identity.org_inactive", message="岗位所属组织未生效"
            )
        if target is None:
            create_payload = cast(IdentityPositionCreateRequest, payload)
            if session.scalar(
                select(Position.id).where(
                    Position.enterprise_id == actor.enterprise_id,
                    Position.position_key == create_payload.position_key,
                )
            ):
                raise ApiProblem(
                    status_code=409,
                    code="identity.position_key_conflict",
                    message="该岗位标识已存在",
                )
            position = Position(
                id=f"position_{uuid4().hex}",
                enterprise_id=actor.enterprise_id,
                org_unit_id=org.id,
                position_key=create_payload.position_key,
                name=create_payload.name.strip(),
                position_level=create_payload.position_level.strip(),
                status="active",
                version=1,
                valid_from=now,
                valid_to=None,
            )
            session.add(position)
            session.flush()
            before: dict[str, object] = {}
            operation = "created"
            changed_fields = ["position"]
        else:
            update_payload = cast(IdentityPositionUpdateRequest, payload)
            position = _find_position(session, actor.enterprise_id, target)
            if position.version != update_payload.expected_version:
                raise ApiProblem(
                    status_code=409,
                    code="identity.position_version_conflict",
                    message="岗位已被其他操作更新，请刷新后重试",
                )
            before = _position_snapshot(session, position)
            if update_payload.status == "suspended" and position.status == "active":
                active_members = int(
                    session.scalar(
                        select(func.count(Membership.id)).where(
                            Membership.position_id == position.id,
                            Membership.status == "active",
                        )
                    )
                    or 0
                )
                if active_members:
                    raise ApiProblem(
                        status_code=409,
                        code="identity.position_has_members",
                        message="岗位仍有生效任职，请先调整人员任职",
                    )
            if position.org_unit_id != org.id:
                active_members = int(
                    session.scalar(
                        select(func.count(Membership.id)).where(
                            Membership.position_id == position.id,
                            Membership.status == "active",
                        )
                    )
                    or 0
                )
                if active_members:
                    raise ApiProblem(
                        status_code=409,
                        code="identity.position_move_has_members",
                        message="岗位仍有生效任职，不能直接迁移组织",
                    )
            position.org_unit_id = org.id
            position.name = update_payload.name.strip()
            position.position_level = update_payload.position_level.strip()
            position.status = update_payload.status
            position.version += 1
            operation = "updated"
            after_preview = _position_snapshot(session, position)
            changed_fields = [
                field
                for field in ("name", "position_level", "org_key", "status")
                if before[field] != after_preview[field]
            ]
            if not changed_fields:
                raise ApiProblem(
                    status_code=409, code="identity.position_unchanged", message="岗位没有发生变化"
                )
        after = _position_snapshot(session, position)
        event = _catalog_event(
            actor=actor,
            event_type=f"identity.position.{operation}",
            target_type="position",
            target_key=position.position_key,
            before=before,
            after=after,
            changed_fields=changed_fields,
            reason=payload.reason,
            idempotency_key=payload.client_request_key,
            payload_hash=payload_hash,
            now=now,
        )
        session.add(event)
        session.commit()
        return _response(operation, "position", position.position_key, event.id, False)


def _find_org(session: Session, enterprise_id: str, org_key: str) -> OrgUnit:
    org = session.scalar(
        select(OrgUnit).where(OrgUnit.enterprise_id == enterprise_id, OrgUnit.org_key == org_key)
    )
    if org is None:
        raise ApiProblem(
            status_code=404,
            code="identity.org_not_found",
            message="组织不存在",
            details={"org_key": org_key},
        )
    return org


def _find_position(session: Session, enterprise_id: str, position_key: str) -> Position:
    position = session.scalar(
        select(Position).where(
            Position.enterprise_id == enterprise_id, Position.position_key == position_key
        )
    )
    if position is None:
        raise ApiProblem(
            status_code=404,
            code="identity.position_not_found",
            message="岗位不存在",
            details={"position_key": position_key},
        )
    return position


def _find_role(session: Session, enterprise_id: str, role_key: str) -> AccessRole:
    role = session.scalar(
        select(AccessRole)
        .where(AccessRole.enterprise_id == enterprise_id, AccessRole.role_key == role_key)
        .order_by(AccessRole.created_at.desc())
    )
    if role is None:
        raise ApiProblem(
            status_code=404,
            code="identity.access_role_not_found",
            message="访问角色不存在",
            details={"role_key": role_key},
        )
    return role


def _resolve_parent(session: Session, enterprise_id: str, parent_key: str | None) -> OrgUnit | None:
    if not parent_key:
        return None
    parent = _find_org(session, enterprise_id, parent_key)
    if parent.status != "active":
        raise ApiProblem(
            status_code=422, code="identity.parent_org_inactive", message="上级组织未生效"
        )
    return parent


def _ensure_parent_safe(session: Session, org: OrgUnit, parent: OrgUnit | None) -> None:
    if parent is None:
        return
    if parent.id == org.id:
        raise ApiProblem(
            status_code=422, code="identity.org_cycle", message="组织不能设置自身为上级"
        )
    seen: set[str] = {org.id}
    cursor: OrgUnit | None = parent
    while cursor is not None:
        if cursor.id in seen:
            raise ApiProblem(
                status_code=422, code="identity.org_cycle", message="组织层级不能形成循环"
            )
        seen.add(cursor.id)
        cursor = (
            session.get(OrgUnit, cursor.parent_org_unit_id) if cursor.parent_org_unit_id else None
        )


def _validate_permissions(session: Session, permission_keys: list[str]) -> list[str]:
    normalized = sorted({key.strip() for key in permission_keys if key.strip()})
    if len(normalized) != len(permission_keys):
        raise ApiProblem(
            status_code=422,
            code="identity.permission_list_invalid",
            message="权限列表包含空值或重复项",
        )
    found = set(
        session.scalars(
            select(PermissionDefinition.permission_key).where(
                PermissionDefinition.permission_key.in_(normalized),
                PermissionDefinition.status == "active",
            )
        )
    )
    missing = [key for key in normalized if key not in found]
    if missing:
        raise ApiProblem(
            status_code=422,
            code="identity.permission_not_found",
            message="权限目录中不存在所选权限",
            details={"permission_keys": missing},
        )
    return normalized


def _replace_role_permissions(session: Session, role_id: str, permission_keys: list[str]) -> None:
    permissions = {
        item.permission_key: item
        for item in session.scalars(
            select(PermissionDefinition).where(
                PermissionDefinition.permission_key.in_(permission_keys)
            )
        )
    }
    session.execute(
        delete(AccessRolePermission).where(AccessRolePermission.access_role_id == role_id)
    )
    for key in sorted(set(permission_keys)):
        session.add(
            AccessRolePermission(
                id=role_permission_id(role_id, key),
                access_role_id=role_id,
                permission_id=permissions[key].id,
                effect="allow",
            )
        )


def _role_permissions(session: Session, role_id: str) -> list[str]:
    rows = session.execute(
        select(PermissionDefinition.permission_key)
        .join(AccessRolePermission, AccessRolePermission.permission_id == PermissionDefinition.id)
        .where(
            AccessRolePermission.access_role_id == role_id, AccessRolePermission.effect == "allow"
        )
    ).scalars()
    return sorted(rows)


def _org_snapshot(org: OrgUnit) -> dict[str, object]:
    return {
        "org_key": org.org_key,
        "name": org.name,
        "unit_type": org.unit_type,
        "parent_org_unit_id": org.parent_org_unit_id,
        "status": org.status,
        "version": org.version,
    }


def _position_snapshot(session: Session, position: Position) -> dict[str, object]:
    org = session.get(OrgUnit, position.org_unit_id)
    return {
        "position_key": position.position_key,
        "name": position.name,
        "position_level": position.position_level,
        "org_key": org.org_key if org else "",
        "status": position.status,
        "version": position.version,
    }


def _role_snapshot(role: AccessRole, permissions: list[str]) -> dict[str, object]:
    return {
        "role_key": role.role_key,
        "name": role.name,
        "description": role.description,
        "version": role.version,
        "revision": role.revision,
        "status": role.status,
        "permissions": sorted(permissions),
    }


def _catalog_replay(
    session: Session, *, actor: ActorContext, idempotency_key: str, payload_hash: str
) -> IdentityCatalogEvent | None:
    event = session.scalar(
        select(IdentityCatalogEvent).where(
            IdentityCatalogEvent.enterprise_id == actor.enterprise_id,
            IdentityCatalogEvent.idempotency_key == idempotency_key,
        )
    )
    if event is None:
        return None
    if event.payload_hash != payload_hash:
        raise ApiProblem(
            status_code=409,
            code="identity.catalog_idempotency_conflict",
            message="同一请求键已用于不同的身份目录操作",
        )
    return event


def _catalog_event(
    *,
    actor: ActorContext,
    event_type: str,
    target_type: str,
    target_key: str,
    before: dict[str, object],
    after: dict[str, object],
    changed_fields: list[str],
    reason: str,
    idempotency_key: str,
    payload_hash: str,
    now: datetime,
) -> IdentityCatalogEvent:
    return IdentityCatalogEvent(
        id=f"identity_catalog_event_{uuid4().hex}",
        enterprise_id=actor.enterprise_id,
        event_type=event_type,
        target_type=target_type,
        target_key=target_key,
        actor_principal_id=actor.principal_id,
        actor_snapshot=actor.snapshot(),
        before_snapshot=before,
        after_snapshot=after,
        changed_fields=changed_fields,
        reason=reason,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        request_id=actor.request_id,
        run_id=actor.run_id,
        occurred_at=now,
    )


def _response(
    operation: str, target_type: str, target_key: str, event_id: str, replayed: bool
) -> IdentityCatalogMutationResponse:
    return IdentityCatalogMutationResponse(
        operation=cast(Literal["created", "updated"], operation),
        target_type=cast(Literal["org_unit", "position", "access_role"], target_type),
        target_key=target_key,
        event_id=event_id,
        replayed=replayed,
    )


def _payload_hash(payload: dict[str, object]) -> str:
    material = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(material.encode()).hexdigest()
