from __future__ import annotations

import asyncio
import hashlib
import json
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from .transport_logging import redact_transport_logs


@dataclass(frozen=True)
class AccessToken:
    value: str = field(repr=False)
    expires_at: datetime


class CredentialProvider(Protocol):
    async def get(self) -> AccessToken: ...


class TokenProvider:
    def __init__(self, fetch: Callable[[], Awaitable[AccessToken]], refresh_before: int = 60):
        self._fetch, self._refresh_before = fetch, refresh_before
        self._token: AccessToken | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> AccessToken:
        now = datetime.now(UTC)
        if self._token and self._token.expires_at > now + timedelta(seconds=self._refresh_before):
            return self._token
        async with self._lock:
            now = datetime.now(UTC)
            if self._token and self._token.expires_at > now + timedelta(
                seconds=self._refresh_before
            ):
                return self._token
            self._token = await self._fetch()
            return self._token


class LingxingTokenProvider:
    def __init__(
        self, app_id: str, app_secret: str, base_url: str, *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or parsed.hostname != "openapi.lingxing.com"
                or parsed.username or parsed.password or parsed.port
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
            raise ValueError("untrusted lingxing host")
        self._app_id, self._app_secret = app_id, app_secret
        self._base_url, self._transport = base_url.rstrip("/"), transport
        self._access: AccessToken | None = None
        self._refresh_token: str | None = None
        self._lock = Lock()

    @asynccontextmanager
    async def _refresh_lock(self) -> AsyncIterator[None]:
        # Worker tasks can use successive event loops; cancellation must not strand a lock.
        while not self._lock.acquire(blocking=False):  # noqa: ASYNC110 -- lock spans event loops
            await asyncio.sleep(0.01)
        try:
            yield
        finally:
            self._lock.release()

    async def get(self) -> AccessToken:
        now = datetime.now(UTC)
        if self._access and self._access.expires_at > now + timedelta(seconds=60):
            return self._access
        async with self._refresh_lock():
            now = datetime.now(UTC)
            if self._access and self._access.expires_at > now + timedelta(seconds=60):
                return self._access
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=30, transport=self._transport
            ) as client:
                if self._refresh_token:
                    response = await self._post(client,
                        "/api/auth-server/oauth/refresh",
                        files={
                            "appId": (None, self._app_id),
                            "refreshToken": (None, self._refresh_token),
                        },
                    )
                    if self._business_code(response) == "200":
                        self._set(response)
                        return self._access  # type: ignore[return-value]
                    self._refresh_token = None
                response = await self._post(client,
                    "/api/auth-server/oauth/access-token",
                    files={"appId": (None, self._app_id), "appSecret": (None, self._app_secret)},
                )
                self._set(response)
                return self._access  # type: ignore[return-value]

    def _set(self, response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise RuntimeError("lingxing token request failed")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("lingxing token response was not JSON") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("lingxing token response invalid")
        data = payload.get("data") if str(payload.get("code")) == "200" else None
        if not isinstance(data, dict):
            raise RuntimeError("lingxing token request failed")
        value, refresh = str(data.get("access_token") or ""), str(data.get("refresh_token") or "")
        try:
            expires = int(data.get("expires_in", 0))
        except (ValueError, TypeError):
            raise RuntimeError("lingxing token response invalid") from None
        if not value or not refresh or expires <= 0:
            raise RuntimeError("lingxing token response invalid")
        self._access = AccessToken(
            value, datetime.now(UTC) + timedelta(seconds=expires)
        )
        self._refresh_token = refresh

    @staticmethod
    async def _post(client: httpx.AsyncClient, path: str, *,
                    files: dict[str, tuple[None, str]]) -> httpx.Response:
        try:
            with redact_transport_logs():
                return await client.post(path, files=files)
        except httpx.HTTPError:
            raise RuntimeError("external_retryable") from None

    @staticmethod
    def _business_code(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""
        return str(payload.get("code")) if isinstance(payload, dict) else ""


class LingxingTokenCache:
    """Bounded process memory only; credential rotation selects a fresh provider."""

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None, capacity: int = 64):
        if capacity < 1:
            raise ValueError("invalid token cache capacity")
        self._transport, self._capacity = transport, capacity
        self._providers: OrderedDict[str, LingxingTokenProvider] = OrderedDict()
        self._lock = Lock()

    def provider(self, app_id: str, app_secret: str, base_url: str) -> LingxingTokenProvider:
        key = hashlib.sha256(json.dumps([app_id, app_secret, base_url]).encode()).hexdigest()
        with self._lock:
            provider = self._providers.get(key)
            if provider is None:
                provider = LingxingTokenProvider(app_id, app_secret, base_url,
                                                transport=self._transport)
                self._providers[key] = provider
            self._providers.move_to_end(key)
            while len(self._providers) > self._capacity:
                self._providers.popitem(last=False)
            return provider
