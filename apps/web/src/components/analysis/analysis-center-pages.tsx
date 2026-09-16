"use client";

import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bot,
  CalendarDays,
  ChartNoAxesCombined,
  CheckCircle2,
  CircleAlert,
  Database,
  FileChartColumn,
  FileLock2,
  Gauge,
  History,
  LoaderCircle,
  ListPlus,
  Megaphone,
  MessageSquareText,
  PackageSearch,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  ShoppingCart,
  Target,
  TriangleAlert
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiErrorMessage } from "@/lib/api-error";
import { useActiveWorkspaceKey } from "@/lib/workspace-context";
import { apiFetch } from "@/lib/api-client";
import type {
  AnalysisCommerceFact,
  AnalysisMetric,
  AnalysisRiskLevel,
  AnalysisStudio,
  BusinessAnalysisRun,
  BusinessAnalysisRunResponse,
  BusinessBrief
} from "@/lib/analysis-types";
import type { BusinessAnalysisActionProposalResponse } from "@/lib/action-types";
import type { Tone } from "@/lib/experience-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const RISK_LABELS: Record<AnalysisRiskLevel, string> = {
  healthy: "健康",
  watch: "关注",
  high: "高风险",
  critical: "严重"
};

function riskTone(level: AnalysisRiskLevel): Tone {
  if (level === "healthy") return "positive";
  if (level === "watch") return "warning";
  return "critical";
}

