export type AnalysisRiskLevel = "healthy" | "watch" | "high" | "critical";
export type AnalysisExecutionMode = "model" | "evidence-fallback";

export interface AnalysisScope {
  type: "enterprise" | "store";
  key: string;
  label: string;
}

export interface AnalysisMetricPoint {
  as_of: string;
  value: number;
}

export interface AnalysisMetric {
  key: string;
  label: string;
  unit: string;
  latest_value: number;
  period_change_rate: number | null;
  minimum: number;
  maximum: number;
  status: AnalysisRiskLevel;
  status_reason: string;
  evidence_ref: string;
  points: AnalysisMetricPoint[];
}

export interface AnalysisCommerceFact {
  key: string;
  domain: "orders" | "refunds" | "inventory" | "advertising" | "exception";
  label: string;
  evidence_ref: string;
  value: number;
  unit: string;
  status: AnalysisRiskLevel;
  detail: string;
  related_keys: string[];
  source_keys: string[];
  sync_run_ids: string[];
}

export interface AnalysisFinding {
  kind: "fact" | "inference" | "risk";
  severity: AnalysisRiskLevel;
  text: string;
  evidence_refs: string[];
}

export interface AnalysisRecommendation {
  title: string;
  action: string;
  owner_role: string;
  priority: "normal" | "high" | "urgent";
  evidence_refs: string[];
  success_metric: string;
  stop_condition: string;
}

export interface BusinessAnalysisRun {
  id: string;
  analysis_type: "store-review" | "enterprise-review";
  scope: AnalysisScope;
  window_days: number;
  status: "completed" | "failed";
  risk_level: AnalysisRiskLevel;
  provider: string;
  model: string;
  execution_mode: AnalysisExecutionMode;
  fallback_reason: string | null;
  result: {
    headline: string;
    summary: string;
    confidence: "high" | "medium" | "low";
    metric_snapshot: AnalysisMetric[];
    commerce_fact_snapshot: AnalysisCommerceFact[];
    findings: AnalysisFinding[];
    recommendations: AnalysisRecommendation[];
    unknowns: string[];
  };
  evidence_snapshot: {
    id: string;
    key: string;
    content_hash: string;
    item_count: number;
    frozen_at: string;
  };
  action_proposals: Array<{
    recommendation_index: number;
    proposal_key: string;
    status: "pending_approval" | "approved" | "rejected";
    work_item_key: string | null;
    work_item_status: "ready" | "claimed" | "in_progress" | "blocked" | "completed" | null;
  }>;
  workspace_key: string | null;
  initiated_by_principal_id: string;
  initiated_by_name: string;
  request_id: string;
  run_id: string;
  created_at: string;
  completed_at: string;
}

export interface BusinessBrief {
  id: string;
  key: string;
  version_number: number;
  brief_type: "daily" | "weekly" | "exception";
  scope: AnalysisScope;
  title: string;
  status: "generated" | "confirmed" | "superseded";
  source_analysis_run_id: string;
  evidence_snapshot_key: string;
  provider: string;
  model: string;
  execution_mode: AnalysisExecutionMode;
  content: {
    headline: string;
    sections: Array<{ key: string; title: string; items: string[] }>;
    evidence_refs: string[];
  };
  created_by_principal_id: string;
  created_by_name: string;
  request_id: string;
  run_id: string;
  created_at: string;
}

export interface AnalysisStudio {
  schema_version: 1;
  data_mode: "database";
  actor_name: string;
  can_run: boolean;
  can_propose: boolean;
  selected_scope: AnalysisScope;
  available_scopes: AnalysisScope[];
  stats: {
    analysis_run_count: number;
    brief_count: number;
    high_risk_count: number;
    model_run_count: number;
    latest_completed_at: string | null;
  };
  latest_run: BusinessAnalysisRun | null;
  runs: BusinessAnalysisRun[];
  briefs: BusinessBrief[];
  generated_at: string;
}

export interface BusinessAnalysisRunResponse {
  schema_version: 1;
  idempotent: boolean;
  run: BusinessAnalysisRun;
  brief: BusinessBrief;
  studio: AnalysisStudio;
}
