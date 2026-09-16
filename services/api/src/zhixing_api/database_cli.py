from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.config import load_settings
from zhixing_api.database import Database, assert_test_database_url
from zhixing_api.retirement import analyze_retirement, execute_retirement
from zhixing_api.seed import seed_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="知行数枢数据库生命周期工具")
    parser.add_argument("--database-url", help="覆盖 DATABASE_URL；不会写入配置文件")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("upgrade", help="将数据库升级到最新 Alembic revision")
    subparsers.add_parser("status", help="输出当前 Alembic revision")
    subparsers.add_parser("seed", help="升级后幂等应用版本化测试数据")
    rebuild = subparsers.add_parser("rebuild", help="重建并填充测试数据库")
    rebuild.add_argument(
        "--confirm-test-database",
        action="store_true",
        help="确认目标为可销毁的 test/verify 数据库",
    )
    rebuild.add_argument("--no-seed", action="store_true", help="只重建结构，不写入种子")
    for name in ("production-bootstrap", "demo-retire"):
        cmd = subparsers.add_parser(name, help="仅在隔离测试库执行的 dry-run 预检")
        cmd.add_argument("--manifest", required=True)
        cmd.add_argument("--backup-id", required=name == "demo-retire")
        cmd.add_argument("--dry-run", action="store_true")
        cmd.add_argument("--execute", action="store_true")
        cmd.add_argument("--confirm-test-database", action="store_true")
        cmd.add_argument("--plan-hash")
    return parser


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings()
    if args.database_url:
        settings = replace(settings, database_url=args.database_url)
    database = Database(settings.database_url)
    try:
        if args.command == "status":
            emit({"command": "status", "revision": database.revision(), "status": "ok"})
            return 0
        if args.command == "upgrade":
            database.migrate()
            emit({"command": "upgrade", "revision": database.revision(), "status": "ok"})
            return 0
        if args.command == "seed":
            database.migrate()
            report = seed_database(database, settings)
            emit(
                {
                    "command": "seed",
                    "revision": database.revision(),
                    "seed": report.as_dict(),
                    "status": "ok",
                }
            )
            return 0
        if args.command in {"production-bootstrap", "demo-retire"}:
            assert_test_database_url(settings.database_url)
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            backup_id = getattr(args, "backup_id", None)
            if args.command == "demo-retire" and not backup_id:
                raise ValueError("demo-retire 必须显式提供 backup ID")
            if args.dry_run and args.execute:
                raise ValueError("dry-run 与 execute 不可同时使用")
            if args.command == "demo-retire":
                impact = analyze_retirement(database.engine, manifest)
                result = None
                if args.execute:
                    if not args.confirm_test_database:
                        raise ValueError("执行要求 --confirm-test-database")
                    result = execute_retirement(
                        database.engine, manifest,
                        backup_id=str(backup_id), plan_hash=args.plan_hash,
                        confirmed=args.confirm_test_database,
                    )
                emit({
                    "command": args.command, "backup_id": backup_id,
                    "dry_run": not args.execute, "impact": impact, "result": result,
                    "status": "blocked" if impact["foreign_key_blocks"] else "ok",
                })
                return 0
            impact = analyze_bootstrap(database.engine, manifest)
            result = None
            if args.execute:
                if not args.confirm_test_database:
                    raise ValueError("执行要求 --confirm-test-database")
                if not backup_id:
                    raise ValueError("production-bootstrap 执行要求 backup ID")
                result = execute_bootstrap(
                    database.engine, manifest, backup_id=str(backup_id),
                    confirmed=args.confirm_test_database, plan_hash=args.plan_hash,
                )
            emit(
                {
                    "command": args.command,
                    "backup_id": backup_id,
                    "dry_run": not args.execute,
                    "impact": impact,
                    "result": result,
                    "manifest_keys": sorted(manifest),
                    "status": "ok",
                }
            )
            return 0
        if not args.confirm_test_database:
            raise ValueError("rebuild 必须显式传入 --confirm-test-database")
        database.rebuild_test_schema()
        rebuild_report = None if args.no_seed else seed_database(database, settings)
        emit(
            {
                "command": "rebuild",
                "revision": database.revision(),
                "seed": rebuild_report.as_dict() if rebuild_report is not None else None,
                "status": "ok",
            }
        )
        return 0
    except (RuntimeError, ValueError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    finally:
        database.dispose()


if __name__ == "__main__":
    raise SystemExit(run())
