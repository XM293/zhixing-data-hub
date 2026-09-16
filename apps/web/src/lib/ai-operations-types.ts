export interface AIProviderConfigView {
  provider_key: string;
  label: string;
  protocol: string;
  endpoint_kind: "official" | "private-compatible";
  enabled: boolean;
  configured: boolean;
  model: string;
  timeout_seconds: number;
  capabilities: string[];
}

export interface AIProviderProbeRunView {
  id: string;
  provider_key: string;
  model: string;
  protocol: string;
  structured_output_supported: boolean;
  status: "succeeded" | "failed";
  duration_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  error_code: string | null;
  error_message: string | null;
  actor_name: string;
  request_id: string;
  run_id: string;
  created_at: string;
}

export interface AgentRuntimeConfigView {
  runtime_key: string;
  label: string;
  protocol: string;
  enabled: boolean;
  command_available: boolean;
  model: string | null;
  timeout_seconds: number;
  capabilities: string[];
  default_sandbox: string;
  approval_policy: string;
}

export interface AgentRuntimeProbeRunView {
  id: string;
  runtime_key: string;
  protocol: string;
  command_version: string | null;
  initialized: boolean;
  status: "succeeded" | "failed";
  duration_ms: number;
  error_code: string | null;
  error_message: string | null;
  actor_name: string;
  request_id: string;
  run_id: string;
  created_at: string;
}

export interface AgentRuntimeSessionView {
  id: string;
  agent_run_id: string;
  runtime_key: string;
  runtime_thread_id: string;
  runtime_session_id: string | null;
  mcp_gateway_session_id: string | null;
  status: string;
  model: string | null;
  turn_count: number;
  event_count: number;
  latest_event_type: string | null;
  can_cancel: boolean;
  failure_code: string | null;
  failure_message: string | null;
  request_id: string;
  run_id: string;
  created_at: string;
  completed_at: string | null;
}

export interface AgentRuntimeApprovalView {
  id: string;
  runtime_session_id: string;
  agent_run_id: string;
  request_method: string;
  item_id: string | null;
  skill_key: string | null;
  skill_version: number | null;
  tool_keys: string[];
  status: "pending" | "approved" | "declined" | "expired";
  decision: string | null;
  requested_at: string;
  decided_at: string | null;
}

export interface AgentRuntimeTurnView {
  id: string;
  agent_run_id: string;
  mcp_gateway_session_id: string | null;
  runtime_turn_id: string;
  turn_number: number;
  status: string;
  model: string | null;
  evidence_count: number;
  context_count: number;
  duration_ms: number;
  failure_code: string | null;
  failure_message: string | null;
  request_id: string;
  run_id: string;
  started_at: string;
  completed_at: string | null;
}

export interface AgentRuntimeEventView {
  id: string;
  runtime_turn_id: string | null;
  sequence: number;
  runtime_sequence: number;
  event_type: string;
  status: string;
  event_payload: Record<string, unknown>;
  occurred_at: string;
}

export interface AgentRuntimeSessionDetailResponse {
  schema_version: 1;
  session: AgentRuntimeSessionView;
  actor_name: string;
  twin_name: string;
  role_twin_version_number: number | null;
  turns: AgentRuntimeTurnView[];
  events: AgentRuntimeEventView[];
  generated_at: string;
}

export interface AgentRuntimeCancelResponse {
  schema_version: 1;
  accepted: true;
  session_id: string;
  agent_run_id: string;
  status: "interrupt_requested";
}

export interface AIRuntimeStats {
  total_runs: number;
  successful_runs: number;
  degraded_runs: number;
  success_rate: number;
  average_duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  token_coverage_rate: number;
  runs_last_24h: number;
  meeting_runs: number;
  answer_runs: number;
  customer_service_runs: number;
  customer_operation_runs: number;
  evaluation_batches: number;
  probe_runs: number;
}

export interface AIRunTypeStat {
  run_type: string;
  label: string;
  total_runs: number;
  successful_runs: number;
  degraded_runs: number;
  average_duration_ms: number;
  input_tokens: number;
  output_tokens: number;
}

export interface AIModelStat {
  provider: string;
  model: string;
  total_runs: number;
  successful_runs: number;
  degraded_runs: number;
  average_duration_ms: number;
  input_tokens: number;
  output_tokens: number;
}

export interface AIDailyStat {
  business_date: string;
  total_runs: number;
  successful_runs: number;
  degraded_runs: number;
  input_tokens: number;
  output_tokens: number;
}

export interface AILatestRunView {
  id: string;
  category: "agent" | "analysis" | "customer-operation";
  run_type: string;
  label: string;
  status: string;
  execution_mode: string;
  provider: string;
  model: string;
  duration_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
}

export interface AIOperationsOverviewResponse {
  schema_version: 1;
  enterprise_id: string;
  provider: AIProviderConfigView;
  runtime: AgentRuntimeConfigView;
  stats: AIRuntimeStats;
  run_types: AIRunTypeStat[];
  models: AIModelStat[];
  daily: AIDailyStat[];
  latest_runs: AILatestRunView[];
  probes: AIProviderProbeRunView[];
  runtime_probes: AgentRuntimeProbeRunView[];
  runtime_sessions: AgentRuntimeSessionView[];
  runtime_approvals: AgentRuntimeApprovalView[];
  generated_at: string;
}
