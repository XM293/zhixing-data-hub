from datetime import UTC, datetime

from sqlalchemy import create_engine

from zhixing_api.data_models import (
    AuthorizationDecision,
    Base,
    Enterprise,
    Principal,
    ToolDefinition,
    ToolInvocation,
)
from zhixing_api.database import Database
from zhixing_api.identity_service import identity_admin_overview
from zhixing_api.tool_service import tool_admin_overview


def test_legal_audit_resolves_group_actor_without_expanding_account_or_audit_scope():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    database = Database.from_engine(engine)
    now = datetime.now(UTC)
    with database.session() as session:
        for key in ("a", "b"):
            session.add(Enterprise(id=key, code=key, name=f"Synthetic legal {key}",
                                   timezone="UTC", created_at=now))
        session.add(Principal(id="group-admin", enterprise_id="a", principal_key="group-admin",
            principal_type="human", display_name="Synthetic group administrator", status="active",
            created_at=now, updated_at=now))
        session.flush()
        for key in ("a", "b"):
            session.add(ToolDefinition(id=f"tool-{key}", enterprise_id=key, tool_key="get_metric",
                display_name="Synthetic metric", description="Synthetic", risk_level="R0",
                permission_key="metric.query.execute", resource_type="metric",
                scope_resolver="scope_key", input_schema={}, output_schema={}, provider="builtin",
                version="1.0.0", timeout_seconds=30, status="active",
                created_at=now, updated_at=now))
            session.add(ToolInvocation(id=f"invocation-{key}", enterprise_id=key,
                tool_definition_id=f"tool-{key}", tool_key="get_metric", tool_version="1.0.0",
                actor_principal_id="group-admin", actor_snapshot={},
                authentication_method="session", permission_set_version="v2",
                request_id=f"request-{key}", run_id=f"run-verify-{key}",
                input_parameters={}, output_summary={}, status="succeeded", duration_ms=1,
                started_at=now, finished_at=now))
            session.add(AuthorizationDecision(id=f"decision-{key}", enterprise_id=key,
                request_id=f"request-{key}", run_id=f"run-verify-{key}",
                actor_principal_id="group-admin",
                permission_key="identity.user.manage", resource_type="identity", resource_key=key,
                decision="allow", reason="Synthetic group grant", policy_version="verify-v2",
                scope_snapshot=[], decided_at=now))
        session.commit()
    result = identity_admin_overview(database, enterprise_id="b")
    assert result.users == []
    assert len(result.recent_decisions) == 1
    assert result.recent_decisions[0].id == "decision-b"
    assert result.recent_decisions[0].actor_name == "Synthetic group administrator"
    tools = tool_admin_overview(database, enterprise_id="b")
    assert tools.stats.invocations == 1
    assert [item.id for item in tools.recent_invocations] == ["invocation-b"]
    assert tools.recent_invocations[0].actor_name == "Synthetic group administrator"
    database.dispose()
