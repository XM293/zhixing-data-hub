"use client";

import {
  Bot,
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  Clock3,
  FileText,
  LoaderCircle,
  MemoryStick,
  MessageSquareWarning,
  MessageSquareText,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  ThumbsUp,
  TrendingUp,
  X
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Dialog } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge, Surface } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiErrorMessage } from "@/lib/api-error";
import { apiFetch } from "@/lib/api-client";
import type { AgentFeedbackStudioResponse, AgentRunFeedbackResponse, FeedbackKind, HandoffPriority } from "@/lib/agent-feedback-types";
import type { RoleTwinProfile, TwinAnswerResponse } from "@/lib/knowledge-types";
import { getActiveWorkspaceKey, useActiveWorkspaceKey } from "@/lib/workspace-context";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const DEFAULT_QUESTION = "请汇报星云铁皮柜2026年8月的销售GMV与净放款情况，以及核心爆款Listing有哪些？";
const SUGGESTIONS = [
  "请汇报星云铁皮柜2026年8月的销售GMV与净放款情况，以及核心爆款Listing有哪些？",
  "星云铁皮柜北美6大站点覆盖情况与对账容差基准如何？",
  "星云铁皮柜2026年7月Prime Day大促与8月淡季的销售及退款差异分析",
  "9 月退款率如何考核？",
  "旗舰店广告预算应该如何止损？",
  "智能客服遇到哪些情况必须转人工？"
];

function formatTime(value: string | null): string {
  if (!value) return "尚无运行";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(value));
}

function formatMetricValue(value: number | null, unit: string): string {
  if (value === null) return "暂无";
  return `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value)}${unit}`;
}

function formatMetricRange(dateFrom: string | null, dateTo: string | null): string {
  if (!dateFrom || !dateTo) return "暂无时间范围";
  return `${dateFrom.slice(0, 10)} 至 ${dateTo.slice(0, 10)}`;
}

