"""Local browser acceptance harness: real API/Worker, synthetic ERP transport only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from threading import Event, Thread

import httpx
import uvicorn
from sqlalchemy.engine import make_url
from zhixing_api.bootstrap import analyze_bootstrap, execute_bootstrap
from zhixing_api.database import Database, assert_test_database_url
from zhixing_jobs import JobRepository, WorkerRunner

from zhixing_worker.config import WorkerSettings
from zhixing_worker.main import build_lingxing_sync_handler


def response(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("access-token"):
        return httpx.Response(200, json={"code": 200, "data": {
            "access_token": "synthetic-browser-token", "refresh_token": "synthetic-refresh",
            "expires_in": 3600}})
    if request.url.path == "/erp/sc/data/seller/lists":
        return httpx.Response(200, json={"code": 0, "data": [
            {"sid": 991, "name": "Synthetic browser store", "status": 1}], "total": 1})
    if request.url.path == "/erp/sc/data/local_inventory/warehouse":
        return httpx.Response(200, json={"code": 0, "data": [
            {"wid": 992, "name": "Synthetic browser warehouse", "type": 1,
             "is_delete": 0}], "total": 1})
    if request.url.path == "/label/operation/v1/label/product/list":
        return httpx.Response(200, json={"code": 0, "data": {"list": [
            {"label_id": "993", "label_name": "Synthetic browser tag"}], "total": 1}})
    if request.url.path == "/erp/sc/routing/storage/spu/spuList":
        return httpx.Response(200, json={"code": 0, "data": [
            {"ps_id": 994, "spu": "SYNTHETIC-SPU", "spu_name": "Synthetic browser style",
             "cid": 7, "bid": 8, "developer_uid": 9, "cg_uid": 10, "status": 2}], "total": 1})
    if request.url.path == "/erp/sc/data/local_inventory/channelList":
        return httpx.Response(200, json={"code": 0, "data": [
            {"id": 995, "channel_name": "Synthetic browser channel", "enabled": 1,
             "provider": {"id": "7"}, "method_id": "9"}], "total": 1})
    if request.url.path == "/erp/sc/data/mws/orders":
        return httpx.Response(200, json={"code": 0, "data": [
            {"sid": 991, "amazon_order_id": f"SYNTHETIC-BROWSER-{currency}",
             "order_status": "Shipped", "order_total_amount": amount,
             "order_total_currency_code": currency,
             "purchase_date_local": "2026-09-09 13:00:00",
             "purchase_date_local_utc": "2026-09-09 13:00:00",
             "last_update_date_utc": "2026-09-09 13:01:00",
             "item_list": [{"seller_sku": "SYNTHETIC-SKU", "quantity_ordered": 1}]}
            for currency, amount in (("KWD", "1.125"), ("JPY", "100"))], "total": 2})
    if request.url.path == "/erp/sc/routing/wms/order/wmsOrderList":
        return httpx.Response(200, json={"code": 0, "total": 1, "data": [{
            "wo_id": 996, "wo_number": "SYNTHETIC-BROWSER-OUTBOUND", "sid": 991, "wid": 992,
            "status": 3, "logistics_status": 5, "order_number": "SYNTHETIC-SYSTEM-ORDER",
            "platform_order_no": ["SYNTHETIC-BROWSER-KWD"],
            "create_at": "2026-09-09 10:00:00", "update_at": "2026-09-09 11:00:00",
            "delivered_at": "2026-09-09 10:30:00", "logistics_freight": "1.125",
            "logistics_freight_currency_code": "KWD",
            "product_info": [{"wod_id": 997, "product_id": 998, "sku": "SYNTHETIC-SKU",
                              "count": 2, "bundle_type": 0}]}]})
    raise AssertionError("Browser fixture has no response for this resource")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args()
    assert_test_database_url(args.database_url)
    url = make_url(args.database_url)
    if url.get_backend_name() != "postgresql" or url.host != "127.0.0.1":
        raise ValueError("Only isolated loopback PostgreSQL is supported")
    root = Path(__file__).resolve().parents[3]
    archive = root / ".tmp" / "browser_verify_raw"
    os.environ.update({
        "APP_ENV": "test", "DATABASE_URL": args.database_url, "SEED_ENABLED": "false",
        "AGENT_RUNTIME_ENABLED": "false", "FILE_ASSET_STORAGE_PROVIDER": "local",
        "REDIS_ENABLED": "false", "LINGXING_ENABLED": "true",
        "SOURCE_ARCHIVE_PATH": str(archive), "API_CORS_ORIGINS": "http://127.0.0.1:3100",
        "LINGXING_APP_ID": "synthetic-app-16", "LINGXING_APP_SECRET": "synthetic-only",
    })
    database = Database(args.database_url)
    database.migrate()
    manifest = json.loads((root / "services/api/tests/fixtures/bootstrap-formal-synthetic.json")
                          .read_text(encoding="utf-8"))
    execute_bootstrap(database.engine, manifest, confirmed=True,
        backup_id="synthetic-browser-empty-database",
        plan_hash=analyze_bootstrap(database.engine, manifest)["plan_hash"],
        credential_provider=lambda _: "Synthetic-Password-Only-378!")
    settings = WorkerSettings(args.database_url, "browser-verify-worker", 0.2, 60, 1, 0,
        lingxing_enabled=True, lingxing_app_id="synthetic-app-16",
        lingxing_app_secret="synthetic-only", source_archive_path=str(archive))
    runner = WorkerRunner(JobRepository(database.engine), {"data-source.sync":
        build_lingxing_sync_handler(settings, database.engine,
                                   transport=httpx.MockTransport(response))},
        worker_id=settings.worker_id, poll_seconds=0.2, lease_seconds=60)
    stop = Event()
    worker = Thread(target=runner.run_forever, args=(stop,), daemon=True)
    worker.start()
    try:
        uvicorn.run("zhixing_api.main:app", host="127.0.0.1", port=8000, log_level="warning")
    finally:
        stop.set()
        worker.join(timeout=10)
        database.dispose()


if __name__ == "__main__":
    main()
