"""Reviewed, atomic bootstrap for isolated verification databases."""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError
from sqlalchemy import Connection, Engine, Table, UniqueConstraint, and_, func, select
from sqlalchemy.exc import IntegrityError

from zhixing_api.auth_service import hash_password
from zhixing_api.bootstrap_schema import BootstrapManifest
from zhixing_api.data_models import (
    AccessRole,
    AccessRolePermission,
    Base,
    BusinessUnit,
    Enterprise,
    EnterpriseGroup,
    EnterpriseMembership,
    EnterpriseScopeGrant,
    PermissionDefinition,
    Principal,
    RoleAssignment,
    ScopeGrant,
    ToolDefinition,
    UserAccount,
)
from zhixing_api.database import assert_test_database_url
from zhixing_api.identity_seed import PERMISSIONS
from zhixing_api.tool_templates import reviewed_tool_template


def _id(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, json.dumps(["zhixing-bootstrap-v2", *parts])))


def _validate_manifest(manifest: dict[str, Any]) -> BootstrapManifest:
    try:
        return BootstrapManifest.model_validate(manifest)
    except ValidationError:
        # Inputs may contain a mistakenly pasted secret; never serialize validation inputs.
        raise ValueError("invalid bootstrap manifest") from None


@dataclass(frozen=True)
class Record:
    table: Table
    values: dict[str, Any]
    password_env: str | None = None


def _records(connection: Connection, spec: BootstrapManifest) -> list[Record]:
    records: list[Record] = []

    def add(model: type[Base], values: dict[str, Any], password_env: str | None = None) -> None:
        records.append(Record(cast(Table, model.__table__), values, password_env))

    add(EnterpriseGroup, spec.group.model_dump())
    for enterprise in spec.enterprises:
        add(Enterprise, {**enterprise.model_dump(), "group_id": spec.group.id,
                         "timezone": enterprise.timezone or spec.group.timezone})
    pending = {unit.id: unit for unit in spec.business_units}
    while pending:
        for key, unit in list(pending.items()):
            if unit.parent_id not in pending:
                add(BusinessUnit, {**unit.model_dump(), "version": 1})
                del pending[key]
    requested_permissions = {key for role in spec.role_templates for key in role.permission_keys}
    permission_ids: dict[str, str] = {}
    for key, label, resource, action, risk in PERMISSIONS:
        if key not in requested_permissions:
            continue
        permission_id = connection.scalar(select(PermissionDefinition.id).where(
            PermissionDefinition.permission_key == key,
        )) or _id("permission", key)
        permission_ids[key] = permission_id
        add(PermissionDefinition, {
            "id": permission_id, "permission_key": key, "label": label, "resource": resource,
            "action": action, "risk_level": risk, "status": "active",
        })
    role_ids: dict[tuple[str, str], str] = {}
    for enterprise in spec.enterprises:
        for tool_key in spec.read_only_tools:
            add(ToolDefinition, {"id": _id("tool", enterprise.id, tool_key),
                "enterprise_id": enterprise.id, **reviewed_tool_template(tool_key)})
        for role in spec.role_templates:
            role_id = _id("role", enterprise.id, role.role_key)
            role_ids[enterprise.id, role.role_key] = role_id
            add(AccessRole, {
                "id": role_id, "enterprise_id": enterprise.id, "role_key": role.role_key,
                "name": role.name, "description": "", "version": "1", "revision": 1,
                "status": "active",
            })
            for key in role.permission_keys:
                add(AccessRolePermission, {
                    "id": _id("role-permission", role_id, key), "access_role_id": role_id,
                    "permission_id": permission_ids[key], "effect": "allow",
                })
    for admin in spec.administrators:
        principal_id = _id("principal", admin.id)
        add(Principal, {
            "id": principal_id, "enterprise_id": admin.home_enterprise_id,
            "principal_key": admin.id, "principal_type": "human",
            "display_name": admin.display_name, "status": "active",
        })
        add(UserAccount, {
            "id": admin.id, "enterprise_id": admin.home_enterprise_id,
            "principal_id": principal_id, "account_key": admin.id,
            "local_login_name": admin.login_name.casefold(), "experience_role_key": "admin",
            "authentication_source": "local", "status": "active", "version": 1,
        }, admin.password_env)
        add(EnterpriseScopeGrant, {
            "id": _id("group-grant", principal_id, spec.group.id), "principal_id": principal_id,
            "group_id": spec.group.id, "enterprise_id": None, "scope_type": "group",
            "scope_id": spec.group.id, "effect": "allow", "status": "active", "valid_to": None,
        })
        for enterprise_id in admin.enterprise_ids:
            add(EnterpriseMembership, {
                "id": _id("membership", principal_id, enterprise_id),
                "principal_id": principal_id, "enterprise_id": enterprise_id,
                "membership_type": "employee",
                "is_primary": enterprise_id == admin.home_enterprise_id,
                "status": "active", "valid_to": None, "version": 1,
            })
            for role_key in admin.role_keys:
                role_id = role_ids[enterprise_id, role_key]
                assignment_id = _id("assignment", principal_id, role_id)
                add(RoleAssignment, {
                    "id": assignment_id, "enterprise_id": enterprise_id,
                    "principal_id": principal_id, "access_role_id": role_id,
                    "status": "active", "valid_to": None,
                })
                add(ScopeGrant, {
                    "id": _id("scope", assignment_id), "enterprise_id": enterprise_id,
                    "role_assignment_id": assignment_id, "scope_type": "enterprise",
                    "scope_ids": [enterprise_id], "effect": "allow", "valid_to": None,
                })
    return records