function formatTime(value: string | null): string {
  if (!value) return "尚未运行";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function formatMetric(value: number, unit: string): string {
  if (unit === "元") return value >= 10000 ? `${(value / 10000).toFixed(1)}万` : value.toFixed(0);
  if (unit === "%" || unit === "x") return value.toFixed(2);
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
}

function formatChange(value: number | null): string {
  if (value === null) return "无可比期";
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

export function AnalysisCenterPage({ view }: { view: "store-review" | "briefs" }) {
  const { roleId } = useExperience();
  const workspaceKey = useActiveWorkspaceKey();
  const { notify } = useNotifications();
  const [studio, setStudio] = useState<AnalysisStudio | null>(null);
  const [selectedScope, setSelectedScope] = useState<string>("");
  const [windowDays, setWindowDays] = useState(30);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedBriefId, setSelectedBriefId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [proposing, setProposing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStudio = useCallback(async (scopeKey?: string) => {
    setError(null);
    const query = scopeKey ? `?scope_key=${encodeURIComponent(scopeKey)}` : "";
    const response = await apiFetch(`${API_BASE_URL}/api/v1/analysis/studio${query}`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取智能分析中心"));
    const payload = (await response.json()) as AnalysisStudio;
    setStudio(payload);
    setSelectedScope(payload.selected_scope.key);
    setSelectedRunId((current) => current && payload.runs.some((item) => item.id === current)
      ? current
      : payload.latest_run?.id ?? null);
    setSelectedBriefId((current) => current && payload.briefs.some((item) => item.id === current)
      ? current
      : payload.briefs[0]?.id ?? null);
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    setStudio(null);
    setSelectedScope("");
    loadStudio()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取智能分析中心"))
      .finally(() => setLoading(false));
  }, [loadStudio]);

  const selectedRun = useMemo(
    () => studio?.runs.find((item) => item.id === selectedRunId) ?? studio?.latest_run ?? null,
    [selectedRunId, studio]
  );
  const selectedBrief = useMemo(
    () => studio?.briefs.find((item) => item.id === selectedBriefId) ?? studio?.briefs[0] ?? null,
    [selectedBriefId, studio]
  );

  const changeScope = useCallback((scopeKey: string) => {
    setSelectedScope(scopeKey);
    setLoading(true);
    loadStudio(scopeKey)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法切换分析范围"))
      .finally(() => setLoading(false));
  }, [loadStudio]);

  const runAnalysis = useCallback(async () => {
    if (!selectedScope) return;
    setRunning(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/analysis/store-reviews`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Zhixing-Demo-Actor": roleId
        },
        body: JSON.stringify({
          scope_key: selectedScope,
          window_days: windowDays,
          client_request_key: `analysis-${selectedScope}-${Date.now()}`,
          workspace_key: workspaceKey
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "经营诊断运行失败"));
      const payload = (await response.json()) as BusinessAnalysisRunResponse;
      setStudio(payload.studio);
      setSelectedRunId(payload.run.id);
      setSelectedBriefId(payload.brief.id);
      notify({ title: "经营诊断已完成", description: payload.run.scope.label, tone: "success" });
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "经营诊断运行失败");
    } finally {
      setRunning(false);
    }
  }, [notify, roleId, selectedScope, windowDays, workspaceKey]);

  const proposeRecommendations = useCallback(async (
    run: BusinessAnalysisRun,
    recommendationIndexes: number[],
    dueHint: string
  ) => {
    setProposing(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/analysis/runs/${encodeURIComponent(run.id)}/action-proposals`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Zhixing-Demo-Actor": roleId
        },
        body: JSON.stringify({
          recommendation_indexes: recommendationIndexes,
          due_hint: dueHint,
          idempotency_key: `analysis-actions:${run.id}:${crypto.randomUUID()}`
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "经营建议送审失败"));
      const payload = (await response.json()) as BusinessAnalysisActionProposalResponse;
      notify({ title: payload.created_count ? "经营建议已送审" : "经营建议已存在", description: payload.created_count ? `${payload.created_count} 条建议已进入审批队列` : "本次未重复创建", tone: "success" });
      await loadStudio(run.scope.key);
      setSelectedRunId(run.id);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "经营建议送审失败");
    } finally {
      setProposing(false);
    }
  }, [loadStudio, notify, roleId]);

  if (loading && !studio) {
    return <AnalysisLoading />;
  }

  if (!studio) {
    return (
      <div className="analysis-center-state failed" role="alert">
        <TriangleAlert size={28} />
        <strong>智能分析中心暂不可用</strong>
        <span>{error}</span>
        <button className="button secondary" onClick={() => window.location.reload()} type="button">重新连接</button>
      </div>
    );
  }

  return (
    <div className="analysis-center-page">
      <PageHeader
        actions={
          <div className="analysis-toolbar">
            <label>
              <span>分析范围</span>
              <select aria-label="选择经营分析范围" disabled={running} onChange={(event) => changeScope(event.target.value)} value={selectedScope}>
                {studio.available_scopes.map((scope) => <option key={scope.key} value={scope.key}>{scope.label}</option>)}
              </select>
            </label>
            {view === "store-review" ? <label><span>观察窗口</span><select aria-label="选择观察窗口" disabled={running} onChange={(event) => setWindowDays(Number(event.target.value))} value={windowDays}><option value={14}>14 天</option><option value={30}>30 天</option><option value={60}>60 天</option><option value={90}>90 天</option></select></label> : null}
            {view === "store-review" && studio.can_run ? <button className="button primary" disabled={running} onClick={() => void runAnalysis()} type="button">{running ? <LoaderCircle className="spinning" size={16} /> : <RefreshCw size={16} />}{running ? "正在冻结证据并分析" : "运行新诊断"}</button> : null}
          </div>
        }
        description={view === "store-review" ? "把指标事实、AI 推断、风险和行动建议分层保存，每次诊断都绑定不可变证据快照。" : "简报由已完成的经营诊断生成，保留原始分析运行、证据编号和生成身份。"}
        eyebrow={`智能分析中心 · ${view === "store-review" ? "经营诊断" : "经营简报"}`}
        meta={`数据库视图 · ${studio.actor_name}`}
        title={view === "store-review" ? `${studio.selected_scope.label}经营诊断` : `${studio.selected_scope.label}经营简报`}
      />

      {error ? <InlineCallout description={error} title="本次操作未完成" tone="critical" /> : null}
      {!studio.can_run && view === "store-review" ? <InlineCallout description="当前角色可以读取授权范围内的诊断和简报，但不能创建新的分析运行。" title="只读经营指导" tone="info" /> : null}

      <AnalysisStatBand studio={studio} />
      {view === "store-review"
        ? <StoreReviewWorkspace canPropose={studio.can_propose} onPropose={proposeRecommendations} onSelectRun={setSelectedRunId} proposing={proposing} run={selectedRun} runs={studio.runs} />
        : <BriefWorkspace brief={selectedBrief} briefs={studio.briefs} onSelectBrief={setSelectedBriefId} />}
    </div>
  );
}

function AnalysisLoading() {
  return <div className="analysis-center-state" role="status"><Database className="spinning" size={28} /><strong>正在读取经营分析数据库</strong><span>加载指标快照、分析运行、证据和简报版本</span></div>;
}

function AnalysisStatBand({ studio }: { studio: AnalysisStudio }) {
  const stats = [
    { label: "分析运行", value: studio.stats.analysis_run_count, note: "当前授权范围", icon: ChartNoAxesCombined },
    { label: "经营简报", value: studio.stats.brief_count, note: "与分析运行同源", icon: FileChartColumn },
    { label: "高风险运行", value: studio.stats.high_risk_count, note: "包含 high / critical", icon: TriangleAlert },
    { label: "模型运行", value: studio.stats.model_run_count, note: "其余为证据降级", icon: Bot },
    { label: "最近完成", value: formatTime(studio.stats.latest_completed_at), note: "数据库业务时间", icon: History }
  ];
  return <section aria-label="经营分析统计" className="analysis-stat-band">{stats.map((item) => { const Icon = item.icon; return <article key={item.label}><Icon size={18} /><span>{item.label}</span><strong>{item.value}</strong><small>{item.note}</small></article>; })}</section>;
}

function StoreReviewWorkspace({ canPropose, onPropose, onSelectRun, proposing, run, runs }: {
  canPropose: boolean;
  onPropose: (run: BusinessAnalysisRun, recommendationIndexes: number[], dueHint: string) => Promise<void>;
  onSelectRun: (id: string) => void;
  proposing: boolean;
  run: BusinessAnalysisRun | null;
  runs: BusinessAnalysisRun[];
}) {
  const [selectedRecommendations, setSelectedRecommendations] = useState<number[]>([]);
  const [dueHint, setDueHint] = useState("未来 3 个工作日内完成");

  useEffect(() => {
    setSelectedRecommendations([]);
    setDueHint("未来 3 个工作日内完成");
  }, [run?.id]);

  if (!run) {
    return <section className="analysis-empty"><Gauge size={32} /><strong>当前范围还没有数据库诊断</strong><span>拥有运行权限的负责人可以冻结当前历史指标并生成首份经营诊断与简报。</span></section>;
  }
  return (
    <div className="analysis-review-workspace">
      <section className={`analysis-headline ${run.risk_level}`}>
        <div><span>ANALYSIS RUN · {run.execution_mode === "model" ? "STRUCTURED AI" : "DETERMINISTIC FALLBACK"}</span><h2>{run.result.headline}</h2><p>{run.result.summary}</p></div>
        <aside><StatusBadge value={{ label: RISK_LABELS[run.risk_level], tone: riskTone(run.risk_level) }} /><strong>{run.result.confidence.toUpperCase()} CONFIDENCE</strong><small>{run.model} · {formatTime(run.completed_at)}</small></aside>
      </section>
      <section aria-label="冻结经营指标" className="analysis-metric-grid">{run.result.metric_snapshot.map((metric) => <AnalysisMetricCard key={metric.key} metric={metric} />)}</section>
      {run.result.commerce_fact_snapshot.length ? <AnalysisCommerceFacts facts={run.result.commerce_fact_snapshot} /> : null}
      <div className="analysis-review-grid">
        <section className="analysis-panel analysis-findings-panel"><PanelHeading icon={Activity} kicker="FACT / INFERENCE / RISK" title="事实与判断分层" meta={`${run.result.findings.length} 条`} /><div className="analysis-findings">{run.result.findings.map((item, index) => <article className={item.severity} key={`${item.kind}-${index}`}><span>{item.kind === "fact" ? "事实" : item.kind === "inference" ? "推断" : "风险"}</span><p>{item.text}</p><EvidenceRefs refs={item.evidence_refs} /></article>)}</div></section>
        <section className="analysis-panel analysis-recommendations-panel">
          <PanelHeading icon={Target} kicker="GOVERNED NEXT ACTION" title="建议与停止条件" meta={`${run.result.recommendations.length} 项`} />
          <div className="analysis-recommendations">{run.result.recommendations.map((item, index) => {
            const proposal = run.action_proposals.find((candidate) => candidate.recommendation_index === index);
            const selected = selectedRecommendations.includes(index);
            return <article className={proposal ? "proposed" : ""} key={`${item.title}-${index}`}>
              <header>
                <label className="analysis-recommendation-select">
                  <input
                    aria-label={proposal ? "建议已进入行动中心" : "选择经营建议"}
                    checked={Boolean(proposal) || selected}
                    disabled={Boolean(proposal) || !canPropose}
                    onChange={() => setSelectedRecommendations((current) => current.includes(index)
                      ? current.filter((value) => value !== index)
                      : [...current, index])}
                    type="checkbox"
                  />
                  <strong>{item.title}</strong>
                </label>
                {proposal
                  ? <StatusBadge value={{ label: proposal.work_item_status ? "已进入工作台" : proposal.status === "pending_approval" ? "待审批" : proposal.status === "approved" ? "已批准" : "已驳回", tone: proposal.status === "rejected" ? "critical" : proposal.status === "pending_approval" ? "warning" : "positive" }} />
                  : <StatusBadge value={{ label: item.priority === "urgent" ? "紧急" : item.priority === "high" ? "高优先" : "普通", tone: item.priority === "normal" ? "info" : "warning" }} />}
              </header>
              <p>{item.action}</p>
              <dl><div><dt>责任角色</dt><dd>{item.owner_role}</dd></div><div><dt>成功指标</dt><dd>{item.success_metric}</dd></div><div><dt>停止条件</dt><dd>{item.stop_condition}</dd></div></dl>
              <EvidenceRefs refs={item.evidence_refs} />
            </article>;
          })}</div>
          <div className="analysis-action-gate">
            <div><ListPlus size={18} /><span><strong>送入行动审批</strong><small>{selectedRecommendations.length} 条已选择 · R2 内部行动</small></span></div>
            <label><span>时间要求</span><input onChange={(event) => setDueHint(event.target.value)} value={dueHint} /></label>
            <button className="button primary" disabled={!canPropose || proposing || !selectedRecommendations.length || dueHint.trim().length < 2} onClick={() => void onPropose(run, selectedRecommendations, dueHint.trim())} type="button">{proposing ? <LoaderCircle className="spinning" size={15} /> : <CheckCircle2 size={15} />}{proposing ? "正在创建提案" : "提交人工审批"}</button>
            <Link className="button secondary" href="/console/actions/approvals">查看审批队列</Link>
          </div>
        </section>
        <aside className="analysis-panel analysis-trace-panel"><PanelHeading icon={FileLock2} kicker="REPLAYABLE EVIDENCE" title="证据与运行追踪" /><dl><div><dt>证据快照</dt><dd><code>{run.evidence_snapshot.key}</code></dd></div><div><dt>冻结条目</dt><dd>{run.evidence_snapshot.item_count} 条证据</dd></div><div><dt>内容哈希</dt><dd><code>{run.evidence_snapshot.content_hash.slice(0, 20)}…</code></dd></div><div><dt>发起人</dt><dd>{run.initiated_by_name}</dd></div><div><dt>请求 / Run</dt><dd><code>{run.request_id}</code><code>{run.run_id}</code></dd></div></dl>{run.result.unknowns.length ? <div className="analysis-unknowns"><CircleAlert size={16} /><div><strong>未知与缺口</strong>{run.result.unknowns.map((item) => <p key={item}>{item}</p>)}</div></div> : null}<Link className="button secondary analysis-meeting-link" href="/console/meetings/mtg-budget-20260825"><MessageSquareText size={16} />进入数字会议<ArrowRight size={15} /></Link></aside>
      </div>
      <section className="analysis-history"><PanelHeading icon={History} kicker="VERSIONED RUN HISTORY" title="历史诊断" meta={`${runs.length} 次`} /><div>{runs.map((item) => <button className={item.id === run.id ? "active" : ""} key={item.id} onClick={() => onSelectRun(item.id)} type="button"><span><strong>{formatTime(item.completed_at)}</strong><small>{item.scope.label} · {item.window_days} 天 · {item.execution_mode === "model" ? "AI" : "降级"}</small></span><StatusBadge value={{ label: RISK_LABELS[item.risk_level], tone: riskTone(item.risk_level) }} /></button>)}</div></section>
    </div>
  );
}

function AnalysisMetricCard({ metric }: { metric: AnalysisMetric }) {
  const rising = (metric.period_change_rate ?? 0) >= 0;
  const ChangeIcon = rising ? ArrowUpRight : ArrowDownRight;
  return <article className={metric.status}><header><span>{metric.evidence_ref}</span><strong>{metric.label}</strong><StatusBadge value={{ label: RISK_LABELS[metric.status], tone: riskTone(metric.status) }} /></header><div><strong>{formatMetric(metric.latest_value, metric.unit)}<small>{metric.unit}</small></strong><span className={rising ? "positive" : "critical"}><ChangeIcon size={14} />{formatChange(metric.period_change_rate)}</span></div><MetricSparkline metric={metric} /><p>{metric.status_reason}</p></article>;
}

function AnalysisCommerceFacts({ facts }: { facts: AnalysisCommerceFact[] }) {
  const summaryCount = facts.filter((item) => item.domain !== "exception").length;
  const exceptionCount = facts.length - summaryCount;
  return (
    <section className="analysis-commerce-panel">
      <PanelHeading
        icon={Database}
        kicker="CANONICAL COMMERCE FACTS"
        meta={`${summaryCount} 组汇总 · ${exceptionCount} 项异常`}
        title="规范经营事实"
      />
      <div className="analysis-commerce-grid">
        {facts.map((fact) => <AnalysisCommerceFactCard fact={fact} key={fact.key} />)}
      </div>
    </section>
  );
}

function AnalysisCommerceFactCard({ fact }: { fact: AnalysisCommerceFact }) {
  const DomainIcon = fact.domain === "orders"
    ? ShoppingCart
    : fact.domain === "refunds"
      ? RotateCcw
      : fact.domain === "inventory"
        ? PackageSearch
        : fact.domain === "advertising"
          ? Megaphone
          : TriangleAlert;
  const domainLabel = fact.domain === "orders"
    ? "订单"
    : fact.domain === "refunds"
      ? "退款"
      : fact.domain === "inventory"
        ? "库存"
        : fact.domain === "advertising"
          ? "投放"
          : "异常";
  return (
    <article className={fact.status}>
      <header>
        <span><DomainIcon size={15} />{domainLabel}</span>
        <EvidenceRefs refs={[fact.evidence_ref]} />
      </header>
      <div>
        <strong>{formatMetric(fact.value, fact.unit)}<small>{fact.unit}</small></strong>
        <StatusBadge value={{ label: RISK_LABELS[fact.status], tone: riskTone(fact.status) }} />
      </div>
      <h3>{fact.label}</h3>
      <p>{fact.detail}</p>
      <footer>
        <span>{fact.source_keys.join(" · ") || "来源待登记"}</span>
        <code>{fact.sync_run_ids[0] ?? "未同步"}</code>
      </footer>
    </article>
  );
}

function MetricSparkline({ metric }: { metric: AnalysisMetric }) {
  if (metric.points.length < 2) return <div className="analysis-sparkline empty" />;
  const values = metric.points.map((item) => item.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values.map((value, index) => `${(index / (values.length - 1)) * 180},${44 - ((value - min) / range) * 36}`).join(" ");
  return <svg aria-label={`${metric.label} ${metric.points.length} 日趋势`} className="analysis-sparkline" preserveAspectRatio="none" role="img" viewBox="0 0 180 48"><path d="M0 44H180" /><polyline points={points} /></svg>;
}

function BriefWorkspace({ brief, briefs, onSelectBrief }: { brief: BusinessBrief | null; briefs: BusinessBrief[]; onSelectBrief: (id: string) => void }) {
  if (!brief) return <section className="analysis-empty"><FileChartColumn size={32} /><strong>当前范围还没有经营简报</strong><span>每次完成经营诊断后，系统会从同一证据快照自动生成版本化简报。</span></section>;
  return <div className="brief-workspace"><aside className="brief-index"><PanelHeading icon={CalendarDays} kicker="BRIEF LEDGER" title="简报版本台账" meta={`${briefs.length} 份`} /><div>{briefs.map((item) => <button className={item.id === brief.id ? "active" : ""} key={item.id} onClick={() => onSelectBrief(item.id)} type="button"><span>{formatTime(item.created_at)}</span><strong>{item.title}</strong><small>v{item.version_number} · {item.execution_mode === "model" ? "模型分析" : "证据降级"}</small></button>)}</div></aside><article className="brief-document"><header><div><span>BUSINESS BRIEF · DATABASE VERSION</span><h2>{brief.title}</h2><p>{brief.content.headline}</p></div><StatusBadge value={{ label: brief.status === "confirmed" ? "已确认" : "已生成", tone: brief.status === "confirmed" ? "positive" : "info" }} /></header><section className="brief-meta"><span><Bot size={15} />{brief.model}</span><span><FileLock2 size={15} />{brief.evidence_snapshot_key}</span><span><ShieldCheck size={15} />{brief.created_by_name}</span><span><History size={15} />{formatTime(brief.created_at)}</span></section><div className="brief-sections">{brief.content.sections.map((section, index) => <section key={section.key}><span>{String(index + 1).padStart(2, "0")}</span><div><h3>{section.title}</h3>{section.items.map((item) => <p key={item}>{item}</p>)}</div></section>)}</div><footer><div><span>证据引用</span><EvidenceRefs refs={brief.content.evidence_refs} /></div><div><span>来源分析</span><code>{brief.source_analysis_run_id}</code></div></footer></article></div>;
}

function PanelHeading({ icon: Icon, kicker, title, meta }: { icon: typeof Activity; kicker: string; title: string; meta?: string }) {
  return <header className="analysis-panel-heading"><Icon size={18} /><div><span>{kicker}</span><h2>{title}</h2></div>{meta ? <strong>{meta}</strong> : null}</header>;
}

function EvidenceRefs({ refs }: { refs: string[] }) {
  return <span className="analysis-evidence-refs">{refs.map((ref) => <code key={ref}>{ref}</code>)}</span>;
}
