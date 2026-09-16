export type CustomerOperationActionType =
  | "manual_review"
  | "service_handoff"
  | "content_preparation"
  | "audience_analysis";

export interface CustomerOperationEvidence {
  evidence_ref: string;
  item_type: string;
  item_key: string;
  label: string;
  version_ref: string | null;
  payload: Record<string, unknown>;
}

export interface CustomerOperationDiagnosis {
  kind: "fact" | "inference" | "risk";
  severity: "low" | "medium" | "high";
  text: string;
  evidence_refs: string[];
}

export interface CustomerOperationStep {
  title: string;
  action: string;
  owner_role: string;
  priority: "normal" | "high" | "urgent";
  action_type: CustomerOperationActionType;
  evidence_refs: string[];
  success_metric: string;
  stop_condition: string;
  requires_human_approval: true;
  external_write_allowed: false;
}

export interface CustomerOperationRun {
  id: string;
  customer_key: string;
  scope_type: "enterprise" | "store";
  scope_key: string;
  objective: string;
  status: "completed";
  risk_level: "low" | "medium" | "high";
  provider: string;
  model: string;
  execution_mode: "model" | "rule-fallback";
  fallback_reason: string | null;
  result: {
    headline: string;
    summary: string;
    objective: string;
    confidence: "high" | "medium" | "low";
    diagnoses: CustomerOperationDiagnosis[];
    steps: CustomerOperationStep[];
    unknowns: string[];
    prohibited_actions: string[];
  };
  evidence_snapshot: {
    id: string;
    snapshot_key: string;
    purpose: "customer-operation";
    content_hash: string;
    item_count: number;
    frozen_at: string;
  };
  evidence: CustomerOperationEvidence[];
  action_proposals: Array<{
    step_index: number;
    proposal_key: string;
    status: "pending_approval" | "approved" | "rejected";
  }>;
  initiated_by_name: string;
  initiated_by_principal_id: string;
  request_id: string;
  run_id: string;
  duration_ms: number;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
  completed_at: string;
}

export interface CustomerOperationStudioResponse {
  schema_version: 1;
  data_mode: "database";
  scope_key: string;
  customer_key: string;
  can_run: boolean;
  can_propose: boolean;
  runs: CustomerOperationRun[];
  generated_at: string;
}

export interface CustomerOperationRunResponse {
  schema_version: 1;
  idempotent: boolean;
  run: CustomerOperationRun;
  studio: CustomerOperationStudioResponse;
}
