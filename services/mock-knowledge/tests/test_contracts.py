import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_weknora_contract_scopes_search_to_knowledge_ids(client: AsyncClient) -> None:
    first = await client.post(
        "/weknora/api/v1/knowledge-bases/test/knowledge/manual",
        json={
            "title": "预算",
            "content": "[zhixing-chunk:budget-a]\n五万元以上需要财务审批。",
        },
    )
    second = await client.post(
        "/weknora/api/v1/knowledge-bases/test/knowledge/manual",
        json={
            "title": "服务",
            "content": "[zhixing-chunk:service-a]\n高风险会话必须转人工。",
        },
    )
    first_id = first.json()["data"]["id"]
    response = await client.post(
        "/weknora/api/v1/knowledge-search",
        json={"query": "转人工", "knowledge_ids": [first_id]},
    )
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert second.json()["data"]["id"] != first_id


@pytest.mark.anyio
async def test_ragflow_contract_indexes_chunks_and_retrieves(client: AsyncClient) -> None:
    document = await client.post(
        "/ragflow/api/v1/datasets/test/documents?type=empty",
        json={"name": "service.md"},
    )
    document_id = document.json()["data"][0]["id"]
    chunk = await client.post(
        f"/ragflow/api/v1/datasets/test/documents/{document_id}/chunks",
        json={"content": "[zhixing-chunk:service-a]\n高风险会话必须转人工。"},
    )
    assert chunk.json()["code"] == 0
    response = await client.post(
        "/ragflow/api/v1/retrieval",
        json={"question": "哪些会话转人工", "document_ids": [document_id], "top_k": 3},
    )
    assert response.status_code == 200
    assert response.json()["data"]["chunks"][0]["id"] == chunk.json()["data"]["id"]


@pytest.mark.anyio
async def test_openviking_contract_scopes_hierarchical_resource_search(
    client: AsyncClient,
) -> None:
    first_root = "viking://resources/zhixing-evaluations/run-a"
    second_root = "viking://resources/zhixing-evaluations/run-b"
    first_uri = f"{first_root}/document-budget/chunk-budget-a.md"
    second_uri = f"{second_root}/document-service/chunk-service-a.md"
    for root, uri, content in (
        (first_root, first_uri, "[zhixing-chunk:budget-a]\n五万元以上需要财务审批。"),
        (second_root, second_uri, "[zhixing-chunk:service-a]\n高风险会话必须转人工。"),
    ):
        response = await client.post(
            "/openviking/api/v1/content/batch-write",
            json={
                "root_uri": root,
                "operations": [{"uri": uri, "content": content, "mode": "replace"}],
                "wait": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    scoped = await client.post(
        "/openviking/api/v1/search/find",
        json={
            "query": "哪些会话转人工",
            "target_uri": [first_root],
            "context_type": "resource",
            "limit": 3,
            "level": [2],
        },
    )
    assert scoped.status_code == 200
    assert scoped.json()["result"]["resources"] == []

    matched = await client.post(
        "/openviking/api/v1/search/find",
        json={
            "query": "哪些会话转人工",
            "target_uri": [second_root],
            "context_type": "resource",
            "limit": 3,
            "level": [2],
        },
    )
    assert matched.json()["result"]["resources"][0]["uri"] == second_uri
