"use client";

import {
  BadgeCheck,
  CheckCircle2,
  CircleAlert,
  Clock3,
  FileCheck2,
  Hand,
  Inbox,
  LoaderCircle,
  MessageSquareMore,
  RefreshCcw,
  RotateCcw,
  ShieldCheck,
  UserCheck,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Dialog } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiErrorMessage } from "@/lib/api-error";
import { apiFetch } from "@/lib/api-client";
import type {
  AgentFeedbackStudioResponse,
  HandoffStatus,
  HumanHandoffCase,
  ResolutionType
} from "@/lib/agent-feedback-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const STATUS_COPY: Record<HandoffStatus, { label: string; tone: "warning" | "info" | "positive" }> = {
  open: { label: "待认领", tone: "warning" },
  in_review: { label: "处理中", tone: "info" },
  resolved: { label: "已解决", tone: "positive" }
};

const PRIORITY_LABELS = { normal: "普通", high: "高优先", urgent: "紧急" } as const;
const CATEGORY_LABELS = {
  helpful: "有帮助",
  inaccurate: "事实不准确",
  incomplete: "回答不完整",
  unsafe: "存在风险",
  scope_issue: "权限或范围",
  handoff: "请求人工"
} as const;
const EVENT_LABELS = {
  feedback_submitted: "提交反馈",
  assigned: "认领工单",
  note_added: "处理记录",
  resolved: "解决工单",
  reopened: "重新打开"
} as const;

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

