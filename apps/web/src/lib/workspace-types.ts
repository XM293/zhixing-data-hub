export type WorkspaceKey =
  | "executive"
  | "manager"
  | "operator"
  | "service"
  | "finance"
  | "people"
  | "data-governance"
  | "platform-ops"
  | "ai-ops";

export interface WorkspaceScope {
  kind: string;
  keys: string[];
  label: string;
  as_of: string;
}

export interface WorkspaceProfile {
  schema_version: 1;
  key: WorkspaceKey;
  label: string;
  audience: string[];
  default_route: string;
  navigation_keys: string[];
  metric_keys: string[];
  attention_query_keys: string[];
  quick_action_keys: string[];
  scene_key: string | null;
  layout_version: number;
  delivery_state: "prototype" | "implemented" | "unavailable";
}

export interface WorkspaceCatalogResponse {
  schema_version: 1;
  data_mode: "database";
  default_workspace_key: WorkspaceKey;
  workspaces: WorkspaceProfile[];
  scope: WorkspaceScope;
  generated_at: string;
}

export interface WorkspaceMetric {
  key: string;
  label: string;
  value: number;
  unit: string;
  change_rate: number | null;
  as_of: string;
  status: "positive" | "warning" | "critical" | "info" | "neutral";
  status_reason: string;
  href: string | null;
  evidence_refs: string[];
}

export interface WorkspaceAttention {
  key: string;
  kind: "anomaly" | "decision" | "approval" | "work" | "system" | "quality";
  title: string;
  detail: string;
  severity: "critical" | "high" | "warning" | "info" | "neutral";
  status: string;
  href: string | null;
  evidence_refs: string[];
  as_of: string | null;
}

export interface WorkspaceActivity {
  key: string;
  kind: string;
  title: string;
  detail: string;
  status: string;
  href: string | null;
  occurred_at: string;
}

export interface WorkspaceFreshness {
  key: string;
  label: string;
  status: string;
  as_of: string | null;
  detail: string;
}

export interface WorkspaceQuickAction {
  key: string;
  label: string;
  href: string;
  required_permission: string | null;
  enabled: boolean;
  disabled_reason: string | null;
}

export interface WorkspaceScene {
  key: string;
  label: string;
  route: string | null;
  enabled: boolean;
  object_refs: string[];
  layer_keys: string[];
}

export interface WorkspaceReadModelResponse {
  schema_version: 1;
  data_mode: "database";
  workspace: WorkspaceProfile;
  actor_name: string;
  actor_position: string;
  actor_organization: string;
  scope: WorkspaceScope;
  scope_context: Record<string, unknown>;
  navigation: Array<{
    key: string;
    label: string;
    short_label: string;
    href: string;
    icon_key: string;
    delivery_state: "prototype" | "implemented" | "unavailable";
    items: Array<{
      key: string;
      label: string;
      href: string;
      required_permission: string | null;
    }>;
  }>;
  metrics: WorkspaceMetric[];
  attention: WorkspaceAttention[];
  decisions: WorkspaceAttention[];
  work_items: WorkspaceAttention[];
  activities: WorkspaceActivity[];
  freshness: WorkspaceFreshness[];
  quick_actions: WorkspaceQuickAction[];
  scene: WorkspaceScene | null;
  generated_at: string;
}
