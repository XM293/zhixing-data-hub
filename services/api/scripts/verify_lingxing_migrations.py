"""Local PostgreSQL verification; URLs are explicit and never read from .env."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import MetaData, Table, inspect, text
from sqlalchemy.engine import make_url

from zhixing_api.database import Database, assert_test_database_url


def verify(url: str, *, upgrade_existing: bool) -> dict[str, object]:
    parsed = make_url(url)
    assert_test_database_url(url)
    if (parsed.host not in {"127.0.0.1", "localhost", "::1"}
            or parsed.get_backend_name() != "postgresql"):
        raise ValueError("Only a local isolated PostgreSQL database is allowed")
    database = Database(url)
    try:
        if database.revision() != "base":
            raise ValueError("Verification requires a new empty database")
        if upgrade_existing:
            database.migrate("0053_runtime_resume_spec")
            with database.engine.begin() as connection:
                # Existing non-demo tenant sentinel proves additive migrations retain rows.
                connection.execute(text(
                    "INSERT INTO enterprises (id, code, name, timezone, created_at) "
                    "VALUES ('verify-retained', 'verify-retained', "
                    "'Synthetic retained legal entity', "
                    "'UTC', :now)"
                ), {"now": datetime.now(UTC)})
                jobs = Table("background_jobs", MetaData(), autoload_with=connection)
                now = datetime.now(UTC)
                connection.execute(jobs.insert().values(
                    id="verify-retained-job", enterprise_id="verify-retained", job_type="test.noop",
                    payload={}, status="queued", priority=0, attempt=1, max_attempts=3,
                    timeout_seconds=300, available_at=now, idempotency_key="verify-retained-job",
                    initiator_type="user", initiator_id="synthetic", actor_snapshot={},
                    permission_set_version="synthetic-v1", required_permissions=[],
                    scope_type="enterprise", scope_id="verify-retained", request_id="synthetic",
                    run_id="synthetic", created_at=now, updated_at=now))
                sources = Table("external_systems", MetaData(), autoload_with=connection)
                connection.execute(sources.insert().values(id="verify-retained-source",
                    enterprise_id="verify-retained", system_key="synthetic", name="Synthetic",
                    system_type="lingxing", base_url="https://openapi.lingxing.com",
                    status="configured", source_schema_version="unknown", mapping_version="1"))
                runs = Table("sync_runs", MetaData(), autoload_with=connection)
                connection.execute(runs.insert().values(id="verify-retained-run",
                    enterprise_id="verify-retained", external_system_id="verify-retained-source",
                    status="succeeded", scenario="synthetic", volume_profile="standard",
                    records_read=0, records_written=0, started_at=now, finished_at=now))
        database.migrate()
        with database.engine.connect() as connection:
            retained = connection.execute(text(
                "SELECT count(*) FROM enterprises WHERE id = 'verify-retained'"
            )).scalar_one()
            assert retained == int(upgrade_existing)
            uniques = inspect(connection).get_unique_constraints("raw_page_manifests")
            assert not any(item["column_names"] == ["content_hash"] for item in uniques)
            if upgrade_existing:
                job = connection.execute(text("SELECT continuation_count, continuation_progress, "
                    "attempt, max_attempts FROM background_jobs WHERE id = 'verify-retained-job'"))
                assert tuple(job.one()) == (0, 0, 1, 3)
                source = connection.execute(text("SELECT version, created_at FROM external_systems "
                    "WHERE id = 'verify-retained-source'"))
                assert tuple(source.one()) == (1, None)
                assert connection.execute(text("SELECT source_version FROM sync_runs "
                    "WHERE id = 'verify-retained-run'")).scalar_one() is None
        return {"path": "0053_to_head" if upgrade_existing else "empty_to_head",
                "revision": database.revision(), "retained_synthetic_rows": retained,
                "tables": len(inspect(database.engine).get_table_names()), "status": "passed"}
    finally:
        database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--empty-url", required=True)
    parser.add_argument("--upgrade-url", required=True)
    args = parser.parse_args()
    results = [verify(args.empty_url, upgrade_existing=False),
               verify(args.upgrade_url, upgrade_existing=True)]
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
