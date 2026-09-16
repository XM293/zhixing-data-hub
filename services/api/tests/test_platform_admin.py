from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from zhixing_jobs import EnqueueJob, JobRepository

from zhixing_api.config import Settings
from zhixing_api.main import create_app

ADMIN = {"X-Zhixing-Demo-Actor": "admin"}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://test",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'platform-admin-test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:9",
        file_asset_storage_path=str(tmp_path / "objects"),
    )


@pytest.mark.anyio
async def test_jobs_keep_attempt_history_and_support_controlled_retry(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    repository = JobRepository(app.state.database.engine)
    queued = repository.enqueue(
        EnqueueJob(
            enterprise_id="ent_zhixing_demo",
            job_type="test.controlled-retry",
            payload={"record": "row-1"},
            idempotency_key="job-controlled-retry-001",
            initiator_type="principal",
            initiator_id="principal-platform-admin",
            actor_snapshot={"principal_id": "principal-platform-admin"},
            permission_set_version="access-test",
            required_permissions=("operations.run.read",),
            scope_type="enterprise",
            scope_id="ent_zhixing_demo",
            run_id="run_platform_admin_test",
        )
    ).job
    claimed = repository.claim("worker-test")
    assert claimed is not None and claimed.id == queued.id
    for progress in range(1, 5):
        repository.continue_job(claimed.id, "worker-test", progress=progress,
                                execution_token=claimed.execution_token)
        claimed = repository.claim("worker-test")
        assert claimed is not None and claimed.id == queued.id
    repository.fail(
        claimed.id,
        "worker-test",
        error_code="test.failed",
        error_message="expected failure",
        retryable=False,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            f"/api/v1/platform/admin/jobs/{queued.id}/retry",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={
                "schema_version": 1,
                "client_request_key": "retry-job-employee-001",
                "reason": "员工不应管理任务",
                "expected_attempt": 5,
            },
        )
        detail = await client.get(f"/api/v1/platform/admin/jobs/{queued.id}", headers=ADMIN)
        retry_payload = {
            "schema_version": 1,
            "client_request_key": "retry-job-admin-001",
            "reason": "修正测试处理器后重新运行",
            "expected_attempt": 5,
        }
        retried = await client.post(
            f"/api/v1/platform/admin/jobs/{queued.id}/retry",
            headers=ADMIN,
            json=retry_payload,
        )
        replay = await client.post(
            f"/api/v1/platform/admin/jobs/{queued.id}/retry",
            headers=ADMIN,
            json=retry_payload,
        )

    assert denied.status_code == 403
    assert detail.status_code == 200
    assert sum(item["status"] == "continued" for item in detail.json()["attempts"]) == 4
    assert sum(item["status"] == "failed" for item in detail.json()["attempts"]) == 1
    assert detail.json()["job"]["continuation_count"] == 4
    assert retried.status_code == 200
    assert retried.json()["job"]["status"] == "queued"
    assert retried.json()["job"]["max_attempts"] == 3
    assert replay.json()["replayed"] is True


@pytest.mark.anyio
async def test_config_notifications_and_file_assets_are_database_backed(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        config = await client.get("/api/v1/platform/admin/config", headers=ADMIN)
        parameter = next(
            item
            for item in config.json()["parameters"]
            if item["parameter_key"] == "agent.default-evidence-limit"
        )
        configured = await client.put(
            "/api/v1/platform/admin/config/parameters/agent.default-evidence-limit",
            headers=ADMIN,
            json={
                "schema_version": 1,
                "client_request_key": "parameter-evidence-limit-001",
                "reason": "提高经营分析证据覆盖",
                "expected_revision": parameter["revision"],
                "value": 18,
                "status": "active",
            },
        )
        published = await client.post(
            "/api/v1/platform/admin/notifications",
            headers=ADMIN,
            json={
                "schema_version": 1,
                "client_request_key": "notification-employee-001",
                "reason": "发布数据质量处理通知",
                "principal_ids": ["principal-employee-demo"],
                "category": "data-quality",
                "title": "门店数据质量待处理",
                "body": "旗舰店订单完整率低于阈值。",
                "severity": "warning",
                "action_route": "/console/data/quality",
                "channels": ["inbox", "feishu"],
            },
        )
        inbox = await client.get(
            "/api/v1/platform/notifications",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        content = b"file asset verification"
        uploaded = await client.post(
            "/api/v1/platform/admin/files",
            headers=ADMIN,
            json={
                "schema_version": 1,
                "client_request_key": "file-asset-test-001",
                "reason": "保存批量交换固定样例",
                "asset_key": "exchange.sample.csv",
                "file_name": "sample.csv",
                "media_type": "text/csv",
                "content_base64": base64.b64encode(content).decode(),
                "category": "exchange",
                "required_permission": "file.asset.read",
                "scope_type": "enterprise",
                "scope_id": "ent_zhixing_demo",
            },
        )
        downloaded = await client.get(
            f"/api/v1/platform/admin/files/{uploaded.json()['asset']['id']}/content",
            headers=ADMIN,
        )

    assert config.status_code == configured.status_code == 200
    assert published.status_code == uploaded.status_code == 201
    assert inbox.status_code == downloaded.status_code == 200
    assert any(item["title"] == "门店数据质量待处理" for item in inbox.json()["items"])
    assert downloaded.content == content
    assert uploaded.json()["asset"]["checksum_sha256"]


@pytest.mark.anyio
async def test_bulk_exchange_and_temporary_delegation_are_governed(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    now = datetime.now(UTC)
    csv_content = (
        "dictionary_key,item_key,label,value,sort_order,status\n"
        "business-severity,notice,关注,notice,15,active\n"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        preflight = await client.post(
            "/api/v1/platform/admin/bulk-exchanges/preflight",
            headers=ADMIN,
            json={
                "schema_version": 1,
                "client_request_key": "exchange-preflight-001",
                "reason": "导入业务严重程度字典",
                "dataset_key": "platform.dictionary-items",
                "file_format": "csv",
                "content": csv_content,
            },
        )
        job_id = preflight.json()["job"]["id"]
        committed = await client.post(
            f"/api/v1/platform/admin/bulk-exchanges/{job_id}/commit",
            headers=ADMIN,
            json={
                "schema_version": 1,
                "client_request_key": "exchange-commit-001",
                "reason": "预检通过后写入平台字典",
            },
        )
        exported = await client.post(
            "/api/v1/platform/admin/bulk-exchanges/export",
            headers=ADMIN,
            json={
                "schema_version": 1,
                "client_request_key": "exchange-export-001",
                "reason": "导出当前平台字典",
                "dataset_key": "platform.dictionary-items",
                "file_format": "csv",
            },
        )
        exported_asset_id = exported.json()["job"]["validation_summary"]["file_asset_id"]
        exported_file = await client.get(
            f"/api/v1/platform/admin/files/{exported_asset_id}/content", headers=ADMIN
        )
        delegation = await client.post(
            "/api/v1/platform/admin/access-governance/delegations",
            headers=ADMIN,
            json={
                "schema_version": 1,
                "client_request_key": "delegation-role-twin-read-001",
                "reason": "经营复盘期间临时查看分身配置",
                "delegation_key": "ceo-to-employee-review",
                "delegator_principal_id": "principal-ceo-lin",
                "delegatee_principal_id": "principal-employee-demo",
                "permissions": ["role-twin.read"],
                "scopes": [
                    {
                        "scope_type": "enterprise",
                        "scope_ids": ["ent_zhixing_demo"],
                        "effect": "allow",
                    }
                ],
                "valid_from": (now - timedelta(minutes=1)).isoformat(),
                "valid_to": (now + timedelta(days=1)).isoformat(),
            },
        )
        employee = await client.get(
            "/api/v1/identity/me", headers={"X-Zhixing-Demo-Actor": "employee"}
        )
        governance = await client.get(
            "/api/v1/platform/admin/access-governance", headers=ADMIN
        )
        delegation_payload = delegation.json()["delegation"]
        revoked = await client.post(
            "/api/v1/platform/admin/access-governance/delegations/"
            f"{delegation_payload['id']}/revoke",
            headers=ADMIN,
            json={
                "schema_version": 1,
                "client_request_key": "delegation-revoke-001",
                "reason": "经营复盘已结束",
                "expected_revision": delegation_payload["revision"],
            },
        )
        employee_after = await client.get(
            "/api/v1/identity/me", headers={"X-Zhixing-Demo-Actor": "employee"}
        )
        audit = await client.get(
            "/api/v1/audit/events", headers=ADMIN, params={"source": "platform"}
        )

    assert preflight.status_code == 201
    assert preflight.json()["job"]["status"] == "ready"
    assert committed.status_code == 200
    assert committed.json()["job"]["applied_rows"] == 1
    assert exported.status_code == 201
    assert "business-severity" in exported_file.content.decode("utf-8-sig")
    assert delegation.status_code == 201
    assert governance.status_code == 200
    assert governance.json()["delegations"][0]["delegation_key"] == "ceo-to-employee-review"
    assert "role-twin.read" in employee.json()["actor"]["permissions"]
    assert revoked.status_code == 200
    assert "role-twin.read" not in employee_after.json()["actor"]["permissions"]
    assert audit.status_code == 200
    assert audit.json()["stats"]["total_events"] >= 3
