"""Copy a local SQLite installation into an already migrated PostgreSQL database.

The command is intentionally explicit because replacing the target database is
destructive. It is useful for moving the local vertical-slice dataset into the
real PostgreSQL runtime before the first server deployment.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, create_engine, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.sql.sqltypes import JSON, String

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT / "src"))

CHUNK_SIZE = 1000
EXCLUDED_TABLES = {"alembic_version"}


def main() -> int:
    from zhixing_api.config import load_settings

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default="var/zhixing.db",
        help="SQLite 文件路径（相对于 services/api）",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--replace-target",
        action="store_true",
        help="清空目标 PostgreSQL 业务表后导入",
    )
    parser.add_argument(
        "--confirm-target",
        action="store_true",
        help="确认目标为本项目数据库，必须与 --replace-target 一起使用",
    )
    args = parser.parse_args()
    settings = load_settings()
    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        raise SystemExit(f"找不到 SQLite 源文件：{source_path}")
    if source_path.suffix.casefold() not in {".db", ".sqlite", ".sqlite3"}:
        raise SystemExit("拒绝读取非 SQLite 扩展名的源文件")
    target_url = make_url(settings.database_url)
    if target_url.get_backend_name() != "postgresql":
        raise SystemExit("目标 DATABASE_URL 必须是 PostgreSQL")
    if args.replace_target and not args.confirm_target:
        raise SystemExit("清空目标库前必须同时提供 --replace-target --confirm-target")
    if args.replace_target and (target_url.database or "").casefold() in {
        "postgres",
        "template0",
        "template1",
    }:
        raise SystemExit("拒绝把系统数据库作为迁移目标")

    source = create_engine(f"sqlite+pysqlite:///{source_path.as_posix()}")
    target = create_engine(settings.database_url, pool_pre_ping=True)
    source_meta = MetaData()
    target_meta = MetaData()
    source_meta.reflect(source)
    target_meta.reflect(target)
    table_names = [
        name
        for name in target_meta.tables
        if name in source_meta.tables and name not in EXCLUDED_TABLES
    ]
    missing = sorted(set(target_meta.tables) - set(source_meta.tables) - EXCLUDED_TABLES)
    if missing:
        raise SystemExit(f"SQLite 缺少目标表：{', '.join(missing)}")
    violations = _find_violations(source, source_meta, target_meta, table_names)
    row_count = _count_rows(source, source_meta, table_names)
    print(f"源文件：{source_path.name}，表 {len(table_names)} 个，待导入行 {row_count}")
    print(f"目标：{_safe_url(settings.database_url)}")
    if violations:
        print(f"已知可修正字段：{len(violations)} 条（ID 使用稳定摘要，错误原因保留摘要尾缀）")
    if args.dry_run:
        return 0
    if not args.replace_target:
        raise SystemExit("实际导入必须显式提供 --replace-target --confirm-target")
    _replace_target(source, target, source_meta, target_meta, table_names)
    print("迁移完成")
    return 0


def _replace_target(
    source: Engine,
    target: Engine,
    source_meta: MetaData,
    target_meta: MetaData,
    table_names: list[str],
) -> None:
    order = _insert_order(target_meta, table_names)
    with source.connect() as source_connection, target.begin() as target_connection:
        quoted = ", ".join(f'"{name}"' for name in table_names)
        target_connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))
        for name in order:
            source_table = source_meta.tables[name]
            target_table = target_meta.tables[name]
            rows = source_connection.execute(select(source_table)).mappings()
            batch: list[dict[str, Any]] = []
            for source_row in rows:
                batch.append(_normalize_row(name, source_row, target_table))
                if len(batch) >= CHUNK_SIZE:
                    target_connection.execute(target_table.insert(), batch)
                    batch.clear()
            if batch:
                target_connection.execute(target_table.insert(), batch)


def _insert_order(metadata: MetaData, table_names: list[str]) -> list[str]:
    table_set = set(table_names)
    dependencies: dict[str, set[str]] = defaultdict(set)
    dependents: dict[str, set[str]] = defaultdict(set)
    for name in table_names:
        table = metadata.tables[name]
        for foreign_key in table.foreign_keys:
            parent = foreign_key.column.table.name
            if parent in table_set and parent != name:
                dependencies[name].add(parent)
                dependents[parent].add(name)
    ready = deque(sorted(name for name in table_names if not dependencies[name]))
    result: list[str] = []
    while ready:
        name = ready.popleft()
        result.append(name)
        for dependent in sorted(dependents[name]):
            dependencies[dependent].discard(name)
            if not dependencies[dependent]:
                ready.append(dependent)
    if len(result) != len(table_names):
        unresolved = sorted(set(table_names) - set(result))
        raise RuntimeError(f"目标表存在无法排序的外键环：{', '.join(unresolved)}")
    return result


def _find_violations(
    source: Engine,
    source_meta: MetaData,
    target_meta: MetaData,
    table_names: list[str],
) -> list[tuple[str, str, int, int]]:
    violations: list[tuple[str, str, int, int]] = []
    with source.connect() as connection:
        for name in table_names:
            source_table = source_meta.tables[name]
            target_table = target_meta.tables[name]
            limited = [column for column in target_table.columns if isinstance(column.type, String)]
            for row in connection.execute(select(source_table)).mappings():
                for column in limited:
                    value = row.get(column.name)
                    limit = _string_limit(column.type)
                    if isinstance(value, str) and limit and len(value) > limit:
                        violations.append((name, column.name, len(value), int(limit)))
    unsupported = [
        item
        for item in violations
        if not (item[1] == "fallback_reason" and item[2] > item[3])
        and not (
            item[1] == "id"
            and item[0] in {"access_role_permissions", "enterprise_memberships"}
        )
    ]
    if unsupported:
        formatted = ", ".join(
            f"{table}.{column}({size}>{limit})"
            for table, column, size, limit in unsupported
        )
        raise RuntimeError(f"发现未定义的字符串截断：{formatted}")
    return violations


def _normalize_row(name: str, row: Any, target_table: Any) -> dict[str, Any]:
    values = dict(row)
    for column in target_table.columns:
        value = values.get(column.name)
        if isinstance(column.type, JSON) and isinstance(value, str):
            try:
                values[column.name] = json.loads(value)
            except json.JSONDecodeError:
                # Older SQLite migrations allowed plain text in JSON columns.
                # Passing the Python string lets PostgreSQL JSON serialize it
                # without guessing a different value type.
                values[column.name] = value
        limit = _string_limit(column.type)
        if isinstance(value, str) and limit and len(value) > limit:
            if column.name == "fallback_reason":
                digest = sha256(value.encode()).hexdigest()[:16]
                values[column.name] = f"{value[: int(limit) - 19]}…[{digest}]"
            elif column.name == "id" and name in {
                "access_role_permissions",
                "enterprise_memberships",
            }:
                values[column.name] = f"{name[:20]}_{sha256(value.encode()).hexdigest()[:40]}"
            else:
                raise RuntimeError(f"{name}.{column.name} 超出 PostgreSQL 长度限制")
    return values


def _string_limit(type_: object) -> int | None:
    if not isinstance(type_, String):
        return None
    length = type_.length
    return int(length) if isinstance(length, int) else None


def _count_rows(engine: Engine, metadata: MetaData, table_names: list[str]) -> int:
    with engine.connect() as connection:
        return sum(
            int(
                connection.execute(
                    select(func.count()).select_from(metadata.tables[name])
                ).scalar_one()
            )
            for name in table_names
        )


def _safe_url(value: str) -> str:
    parsed = make_url(value)
    if parsed.password:
        parsed = parsed.set(password="***")
    return str(parsed)


if __name__ == "__main__":
    raise SystemExit(main())
