import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from zhixing_api.data_models import SourceRequestBudget

from zhixing_worker.rate_limit import SourceRateLimiter


def test_concurrent_workers_share_account_path_budget_and_release_connections(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rate_verify.db'}")
    SourceRequestBudget.__table__.create(engine)
    now = datetime(2026, 9, 9, tzinfo=UTC)
    limiters = [SourceRateLimiter(engine, "synthetic-account", clock=lambda: now)
                for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        delays = list(executor.map(lambda limiter: limiter.reserve("/resource"), limiters))
    assert sorted(delays) == list(range(8))
    other_account = SourceRateLimiter(engine, "other-account", clock=lambda: now)
    assert other_account.reserve("/resource") == 0
    assert limiters[0].reserve("/other-resource") == 0
    assert engine.pool.checkedout() == 0
    resumed = SourceRateLimiter(engine, "synthetic-account",
                                clock=lambda: now + timedelta(seconds=9))
    assert resumed.reserve("/resource") == 0
    engine.dispose()


def test_rate_wait_observes_cancellation_before_request(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rate_cancel_verify.db'}")
    SourceRequestBudget.__table__.create(engine)
    now = datetime(2026, 9, 9, tzinfo=UTC)
    calls = []

    def cancelled():
        calls.append("check")
        raise RuntimeError("cancelled")

    limiter = SourceRateLimiter(engine, "synthetic-account", clock=lambda: now,
                                ensure_active=cancelled)
    try:
        asyncio.run(limiter.acquire("/resource"))
    except RuntimeError as error:
        assert str(error) == "cancelled"
    else:
        raise AssertionError("cancelled task acquired a request slot")
    assert calls == ["check"]
    engine.dispose()


def test_rate_wait_checks_cancel_while_waiting_and_bounds_reservations(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rate_wait_verify.db'}")
    SourceRequestBudget.__table__.create(engine)
    now = datetime(2026, 9, 9, tzinfo=UTC)
    checks = []

    def cancel_during_wait():
        checks.append("check")
        if len(checks) == 2:
            raise RuntimeError("cancelled")

    limiter = SourceRateLimiter(engine, "synthetic-account", clock=lambda: now,
                                ensure_active=cancel_during_wait, maximum_wait=2)
    assert limiter.reserve("/resource") == 0
    try:
        asyncio.run(limiter.acquire("/resource"))
    except RuntimeError as error:
        assert str(error) == "cancelled"
    else:
        raise AssertionError("task ignored cancellation during rate wait")
    assert checks == ["check", "check"]
    assert limiter.reserve("/resource") == 2
    for _ in range(2):
        try:
            limiter.reserve("/resource")
        except RuntimeError as error:
            assert str(error) == "rate_limited"
        else:
            raise AssertionError("unbounded future request slot")
    later = SourceRateLimiter(engine, "synthetic-account", clock=lambda: now + timedelta(seconds=4))
    assert later.reserve("/resource") == 0
    engine.dispose()
