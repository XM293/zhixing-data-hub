export type FeedbackKind =
  | "helpful"
  | "inaccurate"
  | "incomplete"
  | "unsafe"
  | "scope_issue"
  | "handoff";

export type HandoffStatus = "open" | "in_review" | "resolved";
export type HandoffPriority = "normal" | "high" | "urgent";
export type ResolutionType =
  | "corrected_answer"
  | "policy_update"
  | "memory_update"
  | "no_issue"
  | "rerouted";

export interface AgentFeedbackEvent {
  id: string;
  event_type: "feedback_submitted" | "assigned" | "note_added" | "resolved" | "reopened";
  feedback_kind: FeedbackKind | null;
  actor_principal_id: string;
  actor_name: string;
  message: string;
  expected_answer: string | null;
  from_status: HandoffStatus | null;
  to_status: HandoffStatus | null;
  created_at: string;
}

export interface HumanHandoffCase {
  id: string;
  agent_run_id: string;
  twin_key: string;
  twin_name: string;
  role_twin_version_number: number | null;
  question: string;
  answer: string;
  execution_mode: "model" | "evidence-fallback";
  opened_by_principal_id: string;
  opened_by_name: string;
  assigned_to_principal_id: string | null;
  assigned_to_name: string | null;
  status: HandoffStatus;
  priority: HandoffPriority;
  category: FeedbackKind;
  subject: string;
  resolution_type: ResolutionType | null;
  resolution_summary: string | null;
  evaluation_candidate_id: string | null;
  evaluation_candidate_status: "pending" | "accepted" | "rejected" | null;
  opened_at: string;
  updated_at: string;
  resolved_at: string | null;
  events: AgentFeedbackEvent[];
}

export interface AgentRunFeedbackResponse {
  schema_version: 1;
  agent_run_id: string;
  idempotent: boolean;
  feedback: AgentFeedbackEvent | null;
  feedback_events: AgentFeedbackEvent[];
  handoff_case: HumanHandoffCase | null;
}

export interface AgentFeedbackStudioResponse {
  schema_version: 1;
  stats: {
    case_count: number;
    open_count: number;
    in_review_count: number;
    urgent_count: number;
    resolved_count: number;
    feedback_event_count: number;
  };
  cases: HumanHandoffCase[];
  generated_at: string;
}
