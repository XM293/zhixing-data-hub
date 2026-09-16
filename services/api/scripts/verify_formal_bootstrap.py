"""Verify the synthetic formal organization against an explicit empty local database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from secrets import token_urlsafe

from sqlalchemy.engine import make_url

from zhixing_api.actor_context import authenticate_local_actor, resolve_database_actor
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.database import Database, assert_test_database_url
from zhixing_api.scope_context import build_scope_context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    parsed = make_url(args.database_url)
    assert_test_database_url(args.database_url)
    if (parsed.get_backend_name() != "postgresql"
            or parsed.host not in {"127.0.0.1", "localhost", "::1"}):
        raise ValueError("verification requires an isolated local PostgreSQL database")
    manifest = json.loads((Path(__file__).parents[1] / "tests" / "fixtures"
                           / "bootstrap-formal-synthetic.json").read_text(encoding="utf-8"))
    database = Database(args.database_url)
    try:
        database.migrate()
        plan = analyze_bootstrap(database.engine, manifest)
        if plan["group"]["exists"]:
            raise ValueError("verification requires a new synthetic organization")
        credentials = {
            admin["password_env"]: token_urlsafe(32) for admin in manifest["administrators"]
        }
        result = execute_bootstrap(database.engine, manifest, confirmed=True,
                                   backup_id="synthetic-empty-verification-database",
                                   plan_hash=plan["plan_hash"], credential_provider=credentials.get)
        for admin in manifest["administrators"]:
            actor = authenticate_local_actor(database, login_name=admin["login_name"],
                password=credentials[admin["password_env"]], request_id="verify", run_id="verify")
            scope = build_scope_context(database, actor, selection={"scope_level": "group"})
            assert len(scope.selected_enterprise_ids) == 2 and len(scope.business_unit_ids) == 3
            switched = resolve_database_actor(database, login_name=admin["login_name"],
                user_account_id=actor.user_account_id, enterprise_id="legal-b",
                request_id="verify", run_id="verify")
            assert "source.manage" in switched.permissions
        repeated = execute_bootstrap(database.engine, manifest, confirmed=True,
            backup_id="synthetic-empty-verification-database",
            plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
            credential_provider=lambda key: None)
        assert not any(repeated["created"].values())
        print(json.dumps({"status": "passed", "revision": database.revision(),
                          "created": result["created"], "administrators_authenticated": 2,
                          "cross_enterprise_access": "passed", "repeat": "no_changes"}))
    finally:
        database.dispose()


if __name__ == "__main__":
    main()
