import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT / "src"))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
