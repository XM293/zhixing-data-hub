from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from zhixing_api.login_names import LoginName
from zhixing_api.models import ApiModel


class ActorScopeView(ApiModel):
    scope_type: str
    scope_ids: list[str]
    effect: Literal["allow", "deny"]


class CurrentActorView(ApiModel):
    principal_id: str
    principal_key: str
    account_id: str
    login_name: str
    display_name: str
    experience_role_key: str
    organization: str
    position: str
    access_role_keys: list[str]
    permissions: list[str]
    scopes: list[ActorScopeView]
    permission_set_version: str
    authentication_method: str
    group_id: str | None = None


class NavigationItemView(ApiModel):
    key: str
    label: str
    href: str
    required_permission: str | None = None


class NavigationSectionView(ApiModel):
    key: str
    label: str
    short_label: str
    href: str
    icon_key: str
    delivery_state: Literal["prototype", "implemented", "unavailable"]
    group_key: str = "platform"
    items: list[NavigationItemView]


class CurrentIdentityResponse(ApiModel):
    schema_version: Literal[1] = 1
    enterprise_id: str
    enterprise_name: str
    group_id: str | None = None
    actor: CurrentActorView
    navigation_sections: list[str]
    navigation: list[NavigationSectionView]
    resolved_at: datetime


class ScopeOptionView(ApiModel):
    key: str
    label: str
    scope_type: str
    selectable: bool = True
    enterprise_id: str | None = None
    business_unit_id: str | None = None


class ScopeOptionsResponse(ApiModel):
    schema_version: Literal[1] = 1
    group_id: str | None
    current_enterprise_id: str
    groups: list[ScopeOptionView] = Field(default_factory=list)
    enterprises: list[ScopeOptionView]
    business_units: list[ScopeOptionView]
    stores: list[ScopeOptionView]
    warehouses: list[ScopeOptionView]


class DevelopmentSessionRequest(ApiModel):
    login_name: LoginName

    @field_validator("login_name")
    @classmethod
    def normalize_login_name(cls, value: str) -> str:
        return value.strip().casefold()


class LocalLoginRequest(ApiModel):
    login_name: LoginName
    password: str = Field(min_length=12, max_length=256)

    @field_validator("login_name")
    @classmethod
    def normalize_login_name(cls, value: str) -> str:
        return value.strip().casefold()


class AuthSessionResponse(ApiModel):
    schema_version: Literal[1] = 1
    session_id: str
    authentication_method: str
    expires_at: datetime
    identity: CurrentIdentityResponse


class IdentityStats(ApiModel):
    active_users: int
    org_units: int
    positions: int
    access_roles: int
    permissions: int
    active_assignments: int
    authorization_decisions: int
    denied_decisions: int
    management_events: int


class IdentityScopeGrantInput(ApiModel):
    scope_type: Literal[
        "enterprise",
        "org_subtree",
        "store",
        "knowledge_space",
        "object",
        "self",
        "business_unit",
    ]
    scope_ids: list[str] = Field(min_length=1, max_length=100)
    effect: Literal["allow", "deny"] = "allow"

    @field_validator("scope_ids")
    @classmethod
    def normalize_scope_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized:
            raise ValueError("数据范围至少需要一个有效标识")
        if len(normalized) != len(set(normalized)):
            raise ValueError("同一数据范围不能包含重复标识")
        return normalized


class IdentityRoleAssignmentInput(ApiModel):
    role_key: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    scopes: list[IdentityScopeGrantInput] = Field(min_length=1, max_length=12)


