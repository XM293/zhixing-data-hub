import type { TwinAnswerPayload } from "@/lib/knowledge-types";

export type RoleTwinTestCategory = "knowledge" | "data" | "boundary" | "style" | "decision";
export type RoleTwinTestRisk = "low" | "medium" | "high";
export type RoleTwinTestDecision = "pass" | "needs_revision" | "fail";

export interface RoleTwinTestTwinOption {
  key: string;
  display_name: string;
  role_title: string;
  current_version_number: number;
  status: string;
}

export interface RoleTwinTestContextRef {
  kind: "data" | "evidence" | "memory";
  label: string;
  version_ref: string | null;
  excerpt: string;
  rank: number;
}

export interface RoleTwinTestReview {
  id: string;
  decision: RoleTwinTestDecision;
  evidence_grounding: number;
  boundary_adherence: number;
  voice_match: number;
  usefulness: number;
  average_score: number;
  notes: string;
  reviewer_name: string;
  request_id: string;
  run_id: string;
  created_at: string;
}

export interface RoleTwinTestRun {
  id: string;
  case_key: string;
  case_version_number: number;
  twin_key: string;
  twin_name: string;
  role_twin_version_number: number;
  agent_run_id: string;
  question: string;
  answer: TwinAnswerPayload;
  evidence_count: number;
  metric_context_count: number;
  memory_context_count: number;
  context_refs: RoleTwinTestContextRef[];
  execution_mode: "model" | "evidence-fallback";
  provider: string;
  model: string;
  duration_ms: number;
  status: string;
  actor_name: string;
  created_at: string;
  reviews: RoleTwinTestReview[];
  latest_review: RoleTwinTestReview | null;
}

export interface RoleTwinTestCase {
  id: string;
  key: string;
  version_number: number;
  status: string;
  title: string;
  category: RoleTwinTestCategory;
  risk_level: RoleTwinTestRisk;
  question: string;
  expected_behaviors: string[];
  expected_evidence_refs: string[];
  target_twin_key: string;
  target_twin_name: string;
  created_at: string;
  runs: RoleTwinTestRun[];
}

export interface RoleTwinTestStudioResponse {
  schema_version: 1;
  data_mode: "database";
  stats: {
    case_count: number;
    run_count: number;
    pending_review_count: number;
    reviewed_count: number;
    passed_count: number;
    pass_rate: number | null;
  };
  twins: RoleTwinTestTwinOption[];
  cases: RoleTwinTestCase[];
  generated_at: string;
}

export interface RoleTwinTestMutationResponse {
  schema_version: 1;
  run: RoleTwinTestRun;
  studio: RoleTwinTestStudioResponse;
}
