"""Verify PostgreSQL source revision races using synthetic rows and a fixed test actor."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from zhixing_api.data_center_schemas import SourceUpdateRequest
from zhixing_api.data_models import Enterprise, ExternalSystem, PlatformEvent
from zhixing_api.database import Database, assert_test_database_url
from zhixing_api.errors import ApiProblem
from zhixing_api.routers import data_center


def verify(url: str) -> None:
    assert_test_database_url(url)
    parsed = make_url(url)
    if parsed.host != "127.0.0.1" or parsed.get_backend_name() != "postgresql":
        raise ValueError("Only isolated loopback PostgreSQL is allowed")
    database = Database(url)
    database.migrate()
    key = f"synthetic-{uuid4().hex}"
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(Enterprise(id=key, code=key, name="Synthetic revision verification",
                               timezone="UTC", created_at=now))
        session.flush()
        session.add(ExternalSystem(id=key, enterprise_id=key, system_key="synthetic",
            name="Synthetic initial", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured", created_at=now))
        session.commit()
    barrier = Barrier(2)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=database)))

    def edit(number: int) -> str:
        barrier.wait(timeout=10)
        try:
            result = asyncio.run(data_center.update_source(request, "synthetic",
                SourceUpdateRequest(expected_version=1, name=f"Synthetic contender {number}")))
            assert result.version == 2
            return "updated"
        except ApiProblem as error:
            assert error.code == "source.version_conflict" and error.status_code == 409
            return "conflict"

    try:
        with patch.object(data_center, "_authorize", return_value=SimpleNamespace(
                enterprise_id=key, principal_id="synthetic-test-actor")):
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(edit, (1, 2)))
        assert sorted(outcomes) == ["conflict", "updated"]
        with database.session() as session:
            assert session.get(ExternalSystem, key).version == 2
            assert session.scalar(select(func.count()).select_from(PlatformEvent).where(
                PlatformEvent.enterprise_id == key,
                PlatformEvent.event_type == "source.configuration_updated")) == 1
        print("source configuration race: one update, one 409, one audit event; passed")
    finally:
        database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    verify(parser.parse_args().database_url)
