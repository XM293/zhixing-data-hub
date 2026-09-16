from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from zhixing_api.data_models import Base, ExternalSystem, MappingConflict
from zhixing_api.errors import ApiProblem
from zhixing_api.ingestion.conflicts import mark_resolved, review_conflict
from zhixing_api.ingestion.persistence import _conflict, _object_key, stable_key


def test_conflict_keys_do_not_resolve_unrelated_objects_or_pages():
    assert _object_key({"providerId": "a"}, 0, "raw-a") != _object_key(
        {"providerId": "b"}, 0, "raw-a")
    assert _object_key({}, 0, "raw-a") != _object_key({}, 0, "raw-b")
    stock = {"wid": 1, "product_id": 2, "seller_id": 3, "fnsku": "a"}
    assert _object_key(stock, 0, "raw-a") != _object_key({**stock, "fnsku": "b"}, 0, "raw-a")


def test_conflict_approval_requires_verified_mapping_and_is_source_scoped():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        source = ExternalSystem(id="source", enterprise_id="legal", system_key="synthetic",
            name="Synthetic", system_type="lingxing", base_url="https://example.invalid")
        session.add(source)
        conflict = MappingConflict(
            id=stable_key("source", "orders", "order:1", "mapping.unassigned"),
            enterprise_id="legal",
            external_system_id="source", resource_key="orders", external_object_key="order:1",
            candidates=[], status="pending", resolution={"error_code": "mapping.unassigned"})
        session.add(conflict)
        session.commit()
        with pytest.raises(ApiProblem) as pending:
            review_conflict(session, conflict, status="approved", principal_id="admin")
        assert pending.value.code == "mapping_conflict.unresolved"
        mark_resolved(session, source, "orders", "other", "raw-other")
        assert "resolved_manifest_id" not in conflict.resolution
        mark_resolved(session, source, "orders", "order:1", "raw-fixed")
        review_conflict(session, conflict, status="approved", principal_id="admin")
        assert conflict.status == "approved" and conflict.reviewed_by == "admin"
        assert conflict.reviewed_at <= datetime.now(UTC)
        assert conflict.resolution["resolved_manifest_id"] == "raw-fixed"
        _conflict(session, source, "orders", "order:1", "raw-new-failure", "mapping.unassigned")
        assert conflict.status == "pending"
        assert "resolved_manifest_id" not in conflict.resolution
        assert conflict.reviewed_by == "admin"
    engine.dispose()
