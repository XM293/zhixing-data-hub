from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select

from zhixing_api.actor_context import ActorContext
from zhixing_api.data_models import (
    BusinessEntity,
    BusinessUnit,
    CanonicalEntityOrigin,
    ConsolidationProfile,
    Enterprise,
    EnterpriseGroup,
    EnterpriseMembership,
    EnterpriseScopeGrant,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem


@dataclass(frozen=True, slots=True)
class ScopeContext:
    group_id: str | None
    group_name: str | None
    enterprise_id: str
    enterprise_name: str
    allowed_enterprise_ids: tuple[str, ...]
    business_unit_ids: tuple[str, ...]
    scope_version: str
    timezone: str
    currency_code: str | None = None
    selected_enterprise_ids: tuple[str, ...] = ()
    store_ids: tuple[str, ...] = ()
    warehouse_ids: tuple[str, ...] = ()
    scope_level: str = "enterprise"
    consolidation_profile_version: str | None = None
    data_as_of: datetime | None = None

    def snapshot(self) -> dict[str, object]:
        return {
            "schema_version": 2,
            "group_id": self.group_id,
            "group_name": self.group_name,
            "enterprise_id": self.enterprise_id,
            "enterprise_name": self.enterprise_name,
            "allowed_enterprise_ids": list(self.allowed_enterprise_ids),
            "business_unit_ids": list(self.business_unit_ids),
            "scope_version": self.scope_version,
            "timezone": self.timezone,
            "currency_code": self.currency_code,
            "base_currency": self.currency_code,
            "current_enterprise_id": self.enterprise_id,
            "selected_enterprise_ids": list(
                self.selected_enterprise_ids
            ),
            "store_ids": list(self.store_ids),
            "warehouse_ids": list(self.warehouse_ids),
            "scope_level": self.scope_level,
            "consolidation_profile_version": self.consolidation_profile_version,
            "data_as_of": self.data_as_of.isoformat() if self.data_as_of else None,
        }


def build_scope_context(
    database: Database, actor: ActorContext, *, selection: dict[str, object] | None = None
) -> ScopeContext:
    selection = selection if selection is not None else (actor.scope_selection or {})
    with database.session() as session:
        enterprise = session.get(Enterprise, actor.enterprise_id)
        if enterprise is None:
            raise LookupError("企业身份边界不存在")
        group = session.get(EnterpriseGroup, enterprise.group_id) if enterprise.group_id else None
        now = datetime.now(UTC)
        memberships = list(
            session.scalars(
                select(EnterpriseMembership.enterprise_id)
                .join(Enterprise, Enterprise.id == EnterpriseMembership.enterprise_id)
                .where(
                    EnterpriseMembership.principal_id == actor.principal_id,
                    Enterprise.group_id == enterprise.group_id,
                    EnterpriseMembership.status == "active",
                    EnterpriseMembership.valid_from <= now,
                    or_(
                        EnterpriseMembership.valid_to.is_(None),
                        EnterpriseMembership.valid_to > now,
                    ),
                )
            )
        )
        member_ids = {actor.enterprise_id, *memberships}
        allowed: dict[str, set[str]] = {}
        denied: dict[str, set[str]] = {}
        for scope in actor.scopes:
            (denied if scope.effect == "deny" else allowed).setdefault(
                scope.scope_type, set()
            ).update(scope.scope_ids)
        grants = session.scalars(select(EnterpriseScopeGrant).where(
            EnterpriseScopeGrant.principal_id == actor.principal_id,
            EnterpriseScopeGrant.status == "active", EnterpriseScopeGrant.valid_from <= now,
            or_(EnterpriseScopeGrant.valid_to.is_(None), EnterpriseScopeGrant.valid_to > now),
        ))
        for grant in grants:
            (denied if grant.effect == "deny" else allowed).setdefault(
                grant.scope_type, set()
            ).add(grant.scope_id)
        authorized = member_ids.intersection(allowed.get("enterprise", set()))
        if enterprise.group_id in allowed.get("group", set()):
            authorized |= member_ids
        # A project/store-scoped role can still work inside its current legal entity.
        if any(allowed.get(kind) for kind in ("business_unit", "store", "warehouse")):
            authorized.add(actor.enterprise_id)
        if enterprise.group_id in denied.get("group", set()):
            authorized.clear()
        authorized -= denied.get("enterprise", set())
        allowed_enterprises = tuple(sorted(authorized))
        level = str(selection.get("scope_level") or "enterprise")
        if level not in {"group", "enterprise", "business_unit", "store", "warehouse"}:
            raise ApiProblem(status_code=422, code="scope.level_invalid", message="范围层级无效")
        requested = selection.get("selected_enterprise_ids")
        if requested:
            if (not isinstance(requested, list)
                    or not all(isinstance(item, str) for item in requested)
                    or not set(requested).issubset(authorized)):
                raise ApiProblem(status_code=403, code="scope.enterprise_denied",
                                 message="选择的法人不在授权范围内")
            selected = tuple(sorted(set(str(item) for item in requested)))
        else:
            selected = (allowed_enterprises if level == "group" else
                        (actor.enterprise_id,) if actor.enterprise_id in authorized else ())
        units = list(session.scalars(select(BusinessUnit).where(
            BusinessUnit.enterprise_id.in_(selected), BusinessUnit.status == "active"
        )))
        object_grants = {kind: allowed.get(kind, set()) - denied.get(kind, set())
                         for kind in ("store", "warehouse")}
        granted_keys = set().union(*object_grants.values())
        known_keys = set(session.scalars(select(BusinessEntity.canonical_key).where(
            BusinessEntity.entity_type.in_(("store", "warehouse")),
            BusinessEntity.canonical_key.in_(granted_keys))))
        object_units = {origin.business_unit_id for entity, origin in session.execute(
            select(BusinessEntity, CanonicalEntityOrigin).join(CanonicalEntityOrigin,
                CanonicalEntityOrigin.entity_id == BusinessEntity.id).where(
                    BusinessEntity.enterprise_id.in_(selected),
                    BusinessEntity.canonical_key.in_(granted_keys),
                    CanonicalEntityOrigin.status == "assigned",
                    CanonicalEntityOrigin.business_unit_id.in_([unit.id for unit in units])))
            if entity.canonical_key in object_grants.get(entity.entity_type, set())}
        visible_units = {unit.id for unit in units if (
            unit.enterprise_id in allowed.get("enterprise", set())
            or enterprise.group_id in allowed.get("group", set())
            or unit.id in allowed.get("business_unit", set())
            or unit.id in object_units
        )} - denied.get("business_unit", set())
        business_units = _selected_ids(selection, "business_unit_ids", visible_units)
        entities = list(session.execute(select(BusinessEntity, CanonicalEntityOrigin).join(
            CanonicalEntityOrigin, CanonicalEntityOrigin.entity_id == BusinessEntity.id
        ).where(BusinessEntity.enterprise_id.in_(selected),
                CanonicalEntityOrigin.status == "assigned",
                CanonicalEntityOrigin.business_unit_id.in_(business_units))))
        visible_entities: dict[str, set[str]] = {"store": set(), "warehouse": set()}
        for entity, origin in entities:
            if entity.entity_type not in visible_entities:
                continue
            kind = entity.entity_type
            if (entity.enterprise_id in allowed.get("enterprise", set())
                    or enterprise.group_id in allowed.get("group", set())
                    or origin.business_unit_id in allowed.get("business_unit", set())
                    or entity.canonical_key in allowed.get(kind, set())):
                visible_entities[kind].add(entity.canonical_key)
        # Preserve existing explicitly granted store/warehouse keys from other providers.
        for kind in visible_entities:
            if actor.enterprise_id in selected and not denied.get("business_unit"):
                visible_entities[kind] |= allowed.get(kind, set()) - known_keys
            visible_entities[kind] -= denied.get(kind, set())
        store_ids = _selected_ids(selection, "store_ids", visible_entities["store"])
        warehouse_ids = _selected_ids(selection, "warehouse_ids", visible_entities["warehouse"])
        profile = session.scalar(
            select(ConsolidationProfile)
            .where(
                ConsolidationProfile.group_id == enterprise.group_id,
                ConsolidationProfile.status == "active",
            )
            .order_by(ConsolidationProfile.updated_at.desc())
        )
        version = hashlib.sha256(json.dumps({
            "permission": actor.permission_set_version, "allowed": allowed_enterprises,
            "selected": selected, "units": business_units, "stores": store_ids,
            "warehouses": warehouse_ids, "level": level,
            "profile": profile.version if profile else None,
        }, sort_keys=True).encode()).hexdigest()
        return ScopeContext(
            group_id=group.id if group else enterprise.group_id,
            group_name=group.name if group else None,
            enterprise_id=enterprise.id,
            enterprise_name=enterprise.name,
            allowed_enterprise_ids=allowed_enterprises,
            business_unit_ids=business_units,
            selected_enterprise_ids=selected,
            scope_version=version,
            timezone=enterprise.timezone,
            currency_code=profile.base_currency if profile else None,
            consolidation_profile_version=profile.version if profile else None,
            store_ids=store_ids, warehouse_ids=warehouse_ids, scope_level=level,
        )


def _selected_ids(selection: dict[str, object], key: str, allowed: set[str]) -> tuple[str, ...]:
    requested = selection.get(key)
    if requested:
        if (not isinstance(requested, list)
                or not all(isinstance(item, str) for item in requested)
                or not set(requested).issubset(allowed)):
            raise ApiProblem(status_code=403, code="scope.selection_denied",
                             message="选择的范围不存在或未获授权")
        return tuple(sorted(set(str(item) for item in requested)))
    return tuple(sorted(allowed))
