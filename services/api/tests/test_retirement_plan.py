from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from zhixing_api.retirement import analyze_retirement, execute_retirement


@pytest.fixture
def retirement_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'retirement_verify.db'}")
    with engine.begin() as connection:
        for statement in (
            "CREATE TABLE facts (id TEXT PRIMARY KEY, enterprise_id TEXT NOT NULL)",
            "CREATE TABLE details (id TEXT PRIMARY KEY, fact_id TEXT REFERENCES facts(id))",
            "CREATE TABLE auth_sessions (id TEXT PRIMARY KEY, enterprise_id TEXT, revoked_at TEXT)",
            "INSERT INTO facts VALUES ('a', 'legal-a'), ('b', 'legal-b')",
            "INSERT INTO details VALUES ('d', 'a')",
            "INSERT INTO auth_sessions VALUES ('session-a', 'legal-a', NULL)",
        ):
            connection.execute(text(statement))
    yield engine
    engine.dispose()


def manifest(*, child=True):
    return {
        "version": 1, "enterprise_id": "legal-a",
        "tables": ([{"table": "details", "ids": ["d"], "expected_count": 1}] if child else [])
        + [{"table": "facts", "ids": ["a"], "expected_count": 1}],
        "revoke_sessions": True,
    }


def test_preview_counts_and_blocks_are_real(retirement_db):
    plan = analyze_retirement(retirement_db, manifest(child=False))
    assert plan["tables"][0]["matched_count"] == 1
    assert plan["foreign_key_blocks"] == [{"table": "details", "count": 1, "parent": "facts"}]
    assert plan["sessions_to_revoke"] == 1
    with retirement_db.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM facts")).scalar_one() == 2


def test_execute_orders_dependencies_revokes_sessions_and_is_repeatable(retirement_db):
    plan = analyze_retirement(retirement_db, manifest())
    result = execute_retirement(
        retirement_db, manifest(), backup_id="synthetic-backup", plan_hash=plan["plan_hash"],
        confirmed=True,
    )
    assert result["deleted"] == 2 and result["revoked"] == 1
    repeated = analyze_retirement(retirement_db, manifest())
    assert repeated["already_retired"] is True
    with retirement_db.connect() as connection:
        assert connection.execute(text("SELECT id FROM facts")).scalar_one() == "b"
        assert connection.execute(
            text("SELECT revoked_at FROM auth_sessions")
        ).scalar_one() is not None


def test_drift_and_scope_fail_closed(retirement_db):
    spec = manifest()
    plan = analyze_retirement(retirement_db, spec)
    with retirement_db.begin() as connection:
        connection.execute(text("INSERT INTO details VALUES ('late', 'a')"))
    with pytest.raises(ValueError, match="changed|blocked"):
        execute_retirement(
            retirement_db, spec, backup_id="synthetic-backup", plan_hash=plan["plan_hash"],
            confirmed=True,
        )
    spec["tables"][-1]["ids"] = ["b"]
    with pytest.raises(ValueError, match="scope"):
        analyze_retirement(retirement_db, spec)
