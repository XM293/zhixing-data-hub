"""Read existing report tasks; never create export tasks or persist download credentials."""
from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from .catalog import resource_spec, validate_resource_parameters
from .client import LingxingClient
from .transport_logging import redact_transport_logs

_STATES = {"IN_QUEUE": "waiting", "IN_PROGRESS": "waiting", "DONE": "ready",
           "CANCELLED": "cancelled", "FATAL": "failed", "UNKNOWN": "schema_pending"}


@dataclass(frozen=True)
class ReportSnapshot:
    state: str
    progress_status: str
    document_id: str | None
    compression: str | None
    url: str | None = field(repr=False)

    def safe_payload(self) -> dict[str, object]:
        return {"code": 0, "data": {
            "progress_status": self.progress_status, "report_document_id": self.document_id,
            "compression_algorithm": self.compression, "download_link_present": bool(self.url),
        }}


class ReportReader:
    def __init__(self, client: LingxingClient, *, download_hosts: frozenset[str] = frozenset(),
                 download_transport: httpx.AsyncBaseTransport | None = None,
                 max_bytes: int = 64 * 1024 * 1024,
                 ensure_active: Callable[[], object] | None = None):
        if not 0 < max_bytes <= 64 * 1024 * 1024:
            raise ValueError("invalid report size limit")
        self.client, self._download_hosts = client, download_hosts
        self._transport, self._max_bytes = download_transport, max_bytes
        self._ensure_active = ensure_active

    async def poll(self, parameters: dict[str, object]) -> ReportSnapshot:
        spec = resource_spec("report_export_status")
        if spec is None:
            raise RuntimeError("report.catalog_missing")
        payload = await self.client.request_json_post_with_retry(
            spec.path, body=validate_resource_parameters(spec, parameters),
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("report.schema_pending")
        status = str(data.get("progress_status"))
        if status not in _STATES:
            status = "UNKNOWN"
        document = data.get("report_document_id")
        document = (document if isinstance(document, str)
                    and re.fullmatch(r"[A-Za-z0-9_.:-]{1,300}", document) else None)
        url = data.get("url")
        url = url if isinstance(url, str) and len(url) <= 16384 else None
        compression = data.get("compression_algorithm")
        compression = (compression if compression is None or isinstance(compression, str)
                       and compression in {"", "GZIP"} else "UNKNOWN")
        state = _STATES[status]
        if state == "ready" and (not url or not document or compression == "UNKNOWN"):
            state = "schema_pending"
        return ReportSnapshot(state, status, document, compression, url)

    def _validate_download_url(self, url: str | None) -> str:
        if not self._download_hosts:
            raise RuntimeError("report.download_host_pending")
        try:
            parsed = urlsplit(url or "")
            host = parsed.hostname or ""
            if (parsed.scheme != "https" or host not in self._download_hosts
                    or parsed.username or parsed.password or parsed.port or parsed.fragment
                    or host == "localhost" or host.endswith(".localhost")):
                raise ValueError("host invalid")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError("literal IP is not an approved report domain")
        except ValueError:
            raise RuntimeError("report.download_host_blocked") from None
        return str(url)

    async def download(self, report: ReportSnapshot) -> bytes:
        if report.state != "ready":
            raise RuntimeError("report.not_ready")
        url = self._validate_download_url(report.url)
        if self._ensure_active:
            self._ensure_active()
        try:
            # Separate HTTP client carries no ERP token, signature, Cookie or auth headers.
            with redact_transport_logs():
                async with httpx.AsyncClient(transport=self._transport, timeout=60,
                                             follow_redirects=False, trust_env=False) as client:
                    async with client.stream("GET", url) as response:
                        if 300 <= response.status_code < 400:
                            raise RuntimeError("report.download_redirect_blocked")
                        if response.status_code in {401, 403, 404}:
                            raise RuntimeError("report.download_link_expired")
                        if response.status_code == 429 or response.status_code >= 500:
                            raise RuntimeError("external_retryable")
                        if response.status_code != 200:
                            raise RuntimeError("report.download_failed")
                        parts = bytearray()
                        async for part in response.aiter_raw(chunk_size=65536):
                            if self._ensure_active:
                                self._ensure_active()
                            if len(parts) + len(part) > self._max_bytes:
                                raise RuntimeError("report.download_too_large")
                            parts.extend(part)
                        return bytes(parts)
        except httpx.HTTPError:
            raise RuntimeError("external_retryable") from None
