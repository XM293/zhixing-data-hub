export interface ActorScope {
  scope_type: string;
  scope_ids: string[];
  effect: "allow" | "deny";
}

export interface CurrentIdentity {
  schema_version: 1;
  enterprise_id: string;
  enterprise_name: string;
  group_id?: string | null;
  actor: {
    principal_id: string;
    principal_key: string;
    account_id: string;
    login_name: string;
    display_name: string;
    experience_role_key: string;
    organization: string;
    position: string;
    access_role_keys: string[];
    permissions: string[];
    scopes: ActorScope[];
    permission_set_version: string;
    authentication_method: string;
    group_id?: string | null;
  };
  navigation_sections: string[];
  navigation: Array<{
    key: string;
    label: string;
    short_label: string;
    href: string;
    icon_key: string;
    delivery_state: "prototype" | "implemented" | "unavailable";
    group_key?: string;
    items: Array<{
      key: string;
      label: string;
      href: string;
      required_permission: string | null;
    }>;
  }>;
  resolved_at: string;
}

export interface ScopeOptions {
  group_id: string | null;
  current_enterprise_id: string;
  groups?: Array<{ key: string; label: string; scope_type: string }>;
  enterprises: Array<{ key: string; label: string; scope_type: string }>;
  business_units: Array<{ key: string; label: string; scope_type: string; enterprise_id?: string; business_unit_id?: string }>;
  stores: Array<{ key: string; label: string; scope_type: string; enterprise_id?: string; business_unit_id?: string }>;
  warehouses: Array<{ key: string; label: string; scope_type: string; enterprise_id?: string; business_unit_id?: string }>;
}

export interface ScopeSelection {
  enterprise_id: string;
  scope_level: "group" | "enterprise" | "business_unit" | "store" | "warehouse";
  selected_enterprise_ids?: string[];
  business_unit_ids?: string[];
  store_ids?: string[];
  warehouse_ids?: string[];
}

export interface ScopeContext extends ScopeSelection {
  schema_version: 2;
  group_id: string | null;
  current_enterprise_id: string;
  selected_enterprise_ids: string[];
  business_unit_ids: string[];
  store_ids: string[];
  warehouse_ids: string[];
  base_currency: string | null;
  consolidation_profile_version: string | null;
  data_as_of: string | null;
  scope_version: string;
}

export interface AuthSessionResponse {
  schema_version: 1;
  session_id: string;
  authentication_method: string;
  expires_at: string;
  identity: CurrentIdentity;
}

export interface CenterCatalogItem {
  key: string;
  group_key: string;
  label: string;
  short_label: string;
  icon_key: string;
  href: string;
  delivery_state: "prototype" | "implemented" | "unavailable";
  required_permissions: string[];
  scope_level: string;
  scene_node_key: string | null;
}

export interface CenterCatalog {
  schema_version: 1;
  group_id: string | null;
  enterprise_id: string;
  groups: Array<{
    key: string;
    label: string;
    order: number;
    items: CenterCatalogItem[];
  }>;
  resolved_at: string;
}

export type IdentityScopeType = "enterprise" | "org_subtree" | "store" | "knowledge_space" | "object" | "self" | "business_unit";

export interface IdentityScopeGrant {
  scope_type: IdentityScopeType;
  scope_ids: string[];
  effect: "allow" | "deny";
}

export interface IdentityRoleAssignment {
  role_key: string;
  role_name: string;
  scopes: IdentityScopeGrant[];
}

export interface IdentityUserAccount {
  account_id: string;
  account_key: string;
  login_name: string;
  display_name: string;
  email: string | null;
  experience_role_key: string;
  status: string;
  authentication_source: string;
  organization: string;
  org_key: string;
  position: string;
  position_key: string;
  access_roles: string[];
  role_assignments: IdentityRoleAssignment[];
  scope_labels: string[];
  last_login_at: string | null;
  version: number;
}

export interface IdentityUserConfigurationRequest {
  schema_version: 1;
  client_request_key: string;
  login_name?: string;
  initial_password?: string;
  expected_version?: number;
  display_name: string;
  email: string | null;
  experience_role_key: string;
  org_key: string;
  position_key: string;
  status: "active" | "suspended";
  role_assignments: Array<{
    role_key: string;
    scopes: IdentityScopeGrant[];
  }>;
  reason: string;
}

export interface IdentityUserMutationResponse {
  schema_version: 1;
  operation: "created" | "configured";
  account: IdentityUserAccount;
  event_id: string;
  replayed: boolean;
}

export interface IdentityAdminOverview {
  schema_version: 1;
  enterprise_id: string;
  enterprise_name: string;
  stats: {
    active_users: number;
    org_units: number;
    positions: number;
    access_roles: number;
    permissions: number;
    active_assignments: number;
    authorization_decisions: number;
    denied_decisions: number;
    management_events: number;
  };
  users: IdentityUserAccount[];
  org_units: Array<{
    org_id: string;
    org_key: string;
    name: string;
    unit_type: string;
    parent_name: string | null;
    status: string;
    version: number;
    position_count: number;
    member_count: number;
  }>;
  positions: Array<{
    position_key: string;
    name: string;
    position_level: string;
    organization: string;
    org_key: string;
    status: string;
    version: number;
    member_count: number;
  }>;
  access_roles: Array<{
    role_key: string;
    name: string;
    description: string;
    version: string;
    revision: number;
    status: string;
    permission_count: number;
    permissions: string[];
    assignment_count: number;
    scope_types: string[];
  }>;
  permission_catalog: Array<{
    permission_key: string;
    label: string;
    resource: string;
    action: string;
    risk_level: string;
    status: string;
  }>;
  recent_decisions: Array<{
    id: string;
    request_id: string;
    run_id: string;
    actor_name: string;
    permission_key: string;
    resource_type: string;
    resource_key: string;
    decision: "allow" | "deny";
    reason: string;
    policy_version: string;
    decided_at: string;
  }>;
  recent_management_events: Array<{
    id: string;
    event_type: "identity.user.created" | "identity.user.configured";
    actor_name: string;
    target_name: string;
    target_account_key: string;
    changed_fields: string[];
    reason: string;
    request_id: string;
    run_id: string;
    occurred_at: string;
  }>;
  recent_catalog_events: Array<{
    id: string;
    event_type: string;
    target_type: string;
    target_key: string;
    actor_name: string;
    changed_fields: string[];
    reason: string;
    request_id: string;
    run_id: string;
    occurred_at: string;
  }>;
  generated_at: string;
}

export interface IdentityCatalogMutationResponse {
  schema_version: 1;
  operation: "created" | "updated";
  target_type: "org_unit" | "position" | "access_role";
  target_key: string;
  event_id: string;
  replayed: boolean;
}
