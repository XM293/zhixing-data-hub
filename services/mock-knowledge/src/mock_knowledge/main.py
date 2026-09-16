from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from mock_knowledge import __version__

_MARKER = re.compile(r"\[zhixing-chunk:([^\]]+)]")
_TOKEN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", re.IGNORECASE)


class WeKnoraManualKnowledge(BaseModel):
    title: str
    content: str
    status: str = "published"
    channel: str = "api"


class WeKnoraSearch(BaseModel):
    query: str = Field(min_length=1)
    knowledge_ids: list[str] = Field(default_factory=list)


class RAGFlowDocument(BaseModel):
    name: str


class RAGFlowChunk(BaseModel):
    content: str
    important_keywords: list[str] = Field(default_factory=list)
    tag_kwd: list[str] = Field(default_factory=list)


class RAGFlowRetrieval(BaseModel):
    question: str = Field(min_length=1)
    document_ids: list[str] = Field(default_factory=list)
    page: int = 1
    page_size: int = Field(default=10, ge=1, le=100)
    top_k: int = Field(default=10, ge=1, le=100)
    similarity_threshold: float = 0.0
    keyword: bool = True


class OpenVikingBatchWriteOperation(BaseModel):
    uri: str
    content: str
    mode: str = "replace"


class OpenVikingBatchWrite(BaseModel):
    root_uri: str
    operations: list[OpenVikingBatchWriteOperation]
    wait: bool = True
    timeout: float | None = None
    telemetry: bool = False


class OpenVikingFind(BaseModel):
    query: str = Field(min_length=1)
    target_uri: str | list[str] = ""
    context_type: str | None = None
    limit: int = Field(default=10, ge=1, le=100)
    level: list[int] | None = None
    include_provenance: bool = False
    telemetry: bool = False


@dataclass(frozen=True, slots=True)
class StoredChunk:
    provider_id: str
    content: str
    metadata: dict[str, object]
    parent_id: str


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN.findall(value)}


def _score(query: str, content: str) -> float:
    query_tokens = _tokens(query)
    content_tokens = _tokens(content)
    if not query_tokens or not content_tokens:
        return 0.0
    return round(len(query_tokens & content_tokens) / len(query_tokens), 6)


def _id(prefix: str, *values: str) -> str:
    digest = hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def _rank(records: list[StoredChunk], query: str, limit: int) -> list[tuple[StoredChunk, float]]:
    ranked = [(item, _score(query, item.content)) for item in records]
    ranked.sort(key=lambda item: (-item[1], item[0].provider_id))
    return ranked[:limit]


