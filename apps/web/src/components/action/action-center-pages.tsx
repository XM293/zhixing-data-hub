"use client";

import {
  Ban,
  CheckCircle2,
  CirclePause,
  Clock3,
  ClipboardCheck,
  Database,
  FileClock,
  Flag,
  Hand,
  ListChecks,
  LoaderCircle,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  TriangleAlert,
  UserCheck
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ConfirmDialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import type {
  ActionDecisionResponse,
  ActionProposal,
  ActionProposalListResponse,
  ActionProposalStatus,
  ActionSourceType,
  ActionWorkAction,
  ActionWorkEventResponse,
  ActionWorkItem,
  ActionWorkListResponse,
  ActionWorkStatus
} from "@/lib/action-types";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

export type ActionCenterView = "work" | "proposals" | "approvals" | "executions";
type ActionLedgerView = Exclude<ActionCenterView, "work">;

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const STATUS_LABELS: Record<ActionProposalStatus, { label: string; tone: "warning" | "positive" | "critical" }> = {
  pending_approval: { label: "待审批", tone: "warning" },
  approved: { label: "已批准", tone: "positive" },
  rejected: { label: "已驳回", tone: "critical" }
};

const WORK_STATUS_LABELS: Record<ActionWorkStatus, { label: string; tone: "info" | "warning" | "positive" | "critical" }> = {
  ready: { label: "待领取", tone: "info" },
  claimed: { label: "已领取", tone: "warning" },
  in_progress: { label: "进行中", tone: "warning" },
  blocked: { label: "已阻塞", tone: "critical" },
  completed: { label: "已完成", tone: "positive" }
};

function sourceLabel(source: ActionSourceType): string {
  if (source === "meeting-decision") return "数字会议";
  if (source === "customer-operation") return "客户运营";
  return "经营诊断";
}

function formatTime(value: string | null): string {
  if (!value) return "未发生";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

export function ActionCenterPage({ view, inbox = false }: { view: ActionCenterView; inbox?: boolean }) {
  return view === "work" ? <ActionWorkPage inbox={inbox} /> : <ActionLedgerPage view={view} />;
}

function ActionLedgerPage({ view }: { view: ActionLedgerView }) {
  const { can, identity, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<ActionProposalListResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deciding, setDeciding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/action-proposals`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取行动中心"));
    const result = (await response.json()) as ActionProposalListResponse;
    setData(result);
    setSelectedKey((current) => current ?? result.items.find((item) => item.status === "pending_approval")?.key ?? result.items[0]?.key ?? null);
  }, [roleId]);

  useEffect(() => {
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "行动中心连接失败"))
      .finally(() => setLoading(false));
  }, [load]);

  const selected = useMemo(
    () => data?.items.find((item) => item.key === selectedKey) ?? data?.items[0] ?? null,
    [data, selectedKey]
  );

  async function decide(item: ActionProposal, decision: "approve" | "reject", comment: string): Promise<boolean> {
    setDeciding(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/action-proposals/${encodeURIComponent(item.key)}/decision`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Zhixing-Demo-Actor": roleId
        },
        body: JSON.stringify({
          decision,
          comment,
          idempotency_key: `approval:${item.key}:${decision}:v1`
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "行动审批失败"));
      const result = (await response.json()) as ActionDecisionResponse;
      setData((current) => current ? {
        ...current,
        stats: {
          ...current.stats,
          pending_approval: current.stats.pending_approval - 1,
          approved: current.stats.approved + (result.item.status === "approved" ? 1 : 0),
          rejected: current.stats.rejected + (result.item.status === "rejected" ? 1 : 0),
          recorded_executions: current.stats.recorded_executions + (result.item.execution ? 1 : 0)
        },
        items: current.items.map((candidate) => candidate.key === result.item.key ? result.item : candidate)
      } : current);
      notify({ title: decision === "approve" ? "行动提案已批准" : "行动提案已驳回", description: item.title, tone: decision === "approve" ? "success" : "warning" });
      return true;
    } catch (reason: unknown) {
      notify({ title: "行动审批失败", description: reason instanceof Error ? reason.message : "请重试", tone: "error" });
      return false;
    } finally {
      setDeciding(false);
    }
  }

  if (loading) return <ActionPageState title="正在读取行动提案与审批台账" />;
  if (!data) return <ActionPageState error title={error ?? "行动中心暂不可用"} />;

  return <div className="action-center-page">
    <ActionHeader data={data} onRefresh={() => void load()} view={view} />
    {error ? <InlineCallout description={error} title="最近一次操作未完成" tone="critical" /> : null}
    <ActionStats data={data} />
    {view === "proposals" ? <ProposalLedger items={data.items} /> : null}
    {view === "approvals" ? <ApprovalWorkspace actorKey={identity?.actor.principal_key ?? null} canApprove={can("action.approve")} deciding={deciding} items={data.items} onDecide={decide} onSelect={setSelectedKey} selected={selected} /> : null}
    {view === "executions" ? <ExecutionLedger items={data.items} /> : null}
  </div>;
}

