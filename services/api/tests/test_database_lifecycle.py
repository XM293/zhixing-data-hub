from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, inspect, select, text

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AccessRole,
    ActionApprovalEvent,
    ActionExecution,
    ActionProposal,
    AgentFeedbackEvent,
    AgentRuntimeEventRecord,
    AgentRuntimeSession,
    AgentRuntimeTurn,
    AuthorizationDecision,
    BusinessAnalysisRun,
    BusinessBrief,
    ChannelIdentity,
    ChannelIdentityEvent,
    CustomerOperationRun,
    CustomerProfile,
    CustomerServiceConversation,
    CustomerServiceEvent,
    CustomerServiceMessage,
    CustomerServiceOrderContext,
    CustomerServiceReplyDraft,
    CustomerTouchpointFact,
    DataQualityRule,
    DataScopeMapping,
    DecisionPackage,
    Enterprise,
    EvaluationCandidate,
    EvidenceSnapshot,
    HumanHandoffCase,
    IdentityManagementEvent,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionRun,
    KnowledgeLifecycleEvent,
    MCPGatewaySession,
    MCPGatewaySessionEvent,
    MeetingClaim,
    MeetingDecisionConfirmation,
    MeetingDeliberationTurn,
    Membership,
    MemoryCandidate,
    MetricDefinition,
    OrgUnit,
    PermissionDefinition,
    Position,
    Principal,
    RoleAssignment,
    RoleConfigurationEvent,
    RoleTemplate,
    RoleTemplateVersion,
    RoleTwinProfile,
    RoleTwinVersion,
    ScopeGrant,
    SeedVersion,
    SourceSyncSchedule,
    StoreReviewPlan,
    StoreReviewScheduleRun,
    ToolDefinition,
    ToolInvocation,
    TwinMeetingSeat,
    TwinScene,
    UserAccount,
)
from zhixing_api.database import Database, assert_test_database_url
from zhixing_api.seed import SeedDriftError, seed_database


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://test",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'migration_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