export function AgentFeedbackPage() {
  const { roleId } = useExperience();
  const [studio, setStudio] = useState<AgentFeedbackStudioResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<"add_note" | "resolve" | null>(null);
  const [acting, setActing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/agent-feedback/studio`, {
        cache: "no-store",
        headers: { "X-Zhixing-Demo-Actor": roleId }
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "反馈工单接口不可用"));
      const payload = (await response.json()) as AgentFeedbackStudioResponse;
      setStudio(payload);
      setSelectedId((current) =>
        current && payload.cases.some((item) => item.id === current)
          ? current
          : payload.cases[0]?.id ?? null
      );
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "无法读取反馈工单");
    } finally {
      setLoading(false);
    }
  }, [roleId]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => studio?.cases.find((item) => item.id === selectedId) ?? null,
    [selectedId, studio]
  );

  const directAction = async (nextAction: "assign_to_me" | "reopen") => {
    if (!selected) return;
    setActing(true);
    setError(null);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/agent-feedback/cases/${selected.id}/actions`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Zhixing-Demo-Actor": roleId
          },
          body: JSON.stringify({
            action: nextAction,
            message:
              nextAction === "assign_to_me"
                ? "已由当前负责人认领并开始核验回答证据。"
                : "收到新的业务信息，重新打开工单继续处理。",
            client_request_key: `${selected.id}-${nextAction}-${Date.now().toString(36)}`
          })
        }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "工单状态更新失败"));
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "工单状态更新失败");
    } finally {
      setActing(false);
    }
  };

  if (loading && !studio) {
    return <div className="feedback-page-state"><LoaderCircle className="spinning" size={24} /><strong>正在读取反馈队列</strong><span>核对运行、提问人和处理事件</span></div>;
  }

  if (error && !studio) {
    return <div className="feedback-page-state failed"><CircleAlert size={24} /><strong>反馈队列暂时不可用</strong><span>{error}</span><button className="button secondary" onClick={() => void load()} type="button"><RefreshCcw size={15} />重新加载</button></div>;
  }

  const stats = studio?.stats;
  return (
    <div className="agent-feedback-page">
      <PageHeader
        actions={<button className="button secondary" disabled={loading} onClick={() => void load()} type="button"><RefreshCcw className={loading ? "spinning" : ""} size={15} />刷新队列</button>}
        description="将员工对分身回答的纠错和人工请求转成可认领、可解决、可重开的数据库工单。"
        eyebrow="AGENT FEEDBACK · HUMAN HANDOFF LEDGER"
        meta={`${stats?.feedback_event_count ?? 0} 条不可变处理事件`}
        title="回答反馈与人工接管"
      />
      <section aria-label="反馈工单统计" className="feedback-stat-band">
        <FeedbackStat icon={<Inbox size={17} />} label="全部工单" value={stats?.case_count ?? 0} />
        <FeedbackStat icon={<Clock3 size={17} />} label="待认领" value={stats?.open_count ?? 0} />
        <FeedbackStat icon={<UserCheck size={17} />} label="处理中" value={stats?.in_review_count ?? 0} />
        <FeedbackStat critical icon={<CircleAlert size={17} />} label="紧急未结" value={stats?.urgent_count ?? 0} />
        <FeedbackStat icon={<BadgeCheck size={17} />} label="已解决" value={stats?.resolved_count ?? 0} />
      </section>
      {error ? <InlineCallout description={error} title="部分操作未完成" tone="critical" /> : null}
      <div className="feedback-workspace">
        <aside aria-label="人工接管工单队列" className="feedback-case-rail">
          <header><div><small>HANDOFF QUEUE</small><h2>接管队列</h2></div><strong>{studio?.cases.length ?? 0}</strong></header>
          <div className="feedback-case-list">
            {studio?.cases.map((item) => (
              <button className={item.id === selectedId ? "active" : ""} key={item.id} onClick={() => setSelectedId(item.id)} type="button">
                <span className={`feedback-priority ${item.priority}`} />
                <div><small>{PRIORITY_LABELS[item.priority]} · {CATEGORY_LABELS[item.category]}</small><strong>{item.question}</strong><p>{item.opened_by_name} · {formatTime(item.updated_at)}</p></div>
                <StatusBadge value={STATUS_COPY[item.status]} />
              </button>
            ))}
            {!studio?.cases.length ? <div className="feedback-empty"><CheckCircle2 size={24} /><strong>当前没有人工接管工单</strong><span>员工提交纠错或转人工后会进入这里。</span></div> : null}
          </div>
        </aside>
        <main className="feedback-case-detail">
          {selected ? (
            <>
              <header><div><small>{CATEGORY_LABELS[selected.category]} · {PRIORITY_LABELS[selected.priority]}</small><h2>{selected.question}</h2><p>{selected.twin_name} · 分身版本 v{selected.role_twin_version_number ?? "—"} · {selected.execution_mode === "model" ? "真实模型" : "证据降级"}</p></div><StatusBadge value={STATUS_COPY[selected.status]} /></header>
              <section className="feedback-case-identity"><div><span>提问人</span><strong>{selected.opened_by_name}</strong></div><div><span>处理人</span><strong>{selected.assigned_to_name ?? "尚未认领"}</strong></div><div><span>AgentRun</span><code>{selected.agent_run_id}</code></div></section>
              <section className="feedback-answer-compare"><article><span>原始回答</span><p>{selected.answer}</p></article><article className={selected.resolution_summary ? "resolved" : "pending"}><span>人工处理结论</span><p>{selected.resolution_summary ?? "负责人解决工单后在此形成可回传给提问人的正式结论。"}</p>{selected.resolution_type ? <small>{selected.resolution_type}</small> : null}{selected.evaluation_candidate_status ? <small className={`feedback-evaluation-state ${selected.evaluation_candidate_status}`}>{selected.evaluation_candidate_status === "accepted" ? "已进入固定回归集" : selected.evaluation_candidate_status === "rejected" ? "评测候选已拒绝" : "已生成待审核评测候选"}</small> : null}</article></section>
              <section className="feedback-event-ledger"><header><div><small>APPEND-ONLY LEDGER</small><h3>处理事件</h3></div><strong>{selected.events.length}</strong></header><div>{selected.events.map((event) => <article key={event.id}><span className={`feedback-event-dot ${event.event_type}`} /><div><strong>{EVENT_LABELS[event.event_type]} · {event.actor_name}</strong><p>{event.message}</p>{event.expected_answer ? <blockquote>{event.expected_answer}</blockquote> : null}<small>{formatTime(event.created_at)} · {event.from_status ? `${STATUS_COPY[event.from_status].label} → ` : ""}{event.to_status ? STATUS_COPY[event.to_status].label : "仅记录"}</small></div></article>)}</div></section>
              <footer>
                {selected.status === "open" ? <button className="button secondary" disabled={acting} onClick={() => void directAction("assign_to_me")} type="button"><Hand size={15} />认领处理</button> : null}
                {selected.status !== "resolved" ? <button className="button secondary" onClick={() => setAction("add_note")} type="button"><MessageSquareMore size={15} />记录进展</button> : null}
                {selected.status !== "resolved" ? <button className="button primary" onClick={() => setAction("resolve")} type="button"><FileCheck2 size={15} />解决工单</button> : null}
                {selected.status === "resolved" ? <button className="button secondary" disabled={acting} onClick={() => void directAction("reopen")} type="button"><RotateCcw size={15} />重新打开</button> : null}
              </footer>
            </>
          ) : <div className="feedback-detail-empty"><ShieldCheck size={26} /><strong>选择一条工单查看处理链路</strong><span>原始回答、提问人、处理人和所有事件都来自数据库。</span></div>}
        </main>
      </div>
      {selected && action ? <FeedbackCaseActionDialog action={action} caseItem={selected} onClose={() => setAction(null)} onCompleted={async () => { setAction(null); await load(); }} roleId={roleId} /> : null}
    </div>
  );
}