function ActionHeader({ data, onRefresh, view }: { data: ActionProposalListResponse; onRefresh: () => void; view: ActionLedgerView }) {
  const copy = {
    proposals: ["ACTION PROPOSALS · DATABASE", "行动提议", "汇总数字会议、客户运营与经营诊断产生的 R2 内部行动提案，审批前不会改变任何外部系统。"],
    approvals: ["HUMAN APPROVAL · CONTROLLED WRITE", "行动审批", "审批人复核证据、KPI 与停止条件；发起人与审批人必须分离。"],
    executions: ["INTERNAL LEDGER · ZERO EXTERNAL WRITE", "执行台账", "当前仅登记内部行动台账，真实任务系统与外部连接器仍保持零写入。"]
  }[view];
  return <PageHeader
    actions={<button className="button secondary" onClick={onRefresh} type="button"><RefreshCw size={15} />刷新台账</button>}
    description={copy[2]}
    eyebrow={copy[0]}
    meta={`${data.stats.total} 条数据库提案`}
    title={copy[1]}
  />;
}

function ActionStats({ data }: { data: ActionProposalListResponse }) {
  return <section className="action-stat-band" aria-label="行动中心统计">
    <article><span><ListChecks size={16} />行动提案</span><strong>{data.stats.total}</strong><p>会议、客户与经营诊断统一台账</p></article>
    <article><span><FileClock size={16} />待人工审批</span><strong>{data.stats.pending_approval}</strong><p>审批前外部变化为零</p></article>
    <article><span><ShieldCheck size={16} />已形成结论</span><strong>{data.stats.approved + data.stats.rejected}</strong><p>{data.stats.approved} 批准 · {data.stats.rejected} 驳回</p></article>
    <article><span><Database size={16} />内部台账</span><strong>{data.stats.recorded_executions}</strong><p>外部写入 0</p></article>
  </section>;
}

function ProposalLedger({ items }: { items: ActionProposal[] }) {
  if (!items.length) return <ActionEmpty />;
  return <section className="action-ledger-section">
    <header><div><span>PROPOSAL LEDGER</span><h2>跨业务行动分解</h2></div><em>R2 草拟 · 数据库持久化</em></header>
    <div className="action-ledger-table">
      <div className="action-ledger-head"><span>行动与来源</span><span>负责人 / 时间</span><span>KPI / 停止条件</span><span>状态</span></div>
      {items.map((item, index) => <article key={item.key}>
        <b>{String(index + 1).padStart(2, "0")}</b>
        <div><Link href={item.source_route}>{item.title}</Link><small>{sourceLabel(item.source_type)} · {item.source_label}</small><small>{item.scope_key} · {item.evidence_refs.join(" · ")}</small></div>
        <div><strong>{item.owner}</strong><small>{item.due_hint}</small></div>
        <div><strong>{item.kpi}</strong><small>停止：{item.stop_condition}</small></div>
        <StatusBadge value={STATUS_LABELS[item.status]} />
      </article>)}
    </div>
  </section>;
}