def test_empty_database_upgrade_seed_and_rebuild_are_repeatable(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    database = Database(settings.database_url)
    assert database.revision() == "base"

    database.migrate()
    database.migrate()
    assert database.revision() == database.migration_head()
    table_names = inspect(database.engine).get_table_names()
    assert "seed_versions" in table_names
    assert "background_jobs" in table_names
    assert "job_attempts" in table_names
    assert "source_resources" in table_names
    assert "sync_resource_runs" in table_names
    assert "sync_checkpoints" in table_names
    assert "raw_page_manifests" in table_names
    assert "mapping_conflicts" in table_names
    assert "source_authority_rules" in table_names
    assert "metric_definitions" in table_names
    assert "data_quality_rules" in table_names
    assert "data_quality_results" in table_names
    assert "knowledge_documents" in table_names
    assert "knowledge_chunks" in table_names
    assert "role_twin_profiles" in table_names
    assert "agent_runs" in table_names
    assert "agent_runtime_approvals" in table_names
    assert "meeting_runtime_runs" in table_names
    runtime_session_columns = {
        column["name"]: column
        for column in inspect(database.engine).get_columns("agent_runtime_sessions")
    }
    assert runtime_session_columns["runtime_spec"]["nullable"] is False
    assert "evidence_snapshots" in table_names
    assert "evidence_snapshot_items" in table_names
    assert "memory_candidates" in table_names
    assert "meeting_claims" in table_names
    assert "meeting_deliberation_turns" in table_names
    assert "decision_packages" in table_names
    assert "meeting_decision_confirmations" in table_names
    assert "action_proposals" in table_names
    assert "action_approval_events" in table_names
    assert "action_executions" in table_names
    assert "action_work_items" in table_names
    assert "action_work_events" in table_names
    assert "principals" in table_names
    assert "user_accounts" in table_names
    assert "org_units" in table_names
    assert "positions" in table_names
    assert "memberships" in table_names
    assert "permission_definitions" in table_names
    assert "access_roles" in table_names
    assert "access_role_permissions" in table_names
    assert "role_assignments" in table_names
    assert "scope_grants" in table_names
    assert "authorization_decisions" in table_names
    assert "tool_definitions" in table_names
    assert "tool_invocations" in table_names
    assert "mcp_gateway_sessions" in table_names
    assert "mcp_gateway_session_events" in table_names
    assert "channel_identities" in table_names
    assert "channel_identity_events" in table_names
    assert "platform_operation_events" in table_names
    assert "platform_parameters" in table_names
    assert "platform_dictionary_types" in table_names
    assert "platform_dictionary_items" in table_names
    assert "domain_events" in table_names
    assert "notifications" in table_names
    assert "notification_deliveries" in table_names
    assert "file_assets" in table_names
    assert "bulk_exchange_jobs" in table_names
    assert "bulk_exchange_rows" in table_names
    assert "access_delegations" in table_names
    assert "knowledge_ingestion_runs" in table_names
    assert "knowledge_lifecycle_events" in table_names
    assert "chat_import_runs" in table_names
    assert "chat_messages" in table_names
    assert "approved_memories" in table_names
    assert "memory_review_events" in table_names
    assert "agent_run_context_items" in table_names
    assert "role_templates" in table_names
    assert "role_template_versions" in table_names
    assert "role_twin_versions" in table_names
    assert "role_configuration_events" in table_names
    assert "agent_feedback_events" in table_names
    assert "human_handoff_cases" in table_names
    assert "evaluation_candidates" in table_names
    assert "business_analysis_runs" in table_names
    assert "business_briefs" in table_names
    assert "store_review_plans" in table_names
    assert "store_review_schedule_runs" in table_names
    assert "customer_service_conversations" in table_names
    assert "customer_service_messages" in table_names
    assert "customer_service_order_contexts" in table_names
    assert "customer_service_reply_drafts" in table_names
    assert "customer_service_events" in table_names
    assert "ai_provider_probe_runs" in table_names
    assert "agent_runtime_probe_runs" in table_names
    assert "agent_runtime_sessions" in table_names
    assert "agent_runtime_turns" in table_names
    assert "agent_runtime_events" in table_names
    assert "commerce_order_facts" in table_names
    assert "commerce_order_line_facts" in table_names
    assert "commerce_refund_facts" in table_names
    assert "commerce_inventory_snapshot_facts" in table_names
    assert "commerce_ad_performance_facts" in table_names
    assert "data_scope_mappings" in table_names
    assert "customer_profiles" in table_names
    assert "customer_touchpoint_facts" in table_names
    assert "customer_operation_runs" in table_names
    runtime_turn_columns = {
        item["name"]
        for item in inspect(database.engine).get_columns("agent_runtime_turns")
    }
    assert {
        "agent_run_id",
        "mcp_gateway_session_id",
        "request_id",
        "run_id",
    }.issubset(runtime_turn_columns)
    background_job_columns = {
        item["name"] for item in inspect(database.engine).get_columns("background_jobs")
    }
    assert {
        "actor_snapshot",
        "permission_set_version",
        "required_permissions",
        "scope_type",
        "scope_id",
        "execution_token_hash",
    }.issubset(background_job_columns)
    tool_invocation_columns = {
        item["name"] for item in inspect(database.engine).get_columns("tool_invocations")
    }
    assert {
        "gateway_session_id",
        "agent_run_id",
        "authentication_method",
        "permission_set_version",
        "session_permission_set_version",
    }.issubset(tool_invocation_columns)
    meeting_columns = {
        item["name"] for item in inspect(database.engine).get_columns("twin_meetings")
    }
    assert {
        "initiated_by_principal_id",
        "actor_snapshot",
        "idempotency_key",
        "request_hash",
        "scope_type",
        "scope_key",
    }.issubset(meeting_columns)
    agent_run_columns = {
        item["name"] for item in inspect(database.engine).get_columns("agent_runs")
    }
    assert "actor_principal_id" in agent_run_columns
    action_proposal_columns = {
        item["name"] for item in inspect(database.engine).get_columns("action_proposals")
    }
    assert {
        "source_type",
        "source_key",
        "source_label",
        "scope_type",
        "scope_key",
        "customer_operation_run_id",
        "business_analysis_run_id",
        "evidence_snapshot_id",
    }.issubset(action_proposal_columns)

    first = seed_database(database, settings)
    second = seed_database(database, settings)
    assert first.seed_key == "demo-operational-twin"
    assert first.version == "1.31.0"
    assert first.checksum == second.checksum
    with database.session() as session:
        assert session.scalar(select(func.count(SeedVersion.seed_key))) == 1

        assert session.scalar(select(func.count(TwinScene.id))) == 3
        assert session.scalar(select(func.count(TwinMeetingSeat.id))) == 12
        assert session.scalar(select(func.count(MetricDefinition.id))) == 21
        assert session.scalar(select(func.count(DataQualityRule.id))) == 6
        assert session.scalar(select(func.count(KnowledgeDocument.id))) == 6
        assert session.scalar(select(func.count(KnowledgeChunk.id))) >= 20
        assert session.scalar(select(func.count(RoleTwinProfile.id))) == 4
        assert session.scalar(select(func.count(RoleTemplate.id))) == 4
        assert session.scalar(select(func.count(RoleTemplateVersion.id))) == 4
        assert session.scalar(select(func.count(RoleTwinVersion.id))) == 4
        assert session.scalar(select(func.count(RoleConfigurationEvent.id))) == 0
        assert session.scalar(select(func.count(MemoryCandidate.id))) == 6
        assert session.scalar(select(func.count(EvidenceSnapshot.id))) == 0
        assert session.scalar(select(func.count(MeetingClaim.id))) == 0
        assert session.scalar(select(func.count(MeetingDeliberationTurn.id))) == 0
        assert session.scalar(select(func.count(DecisionPackage.id))) == 0
        assert session.scalar(select(func.count(MeetingDecisionConfirmation.id))) == 0
        assert session.scalar(select(func.count(ActionProposal.id))) == 0
        assert session.scalar(select(func.count(ActionApprovalEvent.id))) == 0
        assert session.scalar(select(func.count(ActionExecution.id))) == 0
        assert session.scalar(select(func.count(Principal.id))) == 6
        assert session.scalar(select(func.count(UserAccount.id))) == 6
        assert session.scalar(select(func.count(OrgUnit.id))) == 6
        assert session.scalar(select(func.count(Position.id))) == 6
        assert session.scalar(select(func.count(Membership.id))) == 6
        assert session.scalar(select(func.count(PermissionDefinition.id))) == 54
        assert session.scalar(select(func.count(StoreReviewPlan.id))) == 0
        assert session.scalar(select(func.count(StoreReviewScheduleRun.id))) == 0
        assert session.scalar(select(func.count(AgentFeedbackEvent.id))) == 0
        assert session.scalar(select(func.count(HumanHandoffCase.id))) == 0
        assert session.scalar(select(func.count(EvaluationCandidate.id))) == 0
        assert session.scalar(select(func.count(BusinessAnalysisRun.id))) == 0
        assert session.scalar(select(func.count(BusinessBrief.id))) == 0
        assert session.scalar(select(func.count(CustomerServiceConversation.id))) == 12
        assert session.scalar(select(func.count(CustomerServiceMessage.id))) == 14
        assert session.scalar(select(func.count(CustomerServiceOrderContext.id))) == 12
        assert session.scalar(select(func.count(CustomerServiceReplyDraft.id))) == 0
        assert session.scalar(select(func.count(CustomerServiceEvent.id))) == 0
        assert session.scalar(select(func.count(AccessRole.id))) == 6
        assert session.scalar(select(func.count(RoleAssignment.id))) == 6
        assert session.scalar(select(func.count(ScopeGrant.id))) == 11
        assert session.scalar(select(func.count(AuthorizationDecision.id))) == 0
        assert session.scalar(select(func.count(IdentityManagementEvent.id))) == 0
        assert session.scalar(select(func.count(ToolDefinition.id))) == 5
        assert session.scalar(select(func.count(ToolInvocation.id))) == 0
        assert session.scalar(select(func.count(MCPGatewaySession.id))) == 0
        assert session.scalar(select(func.count(MCPGatewaySessionEvent.id))) == 0
        assert session.scalar(select(func.count(AgentRuntimeSession.id))) == 0
        assert session.scalar(select(func.count(AgentRuntimeTurn.id))) == 0
        assert session.scalar(select(func.count(AgentRuntimeEventRecord.id))) == 0
        assert session.scalar(select(func.count(ChannelIdentity.id))) == 3
        assert session.scalar(select(func.count(ChannelIdentityEvent.id))) == 0
        assert session.scalar(select(func.count(DataScopeMapping.id))) == 0
        assert session.scalar(select(func.count(CustomerProfile.id))) == 0
        assert session.scalar(select(func.count(CustomerTouchpointFact.id))) == 0
        assert session.scalar(select(func.count(CustomerOperationRun.id))) == 0
        assert session.scalar(select(func.count(KnowledgeIngestionRun.id))) == 0
        assert session.scalar(select(func.count(KnowledgeLifecycleEvent.id))) == 0
        session.add(
            Enterprise(
                id="temporary_test_enterprise",
                code="TEMP-TEST",
                name="应在重建后删除",
                timezone="Asia/Shanghai",
                created_at=second.applied_at,
            )
        )
        session.commit()

    database.rebuild_test_schema()
    seed_database(database, settings)
    assert database.revision() == database.migration_head()
    with database.session() as session:
        assert session.get(Enterprise, "temporary_test_enterprise") is None
        assert session.scalar(select(func.count(SeedVersion.seed_key))) == 1
    database.dispose()


def test_seed_rejects_unversioned_content_drift(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    database = Database(settings.database_url)
    database.migrate()
    seed_database(database, settings)
    with database.session() as session:
        record = session.get(SeedVersion, "demo-operational-twin")
        assert record is not None
        record.checksum = "0" * 64
        session.commit()

    with pytest.raises(SeedDriftError, match="请先提升清单版本"):
        seed_database(database, settings)
    database.dispose()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+pysqlite:///var/customer_test.db",
        "postgresql+psycopg://user:password@localhost/zhixing_verify",
        "sqlite+pysqlite:///:memory:",
    ],
)
def test_rebuild_guard_accepts_only_explicit_test_targets(url: str) -> None:
    assert_test_database_url(url)