export function TwinAssistantPage() {
  const { snapshot, roleId } = useExperience();
  const workspaceKey = useActiveWorkspaceKey();
  const currentRole = snapshot.roles.find((role) => role.id === roleId) ?? snapshot.roles[0];
  const [profile, setProfile] = useState<RoleTwinProfile | null>(null);
  const [question, setQuestion] = useState(DEFAULT_QUESTION);
  const [conversation, setConversation] = useState<Array<{ question: string; answer: TwinAnswerResponse }>>([]);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<AgentRunFeedbackResponse | null>(null);
  const [myFeedback, setMyFeedback] = useState<AgentFeedbackStudioResponse | null>(null);
  const [feedbackDialog, setFeedbackDialog] = useState<"correction" | "handoff" | null>(null);
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);
  const lastAskedRole = useRef<string | null>(null);
  const runtimeSessionRef = useRef<string | null>(null);
  const chatThreadRef = useRef<HTMLDivElement | null>(null);
  const answerRequestSequence = useRef(0);
  const feedbackRequestSequence = useRef(0);
  const answer = conversation.at(-1)?.answer ?? null;

  const loadMyFeedback = useCallback(async () => {
    const requestSequence = ++feedbackRequestSequence.current;
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/agent-feedback/mine`, {
        cache: "no-store",
        headers: { "X-Zhixing-Demo-Actor": roleId }
      });
      if (feedbackRequestSequence.current !== requestSequence) return;
      if (!response.ok) {
        setMyFeedback(null);
        return;
      }
      setMyFeedback((await response.json()) as AgentFeedbackStudioResponse);
    } catch {
      if (feedbackRequestSequence.current === requestSequence) setMyFeedback(null);
    }
  }, [roleId]);

  useEffect(() => {
    void loadMyFeedback();
  }, [loadMyFeedback]);

  useEffect(() => {
    apiFetch(`${API_BASE_URL}/api/v1/twins/twin-ceo`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiErrorMessage(response, "分身配置接口不可用"));
        return response.json() as Promise<RoleTwinProfile>;
      })
      .then(setProfile)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取分身配置"));
  }, []);

  const ask = useCallback(async (nextQuestion: string) => {
    const trimmed = nextQuestion.trim();
    if (trimmed.length < 2) return;
    const requestSequence = ++answerRequestSequence.current;
    setPendingQuestion(trimmed);
    setLoading(true);
    setError(null);
    setFeedback(null);
    setFeedbackDialog(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/twins/twin-ceo/answers`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({
          question: trimmed,
          top_k: 6,
          workspace_key: workspaceKey ?? getActiveWorkspaceKey(),
          runtime_session_id: runtimeSessionRef.current
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "数字分身问答接口不可用"));
      const payload = (await response.json()) as TwinAnswerResponse;
      if (answerRequestSequence.current !== requestSequence) return;
      setConversation((current) => [...current, { question: trimmed, answer: payload }]);
      runtimeSessionRef.current = payload.runtime_session_id;
      setProfile(payload.twin);
    } catch (reason: unknown) {
      if (answerRequestSequence.current !== requestSequence) return;
      setError(reason instanceof Error ? reason.message : "数字分身回答失败");
    } finally {
      if (answerRequestSequence.current === requestSequence) {
        setLoading(false);
        setPendingQuestion(null);
      }
    }
  }, [roleId, workspaceKey]);

  useEffect(() => {
    if (lastAskedRole.current === roleId) return;
    lastAskedRole.current = roleId;
    runtimeSessionRef.current = null;
    setConversation([]);
    setPendingQuestion(null);
    setFeedback(null);
    void ask(DEFAULT_QUESTION);
  }, [ask, roleId]);

  useEffect(() => {
    const thread = chatThreadRef.current;
    if (thread) thread.scrollTo({ top: thread.scrollHeight, behavior: "smooth" });
  }, [conversation, error, loading]);

  const submitHelpful = async () => {
    if (!answer) return;
    setFeedbackSubmitting(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/agent-runs/${answer.run_id}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({
          kind: "helpful",
          message: "这次回答有帮助，证据和结论可以直接使用。",
          priority: "normal",
          client_request_key: `${answer.run_id}-helpful-${Date.now().toString(36)}`
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "回答反馈提交失败"));
      setFeedback((await response.json()) as AgentRunFeedbackResponse);
      void loadMyFeedback();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "回答反馈提交失败");
    } finally {
      setFeedbackSubmitting(false);
    }
  };

  return (
    <div className="twin-assistant-page">
      <PageHeader eyebrow="ROLE TWIN · EVIDENCE-GROUNDED" meta={`${currentRole.label} · ${currentRole.scope}`} title="企业数字分身助手" />
      <section className="twin-runtime-bar">
        <span><Bot size={17} /><strong>{profile?.display_name ?? "CEO 决策分身"}</strong>{profile?.role_title}</span>
        <span><ShieldCheck size={15} />上下文：正式资料 + 授权经营数据 + 已激活记忆</span>
        <span><Sparkles size={15} />{answer?.execution_mode === "model" ? `模型运行 · ${answer.model}` : "证据式降级运行"}</span>
        <span><Clock3 size={15} />历史运行 {profile?.run_count ?? 0} 次</span>
      </section>

      <div className="twin-assistant-layout">
        <Surface className="twin-chat-surface" meta={answer ? `${conversation.length} 轮 · ${answer.run_id.slice(-12)}` : "等待运行"} title={`与 ${profile?.display_name ?? "CEO 分身"} 对话`}>
          <div className="chat-thread twin-chat-thread" aria-live="polite" ref={chatThreadRef}>
            {conversation.map((turn, index) => (
              <div className="twin-conversation-turn" key={turn.answer.run_id}>
                <div className="message user-message"><span>你</span><p>{turn.question}</p></div>
                <ConversationAnswer
                  answer={turn.answer}
                  feedback={feedback}
                  feedbackSubmitting={feedbackSubmitting}
                  isLatest={index === conversation.length - 1}
                  onCorrection={() => setFeedbackDialog("correction")}
                  onHandoff={() => setFeedbackDialog("handoff")}
                  onHelpful={() => void submitHelpful()}
                  roleId={roleId}
                />
              </div>
            ))}
            {pendingQuestion ? <div className="message user-message"><span>你</span><p>{pendingQuestion}</p></div> : null}
            {loading ? <div className="twin-answer-loading"><LoaderCircle className="spinning" size={20} /><span>正在检索知识版本并生成有证据的回答</span></div> : null}
            {error ? <div className="twin-answer-error" role="alert"><CircleAlert size={18} /><span>{error}</span></div> : null}
          </div>
          <form className="composer twin-composer" onSubmit={(event) => { event.preventDefault(); void ask(question); }}>
            <textarea aria-label="输入企业问题" disabled={loading} onChange={(event) => setQuestion(event.target.value)} rows={3} value={question} />
            <div><span>{conversation.length ? `当前会话 ${conversation.length} 轮` : ""}</span><button className="button primary" disabled={loading || question.trim().length < 2} type="submit"><Send aria-hidden="true" size={16} />发送问题</button></div>
          </form>
        </Surface>

        <aside className="twin-assistant-side">
          <Surface meta={`${(answer?.evidence.length ?? 0) + (answer?.metric_context.length ?? 0) + (answer?.memory_context.length ?? 0)} 条实际上下文`} title="本次上下文快照">
            <div className="twin-evidence-list">
              {answer?.metric_context.map((item, index) => <article className="metric-context-item" key={`${item.key}-${item.scope_key}`}><span>D{index + 1}</span><div><strong>{item.label} · {formatMetricValue(item.latest_value, item.unit)}</strong><p>{item.period_change_rate === null ? "区间变化暂无" : `区间变化 ${(item.period_change_rate * 100).toFixed(2)}%`} · 最低 {formatMetricValue(item.minimum, item.unit)} · 最高 {formatMetricValue(item.maximum, item.unit)}</p><small>{item.scope_key} · {formatMetricRange(item.date_from, item.date_to)} · 口径 {item.definition_version} · {item.points.length} 个日点</small></div><TrendingUp size={15} /></article>)}
              {answer?.evidence.map((item, index) => <article key={item.chunk_id}><span>E{index + 1}</span><div><strong>{item.document_title} {item.version_label}</strong><p>{item.excerpt}</p><small>{item.locator} · 相关度 {Math.round(item.score * 100)}%</small></div><FileText size={15} /></article>)}
              {answer?.memory_context.map((item, index) => <article className="memory-context-item" key={item.id}><span>M{index + 1}</span><div><strong>长期记忆 v{item.version_number} · {item.category}</strong><p>{item.content}</p><small>{item.source_ref}</small></div><MemoryStick size={15} /></article>)}
              {!answer?.evidence.length && !answer?.metric_context.length && !answer?.memory_context.length ? <p className="twin-empty-evidence">暂无引用</p> : null}
            </div>
          </Surface>
          <Surface title="继续提问">
            <div className="suggestion-list">{SUGGESTIONS.map((item) => <button disabled={loading} key={item} onClick={() => { setQuestion(item); void ask(item); }} type="button"><MessageSquareText aria-hidden="true" size={15} />{item}</button>)}</div>
          </Surface>
          {myFeedback?.cases.length ? <Surface meta={`${myFeedback.stats.open_count + myFeedback.stats.in_review_count} 条处理中`} title="我的反馈"><div className="twin-my-feedback-list">{myFeedback.cases.slice(0, 4).map((item) => <article className={item.status} key={item.id}><div><strong>{item.question}</strong><span>{item.status === "open" ? "等待负责人认领" : item.status === "in_review" ? `${item.assigned_to_name ?? "负责人"} 正在处理` : "人工处理已完成"}</span></div><em>{item.status === "open" ? "待认领" : item.status === "in_review" ? "处理中" : "已解决"}</em>{item.resolution_summary ? <p>{item.resolution_summary}</p> : null}</article>)}</div></Surface> : null}
          <Surface meta="运行配置来自数据库" title="分身能力边界">
            <div className="twin-capability-list">{profile?.capabilities.map((item) => <span key={item}>{item}</span>)}</div>
            <p className="twin-profile-meta">最近运行：{formatTime(profile?.latest_run_at ?? null)}<br />供应商配置：{profile?.provider ?? "读取中"}</p>
          </Surface>
        </aside>
      </div>
      {answer && feedbackDialog ? <AgentFeedbackDialog mode={feedbackDialog} onClose={() => setFeedbackDialog(null)} onCompleted={(payload) => { setFeedback(payload); setFeedbackDialog(null); void loadMyFeedback(); }} roleId={roleId} runId={answer.run_id} /> : null}
    </div>
  );
}

