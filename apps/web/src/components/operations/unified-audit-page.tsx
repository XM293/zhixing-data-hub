"use client";

import {
  Activity,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Fingerprint,
  Link2,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  TriangleAlert,
  UserRoundSearch
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import {
  auditOutcomeLabel,
  auditPaginationLabel,
  auditStatusValue,
  buildAuditSearchParams,
  EMPTY_AUDIT_FILTERS,
  type AuditFilters,
  type AuditTimeRange
} from "@/lib/audit-query";
import type { AuditEvent, AuditSource, UnifiedAuditLedgerResponse } from "@/lib/audit-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const PAGE_SIZE = 50;

const SOURCE_LABELS: Record<AuditSource, string> = {
  authorization: "授权决策",
  identity: "身份目录",
  mcp: "MCP 会话",
  tool: "工具调用",
  worker: "后台任务",
  agent: "Agent 运行",
  action: "行动执行",
  platform: "平台管理"
};

export function UnifiedAuditPage() {
  const { roleId } = useExperience();
  const [data, setData] = useState<UnifiedAuditLedgerResponse | null>(null);
  const [filters, setFilters] = useState<AuditFilters>(EMPTY_AUDIT_FILTERS);
  const [queryDraft, setQueryDraft] = useState("");
  const [requestIdDraft, setRequestIdDraft] = useState("");
  const [runIdDraft, setRunIdDraft] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLedger = useCallback(async (): Promise<UnifiedAuditLedgerResponse> => {
    const parameters = buildAuditSearchParams(filters, offset, PAGE_SIZE);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/audit/events?${parameters}`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取审计事件"));
    return (await response.json()) as UnifiedAuditLedgerResponse;
  }, [filters, offset, roleId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchLedger()
      .then((payload) => {
        if (!active) return;
        setData(payload);
        setSelectedKey((current) => payload.items.some((item) => eventKey(item) === current)
          ? current
          : payload.items[0] ? eventKey(payload.items[0]) : null);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "无法读取审计事件");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [fetchLedger, refreshVersion]);

  const selected = useMemo(
    () => data?.items.find((item) => eventKey(item) === selectedKey) ?? data?.items[0] ?? null,
    [data, selectedKey]
  );

  function patch(next: Partial<AuditFilters>): void {
    setOffset(0);
    setFilters((current) => {
      const merged = { ...current, ...next };
      const unchanged = (Object.keys(merged) as Array<keyof AuditFilters>)
        .every((key) => merged[key] === current[key]);
      return unchanged ? current : merged;
    });
  }

  function reset(): void {
    setOffset(0);
    setQueryDraft("");
    setRequestIdDraft("");
    setRunIdDraft("");
    setFilters(EMPTY_AUDIT_FILTERS);
  }

  function applyTrace(field: "request" | "run", value: string): void {
    const normalized = value.trim();
    if (field === "request") {
      setRequestIdDraft(normalized);
      patch({ requestId: normalized });
      return;
    }
    setRunIdDraft(normalized);
    patch({ runId: normalized });
  }

  if (loading && !data) return <AuditState icon={<LoaderCircle className="spinning" />} title="正在读取审计事件" />;
  if (!data) return <AuditState failed icon={<TriangleAlert />} title={error ?? "审计事件暂不可用"} />;

  const stats = [
    { label: "事件总数", value: data.stats.total_events, icon: Activity },
    { label: "近 24 小时", value: data.stats.events_last_24h, icon: Clock3 },
    { label: "异常与拒绝", value: data.stats.attention_events, icon: AlertTriangle },
    { label: "执行主体", value: data.stats.unique_actors, icon: UserRoundSearch },
    { label: "关联运行", value: data.stats.correlated_runs, icon: Link2 }
  ];

  return <section className="unified-audit-page">
    <PageHeader
      actions={<div className="audit-header-actions">
        <button aria-label="重置审计筛选" className="button secondary icon-only" onClick={reset} title="重置筛选" type="button"><RotateCcw size={16} /></button>
        <button aria-label="刷新审计事件" className="button secondary icon-only" disabled={loading} onClick={() => setRefreshVersion((value) => value + 1)} title="刷新" type="button"><RefreshCw className={loading ? "spinning" : ""} size={16} /></button>
      </div>}
      eyebrow="AUDIT EVENT LEDGER"
      meta={`${data.pagination.total} 条 · ${formatTime(data.generated_at)}`}
      title="统一审计中心"
    />

    {error ? <InlineCallout description={error} title="审计读取失败" tone="critical" /> : null}

    <section aria-label="审计统计" className="audit-stat-band">
      {stats.map(({ icon: Icon, ...item }) => <article key={item.label}><span><Icon size={15} />{item.label}</span><strong>{formatNumber(item.value)}</strong></article>)}
    </section>

    <form className="audit-filter-bar" onSubmit={(event) => { event.preventDefault(); patch({ query: queryDraft.trim(), requestId: requestIdDraft.trim(), runId: runIdDraft.trim() }); }}>
      <label><span>事件来源</span><select onChange={(event) => patch({ source: event.target.value as AuditSource | "" })} value={filters.source}><option value="">全部来源</option>{Object.entries(SOURCE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label><span>结果状态</span><select onChange={(event) => patch({ outcome: event.target.value })} value={filters.outcome}><option value="">全部结果</option>{data.facets.outcomes.map((item) => <option key={item.key} value={item.key}>{auditOutcomeLabel(item.key)} · {item.count}</option>)}</select></label>
      <label><span>执行主体</span><select onChange={(event) => patch({ actor: event.target.value })} value={filters.actor}><option value="">全部主体</option>{data.facets.actors.map((item) => <option key={item.principal_id} value={item.principal_id}>{item.display_name} · {item.count}</option>)}</select></label>
      <label><span>时间范围</span><select onChange={(event) => patch({ timeRange: event.target.value as AuditTimeRange })} value={filters.timeRange}><option value="24h">24 小时</option><option value="7d">7 天</option><option value="30d">30 天</option><option value="all">全部时间</option></select></label>
      <label className="audit-filter-trace"><span>Request ID</span><input maxLength={96} onBlur={() => applyTrace("request", requestIdDraft)} onChange={(event) => setRequestIdDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); applyTrace("request", requestIdDraft); } }} value={requestIdDraft} /></label>
      <label className="audit-filter-trace"><span>Run / AgentRun ID</span><input maxLength={96} onBlur={() => applyTrace("run", runIdDraft)} onChange={(event) => setRunIdDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); applyTrace("run", runIdDraft); } }} value={runIdDraft} /></label>
      <label className="audit-filter-query"><span>事件检索</span><div><Search size={15} /><input maxLength={160} onChange={(event) => setQueryDraft(event.target.value)} value={queryDraft} /><button className="button primary" type="submit">查询</button></div></label>
    </form>

    <section className="audit-ledger-workspace">
      <div className="audit-ledger-index">
        <header><div><span>审计事件</span><strong>{auditPaginationLabel(data.pagination.offset, data.items.length, data.pagination.total)}</strong></div></header>
        {data.items.length ? <div className="audit-ledger-table"><table><thead><tr><th>时间</th><th>来源 / 事件</th><th>主体</th><th>业务对象</th><th>结果</th><th>追踪</th></tr></thead><tbody>{data.items.map((item) => <AuditRow active={selected ? eventKey(selected) === eventKey(item) : false} item={item} key={eventKey(item)} onSelect={setSelectedKey} />)}</tbody></table></div> : <div className="audit-empty"><Fingerprint size={22} /><strong>暂无审计事件</strong></div>}
        <footer><button aria-label="上一页" className="button secondary icon-only" disabled={data.pagination.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} title="上一页" type="button"><ChevronLeft size={16} /></button><span>第 {Math.floor(data.pagination.offset / data.pagination.limit) + 1} 页</span><button aria-label="下一页" className="button secondary icon-only" disabled={!data.pagination.has_more} onClick={() => setOffset(offset + PAGE_SIZE)} title="下一页" type="button"><ChevronRight size={16} /></button></footer>
      </div>
      <AuditDetail event={selected} onTrace={applyTrace} />
    </section>
  </section>;
}

function AuditRow({ active, item, onSelect }: { active: boolean; item: AuditEvent; onSelect: (key: string) => void }) {
  return <tr className={active ? "active" : ""} onClick={() => onSelect(eventKey(item))}>
    <td><button className="audit-event-select" onClick={() => onSelect(eventKey(item))} type="button"><strong>{formatTime(item.occurred_at)}</strong>{item.duration_ms !== null ? <small>{formatDuration(item.duration_ms)}</small> : null}</button></td>
    <td><strong>{SOURCE_LABELS[item.source]}</strong><code>{item.event_type}</code></td>
    <td><strong>{item.actor_name}</strong><small>{item.actor_principal_id ?? "system"}</small></td>
    <td><strong>{item.subject_key}</strong><small>{item.subject_type}</small></td>
    <td><StatusBadge value={auditStatusValue(item.outcome, item.severity)} /></td>
    <td><code>{shortTrace(item.request_id ?? item.run_id ?? item.agent_run_id)}</code></td>
  </tr>;
}

function AuditDetail({ event, onTrace }: { event: AuditEvent | null; onTrace: (field: "request" | "run", value: string) => void }) {
  if (!event) return <aside className="audit-detail audit-detail-empty"><Fingerprint size={24} /><strong>暂无审计事件</strong></aside>;
  const traces = [
    ["Request ID", event.request_id, "request"],
    ["Run ID", event.run_id, "run"],
    ["AgentRun ID", event.agent_run_id, "run"]
  ] as const;
  return <aside className="audit-detail">
    <header><div><span>{SOURCE_LABELS[event.source]}</span><h2>{event.event_type}</h2></div><StatusBadge value={auditStatusValue(event.outcome, event.severity)} /></header>
    <dl className="audit-detail-core"><div><dt>发生时间</dt><dd>{formatFullTime(event.occurred_at)}</dd></div><div><dt>执行主体</dt><dd>{event.actor_name}</dd></div><div><dt>业务对象</dt><dd>{event.subject_type}</dd></div><div><dt>对象标识</dt><dd>{event.subject_key}</dd></div><div><dt>耗时</dt><dd>{event.duration_ms === null ? "-" : formatDuration(event.duration_ms)}</dd></div><div><dt>事件编号</dt><dd>{event.id}</dd></div></dl>
    <section className="audit-detail-summary"><span>结果摘要</span><p>{event.summary || "-"}</p></section>
    {event.attributes.some((item) => item.value) ? <dl className="audit-detail-attributes">{event.attributes.filter((item) => item.value).map((item) => <div key={item.key}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl> : null}
    <section className="audit-trace-list"><header><ShieldCheck size={15} /><strong>追踪标识</strong></header>{traces.map(([label, value, field]) => value ? <div key={label}><span>{label}</span><code>{value}</code><button aria-label={`按 ${label} 筛选`} onClick={() => onTrace(field, value)} title={`按 ${label} 筛选`} type="button"><Search size={14} /></button></div> : null)}</section>
  </aside>;
}

function AuditState({ failed = false, icon, title }: { failed?: boolean; icon: React.ReactNode; title: string }) {
  return <div className={`audit-state ${failed ? "failed" : ""}`}>{icon}<strong>{title}</strong></div>;
}

function eventKey(event: AuditEvent): string {
  return `${event.source}:${event.id}`;
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatDuration(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function formatFullTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(value));
}

function shortTrace(value: string | null): string {
  if (!value) return "-";
  return value.length > 18 ? `…${value.slice(-16)}` : value;
}
