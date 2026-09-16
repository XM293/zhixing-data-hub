from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4


class RedisCoordinator:
    def __init__(self, url: str, *, key_prefix: str) -> None:
        try:
            from redis import asyncio as redis
        except ImportError as exc:  # pragma: no cover - dependency is installed in runtime
            raise RuntimeError("Redis 依赖未安装") from exc
        self._client = redis.from_url(  # type: ignore[no-untyped-call]
            url,
            decode_responses=True,
        )
        self._key_prefix = key_prefix.strip(":") or "zhixing"

    async def ready(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    @asynccontextmanager
    async def lease(self, name: str, *, ttl_seconds: int) -> AsyncIterator[bool]:
        key = f"{self._key_prefix}:lease:{name}"
        token = uuid4().hex
        acquired = False
        try:
            acquired = bool(await self._client.set(key, token, nx=True, ex=max(ttl_seconds, 1)))
            yield acquired
        finally:
            if acquired:
                await self._client.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then "
                    "return redis.call('del', KEYS[1]) else return 0 end",
                    1,
                    key,
                    token,
                )

    async def close(self) -> None:
        await self._client.aclose()


class NoopRedisCoordinator:
    async def ready(self) -> bool:
        return True

    @asynccontextmanager
    async def lease(self, name: str, *, ttl_seconds: int) -> AsyncIterator[bool]:
        del name, ttl_seconds
        yield True

    async def close(self) -> None:
        return None


def build_redis_coordinator(
    *, enabled: bool, url: str, key_prefix: str
) -> RedisCoordinator | NoopRedisCoordinator:
    if not enabled:
        return NoopRedisCoordinator()
    return RedisCoordinator(url, key_prefix=key_prefix)
