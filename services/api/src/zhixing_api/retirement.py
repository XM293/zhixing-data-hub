"""Explicit, tenant-scoped retirement plans for isolated verification databases."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, cast

from sqlalchemy import Connection, Engine, MetaData, Table, and_, func, select

from zhixing_api.database import assert_test_database_url

PROTECTED = frozenset({
    "alembic_version", "enterprise_groups", "enterprises", "business_units",
    "principals", "user_accounts", "access_roles", "permission_definitions", "auth_sessions",
    "enterprise_memberships", "enterprise_scope_grants", "access_role_permissions",
    "role_assignments", "scope_grants", "org_units", "positions", "memberships",
    "channel_identities", "center_assignments", "consolidation_profiles",
})


def _tenant(
    connection: Connection, table: Table, row: Mapping[str, Any], visited: frozenset[str]
) -> set[str]:
    if table.name in visited:
        return set()
    if row.get("enterprise_id") is not None:
        return {str(row["enterprise_id"])}
    owners: set[str] = set()
    for fk in table.foreign_key_constraints:
        parent = fk.referred_table
        clauses = [element.column == row[element.parent.name] for element in fk.elements]
        for parent_row in connection.execute(select(parent).where(and_(*clauses))).mappings():
            owners.update(
                _tenant(
                    connection, parent, cast(Mapping[str, Any], parent_row),
                    visited | {table.name},
                )
            )
    return owners


def _analyze(connection: Connection, manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("version") != 1 or not isinstance(manifest.get("enterprise_id"), str):
        raise ValueError("manifest requires version=1 and enterprise_id")
    tenant = manifest["enterprise_id"]
    specs = manifest.get("tables")
    if not isinstance(specs, list):
        raise ValueError("manifest tables must be explicit")
    metadata = MetaData()
    metadata.reflect(connection)
    selected: dict[str, list[str]] = {}
    impacts: list[dict[str, Any]] = []
    for spec in specs:
        name, ids = spec.get("table"), spec.get("ids")
        if name in PROTECTED or name not in metadata.tables or name in selected:
            raise ValueError("unknown, protected or duplicate table")
        if not isinstance(ids, list) or not all(isinstance(key, str) for key in ids):
            raise ValueError("table ids must be an explicit string list")
        if len(set(ids)) != len(ids) or spec.get("expected_count") != len(ids):
            raise ValueError("expected_count must match unique selected ids")
        table = metadata.tables[name]
        if list(table.primary_key.columns.keys()) != ["id"]:
            raise ValueError("table requires a single id primary key")
        rows = connection.execute(select(table).where(table.c.id.in_(ids))).mappings().all()
        for row in rows:
            if _tenant(connection, table, cast(Mapping[str, Any], row), frozenset()) != {tenant}:
                raise ValueError("retirement scope cannot be proven")
        selected[name] = ids
        impacts.append({
            "table": name, "expected_count": len(ids), "matched_count": len(rows),
            "missing_count": len(ids) - len(rows),
        })
    blocks: list[dict[str, Any]] = []
    for child in metadata.tables.values():
        for fk in child.foreign_key_constraints:
            parent = fk.referred_table
            if parent.name not in selected:
                continue
            condition = and_(*(element.parent == element.column for element in fk.elements))
            query = select(func.count()).select_from(child.join(parent, condition)).where(
                parent.c.id.in_(selected[parent.name])
            )
            if child.name in selected:
                query = query.where(child.c.id.not_in(selected[child.name]))
            count = connection.scalar(query) or 0
            if count:
                blocks.append({"table": child.name, "count": count, "parent": parent.name})
    sessions = metadata.tables.get("auth_sessions")
    revoke = 0
    if manifest.get("revoke_sessions") and sessions is not None:
        if "enterprise_id" not in sessions.c or "revoked_at" not in sessions.c:
            raise ValueError("session revocation scope cannot be proven")
        revoke = connection.scalar(select(func.count()).select_from(sessions).where(
            sessions.c.enterprise_id == tenant, sessions.c.revoked_at.is_(None)
        )) or 0
    impact: dict[str, Any] = {
        "tables": impacts,
        "foreign_key_blocks": sorted(blocks, key=lambda item: (item["table"], item["parent"])),
        "sessions_to_revoke": revoke,
        "already_retired": bool(impacts) and all(item["matched_count"] == 0 for item in impacts),
        "delete_order": [table.name for table in reversed(metadata.sorted_tables)
                         if table.name in selected],
    }
    digest = json.dumps({"manifest": manifest, "impact": impact}, sort_keys=True).encode()
    impact["plan_hash"] = hashlib.sha256(digest).hexdigest()
    return impact


def analyze_retirement(engine: Engine, manifest: dict[str, Any]) -> dict[str, Any]:
    assert_test_database_url(engine.url.render_as_string(hide_password=False))
    with engine.connect() as connection:
        return _analyze(connection, manifest)


def execute_retirement(
    engine: Engine, manifest: dict[str, Any], *, backup_id: str, plan_hash: str,
    confirmed: bool = False,
) -> dict[str, int]:
    assert_test_database_url(engine.url.render_as_string(hide_password=False))
    if not confirmed:
        raise ValueError("retirement requires explicit confirmation")
    if not backup_id or not plan_hash:
        raise ValueError("backup ID and reviewed plan hash are required")
    with engine.connect().execution_options(isolation_level="SERIALIZABLE") as connection:
        with connection.begin():
            plan = _analyze(connection, manifest)
            if plan["plan_hash"] != plan_hash or plan["foreign_key_blocks"]:
                raise ValueError("retirement plan changed or blocked")
            if any(row["missing_count"] for row in plan["tables"]) and not plan["already_retired"]:
                raise ValueError("retirement counts changed")
            metadata = MetaData()
            metadata.reflect(connection)
            specs = {item["table"]: item for item in manifest["tables"]}
            deleted = 0
            for name in plan["delete_order"]:
                table = metadata.tables[name]
                deleted += connection.execute(
                    table.delete().where(table.c.id.in_(specs[name]["ids"]))
                ).rowcount
            revoked = 0
            if manifest.get("revoke_sessions") and "auth_sessions" in metadata.tables:
                sessions = metadata.tables["auth_sessions"]
                revoked = connection.execute(sessions.update().where(
                    sessions.c.enterprise_id == manifest["enterprise_id"],
                    sessions.c.revoked_at.is_(None),
                ).values(revoked_at=func.current_timestamp())).rowcount
            return {"deleted": deleted, "revoked": revoked}
