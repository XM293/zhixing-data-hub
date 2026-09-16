export type AuditSource = "authorization" | "identity" | "mcp" | "tool" | "worker" | "agent" | "action" | "platform";
export type AuditSeverity = "normal" | "warning" | "critical";

export interface AuditEvent {
  id: string;
  source: AuditSource;
  event_type: string;
  outcome: string;
  severity: AuditSeverity;
  actor_principal_id: string | null;
  actor_name: string;
  subject_type: string;
  subject_key: string;
  summary: string;
  request_id: string | null;
  run_id: string | null;
  agent_run_id: string | null;
  duration_ms: number | null;
  occurred_at: string;
  attributes: Array<{ key: string; label: string; value: string }>;
}

export interface UnifiedAuditLedgerResponse {
  schema_version: 1;
  enterprise_id: string;
  filters: {
    source: AuditSource | null;
    outcome: string | null;
    actor_principal_id: string | null;
    request_id: string | null;
    run_id: string | null;
    query: string | null;
    start_at: string | null;
    end_at: string | null;
  };
  stats: {
    total_events: number;
    events_last_24h: number;
    attention_events: number;
    unique_actors: number;
    correlated_runs: number;
  };
  facets: {
    sources: Array<{ key: string; count: number }>;
    outcomes: Array<{ key: string; count: number }>;
    actors: Array<{ principal_id: string; display_name: string; count: number }>;
  };
  items: AuditEvent[];
  pagination: {
    offset: number;
    limit: number;
    total: number;
    has_more: boolean;
  };
  generated_at: string;
}
