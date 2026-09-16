from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from time import monotonic, time
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

import httpx

from .auth import CredentialProvider
from .catalog import OPERATION_HEADERS, READ_ONLY_OPERATIONS
from .signing import build_signature, wire_value
from .transport_logging import redact_transport_logs

ALLOWED_HOST = "openapi.lingxing.com"
READ_ONLY_PATHS = frozenset(path for _, path in READ_ONLY_OPERATIONS)


class LingxingBusinessError(RuntimeError):
    """A redacted permanent business failure with a bounded provider code."""

    def __init__(self, code: object):
        value = str(code)
        self.code = value if re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", value) else "unknown"
        super().__init__("lingxing_business_error")


class RequestRateLimiter(Protocol):
    async def acquire(self, path: str) -> None: ...


@dataclass(frozen=True)
class LingxingConfig:
    app_id: str = field(repr=False)
    app_secret: str = field(repr=False)
    base_url: str = "https://openapi.lingxing.com"
    read_only_post_paths: frozenset[str] = field(default_factory=frozenset, repr=False)

    def validate(self) -> None:
        parsed = urlsplit(self.base_url)
        invalid = (
            parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST
            or parsed.username or parsed.password or parsed.port
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
        )
        if invalid:
            raise ValueError("untrusted lingxing host")


class LingxingClient:
    def __init__(
        self, config: LingxingConfig,
        transport: httpx.AsyncBaseTransport | None = None,
        credential_provider: CredentialProvider | None = None,
        rate_limiter: RequestRateLimiter | None = None,
    ):
        config.validate()
        self.config, self.credential_provider = config, credential_provider
        self.http = httpx.AsyncClient(base_url=config.base_url, transport=transport, timeout=60)
        self._last_request: dict[str, float] = {}
        self._throttle_lock = asyncio.Lock()
        self._rate_limiter = rate_limiter

    async def close(self) -> None:
        await self.http.aclose()

    async def request(
        self, path: str, *, params: dict[str, object] | None = None
    ) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def request_json_post(
        self, path: str, *, body: dict[str, object] | None = None
    ) -> dict[str, Any]:
        return await self._request("POST", path, params=None, body=body or {})

    async def request_multipart(
        self,
        path: str,
        *,
        fields: dict[str, object] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue a read-only multipart request.

        Only scalar multipart fields participate in the Lingxing signature. File
        bytes are intentionally never logged or included in the canonical query.
        """
        return await self._request_multipart(path, fields or {}, files or {})

    async def _request_multipart(
        self, path: str, fields: dict[str, object], files: dict[str, Any]
    ) -> dict[str, Any]:
        if ("POST", path) not in READ_ONLY_OPERATIONS:
            raise ValueError("lingxing write or unknown resource blocked")
        token = await self.credential_provider.get() if self.credential_provider else None
        public = {k: v for k, v in fields.items() if v != ""}
        if token:
            public.update({"access_token": token.value, "app_key": self.config.app_id,
                           "timestamp": str(int(time()))})
        data = {k: wire_value(v) for k, v in fields.items() if v != ""}
        if token:
            data.update({"access_token": token.value, "app_key": self.config.app_id,
                         "timestamp": str(public["timestamp"]),
                         "sign": build_signature(public, self.config.app_id)})
        await self._throttle(path)
        try:
            with redact_transport_logs():
                response = await self.http.post(path, data=data, files=cast(Any, files))
        except httpx.HTTPError:
            raise RuntimeError("external_retryable") from None
        return self._parse_response(response)

    async def _request(
        self, method: str, path: str, *, params: dict[str, object] | None,
        body: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        if (method, path) not in READ_ONLY_OPERATIONS:
            raise ValueError("lingxing write or unknown resource blocked")
        token = await self.credential_provider.get() if self.credential_provider else None
        public = {**(params or {}), **(body or {})}
        if token:
            public.update({
                "access_token": token.value,
                "app_key": self.config.app_id,
                "timestamp": str(int(time())),
            })
        # The wire representation must be byte-for-byte identical to the value
        # included in the signature. ``str(list)`` adds spaces and single quotes,
        # while Lingxing signs JSON.stringify-style compact JSON. This matters for
        # GET resources such as reviewReport/lists whose ``sid`` is an array.
        query = {k: wire_value(v) for k, v in (params or {}).items() if v != ""}
        if token:
            query.update({
                "access_token": token.value, "app_key": self.config.app_id,
                "timestamp": str(public["timestamp"]),
                "sign": build_signature(public, self.config.app_id),
            })
        await self._throttle(path)
        try:
            with redact_transport_logs():
                response = await self.http.request(method, path, params=query, json=body,
                                                   headers=OPERATION_HEADERS[(method, path)])
        except httpx.HTTPError:
            raise RuntimeError("external_retryable") from None
        return self._parse_response(response)

    async def _throttle(self, path: str, minimum_interval: float = 1.0) -> None:
        """Apply the shared budget or conservative per-client request spacing."""
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire(path)
            return
        async with self._throttle_lock:
            now = monotonic()
            wait_for = minimum_interval - (now - self._last_request.get(path, 0.0))
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_request[path] = monotonic()

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        if response.status_code == 429:
            raise RuntimeError("rate_limited")
        if response.status_code >= 500:
            raise RuntimeError("external_retryable")
        if response.status_code >= 400:
            raise RuntimeError("external_permanent")
        payload: object
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("lingxing response was not JSON") from exc
        if isinstance(payload, dict) and str(payload.get("code")) == "3001008":
            raise RuntimeError("rate_limited")
        if not isinstance(payload, dict):
            raise RuntimeError("lingxing response shape invalid")
        code = str(payload.get("code"))
        # Lingxing's newer Amazon endpoints use ``code=1`` for success while
        # legacy endpoints use ``0``/``200``.  Do not accept every ``1`` as
        # success: some endpoints also use it for validation failures.  The
        # newer success envelopes carry either ``success=true`` or an explicit
        # success message, so require that positive marker before accepting it.
        success_message = str(payload.get("msg", payload.get("message", ""))).strip().casefold()
        code_one_success = code == "1" and (
            payload.get("success") is True
            or success_message in {"成功", "操作成功", "success", "ok"}
        )
        if code not in {"0", "200"} and not code_one_success:
            raise LingxingBusinessError(payload.get("code"))
        return cast(dict[str, Any], payload)

    async def request_with_retry(
        self, path: str, *, params: dict[str, object] | None = None, attempts: int = 3
    ) -> dict[str, Any]:
        for attempt in range(max(1, attempts)):
            try:
                return await self.request(path, params=params)
            except RuntimeError as exc:
                if (
                    str(exc) not in {"rate_limited", "external_retryable"}
                    or attempt + 1 >= attempts
                ):
                    raise
                await asyncio.sleep(min(2**attempt, 8))
        raise AssertionError("unreachable")

    async def request_json_post_with_retry(
        self,
        path: str,
        *,
        body: dict[str, object] | None = None,
        attempts: int = 3,
    ) -> dict[str, Any]:
        for attempt in range(max(1, attempts)):
            try:
                return await self.request_json_post(path, body=body)
            except RuntimeError as exc:
                if (
                    str(exc) not in {"rate_limited", "external_retryable"}
                    or attempt + 1 >= attempts
                ):
                    raise
                await asyncio.sleep(min(2**attempt, 8))
        raise AssertionError("unreachable")
