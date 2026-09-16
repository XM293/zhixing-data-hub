"use client";

import {
  Activity,
  Bot,
  Braces,
  Cable,
  CheckCircle2,
  Clock3,
  Cpu,
  DatabaseZap,
  Eye,
  Gauge,
  LoaderCircle,
  Play,
  RefreshCw,
  ServerCog,
  Square,
  TriangleAlert,
  Workflow
} from "lucide-react";
import { useCallback, useEffect, useState, type CSSProperties } from "react";

import { ConfirmDialog, Dialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import type {
  AIDailyStat,
  AIOperationsOverviewResponse,
  AIProviderProbeRunView,
  AIRunTypeStat,
  AgentRuntimeSessionDetailResponse,
  AgentRuntimeSessionView,
  AgentRuntimeProbeRunView
} from "@/lib/ai-operations-types";
import { apiErrorMessage } from "@/lib/api-error";
import { apiFetch } from "@/lib/api-client";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN", { notation: value >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
}

function formatDuration(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)}s` : `${value}ms`;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function runtimeStatus(status: string): { label: string; tone: "positive" | "critical" | "warning" | "info" } {
  if (status === "completed") return { label: "已完成", tone: "positive" };
  if (status === "failed") return { label: "失败", tone: "critical" };
  if (status === "cancelled") return { label: "已取消", tone: "warning" };
  if (status === "waiting_approval") return { label: "等待审批", tone: "warning" };
  return { label: "运行中", tone: "info" };
}

function eventPayload(value: Record<string, unknown>): string {
  const entries = Object.entries(value);
  if (!entries.length) return "--";
  return entries.map(([key, item]) => `${key}=${Array.isArray(item) ? item.join(", ") : String(item)}`).join(" · ");
}

export function AIRuntimePage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [overview, setOverview] = useState<AIOperationsOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [probing, setProbing] = useState(false);
  const [runtimeProbing, setRuntimeProbing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [probeResult, setProbeResult] = useState<AIProviderProbeRunView | null>(null);
  const [runtimeProbeResult, setRuntimeProbeResult] = useState<AgentRuntimeProbeRunView | null>(null);
  const [runtimeDetailId, setRuntimeDetailId] = useState<string | null>(null);
  const [runtimeDetail, setRuntimeDetail] = useState<AgentRuntimeSessionDetailResponse | null>(null);
  const [runtimeDetailLoading, setRuntimeDetailLoading] = useState(false);
  const [runtimeDetailError, setRuntimeDetailError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<AgentRuntimeSessionView | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const canManage = can("ai.provider.manage");

  const loadOverview = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/ai-operations/overview`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取 AI 运行状态"));
    setOverview((await response.json()) as AIOperationsOverviewResponse);
  }, [roleId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    apiFetch(`${API_BASE_URL}/api/v1/ai-operations/overview`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId },
      signal: controller.signal
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取 AI 运行状态"));
        return response.json() as Promise<AIOperationsOverviewResponse>;
      })
      .then(setOverview)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "无法读取 AI 运行状态");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [roleId]);

  async function runProbe() {
    if (!overview || !canManage || probing) return;
    setProbing(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/ai-operations/probes`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Zhixing-Demo-Actor": roleId
        },
        body: JSON.stringify({ model: overview.provider.model })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "Provider 探针执行失败"));
      const result = (await response.json()) as AIProviderProbeRunView;
      setProbeResult(result);
      await loadOverview();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Provider 探针执行失败");
    } finally {
      setProbing(false);
    }
  }

  async function runRuntimeProbe() {
    if (!overview || !canManage || runtimeProbing) return;
    setRuntimeProbing(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/ai-operations/runtime-probes`, {
        method: "POST",
        headers: { "X-Zhixing-Demo-Actor": roleId }
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "Runtime 探针执行失败"));
      setRuntimeProbeResult((await response.json()) as AgentRuntimeProbeRunView);
      await loadOverview();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Runtime 探针执行失败");
    } finally {
      setRuntimeProbing(false);
    }
  }

  async function loadRuntimeDetail(sessionId: string) {
    setRuntimeDetailId(sessionId);
    setRuntimeDetailLoading(true);
    setRuntimeDetailError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/ai-operations/runtime-sessions/${sessionId}`, {
        cache: "no-store",
        headers: { "X-Zhixing-Demo-Actor": roleId }
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取 Runtime 会话"));
      setRuntimeDetail((await response.json()) as AgentRuntimeSessionDetailResponse);
    } catch (reason: unknown) {
      setRuntimeDetail(null);
      setRuntimeDetailError(reason instanceof Error ? reason.message : "无法读取 Runtime 会话");
    } finally {
      setRuntimeDetailLoading(false);
    }
  }

  async function cancelRuntimeSession() {
    if (!cancelTarget || cancelling) return;
    setCancelling(true);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/ai-operations/runtime-sessions/${cancelTarget.id}/cancel`, {
        method: "POST",
        headers: { "X-Zhixing-Demo-Actor": roleId }
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "Runtime 取消失败"));
      notify({ title: "Runtime 取消请求已提交", tone: "success" });
      setCancelTarget(null);
      await loadOverview();
      if (runtimeDetailId === cancelTarget.id) await loadRuntimeDetail(cancelTarget.id);
    } catch (reason: unknown) {
      notify({ title: "Runtime 取消失败", description: reason instanceof Error ? reason.message : "请稍后重试", tone: "error" });
    } finally {
      setCancelling(false);
    }
  }

  async function resolveApproval(sessionId: string, decision: "approve" | "decline") {
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/ai-operations/runtime-sessions/${sessionId}/approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ decision })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "Runtime 审批处理失败"));
      notify({ title: decision === "approve" ? "Runtime 审批已通过" : "Runtime 审批已拒绝", tone: "success" });
      await loadOverview();
    } catch (reason: unknown) {
      notify({ title: "Runtime 审批处理失败", description: reason instanceof Error ? reason.message : "请稍后重试", tone: "error" });
    }
  }

  if (loading) return <RuntimeState icon={<LoaderCircle className="spinning" />} title="正在汇总 AI Provider 与运行记录" />;
  if (!overview) return <RuntimeState failed icon={<TriangleAlert />} title={error ?? "AI 运行控制台暂不可用"} />;

  const providerHealthy = overview.probes[0]?.status === "succeeded";
  const runtimeHealthy = overview.runtime_probes[0]?.status === "succeeded";
  const runtimeSessions = overview.runtime_sessions;
  const stats = [
    { label: "累计 AI 运行", value: formatNumber(overview.stats.total_runs), note: `近 24h ${overview.stats.runs_last_24h} 次`, icon: Activity },
    { label: "模型成功率", value: `${Math.round(overview.stats.success_rate * 100)}%`, note: `${overview.stats.successful_runs} 成功 · ${overview.stats.degraded_runs} 降级`, icon: CheckCircle2 },
    { label: "平均耗时", value: formatDuration(overview.stats.average_duration_ms), note: "分身、分析与客户方案", icon: Clock3 },
    { label: "累计 Token", value: formatNumber(overview.stats.input_tokens + overview.stats.output_tokens), note: `覆盖 ${Math.round(overview.stats.token_coverage_rate * 100)}% 运行`, icon: DatabaseZap },
    { label: "数字会议运行", value: formatNumber(overview.stats.meeting_runs), note: "分析、质询与主持", icon: Workflow },
    { label: "AI 接入", value: providerHealthy && runtimeHealthy ? "正常" : "待检查", note: `${overview.stats.probe_runs} Provider · ${overview.runtime_probes.length} Runtime`, icon: Gauge }
  ];

  return (
    <section className="ai-runtime-page">
      <PageHeader
        actions={
          <div className="ai-runtime-actions">
            <button aria-label="刷新 AI 运行状态" className="button secondary icon-only" onClick={() => void loadOverview()} title="刷新" type="button"><RefreshCw size={16} /></button>
            <button className="button primary" disabled={!canManage || probing} onClick={() => void runProbe()} type="button">
              {probing ? <LoaderCircle className="spinning" size={16} /> : <Play size={16} />}
              {probing ? "正在执行探针" : "运行 Provider 探针"}
            </button>
            <button className="button secondary" disabled={!canManage || runtimeProbing} onClick={() => void runRuntimeProbe()} type="button">
              {runtimeProbing ? <LoaderCircle className="spinning" size={16} /> : <Cable size={16} />}
              {runtimeProbing ? "正在握手" : "运行 Runtime 探针"}
            </button>
          </div>
        }
        eyebrow="平台管理 / AI 运行"
        meta={`更新 ${formatTime(overview.generated_at)}`}
        title="AI Runtime 控制台"
      />

      {error ? <InlineCallout description={error} title="运行状态读取异常" tone="critical" /> : null}
      {probeResult ? (
        <InlineCallout
          description={probeResult.status === "succeeded" ? `${probeResult.model} · ${formatDuration(probeResult.duration_ms)} · JSON Schema ${probeResult.structured_output_supported ? "通过" : "兼容模式"}` : probeResult.error_message ?? "Provider 未返回可用结果"}
          title={probeResult.status === "succeeded" ? "Provider 探针通过" : "Provider 探针失败"}
          tone={probeResult.status === "succeeded" ? "positive" : "critical"}
        />
      ) : null}
      {runtimeProbeResult ? (
        <InlineCallout
          description={runtimeProbeResult.status === "succeeded" ? `${runtimeProbeResult.command_version ?? runtimeProbeResult.runtime_key} · ${formatDuration(runtimeProbeResult.duration_ms)}` : runtimeProbeResult.error_message ?? "Runtime 未完成握手"}
          title={runtimeProbeResult.status === "succeeded" ? "Runtime 握手通过" : "Runtime 握手失败"}
          tone={runtimeProbeResult.status === "succeeded" ? "positive" : "critical"}
        />
      ) : null}

      <section className="ai-runtime-stat-band" aria-label="AI 运行统计">
        {stats.map(({ icon: Icon, ...item }) => (
          <article key={item.label}><span><Icon aria-hidden="true" size={16} />{item.label}</span><strong>{item.value}</strong><p>{item.note}</p></article>
        ))}
      </section>

      <div className="ai-runtime-grid">
        <ProviderPanel overview={overview} />
        <RuntimePanel overview={overview} />
        <DailyRunChart daily={overview.daily} />
        <RunTypePanel runTypes={overview.run_types} />
        <ModelPanel overview={overview} />
      </div>

      <section className="ai-runtime-ledger">
        <header><div><h2>最近模型运行</h2></div><em>{overview.latest_runs.length} 条记录</em></header>
        <div className="ai-runtime-table-wrap">
          <table>
            <thead><tr><th>时间 / 运行</th><th>业务类型</th><th>Provider / 模型</th><th>模式</th><th>耗时</th><th>Token</th></tr></thead>
            <tbody>{overview.latest_runs.map((run) => (
              <tr key={run.id}>
                <td><strong>{formatTime(run.created_at)}</strong><code>{run.id.slice(-12)}</code></td>
                <td><strong>{run.label}</strong><span>{run.category}</span></td>
                <td><strong>{run.model}</strong><span>{run.provider}</span></td>
                <td><StatusBadge value={{ label: run.execution_mode === "model" ? "真实模型" : "证据降级", tone: run.execution_mode === "model" ? "positive" : "warning" }} /></td>
                <td>{formatDuration(run.duration_ms)}</td>
                <td>{run.input_tokens === null && run.output_tokens === null ? "--" : formatNumber((run.input_tokens ?? 0) + (run.output_tokens ?? 0))}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <section className="ai-runtime-ledger">
        <header><div><h2>待处理 Runtime 审批</h2></div><em>{overview.runtime_approvals.filter((item) => item.status === "pending").length} 条待处理</em></header>
        <div className="ai-runtime-table-wrap"><table><thead><tr><th>请求时间 / 运行</th><th>请求方法</th><th>Skill / 工具</th><th>状态</th><th aria-label="操作" /></tr></thead><tbody>
          {overview.runtime_approvals.map((approval) => <tr key={approval.id}>
            <td><strong>{formatTime(approval.requested_at)}</strong><code>{approval.agent_run_id.slice(-12)}</code></td>
            <td><strong>{approval.request_method}</strong><span>{approval.item_id ?? "--"}</span></td>
            <td><strong>{approval.skill_key ?? "--"}{approval.skill_version ? ` · v${approval.skill_version}` : ""}</strong><span>{approval.tool_keys.join("、") || "--"}</span></td>
            <td><StatusBadge value={{ label: approval.status === "pending" ? "待审批" : approval.status === "approved" ? "已通过" : "已拒绝", tone: approval.status === "pending" ? "warning" : approval.status === "approved" ? "positive" : "critical" }} /></td>
            <td>{approval.status === "pending" && canManage ? <div className="ai-runtime-approval-actions"><button className="button primary compact" onClick={() => void resolveApproval(approval.runtime_session_id, "approve")} type="button">通过</button><button className="button secondary compact" onClick={() => void resolveApproval(approval.runtime_session_id, "decline")} type="button">拒绝</button></div> : null}</td>
          </tr>)}
        </tbody></table></div>
      </section>

      <section className="ai-runtime-ledger">
        <header><div><h2>Runtime 会话</h2></div><em>{runtimeSessions.length} 条记录</em></header>
        <div className="ai-runtime-table-wrap">
          <table>
            <thead><tr><th>时间 / AgentRun</th><th>Runtime / 模型</th><th>Thread / Session</th><th>Turn / Event</th><th>MCP 会话</th><th>状态</th><th aria-label="操作" /></tr></thead>
            <tbody>{runtimeSessions.map((session) => (
              <tr key={session.id}>
                <td><strong>{formatTime(session.created_at)}</strong><code>{session.agent_run_id.slice(-12)}</code></td>
                <td><strong>{session.runtime_key}</strong><span>{session.model ?? "继承配置"}</span></td>
                <td><strong>{session.runtime_thread_id.slice(-16)}</strong><code>{session.runtime_session_id?.slice(-16) ?? "--"}</code></td>
                <td><strong>{session.turn_count} / {session.event_count}</strong><span>{session.latest_event_type ?? "--"}</span></td>
                <td><code>{session.mcp_gateway_session_id?.slice(-16) ?? "--"}</code></td>
                <td><StatusBadge value={runtimeStatus(session.status)} /></td>
                <td><button aria-label="查看 Runtime 会话" className="icon-button runtime-detail-trigger" onClick={() => void loadRuntimeDetail(session.id)} title="查看会话" type="button"><Eye size={15} /></button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </section>

      <section className="ai-probe-ledger">
        <header><div><h2>连接与结构化输出探针</h2></div><em>{overview.probes.length} 条记录</em></header>
        {overview.probes.length ? <div className="ai-probe-list">{overview.probes.map((probe) => (
          <article key={probe.id}>
            <span className={probe.status}><ServerCog size={17} /></span>
            <div><strong>{probe.model} · {probe.protocol}</strong><p>{probe.status === "succeeded" ? `结构化输出${probe.structured_output_supported ? "通过" : "兼容模式"} · ${formatDuration(probe.duration_ms)}` : probe.error_message ?? "Provider 探针失败"}</p></div>
            <div><StatusBadge value={{ label: probe.status === "succeeded" ? "正常" : "失败", tone: probe.status === "succeeded" ? "positive" : "critical" }} /><small>{probe.actor_name} · {formatTime(probe.created_at)}</small></div>
          </article>
        ))}</div> : <div className="ai-runtime-empty"><Gauge size={23} /><strong>尚无 Provider 探针记录</strong></div>}
      </section>

      <section className="ai-probe-ledger">
        <header><div><h2>Codex app-server 握手</h2></div><em>{overview.runtime_probes.length} 条记录</em></header>
        {overview.runtime_probes.length ? <div className="ai-probe-list">{overview.runtime_probes.map((probe) => (
          <article key={probe.id}>
            <span className={probe.status}><Cable size={17} /></span>
            <div><strong>{probe.command_version ?? probe.runtime_key}</strong><p>{probe.status === "succeeded" ? `${probe.protocol} · ${formatDuration(probe.duration_ms)}` : probe.error_message ?? "Runtime 握手失败"}</p></div>
            <div><StatusBadge value={{ label: probe.status === "succeeded" ? "正常" : "失败", tone: probe.status === "succeeded" ? "positive" : "critical" }} /><small>{probe.actor_name} · {formatTime(probe.created_at)}</small></div>
          </article>
        ))}</div> : <div className="ai-runtime-empty"><Cable size={23} /><strong>尚无 Runtime 探针记录</strong></div>}
      </section>
      {runtimeDetailId ? (
        <RuntimeSessionDialog
          detail={runtimeDetail}
          error={runtimeDetailError}
          loading={runtimeDetailLoading}
          onCancel={(session) => setCancelTarget(session)}
          onClose={() => { setRuntimeDetailId(null); setRuntimeDetail(null); setRuntimeDetailError(null); }}
        />
      ) : null}
      {cancelTarget ? (
        <ConfirmDialog
          busy={cancelling}
          confirmLabel="停止运行"
          description={`停止 Runtime 会话 ${cancelTarget.id.slice(-12)}？`}
          detail="当前 Turn 将被中断，已保存的 Thread、事件和审计记录继续保留。"
          onCancel={() => setCancelTarget(null)}
          onConfirm={() => void cancelRuntimeSession()}
          title="停止 Runtime 会话"
          tone="danger"
        />
      ) : null}
    </section>
  );
}

function RuntimeSessionDialog({ detail, error, loading, onCancel, onClose }: { detail: AgentRuntimeSessionDetailResponse | null; error: string | null; loading: boolean; onCancel: (session: AgentRuntimeSessionView) => void; onClose: () => void }) {
  return (
    <Dialog
      busy={loading}
      className="runtime-session-dialog"
      footer={<><button className="button secondary" onClick={onClose} type="button">关闭</button>{detail?.session.can_cancel ? <button className="button secondary" onClick={() => onCancel(detail.session)} type="button"><Square size={14} />停止运行</button> : null}</>}
      onClose={onClose}
      size="large"
      title="Runtime 会话详情"
    >
      {loading ? <div className="runtime-detail-state"><LoaderCircle className="spinning" size={20} /><strong>正在读取会话</strong></div> : null}
      {error ? <InlineCallout description={error} title="会话读取失败" tone="critical" /> : null}
      {detail ? <div className="runtime-session-detail">
        <dl className="runtime-session-summary">
          <div><dt>主体</dt><dd>{detail.actor_name}</dd></div>
          <div><dt>角色分身</dt><dd>{detail.twin_name}{detail.role_twin_version_number ? ` v${detail.role_twin_version_number}` : ""}</dd></div>
          <div><dt>状态</dt><dd><StatusBadge value={runtimeStatus(detail.session.status)} /></dd></div>
          <div><dt>Thread</dt><dd><code>{detail.session.runtime_thread_id}</code></dd></div>
          <div><dt>Turn</dt><dd>{detail.session.turn_count}</dd></div>
          <div><dt>Event</dt><dd>{detail.session.event_count}</dd></div>
        </dl>
        <section className="runtime-detail-section">
          <header><h3>Turn 台账</h3><span>{detail.turns.length}</span></header>
          <div className="runtime-detail-table-wrap"><table><thead><tr><th>轮次 / 时间</th><th>AgentRun / MCP</th><th>上下文</th><th>耗时</th><th>状态</th></tr></thead><tbody>{detail.turns.map((turn) => <tr key={turn.id}><td><strong>Turn {turn.turn_number}</strong><span>{formatTime(turn.started_at)}</span></td><td><code>{turn.agent_run_id}</code><code>{turn.mcp_gateway_session_id ?? "--"}</code></td><td><strong>{turn.evidence_count} 证据 · {turn.context_count} 上下文</strong><span>{turn.model ?? "继承配置"}</span></td><td>{formatDuration(turn.duration_ms)}</td><td><StatusBadge value={runtimeStatus(turn.status)} />{turn.failure_message ? <span className="runtime-turn-error">{turn.failure_message}</span> : null}</td></tr>)}</tbody></table></div>
        </section>
        <section className="runtime-detail-section">
          <header><h3>Event 台账</h3><span>{detail.events.length}</span></header>
          <div className="runtime-event-list">{detail.events.map((item) => <article key={item.id}><span>{item.sequence}</span><div><strong>{item.event_type}</strong><code>{eventPayload(item.event_payload)}</code></div><div><StatusBadge value={runtimeStatus(item.status)} /><time>{formatTime(item.occurred_at)}</time></div></article>)}</div>
        </section>
      </div> : null}
    </Dialog>
  );
}

function ProviderPanel({ overview }: { overview: AIOperationsOverviewResponse }) {
  const provider = overview.provider;
  const latest = overview.probes[0];
  const status = !provider.enabled || !provider.configured ? "unavailable" : latest?.status === "succeeded" ? "healthy" : "unknown";
  return <section className="ai-runtime-panel provider-panel"><header><div><h2>模型接入状态</h2></div><Cpu size={19} /></header><div className="provider-identity"><span className={status}><Bot size={21} /></span><div><strong>{provider.label}</strong><p>{provider.model} · {provider.protocol}</p></div><StatusBadge value={{ label: status === "healthy" ? "在线" : status === "unavailable" ? "未配置" : "待探针", tone: status === "healthy" ? "positive" : "warning" }} /></div><dl><div><dt>端点类型</dt><dd>{provider.endpoint_kind === "official" ? "官方端点" : "私有兼容端点"}</dd></div><div><dt>超时</dt><dd>{provider.timeout_seconds}s</dd></div><div><dt>密钥状态</dt><dd>{provider.configured ? "已装载" : "未装载"}</dd></div><div><dt>结构化输出</dt><dd>{latest?.structured_output_supported ? "已验证" : "待验证"}</dd></div></dl><div className="provider-capabilities">{provider.capabilities.map((item) => <span key={item}>{item}</span>)}</div></section>;
}

function RuntimePanel({ overview }: { overview: AIOperationsOverviewResponse }) {
  const runtime = overview.runtime;
  const latest = overview.runtime_probes[0];
  const status = !runtime.enabled || !runtime.command_available ? "unavailable" : latest?.status === "succeeded" ? "healthy" : "unknown";
  return <section className="ai-runtime-panel runtime-panel"><header><div><h2>Codex Runtime</h2></div><Cable size={19} /></header><div className="provider-identity"><span className={status}><Workflow size={21} /></span><div><strong>{runtime.label}</strong><p>{runtime.runtime_key} · {runtime.protocol}</p></div><StatusBadge value={{ label: status === "healthy" ? "在线" : status === "unavailable" ? "不可用" : "待探针", tone: status === "healthy" ? "positive" : "warning" }} /></div><dl><div><dt>CLI</dt><dd>{runtime.command_available ? "已发现" : "未发现"}</dd></div><div><dt>模型</dt><dd>{runtime.model ?? "继承配置"}</dd></div><div><dt>沙箱</dt><dd>{runtime.default_sandbox}</dd></div><div><dt>审批</dt><dd>{runtime.approval_policy}</dd></div></dl><div className="provider-capabilities">{runtime.capabilities.map((item) => <span key={item}>{item}</span>)}</div></section>;
}

function DailyRunChart({ daily }: { daily: AIDailyStat[] }) {
  const maxRuns = Math.max(...daily.map((item) => item.total_runs), 1);
  return <section className="ai-runtime-panel daily-panel"><header><div><h2>模型运行与降级趋势</h2></div><Activity size={19} /></header><div className="ai-daily-chart">{daily.map((item) => <div key={item.business_date}><div className="ai-daily-bars"><i style={{ "--run-height": `${Math.max((item.successful_runs / maxRuns) * 100, item.successful_runs ? 4 : 0)}%` } as CSSProperties} /><b style={{ "--run-height": `${Math.max((item.degraded_runs / maxRuns) * 100, item.degraded_runs ? 4 : 0)}%` } as CSSProperties} /></div><span>{item.business_date.slice(5)}</span><strong>{item.total_runs}</strong></div>)}</div><footer><span><i />模型成功</span><span><b />证据降级</span></footer></section>;
}

function RunTypePanel({ runTypes }: { runTypes: AIRunTypeStat[] }) {
  const visible = runTypes.slice(0, 8);
  const maxRuns = Math.max(...visible.map((item) => item.total_runs), 1);
  return <section className="ai-runtime-panel run-type-panel"><header><div><h2>业务运行类型</h2></div><Workflow size={19} /></header><div className="ai-run-type-list">{visible.map((item) => <article key={item.run_type}><div><strong>{item.label}</strong><span>{formatDuration(item.average_duration_ms)} · {formatNumber(item.input_tokens + item.output_tokens)} Token</span></div><div><i style={{ width: `${Math.max((item.total_runs / maxRuns) * 100, 4)}%` }} /></div><em>{item.total_runs}</em></article>)}</div></section>;
}

function ModelPanel({ overview }: { overview: AIOperationsOverviewResponse }) {
  return <section className="ai-runtime-panel model-panel"><header><div><h2>模型运行分布</h2></div><Braces size={19} /></header><div className="ai-model-list">{overview.models.map((model) => <article key={`${model.provider}-${model.model}`}><div><strong>{model.model}</strong><span>{model.provider}</span></div><dl><div><dt>运行</dt><dd>{model.total_runs}</dd></div><div><dt>成功</dt><dd>{model.successful_runs}</dd></div><div><dt>降级</dt><dd>{model.degraded_runs}</dd></div><div><dt>均耗时</dt><dd>{formatDuration(model.average_duration_ms)}</dd></div></dl></article>)}</div><footer><span>问答 {overview.stats.answer_runs}</span><span>单客方案 {overview.stats.customer_operation_runs}</span><span>客服 {overview.stats.customer_service_runs}</span><span>评测 {overview.stats.evaluation_batches}</span></footer></section>;
}

function RuntimeState({ icon, title, failed = false }: { icon: React.ReactNode; title: string; failed?: boolean }) {
  return <div className={`ai-runtime-state ${failed ? "failed" : ""}`}>{icon}<strong>{title}</strong></div>;
}
