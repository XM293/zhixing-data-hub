import pytest
from httpx import ASGITransport, AsyncClient

from zhixing_api.main import create_app


@pytest.mark.anyio
async def test_platform_module_registry_matches_product_navigation() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/platform/modules")

    assert response.status_code == 200
    payload = response.json()
    modules = payload["modules"]
    keys = [item["key"] for item in modules]
    navigation = {item["navigation"] for item in modules}

    assert payload["schema_version"] == 1
    assert len(keys) == len(set(keys))
    assert navigation == {
        "企业数据中心",
        "企业知识中心",
        "角色分身中心",
        "数字会议中心",
        "智能分析中心",
        "行动与执行中心",
        "平台管理",
    }
    assert {item["availability"] for item in modules} == {"foundation", "planned"}
