from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

import httpx

from zhixing_api.config import Settings

_CHUNK_MARKER = re.compile(r"\[zhixing-chunk:([^\]]+)]")


class KnowledgeProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderKnowledgeChunk:
    chunk_key: str
    heading: str
    content: str
    locator: str


@dataclass(frozen=True, slots=True)
class ProviderKnowledgeDocument:
    document_key: str
    title: str
    version_label: str
    chunks: list[ProviderKnowledgeChunk]


@dataclass(frozen=True, slots=True)
class ProviderKnowledgeIndex:
    document_count: int
    chunk_count: int
    scope_ids: list[str]


@dataclass(frozen=True, slots=True)
class ProviderKnowledgeHit:
    provider_id: str
    chunk_key: str | None
    content: str
    score: float


class KnowledgeProvider(Protocol):
    key: str
    label: str
    protocol: str
    mode: str
    endpoint_fingerprint: str
    authentication_configured: bool

    async def health(self) -> None: ...

    async def index_documents(
        self,
        namespace: str,
        documents: list[ProviderKnowledgeDocument],
    ) -> ProviderKnowledgeIndex: ...

    async def search(
        self,
        index: ProviderKnowledgeIndex,
        query: str,
        *,
        top_k: int,
    ) -> list[ProviderKnowledgeHit]: ...


class _HTTPKnowledgeProvider:
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


class WeKnoraKnowledgeProvider(_HTTPKnowledgeProvider):
    key = "weknora"
    label = "WeKnora"
    protocol = "knowledge-search-v1"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        knowledge_base_id: str,
        mode: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            mode=mode,
            timeout_seconds=timeout_seconds,
        )
        self.knowledge_base_id = knowledge_base_id

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def health(self) -> None:
        async with self._client() as client:
            response = await client.get("/health")
            response.raise_for_status()

    async def index_documents(
        self,
        namespace: str,
        documents: list[ProviderKnowledgeDocument],
    ) -> ProviderKnowledgeIndex:
        scope_ids: list[str] = []
        async with self._client() as client:
            for document in documents:
                response = await client.post(
                    f"/api/v1/knowledge-bases/{self.knowledge_base_id}/knowledge/manual",
                    json={
                        "title": f"{namespace} · {document.title} · {document.version_label}",
                        "content": _document_content(document),
                        "status": "published",
                        "channel": "api",
                    },
                )
                response.raise_for_status()
                payload = _dict_payload(response)
                if payload.get("success") is not True:
                    raise KnowledgeProviderError("WeKnora 拒绝创建评测知识")
                identifier = _string(_dict_value(payload.get("data")).get("id"))
                if not identifier:
                    raise KnowledgeProviderError("WeKnora 未返回评测知识 ID")
                scope_ids.append(identifier)
        return ProviderKnowledgeIndex(
            document_count=len(documents),
            chunk_count=sum(len(item.chunks) for item in documents),
            scope_ids=scope_ids,
        )

    async def search(
        self,
        index: ProviderKnowledgeIndex,
        query: str,
        *,
        top_k: int,
    ) -> list[ProviderKnowledgeHit]:
        async with self._client() as client:
            response = await client.post(
                "/api/v1/knowledge-search",
                json={
                    "query": query,
                    "knowledge_ids": index.scope_ids,
                },
            )
            response.raise_for_status()
            payload = _dict_payload(response)
        if payload.get("success") is not True:
            raise KnowledgeProviderError("WeKnora 检索请求失败")
        return [_weknora_hit(item) for item in _dict_list(payload.get("data"))[:top_k]]


