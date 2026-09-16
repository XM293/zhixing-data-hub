"""Verify concurrent source scheduling using synthetic data in a fresh local PostgreSQL DB."""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from zhixing_jobs.models import BackgroundJob

from zhixing_api.actor_context import resolve_database_actor
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.data_models import ExternalSystem, SourceResource, SourceSyncSchedule, SyncRun
from zhixing_api.database import Database, assert_test_database_url
from zhixing_api.ingestion.batches import cancel_import
from zhixing_api.ingestion.planning import ScheduleRequest
from zhixing_api.ingestion.schedules import dispatch_due, save_schedule
from zhixing_api.scope_context import build_scope_context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    url = make_url(args.database_url)
    assert_test_database_url(args.database_url)
    if (url.get_backend_name() != "postgresql"
            or url.host not in {"127.0.0.1", "localhost", "::1"}):
        raise ValueError("Only an isolated local PostgreSQL verification database is allowed")
    database = Database(args.database_url)
    manifest = json.loads((Path(__file__).parents[1] / "tests/fixtures"
                           / "bootstrap-formal-synthetic.json").read_text(encoding="utf-8"))
    try:
        database.migrate()
        preview = analyze_bootstrap(database.engine, manifest)
        if preview["group"]["exists"]:
            raise ValueError("Requires a fresh synthetic verification organization")
        execute_bootstrap(database.engine, manifest, backup_id="synthetic-empty-database",
            confirmed=True, plan_hash=preview["plan_hash"],
            credential_provider=lambda _: token_urlsafe(32))
        actor = resolve_database_actor(database, login_name="admin-1@verify",
                                       enterprise_id="legal-a", request_id="verify",
                                       run_id="verify")
        now = datetime.now(UTC)
        with database.session() as session:
            session.add(ExternalSystem(id="src", enterprise_id="legal-a", system_key="erp",
                name="Synthetic ERP", provider_key="lingxing", system_type="lingxing",
                base_url="https://openapi.lingxing.com", status="configured"))
            session.flush()
            for key in ("shops", "orders"):
                session.add(SourceResource(id=key, external_system_id="src", resource_key=key,
                    method="GET", path="/synthetic", schema_status="confirmed", enabled=True))
            session.commit()
        for key in ("shops", "orders"):
            save_schedule(database, actor=actor, source_key="erp",
                scope=build_scope_context(database, actor).snapshot(), now=now,
                payload=ScheduleRequest(name=f"Synthetic {key}", resource_key=key, status="active",
                    strategy="updated_utc" if key == "orders" else "snapshot",
                    initial_start=now - timedelta(days=1) if key == "orders" else None))
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda _: dispatch_due(
                database, provider_enabled=True, now=now), range(4)))
        assert sum(results) == 2
        with database.session() as session:
            assert session.scalar(select(func.count()).select_from(BackgroundJob)) == 2
            parents = list(session.scalars(select(SyncRun).where(SyncRun.parent_run_id.is_(None))))
            assert len(parents) == 2
            for parent in parents:
                cancel_import(database, session, parent, principal_id=actor.principal_id)
            session.commit()
        dispatch_due(database, provider_enabled=True, now=now + timedelta(minutes=1))
        with database.session() as session:
            plans = list(session.scalars(select(SourceSyncSchedule)))
            assert all(row.status == "needs_attention" and row.watermark is None for row in plans)
        print(json.dumps({"status": "passed", "concurrent_dispatchers": 4,
                          "schedules": 2, "queued_jobs": 2, "cancel_watermark": "retained",
                          "external_requests": 0, "revision": database.revision()}))
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
