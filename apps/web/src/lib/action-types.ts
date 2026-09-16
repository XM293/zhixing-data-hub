export type ActionProposalStatus = "pending_approval" | "approved" | "rejected";
export type ActionSourceType = "meeting-decision" | "customer-operation" | "business-analysis";
export type ActionWorkStatus = "ready" | "claimed" | "in_progress" | "blocked" | "completed";
export type ActionWorkAction = "claim" | "start" | "block" | "complete" | "release" | "reopen";

export interface MeetingDecisionConfirmation {
  id: string;
  meeting_key: string;
  decision_package_id: string;
  confirmed_by_actor_key: string;
  confirmed_by_name: string;
  comment: string;
  confirmed_at: string;
}

export interface ActionApprovalEvent {
  id: string;
  actor_key: string;
  actor_name: string;
  decision: "approved" | "rejected";
  comment: string;
  idempotency_key: string;
  created_at: string;
}

export interface ActionExecution {
  id: string;
  key: string;
  idempotency_key: string;
  status: "recorded";
  external_write: false;
  actor_key: string;
  result: Record<string, unknown>;
  started_at: string;
  finished_at: string;
}

export interface ActionProposal {
  id: string;
  key: string;
  source_type: ActionSourceType;
  source_key: string;
  source_label: string;
  source_route: string;
  scope_type: "enterprise" | "store" | "object";
  scope_key: string;
  meeting_key: string | null;
  decision_package_id: string | null;
  customer_operation_run_id: string | null;
  business_analysis_run_id: string | null;
  evidence_snapshot_id: string | null;
  title: string;
  owner: string;
  due_hint: string;
  kpi: string;
  stop_condition: string;
  evidence_refs: string[];
  target_system: string;
  target_key: string;
  risk_level: "R2";
  action_level: "R2";
  parameters: Record<string, unknown>;
  status: ActionProposalStatus;
  requested_by_actor_key: string;
  requested_by_name: string;
  idempotency_key: string;
  approved_by_actor_key: string | null;
  approved_by_name: string | null;
  approved_at: string | null;
  decision_comment: string | null;
  approval_events: ActionApprovalEvent[];
  execution: ActionExecution | null;
  work_item: {
    key: string;
    status: ActionWorkStatus;
    assignee_name: string | null;
    version: number;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface ActionProposalStats {
  total: number;
  pending_approval: number;
  approved: number;
  rejected: number;
  recorded_executions: number;
}

export interface ActionProposalListResponse {
  schema_version: 1;
  data_mode: "database";
  stats: ActionProposalStats;
  items: ActionProposal[];
  generated_at: string;
}

export interface ActionDecisionResponse {
  schema_version: 1;
  item: ActionProposal;
}

export interface CustomerOperationActionProposalResponse {
  schema_version: 1;
  idempotent: boolean;
  created_count: number;
  items: ActionProposal[];
}

export interface BusinessAnalysisActionProposalResponse {
  schema_version: 1;
  idempotent: boolean;
  created_count: number;
  items: ActionProposal[];
}

export interface ActionWorkEvent {
  id: string;
  event_type: "created" | ActionWorkAction;
  from_status: string | null;
  to_status: ActionWorkStatus;
  actor_principal_id: string;
  actor_name: string;
  comment: string;
  evidence_refs: string[];
  idempotency_key: string;
  created_at: string;
}

export interface ActionWorkItem {
  id: string;
  key: string;
  proposal_key: string;
  source_type: ActionSourceType;
  source_label: string;
  source_route: string;
  scope_type: "enterprise" | "store" | "object";
  scope_key: string;
  title: string;
  owner_role: string;
  due_hint: string;
  kpi: string;
  stop_condition: string;
  priority: "normal" | "high" | "urgent";
  status: ActionWorkStatus;
  assignee_principal_id: string | null;
  assignee_name: string | null;
  version: number;
  can_update: boolean;
  available_actions: ActionWorkAction[];
  blocker_reason: string | null;
  result_summary: string | null;
  result_evidence_refs: string[];
  claimed_at: string | null;
  started_at: string | null;
  blocked_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  events: ActionWorkEvent[];
}

export interface ActionWorkListResponse {
  schema_version: 1;
  data_mode: "database";
  actor_name: string;
  can_manage: boolean;
  stats: Record<ActionWorkStatus | "total" | "mine", number>;
  items: ActionWorkItem[];
  generated_at: string;
}

export interface ActionWorkEventResponse {
  schema_version: 1;
  idempotent: boolean;
  item: ActionWorkItem;
}
