export interface PageView {
  offset: number;
  limit: number;
  total: number;
}

export interface DataCenterResponseBase {
  schema_version: 1;
  data_mode: "database";
  page: PageView;
  generated_at: string;
}

export interface SyncRunItem {
  id: string;
  source_key: string;
  source_name: string;
  status: string;
  scenario: string;
  volume_profile: string;
  records_read: number;
  records_written: number;
  warning: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
}

export interface SyncRunListResponse extends DataCenterResponseBase {
  status_counts: Record<string, number>;
  items: SyncRunItem[];
}

export interface BusinessEntityItem {
  id: string;
  entity_type: string;
  canonical_key: string;
  display_name: string;
  status: string;
  attributes: Record<string, unknown>;
  attribute_count: number;
  updated_at: string;
}

export interface BusinessEntityListResponse extends DataCenterResponseBase {
  type_counts: Record<string, number>;
  items: BusinessEntityItem[];
}

export interface MetricCatalogItem {
  id: string;
  key: string;
  label: string;
  description: string;
  formula_expression: string;
  unit: string;
  dimensions: string[];
  owner: string;
  version: string;
  status: string;
  source_key: string | null;
  current_value: number | null;
  change_rate: number | null;
  as_of: string | null;
  updated_at: string;
}

export interface MetricCatalogResponse extends DataCenterResponseBase {
  status_counts: Record<string, number>;
  items: MetricCatalogItem[];
}

export interface MetricSeriesPoint {
  as_of: string;
  value: number;
  change_rate: number | null;
}

export interface MetricSeriesItem {
  key: string;
  label: string;
  unit: string;
  scope_key: string;
  definition_version: string;
  latest_value: number | null;
  period_change_rate: number | null;
  minimum: number | null;
  maximum: number | null;
  points: MetricSeriesPoint[];
}

export interface MetricSeriesResponse {
  schema_version: 1;
  data_mode: "database";
  scope_key: string;
  date_from: string | null;
  date_to: string | null;
  granularity: "day";
  series: MetricSeriesItem[];
  generated_at: string;
}

export interface DataQualityItem {
  id: string;
  key: string;
  name: string;
  description: string;
  category: string;
  asset_type: string;
  asset_key: string;
  expectation: string;
  severity: string;
  rule_status: string;
  result_status: string;
  observed_value: string | null;
  affected_records: number;
  details: Record<string, unknown>;
  sync_run_id: string | null;
  checked_at: string | null;
}

export interface CustomerServiceReconciliationIssue {
  conversation_key: string;
  customer_name: string;
  order_key: string | null;
  store_scope_key: string;
  topic: string;
  issue_type: "conflict" | "missing" | "scope_mismatch" | "context_missing";
  difference_fields: string[];
  material: boolean;
  href: string;
}

export interface CustomerServiceReconciliationQualityDetails {
  conversation_count: number;
  order_conversation_count: number;
  matched_count: number;
  consistent_count: number;
  conflict_count: number;
  missing_count: number;
  scope_mismatch_count: number;
  context_missing_count: number;
  not_applicable_count: number;
  issues: CustomerServiceReconciliationIssue[];
}

export interface DataQualityResponse extends DataCenterResponseBase {
  result_counts: Record<string, number>;
  items: DataQualityItem[];
}

export interface CommerceOperationsSummary {
  order_count: number;
  order_line_count: number;
  paid_gmv_yuan: number;
  gross_margin_rate: number;
  refund_count: number;
  refund_amount_yuan: number;
  refund_rate: number;
  inventory_sku_count: number;
  inventory_value_yuan: number;
  low_stock_sku_count: number;
  advertising_spend_yuan: number;
  attributed_revenue_yuan: number;
  advertising_roi: number;
}

export interface CommerceFunnelStep {
  key: string;
  label: string;
  count: number;
  amount_yuan: number;
  conversion_rate: number;
}

export interface CommerceStorePerformance {
  store_key: string;
  store_name: string;
  channel: string;
  order_count: number;
  paid_gmv_yuan: number;
  gross_margin_rate: number;
  refund_count: number;
  refund_rate: number;
  advertising_spend_yuan: number;
  attributed_revenue_yuan: number;
  advertising_roi: number;
}

export interface CommerceException {
  key: string;
  exception_type: string;
  severity: "warning" | "critical";
  title: string;
  detail: string;
  value: number;
  unit: string;
  related_keys: string[];
  source_key: string;
  sync_run_id: string;
}

export interface CommerceOrder {
  order_key: string;
  store_key: string;
  store_name: string;
  customer_key: string;
  channel: string;
  status: string;
  business_date: string;
  paid_amount_yuan: number;
  gross_margin_yuan: number;
  item_count: number;
  province: string;
  source_key: string;
  sync_run_id: string;
}

export interface CommerceLineageAsset {
  key: string;
  label: string;
  table_name: string;
  record_count: number;
  source_key: string;
  source_schema_version: string;
  mapping_version: string;
  latest_sync_run_id: string | null;
}