class RAGFlowKnowledgeProvider(_HTTPKnowledgeProvider):
    key = "ragflow"
    label = "RAGFlow"
    protocol = "retrieval-api-v1"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        dataset_id: str,
        mode: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            mode=mode,
            timeout_seconds=timeout_seconds,
        )
        self.dataset_id = dataset_id

    async def health(self) -> None:
        async with self._client() as client:
            response = await client.get("/api/v1/system/healthz")
            response.raise_for_status()

    async def index_documents(
        self,
        namespace: str,
        documents: list[ProviderKnowledgeDocument],
    ) -> ProviderKnowledgeIndex:
        scope_ids: list[str] = []
        async with self._client() as client:
            for document in documents:
                response = await client.post(
                    f"/api/v1/datasets/{self.dataset_id}/documents",
                    params={"type": "empty"},
                    json={
                        "name": (
                            f"{namespace}-{document.document_key}-"
                            f"{document.version_label}.md"
                        )
                    },
                )
                response.raise_for_status()
                payload = _dict_payload(response)
                if payload.get("code") != 0:
                    raise KnowledgeProviderError("RAGFlow 拒绝创建评测文档")
                rows = _dict_list(payload.get("data"))
                document_id = _string(rows[0].get("id")) if rows else ""
                if not document_id:
                    raise KnowledgeProviderError("RAGFlow 未返回评测文档 ID")
                scope_ids.append(document_id)
                for chunk in document.chunks:
                    chunk_response = await client.post(
                        f"/api/v1/datasets/{self.dataset_id}/documents/{document_id}/chunks",
                        json={
                            "content": _chunk_content(chunk),
                            "important_keywords": [chunk.heading, document.title],
                            "tag_kwd": [document.document_key, document.version_label],
                        },
                    )
                    chunk_response.raise_for_status()
                    chunk_payload = _dict_payload(chunk_response)
                    if chunk_payload.get("code") != 0:
                        raise KnowledgeProviderError("RAGFlow 拒绝写入评测切片")
        return ProviderKnowledgeIndex(
            document_count=len(documents),
            chunk_count=sum(len(item.chunks) for item in documents),
            scope_ids=scope_ids,
        )

    async def search(
        self,
        index: ProviderKnowledgeIndex,
        query: str,
        *,
        top_k: int,
    ) -> list[ProviderKnowledgeHit]:
        async with self._client() as client:
            response = await client.post(
                "/api/v1/retrieval",
                json={
                    "question": query,
                    "document_ids": index.scope_ids,
                    "page": 1,
                    "page_size": top_k,
                    "top_k": max(32, top_k),
                    "similarity_threshold": 0.0,
                    "keyword": True,
                },
            )
            response.raise_for_status()
            payload = _dict_payload(response)
        if payload.get("code") != 0:
            raise KnowledgeProviderError("RAGFlow 检索请求失败")
        data = _dict_value(payload.get("data"))
        return [_ragflow_hit(item) for item in _dict_list(data.get("chunks"))[:top_k]]


class OpenVikingContextProvider(_HTTPKnowledgeProvider):
    key = "openviking"
    label = "OpenViking"
    protocol = "context-resource-search-v1"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        account: str,
        user: str,
        mode: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            mode=mode,
            timeout_seconds=timeout_seconds,
        )
        self.account = account
        self.user = user

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        if self.account:
            headers["X-OpenViking-Account"] = self.account
        if self.user:
            headers["X-OpenViking-User"] = self.user
        return headers

    async def health(self) -> None:
        async with self._client() as client:
            response = await client.get("/health")
            response.raise_for_status()
            payload = _dict_payload(response)
        if payload.get("status") != "ok":
            raise KnowledgeProviderError("OpenViking 健康检查未就绪")

    async def index_documents(
        self,
        namespace: str,
        documents: list[ProviderKnowledgeDocument],
    ) -> ProviderKnowledgeIndex:
        root_uri = (
            "viking://resources/zhixing-evaluations/"
            f"{sha256(namespace.encode('utf-8')).hexdigest()[:20]}"
        )
        operations = [
            {
                "uri": (
                    f"{root_uri}/document-{_uri_token(document.document_key)}/"
                    f"chunk-{_uri_token(chunk.chunk_key)}.md"
                ),
                "content": (
                    f"# {document.title} · {document.version_label}\n\n"
                    f"## {chunk.heading}\n{_chunk_content(chunk)}"
                ),
                "mode": "replace",
            }
            for document in documents
            for chunk in document.chunks
        ]
        async with self._client() as client:
            response = await client.post(
                "/api/v1/content/batch-write",
                json={
                    "root_uri": root_uri,
                    "operations": operations,
                    "wait": True,
                    "timeout": self.timeout_seconds,
                    "telemetry": False,
                },
            )
            response.raise_for_status()
            payload = _dict_payload(response)
        if payload.get("status") != "ok":
            raise KnowledgeProviderError("OpenViking 拒绝写入评测上下文")
        return ProviderKnowledgeIndex(
            document_count=len(documents),
            chunk_count=sum(len(item.chunks) for item in documents),
            scope_ids=[root_uri],
        )

    async def search(
        self,
        index: ProviderKnowledgeIndex,
        query: str,
        *,
        top_k: int,
    ) -> list[ProviderKnowledgeHit]:
        async with self._client() as client:
            response = await client.post(
                "/api/v1/search/find",
                json={
                    "query": query,
                    "target_uri": index.scope_ids,
                    "context_type": "resource",
                    "limit": top_k,
                    "level": [2],
                    "include_provenance": False,
                    "telemetry": False,
                },
            )
            response.raise_for_status()
            payload = _dict_payload(response)
        if payload.get("status") != "ok":
            raise KnowledgeProviderError("OpenViking 层次检索请求失败")
        result = _dict_value(payload.get("result"))
        return [_openviking_hit(item) for item in _dict_list(result.get("resources"))[:top_k]]


