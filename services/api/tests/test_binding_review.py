from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from zhixing_api.data_models import (
    BusinessEntity,
    BusinessUnit,
    CanonicalEntityOrigin,
    Enterprise,
    ExternalSystem,
    PlatformEvent,
    SourceBinding,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.bindings import review_binding


def test_assignment_review_validates_target_and_updates_visibility_atomically(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'binding_verify.db'}")
    database.migrate()
    now = datetime.now(UTC)
    with database.session() as session:
        for enterprise in ("a", "b"):
            session.add(Enterprise(id=enterprise, code=enterprise, name=enterprise,
                                   timezone="UTC", created_at=now))
        session.flush()
        for unit, enterprise in (("a1", "a"), ("b1", "b")):
            session.add(BusinessUnit(id=unit, enterprise_id=enterprise, unit_key=unit,
                        name=unit, unit_type="project", status="active", created_at=now,
                        updated_at=now))
        session.add(ExternalSystem(id="source", enterprise_id="a", system_key="erp", name="ERP",
                    system_type="lingxing", base_url="https://openapi.lingxing.com",
                    status="configured"))
        session.add(BusinessEntity(id="store", enterprise_id="a", canonical_key="store",
                    entity_type="store", display_name="Synthetic Store", status="unassigned",
                    attributes={}, updated_at=now))
        session.flush()
        session.add(SourceBinding(id="binding", enterprise_id="a", source_system_id="source",
                    external_key="store:1", canonical_type="store", canonical_id="store",
                    mapping_version="2.0.0", status="pending", created_at=now, updated_at=now))
        session.commit()
    try:
        with pytest.raises(ApiProblem) as error:
            review_binding(database, enterprise_id="a", source_key="erp", binding_id="binding",
                           principal_id="reviewer", status="approved", business_unit_id="b1")
        assert error.value.code == "source.binding_scope_invalid"
        with database.session() as session:
            assert session.get(SourceBinding, "binding").status == "pending"
        binding = review_binding(database, enterprise_id="a", source_key="erp",
                                 binding_id="binding",
                                 principal_id="reviewer", status="approved", business_unit_id="a1",
                                 store_timezone="Asia/Tokyo")
        assert binding.business_unit_id == "a1" and binding.status == "approved"
        with database.session() as session:
            entity = session.get(BusinessEntity, "store")
            assert entity.status == "active" and entity.attributes["timezone"] == "Asia/Tokyo"
            assert session.scalar(select(PlatformEvent)).event_type == "source.binding.reviewed"
            assert session.scalar(select(CanonicalEntityOrigin)) is None
        with pytest.raises(ApiProblem):
            review_binding(database, enterprise_id="b", source_key="erp", binding_id="binding",
                           principal_id="reviewer", status="approved", business_unit_id="b1")
    finally:
        database.dispose()
