from types import SimpleNamespace

import httpx
import pytest
from zhixing_jobs import PermanentJobError, RetryableJobError

from zhixing_worker.archive import RawArchive
from zhixing_worker.config import WorkerSettings
from zhixing_worker.main import _execute_lingxing_sync


@pytest.mark.parametrize("status,allowed", [
    ("IN_PROGRESS", False), ("DONE", False), ("DONE", True),
])
def test_worker_records_report_state_without_credentials_and_downloads_only_when_trusted(
    tmp_path, status, allowed,
):
    committed = []

    def respond(request):
        if request.url.path.endswith("access-token"):
            return httpx.Response(200, json={"code": 200, "data": {
                "access_token": "synthetic", "refresh_token": "synthetic", "expires_in": 3600}})
        if request.url.host == "reports.example.test":
            return httpx.Response(200, stream=httpx.ByteStream(b"synthetic-report-bytes"))
        return httpx.Response(200, json={"code": 0, "data": {
            "progress_status": status, "report_document_id": "synthetic-report",
            "compression_algorithm": "GZIP",
            "url": "https://reports.example.test/file?signature=synthetic-private-link",
        }})

    settings = WorkerSettings(database_url="sqlite://", worker_id="verify", poll_seconds=0,
        lease_seconds=60, retry_delay_seconds=0, schema_wait_seconds=0,
        lingxing_app_id="synthetic-app-16", lingxing_app_secret="synthetic", lingxing_enabled=True,
        source_archive_path=str(tmp_path / "raw"),
        report_download_hosts=("reports.example.test",) if allowed else ())
    job = SimpleNamespace(enterprise_id="a", attempt=2, payload={
        "provider": "lingxing", "resource_key": "report_export_status",
        "resource_parameters": {
            "seller_id": "SELLER_VERIFY", "task_id": "task-verify", "region": "na",
        },
        "scope_snapshot": {"enterprise_id": "a"},
    })

    def execute():
        return _execute_lingxing_sync(job, SimpleNamespace(ensure_active=lambda: None), settings,
            transport=httpx.MockTransport(respond),
            persist_page=lambda item, payload, parameters: committed.append((item, payload)))

    if status == "IN_PROGRESS":
        with pytest.raises(RetryableJobError) as pending:
            execute()
        assert pending.value.retry_after_seconds == 30
    elif not allowed:
        with pytest.raises(PermanentJobError) as blocked:
            execute()
        assert blocked.value.code == "sync.report.download_host_pending"
    else:
        result = execute()
        assert result["row_count"] == 0
        assert len(committed) == 2
        blob = committed[1][0]
        raw = RawArchive(tmp_path / "raw").read_bytes(blob["storage_key"], blob["content_hash"])
        assert raw == b"synthetic-report-bytes"
    assert committed[0][0]["page"] == 3
    assert "synthetic-private-link" not in str(committed)
    for item, _ in committed:
        raw = RawArchive(tmp_path / "raw").read_bytes(item["storage_key"], item["content_hash"])
        assert b"synthetic-private-link" not in raw
