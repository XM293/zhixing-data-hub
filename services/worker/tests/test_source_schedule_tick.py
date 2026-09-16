from zhixing_api.database import Database

from zhixing_worker.scheduling import SourceScheduleTick


def test_worker_tick_dispatches_incremental_and_backfill_plans(tmp_path, monkeypatch):
    database = Database(f"sqlite:///{tmp_path / 'tick_verify.db'}")
    database.migrate()
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr("zhixing_worker.scheduling.dispatch_due",
                        lambda _database, *, provider_enabled: calls.append(
                            ("incremental", provider_enabled)))
    monkeypatch.setattr("zhixing_worker.scheduling.dispatch_backfills",
                        lambda _database, *, provider_enabled: calls.append(
                            ("backfill", provider_enabled)))
    tick = SourceScheduleTick(database.engine, enabled=True)
    tick()
    assert calls == [("incremental", True), ("backfill", True)]
    database.dispose()


def test_worker_tick_skips_backfills_during_0071_rolling_upgrade(tmp_path, monkeypatch):
    database = Database(f"sqlite:///{tmp_path / 'tick_0071_verify.db'}")
    database.migrate("0071_source_binding_suggestions")
    calls: list[str] = []
    monkeypatch.setattr("zhixing_worker.scheduling.dispatch_due",
                        lambda _database, *, provider_enabled: calls.append("incremental"))
    monkeypatch.setattr("zhixing_worker.scheduling.dispatch_backfills",
                        lambda _database, *, provider_enabled: calls.append("backfill"))
    tick = SourceScheduleTick(database.engine, enabled=True)
    tick()
    assert calls == ["incremental"]
    database.dispose()
