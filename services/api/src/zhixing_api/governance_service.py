from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from zhixing_api.actor_context import ActorContext, require_permission
from zhixing_api.data_models import (
    AuthSession,
    BusinessUnit,
    ConsolidationProfile,
    Enterprise,
    EnterpriseGroup,
    EnterpriseMembership,
    EnterpriseScopeGrant,
    PlatformEvent,
    Principal,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.governance_schemas import (
    BusinessUnitRequest,
    ConsolidationRequest,
    MembershipRequest,
    OrganizationRequest,
)
from zhixing_api.scope_context import build_scope_context


def _view(row: Any) -> dict[str, Any]:
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


def _enterprise(session: Session, key: str, *, lock: bool = True) -> Enterprise:
    row = session.get(Enterprise, key, with_for_update=lock)
    if row is None:
        raise ApiProblem(status_code=404, code="governance.enterprise_missing",
                         message="法人不存在")
    return row


def _governable_enterprises(database: Database, actor: ActorContext) -> tuple[str, ...]:
    context = build_scope_context(database, actor, selection={"scope_level": "group"})
    now = datetime.now(UTC)
    effects = [(scope.scope_type, key, scope.effect)
               for scope in actor.scopes for key in scope.scope_ids]
    with database.session() as session:
        effects.extend((row.scope_type, row.scope_id, row.effect) for row in session.scalars(
            select(EnterpriseScopeGrant).where(
                EnterpriseScopeGrant.principal_id == actor.principal_id,
                EnterpriseScopeGrant.status == "active", EnterpriseScopeGrant.valid_from <= now,
                or_(EnterpriseScopeGrant.valid_to.is_(None), EnterpriseScopeGrant.valid_to > now))))
    group_allowed = ("group", context.group_id, "allow") in effects
    if ("group", context.group_id, "deny") in effects:
        return ()
    return tuple(key for key in context.allowed_enterprise_ids
                 if (group_allowed or ("enterprise", key, "allow") in effects)
                 and ("enterprise", key, "deny") not in effects)


def _authorize(database: Database, actor: ActorContext, enterprise_id: str | None = None) -> None:
    require_permission(actor, "identity.user.manage", database,
                       resource_type="group-governance", resource_key=enterprise_id or "group")
    if (enterprise_id or actor.enterprise_id) not in _governable_enterprises(database, actor):
        raise ApiProblem(status_code=403, code="governance.enterprise_denied",
                         message="需要法人或集团治理范围授权")


def _group_authorized(session: Session, actor: ActorContext, group_id: str | None) -> None:
    now = datetime.now(UTC)
    effects = [scope.effect for scope in actor.scopes
               if scope.scope_type == "group" and group_id in scope.scope_ids]
    effects += list(session.scalars(select(EnterpriseScopeGrant.effect).where(
        EnterpriseScopeGrant.principal_id == actor.principal_id,
        EnterpriseScopeGrant.scope_type == "group", EnterpriseScopeGrant.scope_id == group_id,
        EnterpriseScopeGrant.status == "active", EnterpriseScopeGrant.valid_from <= now,
        or_(EnterpriseScopeGrant.valid_to.is_(None), EnterpriseScopeGrant.valid_to > now),
    )))
    if group_id is None or "allow" not in effects or "deny" in effects:
        raise ApiProblem(status_code=403, code="governance.group_denied",
                         message="需要集团治理范围授权")


def _event(session: Session, actor: ActorContext, kind: str, object_id: str) -> None:
    session.add(PlatformEvent(id=f"evt_{uuid4().hex}", enterprise_id=actor.enterprise_id,
                event_type=f"governance.{kind}", severity="info", title="组织治理变更",
                detail=f"principal_id={actor.principal_id}; object_id={object_id}",
                occurred_at=datetime.now(UTC)))


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise ApiProblem(status_code=409, code="governance.identifier_conflict",
                         message="标识已存在或关联关系无效") from None


def _flush(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise ApiProblem(status_code=409, code="governance.identifier_conflict",
                         message="标识已存在或关联关系无效") from None


def governance_overview(database: Database, actor: ActorContext) -> dict[str, object]:
    _authorize(database, actor)
    context = build_scope_context(database, actor, selection={"scope_level": "group"})
    ids = _governable_enterprises(database, actor)
    with database.session() as session:
        enterprise = _enterprise(session, actor.enterprise_id, lock=False)
        group = session.get(EnterpriseGroup, enterprise.group_id) if enterprise.group_id else None
        manager = True
        try:
            _group_authorized(session, actor, enterprise.group_id)
        except ApiProblem:
            manager = False
        return {
            "schema_version": 1, "group": _view(group) if group else None,
            "can_manage_group": manager,
            "enterprises": [_view(row) for row in session.scalars(select(Enterprise).where(
                Enterprise.id.in_(ids)).order_by(Enterprise.name))],
            "business_units": [_view(row) for row in session.scalars(select(BusinessUnit).where(
                BusinessUnit.enterprise_id.in_(ids)).order_by(BusinessUnit.name))],
            "memberships": [_view(row) for row in session.scalars(select(EnterpriseMembership)
                .where(EnterpriseMembership.enterprise_id.in_(ids)))],
            "principals": [{"id": row.id, "display_name": row.display_name,
                            "enterprise_id": row.enterprise_id} for row in session.scalars(
                select(Principal).where(Principal.enterprise_id.in_(ids),
                                        Principal.status == "active"))],
            "consolidation_profiles": [_view(row) for row in session.scalars(
                select(ConsolidationProfile).where(
                    ConsolidationProfile.group_id == context.group_id)
                .order_by(ConsolidationProfile.created_at.desc()))] if group else [],
        }


def save_group(database: Database, actor: ActorContext,
               payload: OrganizationRequest) -> dict[str, object]:
    _authorize(database, actor, actor.enterprise_id)
    with database.session() as session:
        enterprise = _enterprise(session, actor.enterprise_id)
        now = datetime.now(UTC)
        if enterprise.group_id:
            _group_authorized(session, actor, enterprise.group_id)
            group = session.get(EnterpriseGroup, enterprise.group_id, with_for_update=True)
            if group is None:
                raise ApiProblem(status_code=404, code="governance.group_missing",
                                 message="集团不存在")
        else:
            if "identity.access.manage" not in actor.permissions:
                raise ApiProblem(status_code=403, code="governance.bootstrap_denied",
                                 message="创建集团需要身份与访问管理权限")
            group = EnterpriseGroup(id=f"group_{uuid4().hex}", status="active",
                                    created_at=now, updated_at=now)
            session.add(group)
            group.code, group.name, group.timezone = payload.code, payload.name, payload.timezone
            _flush(session)
            enterprise.group_id = group.id
            session.add(EnterpriseScopeGrant(id=f"grant_{uuid4().hex}",
                principal_id=actor.principal_id, group_id=group.id, scope_type="group",
                scope_id=group.id, effect="allow", status="active", valid_from=now,
                created_at=now, updated_at=now))
        group.code, group.name, group.timezone = payload.code, payload.name, payload.timezone
        group.updated_at = now
        _event(session, actor, "group.saved", group.id)
        _commit(session)
        return _view(group)


def save_enterprise(database: Database, actor: ActorContext, payload: OrganizationRequest,
                    *, enterprise_id: str | None = None) -> dict[str, object]:
    _authorize(database, actor, enterprise_id)
    with database.session() as session:
        home = _enterprise(session, actor.enterprise_id)
        if enterprise_id:
            row = session.get(Enterprise, enterprise_id, with_for_update=True)
            if row is None or row.group_id != home.group_id:
                raise ApiProblem(status_code=404, code="governance.enterprise_missing",
                                 message="法人不存在")
        else:
            _group_authorized(session, actor, home.group_id)
            now = datetime.now(UTC)
            row = Enterprise(id=f"ent_{uuid4().hex}", group_id=home.group_id, created_at=now)
            session.add(row)
            row.code, row.name, row.timezone = payload.code, payload.name, payload.timezone
            _flush(session)
            session.add(EnterpriseMembership(id=f"member_{uuid4().hex}",
                principal_id=actor.principal_id, enterprise_id=row.id,
                membership_type="group_admin",
                is_primary=False, status="active", valid_from=now, version=1,
                created_at=now, updated_at=now))
        row.code, row.name, row.timezone = payload.code, payload.name, payload.timezone
        _event(session, actor, "enterprise.saved", row.id)
        _commit(session)
        return _view(row)


def save_business_unit(database: Database, actor: ActorContext, payload: BusinessUnitRequest,
                       *, unit_id: str | None = None) -> dict[str, object]:
    _authorize(database, actor, payload.enterprise_id)
    with database.session() as session:
        row = session.get(BusinessUnit, unit_id, with_for_update=True) if unit_id else None
        if unit_id and (row is None or row.enterprise_id != payload.enterprise_id):
            raise ApiProblem(status_code=404, code="governance.unit_missing",
                             message="业务单元不存在")
        if row and payload.expected_version != row.version:
            raise ApiProblem(status_code=409, code="governance.version_conflict",
                             message="记录已变更，请刷新后重试")
        parent_id = payload.parent_id
        seen = {unit_id} if unit_id else set()
        while parent_id:
            parent = session.get(BusinessUnit, parent_id)
            if (parent_id in seen or parent is None or parent.status != "active"
                    or parent.enterprise_id != payload.enterprise_id):
                raise ApiProblem(status_code=422, code="governance.parent_invalid",
                                 message="上级单元跨法人、停用或形成循环")
            seen.add(parent_id)
            parent_id = parent.parent_id
        now = datetime.now(UTC)
        if row is None:
            row = BusinessUnit(id=f"bu_{uuid4().hex}", enterprise_id=payload.enterprise_id,
                               created_at=now, version=0)
            session.add(row)
        for key, value in payload.model_dump(exclude={"expected_version", "enterprise_id"}).items():
            setattr(row, key, value)
        row.version += 1
        row.updated_at = now
        _event(session, actor, "business_unit.saved", row.id)
        _commit(session)
        return _view(row)


def save_membership(database: Database, actor: ActorContext,
                    payload: MembershipRequest) -> dict[str, object]:
    _authorize(database, actor, payload.enterprise_id)
    require_permission(actor, "identity.access.manage", database,
                       resource_type="enterprise-membership", resource_key=payload.enterprise_id)
    with database.session() as session:
        enterprise = _enterprise(session, payload.enterprise_id)
        _group_authorized(session, actor, enterprise.group_id)
        principal = session.get(Principal, payload.principal_id)
        home = session.get(Enterprise, principal.enterprise_id) if principal else None
        if home is None or home.group_id != enterprise.group_id:
            raise ApiProblem(status_code=422, code="governance.principal_scope_invalid",
                             message="主体不属于当前集团")
        if home.id == enterprise.id and payload.status == "revoked":
            raise ApiProblem(status_code=409, code="governance.home_membership_protected",
                             message="主法人账号请通过账号停用流程处理")
        if payload.principal_id == actor.principal_id and payload.status == "revoked":
            raise ApiProblem(status_code=409, code="governance.self_revoke_blocked",
                             message="不能撤销当前管理员自己的成员关系")
        row = session.scalar(select(EnterpriseMembership).where(
            EnterpriseMembership.principal_id == payload.principal_id,
            EnterpriseMembership.enterprise_id == payload.enterprise_id).with_for_update())
        if row and row.version != payload.expected_version:
            raise ApiProblem(status_code=409, code="governance.version_conflict",
                             message="成员关系已变更，请刷新后重试")
        now = datetime.now(UTC)
        if row is None:
            row = EnterpriseMembership(id=f"member_{uuid4().hex}",
                principal_id=payload.principal_id, enterprise_id=payload.enterprise_id,
                membership_type="member", is_primary=False, valid_from=now, version=0,
                created_at=now, updated_at=now)
            session.add(row)
        row.status, row.updated_at = payload.status, now
        row.valid_to = now if payload.status == "revoked" else None
        row.version += 1
        if payload.status == "revoked":
            for login in session.scalars(select(AuthSession).join(
                UserAccount, UserAccount.id == AuthSession.user_account_id
            ).where(UserAccount.principal_id == payload.principal_id,
                    AuthSession.enterprise_id == payload.enterprise_id)):
                login.revoked_at = now
        _event(session, actor, "membership.saved", row.id)
        _commit(session)
        return _view(row)


def save_consolidation(database: Database, actor: ActorContext,
                       payload: ConsolidationRequest) -> dict[str, object]:
    _authorize(database, actor)
    with database.session() as session:
        enterprise = _enterprise(session, actor.enterprise_id)
        _group_authorized(session, actor, enterprise.group_id)
        session.get(EnterpriseGroup, enterprise.group_id, with_for_update=True)
        old = list(session.scalars(select(ConsolidationProfile).where(
            ConsolidationProfile.group_id == enterprise.group_id,
            ConsolidationProfile.status == "active").with_for_update()))
        now = datetime.now(UTC)
        for profile in old:
            profile.status, profile.updated_at = "superseded", now
        row = ConsolidationProfile(id=f"profile_{uuid4().hex}", group_id=enterprise.group_id,
            status="active", created_at=now, updated_at=now, **payload.model_dump())
        session.add(row)
        _event(session, actor, "consolidation.published", row.id)
        _commit(session)
        return _view(row)
