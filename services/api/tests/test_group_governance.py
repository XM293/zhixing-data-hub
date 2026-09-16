from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine

from zhixing_api.actor_context import ActorContext, ActorScope
from zhixing_api.data_models import Base, BusinessUnit, Enterprise, EnterpriseGroup, Principal
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.governance_schemas import BusinessUnitRequest
from zhixing_api.governance_service import governance_overview, save_business_unit


def test_governance_rejects_cross_legal_parent_cycles_and_stale_version():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    database = Database.from_engine(engine)
    now = datetime.now(UTC)
    with database.session() as session:
        session.add(EnterpriseGroup(id="g", code="g", name="Synthetic", timezone="UTC",
                    status="active", created_at=now, updated_at=now))
        for enterprise in ("a", "b"):
            session.add(Enterprise(id=enterprise, code=enterprise, name=enterprise,
                                   group_id="g", timezone="UTC", created_at=now))
        session.add(Principal(id="p", enterprise_id="a", principal_key="p", principal_type="person",
                    display_name="Synthetic", status="active", created_at=now, updated_at=now))
        session.add(BusinessUnit(id="b1", enterprise_id="b", unit_key="b1", name="b1",
                    unit_type="project", status="active", created_at=now, updated_at=now))
        session.commit()
    actor = ActorContext(enterprise_id="a", principal_id="p", actor_key="p", user_account_id="u",
            login_name="synthetic", display_name="Synthetic", role_id="admin",
            access_role_keys=("admin",), membership_ids=(),
            permissions=frozenset({"identity.user.manage"}), permission_set_version="v1",
            request_id="r", run_id="r", group_id="g",
            scopes=(ActorScope("enterprise", ("a",), "allow"),))
    request = BusinessUnitRequest(enterprise_id="a", unit_key="a1", name="Project A")
    unit = save_business_unit(database, actor, request)
    assert unit["version"] == 1 and unit["enterprise_id"] == "a"
    local_actor = replace(actor, scopes=(ActorScope("business_unit", (str(unit["id"]),), "allow"),))
    for operation in (
        lambda: governance_overview(database, local_actor),
        lambda: save_business_unit(database, local_actor,
            request.model_copy(update={"expected_version": 1}), unit_id=str(unit["id"])),
    ):
        with pytest.raises(ApiProblem) as denied:
            operation()
        assert denied.value.status_code == 403
    with pytest.raises(ApiProblem) as stale:
        save_business_unit(database, actor, request.model_copy(update={"expected_version": 2}),
                           unit_id=str(unit["id"]))
    assert stale.value.code == "governance.version_conflict"
    for parent in ("b1", str(unit["id"])):
        with pytest.raises(ApiProblem):
            save_business_unit(database, actor, request.model_copy(update={"parent_id": parent,
                               "expected_version": 1}), unit_id=str(unit["id"]))
    with pytest.raises(ApiProblem):
        save_business_unit(database, actor, request.model_copy(update={"enterprise_id": "b"}))
    database.dispose()
