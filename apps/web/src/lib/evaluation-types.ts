export type EvaluationOutcome = "passed" | "failed" | "review_required" | "error";

export interface EvaluationCheck {
  key: string;
  label: string;
  passed: boolean;
  expected: string;
  actual: string;
}

export interface EvaluationCase {
  key: string;
  version_number: number;
  domain: string;
  risk_level: string;
  title: string;
  actor_login_name: string;
  target_twin_key: string;
  input: { question?: string; top_k?: number; scope_key?: string | null };
  expectations: Record<string, unknown>;
  status: string;
}

export interface EvaluationRunItem {
  id: string;
  case_key: string;
  case_version_number: number;
  case_title: string;
  domain: string;
  risk_level: string;
  actor_name: string;
  actor_principal_id: string | null;
  agent_run_id: string | null;
  case_snapshot: Record<string, unknown>;
  actor_snapshot: Record<string, unknown>;
  outcome: EvaluationOutcome;
  checks: EvaluationCheck[];
  error_types: string[];
  observed_error_code: string | null;
  duration_ms: number;
  created_at: string;
}

export interface EvaluationRun {
  id: string;
  suite_key: string;
  suite_version_number: number;
  status: "running" | "completed" | "failed";
  provider: string;
  model: string;
  code_version: string;
  config_version: string;
  baseline_run_id: string | null;
  pass_rate_delta: number | null;
  total_count: number;
  passed_count: number;
  failed_count: number;
  review_required_count: number;
  error_count: number;
  pass_rate: number;
  duration_ms: number;
  initiated_by_name: string;
  started_at: string;
  completed_at: string | null;
  items: EvaluationRunItem[];
}

export interface EvaluationSuite {
  key: string;
  version_number: number;
  domain: string;
  title: string;
  description: string;
  status: string;
  cases: EvaluationCase[];
  latest_run: EvaluationRun | null;
  recent_runs: EvaluationRun[];
}

export type EvaluationCandidateStatus = "pending" | "accepted" | "rejected";

export interface EvaluationCandidate {
  id: string;
  source_handoff_case_id: string;
  source_feedback_event_id: string;
  source_agent_run_id: string;
  proposed_case_key: string;
  proposed_title: string;
  domain: string;
  risk_level: string;
  actor_login_name: string;
  target_twin_key: string;
  input: { question?: string; top_k?: number; scope_key?: string | null };
  expectations: Record<string, unknown>;
  resolution_summary: string;
  status: EvaluationCandidateStatus;
  proposed_by_name: string;
  reviewed_by_name: string | null;
  accepted_case_id: string | null;
  review_reason: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface EvaluationStudioResponse {
  schema_version: 1;
  data_mode: "database";
  stats: {
    suite_count: number;
    case_count: number;
    run_count: number;
    latest_pass_rate: number | null;
    pending_manual_review_count: number;
    candidate_count: number;
    pending_candidate_count: number;
  };
  suites: EvaluationSuite[];
  candidates: EvaluationCandidate[];
  generated_at: string;
}

export interface EvaluationMutationResponse {
  schema_version: 1;
  idempotent: boolean;
  run: EvaluationRun;
  studio: EvaluationStudioResponse;
}

export interface EvaluationCandidateMutationResponse {
  schema_version: 1;
  idempotent: boolean;
  candidate: EvaluationCandidate;
  studio: EvaluationStudioResponse;
}
