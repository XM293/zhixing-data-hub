export type Confidence = "high" | "medium" | "low";
export type Stance = "support" | "oppose" | "conditional";

export interface TwinCatalogStats {
  profile_count: number;
  active_memory_count: number;
  candidate_memory_count: number;
  conflicted_memory_count: number;
  agent_run_count: number;
}

export interface RoleTwinCatalogItem {
  key: string;
  display_name: string;
  role_title: string;
  status: string;
  provider: string;
  model: string;
  capabilities: string[];
  voice_guide: string;
  reasoning_guide: string;
  answer_policy: string;
  active_memory_count: number;
  candidate_memory_count: number;
  conflicted_memory_count: number;
  run_count: number;
  published_at: string | null;
  latest_run_at: string | null;
  updated_at: string;
}

export interface RoleTwinCatalogResponse {
  schema_version: 1;
  data_mode: "database";
  stats: TwinCatalogStats;
  items: RoleTwinCatalogItem[];
  generated_at: string;
}

export interface MemoryCandidateItem {
  id: string;
  key: string;
  twin_key: string;
  twin_name: string;
  category: string;
  content: string;
  source_type: string;
  source_ref: string;
  confidence: number;
  conflict_status: string;
  conflict_ref: string | null;
  evidence_refs: Array<Record<string, unknown>>;
  status: string;
  reviewer: string | null;
  review_reason: string | null;
  reviewed_at: string | null;
  effective_from: string | null;
  retired_at: string | null;
  approved_memory_id: string | null;
  approved_memory_status: string | null;
  memory_version: number | null;
  created_at: string;
  updated_at: string;
}

export interface MemoryCandidateListResponse {
  schema_version: 2;
  data_mode: "database";
  status_counts: Record<string, number>;
  conflict_counts: Record<string, number>;
  items: MemoryCandidateItem[];
  generated_at: string;
}

export interface ChatImportRunItem {
  id: string;
  twin_key: string;
  twin_name: string;
  actor_name: string;
  source_filename: string;
  source_channel: string;
  content_hash: string;
  status: "completed" | "duplicate" | "failed";
  message_count: number;
  topic_count: number;
  candidate_count: number;
  participants: string[];
  started_at: string | null;
  ended_at: string | null;
  warnings: Array<Record<string, unknown>>;
  request_id: string;
  run_id: string;
  created_at: string;
  finished_at: string;
}

export interface ChatImportListResponse {
  schema_version: 1;
  status_counts: Record<string, number>;
  items: ChatImportRunItem[];
  generated_at: string;
}

export interface ChatImportResponse {
  schema_version: 1;
  duplicate: boolean;
  import_run: ChatImportRunItem;
  messages: Array<{
    id: string;
    message_key: string;
    sent_at: string | null;
    sender_name: string;
    topic_key: string;
    content: string;
    ordinal: number;
  }>;
  candidates: MemoryCandidateItem[];
}

export interface MemoryMutationResponse {
  schema_version: 1;
  idempotent: boolean;
  candidate: MemoryCandidateItem;
  approved_memory: {
    id: string;
    status: "approved" | "active" | "retired";
    version_number: number;
  } | null;
  event: {
    id: string;
    event_type: "approved" | "rejected" | "activated" | "retired";
    actor_name: string;
    reason: string;
    request_id: string;
    run_id: string;
    occurred_at: string;
  };
}

export interface MemoryProviderDescriptor {
  key: string;
  label: string;
  protocol: string;
  mode: string;
  endpoint_fingerprint: string;
  authentication_configured: boolean;
}

export interface MemoryBenchmarkCase {
  key: string;
  category: string;
  query: string;
  expected_memory_keys: string[];
  expected_twin_keys: string[];
}

export interface MemoryProviderQueryResult {
  case_key: string;
  query: string;
  expected_memory_keys: string[];
  returned_memory_keys: string[];
  hit: boolean;
  latency_ms: number;
  top_score: number;
}

export interface MemoryProviderEvaluationResult {
  provider_key: string;
  provider_mode: string;
  protocol: string;
  endpoint_fingerprint: string;
  status: "succeeded" | "failed";
  indexed_memory_count: number;
  query_count: number;
  hit_count: number;
  recall_at_k: number;
  average_latency_ms: number;
  p95_latency_ms: number;
  items: MemoryProviderQueryResult[];
  failure_reason: string | null;
}

export interface MemoryProviderEvaluationRun {
  id: string;
  evaluation_key: string;
  benchmark_version: string;
  status: "running" | "completed" | "partial" | "failed";
  provider_keys: string[];
  memory_count: number;
  case_count: number;
  actor_name: string;
  idempotent: boolean;
  request_id: string;
  run_id: string;
  started_at: string;
  finished_at: string | null;
  results: MemoryProviderEvaluationResult[];
}

export interface MemoryProviderOperationsResponse {
  schema_version: 1;
  data_mode: "database";
  benchmark_version: string;
  active_memory_count: number;
  benchmark_cases: MemoryBenchmarkCase[];
  providers: MemoryProviderDescriptor[];
  runs: MemoryProviderEvaluationRun[];
  generated_at: string;
}

