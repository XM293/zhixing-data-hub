"use client";

import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Boxes,
  ChartNoAxesCombined,
  CircleDashed,
  CircleAlert,
  Database,
  Layers3,
  PackageSearch,
  ReceiptText,
  RefreshCw,
  Search,
  ShieldCheck,
  ShoppingCart,
  TrendingUp,
  Warehouse
} from "lucide-react";
import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";

import { PageHeader, StatusBadge } from "@/components/console/ui";
import { CanonicalFactsPanel } from "@/components/data-center/canonical-facts-panel";
import { useExperience } from "@/demo/experience-provider";
import { apiErrorMessage } from "@/lib/api-error";
import { apiFetch } from "@/lib/api-client";
import type {
  BusinessEntityListResponse,
  CommerceOperationsResponse,
  DataCenterResponseBase,
  DataCenterView,
  CustomerServiceReconciliationQualityDetails,
  DataQualityResponse,
  MetricCatalogItem,
  MetricCatalogResponse,
  SyncRunListResponse
} from "@/lib/data-center-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const PAGE_SIZE = 20;
const ENTITY_TYPE_LABELS: Record<string, string> = {
  customer: "客户",
  order: "订单",
  product: "商品",
  sku: "SKU",
  store: "店铺",
  warehouse: "仓库"
};
const ATTRIBUTE_LABELS: Record<string, string> = {
  available_stock: "可售库存",
  brand: "品牌",
  capacity: "容量",
  category: "分类",
  channel: "渠道",
  customer_code: "客户编码",
  manager: "负责人",
  order_state: "订单状态",
  owner_team: "责任团队",
  paid_amount_fen: "实付金额",
  product_code: "商品编码",
  province: "省份",
  region: "区域",
  safety_stock: "安全库存",
  segment: "客群",
  store_code: "店铺编码",
  total_orders: "累计订单",
  warehouse_code: "仓库编码"
};

const RECONCILIATION_FIELD_LABELS: Record<string, string> = {
  order_status: "订单状态",
  paid_amount: "实付金额",
  item_count: "商品件数",
  refund_state: "退款状态"
};

const RECONCILIATION_ISSUE_LABELS: Record<string, string> = {
  conflict: "跨源冲突",
  missing: "订单待同步",
  scope_mismatch: "范围映射不符",
  context_missing: "客服上下文缺失"
};

