export interface JobAttempt {
  attempt_no: number;
  worker_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
}

export interface BackgroundJob {
  id: string;
  job_type: string;
  status: string;
  priority: number;
  attempt: number;
  max_attempts: number;
  continuation_count: number;
  continuation_progress: number;
  initiator_id: string;
  scope_type: string;
  scope_id: string;
  request_id: string;
  run_id: string;
  worker_id: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

export interface JobAdminResponse {
  stats: Record<string, number>;
  job_types: string[];
  items: BackgroundJob[];
  generated_at: string;
}

export interface JobDetailResponse {
  job: BackgroundJob;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  required_permissions: string[];
  permission_set_version: string;
  attempts: JobAttempt[];
}

export interface PlatformParameter {
  parameter_key: string;
  group_key: string;
  label: string;
  value_type: string;
  value: unknown;
  status: string;
  revision: number;
  updated_at: string;
}

export interface DictionaryItem {
  item_key: string;
  label: string;
  value: unknown;
  sort_order: number;
  status: string;
  revision: number;
}

export interface PlatformDictionary {
  dictionary_key: string;
  name: string;
  status: string;
  revision: number;
  items: DictionaryItem[];
}

export interface PlatformConfigResponse {
  parameters: PlatformParameter[];
  dictionaries: PlatformDictionary[];
  generated_at: string;
}

export interface NotificationItem {
  id: string;
  category: string;
  title: string;
  body: string;
  severity: string;
  status: string;
  action_route: string | null;
  created_at: string;
  read_at: string | null;
  deliveries: Record<string, string>;
}

export interface NotificationInboxResponse {
  stats: Record<string, number>;
  items: NotificationItem[];
  generated_at: string;
}

export interface FileAsset {
  id: string;
  asset_key: string;
  file_name: string;
  media_type: string;
  size_bytes: number;
  checksum_sha256: string;
  storage_provider: string;
  category: string;
  status: string;
  uploader_name: string;
  required_permission: string;
  scope_type: string;
  scope_id: string;
  revision: number;
  created_at: string;
}

export interface FileAssetListResponse {
  stats: Record<string, number>;
  items: FileAsset[];
  generated_at: string;
}

export interface BulkExchangeJob {
  id: string;
  operation: string;
  dataset_key: string;
  file_format: string;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  applied_rows: number;
  validation_summary: Record<string, unknown>;
  created_at: string;
  completed_at: string | null;
}

export interface BulkExchangeListResponse {
  datasets: string[];
  items: BulkExchangeJob[];
  generated_at: string;
}

export interface BulkExchangeRow {
  row_number: number;
  status: string;
  normalized_data: Record<string, unknown>;
  errors: Array<Record<string, unknown>>;
}

export interface BulkExchangeDetailResponse {
  job: BulkExchangeJob;
  rows: BulkExchangeRow[];
}

export interface OrgTreeNode {
  id: string;
  org_key: string;
  name: string;
  unit_type: string;
  status: string;
  member_count: number;
  children: OrgTreeNode[];
}

export interface PrincipalOption {
  id: string;
  display_name: string;
  account_key: string;
  organization: string;
  position: string;
}

export interface AccessDelegation {
  id: string;
  delegation_key: string;
  delegator_principal_id: string;
  delegator_name: string;
  delegatee_principal_id: string;
  delegatee_name: string;
  permissions: string[];
  scopes: Array<Record<string, unknown>>;
  status: string;
  valid_from: string;
  valid_to: string;
  reason: string;
  revision: number;
  created_at: string;
}

export interface AccessGovernanceResponse {
  org_tree: OrgTreeNode[];
  principals: PrincipalOption[];
  delegations: AccessDelegation[];
  permission_catalog: string[];
  generated_at: string;
}

export interface PermissionExplanation {
  principal_id: string;
  principal_name: string;
  direct_roles: string[];
  direct_permissions: string[];
  delegated_permissions: string[];
  effective_permissions: string[];
  scopes: Array<Record<string, unknown>>;
  active_delegations: string[];
  generated_at: string;
}
