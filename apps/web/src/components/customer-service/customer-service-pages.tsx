"use client";

import {
  AlertTriangle,
  Bot,
  Box,
  ChevronRight,
  CircleDot,
  Clock3,
  Database,
  FileCheck2,
  Headphones,
  History,
  LoaderCircle,
  MessageSquareText,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserRoundCheck
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch, newTraceId } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type {
  CustomerServiceConversation,
  CustomerServiceEvidence,
  CustomerServiceMutationResponse,
  CustomerServiceReplyDraft,
  CustomerServiceRisk,
  CustomerServiceStatus,
  CustomerServiceStudio
} from "@/lib/customer-service-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const STATUS_LABELS: Record<CustomerServiceStatus, string> = {
  waiting: "等待处理",
  draft_ready: "草稿待确认",
  review_required: "风险复核",
  handed_off: "已转人工",
  resolved: "已结束"
};

const RISK_LABELS: Record<CustomerServiceRisk, string> = {
  low: "低风险",
  medium: "需核验",
  high: "高风险",
  critical: "严重风险"
};

const FLAG_LABELS: Record<string, string> = {
  compensation_commitment: "补偿承诺",
  refund_timeline: "退款时点",
  unverified_logistics: "物流未核验",
  safety_or_complaint: "安全/质量",
  legal_or_media: "法务/媒体",
  personal_data: "个人信息",
  manual_request: "要求人工",
  data_conflict: "跨源数据冲突",
  other: "业务复核"
};

const FACT_STATUS_LABELS = {
  matched: "已关联",
  not_applicable: "无需对账",
  missing: "等待同步",
  scope_mismatch: "范围不符"
} as const;

const CONSISTENCY_STATUS_LABELS = {
  consistent: "对账一致",
  conflict: "对账冲突",
  not_checked: "未执行对账"
} as const;

const DIFFERENCE_FIELD_LABELS = {
  order_status: "订单状态",
  paid_amount: "实付金额",
  item_count: "商品件数",
  refund_state: "退款状态"
} as const;

function formatTime(value: string | null): string {
  if (!value) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function money(value: number | null, currency: string): string {
  if (value === null) return "未产生订单";
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2
  }).format(value);
}

function statusClass(status: CustomerServiceStatus): string {
  if (status === "resolved") return "positive";
  if (status === "review_required" || status === "handed_off") return "critical";
  if (status === "draft_ready") return "info";
  return "warning";
}

function riskClass(risk: CustomerServiceRisk): string {
  if (risk === "low") return "positive";
  if (risk === "medium") return "warning";
  return "critical";
}