function useDataCenterResource<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    apiFetch(`${API_BASE_URL}${path}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiErrorMessage(response, "数据中心接口不可用"));
        return response.json() as Promise<T>;
      })
      .then(setData)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "无法读取数据中心");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, reloadToken]);

  return { data, loading, error, reload: useCallback(() => setReloadToken((value) => value + 1), []) };
}

function buildPath(endpoint: string, options: Record<string, string | number | null>): string {
  const params = new URLSearchParams();
  Object.entries(options).forEach(([key, value]) => {
    if (value !== null && value !== "") params.set(key, String(value));
  });
  return `/api/v1/data-center/${endpoint}?${params.toString()}`;
}

function formatTime(value: string | null): string {
  if (!value) return "尚无数据";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function formatDuration(value: number | null): string {
  if (value === null) return "运行中";
  if (value < 1) return `${Math.round(value * 1000)}ms`;
  if (value < 60) return `${value.toFixed(1)}s`;
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function statusTone(value: string): "positive" | "warning" | "critical" | "info" | "neutral" {
  if (["succeeded", "passed", "published", "active", "connected", "paid", "shipped", "completed"].includes(value)) return "positive";
  if (["partial", "warning", "delayed", "running", "refunding"].includes(value)) return "warning";
  if (["failed", "critical", "disconnected", "cancelled"].includes(value)) return "critical";
  if (value === "pending") return "info";
  return "neutral";
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    succeeded: "成功",
    partial: "部分完成",
    failed: "失败",
    running: "运行中",
    passed: "通过",
    warning: "警告",
    pending: "待检查",
    published: "已发布",
    active: "有效",
    inactive: "停用"
  };
  return labels[value] ?? value;
}

function entityTypeLabel(value: string): string {
  return ENTITY_TYPE_LABELS[value] ?? value;
}

function attributeValue(key: string, value: unknown): string {
  if (key === "paid_amount_fen" && typeof value === "number") {
    return `${new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(value / 100)}`;
  }
  return String(value);
}

function DataPageState({ loading, error }: { loading: boolean; error: string | null }) {
  if (loading) return <div className="database-page-state"><Database className="spinning" size={27} /><strong>正在读取数据库</strong><span>汇总当前筛选范围内的企业数据</span></div>;
  if (error) return <div className="database-page-state failed" role="alert"><AlertTriangle size={28} /><strong>数据读取失败</strong><span>{error}</span></div>;
  return <div className="database-page-state"><CircleDashed size={27} /><strong>当前没有数据</strong><span>调整筛选条件或执行新的同步批次</span></div>;
}

function DataToolbar({
  query,
  setQuery,
  status,
  setStatus,
  statusOptions,
  onRefresh,
  extra
}: {
  query: string;
  setQuery: (value: string) => void;
  status: string;
  setStatus: (value: string) => void;
  statusOptions: Array<{ value: string; label: string }>;
  onRefresh: () => void;
  extra?: React.ReactNode;
}) {
  return (
    <div className="data-toolbar">
      <label className="data-search"><Search aria-hidden="true" size={16} /><input aria-label="搜索当前数据" onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、编码或运行 ID" value={query} /></label>
      <label><span>状态</span><select onChange={(event) => setStatus(event.target.value)} value={status}><option value="">全部状态</option>{statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      {extra}
      <button aria-label="刷新数据库结果" className="icon-button data-refresh" onClick={onRefresh} title="刷新数据库结果" type="button"><RefreshCw aria-hidden="true" size={16} /></button>
    </div>
  );
}

function DataPagination({ page, setOffset }: { page: DataCenterResponseBase["page"]; setOffset: (value: number) => void }) {
  const start = page.total === 0 ? 0 : page.offset + 1;
  const end = Math.min(page.offset + page.limit, page.total);
  return (
    <footer className="data-pagination">
      <span>显示 {start}-{end} / 共 {page.total} 条</span>
      <div>
        <button aria-label="上一页" disabled={page.offset === 0} onClick={() => setOffset(Math.max(page.offset - page.limit, 0))} title="上一页" type="button"><ArrowLeft size={15} /></button>
        <button aria-label="下一页" disabled={page.offset + page.limit >= page.total} onClick={() => setOffset(page.offset + page.limit)} title="下一页" type="button"><ArrowRight size={15} /></button>
      </div>
    </footer>
  );
}

function StatBand({ items }: { items: Array<{ label: string; value: number; note: string; tone?: string }> }) {
  return <section className="database-stat-band">{items.map((item) => <article className={item.tone ?? ""} key={item.label}><span>{item.label}</span><strong>{formatNumber(item.value)}</strong><p>{item.note}</p></article>)}</section>;
}

function SyncRunsPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const deferredQuery = useDeferredValue(query);
  const path = useMemo(() => buildPath("sync-runs", { query: deferredQuery, status, offset, limit: PAGE_SIZE }), [deferredQuery, status, offset]);
  const { data, loading, error, reload } = useDataCenterResource<SyncRunListResponse>(path);
  const counts = data?.status_counts ?? {};
  return (
    <DatabasePageFrame description="按来源追踪每个同步批次的读取量、写入量、耗时、告警与错误。" eyebrow="DATA OPERATIONS · DATABASE VIEW" generatedAt={data?.generated_at ?? null} title="同步任务与运行批次">
      <StatBand items={[
        { label: "全部批次", value: Object.values(counts).reduce((sum, value) => sum + value, 0), note: "数据库历史运行" },
        { label: "成功", value: counts.succeeded ?? 0, note: "完整写入", tone: "positive" },
        { label: "部分完成", value: counts.partial ?? 0, note: "保留可用资源", tone: "warning" },
        { label: "失败", value: counts.failed ?? 0, note: "可追踪错误", tone: "critical" }
      ]} />
      <section className="database-table-panel">
        <header><h2>同步运行记录</h2><DataToolbar onRefresh={reload} query={query} setQuery={(value) => { setQuery(value); setOffset(0); }} status={status} setStatus={(value) => { setStatus(value); setOffset(0); }} statusOptions={[{ value: "succeeded", label: "成功" }, { value: "partial", label: "部分完成" }, { value: "failed", label: "失败" }, { value: "running", label: "运行中" }]} /></header>
        {!data?.items.length ? <DataPageState error={error} loading={loading} /> : <div className="table-wrap"><table><thead><tr><th>运行批次</th><th>来源 / 场景</th><th>读取</th><th>写入</th><th>耗时</th><th>开始时间</th><th>状态</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.id}><td><strong className="database-primary">{item.id}</strong>{item.error || item.warning ? <small className="row-issue">{item.error ?? item.warning}</small> : null}</td><td><strong>{item.source_name}</strong><small>{item.scenario} · {item.volume_profile} · {item.source_key}</small></td><td>{formatNumber(item.records_read)}</td><td>{formatNumber(item.records_written)}</td><td>{formatDuration(item.duration_seconds)}</td><td>{formatTime(item.started_at)}</td><td><StatusBadge value={{ label: statusLabel(item.status), tone: statusTone(item.status) }} /></td></tr>)}</tbody></table></div>}
        {data ? <DataPagination page={data.page} setOffset={setOffset} /> : null}
      </section>
    </DatabasePageFrame>
  );
}

function EntitiesPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [entityType, setEntityType] = useState("");
  const [offset, setOffset] = useState(0);
  const deferredQuery = useDeferredValue(query);
  const path = useMemo(() => buildPath("entities", { query: deferredQuery, status, entity_type: entityType, offset, limit: PAGE_SIZE }), [deferredQuery, status, entityType, offset]);
  const { data, loading, error, reload } = useDataCenterResource<BusinessEntityListResponse>(path);
  const typeCounts = data?.type_counts ?? {};
  return (
    <DatabasePageFrame description="使用稳定企业 ID 汇聚不同来源的店铺、商品、客户、订单与仓库主数据。" eyebrow="MASTER DATA · DATABASE VIEW" generatedAt={data?.generated_at ?? null} title="企业实体与统一标识">
      <StatBand items={[
        { label: "实体总量", value: Object.values(typeCounts).reduce((sum, value) => sum + value, 0), note: "当前标准化对象" },
        { label: "店铺", value: typeCounts.store ?? 0, note: "跨平台统一店铺", tone: "positive" },
        { label: "商品 / SKU", value: (typeCounts.product ?? 0) + (typeCounts.sku ?? 0), note: `${typeCounts.product ?? 0} 商品 · ${typeCounts.sku ?? 0} SKU` },
        { label: "客户 / 订单", value: (typeCounts.customer ?? 0) + (typeCounts.order ?? 0), note: `${typeCounts.customer ?? 0} 客户 · ${typeCounts.order ?? 0} 订单`, tone: "warning" }
      ]} />
      <section className="database-table-panel">
        <header><h2>统一实体目录</h2><DataToolbar extra={<label><span>类型</span><select onChange={(event) => { setEntityType(event.target.value); setOffset(0); }} value={entityType}><option value="">全部类型</option>{Object.keys(typeCounts).map((key) => <option key={key} value={key}>{entityTypeLabel(key)}</option>)}</select></label>} onRefresh={reload} query={query} setQuery={(value) => { setQuery(value); setOffset(0); }} status={status} setStatus={(value) => { setStatus(value); setOffset(0); }} statusOptions={[{ value: "active", label: "有效" }, { value: "inactive", label: "停用" }]} /></header>
        {!data?.items.length ? <DataPageState error={error} loading={loading} /> : <div className="table-wrap"><table><thead><tr><th>企业实体</th><th>类型</th><th>稳定业务键</th><th>标准属性</th><th>更新时间</th><th>状态</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.id}><td><strong className="database-primary">{item.display_name}</strong><small>{item.id}</small></td><td>{entityTypeLabel(item.entity_type)}</td><td><code>{item.canonical_key}</code></td><td><div className="attribute-tags">{Object.entries(item.attributes).map(([key, value]) => <span key={key}>{ATTRIBUTE_LABELS[key] ?? key}: {attributeValue(key, value)}</span>)}</div></td><td>{formatTime(item.updated_at)}</td><td><StatusBadge value={{ label: statusLabel(item.status), tone: statusTone(item.status) }} /></td></tr>)}</tbody></table></div>}
        {data ? <DataPagination page={data.page} setOffset={setOffset} /> : null}
      </section>
    </DatabasePageFrame>
  );
}

function formatMetric(item: MetricCatalogItem): string {
  if (item.current_value === null) return "尚无快照";
  if (item.unit === "元" && item.current_value >= 10000) return `${(item.current_value / 10000).toFixed(1)} 万元`;
  return `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(item.current_value)} ${item.unit}`;
}

function MetricsPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const deferredQuery = useDeferredValue(query);
  const path = useMemo(() => buildPath("metrics", { query: deferredQuery, status, offset, limit: PAGE_SIZE }), [deferredQuery, status, offset]);
  const { data, loading, error, reload } = useDataCenterResource<MetricCatalogResponse>(path);
  const activeSnapshots = data?.items.filter((item) => item.current_value !== null).length ?? 0;
  const dimensionCount = new Set(data?.items.flatMap((item) => item.dimensions) ?? []).size;
  return (
    <DatabasePageFrame description="先治理指标口径、版本和维度，再向驾驶舱、智能分析与角色分身开放。" eyebrow="METRIC CATALOG · DATABASE VIEW" generatedAt={data?.generated_at ?? null} title="经营指标目录">
      <StatBand items={[
        { label: "指标定义", value: data?.page.total ?? 0, note: "版本化口径" },
        { label: "已发布", value: data?.status_counts.published ?? 0, note: "可供分析使用", tone: "positive" },
        { label: "当前有值", value: activeSnapshots, note: "最新快照可用" },
        { label: "覆盖维度", value: dimensionCount, note: "当前页去重维度" }
      ]} />
      <section className="database-catalog-panel">
        <header><h2>已治理指标</h2><DataToolbar onRefresh={reload} query={query} setQuery={(value) => { setQuery(value); setOffset(0); }} status={status} setStatus={(value) => { setStatus(value); setOffset(0); }} statusOptions={[{ value: "published", label: "已发布" }, { value: "draft", label: "草稿" }, { value: "deprecated", label: "已废止" }]} /></header>
        {!data?.items.length ? <DataPageState error={error} loading={loading} /> : <div className="metric-catalog-grid">{data.items.map((item) => <article key={item.id}><header><div><span>{item.key}</span><h3>{item.label}</h3></div><StatusBadge value={{ label: statusLabel(item.status), tone: statusTone(item.status) }} /></header><strong>{formatMetric(item)}</strong><p>{item.description}</p><code>{item.formula_expression}</code><dl><div><dt>版本 / 责任方</dt><dd>{item.version} · {item.owner}</dd></div><div><dt>数据时间</dt><dd>{formatTime(item.as_of)}</dd></div></dl><div className="dimension-tags">{item.dimensions.map((dimension) => <span key={dimension}>{dimension}</span>)}</div></article>)}</div>}
        {data ? <DataPagination page={data.page} setOffset={setOffset} /> : null}
      </section>
    </DatabasePageFrame>
  );
}

function QualityPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [offset, setOffset] = useState(0);
  const deferredQuery = useDeferredValue(query);
  const path = useMemo(() => buildPath("quality", { query: deferredQuery, status, category, offset, limit: PAGE_SIZE }), [deferredQuery, status, category, offset]);
  const { data, loading, error, reload } = useDataCenterResource<DataQualityResponse>(path);
  const counts = data?.result_counts ?? {};
  const reconciliationItem = data?.items.find(
    (item) => item.key === "customer-service-order-reconciliation"
  );
  const reconciliation = reconciliationDetails(reconciliationItem?.details);
  return (
    <DatabasePageFrame description="把契约、完整性、映射、指标、同步健康和跨源业务对账集中为可追溯检查。" eyebrow="DATA QUALITY · DATABASE VIEW" generatedAt={data?.generated_at ?? null} title="数据质量控制台">
      <StatBand items={[
        { label: "规则总数", value: Object.values(counts).reduce((sum, value) => sum + value, 0), note: "有效质量规则" },
        { label: "通过", value: counts.passed ?? 0, note: "最近检查通过", tone: "positive" },
        { label: "警告", value: counts.warning ?? 0, note: "可用但需处理", tone: "warning" },
        { label: "失败 / 待检查", value: (counts.failed ?? 0) + (counts.pending ?? 0), note: "阻断或尚未运行", tone: "critical" }
      ]} />
      <div className="quality-workspace">
      {reconciliationItem && reconciliation ? (
        <section className={`quality-reconciliation-panel ${reconciliationItem.result_status}`}>
          <header>
            <div>
              <span>CROSS-SOURCE RECONCILIATION</span>
              <h2>跨源客服订单对账</h2>
              <p>{reconciliationItem.observed_value}</p>
            </div>
            <StatusBadge value={{ label: statusLabel(reconciliationItem.result_status), tone: statusTone(reconciliationItem.result_status) }} />
          </header>
          <div className="quality-reconciliation-kpis">
            <article><span>订单会话</span><strong>{reconciliation.order_conversation_count}</strong><small>{reconciliation.not_applicable_count} 个售前无需对账</small></article>
            <article><span>已建立关联</span><strong>{reconciliation.matched_count}</strong><small>订单、客户和门店映射通过</small></article>
            <article><span>字段一致</span><strong>{reconciliation.consistent_count}</strong><small>状态、金额、件数与退款一致</small></article>
            <article className={reconciliation.conflict_count ? "critical" : ""}><span>重大冲突</span><strong>{reconciliation.conflict_count}</strong><small>阻止 AI 草稿发送</small></article>
            <article className={reconciliation.missing_count + reconciliation.scope_mismatch_count + reconciliation.context_missing_count ? "warning" : ""}><span>待补数 / 映射</span><strong>{reconciliation.missing_count + reconciliation.scope_mismatch_count + reconciliation.context_missing_count}</strong><small>缺失、越界或上下文缺口</small></article>
          </div>
          <div className="quality-reconciliation-queue">
            <header><strong>影响会话队列</strong><span>{reconciliation.issues.length} 项 · {reconciliationItem.sync_run_id}</span></header>
            {reconciliation.issues.length ? reconciliation.issues.map((issue) => (
              <article key={issue.conversation_key}>
                <div><strong>{issue.customer_name} · {issue.topic}</strong><code>{issue.conversation_key}</code></div>
                <div><span>{issue.order_key ?? "无订单键"}</span><small>{issue.store_scope_key}</small></div>
                <div className="quality-reconciliation-fields">
                  {issue.difference_fields.length ? issue.difference_fields.map((field) => <span key={field}>{RECONCILIATION_FIELD_LABELS[field] ?? field}</span>) : <span>{RECONCILIATION_ISSUE_LABELS[issue.issue_type] ?? issue.issue_type}</span>}
                </div>
                <StatusBadge value={{ label: RECONCILIATION_ISSUE_LABELS[issue.issue_type] ?? issue.issue_type, tone: issue.material ? "critical" : "warning" }} />
              </article>
            )) : <div className="quality-reconciliation-empty"><ShieldCheck aria-hidden="true" size={18} /><span>当前批次没有需要处理的客服订单差异</span></div>}
          </div>
        </section>
      ) : null}
      <section className="database-table-panel quality-table-panel">
        <header><h2>质量规则与最近结果</h2><DataToolbar extra={<label><span>类别</span><select onChange={(event) => { setCategory(event.target.value); setOffset(0); }} value={category}><option value="">全部类别</option>{["validity", "completeness", "mapping", "coverage", "freshness", "reconciliation"].map((key) => <option key={key} value={key}>{key}</option>)}</select></label>} onRefresh={reload} query={query} setQuery={(value) => { setQuery(value); setOffset(0); }} status={status} setStatus={(value) => { setStatus(value); setOffset(0); }} statusOptions={[{ value: "passed", label: "通过" }, { value: "warning", label: "警告" }, { value: "failed", label: "失败" }, { value: "pending", label: "待检查" }]} /></header>
        {!data?.items.length ? <DataPageState error={error} loading={loading} /> : <div className="table-wrap"><table><thead><tr><th>质量规则</th><th>类别 / 影响资产</th><th>期望</th><th>观测结果</th><th>影响记录</th><th>检查时间</th><th>状态</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.id}><td><strong className="database-primary">{item.name}</strong><small>{item.key} · {item.severity}</small></td><td><strong>{item.category}</strong><small>{item.asset_type} / {item.asset_key}</small></td><td>{item.expectation}</td><td>{item.observed_value ?? "尚未运行"}{item.sync_run_id ? <small>{item.sync_run_id}</small> : null}</td><td>{formatNumber(item.affected_records)}</td><td>{formatTime(item.checked_at)}</td><td><StatusBadge value={{ label: statusLabel(item.result_status), tone: statusTone(item.result_status) }} /></td></tr>)}</tbody></table></div>}
        {data ? <DataPagination page={data.page} setOffset={setOffset} /> : null}
      </section>
      </div>
    </DatabasePageFrame>
  );
}

function reconciliationDetails(
  value: Record<string, unknown> | undefined
): CustomerServiceReconciliationQualityDetails | null {
  if (!value || !Array.isArray(value.issues)) return null;
  const numericKeys = [
    "conversation_count",
    "order_conversation_count",
    "matched_count",
    "consistent_count",
    "conflict_count",
    "missing_count",
    "scope_mismatch_count",
    "context_missing_count",
    "not_applicable_count"
  ] as const;
  if (numericKeys.some((key) => typeof value[key] !== "number")) return null;
  return value as unknown as CustomerServiceReconciliationQualityDetails;
}

function formatCurrency(value: number): string {
  if (Math.abs(value) >= 10000) return `¥${(value / 10000).toFixed(1)}万`;
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0
  }).format(value);
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function commerceStatusLabel(value: string): string {
  const labels: Record<string, string> = {
    paid: "已支付",
    shipped: "已发货",
    completed: "已完成",
    refunding: "退款中",
    cancelled: "已取消"
  };
  return labels[value] ?? value;
}

function exceptionTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    inventory: "库存",
    refund: "退款",
    advertising: "投放",
    margin: "毛利"
  };
  return labels[value] ?? value;
}

type CommercePageMode = "facts" | "stores";

function CommerceOperationsPage({ mode = "facts", scopeKey }: { mode?: CommercePageMode; scopeKey: string }) {
  const isStoreCenter = mode === "stores";
  const effectiveScope = scopeKey;
  const path = `/api/v1/data-center/commerce-operations?scope_key=${encodeURIComponent(effectiveScope)}`;
  const { data, loading, error, reload } = useDataCenterResource<CommerceOperationsResponse>(path);
  const scopeControl = null;
  if (!data) {
    return (
      <DatabasePageFrame
        actions={scopeControl}
        description={isStoreCenter ? "查看渠道授权、店铺经营状态和当前业务范围。" : "汇总订单、退款、库存和广告的规范事实，并保留同步批次与来源追踪。"}
        eyebrow={isStoreCenter ? "渠道与店铺" : "CANONICAL COMMERCE FACTS · 0030"}
        generatedAt={null}
        meta={isStoreCenter ? "经营数据实时读取" : undefined}
        scopeLabel={effectiveScope === "enterprise" ? "企业全域" : effectiveScope}
        title={isStoreCenter ? "渠道与店铺" : "电商经营事实台"}
      >
        <DataPageState error={error} loading={loading} />
      </DatabasePageFrame>
    );
  }

  const summary = data.summary;
  const statItems = [
    {
      key: "gmv",
      label: "实付成交",
      value: formatCurrency(summary.paid_gmv_yuan),
      note: `${formatNumber(summary.order_count)} 单 · ${formatNumber(summary.order_line_count)} 行`,
      icon: ShoppingCart,
      tone: "green"
    },
    {
      key: "margin",
      label: "订单毛利率",
      value: formatPercent(summary.gross_margin_rate),
      note: "按实付金额减订单成本",
      icon: TrendingUp,
      tone: "blue"
    },
    {
      key: "refund",
      label: "退款金额率",
      value: formatPercent(summary.refund_rate),
      note: `${summary.refund_count} 笔 · ${formatCurrency(summary.refund_amount_yuan)}`,
      icon: ReceiptText,
      tone: summary.refund_rate > 0.08 ? "red" : "amber"
    },
    {
      key: "inventory",
      label: "库存资产",
      value: formatCurrency(summary.inventory_value_yuan),
      note: `${summary.inventory_sku_count} SKU · ${summary.low_stock_sku_count} 低库存`,
      icon: Warehouse,
      tone: "teal"
    },
    {
      key: "ad-spend",
      label: "广告消耗",
      value: formatCurrency(summary.advertising_spend_yuan),
      note: `归因成交 ${formatCurrency(summary.attributed_revenue_yuan)}`,
      icon: Activity,
      tone: "violet"
    },
    {
      key: "ad-roi",
      label: "广告归因 ROI",
      value: summary.advertising_roi.toFixed(2),
      note: "归因成交 / 广告消耗",
      icon: ChartNoAxesCombined,
      tone: summary.advertising_roi < 2.5 ? "red" : "green"
    }
  ];

  return (
    <DatabasePageFrame
      actions={scopeControl}
      description={isStoreCenter ? "查看渠道授权、店铺经营状态和当前业务范围。" : "从原始来源映射为订单、订单行、退款、库存快照和广告日绩效，支持经营核对与 AI 明细分析。"}
      eyebrow={isStoreCenter ? "渠道与店铺" : "CANONICAL COMMERCE FACTS · 0030"}
      generatedAt={data.generated_at}
      meta={isStoreCenter ? "经营数据实时读取" : undefined}
      scopeLabel={effectiveScope === "enterprise" ? "企业全域" : effectiveScope}
      title={isStoreCenter ? "渠道与店铺" : "电商经营事实台"}
    >
      <section aria-label="经营事实汇总" className="commerce-fact-kpis">
        {statItems.map((item) => {
          const Icon = item.icon;
          return (
            <article className={item.tone} key={item.key}>
              <header><Icon aria-hidden="true" size={17} /><span>{item.label}</span></header>
              <strong>{item.value}</strong>
              <p>{item.note}</p>
            </article>
          );
        })}
      </section>

      <div className="commerce-fact-workspace">
      <div className="commerce-fact-primary-grid">
        <section className="commerce-fact-panel commerce-store-panel">
          <header className="commerce-panel-heading">
            <div><span>STORE CONTRIBUTION</span><h2>店铺经营贡献</h2></div>
            <button aria-label="刷新经营事实" className="icon-button" onClick={reload} title="刷新经营事实" type="button"><RefreshCw size={16} /></button>
          </header>
          <div className="commerce-store-table"><table><thead><tr><th>店铺 / 渠道</th><th>订单</th><th>实付成交</th><th>毛利率</th><th>退款率</th><th>广告消耗</th><th>ROI</th></tr></thead><tbody>{data.stores.map((store) => <tr key={store.store_key}><td><strong>{store.store_name}</strong><small>{store.channel} · {store.store_key}</small></td><td>{formatNumber(store.order_count)}</td><td>{formatCurrency(store.paid_gmv_yuan)}</td><td>{formatPercent(store.gross_margin_rate)}</td><td className={store.refund_rate > 0.08 ? "negative" : ""}>{formatPercent(store.refund_rate)}</td><td>{formatCurrency(store.advertising_spend_yuan)}</td><td className={store.advertising_roi < 2.5 ? "negative" : "positive"}>{store.advertising_roi.toFixed(2)}</td></tr>)}</tbody></table></div>
        </section>

        <section className="commerce-fact-panel commerce-funnel-panel">
          <header className="commerce-panel-heading"><div><span>ORDER LIFECYCLE</span><h2>订单履约漏斗</h2></div><Boxes size={18} /></header>
          <div className="commerce-funnel-list">
            {data.funnel.map((step, index) => (
              <article key={step.key}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div><header><strong>{step.label}</strong><em>{formatPercent(step.conversion_rate)}</em></header><i><b style={{ width: `${Math.max(step.conversion_rate * 100, step.count ? 3 : 0)}%` }} /></i><p>{formatNumber(step.count)} 笔 · {formatCurrency(step.amount_yuan)}</p></div>
              </article>
            ))}
          </div>
          <footer><Layers3 size={15} /><span>业务日期 {data.business_date_from ?? "--"} 至 {data.business_date_to ?? "--"}</span></footer>
        </section>
      </div>

      <div className="commerce-fact-secondary-grid">
        <section className="commerce-fact-panel commerce-exception-panel">
          <header className="commerce-panel-heading"><div><span>EXCEPTION QUEUE</span><h2>跨域经营异常</h2></div><strong>{data.exceptions.length} 项</strong></header>
          {!data.exceptions.length ? <div className="commerce-empty"><ShieldCheck size={22} /><span>当前事实范围内未识别到经营异常</span></div> : <div className="commerce-exception-list">{data.exceptions.map((item) => <article className={item.severity} key={item.key}><span><CircleAlert size={16} />{exceptionTypeLabel(item.exception_type)}</span><div><strong>{item.title}</strong><p>{item.detail}</p><small>{item.related_keys.join(" · ")}</small></div><aside><strong>{item.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}</strong><span>{item.unit}</span><code>{item.source_key}</code></aside></article>)}</div>}
        </section>

        {!isStoreCenter ? (
          <section className="commerce-fact-panel commerce-lineage-panel">
            <header className="commerce-panel-heading"><div><span>FACT LINEAGE</span><h2>事实资产与血缘</h2></div><PackageSearch size={18} /></header>
            <div>{data.lineage.map((item) => <article key={item.key}><span>{item.label}</span><strong>{formatNumber(item.record_count)}</strong><code>{item.table_name}</code><p>{item.source_key} · schema {item.source_schema_version} · map {item.mapping_version}</p><small>{item.latest_sync_run_id ?? "尚未同步"}</small></article>)}</div>
          </section>
        ) : null}
      </div>

      <section className="commerce-fact-panel commerce-order-panel">
        <header className="commerce-panel-heading"><div><span>RECENT ORDER FACTS</span><h2>最近订单与来源批次</h2></div><em>{data.recent_orders.length} 条当前视图</em></header>
        {!data.recent_orders.length ? <div className="commerce-empty"><CircleDashed size={22} /><span>同步 ERP / OMS 后显示规范订单事实</span></div> : <div className="commerce-order-table"><table><thead><tr><th>订单 / 客户</th><th>店铺</th><th>业务日期</th><th>商品行</th><th>实付金额</th><th>订单毛利</th><th>来源批次</th><th>状态</th></tr></thead><tbody>{data.recent_orders.map((order) => <tr key={order.order_key}><td><strong>{order.order_key}</strong><small>{order.customer_key} · {order.province}</small></td><td><strong>{order.store_name}</strong><small>{order.channel}</small></td><td>{order.business_date}</td><td>{order.item_count}</td><td>{formatCurrency(order.paid_amount_yuan)}</td><td className={order.gross_margin_yuan < 0 ? "negative" : "positive"}>{formatCurrency(order.gross_margin_yuan)}</td><td><code>{order.source_key}</code><small>{order.sync_run_id}</small></td><td><StatusBadge value={{ label: commerceStatusLabel(order.status), tone: statusTone(order.status) }} /></td></tr>)}</tbody></table></div>}
      </section>
      </div>
    </DatabasePageFrame>
  );
}

function DatabasePageFrame({ title, eyebrow, description, generatedAt, scopeLabel, actions, meta = "数据库实时读取", children }: { title: string; eyebrow: string; description: string; generatedAt: string | null; scopeLabel?: string; actions?: React.ReactNode; meta?: string; children: React.ReactNode }) {
  const { scopeContext, scopeOptions } = useExperience();
  const enterpriseName = scopeOptions?.enterprises.find((item) => item.key === scopeContext?.enterprise_id)?.label;
  return <div className="database-page"><PageHeader actions={actions} description={description} eyebrow={eyebrow} meta={meta} title={title} /><div className="database-context"><ShieldCheck aria-hidden="true" size={15} /><span>数据范围：{scopeLabel ?? enterpriseName ?? "—"}</span><span>生成时间：{formatTime(generatedAt)}</span></div>{children}</div>;
}

function ScopedCommercePage({ mode = "facts" }: { mode?: CommercePageMode }) {
  const { scopeContext } = useExperience();
  const scopeKey = scopeContext?.scope_level === "enterprise" ? "enterprise"
    : scopeContext?.scope_level === "store" && scopeContext.store_ids.length === 1
      ? scopeContext.store_ids[0] : null;
  return <><CanonicalFactsPanel />{scopeKey ? <CommerceOperationsPage
    key={scopeContext?.scope_version} mode={mode} scopeKey={scopeKey} /> : null}</>;
}

export function DataCenterOperationsPage({ view }: { view: DataCenterView }) {
  if (view === "commerce") return <ScopedCommercePage />;
  if (view === "sync-runs") return <SyncRunsPage />;
  if (view === "entities") return <EntitiesPage />;
  if (view === "metrics") return <MetricsPage />;
  return <QualityPage />;
}

export function CommerceCenterPage() {
  return <ScopedCommercePage mode="stores" />;
}
