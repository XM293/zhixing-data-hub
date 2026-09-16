from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

import httpx

from zhixing_api.config import Settings


class MemoryProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderMemory:
    memory_key: str
    content: str
    category: str


@dataclass(frozen=True, slots=True)
class ProviderHit:
    provider_id: str
    memory_key: str | None
    content: str
    score: float


class MemoryProvider(Protocol):
    key: str
    label: str
    protocol: str
    mode: str
    endpoint_fingerprint: str
    authentication_configured: bool

    async def health(self) -> None: ...

    async def index_memories(
        self,
        namespace: str,
        memories: list[ProviderMemory],
    ) -> int: ...

    async def search(
        self,
        namespace: str,
        query: str,
        *,
        top_k: int,
    ) -> list[ProviderHit]: ...


class _HTTPMemoryProvider:
    key = ""
    label = ""
    protocol = ""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        mode: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.mode = mode
        self.timeout_seconds = timeout_seconds
        self.endpoint_fingerprint = sha256(self.base_url.encode("utf-8")).hexdigest()[:16]
        self.authentication_configured = bool(api_key)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )


class TencentDBAgentMemoryProvider(_HTTPMemoryProvider):
    key = "tencentdb-agent-memory"
    label = "TencentDB Agent Memory"
    protocol = "gateway-v3"

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers.setdefault("Authorization", "Bearer local")
        headers["x-tdai-service-id"] = "zhixing-data-hub"
        return headers

    async def health(self) -> None:
        async with self._client() as client:
            response = await client.get("/health")
            response.raise_for_status()
            payload = _dict_payload(response)
        if payload.get("status") not in {"ok", "ready", "degraded"}:
            raise MemoryProviderError("TencentDB Agent Memory Gateway 健康状态不可用")

    async def index_memories(
        self,
        namespace: str,
        memories: list[ProviderMemory],
    ) -> int:
        messages = [
            {
                "role": "user",
                "content": (
                    f'<zhixing-memory key="{item.memory_key}">'
                    f"{item.content}</zhixing-memory>"
                ),
            }
            for item in memories
        ]
        body = {
            "team_id": "zhixing-enterprise",
            "agent_id": "role-memory-evaluation",
            "user_id": namespace,
            "session_id": namespace,
            "messages": messages,
        }
        async with self._client() as client:
            response = await client.post("/v3/conversation/add", json=body)
            response.raise_for_status()
            payload = _dict_payload(response)
        if payload.get("code") != 0:
            raise MemoryProviderError("TencentDB Agent Memory 拒绝写入评测命名空间")
        return len(memories)

    async def search(
        self,
        namespace: str,
        query: str,
        *,
        top_k: int,
    ) -> list[ProviderHit]:
        body = {
            "team_id": "zhixing-enterprise",
            "agent_id": "role-memory-evaluation",
            "user_id": namespace,
            "query": query,
            "limit": top_k,
        }
        async with self._client() as client:
            response = await client.post("/v3/atomic/search", json=body)
            response.raise_for_status()
            payload = _dict_payload(response)
        if payload.get("code") != 0:
            raise MemoryProviderError("TencentDB Agent Memory 召回请求失败")
        data = _dict_value(payload.get("data"))
        return [_tencent_hit(item) for item in _dict_list(data.get("items"))]


class Mem0MemoryProvider(_HTTPMemoryProvider):
    key = "mem0"
    label = "Mem0"
    protocol = "self-hosted-http-v1"

    async def health(self) -> None:
        async with self._client() as client:
            response = await client.get("/health")
            response.raise_for_status()
            payload = _dict_payload(response)
        if payload.get("status") not in {"ok", "ready", "healthy"}:
            raise MemoryProviderError("Mem0 服务健康状态不可用")

    async def index_memories(
        self,
        namespace: str,
        memories: list[ProviderMemory],
    ) -> int:
        async with self._client() as client:
            for memory in memories:
                response = await client.post(
                    "/memories",
                    json={
                        "messages": [{"role": "user", "content": memory.content}],
                        "user_id": namespace,
                        "agent_id": "zhixing-role-memory-evaluation",
                        "metadata": {
                            "memory_key": memory.memory_key,
                            "category": memory.category,
                        },
                        "infer": False,
                    },
                )
                response.raise_for_status()
                _dict_payload(response)
        return len(memories)

    async def search(
        self,
        namespace: str,
        query: str,
        *,
        top_k: int,
    ) -> list[ProviderHit]:
        async with self._client() as client:
            response = await client.post(
                "/search",
                json={
                    "query": query,
                    "filters": {"user_id": namespace},
                    "top_k": top_k,
                },
            )
            response.raise_for_status()
            payload = _dict_payload(response)
        return [_mem0_hit(item) for item in _dict_list(payload.get("results"))]


def build_memory_providers(settings: Settings) -> dict[str, MemoryProvider]:
    providers: list[MemoryProvider] = [
        TencentDBAgentMemoryProvider(
            base_url=settings.tencentdb_memory_base_url,
            api_key=settings.tencentdb_memory_api_key,
            mode=settings.memory_provider_mode,
            timeout_seconds=settings.memory_provider_timeout_seconds,
        ),
        Mem0MemoryProvider(
            base_url=settings.mem0_base_url,
            api_key=settings.mem0_api_key,
            mode=settings.memory_provider_mode,
            timeout_seconds=settings.memory_provider_timeout_seconds,
        ),
    ]
    return {provider.key: provider for provider in providers}


def _dict_payload(response: httpx.Response) -> dict[str, object]:
    payload: object = response.json()
    if not isinstance(payload, dict):
        raise MemoryProviderError("记忆 Provider 返回了非对象响应")
    return {str(key): value for key, value in payload.items()}


def _dict_value(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [_dict_value(item) for item in value if isinstance(item, dict)]


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _number(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _tencent_hit(item: dict[str, object]) -> ProviderHit:
    metadata = _dict_value(item.get("metadata"))
    memory_key = _string(metadata.get("memory_key")) or None
    return ProviderHit(
        provider_id=_string(item.get("id")),
        memory_key=memory_key,
        content=_string(item.get("content")),
        score=_number(item.get("score")),
    )


def _mem0_hit(item: dict[str, object]) -> ProviderHit:
    metadata = _dict_value(item.get("metadata"))
    memory_key = _string(metadata.get("memory_key")) or None
    return ProviderHit(
        provider_id=_string(item.get("id")),
        memory_key=memory_key,
        content=_string(item.get("memory")),
        score=_number(item.get("score")),
    )