export function CustomerServicePage({
  view,
  conversationKey
}: {
  view: "conversations" | "drafts";
  conversationKey?: string;
}) {
  const { roleId } = useExperience();
  const [studio, setStudio] = useState<CustomerServiceStudio | null>(null);
  const [loading, setLoading] = useState(true);
  const [mutating, setMutating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [draftBody, setDraftBody] = useState("");

  const acceptStudio = useCallback((next: CustomerServiceStudio) => {
    setStudio(next);
    const latestDraft = next.selected.drafts.find((item) => item.status === "generated")
      ?? next.selected.drafts[0];
    setDraftBody(latestDraft?.body ?? "");
  }, []);

  const loadStudio = useCallback(async () => {
    setError(null);
    const suffix = conversationKey
      ? `?conversation_key=${encodeURIComponent(conversationKey)}`
      : "";
    const response = await apiFetch(`${API_BASE_URL}/api/v1/customer-service/studio${suffix}`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) {
      throw new Error(await apiErrorMessage(response, "无法读取客服数据库工作台"));
    }
    acceptStudio((await response.json()) as CustomerServiceStudio);
  }, [acceptStudio, conversationKey, roleId]);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      try {
        await loadStudio();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "客服工作台加载失败");
      } finally {
        setLoading(false);
      }
    };
    void run();
  }, [loadStudio]);

  async function mutate(
    action: string,
    url: string,
    payload: Record<string, unknown>
  ) {
    setMutating(action);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}${url}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Zhixing-Demo-Actor": roleId
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        throw new Error(await apiErrorMessage(response, "客服动作执行失败"));
      }
      const result = (await response.json()) as CustomerServiceMutationResponse;
      acceptStudio(result.studio);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "客服动作执行失败");
    } finally {
      setMutating(null);
    }
  }

  if (loading) return <CustomerServiceState mode="loading" />;
  if (!studio) {
    return <CustomerServiceState mode="failed" message={error ?? "客服数据库暂无可用数据"} />;
  }

  const selected = studio.selected;
  const generatedDraft = selected.drafts.find((item) => item.status === "generated");
  const filteredConversations = studio.conversations.filter((item) => {
    const term = query.trim().toLocaleLowerCase("zh-CN");
    if (!term) return true;
    return [item.customer_name, item.topic, item.order_key, item.conversation_key]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase("zh-CN").includes(term));
  });

  const generateDraft = () => mutate(
    "draft",
    `/api/v1/customer-service/conversations/${selected.conversation.conversation_key}/drafts`,
    { client_request_key: `web-cs-draft-${newTraceId("req")}` }
  );
  const handoff = () => mutate(
    "handoff",
    `/api/v1/customer-service/conversations/${selected.conversation.conversation_key}/handoffs`,
    {
      reason: selected.conversation.risk_reason || "客服人工确认转交风险队列",
      client_request_key: `web-cs-handoff-${newTraceId("req")}`
    }
  );
  const sandboxSend = () => {
    if (!generatedDraft) return;
    void mutate(
      "send",
      `/api/v1/customer-service/drafts/${generatedDraft.id}/sandbox-send`,
      {
        final_body: draftBody,
        note: "客服工作台人工复核并确认写入沙箱通道",
        client_request_key: `web-cs-send-${newTraceId("req")}`
      }
    );
  };

  return (
    <div className="customer-service-page">
      <PageHeader
        actions={
          <button className="button secondary" onClick={() => void loadStudio()} type="button">
            <RefreshCw aria-hidden="true" size={16} />
            刷新队列
          </button>
        }
        description="数据库会话、订单履约、现行制度和客服分身共同生成可追溯草稿；高风险由确定性规则强制转人工。"
        eyebrow="AI CUSTOMER OPERATIONS · DATABASE WORKBENCH"
        meta="commerce-sandbox"
        title={view === "drafts" ? "回复草稿台账" : "智能客服工作台"}
      />

      <CustomerServiceStats studio={studio} />
      {error ? (
        <div className="customer-service-error" role="alert">
          <AlertTriangle aria-hidden="true" size={18} />
          <span>{error}</span>
        </div>
      ) : null}

      {view === "drafts" ? (
        <DraftLedger studio={studio} />
      ) : (
        <div className="customer-service-workbench">
          <ConversationQueue
            activeKey={selected.conversation.conversation_key}
            conversations={filteredConversations}
            onQuery={setQuery}
            query={query}
          />
          <ConversationThread
            onGenerate={generateDraft}
            onHandoff={handoff}
            mutating={mutating}
            studio={studio}
          />
          <CustomerContextPanel
            draftBody={draftBody}
            mutating={mutating}
            onDraftBody={setDraftBody}
            onGenerate={generateDraft}
            onHandoff={handoff}
            onSend={sandboxSend}
            studio={studio}
          />
        </div>
      )}
    </div>
  );
}

function CustomerServiceStats({ studio }: { studio: CustomerServiceStudio }) {
  const stats = [
    { label: "会话总量", value: studio.stats.total_count, detail: "数据库分配队列", icon: Database },
    { label: "等待处理", value: studio.stats.waiting_count, detail: "尚未生成草稿", icon: MessageSquareText },
    { label: "风险复核", value: studio.stats.review_required_count, detail: "规则强制拦截", icon: ShieldAlert },
    { label: "SLA 超时", value: studio.stats.overdue_count, detail: "首响时限已过", icon: Clock3 },
    { label: "可确认草稿", value: studio.stats.safe_draft_count, detail: "仍需人工发送", icon: ShieldCheck },
    { label: "已转人工", value: studio.stats.handoff_count, detail: "进入风险队列", icon: UserRoundCheck }
  ];
  return (
    <section className="customer-service-stat-band" aria-label="客服队列统计">
      {stats.map(({ label, value, detail, icon: Icon }) => (
        <article key={label}>
          <Icon aria-hidden="true" size={19} />
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{detail}</small>
        </article>
      ))}
    </section>
  );
}

