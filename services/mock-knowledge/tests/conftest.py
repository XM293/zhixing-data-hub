import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mock_knowledge.main import create_app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as value:
        yield value
