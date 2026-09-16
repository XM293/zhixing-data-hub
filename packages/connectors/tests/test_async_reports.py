import asyncio
import logging

import httpx
import pytest
from zhixing_connectors import LingxingClient, LingxingConfig
from zhixing_connectors.reports import ReportReader


def test_report_states_strip_download_credentials_and_block_unknown_host(caplog):
    caplog.set_level(logging.DEBUG)

    async def run():
        state = "IN_QUEUE"
        seen = []

        def response(request):
            seen.append(request.url.host)
            return httpx.Response(200, json={"code": 0, "data": {
                "progress_status": state, "report_document_id": "synthetic-report",
                "compression_algorithm": "GZIP",
                "url": "https://untrusted.example.test/report?signature=synthetic-private-link",
            }})
        client = LingxingClient(LingxingConfig("synthetic-app-16", "synthetic-secret"),
                                 httpx.MockTransport(response))
        reader = ReportReader(client)
        parameters = {"seller_id": "SELLER_VERIFY", "task_id": "task-verify", "region": "na"}
        try:
            for status, expected in (("IN_QUEUE", "waiting"), ("IN_PROGRESS", "waiting"),
                                     ("DONE", "ready"), ("FATAL", "failed"),
                                     ("CANCELLED", "cancelled"), ("future", "schema_pending")):
                state = status
                report = await reader.poll(parameters)
                assert report.state == expected
                assert "synthetic-private" not in repr(report) + str(report.safe_payload())
            state = "DONE"
            report = await reader.poll(parameters)
            with pytest.raises(RuntimeError, match="host_pending"):
                await reader.download(report)
            assert set(seen) == {"openapi.lingxing.com"}
        finally:
            await client.close()
    asyncio.run(run())
    assert "synthetic-private-link" not in caplog.text


def test_report_download_is_bounded_and_never_forwards_erp_credentials(caplog):
    caplog.set_level(logging.DEBUG)

    async def run():
        mode = "success"
        downloaded = []

        def response(request):
            if request.url.host == "openapi.lingxing.com":
                return httpx.Response(200, json={"code": 0, "data": {
                    "progress_status": "DONE", "report_document_id": "synthetic-report",
                    "compression_algorithm": "GZIP",
                    "url": "https://reports.example.test/file?signature=synthetic-private-link",
                }})
            downloaded.append(request)
            assert "Authorization" not in request.headers
            assert "access_token" not in request.url.params
            if mode == "redirect":
                return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
            return httpx.Response(200, stream=httpx.ByteStream(b"synthetic-report-bytes"))

        transport = httpx.MockTransport(response)
        client = LingxingClient(LingxingConfig("synthetic-app-16", "synthetic-secret"), transport)
        reader = ReportReader(client, download_hosts=frozenset({"reports.example.test"}),
                              download_transport=transport, max_bytes=64)
        try:
            report = await reader.poll({"seller_id": "SELLER_VERIFY", "task_id": "task-verify",
                                        "region": "eu"})
            assert await reader.download(report) == b"synthetic-report-bytes"
            mode = "redirect"
            with pytest.raises(RuntimeError, match="redirect"):
                await reader.download(report)
            mode = "success"
            small = ReportReader(client, download_hosts=frozenset({"reports.example.test"}),
                                 download_transport=transport, max_bytes=5)
            with pytest.raises(RuntimeError, match="too_large"):
                await small.download(report)
            assert len(downloaded) == 3
        finally:
            await client.close()
    asyncio.run(run())
    assert "synthetic-private-link" not in caplog.text