function ConversationQueue({
  conversations,
  activeKey,
  query,
  onQuery
}: {
  conversations: CustomerServiceConversation[];
  activeKey: string;
  query: string;
  onQuery: (value: string) => void;
}) {
  return (
    <aside className="customer-conversation-rail">
      <header>
        <div>
          <span>ASSIGNED QUEUE</span>
          <strong>我的会话</strong>
        </div>
        <b>{conversations.length}</b>
      </header>
      <label className="customer-conversation-search">
        <Search aria-hidden="true" size={16} />
        <input
          aria-label="搜索客户、订单或会话"
          onChange={(event) => onQuery(event.target.value)}
          placeholder="客户 / 订单 / 主题"
          value={query}
        />
      </label>
      <div className="customer-conversation-list">
        {conversations.map((item) => (
          <Link
            className={item.conversation_key === activeKey ? "active" : ""}
            href={`/console/customer-service/conversations/${item.conversation_key}`}
            key={item.id}
          >
            <div className="customer-conversation-heading">
              <strong>{item.customer_name}</strong>
              <time>{formatTime(item.last_message_at).split(" ").at(-1)}</time>
            </div>
            <b>{item.topic}</b>
            <p>{item.last_message_preview}</p>
            <footer>
              <span className={`customer-status-pill ${statusClass(item.status)}`}>
                {STATUS_LABELS[item.status]}
              </span>
              {item.sla_overdue ? <em>超时</em> : null}
              <small>{item.order_key ?? "售前咨询"}</small>
            </footer>
          </Link>
        ))}
        {conversations.length === 0 ? <p className="customer-empty-rail">没有匹配会话</p> : null}
      </div>
    </aside>
  );
}

function ConversationThread({
  studio,
  mutating,
  onGenerate,
  onHandoff
}: {
  studio: CustomerServiceStudio;
  mutating: string | null;
  onGenerate: () => void;
  onHandoff: () => void;
}) {
  const { conversation, messages } = studio.selected;
  const closed = conversation.status === "resolved" || conversation.status === "handed_off";
  return (
    <section className="customer-thread-panel">
      <header>
        <div className="customer-thread-identity">
          <span>{conversation.customer_name.slice(0, 1)}</span>
          <div>
            <strong>{conversation.customer_name}</strong>
            <small>{conversation.customer_key} · {conversation.store_scope_key}</small>
          </div>
        </div>
        <div className="customer-thread-badges">
          <span className={`customer-status-pill ${riskClass(conversation.risk_level)}`}>
            {RISK_LABELS[conversation.risk_level]}
          </span>
          <span className={`customer-status-pill ${statusClass(conversation.status)}`}>
            {STATUS_LABELS[conversation.status]}
          </span>
        </div>
      </header>
      <div className={`customer-risk-strip ${riskClass(conversation.risk_level)}`}>
        {conversation.risk_level === "low" ? (
          <ShieldCheck aria-hidden="true" size={17} />
        ) : (
          <ShieldAlert aria-hidden="true" size={17} />
        )}
        <div>
          <strong>{conversation.topic}</strong>
          <span>{conversation.risk_reason}</span>
        </div>
      </div>
      <div className="customer-message-thread">
        {messages.map((message) => (
          <article className={message.direction} key={message.id}>
            <header>
              <strong>{message.sender_name}</strong>
              <time>{formatTime(message.occurred_at)}</time>
            </header>
            <p>{message.content}</p>
            <small>{message.direction === "outbound" ? "沙箱通道 · 已写入" : "客户消息 · 已接收"}</small>
          </article>
        ))}
      </div>
      <footer className="customer-thread-actions">
        <div>
          <CircleDot aria-hidden="true" size={15} />
          <span>{closed ? "当前会话已进入终态" : "AI 只生成草稿，发送必须由客服确认"}</span>
        </div>
        <button
          className="button secondary danger"
          disabled={closed || !studio.can_handoff || mutating !== null}
          onClick={onHandoff}
          type="button"
        >
          {mutating === "handoff" ? <LoaderCircle className="spinning" size={16} /> : <Headphones size={16} />}
          转人工
        </button>
        <button
          className="button primary"
          disabled={closed || !studio.can_generate || mutating !== null}
          onClick={onGenerate}
          type="button"
        >
          {mutating === "draft" ? <LoaderCircle className="spinning" size={16} /> : <Sparkles size={16} />}
          {studio.selected.drafts.length > 0 ? "重新生成" : "生成草稿"}
        </button>
      </footer>
    </section>
  );
}

