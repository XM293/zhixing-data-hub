import type { AnalysisExecutionMode, AnalysisScope } from "@/lib/analysis-types";

export type ReviewPlanStatus = "active" | "paused";
export type ReviewRunStatus = "preparing" | "queued" | "running" | "succeeded" | "failed";
export type ReviewAutoPriority = "off" | "urgent" | "high";

export interface StoreReviewPlan {
  key: string;
  name: string;
  scope: AnalysisScope;
  window_days: number;
  timezone: string;
  local_time: string;
  weekdays: number[];
  auto_propose_min_priority: ReviewAutoPriority;
  status: ReviewPlanStatus;
  next_run_at: string | null;
  last_enqueued_at: string | null;
  created_by_name: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface StoreReviewScheduleRun {
  id: string;
  plan_key: string;
  plan_name: string;
  scope: AnalysisScope;
  business_date: string;
  trigger_type: "scheduled" | "manual";
  status: ReviewRunStatus;
  background_job_id: string | null;
  background_job_attempt: number;
  analysis_run_id: string | null;
  brief_id: string | null;
  proposal_count: number;
  execution_mode: AnalysisExecutionMode | null;
  error_code: string | null;
  error_message: string | null;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface StoreReviewSchedule {
  schema_version: 1;
  data_mode: "database";
  actor_name: string;
  can_manage: boolean;
  available_scopes: AnalysisScope[];
  stats: {
    plan_count: number;
    active_plan_count: number;
    queued_or_running_count: number;
    succeeded_count: number;
    failed_count: number;
    pending_proposal_count: number;
  };
  plans: StoreReviewPlan[];
  runs: StoreReviewScheduleRun[];
  generated_at: string;
}

export interface StoreReviewPlanMutationResponse {
  schema_version: 1;
  idempotent: boolean;
  schedule: StoreReviewSchedule;
}
