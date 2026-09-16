from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass

from fastapi import FastAPI
from pydantic import BaseModel, Field

from mock_memory import __version__

_MARKER = re.compile(r'^<zhixing-memory key="([^"]+)">(.*)</zhixing-memory>$', re.DOTALL)
_TOKEN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)


class Message(BaseModel):
    role: str
    content: str


class TencentConversationAdd(BaseModel):
    team_id: str
    agent_id: str
    user_id: str
    session_id: str = ""
    messages: list[Message]


class TencentAtomicSearch(BaseModel):
    team_id: str
    agent_id: str
    user_id: str
    query: str
    limit: int = Field(default=5, ge=1, le=50)
    type: str | None = None


class Mem0Create(BaseModel):
    messages: list[Message]
    user_id: str
    agent_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, object] | None = None
    infer: bool | None = None


class Mem0Search(BaseModel):
    query: str
    filters: dict[str, object] = Field(default_factory=dict)
    top_k: int = Field(default=5, ge=1, le=50)


@dataclass(frozen=True, slots=True)
class StoredMemory:
    provider_id: str
    memory_key: str
    content: str
    metadata: dict[str, object]


def _tokens(value: str) -> set[str]:
    return {item.casefold() for item in _TOKEN.findall(value)}


def _score(query: str, content: str) -> float:
    query_tokens = _tokens(query)
    content_tokens = _tokens(content)
    if not query_tokens or not content_tokens:
        return 0.0
    overlap = len(query_tokens & content_tokens)
    return round(overlap / len(query_tokens), 6)


def _memory_key(content: str) -> tuple[str, str]:
    marker = _MARKER.match(content.strip())
    if marker:
        return marker.group(1), marker.group(2).strip()
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"sandbox-{digest}", content.strip()


def _rank(
    records: list[StoredMemory],
    query: str,
    limit: int,
) -> list[tuple[StoredMemory, float]]:
    ranked = [(item, _score(query, item.content)) for item in records]
    ranked.sort(key=lambda item: (-item[1], item[0].memory_key))
    return ranked[:limit]


def create_app() -> FastAPI:
    app = FastAPI(
        title="知行数枢记忆 Provider 契约沙箱",
        version=__version__,
    )
    tencent_records: dict[str, dict[str, StoredMemory]] = {}
    mem0_records: dict[str, dict[str, StoredMemory]] = {}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"service": "mock-memory", "status": "ready", "version": __version__}

    @app.get("/tencentdb/health")
    async def tencent_health() -> dict[str, str]:
        return {"status": "ok", "storage": "in-memory-contract-sandbox"}

    @app.post("/tencentdb/v3/conversation/add")
    async def tencent_conversation_add(payload: TencentConversationAdd) -> dict[str, object]:
        await asyncio.sleep(0.008)
        namespace = f"{payload.team_id}:{payload.agent_id}:{payload.user_id}"
        target = tencent_records.setdefault(namespace, {})
        for message in payload.messages:
            key, content = _memory_key(message.content)
            provider_id = f"tdai-{hashlib.sha256((namespace + key).encode()).hexdigest()[:20]}"
            target[key] = StoredMemory(
                provider_id=provider_id,
                memory_key=key,
                content=content,
                metadata={"memory_key": key, "layer": "L1"},
            )
        return {
            "code": 0,
            "message": "ok",
            "data": {"accepted": len(payload.messages), "session_id": payload.session_id},
        }

    @app.post("/tencentdb/v3/atomic/search")
    async def tencent_atomic_search(payload: TencentAtomicSearch) -> dict[str, object]:
        await asyncio.sleep(0.011)
        namespace = f"{payload.team_id}:{payload.agent_id}:{payload.user_id}"
        ranked = _rank(
            list(tencent_records.get(namespace, {}).values()),
            payload.query,
            payload.limit,
        )
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "items": [
                    {
                        "id": record.provider_id,
                        "type": "approved-memory",
                        "content": record.content,
                        "metadata": record.metadata,
                        "score": score,
                    }
                    for record, score in ranked
                ]
            },
        }

    @app.get("/mem0/health")
    async def mem0_health() -> dict[str, str]:
        return {"status": "ok", "storage": "in-memory-contract-sandbox"}

    @app.post("/mem0/memories")
    async def mem0_add(payload: Mem0Create) -> dict[str, object]:
        await asyncio.sleep(0.012)
        metadata = dict(payload.metadata or {})
        target = mem0_records.setdefault(payload.user_id, {})
        results: list[dict[str, object]] = []
        for message in payload.messages:
            key_value = metadata.get("memory_key")
            key, content = _memory_key(message.content)
            if isinstance(key_value, str) and key_value:
                key = key_value
            digest = hashlib.sha256((payload.user_id + key).encode()).hexdigest()[:20]
            provider_id = f"mem0-{digest}"
            item_metadata = {**metadata, "memory_key": key}
            target[key] = StoredMemory(provider_id, key, content, item_metadata)
            results.append({"id": provider_id, "memory": content, "event": "ADD"})
        return {"results": results}

    @app.post("/mem0/search")
    async def mem0_search(payload: Mem0Search) -> dict[str, object]:
        await asyncio.sleep(0.017)
        user_value = payload.filters.get("user_id")
        user_id = user_value if isinstance(user_value, str) else ""
        ranked = _rank(list(mem0_records.get(user_id, {}).values()), payload.query, payload.top_k)
        return {
            "results": [
                {
                    "id": record.provider_id,
                    "memory": record.content,
                    "score": score,
                    "metadata": record.metadata,
                }
                for record, score in ranked
            ]
        }

    return app


app = create_app()