function AnswerSection({ icon, label, items }: { icon: React.ReactNode; label: string; items: string[] }) {
  return <section className="twin-answer-section"><h3>{icon}{label}</h3><ul>{items.map((item, index) => <li key={`${label}-${index}`}>{item}</li>)}</ul></section>;
}

function ConversationAnswer({ answer, feedback, feedbackSubmitting, isLatest, onCorrection, onHandoff, onHelpful, roleId }: { answer: TwinAnswerResponse; feedback: AgentRunFeedbackResponse | null; feedbackSubmitting: boolean; isLatest: boolean; onCorrection: () => void; onHandoff: () => void; onHelpful: () => void; roleId: string }) {
  const confidenceLabel = answer.answer.confidence === "high" ? "高" : answer.answer.confidence === "medium" ? "中" : "低";
  return <div className="message assistant-message twin-answer-message">
    <span><Bot aria-hidden="true" size={15} />{answer.twin.display_name}</span>
    <p className="twin-answer-summary">{answer.answer.summary}</p>
    {answer.answer.facts.length ? <AnswerSection icon={<CheckCircle2 size={15} />} items={answer.answer.facts} label="可核验事实" /> : null}
    {answer.answer.actions.length ? <AnswerSection icon={<Sparkles size={15} />} items={answer.answer.actions} label="建议动作" /> : null}
    {answer.answer.caveats.length ? <AnswerSection icon={<CircleAlert size={15} />} items={answer.answer.caveats} label="限制与未知" /> : null}
    <div className="answer-tags"><StatusBadge value={{ label: answer.execution_mode === "model" ? "模型综合" : "证据降级", tone: answer.execution_mode === "model" ? "positive" : "warning" }} /><StatusBadge value={{ label: `置信度 ${confidenceLabel}`, tone: answer.answer.confidence === "high" ? "positive" : "info" }} /><span>{formatTime(answer.created_at)}</span></div>
    {isLatest ? <div className="twin-feedback-actions"><span>回答反馈</span><button disabled={feedbackSubmitting} onClick={onHelpful} type="button"><ThumbsUp size={14} />有帮助</button><button disabled={feedbackSubmitting} onClick={onCorrection} type="button"><MessageSquareWarning size={14} />需要纠正</button><button className="handoff" disabled={feedbackSubmitting} onClick={onHandoff} type="button"><ShieldAlert size={14} />转人工</button></div> : null}
    {isLatest && feedback && !feedback.handoff_case ? <div className="twin-feedback-receipt"><ClipboardCheck size={15} /><span>反馈已写入本次 AgentRun。</span></div> : null}
    {isLatest && feedback?.handoff_case ? <div className={`twin-handoff-status ${feedback.handoff_case.status}`}><div><ShieldAlert size={16} /><strong>{feedback.handoff_case.status === "open" ? "已进入人工接管队列" : feedback.handoff_case.status === "in_review" ? "负责人正在处理" : "人工处理已完成"}</strong></div><p>{feedback.handoff_case.resolution_summary ?? `优先级：${feedback.handoff_case.priority === "urgent" ? "紧急" : feedback.handoff_case.priority === "high" ? "高" : "普通"}`}</p>{["ceo", "manager", "admin", "service"].includes(roleId) ? <Link href="/console/twins/feedback">查看反馈工单</Link> : null}</div> : null}
  </div>;
}

