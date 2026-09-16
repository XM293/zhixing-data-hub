import asyncio

from zhixing_worker.lingxing_sync import execute_pages


def test_checkpoint_resume_and_page_persistence():
    calls = []

    async def fetch(page):
        calls.append(page)
        return {"data": {"items": [page], "has_more": page < 3}}

    async def persist(payload):
        return len(payload["data"]["items"])

    result = asyncio.run(execute_pages(fetch, persist, checkpoint=1))
    assert result.records == 2 and result.checkpoint == 3 and calls == [2, 3]