function ApprovalWorkspace({ actorKey, canApprove, deciding, items, onDecide, onSelect, selected }: {
  actorKey: string | null;
  canApprove: boolean;
  deciding: boolean;
  items: ActionProposal[];
  onDecide: (item: ActionProposal, decision: "approve" | "reject", comment: string) => Promise<boolean>;
  onSelect: (key: string) => void;
  selected: ActionProposal | null;
}) {
  const [decision, setDecision] = useState<"approve" | "reject" | null>(null);
  const [decisionComment, setDecisionComment] = useState("");
  if (!items.length || !selected) return <ActionEmpty />;
  const sameActor = actorKey !== null && selected.requested_by_actor_key === actorKey;
  const actionable = selected.status === "pending_approval" && canApprove && !sameActor;
  function openDecision(next: "approve" | "reject") {
    setDecision(next);
    setDecisionComment(next === "approve" ? "批准登记内部行动台账，外部系统保持零写入。" : "当前证据或执行条件不足，退回行动提案。");
  }
  return <>
  <div className="action-approval-layout">
    <section className="approval-queue">
      <header><div><span>APPROVAL QUEUE</span><h2>待处理与历史提案</h2></div><em>{items.filter((item) => item.status === "pending_approval").length} 条待处理</em></header>
      <div>{items.map((item) => <button className={item.key === selected.key ? "active" : ""} key={item.key} onClick={() => onSelect(item.key)} type="button">
        <span className={`approval-state ${item.status}`} />
        <div><strong>{item.title}</strong><small>{item.owner} · {item.due_hint}</small></div>
        <StatusBadge value={STATUS_LABELS[item.status]} />
      </button>)}</div>
    </section>
    <section className="approval-detail">
      <header><div><span>{selected.risk_level} · {sourceLabel(selected.source_type)} · {selected.target_system}</span><h2>{selected.title}</h2><p>{selected.key}</p><Link href={selected.source_route}>查看来源：{selected.source_label}</Link></div><StatusBadge value={STATUS_LABELS[selected.status]} /></header>
      <div className="approval-identity-strip">
        <div><span>提案人</span><strong>{selected.requested_by_name}</strong></div>
        <div><span>审批人</span><strong>{selected.approved_by_name ?? "等待不同主体审批"}</strong></div>
        <div><span>外部写入</span><strong>0</strong></div>
      </div>
      <div className="approval-evidence-grid">
        <div><span>成功指标</span><p>{selected.kpi}</p></div>
        <div><span>停止条件</span><p>{selected.stop_condition}</p></div>
        <div><span>证据引用</span><p>{selected.evidence_refs.join(" · ")}</p></div>
        <div><span>幂等键</span><code>{selected.idempotency_key}</code></div>
      </div>
      {selected.approval_events.length ? <div className="approval-decision-result"><CheckCircle2 size={18} /><div><strong>{selected.approved_by_name} · {formatTime(selected.approved_at)}</strong><p>{selected.decision_comment}</p></div></div> : null}
      {!canApprove ? <InlineCallout description="当前角色可以查看证据与结论，但没有 action.approve 权限。" title="只读角色" tone="warning" /> : null}
      {sameActor ? <InlineCallout description="当前角色是该提案的发起人，职责分离规则禁止自行审批。" title="不能自批" tone="warning" /> : null}
      <footer>
        <button className="button secondary danger" disabled={!actionable || deciding} onClick={() => openDecision("reject")} type="button"><Ban size={15} />驳回提案</button>
        <button className="button primary" disabled={!actionable || deciding} onClick={() => openDecision("approve")} type="button">{deciding ? <LoaderCircle className="spinning" size={16} /> : <UserCheck size={16} />}批准并登记内部台账</button>
      </footer>
    </section>
  </div>
  {decision ? <ConfirmDialog busy={deciding} confirmDisabled={decisionComment.trim().length < 3} confirmLabel={decision === "approve" ? "确认批准" : "确认驳回"} description={decision === "approve" ? `批准 ${selected.title}？` : `驳回 ${selected.title}？`} detail={decision === "approve" ? "批准后将登记内部执行台账，但不会写入任何外部系统。" : "驳回后提案不会进入内部执行台账。"} onCancel={() => setDecision(null)} onConfirm={() => void onDecide(selected, decision, decisionComment).then((completed) => { if (completed) setDecision(null); })} title={decision === "approve" ? "批准行动提案" : "驳回行动提案"} tone={decision === "approve" ? "primary" : "danger"}><label className="confirm-input-field"><span>审批意见</span><textarea autoFocus onChange={(event) => setDecisionComment(event.target.value)} rows={4} value={decisionComment} /></label></ConfirmDialog> : null}
  </>;
}