function CustomerContextPanel({
  studio,
  draftBody,
  mutating,
  onDraftBody,
  onGenerate,
  onHandoff,
  onSend
}: {
  studio: CustomerServiceStudio;
  draftBody: string;
  mutating: string | null;
  onDraftBody: (value: string) => void;
  onGenerate: () => void;
  onHandoff: () => void;
  onSend: () => void;
}) {
  const { order_context: context, canonical_order_fact: canonical, drafts } = studio.selected;
  const latest = drafts[0];
  const generated = drafts.find((item) => item.status === "generated");
  return (
    <aside className="customer-context-panel">
      <section className="customer-context-block">
        <header>
          <Box aria-hidden="true" size={17} />
          <div><span>ORDER CONTEXT</span><strong>订单与履约</strong></div>
          <small>{formatTime(context.synced_at)} 同步</small>
        </header>
        <dl className="customer-order-grid">
          <div><dt>订单</dt><dd>{context.order_key ?? "售前咨询"}</dd></div>
          <div><dt>实付</dt><dd>{money(context.paid_amount, context.currency)}</dd></div>
          <div><dt>订单状态</dt><dd>{context.order_status ?? "无"}</dd></div>
          <div><dt>售后状态</dt><dd>{context.aftersale_status ?? "无"}</dd></div>
        </dl>
        <div className={`customer-canonical-fact ${canonical.match_status} ${canonical.consistency_status}`}>
          <header>
            <div><Database aria-hidden="true" size={15} /><strong>数据中心交易事实</strong></div>
            <div className="customer-fact-badges">
              <span>{FACT_STATUS_LABELS[canonical.match_status]}</span>
              <span>{CONSISTENCY_STATUS_LABELS[canonical.consistency_status]}</span>
            </div>
          </header>
          <p>{canonical.match_reason}</p>
          {canonical.match_status === "matched" ? (
            <>
              <div className={`customer-reconciliation-summary ${canonical.consistency_status}`}>
                {canonical.material_conflict ? <AlertTriangle aria-hidden="true" size={15} /> : <ShieldCheck aria-hidden="true" size={15} />}
                <div>
                  <strong>{canonical.material_conflict ? "重大差异已触发 AI 门禁" : "业务上下文与规范事实一致"}</strong>
                  <span>{canonical.consistency_reason}</span>
                </div>
              </div>
              {canonical.differences.length > 0 ? (
                <div className="customer-reconciliation-differences">
                  {canonical.differences.map((difference) => (
                    <article key={difference.field}>
                      <header>
                        <strong>{DIFFERENCE_FIELD_LABELS[difference.field]}</strong>
                        <span>{difference.severity === "critical" ? "重大" : difference.severity === "warning" ? "警告" : "提示"}</span>
                      </header>
                      <dl>
                        <div><dt>客服上下文</dt><dd>{difference.context_value ?? "未记录"}</dd></div>
                        <div><dt>数据中心</dt><dd>{difference.canonical_value ?? "未记录"}</dd></div>
                      </dl>
                    </article>
                  ))}
                </div>
              ) : null}
              <dl>
                <div><dt>规范实付</dt><dd>{money(canonical.paid_amount, canonical.currency)}</dd></div>
                <div><dt>规范状态</dt><dd>{canonical.order_status ?? "未记录"}</dd></div>
                <div><dt>毛利率</dt><dd>{canonical.gross_margin_rate === null ? "未核算" : `${(canonical.gross_margin_rate * 100).toFixed(1)}%`}</dd></div>
                <div><dt>退款</dt><dd>{canonical.refund_count > 0 ? `${canonical.refund_count} 笔 / ${money(canonical.refund_amount, canonical.currency)}` : "无退款事实"}</dd></div>
              </dl>
              <footer>
                <span>{canonical.source_system_key} · {canonical.external_store_key}</span>
                <code>{canonical.sync_run_ids.join(" · ")}</code>
                <small>{canonical.business_date} 经营日 · 映射 {canonical.mapping_version}</small>
              </footer>
            </>
          ) : null}
        </div>
        <p className="customer-product-summary">{context.product_summary}</p>
        <div className="customer-logistics-line">
          <span>{context.carrier ?? "暂无承运商"}</span>
          <strong>{context.logistics_status ?? "无物流"}</strong>
          <small>{context.latest_logistics_event ?? "暂无可验证轨迹"}</small>
        </div>
      </section>

      <section className="customer-context-block customer-draft-block">
        <header>
          <Bot aria-hidden="true" size={17} />
          <div><span>ROLE TWIN DRAFT</span><strong>{studio.twin.display_name}</strong></div>
          <small>v{studio.twin.version_number}</small>
        </header>
        {!latest ? (
          <div className="customer-draft-empty">
            <Sparkles aria-hidden="true" size={26} />
            <strong>尚未生成回复草稿</strong>
            <span>将冻结履约上下文、数据中心规范事实和现行制度后调用客服分身。</span>
            <button className="button primary" disabled={mutating !== null} onClick={onGenerate} type="button">
              生成首版草稿
            </button>
          </div>
        ) : (
          <>
            <div className="customer-draft-runtime">
              <span className={`customer-status-pill ${latest.safe_to_send ? "positive" : "critical"}`}>
                {latest.safe_to_send ? "规则放行" : "禁止发送"}
              </span>
              <span>{latest.execution_mode === "model" ? "AI 模型" : "证据降级"}</span>
              <code>v{latest.version_number}</code>
            </div>
            {latest.risk_flags.length > 0 ? (
              <div className="customer-risk-flags">
                {latest.risk_flags.map((flag) => <span key={flag}>{FLAG_LABELS[flag] ?? flag}</span>)}
              </div>
            ) : null}
            <textarea
              aria-label="客服回复草稿"
              disabled={!generated || !generated.safe_to_send}
              onChange={(event) => onDraftBody(event.target.value)}
              rows={7}
              value={draftBody || latest.body}
            />
            <EvidenceStack evidence={latest.evidence} />
            <div className="customer-draft-actions">
              {!latest.safe_to_send ? (
                <button
                  className="button secondary danger"
                  disabled={!studio.can_handoff || mutating !== null}
                  onClick={onHandoff}
                  type="button"
                >
                  <ShieldAlert size={16} />按规则转人工
                </button>
              ) : (
                <button
                  className="button primary"
                  disabled={!generated || !studio.can_send || mutating !== null || draftBody.trim().length < 2}
                  onClick={onSend}
                  type="button"
                >
                  {mutating === "send" ? <LoaderCircle className="spinning" size={16} /> : <Send size={16} />}
                  人工确认并写入沙箱
                </button>
              )}
            </div>
          </>
        )}
      </section>

      <section className="customer-context-block customer-policy-block">
        <header>
          <FileCheck2 aria-hidden="true" size={17} />
          <div><span>EFFECTIVE POLICY</span><strong>{studio.active_policy.title}</strong></div>
        </header>
        <div>
          <span>{studio.active_policy.version_label}</span>
          <strong>{studio.active_policy.status}</strong>
          <small>{formatTime(studio.active_policy.effective_from)} 生效</small>
        </div>
      </section>
    </aside>
  );
}