export interface MeetingListItem {
  key: string;
  title: string;
  topic: string;
  status: string;
  protocol_status: string;
  template_key: string;
  initiated_by_name: string;
  scope_type: "enterprise" | "store";
  scope_key: string;
  scope_label: string;
  decision_owner: string;
  deadline_at: string | null;
  success_metric: string;
  evidence_snapshot: string;
  participant_count: number;
  claim_count: number;
  deliberation_count: number;
  has_decision_package: boolean;
  workspace_key: string | null;
  updated_at: string;
  created_at: string;
}

export interface MeetingTemplate {
  key: "budget-inventory-review" | "inventory-clearance-review" | "kpi-incentive-review";
  label: string;
  description: string;
  default_title: string;
  default_topic: string;
  default_success_metric: string;
}

export interface MeetingScope {
  type: "enterprise" | "store";
  key: string;
  label: string;
  has_metric_data: boolean;
}

export interface MeetingCreateRequest {
  schema_version: 1;
  client_request_key: string;
  template_key: MeetingTemplate["key"];
  title: string;
  topic: string;
  scope_type: MeetingScope["type"];
  scope_key: string;
  success_metric: string;
  deadline_at: string | null;
  participant_keys: string[];
  workspace_key?: string | null;
}

export interface MeetingCreateResponse {
  schema_version: 1;
  idempotent: boolean;
  meeting: MeetingListItem;
}

export interface MeetingListResponse {
  schema_version: 1;
  data_mode: "database";
  status_counts: Record<string, number>;
  templates: MeetingTemplate[];
  scopes: MeetingScope[];
  items: MeetingListItem[];
  generated_at: string;
}

export interface EvidenceSnapshotItem {
  type: string;
  key: string;
  version_ref: string | null;
  label: string;
  payload: Record<string, unknown>;
  rank: number;
}

export interface EvidenceSnapshot {
  key: string;
  purpose: string;
  query: string;
  content_hash: string;
  item_count: number;
  frozen_at: string;
  items: EvidenceSnapshotItem[];
}

export interface ClaimItem {
  statement: string;
  evidence_refs: string[];
  assumption: string;
  confidence: Confidence;
}

export interface MeetingClaim {
  id: string;
  twin_key: string;
  twin_name: string;
  role_title: string;
  phase: string;
  stance: Stance;
  summary: string;
  claims: ClaimItem[];
  risks: string[];
  unknowns: string[];
  recommendation: string;
  confidence: Confidence;
  created_at: string;
}

export interface CrossExaminationItem {
  statement: string;
  target_claim: string;
  evidence_refs: string[];
  new_evidence_refs: string[];
  question: string;
  confidence: Confidence;
}

export interface CrossExaminationPayload {
  summary: string;
  challenges: CrossExaminationItem[];
  position_after: Stance;
  position_changed: boolean;
  unresolved: string[];
  confidence: Confidence;
}

export interface RiskFailureMode {
  risk: string;
  mechanism: string;
  evidence_refs: string[];
  trigger: string;
  mitigation: string;
}

export interface RiskReviewPayload {
  summary: string;
  failure_modes: RiskFailureMode[];
  counterfactuals: string[];
  incentive_risks: string[];
  unresolved: string[];
  confidence: Confidence;
}

export interface MeetingDeliberationTurn {
  id: string;
  speaker_twin_key: string;
  speaker_name: string;
  speaker_role_title: string;
  target_twin_key: string | null;
  target_name: string | null;
  phase: string;
  round_number: number;
  turn_type: "challenge" | "response" | "risk_review";
  summary: string;
  payload: CrossExaminationPayload | RiskReviewPayload;
  evidence_refs: string[];
  new_evidence_refs: string[];
  position_after: Stance | null;
  position_changed: boolean;
  confidence: Confidence;
  created_at: string;
}

export interface DecisionAction {
  title: string;
  owner: string;
  due_hint: string;
  kpi: string;
  stop_condition: string;
  evidence_refs: string[];
}

export interface DecisionPackage {
  id: string;
  summary: string;
  consensus: string[];
  disagreements: string[];
  risks: string[];
  decision: string;
  actions: DecisionAction[];
  confidence: Confidence;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface MeetingParticipant {
  actor_key: string;
  role_name: string;
  position: string;
  finding: string;
  status: string;
  speaking_order: number;
}

export interface DigitalMeetingDetailResponse {
  schema_version: 1;
  data_mode: "database";
  meeting: MeetingListItem;
  participants: MeetingParticipant[];
  evidence: EvidenceSnapshot | null;
  claims: MeetingClaim[];
  deliberation_turns: MeetingDeliberationTurn[];
  decision_package: DecisionPackage | null;
  confirmation: MeetingDecisionConfirmation | null;
  action_proposals: ActionProposal[];
  generated_at: string;
}

export interface MeetingRunResponse {
  schema_version: 1;
  detail: DigitalMeetingDetailResponse;
  execution_modes: Record<string, "model" | "evidence-fallback">;
  duration_ms: number;
}

export interface MeetingConfirmResponse {
  schema_version: 1;
  detail: DigitalMeetingDetailResponse;
  created_action_count: number;
}
import type { ActionProposal, MeetingDecisionConfirmation } from "@/lib/action-types";
