export interface ToolDefinition {
  key: string;
  display_name: string;
  description: string;
  risk_level: "R0" | "R1" | "R2" | "R3";
  permission_key: string;
  resource_type: string;
  scope_resolver: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  provider: string;
  version: string;
  timeout_seconds: number;
  status: string;
}

export interface ToolAdminOverview {
  schema_version: 1;
  enterprise_id: string;
  stats: {
    active_tools: number;
    r0_tools: number;
    invocations: number;
    succeeded: number;
    denied: number;
    failed: number;
  };
  tools: ToolDefinition[];
  recent_invocations: Array<{
    id: string;
    tool_key: string;
    tool_version: string;
    actor_name: string;
    risk_level: string;
    permission_key: string;
    authentication_method: string;
    permission_set_version: string;
    session_permission_set_version: string | null;
    permission_set_version_changed: boolean;
    gateway_session_id: string | null;
    agent_run_id: string | null;
    status: "succeeded" | "denied" | "failed";
    error_code: string | null;
    duration_ms: number;
    request_id: string;
    run_id: string;
    input_parameters: Record<string, unknown>;
    output_summary: Record<string, unknown>;
    started_at: string;
    finished_at: string;
  }>;
  generated_at: string;
}
