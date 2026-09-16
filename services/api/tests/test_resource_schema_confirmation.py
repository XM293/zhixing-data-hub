import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from zhixing_connectors.catalog import CATALOG_VERSION, resource_spec

from zhixing_api.data_center_schemas import SourceResourceUpdateRequest
from zhixing_api.data_models import Base, ExternalSystem, PlatformEvent, SourceResource
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.routers import data_center


def test_schema_confirmation_is_explicit_versioned_and_catalog_gated(monkeypatch):
    catalog_spec = resource_spec("warehouse_bins")
    assert catalog_spec is not None and catalog_spec.schema_status == "confirmed"
    db = Database("sqlite://")
    Base.metadata.create_all(db.engine)
    with db.session() as session:
        session.add(ExternalSystem(id="src", enterprise_id="legal", system_key="erp",
            name="Synthetic", system_type="lingxing", status="configured",
            base_url="https://openapi.lingxing.com"))
        session.flush()
        for key in ("shops", "warehouse_bins"):
            session.add(SourceResource(id=key, external_system_id="src", resource_key=key,
                method="GET", path="/synthetic", schema_status="schema_pending", enabled=True))
        session.commit()
    monkeypatch.setattr(data_center, "_authorize", lambda *a, **k:
                        SimpleNamespace(enterprise_id="legal", principal_id="reviewer"))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=db,
                              settings=SimpleNamespace(lingxing_enabled=True))))
    async def run():
        row = await data_center.update_source_resource(request, "erp", "shops",
            SourceResourceUpdateRequest(enabled=True))
        assert row.schema_status == "schema_pending"
        assert row.schema_confirmation_available
        for resource, version in (("shops", "stale"), ("warehouse_bins", CATALOG_VERSION)):
            if resource == "warehouse_bins":
                pending = await data_center.update_source_resource(
                    request, "erp", resource, SourceResourceUpdateRequest(enabled=True))
                assert pending.schema_status == "schema_pending"
                row = await data_center.update_source_resource(request, "erp", resource,
                    SourceResourceUpdateRequest(enabled=True, confirm_catalog_version=version))
                assert row.schema_status == "confirmed"
                continue
            with pytest.raises(ApiProblem) as error:
                await data_center.update_source_resource(request, "erp", resource,
                    SourceResourceUpdateRequest(enabled=True, confirm_catalog_version=version))
            assert error.value.status_code == 409
        for _ in range(2):
            row = await data_center.update_source_resource(request, "erp", "shops",
                SourceResourceUpdateRequest(enabled=True, confirm_catalog_version=CATALOG_VERSION))
            assert row.schema_status == "confirmed"
            assert not row.schema_confirmation_available
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(PlatformEvent)) == 2
            session.delete(session.get(SourceResource, "shops"))
            session.commit()
        row = await data_center.update_source_resource(request, "erp", "shops",
            SourceResourceUpdateRequest(enabled=True))
        assert row.schema_status == "schema_pending" and row.schema_confirmation_available
        row = await data_center.update_source_resource(request, "erp", "shops",
            SourceResourceUpdateRequest(enabled=True, confirm_catalog_version=CATALOG_VERSION))
        assert row.schema_status == "confirmed"
        with db.session() as session:
                assert session.scalar(select(func.count()).select_from(PlatformEvent)) == 3
    asyncio.run(run())
    db.dispose()
