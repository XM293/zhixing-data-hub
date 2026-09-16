export interface KnowledgePage {
  offset: number;
  limit: number;
  total: number;
}

export interface KnowledgeVersion {
  id: string;
  version_label: string;
  version_number: number;
  status: string;
  effective_from: string | null;
  effective_until: string | null;
  published_at: string | null;
  change_summary: string;
  chunk_count: number;
}

export interface KnowledgeDocument {
  id: string;
  key: string;
  title: string;
  document_type: string;
  knowledge_space: string;
  source_type: string;
  owner: string;
  tags: string[];
  status: string;
  content_hash: string;
  created_at: string;
  updated_at: string;
  versions: KnowledgeVersion[];
}

export interface KnowledgeDocumentListResponse {
  schema_version: 1;
  page: KnowledgePage;
  status_counts: Record<string, number>;
  version_count: number;
  chunk_count: number;
  items: KnowledgeDocument[];
  generated_at: string;
}

export interface KnowledgeConflict {
  conflict_type: string;
  severity: "warning" | "critical";
  related_version_id: string;
  related_version_label: string;
  heading: string;
  locator: string;
  summary: string;
}

export interface KnowledgeIngestionRun {
  id: string;
  document_key: string | null;
  document_title: string | null;
  version_id: string | null;
  version_label: string | null;
  actor_name: string;
  source_filename: string;
  content_hash: string;
  parser_provider: string;
  status: "completed" | "duplicate" | "failed";
  chunk_count: number;
  warnings: KnowledgeConflict[];
  error_code: string | null;
  request_id: string;
  run_id: string;
  created_at: string;
  finished_at: string;
}

export interface KnowledgeIngestionListResponse {
  schema_version: 1;
  stats: Record<string, number>;
  items: KnowledgeIngestionRun[];
  generated_at: string;
}

export interface KnowledgeIngestionResponse {
  schema_version: 1;
  duplicate: boolean;
  document: KnowledgeDocument;
  version: KnowledgeVersion;
  ingestion_run: KnowledgeIngestionRun;
}

export interface KnowledgeLifecycleResponse {
  schema_version: 1;
  document_key: string;
  version: KnowledgeVersion;
  event_id: string;
  event_type: "published" | "retired";
  idempotent: boolean;
  occurred_at: string;
}

export interface EvidenceItem {
  chunk_id: string;
  document_key: string;
  document_title: string;
  version_id: string;
  version_label: string;
  version_status: string;
  effective_from: string | null;
  heading: string;
  locator: string;
  excerpt: string;
  score: number;
}

export interface EvidenceSearchResponse {
  schema_version: 1;
  query: string;
  retrieval_provider: string;
  items: EvidenceItem[];
  generated_at: string;
}

export interface KnowledgeProviderDescriptor {
  key: string;
  label: string;
  protocol: string;
  mode: string;
  endpoint_fingerprint: string;
  authentication_configured: boolean;
}

export interface KnowledgeBenchmarkCase {
  key: string;
  category: string;
  query: string;
  expected_chunk_keys: string[];
  expected_document_keys: string[];
}

export interface KnowledgeProviderQueryResult {
  case_key: string;
  query: string;
  expected_chunk_keys: string[];
  returned_chunk_keys: string[];
  hit: boolean;
  reciprocal_rank: number;
  latency_ms: number;
  top_score: number;
}

export interface KnowledgeProviderEvaluationResult {
  provider_key: string;
  provider_mode: string;
  protocol: string;
  endpoint_fingerprint: string;
  status: "succeeded" | "failed";
  indexed_document_count: number;
  indexed_chunk_count: number;
  query_count: number;
  hit_count: number;
  recall_at_k: number;
  mean_reciprocal_rank: number;
  average_latency_ms: number;
  p95_latency_ms: number;
  items: KnowledgeProviderQueryResult[];
  failure_reason: string | null;
}

export interface KnowledgeProviderEvaluationRun {
  id: string;
  evaluation_key: string;
  benchmark_version: string;
  status: "running" | "completed" | "partial" | "failed";
  provider_keys: string[];
  document_count: number;
  chunk_count: number;
  case_count: number;
  actor_name: string;
  idempotent: boolean;
  request_id: string;
  run_id: string;
  started_at: string;
  finished_at: string | null;
  results: KnowledgeProviderEvaluationResult[];
}

export interface KnowledgeProviderOperationsResponse {
  schema_version: 1;
  data_mode: "database";
  benchmark_version: string;
  active_document_count: number;
  active_chunk_count: number;
  benchmark_cases: KnowledgeBenchmarkCase[];
  providers: KnowledgeProviderDescriptor[];
  runs: KnowledgeProviderEvaluationRun[];
  generated_at: string;
}

export interface RoleTwinProfile {
  key: string;
  display_name: string;
  role_title: string;
  capabilities: string[];
  provider: string;
  model: string;
  status: string;
  published_at: string | null;
  run_count: number;
  latest_run_at: string | null;
}

export interface TwinAnswerPayload {
  summary: string;
  facts: string[];
  actions: string[];
  caveats: string[];
  confidence: "high" | "medium" | "low";
}

export interface MetricContextPoint {
  as_of: string;
  value: number;
  change_rate: number | null;
}

export interface MetricContext {
  key: string;
  label: string;
  unit: string;
  scope_key: string;
  definition_version: string;
  date_from: string | null;
  date_to: string | null;
  latest_value: number | null;
  period_change_rate: number | null;
  minimum: number | null;
  maximum: number | null;
  points: MetricContextPoint[];
}

export interface TwinAnswerResponse {
  schema_version: 3;
  run_id: string;
  twin: RoleTwinProfile;
  question: string;
  answer: TwinAnswerPayload;
  evidence: EvidenceItem[];
  metric_context: MetricContext[];
  memory_context: Array<{
    id: string;
    memory_key: string;
    version_number: number;
    category: string;
    content: string;
    source_ref: string;
    effective_from: string | null;
  }>;
  execution_mode: "model" | "evidence-fallback";
  provider: string;
  model: string;
  duration_ms: number;
  created_at: string;
  workspace_key: string | null;
  runtime_session_id: string | null;
  runtime_turn_id: string | null;
}