export interface CommerceOperationsResponse {
  schema_version: 1;
  data_mode: "database";
  scope_key: string;
  business_date_from: string | null;
  business_date_to: string | null;
  summary: CommerceOperationsSummary;
  funnel: CommerceFunnelStep[];
  stores: CommerceStorePerformance[];
  exceptions: CommerceException[];
  recent_orders: CommerceOrder[];
  lineage: CommerceLineageAsset[];
  generated_at: string;
}

export interface Customer360Summary {
  profile_count: number;
  active_customer_count: number;
  consented_customer_count: number;
  at_risk_customer_count: number;
  purchasing_customer_count: number;
  repeat_customer_count: number;
  repeat_purchase_rate: number;
  paid_gmv_yuan: number;
  average_customer_value_yuan: number;
  touchpoint_count: number;
}

export interface Customer360Segment {
  key: string;
  label: string;
  customer_count: number;
  purchasing_customer_count: number;
  paid_gmv_yuan: number;
  average_order_count: number;
  at_risk_customer_count: number;
}

export interface Customer360Channel {
  key: string;
  label: string;
  customer_count: number;
  touchpoint_count: number;
  purchasing_customer_count: number;
  paid_gmv_yuan: number;
}

export interface Customer360TrendPoint {
  business_date: string;
  touchpoint_count: number;
  active_customer_count: number;
}

export interface Customer360Customer {
  customer_key: string;
  display_name: string;
  home_store_key: string;
  home_store_name: string;
  member_level: string;
  lifecycle_stage: string;
  status: string;
  province: string;
  acquisition_channel: string;
  preferred_category: string;
  churn_risk_score: number;
  consent_status: string;
  member_points: number;
  growth_value: number;
  tags: string[];
  registered_at: string;
  last_active_at: string;
  order_count: number;
  paid_gmv_yuan: number;
  refund_amount_yuan: number;
  last_order_at: string | null;
  touchpoint_count: number;
  last_touchpoint_at: string | null;
  source_key: string;
  sync_run_id: string;
}

export interface Customer360Touchpoint {
  touchpoint_key: string;
  customer_key: string;
  customer_name: string;
  store_key: string;
  touchpoint_type: string;
  channel: string;
  occurred_at: string;
  campaign_key: string | null;
  value_yuan: number;
  properties: Record<string, unknown>;
  source_key: string;
  sync_run_id: string;
}

export interface Customer360LineageAsset {
  key: string;
  label: string;
  table_name: string;
  record_count: number;
  source_key: string;
  source_schema_version: string;
  mapping_version: string;
  latest_sync_run_id: string | null;
}

export interface Customer360Response {
  schema_version: 1;
  data_mode: "database";
  scope_key: string;
  summary: Customer360Summary;
  segments: Customer360Segment[];
  channels: Customer360Channel[];
  touchpoint_trend: Customer360TrendPoint[];
  customers: Customer360Customer[];
  recent_touchpoints: Customer360Touchpoint[];
  lineage: Customer360LineageAsset[];
  generated_at: string;
}

export interface CustomerDetailSummary {
  lifetime_order_count: number;
  paid_gmv_yuan: number;
  average_order_value_yuan: number;
  refund_count: number;
  refund_amount_yuan: number;
  refund_rate: number;
  touchpoint_count: number;
  days_since_last_active: number;
  days_since_last_order: number | null;
  engagement_eligible: boolean;
  risk_level: "low" | "medium" | "high";
}

export interface CustomerDetailOrder {
  order_key: string;
  store_key: string;
  store_name: string;
  channel: string;
  status: string;
  business_date: string;
  paid_at: string;
  shipped_at: string | null;
  paid_amount_yuan: number;
  gross_margin_yuan: number;
  gross_margin_rate: number;
  item_count: number;
  source_key: string;
  sync_run_id: string;
}

export interface CustomerDetailRefund {
  refund_key: string;
  order_key: string;
  sku_key: string;
  reason_category: string;
  status: string;
  requested_at: string;
  completed_at: string | null;
  refund_amount_yuan: number;
  quantity: number;
  source_key: string;
  sync_run_id: string;
}

export interface CustomerDetailTimelineEvent {
  event_key: string;
  event_type: "profile" | "order" | "refund" | "touchpoint";
  occurred_at: string;
  title: string;
  detail: string;
  value_yuan: number | null;
  source_key: string;
  sync_run_id: string;
  evidence_key: string;
}

export interface CustomerDetailRecommendation {
  key: string;
  title: string;
  priority: "critical" | "high" | "medium" | "low";
  rationale: string;
  objective: string;
  action_boundary: string;
  eligible: boolean;
  evidence_keys: string[];
}

export interface CustomerDetailResponse {
  schema_version: 1;
  data_mode: "database";
  scope_key: string;
  customer_key: string;
  recommendation_mode: "deterministic_playbook";
  playbook_version: string;
  profile: Customer360Customer;
  summary: CustomerDetailSummary;
  recommendations: CustomerDetailRecommendation[];
  timeline: CustomerDetailTimelineEvent[];
  orders: CustomerDetailOrder[];
  refunds: CustomerDetailRefund[];
  touchpoints: Customer360Touchpoint[];
  lineage: Customer360LineageAsset[];
  generated_at: string;
}

export type DataCenterView = "commerce" | "sync-runs" | "entities" | "metrics" | "quality";
