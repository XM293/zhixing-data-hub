export type ChannelBindingStatus = "unknown" | "bound" | "suspended";

export interface ChannelIdentityAccount {
  principal_id: string;
  account_key: string;
  display_name: string;
  login_name: string;
  organization: string;
  position: string;
}

export interface ChannelIdentityItem {
  id: string;
  channel_key: string;
  channel_label: string;
  external_tenant_key: string;
  external_identity_hint: string;
  external_identity_fingerprint: string;
  observed_display_name: string | null;
  principal_id: string | null;
  principal_name: string | null;
  principal_account_key: string | null;
  binding_status: ChannelBindingStatus;
  version: number;
  first_seen_at: string;
  last_seen_at: string;
  updated_at: string;
}

export interface ChannelIdentityEvent {
  id: string;
  event_type: string;
  channel_identity_id: string;
  actor_name: string;
  before_status: string;
  after_status: string;
  before_principal_name: string | null;
  after_principal_name: string | null;
  reason: string;
  request_id: string;
  run_id: string;
  occurred_at: string;
}

export interface ChannelIdentityAdminResponse {
  schema_version: 1;
  enterprise_id: string;
  stats: {
    total: number;
    bound: number;
    unknown: number;
    suspended: number;
    seen_last_24h: number;
    channel_count: number;
  };
  accounts: ChannelIdentityAccount[];
  items: ChannelIdentityItem[];
  recent_events: ChannelIdentityEvent[];
  generated_at: string;
}

export interface ChannelIdentityConfigureRequest {
  schema_version: 1;
  client_request_key: string;
  expected_version: number;
  principal_id: string | null;
  status: "active" | "suspended";
  reason: string;
}

export interface ChannelIdentityMutationResponse {
  schema_version: 1;
  operation: "configured";
  identity: ChannelIdentityItem;
  event_id: string;
  replayed: boolean;
}
