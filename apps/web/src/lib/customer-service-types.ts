export type CustomerServiceStatus =
  | "waiting"
  | "draft_ready"
  | "review_required"
  | "handed_off"
  | "resolved";

export type CustomerServiceRisk = "low" | "medium" | "high" | "critical";

export interface CustomerServiceConversation {
  schema_version: 1;
  id: string;
  enterprise_id: string;
  conversation_key: string;
  channel_key: string;
  external_conversation_id: string | null;
  source_system_key: string;
  customer_key: string;
  customer_name: string;
  order_key: string | null;
  store_scope_key: string;
  topic: string;
  status: CustomerServiceStatus;
  priority: "normal" | "high" | "urgent";
  sentiment: "calm" | "concerned" | "angry";
  risk_level: CustomerServiceRisk;
  risk_reason: string;
  assigned_principal_id: string | null;
  last_message_at: string;
  first_response_due_at: string;
  latest_sync_at: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string;
  message_count: number;
  draft_count: number;
  sla_overdue: boolean;
}

export interface CustomerServiceMessage {
  id: string;
  message_key: string;
  sender_type: "customer" | "agent" | "system";
  direction: "inbound" | "outbound";
  sender_name: string;
  content: string;
  delivery_status: string;
  occurred_at: string;
}

export interface CustomerServiceOrderContext {
  context_type: "order" | "pre-sale";
  order_key: string | null;
  order_status: string | null;
  paid_amount: number | null;
  currency: string;
  product_summary: string;
  item_quantity: number;
  payment_at: string | null;
  logistics_status: string | null;
  carrier: string | null;
  tracking_no: string | null;
  latest_logistics_event: string | null;
  promised_delivery_at: string | null;
  latest_logistics_at: string | null;
  delayed_hours: number;
  aftersale_status: string | null;
  source_system_key: string;
  payload_version: string;
  synced_at: string;
}

export interface CustomerServiceCanonicalFact {
  match_status: "matched" | "not_applicable" | "missing" | "scope_mismatch";
  match_reason: string;
  consistency_status: "consistent" | "conflict" | "not_checked";
  consistency_reason: string;
  material_conflict: boolean;
  differences: Array<{
    field: "order_status" | "paid_amount" | "item_count" | "refund_state";
    severity: "info" | "warning" | "critical";
    context_value: string | null;
    canonical_value: string | null;
    message: string;
  }>;
  order_key: string | null;
  customer_key: string | null;
  store_scope_key: string;
  external_store_key: string | null;
  order_status: string | null;
  paid_amount: number | null;
  cost_amount: number | null;
  gross_margin_rate: number | null;
  currency: string;
  item_count: number | null;
  refund_count: number;
  refund_amount: number;
  refund_statuses: string[];
  business_date: string | null;
  paid_at: string | null;
  source_system_key: string | null;
  sync_run_ids: string[];
  scope_mapping_id: string | null;
  mapping_version: string | null;
}

export interface CustomerServiceEvidence {
  ref: string;
  item_type: "order" | "logistics" | "order-fact" | "refund-fact" | "reconciliation" | "policy";
  label: string;
  version_ref: string | null;
  excerpt: string;
  locator: string | null;
}

export interface CustomerServiceReplyDraft {
  schema_version: 1;
  id: string;
  enterprise_id: string;
  conversation_id: string;
  version_number: number;
  status: "generated" | "sandbox_sent" | "rejected" | "superseded";
  body: string;
  risk_level: CustomerServiceRisk;
  risk_flags: string[];
  safe_to_send: boolean;
  suggested_action: "reply" | "investigate" | "handoff";
  evidence_refs: string[];
  evidence: CustomerServiceEvidence[];
  provider: string;
  model: string;
  execution_mode: "model" | "evidence-fallback";
  fallback_reason: string | null;
  evidence_snapshot_id: string;
  agent_run_id: string;
  role_twin_version_id: string;
  created_by_principal_id: string;
  approved_by_principal_id: string | null;
  approval_note: string | null;
  idempotency_key: string;
  request_id: string;
  run_id: string;
  created_at: string;
  approved_at: string | null;
}

export interface CustomerServiceEvent {
  id: string;
  event_type: "draft_generated" | "sandbox_reply_sent" | "handoff_created";
  reply_draft_id: string | null;
  actor_principal_id: string;
  actor_name: string;
  details: Record<string, unknown>;
  occurred_at: string;
}

export interface CustomerServiceStudio {
  schema_version: 1;
  data_mode: "database";
  channel_mode: "commerce-sandbox";
  actor_name: string;
  can_generate: boolean;
  can_send: boolean;
  can_handoff: boolean;
  stats: {
    waiting_count: number;
    review_required_count: number;
    handoff_count: number;
    overdue_count: number;
    safe_draft_count: number;
    total_count: number;
  };
  active_policy: {
    document_key: string;
    title: string;
    version_label: string;
    status: string;
    effective_from: string | null;
    resolved_at: string;
  };
  twin: {
    key: string;
    display_name: string;
    role_title: string;
    version_number: number;
    version_id: string;
    status: string;
  };
  conversations: CustomerServiceConversation[];
  drafts: CustomerServiceReplyDraft[];
  selected: {
    conversation: CustomerServiceConversation;
    messages: CustomerServiceMessage[];
    order_context: CustomerServiceOrderContext;
    canonical_order_fact: CustomerServiceCanonicalFact;
    drafts: CustomerServiceReplyDraft[];
    events: CustomerServiceEvent[];
  };
  generated_at: string;
}

export interface CustomerServiceMutationResponse {
  schema_version: 1;
  idempotent: boolean;
  studio: CustomerServiceStudio;
}