class IdentityUserConfigurationBase(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    display_name: str = Field(min_length=2, max_length=160)
    email: str | None = Field(default=None, max_length=240)
    experience_role_key: str = Field(
        min_length=2,
        max_length=48,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    org_key: str = Field(min_length=1, max_length=120)
    position_key: str = Field(min_length=1, max_length=120)
    status: Literal["active", "suspended"] = "active"
    role_assignments: list[IdentityRoleAssignmentInput] = Field(min_length=1, max_length=8)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator(
        "client_request_key",
        "display_name",
        "experience_role_key",
        "org_key",
        "position_key",
        "reason",
    )
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = value.strip().casefold()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("邮箱格式无效")
        return normalized


class IdentityUserCreateRequest(IdentityUserConfigurationBase):
    login_name: LoginName
    initial_password: str | None = Field(default=None, min_length=12, max_length=256)

    @field_validator("login_name")
    @classmethod
    def normalize_login_name(cls, value: str) -> str:
        return value.strip().casefold()


class IdentityUserUpdateRequest(IdentityUserConfigurationBase):
    expected_version: int = Field(ge=1)


class IdentityScopeGrantView(ApiModel):
    scope_type: str
    scope_ids: list[str]
    effect: Literal["allow", "deny"]


class IdentityRoleAssignmentView(ApiModel):
    role_key: str
    role_name: str
    scopes: list[IdentityScopeGrantView]


class UserAccountView(ApiModel):
    account_id: str
    account_key: str
    login_name: str
    display_name: str
    email: str | None
    experience_role_key: str
    status: str
    authentication_source: str
    organization: str
    org_key: str
    position: str
    position_key: str
    access_roles: list[str]
    role_assignments: list[IdentityRoleAssignmentView]
    scope_labels: list[str]
    last_login_at: datetime | None
    version: int


class OrgUnitView(ApiModel):
    org_id: str
    org_key: str
    name: str
    unit_type: str
    parent_name: str | None
    status: str
    version: int
    position_count: int
    member_count: int


class PositionView(ApiModel):
    position_key: str
    name: str
    position_level: str
    organization: str
    org_key: str
    status: str
    version: int
    member_count: int


class AccessRoleView(ApiModel):
    role_key: str
    name: str
    description: str
    version: str
    revision: int
    status: str
    permission_count: int
    permissions: list[str]
    assignment_count: int
    scope_types: list[str]


class PermissionDefinitionView(ApiModel):
    permission_key: str
    label: str
    resource: str
    action: str
    risk_level: str
    status: str


class AuthorizationDecisionView(ApiModel):
    id: str
    request_id: str
    run_id: str
    actor_name: str
    permission_key: str
    resource_type: str
    resource_key: str
    decision: Literal["allow", "deny"]
    reason: str
    policy_version: str
    decided_at: datetime


class IdentityManagementEventView(ApiModel):
    id: str
    event_type: Literal["identity.user.created", "identity.user.configured"]
    actor_name: str
    target_name: str
    target_account_key: str
    changed_fields: list[str]
    reason: str
    request_id: str
    run_id: str
    occurred_at: datetime


class IdentityCatalogEventView(ApiModel):
    id: str
    event_type: str
    target_type: str
    target_key: str
    actor_name: str
    changed_fields: list[str]
    reason: str
    request_id: str
    run_id: str
    occurred_at: datetime


class IdentityUserMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    operation: Literal["created", "configured"]
    account: UserAccountView
    event_id: str
    replayed: bool


class IdentityAdminOverviewResponse(ApiModel):
    schema_version: Literal[1] = 1
    enterprise_id: str
    enterprise_name: str
    stats: IdentityStats
    users: list[UserAccountView]
    org_units: list[OrgUnitView]
    positions: list[PositionView]
    access_roles: list[AccessRoleView]
    permission_catalog: list[PermissionDefinitionView]
    recent_decisions: list[AuthorizationDecisionView] = Field(max_length=100)
    recent_management_events: list[IdentityManagementEventView] = Field(max_length=100)
    recent_catalog_events: list[IdentityCatalogEventView] = Field(max_length=100)
    generated_at: datetime


class IdentityCatalogMutationResponse(ApiModel):
    schema_version: Literal[1] = 1
    operation: Literal["created", "updated"]
    target_type: Literal["org_unit", "position", "access_role"]
    target_key: str
    event_id: str
    replayed: bool


class IdentityOrgUnitCreateRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    org_key: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=160)
    unit_type: str = Field(min_length=2, max_length=48)
    parent_org_key: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=3, max_length=500)


class IdentityOrgUnitUpdateRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=2, max_length=160)
    unit_type: str = Field(min_length=2, max_length=48)
    parent_org_key: str | None = Field(default=None, max_length=120)
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=3, max_length=500)


class IdentityPositionCreateRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    position_key: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=160)
    position_level: str = Field(min_length=2, max_length=48)
    org_key: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=3, max_length=500)


class IdentityPositionUpdateRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=2, max_length=160)
    position_level: str = Field(min_length=2, max_length=48)
    org_key: str = Field(min_length=1, max_length=120)
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=3, max_length=500)


class IdentityAccessRoleCreateRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    role_key: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=3, max_length=500)
    permissions: list[str] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=500)


class IdentityAccessRoleUpdateRequest(ApiModel):
    schema_version: Literal[1] = 1
    client_request_key: str = Field(min_length=8, max_length=160)
    expected_revision: int = Field(ge=1)
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=3, max_length=500)
    status: Literal["active", "suspended"]
    permissions: list[str] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=500)