function ExecutionLedger({ items }: { items: ActionProposal[] }) {
  const executions = items.filter((item) => item.execution);
  if (!executions.length) return <ActionEmpty execution />;
  return <section className="action-ledger-section execution-ledger-section">
    <header><div><span>EXECUTION LEDGER</span><h2>内部台账记录</h2></div><em>所有记录 external_write = false</em></header>
    <div className="execution-ledger-list">{executions.map((item) => <article key={item.key}>
      <span><ClipboardCheck size={18} /></span>
      <div><strong>{item.title}</strong><small>{sourceLabel(item.source_type)} · {item.execution?.key} · {formatTime(item.execution?.finished_at ?? null)}</small></div>
      <div><span>登记结果</span><p>{String(item.execution?.result.message ?? "已登记内部行动台账")}</p></div>
      <div><span>幂等键</span><code>{item.execution?.idempotency_key}</code></div>
      <StatusBadge value={{ label: "内部台账已登记", tone: "positive" }} />
  </article>)}</div>
  </section>;
}

function ActionWorkPage({ inbox = false }: { inbox?: boolean }) {
  const { roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<ActionWorkListResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [comment, setComment] = useState("");
  const [evidence, setEvidence] = useState("");
  const [error, setError] = useState<string | null>(null);
  const requestKeys = useRef(new Map<string, string>());

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/action-work-items`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取运营工作台"));
    const payload = (await response.json()) as ActionWorkListResponse;
    setData(payload);
    setSelectedKey((current) => current && payload.items.some((item) => item.key === current)
      ? current
      : payload.items.find((item) => item.assignee_name?.includes(payload.actor_name.split(" / ")[0]))?.key
        ?? payload.items.find((item) => item.status !== "completed")?.key
        ?? payload.items[0]?.key
        ?? null);
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    setData(null);
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "运营工作台连接失败"))
      .finally(() => setLoading(false));
  }, [load]);

  const selected = useMemo(
    () => data?.items.find((item) => item.key === selectedKey) ?? data?.items[0] ?? null,
    [data, selectedKey]
  );

  useEffect(() => {
    setComment("");
    setEvidence("");
  }, [selectedKey]);

  async function transition(action: ActionWorkAction) {
    if (!selected) return;
    const requestSlot = `${selected.key}:${action}:${selected.version}`;
    const existingKey = requestKeys.current.get(requestSlot);
    const idempotencyKey = existingKey ?? `work:${selected.key}:${action}:${crypto.randomUUID()}`;
    requestKeys.current.set(requestSlot, idempotencyKey);
    const normalizedComment = comment.trim() || defaultWorkComment(action, selected.title);
    const evidenceRefs = Array.from(new Set(evidence.split(/[\s,，]+/).map((item) => item.trim()).filter(Boolean)));
    setUpdating(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/action-work-items/${encodeURIComponent(selected.key)}/events`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Zhixing-Demo-Actor": roleId
        },
        body: JSON.stringify({
          action,
          comment: normalizedComment,
          evidence_refs: evidenceRefs,
          expected_version: selected.version,
          idempotency_key: idempotencyKey
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "工作项更新失败"));
      const payload = (await response.json()) as ActionWorkEventResponse;
      requestKeys.current.delete(requestSlot);
      notify({ title: "工作项已更新", description: `${payload.item.title} · ${WORK_STATUS_LABELS[payload.item.status].label}`, tone: "success" });
      setSelectedKey(payload.item.key);
      setComment("");
      setEvidence("");
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "工作项更新失败");
    } finally {
      setUpdating(false);
    }
  }

  if (loading) return <ActionPageState title="正在读取授权范围内的运营工作项" />;
  if (!data) return <ActionPageState error title={error ?? "运营工作台暂不可用"} />;

  return <div className="action-center-page action-work-page">
    <PageHeader
      actions={<button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />{inbox ? "刷新待办" : "刷新工作台"}</button>}
      description={inbox ? "汇总当前授权范围内的待办、阻塞和执行事项；所有状态均来自数据库工作项。" : "承接已批准的经营行动，记录领取、推进、阻塞与完成结果；当前所有工作仍限定在企业内部。"}
      eyebrow={inbox ? "INBOX · AUTHORIZED WORK QUEUE" : "OPERATION WORKBENCH · GOVERNED EXECUTION"}
      meta={`${data.actor_name} · ${data.stats.mine} 项与我相关`}
      title={inbox ? "待办中心" : "运营工作台"}
    />
    {error ? <InlineCallout description={error} title="最近一次操作未完成" tone="critical" /> : null}
    <ActionWorkStats data={data} />
    <ActionWorkWorkspace
      comment={comment}
      data={data}
      evidence={evidence}
      onComment={setComment}
      onEvidence={setEvidence}
      onSelect={setSelectedKey}
      onTransition={transition}
      selected={selected}
      updating={updating}
    />
  </div>;
}