def _analyze(
    connection: Connection, spec: BootstrapManifest,
) -> tuple[dict[str, Any], list[Record]]:
    records = _records(connection, spec)
    impacts: dict[str, dict[str, Any]] = {}
    missing: list[Record] = []
    for record in records:
        table, values = record.table, record.values
        impact = impacts.setdefault(table.name, {
            "table": table.name, "requested": 0, "existing": 0, "to_create": 0,
        })
        impact["requested"] += 1
        row = connection.execute(select(table).where(table.c.id == values["id"])).mappings().first()
        if row is not None:
            if any(row[key] != value for key, value in values.items()):
                raise ValueError(f"bootstrap identity drift: {table.name}")
            if record.password_env and not row.get("password_hash"):
                raise ValueError("bootstrap account credential drift")
            impact["existing"] += 1
            continue
        # Detect natural-key collisions with records created by another workflow.
        uniques = [list(item.columns) for item in table.constraints
                   if isinstance(item, UniqueConstraint)]
        uniques += [list(item.columns) for item in table.indexes if item.unique]
        for columns in uniques:
            if not all(column.name in values and values[column.name] is not None
                       for column in columns):
                continue
            condition = and_(*(column == values[column.name] for column in columns))
            if connection.scalar(select(table.c.id).where(condition).limit(1)) is not None:
                raise ValueError(f"bootstrap identity collision: {table.name}")
        impact["to_create"] += 1
        missing.append(record)
    tables = sorted(impacts.values(), key=lambda row: row["table"])
    result: dict[str, Any] = {
        "mode": "preview", "tables": tables,
        "group": {"id": spec.group.id, "exists": impacts["enterprise_groups"]["existing"] == 1},
        "enterprises": impacts["enterprises"],
        "business_units": impacts.get("business_units", {
            "requested": 0, "existing": 0, "to_create": 0,
        }),
    }
    digest = json.dumps({"manifest": spec.model_dump(), "impact": result}, sort_keys=True).encode()
    result["plan_hash"] = hashlib.sha256(digest).hexdigest()
    return result, missing


def analyze_bootstrap(engine: Engine, manifest: dict[str, Any]) -> dict[str, Any]:
    assert_test_database_url(engine.url.render_as_string(hide_password=False))
    spec = _validate_manifest(manifest)
    with engine.connect() as connection:
        return _analyze(connection, spec)[0]


def execute_bootstrap(
    engine: Engine, manifest: dict[str, Any], *, backup_id: str,
    confirmed: bool = False, plan_hash: str | None = None,
    credential_provider: Callable[[str], str | None] = os.environ.get,
) -> dict[str, Any]:
    assert_test_database_url(engine.url.render_as_string(hide_password=False))
    if not confirmed:
        raise ValueError("bootstrap requires explicit confirmation")
    if not backup_id.strip() or not plan_hash:
        raise ValueError("bootstrap requires backup ID and reviewed plan hash")
    spec = _validate_manifest(manifest)
    engine.hide_parameters = True
    try:
        with engine.connect().execution_options(isolation_level="SERIALIZABLE") as connection:
            with connection.begin():
                if connection.dialect.name == "postgresql":
                    lock = int.from_bytes(
                        hashlib.sha256(spec.group.id.encode()).digest()[:8], signed=True,
                    )
                    connection.execute(select(func.pg_advisory_xact_lock(lock)))
                plan, missing = _analyze(connection, spec)
                if plan["plan_hash"] != plan_hash:
                    raise ValueError("bootstrap plan changed")
                now = datetime.now(UTC)
                created = {row["table"]: 0 for row in plan["tables"]}
                for record in missing:
                    values = dict(record.values)
                    for name in ("created_at", "updated_at", "valid_from"):
                        if name in record.table.c:
                            values[name] = now
                    if record.password_env:
                        try:
                            password = credential_provider(record.password_env)
                            if not isinstance(password, str) or len(password) < 12:
                                raise ValueError("missing credential")
                            values["password_hash"] = hash_password(password)
                        except Exception:
                            raise ValueError(
                                "bootstrap credential unavailable or invalid",
                            ) from None
                    connection.execute(record.table.insert().values(**values))
                    created[record.table.name] += 1
    except IntegrityError:
        raise ValueError("bootstrap identity collision; no changes committed") from None
    if spec.version == 1:
        created = {"group": created["enterprise_groups"], "enterprises": created["enterprises"],
                   "business_units": created.get("business_units", 0)}
    return {
        "backup_id": backup_id, "created": created, "status": "succeeded", "plan_hash": plan_hash,
    }