def build_knowledge_providers(settings: Settings) -> dict[str, KnowledgeProvider]:
    providers: list[KnowledgeProvider] = [
        WeKnoraKnowledgeProvider(
            base_url=settings.weknora_base_url,
            api_key=settings.weknora_api_key,
            knowledge_base_id=settings.weknora_knowledge_base_id,
            mode=settings.knowledge_provider_mode,
            timeout_seconds=settings.knowledge_provider_timeout_seconds,
        ),
        RAGFlowKnowledgeProvider(
            base_url=settings.ragflow_base_url,
            api_key=settings.ragflow_api_key,
            dataset_id=settings.ragflow_dataset_id,
            mode=settings.knowledge_provider_mode,
            timeout_seconds=settings.knowledge_provider_timeout_seconds,
        ),
        OpenVikingContextProvider(
            base_url=settings.openviking_base_url,
            api_key=settings.openviking_api_key,
            account=settings.openviking_account,
            user=settings.openviking_user,
            mode=settings.knowledge_provider_mode,
            timeout_seconds=settings.knowledge_provider_timeout_seconds,
        ),
    ]
    return {provider.key: provider for provider in providers}


def _document_content(document: ProviderKnowledgeDocument) -> str:
    return "\n\n".join(
        f"## {chunk.heading}\n{_chunk_content(chunk)}" for chunk in document.chunks
    )


def _chunk_content(chunk: ProviderKnowledgeChunk) -> str:
    return f"[zhixing-chunk:{chunk.chunk_key}]\n{chunk.content}"


def _uri_token(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _uri_chunk_key(uri: str) -> str | None:
    match = re.search(r"/chunk-([A-Za-z0-9_-]+)\.md$", uri)
    if match is None:
        return None
    token = match.group(1)
    try:
        return base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None


def _dict_payload(response: httpx.Response) -> dict[str, object]:
    payload: object = response.json()
    if not isinstance(payload, dict):
        raise KnowledgeProviderError("知识 Provider 返回了非对象响应")
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


def _chunk_key(content: str, metadata: dict[str, object]) -> str | None:
    metadata_key = _string(metadata.get("chunk_key"))
    if metadata_key:
        return metadata_key
    match = _CHUNK_MARKER.search(content)
    return match.group(1) if match else None


def _weknora_hit(item: dict[str, object]) -> ProviderKnowledgeHit:
    content = _string(item.get("content"))
    return ProviderKnowledgeHit(
        provider_id=_string(item.get("id")),
        chunk_key=_chunk_key(content, _dict_value(item.get("metadata"))),
        content=content,
        score=_number(item.get("score")),
    )


def _ragflow_hit(item: dict[str, object]) -> ProviderKnowledgeHit:
    content = _string(item.get("content"))
    return ProviderKnowledgeHit(
        provider_id=_string(item.get("id")),
        chunk_key=_chunk_key(content, item),
        content=content,
        score=_number(item.get("similarity")),
    )


def _openviking_hit(item: dict[str, object]) -> ProviderKnowledgeHit:
    uri = _string(item.get("uri"))
    content = _string(item.get("abstract"))
    return ProviderKnowledgeHit(
        provider_id=uri,
        chunk_key=_uri_chunk_key(uri) or _chunk_key(content, item),
        content=content,
        score=_number(item.get("score")),
    )
