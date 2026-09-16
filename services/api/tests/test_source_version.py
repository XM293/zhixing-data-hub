import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from zhixing_api.data_center_schemas import SourceUpdateRequest


def test_source_edits_require_an_explicit_configuration_version():
    with pytest.raises(ValidationError):
        SourceUpdateRequest(name="Synthetic")


def test_source_revision_prevents_stale_edit_and_disable(monkeypatch):
    from zhixing_api.data_models import Base, ExternalSystem
    from zhixing_api.database import Database
    from zhixing_api.errors import ApiProblem
    from zhixing_api.routers import data_center

    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)
    with database.session() as session:
        session.add(ExternalSystem(id="source", enterprise_id="a", system_key="synthetic",
            name="Synthetic initial", system_type="lingxing", provider_key="lingxing",
            base_url="https://openapi.lingxing.com", status="configured"))
        session.commit()
    monkeypatch.setattr(data_center, "_authorize", lambda *args, **kwargs:
                        SimpleNamespace(enterprise_id="a", principal_id="synthetic"))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=database)))

    async def run():
        edited = await data_center.update_source(request, "synthetic",
            SourceUpdateRequest(name="Synthetic revised", expected_version=1))
        assert edited.version == 2
        for values in ({"name": "Stale name"}, {"status": "disabled"}):
            with pytest.raises(ApiProblem) as error:
                await data_center.update_source(request, "synthetic",
                    SourceUpdateRequest(**values, expected_version=1))
            assert error.value.status_code == 409 and error.value.code == "source.version_conflict"
        disabled = await data_center.update_source(request, "synthetic",
            SourceUpdateRequest(status="disabled", expected_version=2))
        assert disabled.version == 3 and disabled.name == "Synthetic revised"
        assert disabled.status == "disabled"

    asyncio.run(run())
    database.dispose()
