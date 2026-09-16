"use client";

import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  Layers3,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  UsersRound
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader, Surface, StatusBadge } from "@/components/console/ui";
import { OrderSummaryPanel } from "@/components/data-center/order-summary-panel";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import { setActiveWorkspaceKey } from "@/lib/workspace-context";
import type {
  WorkspaceAttention,
  WorkspaceCatalogResponse,
  WorkspaceKey,
  WorkspaceMetric,
  WorkspaceReadModelResponse
} from "@/lib/workspace-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
}

function formatMetric(metric: WorkspaceMetric): string {
  if (metric.unit === "元" && metric.value >= 10000) {
    return `${(metric.value / 10000).toFixed(1)}万`;
  }
  if (metric.unit === "%" || metric.unit === "x") return metric.value.toFixed(2);
  return formatNumber(metric.value);
}

function formatTime(value: string | null): string {
  if (!value) return "尚未同步";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function metricChange(metric: WorkspaceMetric): string | undefined {
  if (metric.change_rate === null) return undefined;
  const value = metric.change_rate * 100;
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function statusTone(item: WorkspaceAttention): "critical" | "warning" | "info" | "neutral" {
  if (item.severity === "critical" || item.severity === "high") return "critical";
  if (item.severity === "warning") return "warning";
  if (item.severity === "info") return "info";
  return "neutral";
}

function AttentionRow({ item }: { item: WorkspaceAttention }) {
  const content = (
    <>
      <span className={`workspace-attention-dot ${statusTone(item)}`} aria-hidden="true" />
      <div className="workspace-attention-copy">
        <div>
          <strong>{item.title}</strong>
          <StatusBadge value={{ label: item.status, tone: statusTone(item) }} />
        </div>
        <p>{item.detail}</p>
        {item.as_of ? <time><Clock3 aria-hidden="true" size={12} />{formatTime(item.as_of)}</time> : null}
      </div>
      {item.href ? <ChevronRight aria-hidden="true" size={16} /> : null}
    </>
  );
  return item.href ? <Link className="workspace-attention-row" href={item.href}>{content}</Link> : <div className="workspace-attention-row">{content}</div>;
}

function LoadingState() {
  return (
    <div className="workspace-state" role="status">
      <LoaderCircle className="spinning" aria-hidden="true" size={24} />
      <strong>正在读取工作空间</strong>
    </div>
  );
}

export function WorkspaceHomePage({ workspaceKey }: { workspaceKey?: WorkspaceKey }) {
  const { scopeContext } = useExperience();
  return <ScopedWorkspaceHomePage key={scopeContext?.scope_version ?? "pending"} workspaceKey={workspaceKey} />;
}

function ScopedWorkspaceHomePage({ workspaceKey }: { workspaceKey?: WorkspaceKey }) {
  const { can } = useExperience();
  const [catalog, setCatalog] = useState<WorkspaceCatalogResponse | null>(null);
  const [model, setModel] = useState<WorkspaceReadModelResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState<WorkspaceKey | null>(workspaceKey ?? null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCatalog = useCallback(async () => {
    const response = await apiFetch(`${API_BASE_URL}/api/v1/workspaces/me`, { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "工作空间目录不可用"));
    const payload = (await response.json()) as WorkspaceCatalogResponse;
    setCatalog(payload);
    setSelectedKey((current) => {
      if (workspaceKey) return workspaceKey;
      if (current && payload.workspaces.some((item) => item.key === current)) return current;
      return payload.default_workspace_key;
    });
    return payload;
  }, []);

  const loadModel = useCallback(async (key: WorkspaceKey) => {
    const response = await apiFetch(`${API_BASE_URL}/api/v1/workspaces/${encodeURIComponent(key)}/read-model`, { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "工作空间数据不可用"));
    setModel((await response.json()) as WorkspaceReadModelResponse);
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const nextCatalog = await loadCatalog();
      const key = selectedKey && nextCatalog.workspaces.some((item) => item.key === selectedKey)
        ? selectedKey
        : nextCatalog.default_workspace_key;
      await loadModel(key);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "工作空间刷新失败");
    } finally {
      setRefreshing(false);
    }
  }, [loadCatalog, loadModel, selectedKey]);

  useEffect(() => {
    let cancelled = false;
      setLoading(true);
      setError(null);
      loadCatalog()
      .then((payload) => {
        if (cancelled) return;
        const key = workspaceKey ?? payload.default_workspace_key;
        return loadModel(key);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "工作空间读取失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadCatalog, loadModel, workspaceKey]);

  useEffect(() => {
    if (model?.workspace.key) setActiveWorkspaceKey(model.workspace.key);
  }, [model?.workspace.key]);

  useEffect(() => {
    if (!selectedKey || !catalog || !catalog.workspaces.some((item) => item.key === selectedKey)) return;
    if (model?.workspace.key === selectedKey) return;
    setLoading(true);
    loadModel(selectedKey)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "工作空间读取失败"))
      .finally(() => setLoading(false));
  }, [catalog, loadModel, model?.workspace.key, selectedKey]);

  const metricCards = useMemo(() => model?.metrics ?? [], [model?.metrics]);
  if (loading && !model) return <LoadingState />;
  if (!model) {
    return (
      <div className="workspace-state failed" role="alert">
        <TriangleAlert aria-hidden="true" size={26} />
        <strong>工作空间暂不可用</strong>
        <span>{error ?? "请稍后重试"}</span>
        <button className="button secondary" onClick={() => void refresh()} type="button"><RefreshCw size={15} />重试</button>
      </div>
    );
  }

  return (
    <div className="workspace-home page-stack">
      {can("metric.query.execute") ? <OrderSummaryPanel /> : null}
      <PageHeader
        actions={
          <div className="workspace-header-actions">
            {catalog && catalog.workspaces.length > 1 ? (
              <label className="workspace-switcher">
                <span>工作空间</span>
                <select value={selectedKey ?? model.workspace.key} onChange={(event) => setSelectedKey(event.target.value as WorkspaceKey)}>
                  {catalog.workspaces.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </select>
              </label>
            ) : null}
            <button className="button secondary" disabled={refreshing} onClick={() => void refresh()} type="button">
              <RefreshCw className={refreshing ? "spinning" : ""} aria-hidden="true" size={15} />刷新
            </button>
          </div>
        }
        eyebrow={model.workspace.label}
        meta={`${model.actor_position} · ${model.scope.label}`}
        title={`你好，${model.actor_name.split(" /")[0]}`}
      />

      {error ? <div className="workspace-inline-error" role="alert"><AlertTriangle aria-hidden="true" size={15} />{error}</div> : null}

      <div className="workspace-context-strip">
        <div><ShieldCheck aria-hidden="true" size={16} /><strong>{model.scope.label}</strong><span>数据范围</span></div>
        <div><Clock3 aria-hidden="true" size={16} /><strong>{formatTime(model.scope.as_of)}</strong><span>权限解析</span></div>
        <div><Database aria-hidden="true" size={16} /><strong>{model.freshness.filter((item) => item.status === "connected").length}/{model.freshness.length}</strong><span>来源在线</span></div>
        <Link className="workspace-context-link" href={model.scene?.route ?? "/console/cockpit"}><Layers3 aria-hidden="true" size={15} />进入空间视图<ChevronRight aria-hidden="true" size={14} /></Link>
      </div>

      {metricCards.length > 0 ? (
        <section className="workspace-metric-strip" aria-label="岗位关键指标">
          {metricCards.map((metric) => {
            const change = metricChange(metric);
            const favorable = metric.status === "positive";
            return (
              <Link className="workspace-metric-card" href={metric.href ?? "#"} key={metric.key}>
                <div><span>{metric.label}</span><em>{metric.unit}</em></div>
                <strong>{formatMetric(metric)}</strong>
                <p className={metric.status}>
                  {change ? (favorable ? <ArrowUpRight aria-hidden="true" size={13} /> : <ArrowDownRight aria-hidden="true" size={13} />) : null}
                  {change ?? "当前快照"}
                  <small>{metric.status_reason}</small>
                </p>
              </Link>
            );
          })}
        </section>
      ) : (
        <div className="workspace-empty-metrics"><Database aria-hidden="true" size={20} /><span>当前工作空间暂无可用指标</span><Link href="/console/data/foundation/sources">查看数据来源</Link></div>
      )}

      <div className="workspace-primary-grid">
        <Surface
          action={<Link className="inline-link" href="/console/analysis/store-review">进入分析<ChevronRight aria-hidden="true" size={14} /></Link>}
          className="workspace-attention-surface"
          meta={`${model.attention.length} 项`}
          title="需要关注"
        >
          {model.attention.length ? model.attention.map((item) => <AttentionRow item={item} key={item.key} />) : <div className="workspace-empty-row"><CheckCircle2 aria-hidden="true" size={18} /><span>当前没有新的经营异常</span></div>}
        </Surface>

        <Surface
          action={<Link className="inline-link" href="/console/actions/approvals">打开行动中心<ChevronRight aria-hidden="true" size={14} /></Link>}
          className="workspace-decision-surface"
          meta={`${model.decisions.length} 项`}
          title={model.workspace.key === "executive" ? "待决策与审批" : "待处理事项"}
        >
          {model.decisions.length ? model.decisions.map((item) => <AttentionRow item={item} key={item.key} />) : <div className="workspace-empty-row"><CheckCircle2 aria-hidden="true" size={18} /><span>当前没有待处理审批</span></div>}
          {model.work_items.length ? (
            <div className="workspace-subqueue"><div className="workspace-subqueue-heading"><strong>我的工作</strong><Link href="/console/actions/work">查看全部</Link></div>{model.work_items.slice(0, 3).map((item) => <AttentionRow item={item} key={item.key} />)}</div>
          ) : null}
        </Surface>
      </div>

      <div className="workspace-secondary-grid">
        <Surface title="快捷操作" meta="按当前权限显示">
          <div className="workspace-quick-actions">
            {model.quick_actions.map((action) => action.enabled ? (
              <Link className="workspace-quick-action" href={action.href} key={action.key}><Sparkles aria-hidden="true" size={15} /><span>{action.label}</span><ChevronRight aria-hidden="true" size={14} /></Link>
            ) : (
              <button className="workspace-quick-action disabled" disabled key={action.key} title={action.disabled_reason ?? "当前账号未获得该操作权限"}><ShieldCheck aria-hidden="true" size={15} /><span>{action.label}</span></button>
            ))}
          </div>
        </Surface>

        <Surface title="数据状态" meta="来源与最近同步">
          <div className="workspace-freshness-list">
            {model.freshness.slice(0, 5).map((item) => <div className="workspace-freshness-row" key={item.key}><span className={item.status === "connected" ? "online" : "offline"} /><div><strong>{item.label}</strong><small>{item.detail}</small></div><time>{formatTime(item.as_of)}</time></div>)}
          </div>
        </Surface>

        <Surface title="最近动态" meta="按时间倒序">
          <div className="workspace-activity-list">
            {model.activities.length ? model.activities.map((item) => <Link className="workspace-activity-row" href={item.href ?? "/console/cockpit"} key={item.key}><Activity aria-hidden="true" size={15} /><div><strong>{item.title}</strong><span>{item.detail}</span></div><time>{formatTime(item.occurred_at)}</time></Link>) : <div className="workspace-empty-row"><UsersRound aria-hidden="true" size={18} /><span>暂无新的业务动态</span></div>}
          </div>
        </Surface>
      </div>
    </div>
  );
}
