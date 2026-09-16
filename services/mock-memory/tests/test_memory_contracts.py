import pytest
from httpx import ASGITransport, AsyncClient

from mock_memory.main import create_app


@pytest.mark.anyio
async def test_tencentdb_v3_contract_indexes_and_searches_isolated_memory() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        added = await client.post(
            "/tencentdb/v3/conversation/add",
            json={
                "team_id": "ent-demo",
                "agent_id": "twin-ceo",
                "user_id": "run-1",
                "session_id": "eval-1",
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            '<zhixing-memory key="ceo-conclusion-first">'
                            "管理讨论先给结论，再给证据、责任人和期限。"
                            "</zhixing-memory>"
                        ),
                    }
                ],
            },
        )
        searched = await client.post(
            "/tencentdb/v3/atomic/search",
            json={
                "team_id": "ent-demo",
                "agent_id": "twin-ceo",
                "user_id": "run-1",
                "query": "管理汇报的结论和证据如何组织？",
                "limit": 3,
            },
        )

    assert added.status_code == 200
    assert added.json()["code"] == 0
    items = searched.json()["data"]["items"]
    assert items[0]["metadata"]["memory_key"] == "ceo-conclusion-first"
    assert items[0]["score"] > 0


@pytest.mark.anyio
async def test_mem0_contract_indexes_and_searches_by_user_filter() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        added = await client.post(
            "/mem0/memories",
            json={
                "messages": [{"role": "user", "content": "财务评审必须设置停止条件。"}],
                "user_id": "eval-run-2",
                "agent_id": "zhixing-evaluation",
                "metadata": {"memory_key": "finance-stop-condition"},
                "infer": False,
            },
        )
        searched = await client.post(
            "/mem0/search",
            json={
                "query": "财务审批关注哪些停止条件？",
                "filters": {"user_id": "eval-run-2"},
                "top_k": 3,
            },
        )

    assert added.status_code == 200
    assert added.json()["results"][0]["event"] == "ADD"
    assert searched.json()["results"][0]["metadata"]["memory_key"] == (
        "finance-stop-condition"
    )