def test_rebuild_guard_rejects_non_test_database() -> None:
    with pytest.raises(ValueError, match="拒绝重建非测试数据库"):
        assert_test_database_url("postgresql+psycopg://user:password@localhost/customer_production")


def test_0053_upgrade_path_reaches_current_lingxing_head(tmp_path: Path) -> None:
    database = Database(
        f"sqlite+pysqlite:///{(tmp_path / 'upgrade_test.db').as_posix()}"
    )
    database.migrate("0053_runtime_resume_spec")
    assert database.revision() == "0053_runtime_resume_spec"
    database.migrate("head")
    assert database.revision() == database.migration_head()
    columns = {
        column["name"] for column in inspect(database.engine).get_columns("sync_runs")
    }
    assert {"request_id", "scope_snapshot", "lease_owner"}.issubset(columns)
    schedule_columns = {
        column["name"] for column in inspect(database.engine).get_columns(
            "source_sync_schedules")
    }
    assert "resource_parameters" in schedule_columns
    manifest_columns = {
        column["name"] for column in inspect(database.engine).get_columns(
            "raw_page_manifests")
    }
    assert "request_parameters" in manifest_columns
    database.dispose()


def test_0067_schedule_rows_receive_empty_resource_parameters(tmp_path: Path) -> None:
    database = Database(
        f"sqlite+pysqlite:///{(tmp_path / 'schedule_upgrade_test.db').as_posix()}"
    )
    database.migrate("0067_source_mirror_pages")
    now = datetime.now(UTC)
    with database.engine.begin() as connection:
        connection.execute(text("INSERT INTO enterprises "
            "(id, code, name, timezone, created_at) VALUES "
            "('legal', 'legal', 'Synthetic', 'UTC', :now)"), {"now": now})
        connection.execute(text("INSERT INTO external_systems "
            "(id, enterprise_id, system_key, name, system_type, base_url, status, "
            "source_schema_version, mapping_version) VALUES "
            "('source', 'legal', 'source', 'Synthetic', 'lingxing', "
            "'https://openapi.lingxing.com', 'configured', 'unknown', '1')"))
        connection.execute(text("INSERT INTO source_sync_schedules "
            "(id, enterprise_id, external_system_id, name, resource_key, strategy, status, "
            "interval_seconds, overlap_seconds, safety_lag_seconds, reconcile_days, "
            "next_run_at, pending_reconciliation, actor_snapshot, scope_snapshot, version, "
            "created_at, updated_at, projection_mode) VALUES "
            "('schedule', 'legal', 'source', 'Synthetic', 'shops', 'snapshot', 'paused', "
            "3600, 300, 120, 7, :now, false, '{}', '{}', 1, :now, :now, 'deferred')"),
            {"now": now})
    database.migrate("head")
    with database.session() as session:
        assert session.get(SourceSyncSchedule, "schedule").resource_parameters == {}
    database.dispose()