function AgentFeedbackDialog({ mode, runId, roleId, onClose, onCompleted }: { mode: "correction" | "handoff"; runId: string; roleId: string; onClose: () => void; onCompleted: (payload: AgentRunFeedbackResponse) => void }) {
  const [kind, setKind] = useState<FeedbackKind>(mode === "handoff" ? "handoff" : "inaccurate");
  const [priority, setPriority] = useState<HandoffPriority>(mode === "handoff" ? "high" : "normal");
  const [message, setMessage] = useState(mode === "handoff" ? "这个问题需要业务负责人结合当前情况确认。" : "请说明回答中需要纠正的事实、边界或遗漏。");
  const [expectedAnswer, setExpectedAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/agent-runs/${runId}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({
          kind,
          message,
          expected_answer: expectedAnswer.trim() || null,
          priority,
          client_request_key: `${runId}-${kind}-${Date.now().toString(36)}`
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "反馈与人工接管请求提交失败"));
      onCompleted((await response.json()) as AgentRunFeedbackResponse);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "反馈与人工接管请求提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  return <Dialog busy={submitting} className="knowledge-dialog agent-feedback-dialog unified" eyebrow="ANSWER FEEDBACK · TRACEABLE HANDOFF" onClose={onClose} size="medium" title={mode === "handoff" ? "请求人工负责人接管" : "提交回答纠错"}><form onSubmit={(event) => void submit(event)}><div className="feedback-dialog-grid"><label><span>问题类型</span><select disabled={mode === "handoff"} onChange={(event) => setKind(event.target.value as FeedbackKind)} value={kind}>{mode === "handoff" ? <option value="handoff">请求人工</option> : <><option value="inaccurate">事实不准确</option><option value="incomplete">回答不完整</option><option value="scope_issue">权限或范围有问题</option><option value="unsafe">建议存在风险</option></>}</select></label><label><span>处理优先级</span><select onChange={(event) => setPriority(event.target.value as HandoffPriority)} value={priority}><option value="normal">普通</option><option value="high">高优先</option><option value="urgent">紧急</option></select></label></div><label><span>问题说明</span><textarea onChange={(event) => setMessage(event.target.value)} rows={5} value={message} /></label><label><span>期望回答（可选）</span><textarea onChange={(event) => setExpectedAnswer(event.target.value)} placeholder="可写出正确口径、应补充的事实或期望负责人确认的内容。" rows={5} value={expectedAnswer} /></label><div className="feedback-dialog-boundary"><ShieldCheck size={17} /><span>提交后只创建内部反馈与接管工单，不会自动修改制度、记忆、Prompt 或对外发送消息。</span></div>{error ? <InlineCallout description={error} title="反馈提交失败" tone="critical" /> : null}<footer><button className="button secondary" onClick={onClose} type="button">取消</button><button className="button primary" disabled={submitting || message.trim().length < 2} type="submit">{submitting ? <LoaderCircle className="spinning" size={15} /> : mode === "handoff" ? <ShieldAlert size={15} /> : <MessageSquareWarning size={15} />}{submitting ? "正在写入" : mode === "handoff" ? "创建接管工单" : "提交纠错"}</button></footer></form></Dialog>;
}