function ActionWorkStats({ data }: { data: ActionWorkListResponse }) {
  const items = [
    ["待领取", data.stats.ready, Hand],
    ["推进中", data.stats.claimed + data.stats.in_progress, Play],
    ["已阻塞", data.stats.blocked, CirclePause],
    ["已完成", data.stats.completed, CheckCircle2],
    ["与我相关", data.stats.mine, UserCheck]
  ] as const;
  return <section aria-label="运营工作项统计" className="action-work-stat-band">
    {items.map(([label, value, Icon]) => <article key={label}><Icon size={16} /><span>{label}</span><strong>{value}</strong></article>)}
  </section>;
}

function ActionWorkWorkspace({ comment, data, evidence, onComment, onEvidence, onSelect, onTransition, selected, updating }: {
  comment: string;
  data: ActionWorkListResponse;
  evidence: string;
  onComment: (value: string) => void;
  onEvidence: (value: string) => void;
  onSelect: (key: string) => void;
  onTransition: (action: ActionWorkAction) => Promise<void>;
  selected: ActionWorkItem | null;
  updating: boolean;
}) {
  if (!selected) return <ActionEmpty work />;
  return <div className="action-work-layout">
    <section className="action-work-queue">
      <header><div><span>AUTHORIZED WORK QUEUE</span><h2>授权范围工作项</h2></div><em>{data.items.length} 项</em></header>
      <div>{data.items.map((item) => <button className={item.key === selected.key ? "active" : ""} key={item.key} onClick={() => onSelect(item.key)} type="button">
        <span className={`work-priority ${item.priority}`}><Flag size={13} /></span>
        <div><strong>{item.title}</strong><small>{item.scope_key} · {item.assignee_name ?? "等待领取"}</small></div>
        <StatusBadge value={WORK_STATUS_LABELS[item.status]} />
      </button>)}</div>
    </section>
    <section className="action-work-detail">
      <header>
        <div><span>{sourceLabel(selected.source_type)} · {selected.scope_key} · v{selected.version}</span><h2>{selected.title}</h2><Link href={selected.source_route}>查看来源：{selected.source_label}</Link></div>
        <StatusBadge value={WORK_STATUS_LABELS[selected.status]} />
      </header>
      <div className="action-work-owner-strip">
        <div><span>建议责任角色</span><strong>{selected.owner_role}</strong></div>
        <div><span>当前负责人</span><strong>{selected.assignee_name ?? "等待领取"}</strong></div>
        <div><span>时间要求</span><strong>{selected.due_hint}</strong></div>
        <div><span>外部写入</span><strong>0</strong></div>
      </div>
      <div className="action-work-targets">
        <article><span>成功指标</span><p>{selected.kpi}</p></article>
        <article><span>停止条件</span><p>{selected.stop_condition}</p></article>
        {selected.blocker_reason ? <article className="blocked"><span>当前阻塞</span><p>{selected.blocker_reason}</p></article> : null}
        {selected.result_summary ? <article className="completed"><span>完成结果</span><p>{selected.result_summary}</p><small>{selected.result_evidence_refs.join(" · ") || "未附加结果证据"}</small></article> : null}
      </div>
      <section className="action-work-timeline">
        <header><span>APPEND-ONLY EVENTS</span><strong>{selected.events.length} 条进度事件</strong></header>
        <div>{selected.events.map((event) => <article key={event.id}>
          <span><Clock3 size={13} /></span>
          <div><strong>{event.actor_name} · {workEventLabel(event.event_type)}</strong><p>{event.comment}</p><small>{formatTime(event.created_at)} · {event.from_status ?? "新建"} → {event.to_status}</small></div>
        </article>)}</div>
      </section>
      {selected.available_actions.length ? <footer className="action-work-controls">
        <label><span>进度说明</span><textarea onChange={(event) => onComment(event.target.value)} placeholder="填写本次领取、推进、阻塞或完成说明" rows={3} value={comment} /></label>
        <label><span>结果证据编号</span><input onChange={(event) => onEvidence(event.target.value)} placeholder="E1, E2 或内部凭据编号" value={evidence} /></label>
        <div>{selected.available_actions.map((action) => {
          const Icon = workActionIcon(action);
          return <button className={`button ${action === "complete" || action === "claim" ? "primary" : "secondary"}`} disabled={updating} key={action} onClick={() => void onTransition(action)} type="button"><Icon size={15} />{workActionLabel(action)}</button>;
        })}</div>
      </footer> : <InlineCallout description={selected.status === "completed" ? "结果已进入内部台账。只有具备工作项管理权限的负责人可以重新打开。" : "该工作项已由其他负责人领取，当前账号可以查看进度但不能覆盖。"} title="当前为只读状态" tone="info" />}
    </section>
  </div>;
}

