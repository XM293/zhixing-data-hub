from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceMirrorPage(Base):
    """Source landing receipt; projection state belongs to its independent run."""

    __tablename__ = "source_mirror_pages"

    raw_manifest_id: Mapped[str] = mapped_column(
        ForeignKey("raw_page_manifests.id"), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    source_resource_id: Mapped[str] = mapped_column(ForeignKey("source_resources.id"), index=True)
    acquisition_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    projection_run_id: Mapped[str | None] = mapped_column(ForeignKey("sync_runs.id"), unique=True)
    schema_status: Mapped[str] = mapped_column(String(40))
    mapping_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceRequestBudget(Base):
    """Shared per-account/resource budget; contains no credentials or tokens."""

    __tablename__ = "source_request_budgets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    next_allowed_epoch: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SeedVersion(Base):
    __tablename__ = "seed_versions"

    seed_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    checksum: Mapped[str] = mapped_column(String(64))
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EnterpriseGroup(Base):
    """集团层级。法人企业仍以 ``Enterprise.id`` 作为数据隔离边界。"""

    __tablename__ = "enterprise_groups"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Enterprise(Base):
    __tablename__ = "enterprises"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    group_id: Mapped[str | None] = mapped_column(
        ForeignKey("enterprise_groups.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BusinessUnit(Base):
    """法人企业下的品牌、事业部或区域经营单元。"""

    __tablename__ = "business_units"
    __table_args__ = (UniqueConstraint("enterprise_id", "unit_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    unit_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    unit_type: Mapped[str] = mapped_column(String(48), index=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_units.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EnterpriseMembership(Base):
    """主体与法人企业的成员关系，支持集团账号的多企业成员关系。"""

    __tablename__ = "enterprise_memberships"
    __table_args__ = (UniqueConstraint("principal_id", "enterprise_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    membership_type: Mapped[str] = mapped_column(String(32), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EnterpriseScopeGrant(Base):
    """集团/企业范围授权的声明层，角色范围仍由 ``ScopeGrant`` 承载。"""

    __tablename__ = "enterprise_scope_grants"
    __table_args__ = (UniqueConstraint("principal_id", "scope_type", "scope_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    group_id: Mapped[str | None] = mapped_column(
        ForeignKey("enterprise_groups.id"), nullable=True, index=True
    )
    enterprise_id: Mapped[str | None] = mapped_column(
        ForeignKey("enterprises.id"), nullable=True, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(48), index=True)
    scope_id: Mapped[str] = mapped_column(String(160), index=True)
    effect: Mapped[str] = mapped_column(String(16), default="allow")
    status: Mapped[str] = mapped_column(String(32), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConsolidationProfile(Base):
    """集团指标合并口径的版本化配置。"""

    __tablename__ = "consolidation_profiles"
    __table_args__ = (UniqueConstraint("group_id", "profile_key", "version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("enterprise_groups.id"), index=True)
    profile_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    base_currency: Mapped[str] = mapped_column(String(16))
    elimination_rules: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    exchange_rate_policy: Mapped[dict[str, object]] = mapped_column(JSON)
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CenterAssignment(Base):
    """中心在集团、法人或业务单元范围内的启用状态。"""

    __tablename__ = "center_assignments"
    __table_args__ = (UniqueConstraint("scope_type", "scope_id", "center_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    group_id: Mapped[str | None] = mapped_column(
        ForeignKey("enterprise_groups.id"), nullable=True, index=True
    )
    enterprise_id: Mapped[str | None] = mapped_column(
        ForeignKey("enterprises.id"), nullable=True, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(48), index=True)
    scope_id: Mapped[str] = mapped_column(String(160), index=True)
    center_key: Mapped[str] = mapped_column(String(120), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SourceBinding(Base):
    """外部来源与法人、业务单元及店铺业务键的稳定映射。"""

    __tablename__ = "source_bindings"
    __table_args__ = (UniqueConstraint("enterprise_id", "source_system_id", "external_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    business_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_units.id"), nullable=True, index=True
    )
    source_system_id: Mapped[str] = mapped_column(String(64), index=True)
    external_key: Mapped[str] = mapped_column(String(200), index=True)
    canonical_type: Mapped[str] = mapped_column(String(64), index=True)
    canonical_id: Mapped[str] = mapped_column(String(200), index=True)
    mapping_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    suggested_business_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_units.id"), nullable=True, index=True
    )
    suggestion_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suggestion_evidence: Mapped[list[object]] = mapped_column(JSON, default=list)
    suggestion_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Principal(Base):
    __tablename__ = "principals"
    __table_args__ = (UniqueConstraint("enterprise_id", "principal_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    principal_key: Mapped[str] = mapped_column(String(120), index=True)
    principal_type: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserAccount(Base):
    __tablename__ = "user_accounts"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "account_key"),
        UniqueConstraint("enterprise_id", "local_login_name"),
        UniqueConstraint("principal_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    account_key: Mapped[str] = mapped_column(String(120), index=True)
    local_login_name: Mapped[str] = mapped_column(String(120), index=True)
    experience_role_key: Mapped[str] = mapped_column(String(48), index=True)
    email: Mapped[str | None] = mapped_column(String(240), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    authentication_source: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChannelIdentity(Base):
    __tablename__ = "channel_identities"
    __table_args__ = (
        UniqueConstraint(
            "enterprise_id",
            "channel_key",
            "external_tenant_key",
            "external_identity_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    channel_key: Mapped[str] = mapped_column(String(48), index=True)
    external_tenant_key: Mapped[str] = mapped_column(String(160), index=True)
    external_identity_hash: Mapped[str] = mapped_column(String(64))
    external_identity_hint: Mapped[str] = mapped_column(String(32))
    observed_display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (UniqueConstraint("session_token_hash"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    user_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    session_token_hash: Mapped[str] = mapped_column(String(128), index=True)
    authentication_method: Mapped[str] = mapped_column(String(48))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96))
    run_id: Mapped[str] = mapped_column(String(96))
    scope_selection: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class MCPGatewaySession(Base):
    __tablename__ = "mcp_gateway_sessions"
    __table_args__ = (UniqueConstraint("session_token_hash"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    user_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    client_id: Mapped[str] = mapped_column(String(120), index=True)
    session_token_hash: Mapped[str] = mapped_column(String(128), index=True)
    allowed_tool_keys: Mapped[list[str]] = mapped_column(JSON)
    scope_constraints: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    issued_permission_set_version: Mapped[str] = mapped_column(String(120), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)


class MCPGatewaySessionEvent(Base):
    __tablename__ = "mcp_gateway_session_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    gateway_session_id: Mapped[str] = mapped_column(
        ForeignKey("mcp_gateway_sessions.id", ondelete="CASCADE"), index=True
    )
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    reason: Mapped[str] = mapped_column(String(500))
    permission_set_version: Mapped[str] = mapped_column(String(120))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OrgUnit(Base):
    __tablename__ = "org_units"
    __table_args__ = (UniqueConstraint("enterprise_id", "org_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    org_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    unit_type: Mapped[str] = mapped_column(String(48), index=True)
    parent_org_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("org_units.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("enterprise_id", "position_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    org_unit_id: Mapped[str] = mapped_column(ForeignKey("org_units.id"), index=True)
    position_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    position_level: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "principal_id", "org_unit_id", "position_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    org_unit_id: Mapped[str] = mapped_column(ForeignKey("org_units.id"), index=True)
    position_id: Mapped[str] = mapped_column(ForeignKey("positions.id"), index=True)
    membership_type: Mapped[str] = mapped_column(String(32))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PermissionDefinition(Base):
    __tablename__ = "permission_definitions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    permission_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160))
    resource: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(80))
    risk_level: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)


class AccessRole(Base):
    __tablename__ = "access_roles"
    __table_args__ = (UniqueConstraint("enterprise_id", "role_key", "version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    role_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(500))
    version: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccessRolePermission(Base):
    __tablename__ = "access_role_permissions"
    __table_args__ = (UniqueConstraint("access_role_id", "permission_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    access_role_id: Mapped[str] = mapped_column(ForeignKey("access_roles.id"), index=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey("permission_definitions.id"), index=True)
    effect: Mapped[str] = mapped_column(String(16), default="allow")


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("enterprise_id", "principal_id", "access_role_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    access_role_id: Mapped[str] = mapped_column(ForeignKey("access_roles.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScopeGrant(Base):
    __tablename__ = "scope_grants"
    __table_args__ = (UniqueConstraint("role_assignment_id", "scope_type"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    role_assignment_id: Mapped[str] = mapped_column(
        ForeignKey("role_assignments.id", ondelete="CASCADE"), index=True
    )
    scope_type: Mapped[str] = mapped_column(String(48), index=True)
    scope_ids: Mapped[list[str]] = mapped_column(JSON)
    effect: Mapped[str] = mapped_column(String(16), default="allow")
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthorizationDecision(Base):
    __tablename__ = "authorization_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    permission_key: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), index=True)
    resource_key: Mapped[str] = mapped_column(String(200), index=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str] = mapped_column(String(240))
    policy_version: Mapped[str] = mapped_column(String(120))
    scope_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IdentityManagementEvent(Base):
    __tablename__ = "identity_management_events"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    target_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    target_account_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id"), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    before_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    after_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    changed_fields: Mapped[list[str]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class IdentityCatalogEvent(Base):
    __tablename__ = "identity_catalog_events"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(96), index=True)
    target_type: Mapped[str] = mapped_column(String(48), index=True)
    target_key: Mapped[str] = mapped_column(String(160), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    before_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    after_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    changed_fields: Mapped[list[str]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ChannelIdentityEvent(Base):
    __tablename__ = "channel_identity_events"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    channel_identity_id: Mapped[str] = mapped_column(
        ForeignKey("channel_identities.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    before_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True
    )
    after_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True
    )
    before_status: Mapped[str] = mapped_column(String(32))
    after_status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PlatformOperationEvent(Base):
    __tablename__ = "platform_operation_events"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(96), index=True)
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str] = mapped_column(String(160), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    reason: Mapped[str] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    attributes: Mapped[dict[str, object]] = mapped_column(JSON)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PlatformParameter(Base):
    __tablename__ = "platform_parameters"
    __table_args__ = (UniqueConstraint("enterprise_id", "parameter_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    parameter_key: Mapped[str] = mapped_column(String(160), index=True)
    group_key: Mapped[str] = mapped_column(String(80), index=True)
    label: Mapped[str] = mapped_column(String(160))
    value_type: Mapped[str] = mapped_column(String(32))
    value: Mapped[object] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PlatformDictionaryType(Base):
    __tablename__ = "platform_dictionary_types"
    __table_args__ = (UniqueConstraint("enterprise_id", "dictionary_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    dictionary_key: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PlatformDictionaryItem(Base):
    __tablename__ = "platform_dictionary_items"
    __table_args__ = (UniqueConstraint("dictionary_type_id", "item_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    dictionary_type_id: Mapped[str] = mapped_column(
        ForeignKey("platform_dictionary_types.id", ondelete="CASCADE"), index=True
    )
    item_key: Mapped[str] = mapped_column(String(120), index=True)
    label: Mapped[str] = mapped_column(String(160))
    value: Mapped[object] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DomainEvent(Base):
    __tablename__ = "domain_events"
    __table_args__ = (UniqueConstraint("enterprise_id", "event_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    event_key: Mapped[str] = mapped_column(String(160), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(80), index=True)
    aggregate_id: Mapped[str] = mapped_column(String(160), index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("domain_events.id"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(240))
    body: Mapped[str] = mapped_column(String(1000))
    severity: Mapped[str] = mapped_column(String(24), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    action_route: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("notification_id", "channel"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notification_id: Mapped[str] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FileAsset(Base):
    __tablename__ = "file_assets"
    __table_args__ = (UniqueConstraint("enterprise_id", "asset_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    asset_key: Mapped[str] = mapped_column(String(160), index=True)
    file_name: Mapped[str] = mapped_column(String(300))
    media_type: Mapped[str] = mapped_column(String(160))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_provider: Mapped[str] = mapped_column(String(48))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    uploaded_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"))
    required_permission: Mapped[str] = mapped_column(String(120))
    scope_type: Mapped[str] = mapped_column(String(48))
    scope_id: Mapped[str] = mapped_column(String(160))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class BulkExchangeJob(Base):
    __tablename__ = "bulk_exchange_jobs"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    operation: Mapped[str] = mapped_column(String(24), index=True)
    dataset_key: Mapped[str] = mapped_column(String(120), index=True)
    file_format: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(32), index=True)
    file_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("file_assets.id"), nullable=True, index=True
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)
    applied_rows: Mapped[int] = mapped_column(Integer, default=0)
    validation_summary: Mapped[dict[str, object]] = mapped_column(JSON)
    requested_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"))
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BulkExchangeRow(Base):
    __tablename__ = "bulk_exchange_rows"
    __table_args__ = (UniqueConstraint("exchange_job_id", "row_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    exchange_job_id: Mapped[str] = mapped_column(
        ForeignKey("bulk_exchange_jobs.id", ondelete="CASCADE"), index=True
    )
    row_number: Mapped[int] = mapped_column(Integer)
    source_data: Mapped[dict[str, object]] = mapped_column(JSON)
    normalized_data: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    errors: Mapped[list[dict[str, object]]] = mapped_column(JSON)


class AccessDelegation(Base):
    __tablename__ = "access_delegations"
    __table_args__ = (UniqueConstraint("enterprise_id", "delegation_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    delegation_key: Mapped[str] = mapped_column(String(160), index=True)
    delegator_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    delegatee_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    permissions: Mapped[list[str]] = mapped_column(JSON)
    scopes: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reason: Mapped[str] = mapped_column(String(500))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"
    __table_args__ = (UniqueConstraint("enterprise_id", "tool_key", "version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    tool_key: Mapped[str] = mapped_column(String(120), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(800))
    risk_level: Mapped[str] = mapped_column(String(16), index=True)
    permission_key: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80))
    scope_resolver: Mapped[str] = mapped_column(String(120))
    input_schema: Mapped[dict[str, object]] = mapped_column(JSON)
    output_schema: Mapped[dict[str, object]] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    timeout_seconds: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ToolInvocation(Base):
    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    tool_definition_id: Mapped[str] = mapped_column(ForeignKey("tool_definitions.id"), index=True)
    tool_key: Mapped[str] = mapped_column(String(120), index=True)
    tool_version: Mapped[str] = mapped_column(String(32))
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    gateway_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("mcp_gateway_sessions.id"), nullable=True, index=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True, index=True
    )
    authentication_method: Mapped[str] = mapped_column(String(48), index=True)
    permission_set_version: Mapped[str] = mapped_column(String(120), index=True)
    session_permission_set_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    input_parameters: Mapped[dict[str, object]] = mapped_column(JSON)
    output_summary: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExternalSystem(Base):
    __tablename__ = "external_systems"
    __table_args__ = (UniqueConstraint("enterprise_id", "system_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    business_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_units.id"), nullable=True, index=True
    )
    system_key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    system_type: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="configured")
    source_schema_version: Mapped[str] = mapped_column(String(32), default="unknown")
    mapping_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    access_mode: Mapped[str] = mapped_column(String(32), default="read_only")
    credential_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    capability_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connection_status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceResource(Base):
    __tablename__ = "source_resources"
    __table_args__ = (UniqueConstraint("external_system_id", "resource_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    resource_key: Mapped[str] = mapped_column(String(120))
    method: Mapped[str] = mapped_column(String(8), default="GET")
    path: Mapped[str] = mapped_column(String(300))
    schema_status: Mapped[str] = mapped_column(String(32), default="schema_pending")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    display_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    version: Mapped[str] = mapped_column(String(32), default="1")
    validation_status: Mapped[str] = mapped_column(
        String(32), default="unvalidated", server_default="unvalidated", index=True)
    validation_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceSyncSchedule(Base):
    __tablename__ = "source_sync_schedules"
    projection_mode: Mapped[str] = mapped_column(
        String(20), default="inline", server_default="inline")
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    resource_key: Mapped[str] = mapped_column(String(120))
    resource_version: Mapped[str] = mapped_column(String(32), default="unknown",
                                                  server_default="unknown")
    resource_parameters: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, server_default="{}")
    parameter_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameter_fanout_offset: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    parameter_pending_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parameter_fanout_total: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1")
    parameter_cycle_as_of: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    parameter_waiting_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    strategy: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="paused", index=True)
    interval_seconds: Mapped[int] = mapped_column(Integer)
    overlap_seconds: Mapped[int] = mapped_column(Integer)
    safety_lag_seconds: Mapped[int] = mapped_column(Integer)
    reconcile_days: Mapped[int] = mapped_column(Integer)
    initial_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    watermark: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pending_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_run_id: Mapped[str | None] = mapped_column(ForeignKey("sync_runs.id"), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    pending_reconciliation: Mapped[bool] = mapped_column(Boolean, default=False)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    scope_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceBackfillPlan(Base):
    __tablename__ = "source_backfill_plans"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    source_resource_id: Mapped[str] = mapped_column(ForeignKey("source_resources.id"), index=True)
    resource_version: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    resource_key: Mapped[str] = mapped_column(String(120))
    resource_parameters: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, server_default="{}")
    parameter_policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameter_waiting_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    projection_mode: Mapped[str] = mapped_column(
        String(20), default="deferred", server_default="deferred")
    status: Mapped[str] = mapped_column(String(32), default="paused", index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cursor: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    partition_days: Mapped[int] = mapped_column(Integer, default=7)
    batch_size: Mapped[int] = mapped_column(Integer, default=16)
    active_run_id: Mapped[str | None] = mapped_column(ForeignKey("sync_runs.id"), nullable=True)
    windows_total: Mapped[int] = mapped_column(Integer)
    windows_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    windows_no_data: Mapped[int] = mapped_column(Integer, default=0)
    windows_with_conflicts: Mapped[int] = mapped_column(Integer, default=0)
    windows_failed: Mapped[int] = mapped_column(Integer, default=0)
    records_read: Mapped[int] = mapped_column(BigInteger, default=0)
    records_written: Mapped[int] = mapped_column(BigInteger, default=0)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    scope_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceCoverageWindow(Base):
    __tablename__ = "source_coverage_windows"
    __table_args__ = (UniqueConstraint(
        "backfill_plan_id", "window_start", "window_end",
        name="uq_source_coverage_windows_plan_range"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    backfill_plan_id: Mapped[str] = mapped_column(
        ForeignKey("source_backfill_plans.id", ondelete="CASCADE"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    source_resource_id: Mapped[str] = mapped_column(ForeignKey("source_resources.id"), index=True)
    resource_version: Mapped[str] = mapped_column(String(32))
    resource_key: Mapped[str] = mapped_column(String(120))
    partition_key: Mapped[str] = mapped_column(String(64), index=True)
    resource_parameters: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, server_default="{}")
    parameter_fanout_offset: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0")
    parameter_pending_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parameter_fanout_total: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1")
    parameter_cycle_as_of: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sync_run_id: Mapped[str | None] = mapped_column(ForeignKey("sync_runs.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    records_read: Mapped[int] = mapped_column(BigInteger, default=0)
    records_written: Mapped[int] = mapped_column(BigInteger, default=0)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SyncResourceRun(Base):
    __tablename__ = "sync_resource_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    source_resource_id: Mapped[str] = mapped_column(ForeignKey("source_resources.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    partition_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    records_read: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncCheckpoint(Base):
    __tablename__ = "sync_checkpoints"
    __table_args__ = (UniqueConstraint("source_resource_id", "partition_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_resource_id: Mapped[str] = mapped_column(ForeignKey("source_resources.id"), index=True)
    partition_key: Mapped[str] = mapped_column(String(160))
    cursor: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RawPageManifest(Base):
    __tablename__ = "raw_page_manifests"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sync_resource_run_id: Mapped[str] = mapped_column(
        ForeignKey("sync_resource_runs.id"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    compression: Mapped[str] = mapped_column(String(24), default="gzip")
    bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cursor: Mapped[str | None] = mapped_column(String(300), nullable=True)
    schema_status: Mapped[str] = mapped_column(String(32), default="unknown")
    request_parameters: Mapped[dict[str, object]] = mapped_column(
        JSON, default=dict, server_default="{}")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceDependencyValue(Base):
    """A non-secret source value that can safely drive a dependent read operation."""

    __tablename__ = "source_dependency_values"
    __table_args__ = (UniqueConstraint(
        "external_system_id", "value_type", "value_hash", "scope_kind",
        "scope_external_key", name="uq_source_dependency_value_identity"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(
        ForeignKey("external_systems.id"), index=True)
    source_resource_id: Mapped[str] = mapped_column(
        ForeignKey("source_resources.id"), index=True)
    first_manifest_id: Mapped[str] = mapped_column(ForeignKey("raw_page_manifests.id"))
    last_manifest_id: Mapped[str] = mapped_column(ForeignKey("raw_page_manifests.id"))
    business_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_units.id"), nullable=True, index=True)
    value_type: Mapped[str] = mapped_column(String(64), index=True)
    external_value: Mapped[str] = mapped_column(String(300))
    value_hash: Mapped[str] = mapped_column(String(64))
    scope_kind: Mapped[str] = mapped_column(String(32), default="source")
    scope_external_key: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    occurrence_count: Mapped[int] = mapped_column(BigInteger, default=1)
    extractor_version: Mapped[str] = mapped_column(String(32))


class SourceDependencyTuple(Base):
    """Same-row provider identifiers kept together to prevent invalid Cartesian fanout."""

    __tablename__ = "source_dependency_tuples"
    __table_args__ = (UniqueConstraint(
        "external_system_id", "tuple_type", "tuple_hash", "scope_kind",
        "scope_external_key", name="uq_source_dependency_tuple_identity"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(
        ForeignKey("external_systems.id"), index=True)
    source_resource_id: Mapped[str] = mapped_column(
        ForeignKey("source_resources.id"), index=True)
    first_manifest_id: Mapped[str] = mapped_column(ForeignKey("raw_page_manifests.id"))
    last_manifest_id: Mapped[str] = mapped_column(ForeignKey("raw_page_manifests.id"))
    business_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_units.id"), nullable=True, index=True)
    tuple_type: Mapped[str] = mapped_column(String(160), index=True)
    tuple_values: Mapped[dict[str, str]] = mapped_column(JSON)
    tuple_hash: Mapped[str] = mapped_column(String(64))
    scope_kind: Mapped[str] = mapped_column(String(32), default="source")
    scope_external_key: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    occurrence_count: Mapped[int] = mapped_column(BigInteger, default=1)
    extractor_version: Mapped[str] = mapped_column(String(32))


class SourceAuthorityRule(Base):
    __tablename__ = "source_authority_rules"
    __table_args__ = (UniqueConstraint("enterprise_id", "fact_family"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    fact_family: Mapped[str] = mapped_column(String(80))
    authority_resource_key: Mapped[str] = mapped_column(String(120))
    supplement_resource_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    late_arrival_window_hours: Mapped[int] = mapped_column(Integer, default=24)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("enterprise_groups.id"), nullable=True)
    version: Mapped[str] = mapped_column(String(32), default="1")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)


class SourceAuthorityAssignment(Base):
    __tablename__ = "source_authority_assignments"
    __table_args__ = (UniqueConstraint("enterprise_id", "business_unit_id", "fact_family"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    business_unit_id: Mapped[str] = mapped_column(ForeignKey("business_units.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    fact_family: Mapped[str] = mapped_column(String(80))
    resource_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MappingConflict(Base):
    __tablename__ = "mapping_conflicts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    external_object_key: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    candidates: Mapped[list[object]] = mapped_column(JSON)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enterprise_id: Mapped[str | None] = mapped_column(ForeignKey("enterprises.id"), nullable=True)
    resource_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_manifest_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class DataScopeMapping(Base):
    __tablename__ = "data_scope_mappings"
    __table_args__ = (
        UniqueConstraint(
            "enterprise_id",
            "external_system_id",
            "scope_type",
            "external_scope_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    scope_type: Mapped[str] = mapped_column(String(48), index=True)
    scope_key: Mapped[str] = mapped_column(String(160), index=True)
    external_scope_key: Mapped[str] = mapped_column(String(160), index=True)
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), index=True)
    attributes: Mapped[dict[str, object]] = mapped_column(JSON)
    source_schema_version: Mapped[str] = mapped_column(String(64))
    mapping_version: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("external_system_id", "record_type", "external_id", "content_hash"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    record_type: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(160))
    source_schema_version: Mapped[str] = mapped_column(String(32))
    mapping_version: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BusinessEntity(Base):
    __tablename__ = "business_entities"
    __table_args__ = (UniqueConstraint("enterprise_id", "entity_type", "canonical_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    canonical_key: Mapped[str] = mapped_column(String(160))
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32))
    attributes: Mapped[dict[str, object]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CanonicalSourceMixin:
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    resource_key: Mapped[str] = mapped_column(String(120))
    external_key: Mapped[str] = mapped_column(String(200))
    business_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_units.id"), nullable=True, index=True
    )
    raw_manifest_id: Mapped[str] = mapped_column(ForeignKey("raw_page_manifests.id"), index=True)
    schema_version: Mapped[str] = mapped_column(String(64))
    mapping_version: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CanonicalEntityOrigin(CanonicalSourceMixin, Base):
    __tablename__ = "canonical_entity_origins"
    __table_args__ = (UniqueConstraint("external_system_id", "resource_key", "external_key"),)
    entity_id: Mapped[str] = mapped_column(ForeignKey("business_entities.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)


class CanonicalSalesOrder(CanonicalSourceMixin, Base):
    """An order total is separate from a confirmed payment or recognized revenue."""
    __tablename__ = "canonical_sales_orders"
    __table_args__ = (UniqueConstraint("external_system_id", "resource_key", "external_key"),)
    store_key: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    base_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    exchange_rate_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_local_time: Mapped[str] = mapped_column(String(64))
    store_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    fulfillment_channel: Mapped[str | None] = mapped_column(String(32), nullable=True)


class CanonicalSalesOrderLine(Base):
    __tablename__ = "canonical_sales_order_lines"
    __table_args__ = (UniqueConstraint("order_id", "line_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("canonical_sales_orders.id"), index=True)
    line_key: Mapped[str] = mapped_column(String(64))
    sku: Mapped[str] = mapped_column(String(160))
    local_sku: Mapped[str | None] = mapped_column(String(160), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer)


class CanonicalAfterSale(CanonicalSourceMixin, Base):
    __tablename__ = "canonical_after_sales"
    __table_args__ = (UniqueConstraint("external_system_id", "resource_key", "external_key"),)
    source_item_key: Mapped[str] = mapped_column(Text)
    store_key: Mapped[str] = mapped_column(String(160), index=True)
    order_external_key: Mapped[str] = mapped_column(String(200), index=True)
    sku: Mapped[str] = mapped_column(String(160))
    after_type: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_amount_text: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    base_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    exchange_rate_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_local_time: Mapped[str] = mapped_column(String(64))
    source_updated_local_time: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    store_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality_flags: Mapped[list[str]] = mapped_column(JSON)


class CanonicalFulfillment(CanonicalSourceMixin, Base):
    __tablename__ = "canonical_fulfillments"
    __table_args__ = (UniqueConstraint("external_system_id", "resource_key", "external_key"),)
    store_key: Mapped[str] = mapped_column(String(160), index=True)
    warehouse_key: Mapped[str] = mapped_column(String(160), index=True)
    shipment_number: Mapped[str] = mapped_column(String(200))
    order_external_key: Mapped[str] = mapped_column(String(200), index=True)
    platform_order_keys: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(64), index=True)
    logistics_status: Mapped[int] = mapped_column(Integer)
    freight_amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    freight_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_freight_amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    base_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    exchange_rate_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_local_time: Mapped[str] = mapped_column(String(64))
    source_updated_local_time: Mapped[str] = mapped_column(String(64))
    dispatched_local_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    quality_flags: Mapped[list[str]] = mapped_column(JSON)


class CanonicalFulfillmentLine(Base):
    __tablename__ = "canonical_fulfillment_lines"
    __table_args__ = (UniqueConstraint("fulfillment_id", "external_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fulfillment_id: Mapped[str] = mapped_column(ForeignKey("canonical_fulfillments.id"), index=True)
    external_key: Mapped[str] = mapped_column(String(200))
    product_external_key: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(BigInteger)
    bundle_type: Mapped[int] = mapped_column(Integer)
    parent_external_key: Mapped[str | None] = mapped_column(String(200), nullable=True)


class CanonicalInventoryBalance(CanonicalSourceMixin, Base):
    __tablename__ = "canonical_inventory_balances"
    __table_args__ = (UniqueConstraint("external_system_id", "resource_key", "external_key"),)
    warehouse_key: Mapped[str] = mapped_column(String(160), index=True)
    product_key: Mapped[str] = mapped_column(String(160), index=True)
    sku: Mapped[str] = mapped_column(String(160), index=True)
    store_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    total: Mapped[int] = mapped_column(BigInteger)
    available: Mapped[int] = mapped_column(BigInteger)
    defective: Mapped[int] = mapped_column(BigInteger)
    inspecting: Mapped[int] = mapped_column(BigInteger)
    reserved: Mapped[int] = mapped_column(BigInteger)
    in_transit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class CanonicalOperationalFact(CanonicalSourceMixin, Base):
    __tablename__ = "canonical_operational_facts"
    __table_args__ = (UniqueConstraint("external_system_id", "resource_key", "external_key"),)
    fact_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(80), index=True)
    store_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    warehouse_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    product_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    source_local_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    business_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(38, 12), nullable=True)
    attributes: Mapped[dict[str, object]] = mapped_column(JSON)
    quality_flags: Mapped[list[str]] = mapped_column(JSON)


class StagingPageResult(Base):
    __tablename__ = "staging_page_results"
    raw_manifest_id: Mapped[str] = mapped_column(
        ForeignKey("raw_page_manifests.id"), primary_key=True
    )
    accepted: Mapped[int] = mapped_column(Integer)
    rejected: Mapped[int] = mapped_column(Integer)
    unassigned: Mapped[int] = mapped_column(Integer)
    stale: Mapped[int] = mapped_column(Integer)
    mapping_version: Mapped[str] = mapped_column(String(32))


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    source_system_id: Mapped[str | None] = mapped_column(
        ForeignKey("external_systems.id"), nullable=True, index=True
    )
    sync_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("sync_runs.id"), nullable=True, index=True
    )
    metric_key: Mapped[str] = mapped_column(String(100), index=True)
    label: Mapped[str] = mapped_column(String(160))
    scope_key: Mapped[str] = mapped_column(String(160), default="enterprise")
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    change_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CommerceOrderFact(Base):
    __tablename__ = "commerce_order_facts"
    __table_args__ = (UniqueConstraint("enterprise_id", "order_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    order_key: Mapped[str] = mapped_column(String(160), index=True)
    store_key: Mapped[str] = mapped_column(String(160), index=True)
    customer_key: Mapped[str] = mapped_column(String(160), index=True)
    channel: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), index=True)
    business_date: Mapped[date] = mapped_column(Date, index=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_amount_fen: Mapped[int] = mapped_column(BigInteger)
    item_amount_fen: Mapped[int] = mapped_column(BigInteger)
    discount_amount_fen: Mapped[int] = mapped_column(BigInteger)
    freight_amount_fen: Mapped[int] = mapped_column(BigInteger)
    cost_amount_fen: Mapped[int] = mapped_column(BigInteger)
    item_count: Mapped[int] = mapped_column(Integer)
    province: Mapped[str] = mapped_column(String(80))
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    original_paid_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_paid_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange_rate_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CommerceOrderLineFact(Base):
    __tablename__ = "commerce_order_line_facts"
    __table_args__ = (UniqueConstraint("enterprise_id", "line_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("commerce_order_facts.id", ondelete="CASCADE"), index=True
    )
    line_key: Mapped[str] = mapped_column(String(160), index=True)
    order_key: Mapped[str] = mapped_column(String(160), index=True)
    product_key: Mapped[str] = mapped_column(String(160), index=True)
    sku_key: Mapped[str] = mapped_column(String(160), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    original_refund_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_refund_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange_rate_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit_price_fen: Mapped[int] = mapped_column(BigInteger)
    paid_amount_fen: Mapped[int] = mapped_column(BigInteger)
    cost_amount_fen: Mapped[int] = mapped_column(BigInteger)
    refund_quantity: Mapped[int] = mapped_column(Integer)
    refund_amount_fen: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CommerceRefundFact(Base):
    __tablename__ = "commerce_refund_facts"
    __table_args__ = (UniqueConstraint("enterprise_id", "refund_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    refund_key: Mapped[str] = mapped_column(String(160), index=True)
    order_key: Mapped[str] = mapped_column(String(160), index=True)
    line_key: Mapped[str] = mapped_column(String(160))
    store_key: Mapped[str] = mapped_column(String(160), index=True)
    customer_key: Mapped[str] = mapped_column(String(160))
    sku_key: Mapped[str] = mapped_column(String(160), index=True)
    reason_category: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refund_amount_fen: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CommerceInventorySnapshotFact(Base):
    __tablename__ = "commerce_inventory_snapshot_facts"
    __table_args__ = (UniqueConstraint("enterprise_id", "snapshot_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    snapshot_key: Mapped[str] = mapped_column(String(160), index=True)
    warehouse_key: Mapped[str] = mapped_column(String(160), index=True)
    product_key: Mapped[str] = mapped_column(String(160), index=True)
    sku_key: Mapped[str] = mapped_column(String(160), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    available_quantity: Mapped[int] = mapped_column(Integer)
    reserved_quantity: Mapped[int] = mapped_column(Integer)
    in_transit_quantity: Mapped[int] = mapped_column(Integer)
    safety_quantity: Mapped[int] = mapped_column(Integer)
    inventory_cost_fen: Mapped[int] = mapped_column(BigInteger)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    original_inventory_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_inventory_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange_rate_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    days_cover: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CommerceAdPerformanceFact(Base):
    __tablename__ = "commerce_ad_performance_facts"
    __table_args__ = (UniqueConstraint("enterprise_id", "performance_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    performance_key: Mapped[str] = mapped_column(String(160), index=True)
    campaign_key: Mapped[str] = mapped_column(String(160), index=True)
    store_key: Mapped[str] = mapped_column(String(160), index=True)
    product_key: Mapped[str] = mapped_column(String(160), index=True)
    channel: Mapped[str] = mapped_column(String(80))
    business_date: Mapped[date] = mapped_column(Date, index=True)
    impressions: Mapped[int] = mapped_column(BigInteger)
    clicks: Mapped[int] = mapped_column(BigInteger)
    spend_fen: Mapped[int] = mapped_column(BigInteger)
    attributed_order_count: Mapped[int] = mapped_column(Integer)
    attributed_revenue_fen: Mapped[int] = mapped_column(BigInteger)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    original_spend: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    base_spend: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange_rate_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CustomerProfile(Base):
    __tablename__ = "customer_profiles"
    __table_args__ = (UniqueConstraint("enterprise_id", "customer_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    customer_key: Mapped[str] = mapped_column(String(160), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    home_store_key: Mapped[str] = mapped_column(String(160), index=True)
    member_level: Mapped[str] = mapped_column(String(48), index=True)
    lifecycle_stage: Mapped[str] = mapped_column(String(48), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    province: Mapped[str] = mapped_column(String(80), index=True)
    acquisition_channel: Mapped[str] = mapped_column(String(80), index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    member_points: Mapped[int] = mapped_column(Integer)
    growth_value: Mapped[int] = mapped_column(Integer)
    churn_risk_score: Mapped[float] = mapped_column(Float, index=True)
    preferred_category: Mapped[str] = mapped_column(String(120), index=True)
    consent_status: Mapped[str] = mapped_column(String(32), index=True)
    tags: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CustomerTouchpointFact(Base):
    __tablename__ = "customer_touchpoint_facts"
    __table_args__ = (UniqueConstraint("enterprise_id", "touchpoint_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    sync_run_id: Mapped[str] = mapped_column(ForeignKey("sync_runs.id"), index=True)
    touchpoint_key: Mapped[str] = mapped_column(String(160), index=True)
    customer_key: Mapped[str] = mapped_column(String(160), index=True)
    store_key: Mapped[str] = mapped_column(String(160), index=True)
    touchpoint_type: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(80), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    campaign_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    value_fen: Mapped[int] = mapped_column(BigInteger)
    properties: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MetricDefinition(Base):
    __tablename__ = "metric_definitions"
    __table_args__ = (UniqueConstraint("enterprise_id", "metric_key", "version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    source_system_id: Mapped[str | None] = mapped_column(
        ForeignKey("external_systems.id"), nullable=True, index=True
    )
    metric_key: Mapped[str] = mapped_column(String(100), index=True)
    label: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(500))
    formula_expression: Mapped[str] = mapped_column(String(1000))
    unit: Mapped[str] = mapped_column(String(32))
    dimensions: Mapped[list[str]] = mapped_column(JSON)
    owner: Mapped[str] = mapped_column(String(160))
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DataQualityRule(Base):
    __tablename__ = "data_quality_rules"
    __table_args__ = (UniqueConstraint("enterprise_id", "rule_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    rule_key: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(48), index=True)
    asset_type: Mapped[str] = mapped_column(String(48))
    asset_key: Mapped[str] = mapped_column(String(160))
    expectation: Mapped[str] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DataQualityResult(Base):
    __tablename__ = "data_quality_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("data_quality_rules.id", ondelete="CASCADE"), index=True
    )
    sync_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("sync_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    observed_value: Mapped[str] = mapped_column(String(300))
    affected_records: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    external_system_id: Mapped[str] = mapped_column(ForeignKey("external_systems.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    scenario: Mapped[str] = mapped_column(String(32))
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volume_profile: Mapped[str] = mapped_column(String(32), default="standard")
    records_read: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_run_id: Mapped[str | None] = mapped_column(ForeignKey("sync_runs.id"), nullable=True)
    command_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    scope_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    selected_enterprise_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    business_unit_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    store_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    warehouse_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


class TwinNode(Base):
    __tablename__ = "twin_nodes"
    __table_args__ = (UniqueConstraint("enterprise_id", "node_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    node_key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(160))
    node_type: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(32))
    health: Mapped[float] = mapped_column(Float)
    position_x: Mapped[float] = mapped_column(Float)
    position_y: Mapped[float] = mapped_column(Float)
    position_z: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String(300))


class TwinEdge(Base):
    __tablename__ = "twin_edges"
    __table_args__ = (UniqueConstraint("enterprise_id", "edge_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    edge_key: Mapped[str] = mapped_column(String(120))
    source_key: Mapped[str] = mapped_column(String(100))
    target_key: Mapped[str] = mapped_column(String(100))
    flow_type: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(32))
    traffic: Mapped[float] = mapped_column(Float)


class PlatformEvent(Base):
    __tablename__ = "platform_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(String(500))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TwinScene(Base):
    __tablename__ = "twin_scenes"
    __table_args__ = (UniqueConstraint("enterprise_id", "scene_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    scene_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(160))
    version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(String(500))
    parent_scene_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scene_level: Mapped[str] = mapped_column(String(32), default="campus")
    entry_space_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    asset_bundle_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    camera_preset: Mapped[dict[str, object]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TwinSpace(Base):
    __tablename__ = "twin_spaces"
    __table_args__ = (UniqueConstraint("scene_id", "space_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("twin_scenes.id"), index=True)
    space_key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(160))
    space_type: Mapped[str] = mapped_column(String(48))
    parent_space_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    health: Mapped[float] = mapped_column(Float)
    alert_level: Mapped[str] = mapped_column(String(32))
    metric_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[list[float]] = mapped_column(JSON)
    size: Mapped[list[float]] = mapped_column(JSON)
    description: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer)


class TwinActor(Base):
    __tablename__ = "twin_actors"
    __table_args__ = (UniqueConstraint("enterprise_id", "actor_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    actor_key: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(160))
    role_title: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32))
    home_space_key: Mapped[str] = mapped_column(String(100))
    current_space_key: Mapped[str] = mapped_column(String(100))
    avatar_style: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(16))
    position: Mapped[list[float]] = mapped_column(JSON)
    capabilities: Mapped[list[str]] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer)


class TwinRoute(Base):
    __tablename__ = "twin_routes"
    __table_args__ = (UniqueConstraint("scene_id", "route_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("twin_scenes.id"), index=True)
    route_key: Mapped[str] = mapped_column(String(100))
    source_space_key: Mapped[str] = mapped_column(String(100))
    target_space_key: Mapped[str] = mapped_column(String(100))
    route_type: Mapped[str] = mapped_column(String(48))
    path: Mapped[list[list[float]]] = mapped_column(JSON)


class TwinMeeting(Base):
    __tablename__ = "twin_meetings"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "meeting_key"),
        UniqueConstraint("enterprise_id", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("twin_scenes.id"), index=True)
    meeting_key: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(240))
    topic: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), index=True)
    protocol_status: Mapped[str] = mapped_column(String(32), index=True, default="draft")
    template_key: Mapped[str] = mapped_column(String(100), default="budget-inventory-review")
    initiated_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    actor_snapshot: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True, default="enterprise")
    scope_key: Mapped[str] = mapped_column(String(160), index=True, default="enterprise")
    decision_owner: Mapped[str] = mapped_column(String(160), default="CEO")
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    success_metric: Mapped[str] = mapped_column(String(500), default="等待定义")
    evidence_snapshot: Mapped[str] = mapped_column(String(120))
    decision: Mapped[str] = mapped_column(String(1000))
    room_space_key: Mapped[str] = mapped_column(String(100))
    next_transition_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TwinMeetingParticipant(Base):
    __tablename__ = "twin_meeting_participants"
    __table_args__ = (UniqueConstraint("meeting_id", "actor_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("twin_meetings.id"), index=True)
    actor_key: Mapped[str] = mapped_column(String(100))
    seat_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[str] = mapped_column(String(160))
    finding: Mapped[str] = mapped_column(String(800))
    status: Mapped[str] = mapped_column(String(32))
    speaking_order: Mapped[int] = mapped_column(Integer)


class TwinMeetingSeat(Base):
    __tablename__ = "twin_meeting_seats"
    __table_args__ = (UniqueConstraint("scene_id", "seat_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("twin_scenes.id"), index=True)
    seat_key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(160))
    layout_key: Mapped[str] = mapped_column(String(64))
    position: Mapped[list[float]] = mapped_column(JSON)
    rotation_y: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32))
    sort_order: Mapped[int] = mapped_column(Integer)


class TwinInteractionProfile(Base):
    __tablename__ = "twin_interaction_profiles"
    __table_args__ = (UniqueConstraint("enterprise_id", "entity_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    entity_key: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(48))
    detail_route: Mapped[str | None] = mapped_column(String(300), nullable=True)
    enter_space_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actions: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer)


class TwinHotspot(Base):
    __tablename__ = "twin_hotspots"
    __table_args__ = (UniqueConstraint("scene_id", "hotspot_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("twin_scenes.id"), index=True)
    hotspot_key: Mapped[str] = mapped_column(String(120))
    label: Mapped[str] = mapped_column(String(200))
    hotspot_type: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(32))
    business_ref: Mapped[str] = mapped_column(String(200))
    metric_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[list[float]] = mapped_column(JSON)
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer)


class TwinDataLayer(Base):
    __tablename__ = "twin_data_layers"
    __table_args__ = (UniqueConstraint("scene_id", "layer_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("twin_scenes.id"), index=True)
    layer_key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(48))
    enabled_default: Mapped[bool] = mapped_column(default=True)
    style: Mapped[dict[str, object]] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("enterprise_id", "document_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    document_key: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(240))
    document_type: Mapped[str] = mapped_column(String(48))
    knowledge_space: Mapped[str] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(48))
    source_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    owner: Mapped[str] = mapped_column(String(160))
    tags: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_label"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(40))
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    effective_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    change_summary: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("version_id", "chunk_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"), index=True
    )
    chunk_key: Mapped[str] = mapped_column(String(160))
    sequence: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(240))
    content: Mapped[str] = mapped_column(Text)
    locator: Mapped[str] = mapped_column(String(300))
    token_estimate: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON)
    index_status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KnowledgeIngestionRun(Base):
    __tablename__ = "knowledge_ingestion_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    version_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    source_filename: Mapped[str] = mapped_column(String(260))
    source_type: Mapped[str] = mapped_column(String(48))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    parser_provider: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KnowledgeLifecycleEvent(Base):
    __tablename__ = "knowledge_lifecycle_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"), index=True
    )
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(1000))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RoleTemplate(Base):
    __tablename__ = "role_templates"
    __table_args__ = (UniqueConstraint("enterprise_id", "template_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    template_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RoleTemplateVersion(Base):
    __tablename__ = "role_template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("role_templates.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    role_title: Mapped[str] = mapped_column(String(160))
    responsibilities: Mapped[list[str]] = mapped_column(JSON)
    capability_boundaries: Mapped[list[str]] = mapped_column(JSON)
    default_voice_guide: Mapped[str] = mapped_column(Text)
    default_reasoning_guide: Mapped[str] = mapped_column(Text)
    default_answer_policy: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[str] = mapped_column(String(1000))
    created_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoleTwinProfile(Base):
    __tablename__ = "role_twin_profiles"
    __table_args__ = (UniqueConstraint("enterprise_id", "twin_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    role_template_id: Mapped[str | None] = mapped_column(
        ForeignKey("role_templates.id"), nullable=True, index=True
    )
    owner_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    twin_key: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(160))
    role_title: Mapped[str] = mapped_column(String(160))
    voice_guide: Mapped[str] = mapped_column(Text)
    reasoning_guide: Mapped[str] = mapped_column(Text)
    answer_policy: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RoleTwinVersion(Base):
    __tablename__ = "role_twin_versions"
    __table_args__ = (UniqueConstraint("twin_profile_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    twin_profile_id: Mapped[str] = mapped_column(
        ForeignKey("role_twin_profiles.id", ondelete="CASCADE"), index=True
    )
    template_version_id: Mapped[str] = mapped_column(
        ForeignKey("role_template_versions.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    voice_guide: Mapped[str] = mapped_column(Text)
    reasoning_guide: Mapped[str] = mapped_column(Text)
    answer_policy: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    capabilities: Mapped[list[str]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(String(1000))
    created_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoleConfigurationEvent(Base):
    __tablename__ = "role_configuration_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    configuration_type: Mapped[str] = mapped_column(String(32), index=True)
    configuration_key: Mapped[str] = mapped_column(String(100), index=True)
    version_id: Mapped[str] = mapped_column(String(64), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    reason: Mapped[str] = mapped_column(String(1000))
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AgentSkill(Base):
    __tablename__ = "agent_skills"
    __table_args__ = (UniqueConstraint("enterprise_id", "skill_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    skill_key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(32), index=True)
    current_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentSkillVersion(Base):
    __tablename__ = "agent_skill_versions"
    __table_args__ = (UniqueConstraint("skill_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("agent_skills.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    instructions: Mapped[str] = mapped_column(Text)
    tool_keys: Mapped[list[str]] = mapped_column(JSON)
    input_schema: Mapped[dict[str, object]] = mapped_column(JSON)
    output_schema: Mapped[dict[str, object]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(String(1000))
    created_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentSkillEvent(Base):
    __tablename__ = "agent_skill_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("agent_skills.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("agent_skill_versions.id", ondelete="CASCADE"), index=True
    )
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    reason: Mapped[str] = mapped_column(String(1000))
    request_id: Mapped[str] = mapped_column(String(96))
    run_id: Mapped[str] = mapped_column(String(96))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    actor_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    twin_profile_id: Mapped[str] = mapped_column(ForeignKey("role_twin_profiles.id"), index=True)
    role_twin_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("role_twin_versions.id"), nullable=True, index=True
    )
    meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("twin_meetings.id"), nullable=True, index=True
    )
    run_type: Mapped[str] = mapped_column(String(32), index=True, default="answer")
    phase: Mapped[str | None] = mapped_column(String(48), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    answer_payload: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    fallback_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AgentRuntimeSession(Base):
    __tablename__ = "agent_runtime_sessions"
    __table_args__ = (UniqueConstraint("agent_run_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    runtime_key: Mapped[str] = mapped_column(String(64), index=True)
    runtime_thread_id: Mapped[str] = mapped_column(String(160), index=True)
    runtime_session_id: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True
    )
    runtime_spec: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    mcp_gateway_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("mcp_gateway_sessions.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    last_event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentRuntimeTurn(Base):
    __tablename__ = "agent_runtime_turns"
    __table_args__ = (
        UniqueConstraint("runtime_session_id", "turn_number"),
        UniqueConstraint("runtime_session_id", "runtime_turn_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    runtime_session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runtime_sessions.id", ondelete="CASCADE"), index=True
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    mcp_gateway_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("mcp_gateway_sessions.id"), nullable=True, index=True
    )
    runtime_turn_id: Mapped[str] = mapped_column(String(160), index=True)
    turn_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentRuntimeEventRecord(Base):
    __tablename__ = "agent_runtime_events"
    __table_args__ = (UniqueConstraint("runtime_session_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    runtime_session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runtime_sessions.id", ondelete="CASCADE"), index=True
    )
    runtime_turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runtime_turns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    runtime_sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    event_payload: Mapped[dict[str, object]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AgentRuntimeApproval(Base):
    __tablename__ = "agent_runtime_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    runtime_session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runtime_sessions.id", ondelete="CASCADE"), index=True
    )
    runtime_turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    request_method: Mapped[str] = mapped_column(String(120))
    item_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    skill_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    skill_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_keys: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True
    )
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)


class MeetingRuntimeRun(Base):
    __tablename__ = "meeting_runtime_runs"
    __table_args__ = (
        UniqueConstraint(
            "meeting_id",
            "participant_id",
            "agent_run_id",
            name="uq_meeting_runtime_runs_meeting_participant_agent_run",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("twin_meetings.id", ondelete="CASCADE"), index=True
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("twin_meeting_participants.id", ondelete="CASCADE"), index=True
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    runtime_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runtime_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_snapshots.id"), index=True
    )
    skill_key: Mapped[str] = mapped_column(String(100))
    skill_version: Mapped[int] = mapped_column(Integer)
    tool_keys: Mapped[list[str]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIProviderProbeRun(Base):
    __tablename__ = "ai_provider_probe_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(120), index=True)
    protocol: Mapped[str] = mapped_column(String(64))
    structured_output_supported: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(32), index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AgentRuntimeProbeRun(Base):
    __tablename__ = "agent_runtime_probe_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    runtime_key: Mapped[str] = mapped_column(String(64), index=True)
    protocol: Mapped[str] = mapped_column(String(64))
    command_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    initialized: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(32), index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AgentRunEvidence(Base):
    __tablename__ = "agent_run_evidence"
    __table_args__ = (UniqueConstraint("run_id", "rank"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("knowledge_chunks.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    excerpt: Mapped[str] = mapped_column(Text)
    citation_label: Mapped[str] = mapped_column(String(400))


class AgentRunContextItem(Base):
    __tablename__ = "agent_run_context_items"
    __table_args__ = (UniqueConstraint("run_id", "item_type", "rank"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    item_type: Mapped[str] = mapped_column(String(48), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    version_ref: Mapped[str] = mapped_column(String(120))
    rank: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    excerpt: Mapped[str] = mapped_column(Text)
    citation_label: Mapped[str] = mapped_column(String(400))


class HumanHandoffCase(Base):
    __tablename__ = "human_handoff_cases"
    __table_args__ = (UniqueConstraint("enterprise_id", "agent_run_id", "opened_by_principal_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    opened_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    assigned_to_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(48), index=True)
    subject: Mapped[str] = mapped_column(String(240))
    resolution_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class AgentFeedbackEvent(Base):
    __tablename__ = "agent_feedback_events"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    handoff_case_id: Mapped[str | None] = mapped_column(
        ForeignKey("human_handoff_cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    feedback_kind: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RoleTwinTestCase(Base):
    __tablename__ = "role_twin_test_cases"
    __table_args__ = (UniqueConstraint("enterprise_id", "case_key", "version_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    target_twin_profile_id: Mapped[str] = mapped_column(
        ForeignKey("role_twin_profiles.id"), index=True
    )
    case_key: Mapped[str] = mapped_column(String(120), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(48), index=True)
    risk_level: Mapped[str] = mapped_column(String(32), index=True)
    question: Mapped[str] = mapped_column(Text)
    expected_behaviors: Mapped[list[str]] = mapped_column(JSON)
    expected_evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    created_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RoleTwinTestRun(Base):
    __tablename__ = "role_twin_test_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("role_twin_test_cases.id"), index=True)
    twin_profile_id: Mapped[str] = mapped_column(ForeignKey("role_twin_profiles.id"), index=True)
    role_twin_version_id: Mapped[str] = mapped_column(
        ForeignKey("role_twin_versions.id"), index=True
    )
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), unique=True, index=True
    )
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RoleTwinTestReview(Base):
    __tablename__ = "role_twin_test_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    test_run_id: Mapped[str] = mapped_column(
        ForeignKey("role_twin_test_runs.id", ondelete="CASCADE"), index=True
    )
    reviewer_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    evidence_grounding: Mapped[int] = mapped_column(Integer)
    boundary_adherence: Mapped[int] = mapped_column(Integer)
    voice_match: Mapped[int] = mapped_column(Integer)
    usefulness: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EvaluationSuite(Base):
    __tablename__ = "evaluation_suites"
    __table_args__ = (UniqueConstraint("enterprise_id", "suite_key", "version_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    suite_key: Mapped[str] = mapped_column(String(120), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    domain: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (UniqueConstraint("suite_id", "case_key", "version_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    suite_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_suites.id", ondelete="CASCADE"), index=True
    )
    case_key: Mapped[str] = mapped_column(String(120), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    domain: Mapped[str] = mapped_column(String(48), index=True)
    risk_level: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(200))
    actor_login_name: Mapped[str] = mapped_column(String(100), index=True)
    target_twin_key: Mapped[str] = mapped_column(String(100), index=True)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSON)
    expectations: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (UniqueConstraint("enterprise_id", "client_request_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    suite_id: Mapped[str] = mapped_column(ForeignKey("evaluation_suites.id"), index=True)
    initiated_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    baseline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluation_runs.id"), nullable=True, index=True
    )
    client_request_key: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    code_version: Mapped[str] = mapped_column(String(64))
    config_version: Mapped[str] = mapped_column(String(64))
    total_count: Mapped[int] = mapped_column(Integer)
    passed_count: Mapped[int] = mapped_column(Integer)
    failed_count: Mapped[int] = mapped_column(Integer)
    review_required_count: Mapped[int] = mapped_column(Integer)
    error_count: Mapped[int] = mapped_column(Integer)
    pass_rate: Mapped[float] = mapped_column(Float)
    duration_ms: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class EvaluationRunItem(Base):
    __tablename__ = "evaluation_run_items"
    __table_args__ = (UniqueConstraint("evaluation_run_id", "evaluation_case_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    evaluation_case_id: Mapped[str] = mapped_column(ForeignKey("evaluation_cases.id"), index=True)
    actor_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True, index=True
    )
    case_key: Mapped[str] = mapped_column(String(120), index=True)
    case_version_number: Mapped[int] = mapped_column(Integer)
    case_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    checks: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    error_types: Mapped[list[str]] = mapped_column(JSON)
    observed_error_code: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EvaluationCandidate(Base):
    __tablename__ = "evaluation_candidates"
    __table_args__ = (UniqueConstraint("source_feedback_event_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    source_handoff_case_id: Mapped[str] = mapped_column(
        ForeignKey("human_handoff_cases.id"), index=True
    )
    source_feedback_event_id: Mapped[str] = mapped_column(
        ForeignKey("agent_feedback_events.id"), unique=True, index=True
    )
    source_agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    proposed_case_key: Mapped[str] = mapped_column(String(120), index=True)
    proposed_title: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(48), index=True)
    risk_level: Mapped[str] = mapped_column(String(32), index=True)
    actor_login_name: Mapped[str] = mapped_column(String(100), index=True)
    target_twin_key: Mapped[str] = mapped_column(String(100), index=True)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSON)
    expectations: Mapped[dict[str, object]] = mapped_column(JSON)
    resolution_summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    proposed_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    reviewed_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    accepted_case_id: Mapped[str | None] = mapped_column(
        ForeignKey("evaluation_cases.id"), nullable=True, index=True
    )
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_idempotency_key: Mapped[str | None] = mapped_column(
        String(160), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class EvidenceSnapshot(Base):
    __tablename__ = "evidence_snapshots"
    __table_args__ = (UniqueConstraint("enterprise_id", "snapshot_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    snapshot_key: Mapped[str] = mapped_column(String(120))
    purpose: Mapped[str] = mapped_column(String(64), index=True)
    query: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    item_count: Mapped[int] = mapped_column(Integer)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceSnapshotItem(Base):
    __tablename__ = "evidence_snapshot_items"
    __table_args__ = (UniqueConstraint("snapshot_id", "rank"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_snapshots.id", ondelete="CASCADE"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(48), index=True)
    item_key: Mapped[str] = mapped_column(String(160))
    version_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    label: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    rank: Mapped[int] = mapped_column(Integer)


class BusinessAnalysisRun(Base):
    __tablename__ = "business_analysis_runs"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    analysis_type: Mapped[str] = mapped_column(String(48), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_key: Mapped[str] = mapped_column(String(160), index=True)
    scope_label: Mapped[str] = mapped_column(String(200))
    window_days: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    risk_level: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100))
    execution_mode: Mapped[str] = mapped_column(String(32), index=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evidence_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_snapshots.id"), index=True
    )
    result: Mapped[dict[str, object]] = mapped_column(JSON)
    initiated_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CustomerOperationRun(Base):
    __tablename__ = "customer_operation_runs"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    customer_key: Mapped[str] = mapped_column(String(160), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_key: Mapped[str] = mapped_column(String(160), index=True)
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    risk_level: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100))
    execution_mode: Mapped[str] = mapped_column(String(32), index=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evidence_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_snapshots.id"), index=True
    )
    result: Mapped[dict[str, object]] = mapped_column(JSON)
    initiated_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    duration_ms: Mapped[int] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class BusinessBrief(Base):
    __tablename__ = "business_briefs"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "brief_key", "version_number"),
        UniqueConstraint("enterprise_id", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    brief_key: Mapped[str] = mapped_column(String(160), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    brief_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_key: Mapped[str] = mapped_column(String(160), index=True)
    scope_label: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32), index=True)
    source_analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("business_analysis_runs.id"), index=True
    )
    evidence_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_snapshots.id"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(100))
    execution_mode: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[dict[str, object]] = mapped_column(JSON)
    created_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class StoreReviewPlan(Base):
    __tablename__ = "store_review_plans"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "plan_key"),
        UniqueConstraint("enterprise_id", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    plan_key: Mapped[str] = mapped_column(String(160), index=True)
    name: Mapped[str] = mapped_column(String(120))
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_key: Mapped[str] = mapped_column(String(160), index=True)
    scope_label: Mapped[str] = mapped_column(String(200))
    window_days: Mapped[int] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(64))
    local_time: Mapped[str] = mapped_column(String(5))
    weekdays: Mapped[list[int]] = mapped_column(JSON)
    auto_propose_min_priority: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), index=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_enqueued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    last_action: Mapped[str | None] = mapped_column(String(24), nullable=True)
    last_action_idempotency_key: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class StoreReviewScheduleRun(Base):
    __tablename__ = "store_review_schedule_runs"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "idempotency_key"),
        UniqueConstraint("background_job_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("store_review_plans.id", ondelete="CASCADE"), index=True
    )
    business_date: Mapped[date] = mapped_column(Date, index=True)
    trigger_type: Mapped[str] = mapped_column(String(24), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    background_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_analysis_runs.id"), nullable=True, index=True
    )
    brief_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_briefs.id"), nullable=True, index=True
    )
    proposal_count: Mapped[int] = mapped_column(Integer)
    execution_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class MemoryCandidate(Base):
    __tablename__ = "memory_candidates"
    __table_args__ = (UniqueConstraint("enterprise_id", "candidate_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    twin_profile_id: Mapped[str] = mapped_column(ForeignKey("role_twin_profiles.id"), index=True)
    candidate_key: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(48))
    content: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(48))
    source_ref: Mapped[str] = mapped_column(String(300))
    normalized_hash: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float)
    conflict_status: Mapped[str] = mapped_column(String(32))
    conflict_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_import_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), index=True)
    reviewer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatImportRun(Base):
    __tablename__ = "chat_import_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    twin_profile_id: Mapped[str] = mapped_column(ForeignKey("role_twin_profiles.id"), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    source_filename: Mapped[str] = mapped_column(String(260))
    source_channel: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    message_count: Mapped[int] = mapped_column(Integer)
    topic_count: Mapped[int] = mapped_column(Integer)
    candidate_count: Mapped[int] = mapped_column(Integer)
    participants: Mapped[list[str]] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warnings: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("import_run_id", "message_key"),
        UniqueConstraint("import_run_id", "ordinal"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    import_run_id: Mapped[str] = mapped_column(
        ForeignKey("chat_import_runs.id", ondelete="CASCADE"), index=True
    )
    message_key: Mapped[str] = mapped_column(String(120))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sender_name: Mapped[str] = mapped_column(String(160), index=True)
    sender_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    topic_key: Mapped[str] = mapped_column(String(120), index=True)
    content: Mapped[str] = mapped_column(Text)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON)
    ordinal: Mapped[int] = mapped_column(Integer)


class ApprovedMemory(Base):
    __tablename__ = "approved_memories"
    __table_args__ = (UniqueConstraint("enterprise_id", "memory_key", "version_number"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    twin_profile_id: Mapped[str] = mapped_column(ForeignKey("role_twin_profiles.id"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("memory_candidates.id"), index=True)
    memory_key: Mapped[str] = mapped_column(String(120), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(48))
    content: Mapped[str] = mapped_column(Text)
    normalized_hash: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(48))
    source_ref: Mapped[str] = mapped_column(String(300))
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    approved_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MemoryProviderEvaluationRun(Base):
    __tablename__ = "memory_provider_evaluation_runs"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    evaluation_key: Mapped[str] = mapped_column(String(120), index=True)
    benchmark_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    provider_keys: Mapped[list[str]] = mapped_column(JSON)
    benchmark_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    memory_count: Mapped[int] = mapped_column(Integer)
    case_count: Mapped[int] = mapped_column(Integer)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MemoryProviderEvaluationResult(Base):
    __tablename__ = "memory_provider_evaluation_results"
    __table_args__ = (UniqueConstraint("evaluation_run_id", "provider_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("memory_provider_evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    provider_mode: Mapped[str] = mapped_column(String(48))
    protocol: Mapped[str] = mapped_column(String(80))
    endpoint_fingerprint: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(32), index=True)
    indexed_memory_count: Mapped[int] = mapped_column(Integer)
    query_count: Mapped[int] = mapped_column(Integer)
    hit_count: Mapped[int] = mapped_column(Integer)
    recall_at_k: Mapped[float] = mapped_column(Float)
    average_latency_ms: Mapped[int] = mapped_column(Integer)
    p95_latency_ms: Mapped[int] = mapped_column(Integer)
    result_items: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class KnowledgeProviderEvaluationRun(Base):
    __tablename__ = "knowledge_provider_evaluation_runs"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    evaluation_key: Mapped[str] = mapped_column(String(120), index=True)
    benchmark_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    provider_keys: Mapped[list[str]] = mapped_column(JSON)
    benchmark_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    document_count: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer)
    case_count: Mapped[int] = mapped_column(Integer)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class KnowledgeProviderEvaluationResult(Base):
    __tablename__ = "knowledge_provider_evaluation_results"
    __table_args__ = (UniqueConstraint("evaluation_run_id", "provider_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_provider_evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    provider_key: Mapped[str] = mapped_column(String(64), index=True)
    provider_mode: Mapped[str] = mapped_column(String(48))
    protocol: Mapped[str] = mapped_column(String(80))
    endpoint_fingerprint: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(32), index=True)
    indexed_document_count: Mapped[int] = mapped_column(Integer)
    indexed_chunk_count: Mapped[int] = mapped_column(Integer)
    query_count: Mapped[int] = mapped_column(Integer)
    hit_count: Mapped[int] = mapped_column(Integer)
    recall_at_k: Mapped[float] = mapped_column(Float)
    mean_reciprocal_rank: Mapped[float] = mapped_column(Float)
    average_latency_ms: Mapped[int] = mapped_column(Integer)
    p95_latency_ms: Mapped[int] = mapped_column(Integer)
    result_items: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MemoryReviewEvent(Base):
    __tablename__ = "memory_review_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("memory_candidates.id"), index=True)
    approved_memory_id: Mapped[str | None] = mapped_column(
        ForeignKey("approved_memories.id"), nullable=True, index=True
    )
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    from_status: Mapped[str] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(1000))
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class MeetingClaim(Base):
    __tablename__ = "meeting_claims"
    __table_args__ = (UniqueConstraint("meeting_id", "twin_profile_id", "phase"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("twin_meetings.id", ondelete="CASCADE"), index=True
    )
    twin_profile_id: Mapped[str] = mapped_column(ForeignKey("role_twin_profiles.id"), index=True)
    phase: Mapped[str] = mapped_column(String(48))
    stance: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    claims: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    risks: Mapped[list[str]] = mapped_column(JSON)
    unknowns: Mapped[list[str]] = mapped_column(JSON)
    recommendation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MeetingDeliberationTurn(Base):
    __tablename__ = "meeting_deliberation_turns"
    __table_args__ = (UniqueConstraint("meeting_id", "speaker_twin_profile_id", "phase"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("twin_meetings.id", ondelete="CASCADE"), index=True
    )
    speaker_twin_profile_id: Mapped[str] = mapped_column(
        ForeignKey("role_twin_profiles.id"), index=True
    )
    target_twin_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("role_twin_profiles.id"), nullable=True, index=True
    )
    phase: Mapped[str] = mapped_column(String(48), index=True)
    round_number: Mapped[int] = mapped_column(Integer)
    turn_type: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    new_evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    position_after: Mapped[str | None] = mapped_column(String(32), nullable=True)
    position_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DecisionPackage(Base):
    __tablename__ = "decision_packages"
    __table_args__ = (UniqueConstraint("meeting_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("twin_meetings.id", ondelete="CASCADE"), index=True
    )
    summary: Mapped[str] = mapped_column(Text)
    consensus: Mapped[list[str]] = mapped_column(JSON)
    disagreements: Mapped[list[str]] = mapped_column(JSON)
    risks: Mapped[list[str]] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(Text)
    actions: Mapped[list[dict[str, object]]] = mapped_column(JSON)
    confidence: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MeetingDecisionConfirmation(Base):
    __tablename__ = "meeting_decision_confirmations"
    __table_args__ = (UniqueConstraint("meeting_id"), UniqueConstraint("decision_package_id"))

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("twin_meetings.id", ondelete="CASCADE"), index=True
    )
    decision_package_id: Mapped[str] = mapped_column(
        ForeignKey("decision_packages.id", ondelete="CASCADE"), index=True
    )
    confirmed_by_actor_key: Mapped[str] = mapped_column(String(120), index=True)
    confirmed_by_name: Mapped[str] = mapped_column(String(160))
    actor_context: Mapped[dict[str, object]] = mapped_column(JSON)
    comment: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ActionProposal(Base):
    __tablename__ = "action_proposals"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "proposal_key"),
        UniqueConstraint("decision_package_id", "source_action_index"),
        UniqueConstraint("customer_operation_run_id", "source_action_index"),
        UniqueConstraint("business_analysis_run_id", "source_action_index"),
        UniqueConstraint("enterprise_id", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    proposal_key: Mapped[str] = mapped_column(String(160), index=True)
    source_type: Mapped[str] = mapped_column(String(48), index=True, default="meeting-decision")
    source_key: Mapped[str] = mapped_column(String(160), index=True)
    source_label: Mapped[str] = mapped_column(String(300))
    scope_type: Mapped[str] = mapped_column(String(32), index=True, default="object")
    scope_key: Mapped[str] = mapped_column(String(160), index=True)
    meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("twin_meetings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    decision_package_id: Mapped[str | None] = mapped_column(
        ForeignKey("decision_packages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_operation_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("customer_operation_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    business_analysis_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("business_analysis_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    evidence_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("evidence_snapshots.id"), nullable=True, index=True
    )
    source_action_index: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    owner: Mapped[str] = mapped_column(String(160))
    due_hint: Mapped[str] = mapped_column(String(300))
    kpi: Mapped[str] = mapped_column(Text)
    stop_condition: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    target_system: Mapped[str] = mapped_column(String(120))
    target_key: Mapped[str] = mapped_column(String(200))
    risk_level: Mapped[str] = mapped_column(String(16), index=True)
    action_level: Mapped[str] = mapped_column(String(16))
    parameters: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), index=True)
    requested_by_actor_key: Mapped[str] = mapped_column(String(120), index=True)
    requested_by_name: Mapped[str] = mapped_column(String(160))
    idempotency_key: Mapped[str] = mapped_column(String(200), index=True)
    approved_by_actor_key: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    approved_by_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActionApprovalEvent(Base):
    __tablename__ = "action_approval_events"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("action_proposals.id", ondelete="CASCADE"), index=True
    )
    actor_key: Mapped[str] = mapped_column(String(120), index=True)
    actor_name: Mapped[str] = mapped_column(String(160))
    decision: Mapped[str] = mapped_column(String(24), index=True)
    comment: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(200), index=True)
    actor_context: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ActionExecution(Base):
    __tablename__ = "action_executions"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "execution_key"),
        UniqueConstraint("proposal_id"),
        UniqueConstraint("enterprise_id", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    execution_key: Mapped[str] = mapped_column(String(160), index=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("action_proposals.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    external_write: Mapped[bool] = mapped_column(Boolean, default=False)
    actor_key: Mapped[str] = mapped_column(String(120))
    result: Mapped[dict[str, object]] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ActionWorkItem(Base):
    __tablename__ = "action_work_items"
    __table_args__ = (
        UniqueConstraint("enterprise_id", "work_key"),
        UniqueConstraint("proposal_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    work_key: Mapped[str] = mapped_column(String(200), index=True)
    proposal_id: Mapped[str] = mapped_column(
        ForeignKey("action_proposals.id", ondelete="CASCADE"), index=True
    )
    scope_type: Mapped[str] = mapped_column(String(32), index=True)
    scope_key: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    assignee_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    assignee_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    owner_role: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(300))
    due_hint: Mapped[str] = mapped_column(String(300))
    kpi: Mapped[str] = mapped_column(Text)
    stop_condition: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(24), index=True)
    version: Mapped[int] = mapped_column(Integer)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    blocker_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ActionWorkEvent(Base):
    __tablename__ = "action_work_events"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    work_item_id: Mapped[str] = mapped_column(
        ForeignKey("action_work_items.id", ondelete="CASCADE"), index=True
    )
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_name: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), index=True)
    comment: Mapped[str] = mapped_column(Text)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(200), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CustomerServiceConversation(Base):
    __tablename__ = "customer_service_conversations"
    __table_args__ = (UniqueConstraint("enterprise_id", "channel_key", "conversation_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    conversation_key: Mapped[str] = mapped_column(String(120), index=True)
    channel_key: Mapped[str] = mapped_column(String(64), index=True)
    external_conversation_id: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True
    )
    source_system_key: Mapped[str] = mapped_column(String(100), index=True)
    customer_key: Mapped[str] = mapped_column(String(160), index=True)
    customer_name: Mapped[str] = mapped_column(String(160))
    order_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    store_scope_key: Mapped[str] = mapped_column(String(160), index=True)
    topic: Mapped[str] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[str] = mapped_column(String(24), index=True)
    sentiment: Mapped[str] = mapped_column(String(24), index=True)
    risk_level: Mapped[str] = mapped_column(String(24), index=True)
    risk_reason: Mapped[str] = mapped_column(String(1000))
    assigned_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    first_response_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latest_sync_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CustomerServiceMessage(Base):
    __tablename__ = "customer_service_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "message_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("customer_service_conversations.id", ondelete="CASCADE"), index=True
    )
    message_key: Mapped[str] = mapped_column(String(120))
    sender_type: Mapped[str] = mapped_column(String(32), index=True)
    direction: Mapped[str] = mapped_column(String(16), index=True)
    sender_name: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(32), index=True)
    source_message_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CustomerServiceOrderContext(Base):
    __tablename__ = "customer_service_order_contexts"
    __table_args__ = (UniqueConstraint("conversation_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("customer_service_conversations.id", ondelete="CASCADE"), index=True
    )
    context_type: Mapped[str] = mapped_column(String(32), index=True)
    order_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    order_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paid_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16))
    product_summary: Mapped[str] = mapped_column(String(500))
    item_quantity: Mapped[int] = mapped_column(Integer)
    payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    logistics_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tracking_no: Mapped[str | None] = mapped_column(String(160), nullable=True)
    latest_logistics_event: Mapped[str | None] = mapped_column(Text, nullable=True)
    promised_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latest_logistics_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delayed_hours: Mapped[int] = mapped_column(Integer)
    aftersale_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_system_key: Mapped[str] = mapped_column(String(100), index=True)
    payload_version: Mapped[str] = mapped_column(String(32))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CustomerServiceReplyDraft(Base):
    __tablename__ = "customer_service_reply_drafts"
    __table_args__ = (
        UniqueConstraint("conversation_id", "version_number"),
        UniqueConstraint("enterprise_id", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("customer_service_conversations.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    body: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(24), index=True)
    risk_flags: Mapped[list[str]] = mapped_column(JSON)
    safe_to_send: Mapped[bool] = mapped_column(Boolean, index=True)
    suggested_action: Mapped[str] = mapped_column(String(32))
    evidence_refs: Mapped[list[str]] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    execution_mode: Mapped[str] = mapped_column(String(32), index=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    evidence_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_snapshots.id"), index=True
    )
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    role_twin_version_id: Mapped[str] = mapped_column(
        ForeignKey("role_twin_versions.id"), index=True
    )
    created_by_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    approved_by_principal_id: Mapped[str | None] = mapped_column(
        ForeignKey("principals.id"), nullable=True, index=True
    )
    approval_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class CustomerServiceEvent(Base):
    __tablename__ = "customer_service_events"
    __table_args__ = (UniqueConstraint("enterprise_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(ForeignKey("enterprises.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("customer_service_conversations.id", ondelete="CASCADE"), index=True
    )
    reply_draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("customer_service_reply_drafts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    actor_principal_id: Mapped[str] = mapped_column(ForeignKey("principals.id"), index=True)
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    details: Mapped[dict[str, object]] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(160), index=True)
    request_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(96), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
