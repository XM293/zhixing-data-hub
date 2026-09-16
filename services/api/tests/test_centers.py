from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from zhixing_api.config import Settings
from zhixing_api.data_models import Enterprise, EnterpriseMembership, Principal
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'centers_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


@pytest.mark.anyio
async def test_center_catalog_projects_business_boundaries_by_permission(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ceo = await client.get("/api/v1/centers/me", headers={"X-Zhixing-Demo-Actor": "ceo"})
        employee = await client.get(
            "/api/v1/centers/me", headers={"X-Zhixing-Demo-Actor": "employee"}
        )
        admin = await client.get(
            "/api/v1/centers/me", headers={"X-Zhixing-Demo-Actor": "admin"}
        )
        context = await client.get("/api/v1/context", headers={"X-Zhixing-Demo-Actor": "ceo"})

    assert ceo.status_code == 200, ceo.text
    payload = ceo.json()
    group_keys = [group["key"] for group in payload["groups"]]
    assert group_keys == [
        "experience",
        "insights",
        "data",
        "business",
        "governance",
        "ai",
    ]
    centers = {
        center["key"]: center
        for group in payload["groups"]
        for center in group["items"]
    }
    assert centers["data-foundation"]["scope_level"] == "enterprise"
    assert centers["data-products"]["scope_level"] == "enterprise"
    assert centers["digital-twin"]["href"] == "/console/spatial"
    assert centers["data-sync-jobs"]["href"] == "/console/data/foundation/sync-jobs"
    assert centers["data-customers"]["href"] == "/console/data/products/customers"
    assert "fulfillment" not in centers
    assert "integrations" not in centers
    assert "organization" not in centers
    assert "platform" not in centers

    for center in centers.values():
        if center["key"] == "workspaces":
            continue
        assert not center["href"].startswith("/console/workspaces/")

    data_group = next(group for group in payload["groups"] if group["key"] == "data")
    data_hrefs = {center["href"] for center in data_group["items"]}
    assert all(
        href.startswith(("/console/data/foundation/", "/console/data/products/"))
        for href in data_hrefs
    )
    business_group = next(group for group in payload["groups"] if group["key"] == "business")
    business_hrefs = {center["href"] for center in business_group["items"]}
    assert "/console/commerce/stores" in business_hrefs

    assert employee.status_code == 200, employee.text
    employee_centers = {
        center["key"]
        for group in employee.json()["groups"]
        for center in group["items"]
    }
    assert "digital-twin" in employee_centers
    assert "data-foundation" not in employee_centers
    assert "knowledge" in employee_centers

    admin_centers = {
        center["key"]
        for group in admin.json()["groups"]
        for center in group["items"]
    }
    assert "platform" in admin_centers
    assert "platform-org" in admin_centers

    assert context.status_code == 200, context.text
    context_payload = context.json()
    assert context_payload["group_id"] == "grp_ent_zhixing_demo"
    assert context_payload["enterprise_id"] == "ent_zhixing_demo"
    assert context_payload["allowed_enterprise_ids"] == ["ent_zhixing_demo"]


@pytest.mark.anyio
async def test_context_switch_requires_membership_and_reprojects_session(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    now = datetime.now(UTC)
    with app.state.database.session() as session:
        principal = session.scalar(
            select(Principal).where(Principal.principal_key == "principal-ceo-lin")
        )
        assert principal is not None
        session.add(
            Enterprise(
                id="ent_zhixing_sub",
                code="ZHIXING-SUB",
                name="知行子公司",
                timezone="Asia/Shanghai",
                group_id="grp_ent_zhixing_demo",
                created_at=now,
            )
        )
        session.add(
            EnterpriseMembership(
                id="enterprise_membership_ceo_sub",
                principal_id=principal.id,
                enterprise_id="ent_zhixing_sub",
                membership_type="director",
                is_primary=False,
                status="active",
                valid_from=now,
                valid_to=None,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        session_response = await client.post(
            "/api/v1/auth/development/session",
            json={"login_name": "ceo"},
        )
        denied = await client.post(
            "/api/v1/context/switch",
            json={"enterprise_id": "ent_other"},
        )
        switched = await client.post(
            "/api/v1/context/switch",
            json={"enterprise_id": "ent_zhixing_sub"},
        )

    assert session_response.status_code == 200, session_response.text
    assert switched.status_code == 200, switched.text
    assert switched.json()["context"]["enterprise_id"] == "ent_zhixing_sub"
    assert switched.json()["identity"]["enterprise_id"] == "ent_zhixing_sub"
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "auth.enterprise_membership_required"