function workActionLabel(action: ActionWorkAction): string {
  return { claim: "领取工作项", start: "开始推进", block: "标记阻塞", complete: "提交完成", release: "释放工作项", reopen: "重新打开" }[action];
}

function workEventLabel(action: "created" | ActionWorkAction): string {
  return action === "created" ? "创建工作项" : workActionLabel(action);
}

function defaultWorkComment(action: ActionWorkAction, title: string): string {
  return `${workActionLabel(action)}：${title}`;
}

function workActionIcon(action: ActionWorkAction) {
  return { claim: Hand, start: Play, block: CirclePause, complete: CheckCircle2, release: RotateCcw, reopen: RotateCcw }[action];
}

function ActionEmpty({ execution = false, work = false }: { execution?: boolean; work?: boolean }) {
  const title = work ? "当前授权范围还没有运营工作项" : execution ? "尚无内部执行台账" : "尚无数据库行动提案";
  const detail = work ? "经营诊断、客户运营或数字会议行动审批通过后会进入这里。" : execution ? "批准行动提案后会在这里登记，不会调用外部系统。" : "可以从数字会议、客户运营或经营诊断选择步骤进入审批。";
  return <div className="action-empty-state"><TriangleAlert size={26} /><strong>{title}</strong><span>{detail}</span><div><Link className="button secondary" href="/console/analysis/store-review">进入经营诊断</Link><Link className="button secondary" href="/console/meetings">进入数字会议</Link><Link className="button secondary" href="/console/data/products/customers">进入客户 360</Link></div></div>;
}

function ActionPageState({ error = false, title }: { error?: boolean; title: string }) {
  return <div className={`action-page-state ${error ? "error" : ""}`}>{error ? <TriangleAlert size={26} /> : <LoaderCircle className="spinning" size={26} />}<strong>{title}</strong></div>;
}