function FeedbackStat({ icon, label, value, critical = false }: { icon: React.ReactNode; label: string; value: number; critical?: boolean }) {
  return <article className={critical && value > 0 ? "critical" : ""}><span>{icon}{label}</span><strong>{value}</strong></article>;
}

function FeedbackCaseActionDialog({ action, caseItem, roleId, onClose, onCompleted }: { action: "add_note" | "resolve"; caseItem: HumanHandoffCase; roleId: string; onClose: () => void; onCompleted: () => Promise<void> }) {
  const [message, setMessage] = useState(action === "resolve" ? "已核对原始问题、回答证据和当前有效制度。" : "正在核对回答证据和业务口径。");
  const [resolutionType, setResolutionType] = useState<ResolutionType>("corrected_answer");
  const [resolutionSummary, setResolutionSummary] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/agent-feedback/cases/${caseItem.id}/actions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({
          action,
          message,
          resolution_type: action === "resolve" ? resolutionType : null,
          resolution_summary: action === "resolve" ? resolutionSummary : null,
          client_request_key: `${caseItem.id}-${action}-${Date.now().toString(36)}`
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "工单处理未写入"));
      await onCompleted();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "工单处理未写入");
    } finally {
      setSubmitting(false);
    }
  };

  return <Dialog busy={submitting} className="knowledge-dialog feedback-action-dialog unified" eyebrow="HUMAN HANDOFF EVENT · APPEND ONLY" onClose={onClose} size="medium" title={action === "resolve" ? "解决人工接管工单" : "追加处理记录"}><form onSubmit={(event) => void submit(event)}><div className="feedback-action-target"><CircleAlert size={18} /><div><strong>{caseItem.question}</strong><span>{caseItem.opened_by_name} · {caseItem.agent_run_id}</span></div></div>{action === "resolve" ? <label><span>处理类型</span><select onChange={(event) => setResolutionType(event.target.value as ResolutionType)} value={resolutionType}><option value="corrected_answer">给出纠正答案</option><option value="policy_update">推动制度更新</option><option value="memory_update">修订角色记忆</option><option value="no_issue">核验无问题</option><option value="rerouted">转交其他业务流程</option></select></label> : null}<label><span>处理记录</span><textarea onChange={(event) => setMessage(event.target.value)} rows={4} value={message} /></label>{action === "resolve" ? <label><span>回传给提问人的处理结论</span><textarea onChange={(event) => setResolutionSummary(event.target.value)} placeholder="说明正确结论、依据和后续动作。" rows={6} value={resolutionSummary} /></label> : null}{error ? <InlineCallout description={error} title="工单处理失败" tone="critical" /> : null}<footer><button className="button secondary" onClick={onClose} type="button">取消</button><button className="button primary" disabled={submitting || message.trim().length < 2 || (action === "resolve" && resolutionSummary.trim().length < 2)} type="submit">{submitting ? <LoaderCircle className="spinning" size={15} /> : <FileCheck2 size={15} />}{submitting ? "正在写入" : action === "resolve" ? "解决并回传" : "追加处理事件"}</button></footer></form></Dialog>;
}