function EvidenceStack({ evidence }: { evidence: CustomerServiceEvidence[] }) {
  return (
    <div className="customer-evidence-stack">
      <header><ShieldCheck size={15} /><strong>本次冻结证据</strong><span>{evidence.length} 项</span></header>
      {evidence.slice(0, 5).map((item) => (
        <article key={item.ref}>
          <code>{item.ref}</code>
          <div><strong>{item.label}</strong><p>{item.excerpt}</p></div>
        </article>
      ))}
    </div>
  );
}

function DraftLedger({ studio }: { studio: CustomerServiceStudio }) {
  const conversations = useMemo(
    () => new Map(studio.conversations.map((item) => [item.id, item])),
    [studio.conversations]
  );
  return (
    <section className="customer-draft-ledger">
      <header>
        <div><span>DRAFT AUDIT LEDGER</span><h2>全部回复草稿</h2></div>
        <p>草稿版本不可覆盖；模型、证据快照、人工确认和沙箱写入状态均可追溯。</p>
      </header>
      {studio.drafts.length === 0 ? (
        <div className="customer-ledger-empty">
          <History size={28} />
          <strong>尚无持久化草稿</strong>
          <span>从客户会话生成第一条回复草稿后，将在这里形成审计台账。</span>
          <Link className="button primary" href="/console/customer-service/conversations">进入会话队列</Link>
        </div>
      ) : (
        <div className="customer-draft-table-wrap">
          <table className="customer-draft-table">
            <thead><tr><th>客户 / 会话</th><th>草稿摘要</th><th>风险与动作</th><th>运行方式</th><th>状态</th><th>生成时间</th><th aria-label="打开" /></tr></thead>
            <tbody>
              {studio.drafts.map((draft) => {
                const conversation = conversations.get(draft.conversation_id);
                return (
                  <tr key={draft.id}>
                    <td><strong>{conversation?.customer_name ?? draft.conversation_id}</strong><small>{conversation?.topic ?? "会话已归档"}</small></td>
                    <td><p>{draft.body}</p><code>{draft.evidence_snapshot_id}</code></td>
                    <td><span className={`customer-status-pill ${riskClass(draft.risk_level)}`}>{RISK_LABELS[draft.risk_level]}</span><small>{draft.suggested_action === "handoff" ? "转人工" : draft.suggested_action === "investigate" ? "继续核验" : "回复客户"}</small></td>
                    <td><strong>{draft.execution_mode === "model" ? "AI 模型" : "证据降级"}</strong><small>{draft.model}</small></td>
                    <td><span className={`customer-status-pill ${draft.status === "sandbox_sent" ? "positive" : draft.safe_to_send ? "info" : "critical"}`}>{draft.status === "sandbox_sent" ? "沙箱已写入" : !draft.safe_to_send ? "禁止发送" : draft.status === "generated" ? "待确认" : draft.status}</span></td>
                    <td>{formatTime(draft.created_at)}</td>
                    <td>{conversation ? <Link aria-label={`打开 ${conversation.customer_name} 会话`} href={`/console/customer-service/conversations/${conversation.conversation_key}`}><ChevronRight size={18} /></Link> : null}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CustomerServiceState({
  mode,
  message
}: {
  mode: "loading" | "failed";
  message?: string;
}) {
  return (
    <div className={`customer-service-state ${mode}`}>
      {mode === "loading" ? <LoaderCircle className="spinning" size={28} /> : <AlertTriangle size={28} />}
      <strong>{mode === "loading" ? "正在读取客服数据库队列" : "客服工作台暂不可用"}</strong>
      <span>{message ?? "正在组合会话、履约上下文、规范经营事实、现行制度与角色分身版本。"}</span>
    </div>
  );
}