def create_app() -> FastAPI:
    app = FastAPI(title="知行数枢知识 Provider 契约沙箱", version=__version__)
    weknora_knowledge: dict[str, list[StoredChunk]] = {}
    ragflow_documents: dict[str, list[StoredChunk]] = {}
    openviking_resources: dict[str, StoredChunk] = {}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"service": "mock-knowledge", "status": "ready", "version": __version__}

    @app.get("/weknora/health")
    async def weknora_health() -> dict[str, str]:
        return {"status": "ok", "storage": "in-memory-contract-sandbox"}

    @app.post("/weknora/api/v1/knowledge-bases/{knowledge_base_id}/knowledge/manual")
    async def weknora_manual(
        knowledge_base_id: str,
        payload: WeKnoraManualKnowledge,
    ) -> dict[str, object]:
        await asyncio.sleep(0.018)
        identifier = _id("wk", knowledge_base_id, payload.title, payload.content)
        chunks: list[StoredChunk] = []
        markers = list(_MARKER.finditer(payload.content))
        if markers:
            for index, marker in enumerate(markers):
                start = marker.start()
                end = (
                    markers[index + 1].start()
                    if index + 1 < len(markers)
                    else len(payload.content)
                )
                content = payload.content[start:end].strip()
                chunks.append(
                    StoredChunk(
                        provider_id=_id("wk-chunk", identifier, str(index)),
                        content=content,
                        metadata={"chunk_key": marker.group(1), "knowledge_id": identifier},
                        parent_id=identifier,
                    )
                )
        else:
            chunks.append(
                StoredChunk(
                    provider_id=_id("wk-chunk", identifier, "0"),
                    content=payload.content,
                    metadata={"knowledge_id": identifier},
                    parent_id=identifier,
                )
            )
        weknora_knowledge[identifier] = chunks
        return {
            "success": True,
            "data": {"id": identifier, "title": payload.title, "status": payload.status},
        }

    @app.post("/weknora/api/v1/knowledge-search")
    async def weknora_search(payload: WeKnoraSearch) -> dict[str, object]:
        await asyncio.sleep(0.022)
        records = [
            chunk
            for identifier, chunks in weknora_knowledge.items()
            if not payload.knowledge_ids or identifier in payload.knowledge_ids
            for chunk in chunks
        ]
        ranked = [
            (record, score)
            for record, score in _rank(records, payload.query, 50)
            if score > 0
        ]
        return {
            "success": True,
            "data": [
                {
                    "id": record.provider_id,
                    "content": record.content,
                    "score": score,
                    "metadata": record.metadata,
                }
                for record, score in ranked
            ],
        }

    @app.get("/ragflow/api/v1/system/healthz")
    async def ragflow_health() -> dict[str, object]:
        return {"code": 0, "data": {"status": "ok", "storage": "in-memory-contract-sandbox"}}

    @app.post("/ragflow/api/v1/datasets/{dataset_id}/documents")
    async def ragflow_document(
        dataset_id: str,
        payload: RAGFlowDocument,
        type: str = Query(default="empty"),
    ) -> dict[str, object]:
        await asyncio.sleep(0.016)
        identifier = _id("rf-doc", dataset_id, payload.name, type)
        ragflow_documents.setdefault(identifier, [])
        return {"code": 0, "data": [{"id": identifier, "name": payload.name}]}

    @app.post("/ragflow/api/v1/datasets/{dataset_id}/documents/{document_id}/chunks")
    async def ragflow_chunk(
        dataset_id: str,
        document_id: str,
        payload: RAGFlowChunk,
    ) -> dict[str, object]:
        await asyncio.sleep(0.012)
        if document_id not in ragflow_documents:
            return {"code": 404, "message": "document not found"}
        identifier = _id("rf-chunk", dataset_id, document_id, payload.content)
        metadata: dict[str, object] = {
            "document_id": document_id,
            "important_keywords": payload.important_keywords,
            "tag_kwd": payload.tag_kwd,
        }
        ragflow_documents[document_id].append(
            StoredChunk(identifier, payload.content, metadata, document_id)
        )
        return {"code": 0, "data": {"id": identifier, "document_id": document_id}}

    @app.post("/ragflow/api/v1/retrieval")
    async def ragflow_retrieval(payload: RAGFlowRetrieval) -> dict[str, object]:
        await asyncio.sleep(0.026)
        records = [
            chunk
            for document_id, chunks in ragflow_documents.items()
            if not payload.document_ids or document_id in payload.document_ids
            for chunk in chunks
        ]
        ranked = [
            (record, score)
            for record, score in _rank(records, payload.question, payload.top_k)
            if score >= payload.similarity_threshold and score > 0
        ]
        return {
            "code": 0,
            "data": {
                "chunks": [
                    {
                        "id": record.provider_id,
                        "content": record.content,
                        "similarity": score,
                        "document_id": record.parent_id,
                        "important_keywords": record.metadata.get("important_keywords", []),
                        "metadata": record.metadata,
                    }
                    for record, score in ranked[: payload.page_size]
                ],
                "total": len(ranked),
            },
        }

    @app.get("/openviking/health")
    async def openviking_health() -> dict[str, object]:
        return {
            "status": "ok",
            "healthy": True,
            "version": __version__,
            "storage": "in-memory-contract-sandbox",
        }

    @app.post("/openviking/api/v1/content/batch-write")
    async def openviking_batch_write(payload: OpenVikingBatchWrite) -> dict[str, object]:
        await asyncio.sleep(0.02)
        root = payload.root_uri.rstrip("/")
        for operation in payload.operations:
            if not operation.uri.startswith(f"{root}/"):
                raise HTTPException(status_code=422, detail="operation outside root_uri")
            openviking_resources[operation.uri] = StoredChunk(
                provider_id=operation.uri,
                content=operation.content,
                metadata={"level": 2, "context_type": "resource"},
                parent_id=root,
            )
        return {
            "status": "ok",
            "result": {
                "root_uri": root,
                "written": len(payload.operations),
                "waited": payload.wait,
            },
        }

    @app.post("/openviking/api/v1/search/find")
    async def openviking_find(payload: OpenVikingFind) -> dict[str, object]:
        await asyncio.sleep(0.024)
        targets = (
            payload.target_uri if isinstance(payload.target_uri, list) else [payload.target_uri]
        )
        roots = [value.rstrip("/") for value in targets if value]
        records = [
            item
            for uri, item in openviking_resources.items()
            if not roots or any(uri.startswith(f"{root}/") for root in roots)
        ]
        ranked = [
            (record, score)
            for record, score in _rank(records, payload.query, payload.limit)
            if score > 0
        ]
        return {
            "status": "ok",
            "result": {
                "memories": [],
                "resources": [
                    {
                        "context_type": "resource",
                        "uri": record.provider_id,
                        "level": 2,
                        "score": score,
                        "abstract": record.content,
                        "tags": [],
                    }
                    for record, score in ranked
                ],
                "skills": [],
                "total": len(ranked),
            },
        }

    return app


app = create_app()
