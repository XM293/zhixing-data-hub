"use client";

import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  Bot,
  CheckCircle2,
  Clock3,
  CircleDollarSign,
  Database,
  FileKey2,
  ListPlus,
  LoaderCircle,
  MousePointerClick,
  PackageCheck,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
  Target,
  UserRound
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { useNotifications } from "@/components/console/interaction";
import { PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type {
  CustomerOperationActionProposalResponse
} from "@/lib/action-types";
import type {
  CustomerOperationRun,
  CustomerOperationRunResponse,
  CustomerOperationStudioResponse
} from "@/lib/customer-operation-types";
import type {
  Customer360Touchpoint,
  CustomerDetailRecommendation,
  CustomerDetailResponse,
  CustomerDetailTimelineEvent
} from "@/lib/data-center-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const LIFECYCLE_LABELS: Record<string, string> = {
  new: "新客培育",
  growing: "成长客户",
  mature: "成熟客户",
  sleeping: "沉睡唤醒",
  at_risk: "流失预警"
};

const MEMBER_LABELS: Record<string, string> = {
  regular: "普通会员",
  standard: "普通会员",
  silver: "银卡会员",
  gold: "金卡会员",
  platinum: "铂金会员",
  black_gold: "黑金会员"
};

const TOUCHPOINT_LABELS: Record<string, string> = {
  visit: "访问店铺",
  product_view: "浏览商品",
  add_to_cart: "加入购物车",
  campaign_click: "点击活动",
  coupon_claim: "领取优惠券",
  service: "咨询客服"
};

const PRIORITY_LABELS = {
  critical: "强制边界",
  high: "高优先",
  medium: "中优先",
  low: "低优先"
} as const;

const EVENT_LABELS = {
  profile: "客户主档",
  order: "订单事实",
  refund: "退款事实",
  touchpoint: "行为触点"
} as const;

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2
  }).format(value);
}

function formatPercent(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "percent",
    maximumFractionDigits: 1
  }).format(value);
}

function formatDateTime(value: string | null): string {
  if (!value) return "暂无";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function formatDuration(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(1)} 秒` : `${value} 毫秒`;
}

function scopeLabel(scopeKey: string): string {
  if (scopeKey === "enterprise") return "全企业";
  if (scopeKey === "store-flagship") return "旗舰店";
  if (scopeKey === "store-outlet") return "奥莱店";
  return `门店 · ${scopeKey}`;
}

function riskStatus(level: "low" | "medium" | "high") {
  if (level === "high") return { label: "高风险", tone: "critical" as const };
  if (level === "medium") return { label: "需关注", tone: "warning" as const };
  return { label: "风险稳定", tone: "positive" as const };
}

function priorityTone(priority: CustomerDetailRecommendation["priority"]) {
  if (priority === "critical") return "critical" as const;
  if (priority === "high") return "warning" as const;
  if (priority === "medium") return "info" as const;
  return "neutral" as const;
}

function eventIcon(eventType: CustomerDetailTimelineEvent["event_type"]) {
  if (eventType === "order") return <ShoppingBag aria-hidden="true" size={15} />;
  if (eventType === "refund") return <ReceiptText aria-hidden="true" size={15} />;
  if (eventType === "touchpoint") return <MousePointerClick aria-hidden="true" size={15} />;
  return <UserRound aria-hidden="true" size={15} />;
}

export function Customer360DetailPage({
  scopeKey,
  customerKey
}: {
  scopeKey: string;
  customerKey: string;
}) {
  const { identity, identityLoading, can } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<CustomerDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [operationStudio, setOperationStudio] = useState<CustomerOperationStudioResponse | null>(null);
  const [operationLoading, setOperationLoading] = useState(true);
  const [operationRunning, setOperationRunning] = useState(false);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const [proposalRunning, setProposalRunning] = useState(false);
  const [selectedOperationSteps, setSelectedOperationSteps] = useState<number[]>([]);
  const [proposalDueHint, setProposalDueHint] = useState("未来 7 天内完成");
  const [objective, setObjective] = useState("提升未来三十天复购质量并降低流失风险，先核验体验与触达边界");
  const operationRequestKey = useRef("");
  const proposalRequestKey = useRef("");
  const [reloadToken, setReloadToken] = useState(0);
  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    if (identityLoading) return;
    if (!identity || !can("customer.profile.read")) {
      setLoading(false);
      setData(null);
      return;
    }
    const controller = new AbortController();
    const params = new URLSearchParams({ scope_key: scopeKey, limit: "100" });
    setLoading(true);
    setError(null);
    apiFetch(
      `${API_BASE_URL}/api/v1/data-center/customer-360/${encodeURIComponent(customerKey)}?${params}`,
      {
        cache: "no-store",
        signal: controller.signal
      }
    )
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiErrorMessage(response, "客户详情暂不可用"));
        return response.json() as Promise<CustomerDetailResponse>;
      })
      .then(setData)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setData(null);
        setError(reason instanceof Error ? reason.message : "无法读取客户详情");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [can, customerKey, identity, identityLoading, reloadToken, scopeKey]);

  useEffect(() => {
    if (identityLoading || !identity || !can("customer.profile.read")) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ scope_key: scopeKey, customer_key: customerKey });
    setOperationLoading(true);
    setOperationError(null);
    apiFetch(`${API_BASE_URL}/api/v1/customer-operations/studio?${params}`, {
      cache: "no-store",
      signal: controller.signal
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiErrorMessage(response, "客户运营方案台暂不可用"));
        return response.json() as Promise<CustomerOperationStudioResponse>;
      })
      .then(setOperationStudio)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setOperationError(reason instanceof Error ? reason.message : "无法读取客户运营方案");
      })
      .finally(() => {
        if (!controller.signal.aborted) setOperationLoading(false);
      });
    return () => controller.abort();
  }, [can, customerKey, identity, identityLoading, reloadToken, scopeKey]);

  async function runOperationPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (operationRunning || !operationStudio?.can_run || objective.trim().length < 8) return;
    if (!operationRequestKey.current) operationRequestKey.current = `customer-operation-${crypto.randomUUID()}`;
    setOperationRunning(true);
    setOperationError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/customer-operations/plans`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scope_key: scopeKey,
          customer_key: customerKey,
          objective: objective.trim(),
          client_request_key: operationRequestKey.current
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "客户运营方案生成失败"));
      const result = (await response.json()) as CustomerOperationRunResponse;
      setOperationStudio(result.studio);
      operationRequestKey.current = "";
      proposalRequestKey.current = "";
      setSelectedOperationSteps([]);
    } catch (reason: unknown) {
      setOperationError(reason instanceof Error ? reason.message : "客户运营方案生成失败");
    } finally {
      setOperationRunning(false);
    }
  }

  function toggleOperationStep(index: number) {
    setSelectedOperationSteps((current) => (
      current.includes(index)
        ? current.filter((item) => item !== index)
        : [...current, index].sort((left, right) => left - right)
    ));
  }

  async function proposeOperationActions() {
    const latest = operationStudio?.runs[0];
    if (!latest || proposalRunning || !operationStudio?.can_propose || !selectedOperationSteps.length) return;
    if (!proposalRequestKey.current) proposalRequestKey.current = `customer-action-${crypto.randomUUID()}`;
    setProposalRunning(true);
    setProposalError(null);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/customer-operations/plans/${encodeURIComponent(latest.id)}/action-proposals`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            step_indexes: selectedOperationSteps,
            due_hint: proposalDueHint.trim(),
            idempotency_key: proposalRequestKey.current
          })
        }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "行动提案创建失败"));
      const result = (await response.json()) as CustomerOperationActionProposalResponse;
      notify({
        title: result.created_count ? "行动提案已创建" : "行动提案已存在",
        description: result.created_count ? `${result.created_count} 个步骤已进入审批队列` : "本次未重复创建",
        tone: "success"
      });
      setSelectedOperationSteps([]);
      proposalRequestKey.current = "";
      reload();
    } catch (reason: unknown) {
      setProposalError(reason instanceof Error ? reason.message : "行动提案创建失败");
    } finally {
      setProposalRunning(false);
    }
  }

  if (identityLoading || loading) {
    return <CustomerDetailState message="正在合并主档、交易、退款与行为时间线" />;
  }

  if (!identity || !can("customer.profile.read")) {
    return (
      <CustomerDetailState
        failed
        message="当前账号没有客户画像读取权限"
        note="数据范围和权限由服务端统一判断，页面不会扩大当前账号的可见范围。"
      />
    );
  }

  if (!data) {
    return (
      <CustomerDetailState
        failed
        message="无法打开这位客户"
        note={error ?? "客户不存在，或不在当前账号的数据范围内。"}
        onRetry={reload}
      />
    );
  }

  const { profile, summary } = data;
  const initials = profile.display_name.slice(0, 1);
  const stats = [
    {
      icon: ShoppingBag,
      label: "累计订单",
      value: `${formatNumber(summary.lifetime_order_count)} 单`,
      note: summary.days_since_last_order === null
        ? "暂无可信订单事实"
        : `距最近下单 ${summary.days_since_last_order} 天`
    },
    {
      icon: CircleDollarSign,
      label: "累计成交",
      value: formatMoney(summary.paid_gmv_yuan),
      note: `客单价 ${formatMoney(summary.average_order_value_yuan)}`
    },
    {
      icon: ReceiptText,
      label: "累计退款",
      value: formatMoney(summary.refund_amount_yuan),
      note: `${summary.refund_count} 笔 · 退款率 ${formatPercent(summary.refund_rate)}`,
      tone: summary.refund_rate >= 0.2 ? "critical" : ""
    },
    {
      icon: Activity,
      label: "行为触点",
      value: `${formatNumber(summary.touchpoint_count)} 次`,
      note: `距最近活跃 ${summary.days_since_last_active} 天`
    },
    {
      icon: BadgeCheck,
      label: "会员积分",
      value: formatNumber(profile.member_points),
      note: `成长值 ${formatNumber(profile.growth_value)}`
    },
    {
      icon: ShieldCheck,
      label: "触达资格",
      value: summary.engagement_eligible ? "可进入审核" : "禁止自动触达",
      note: summary.engagement_eligible ? "仅允许形成待审核方案" : "同意状态或主档状态不满足",
      tone: summary.engagement_eligible ? "positive" : "critical"
    }
  ];

  return (
    <div className="customer-detail-page">
      <PageHeader
        actions={
          <div className="customer-detail-actions">
            <Link className="button secondary" href="/console/data/products/customers">
              <ArrowLeft aria-hidden="true" size={16} />返回客户队列
            </Link>
            <button aria-label="刷新客户详情" className="icon-button" onClick={reload} title="刷新客户详情" type="button">
              <RefreshCw aria-hidden="true" size={16} />
            </button>
          </div>
        }
        description="以 CRM 主档为锚点读取 ERP 交易真值和客户触点，所有建议均保留证据与操作边界。"
        eyebrow="CUSTOMER 360 · GOVERNED PROFILE"
        meta={`${scopeLabel(data.scope_key)} · ${profile.source_key}`}
        title={profile.display_name}
      />

      <section className="customer-detail-stat-band" aria-label="客户关键指标">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <article className={stat.tone ?? ""} key={stat.label}>
              <span><Icon aria-hidden="true" size={17} />{stat.label}</span>
              <strong>{stat.value}</strong>
              <p>{stat.note}</p>
            </article>
          );
        })}
      </section>

      <div className="customer-detail-primary-grid">
        <section className="customer-detail-panel customer-profile-panel">
          <DetailPanelHeader eyebrow="IDENTITY" meta={profile.customer_key} title="客户身份与归属" />
          <div className="customer-profile-identity">
            <span className="customer-profile-avatar" aria-hidden="true">{initials}</span>
            <div>
              <strong>{profile.display_name}</strong>
              <p>{MEMBER_LABELS[profile.member_level] ?? profile.member_level} · {LIFECYCLE_LABELS[profile.lifecycle_stage] ?? profile.lifecycle_stage}</p>
            </div>
            <StatusBadge value={riskStatus(summary.risk_level)} />
          </div>
          <dl className="customer-profile-meta">
            <div><dt>归属门店</dt><dd>{profile.home_store_name}</dd></div>
            <div><dt>获客渠道</dt><dd>{profile.acquisition_channel}</dd></div>
            <div><dt>地域</dt><dd>{profile.province}</dd></div>
            <div><dt>偏好品类</dt><dd>{profile.preferred_category}</dd></div>
            <div><dt>注册时间</dt><dd>{formatDateTime(profile.registered_at)}</dd></div>
            <div><dt>最近活跃</dt><dd>{formatDateTime(profile.last_active_at)}</dd></div>
          </dl>
          <div className="customer-profile-tags">
            {profile.tags.map((tag) => <span key={tag}>{tag}</span>)}
          </div>
          <footer className="customer-profile-provenance">
            <FileKey2 aria-hidden="true" size={15} />
            <span>主档同步批次</span>
            <code>{profile.sync_run_id}</code>
          </footer>
        </section>

        <section className="customer-detail-panel customer-playbook-panel">
          <DetailPanelHeader
            eyebrow="GOVERNED NEXT MOVE"
            meta={`规则策略 · ${data.playbook_version}`}
            title="运营判断与动作边界"
          />
          <div className="customer-recommendation-list">
            {data.recommendations.length > 0 ? data.recommendations.map((item) => (
              <article className={item.eligible ? "" : "ineligible"} key={item.key}>
                <header>
                  <div><Target aria-hidden="true" size={17} /><strong>{item.title}</strong></div>
                  <StatusBadge value={{ label: PRIORITY_LABELS[item.priority], tone: priorityTone(item.priority) }} />
                </header>
                <p>{item.rationale}</p>
                <dl>
                  <div><dt>运营目标</dt><dd>{item.objective}</dd></div>
                  <div><dt>动作边界</dt><dd>{item.action_boundary}</dd></div>
                </dl>
                <footer>
                  <span>{item.eligible ? "可进入人工方案审核" : "当前不可触达"}</span>
                  <div>{item.evidence_keys.map((key) => <code key={key}>{key}</code>)}</div>
                </footer>
              </article>
            )) : (
              <div className="customer-playbook-empty"><BadgeCheck size={22} /><strong>当前无额外干预建议</strong><span>继续按正常生命周期观察。</span></div>
            )}
          </div>
          <p className="customer-playbook-note">
            <Sparkles aria-hidden="true" size={15} />
            当前结果由确定性规则生成，不是模型自由推断；不会自动发券、发消息或写回第三方系统。
          </p>
        </section>
      </div>

      <CustomerOperationPanel
        error={operationError}
        loading={operationLoading}
        objective={objective}
        onDueHintChange={setProposalDueHint}
        onObjectiveChange={setObjective}
        onPropose={() => void proposeOperationActions()}
        onRun={runOperationPlan}
        onToggleStep={toggleOperationStep}
        proposalDueHint={proposalDueHint}
        proposalError={proposalError}
        proposalRunning={proposalRunning}
        running={operationRunning}
        selectedSteps={selectedOperationSteps}
        studio={operationStudio}
      />

      <div className="customer-detail-activity-grid">
        <section className="customer-detail-panel customer-timeline-panel">
          <DetailPanelHeader eyebrow="UNIFIED TIMELINE" meta={`${data.timeline.length} 条事实`} title="客户活动时间线" />
          <div className="customer-detail-timeline">
            {data.timeline.map((item) => (
              <article key={item.event_key}>
                <span className={`customer-event-icon ${item.event_type}`}>{eventIcon(item.event_type)}</span>
                <div>
                  <header><strong>{item.title}</strong><em>{EVENT_LABELS[item.event_type]}</em></header>
                  <p>{item.detail}</p>
                  <footer><time>{formatDateTime(item.occurred_at)}</time><code>{item.evidence_key}</code></footer>
                </div>
                {item.value_yuan !== null ? <b>{formatMoney(item.value_yuan)}</b> : null}
              </article>
            ))}
          </div>
        </section>

        <section className="customer-detail-panel customer-signal-panel">
          <DetailPanelHeader eyebrow="RECENT SIGNAL" meta={`${data.touchpoints.length} 条行为`} title="行为触点明细" />
          <div className="customer-detail-touchpoints">
            {data.touchpoints.map((item) => <CustomerSignal item={item} key={item.touchpoint_key} />)}
          </div>
        </section>
      </div>

      <div className="customer-detail-ledger-grid">
        <section className="customer-detail-panel">
          <DetailPanelHeader eyebrow="ERP ORDER FACT" meta={`${data.orders.length} 笔`} title="可信订单台账" />
          <div className="customer-detail-table-wrap">
            <table>
              <thead><tr><th>订单</th><th>门店 / 渠道</th><th>支付时间</th><th>件数</th><th className="align-right">实付 / 毛利</th></tr></thead>
              <tbody>
                {data.orders.map((item) => (
                  <tr key={item.order_key}>
                    <td><strong>{item.order_key}</strong><small>{item.status} · {item.source_key}</small></td>
                    <td><strong>{item.store_name}</strong><small>{item.channel}</small></td>
                    <td>{formatDateTime(item.paid_at)}</td>
                    <td>{item.item_count}</td>
                    <td className="align-right"><strong>{formatMoney(item.paid_amount_yuan)}</strong><small>毛利 {formatMoney(item.gross_margin_yuan)} · {formatPercent(item.gross_margin_rate)}</small></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.orders.length === 0 ? <LedgerEmpty label="当前范围内没有可信订单事实" /> : null}
          </div>
        </section>

        <section className="customer-detail-panel">
          <DetailPanelHeader eyebrow="ERP REFUND FACT" meta={`${data.refunds.length} 笔`} title="退款与售后台账" />
          <div className="customer-detail-table-wrap">
            <table>
              <thead><tr><th>退款</th><th>关联订单</th><th>原因 / 状态</th><th>申请时间</th><th className="align-right">退款金额</th></tr></thead>
              <tbody>
                {data.refunds.map((item) => (
                  <tr key={item.refund_key}>
                    <td><strong>{item.refund_key}</strong><small>{item.sku_key} · {item.source_key}</small></td>
                    <td>{item.order_key}</td>
                    <td><strong>{item.reason_category}</strong><small>{item.status} · {item.quantity} 件</small></td>
                    <td>{formatDateTime(item.requested_at)}</td>
                    <td className="align-right"><strong>{formatMoney(item.refund_amount_yuan)}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.refunds.length === 0 ? <LedgerEmpty label="当前范围内没有退款事实" /> : null}
          </div>
        </section>
      </div>

      <section className="customer-detail-panel customer-detail-lineage-panel">
        <DetailPanelHeader eyebrow="DATA LINEAGE" meta={`生成于 ${formatDateTime(data.generated_at)}`} title="本页实际使用的数据资产" />
        <div className="customer-detail-lineage">
          {data.lineage.map((asset) => (
            <article key={asset.key}>
              <Database aria-hidden="true" size={17} />
              <div><strong>{asset.label}</strong><code>{asset.table_name}</code></div>
              <b>{formatNumber(asset.record_count)}<small> 条</small></b>
              <p>{asset.source_key} · schema {asset.source_schema_version} · map {asset.mapping_version}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

const OPERATION_ACTION_LABELS = {
  manual_review: "人工复核",
  service_handoff: "客服交接",
  content_preparation: "内容准备",
  audience_analysis: "人群分析"
} as const;

function CustomerOperationPanel({
  studio,
  loading,
  running,
  error,
  objective,
  proposalDueHint,
  proposalError,
  proposalRunning,
  selectedSteps,
  onObjectiveChange,
  onDueHintChange,
  onPropose,
  onToggleStep,
  onRun
}: {
  studio: CustomerOperationStudioResponse | null;
  loading: boolean;
  running: boolean;
  error: string | null;
  objective: string;
  proposalDueHint: string;
  proposalError: string | null;
  proposalRunning: boolean;
  selectedSteps: number[];
  onObjectiveChange: (value: string) => void;
  onDueHintChange: (value: string) => void;
  onPropose: () => void;
  onToggleStep: (index: number) => void;
  onRun: (event: FormEvent<HTMLFormElement>) => void;
}) {
  const latest = studio?.runs[0] ?? null;
  return (
    <section className="customer-operation-panel">
      <header>
        <div><span>AI CUSTOMER OPERATION · EVIDENCE LOCKED</span><h2>AI 客户运营方案台</h2></div>
        <div className="customer-operation-status">
          <StatusBadge value={{ label: "禁止外部写入", tone: "warning" }} />
          <StatusBadge value={{ label: "必须人工确认", tone: "info" }} />
        </div>
      </header>
      <div className="customer-operation-layout">
        <form className="customer-operation-composer" onSubmit={onRun}>
          <div className="customer-operation-intro">
            <Bot aria-hidden="true" size={21} />
            <div><strong>从当前客户证据生成内部运营方案</strong><p>运行时冻结主档、订单、退款和触点。模型只能引用本次 E 编号证据，生成结果不会直接触达客户。</p></div>
          </div>
          <label htmlFor="customer-operation-objective">本次运营目标</label>
          <textarea
            id="customer-operation-objective"
            maxLength={1000}
            minLength={8}
            onChange={(event) => onObjectiveChange(event.target.value)}
            rows={4}
            value={objective}
          />
          {error ? <p className="customer-operation-error"><AlertTriangle size={14} />{error}</p> : null}
          <div className="customer-operation-submit">
            <span>{studio?.can_run ? "发起人和数据范围将写入审计快照" : "当前账号可查看方案，但没有生成权限"}</span>
            <button className="button primary" disabled={!studio?.can_run || running || loading || objective.trim().length < 8} type="submit">
              {running ? <LoaderCircle className="spinning" aria-hidden="true" size={16} /> : <Sparkles aria-hidden="true" size={16} />}
              {running ? "正在冻结证据并生成" : "生成 AI 运营方案"}
            </button>
          </div>
          <div className="customer-operation-guardrails">
            <span><ShieldCheck aria-hidden="true" size={15} />不发送消息</span>
            <span><ShieldCheck aria-hidden="true" size={15} />不自动发券</span>
            <span><ShieldCheck aria-hidden="true" size={15} />不写回 CRM</span>
          </div>
        </form>
        <CustomerOperationResult
          canPropose={studio?.can_propose ?? false}
          dueHint={proposalDueHint}
          error={proposalError}
          loading={loading}
          onDueHintChange={onDueHintChange}
          onPropose={onPropose}
          onToggleStep={onToggleStep}
          proposing={proposalRunning}
          run={latest}
          selectedSteps={selectedSteps}
        />
      </div>
    </section>
  );
}

function CustomerOperationResult({
  run,
  loading,
  canPropose,
  proposing,
  selectedSteps,
  dueHint,
  error,
  onToggleStep,
  onDueHintChange,
  onPropose
}: {
  run: CustomerOperationRun | null;
  loading: boolean;
  canPropose: boolean;
  proposing: boolean;
  selectedSteps: number[];
  dueHint: string;
  error: string | null;
  onToggleStep: (index: number) => void;
  onDueHintChange: (value: string) => void;
  onPropose: () => void;
}) {
  if (loading) {
    return <div className="customer-operation-empty"><LoaderCircle className="spinning" size={23} /><strong>正在读取运营方案台账</strong></div>;
  }
  if (!run) {
    return <div className="customer-operation-empty"><Sparkles size={23} /><strong>尚未生成运营方案</strong><span>确定性策略仍作为当前安全底线。</span></div>;
  }
  const proposalByStep = new Map(run.action_proposals.map((item) => [item.step_index, item]));
  return (
    <div className="customer-operation-result">
      <div className="customer-operation-result-head">
        <div><span>{run.execution_mode === "model" ? "STRUCTURED MODEL" : "RULE FALLBACK"}</span><h3>{run.result.headline}</h3></div>
        <StatusBadge value={{ label: run.execution_mode === "model" ? "真实模型" : "规则降级", tone: run.execution_mode === "model" ? "positive" : "warning" }} />
      </div>
      <p className="customer-operation-summary">{run.result.summary}</p>
      <dl className="customer-operation-meta">
        <div><dt>发起人</dt><dd>{run.initiated_by_name}</dd></div>
        <div><dt>风险</dt><dd>{run.risk_level === "high" ? "高" : run.risk_level === "medium" ? "中" : "低"}</dd></div>
        <div><dt>冻结证据</dt><dd>{run.evidence_snapshot.item_count} 条</dd></div>
        <div><dt>运行耗时</dt><dd>{formatDuration(run.duration_ms)}</dd></div>
      </dl>
      <div className="customer-operation-diagnoses">
        {run.result.diagnoses.slice(0, 4).map((item, index) => (
          <article key={`${item.kind}-${index}`}>
            <span className={item.severity} />
            <p>{item.text}</p>
            <div>{item.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</div>
          </article>
        ))}
      </div>
      <div className="customer-operation-steps">
        {run.result.steps.map((step, index) => {
          const proposal = proposalByStep.get(index);
          return (
          <article key={`${step.title}-${index}`}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              <header><strong>{step.title}</strong><div><em>{OPERATION_ACTION_LABELS[step.action_type]}</em><label className={proposal ? "proposed" : ""}><input checked={proposal ? true : selectedSteps.includes(index)} disabled={Boolean(proposal) || !canPropose || proposing} onChange={() => onToggleStep(index)} type="checkbox" /><span>{proposal ? (proposal.status === "approved" ? "行动已批准" : proposal.status === "rejected" ? "行动已驳回" : "行动待审批") : "选择"}</span></label></div></header>
              <p>{step.action}</p>
              <footer><span>{step.owner_role} · {step.success_metric}</span><div>{step.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</div></footer>
            </div>
          </article>
        );})}
      </div>
      <div className="customer-operation-action-gate">
        <div><ListPlus size={18} /><div><strong>人工确认后送入行动中心</strong><p>仅生成 R2 内部提案；发起人与审批人分离，批准后也只登记内部台账。</p></div></div>
        <label><span>期望完成时间</span><input disabled={!canPropose || proposing} maxLength={300} minLength={2} onChange={(event) => onDueHintChange(event.target.value)} value={dueHint} /></label>
        <button className="button primary" disabled={!canPropose || proposing || !selectedSteps.length || dueHint.trim().length < 2} onClick={onPropose} type="button">{proposing ? <LoaderCircle className="spinning" size={16} /> : <ListPlus size={16} />}{proposing ? "正在创建提案" : `送入行动中心${selectedSteps.length ? ` (${selectedSteps.length})` : ""}`}</button>
        <Link className="button secondary" href="/console/actions/approvals">查看审批队列</Link>
        {!canPropose ? <p className="customer-operation-action-message warning">当前账号没有 action.propose 权限。</p> : null}
        {error ? <p className="customer-operation-action-message error"><AlertTriangle size={14} />{error}</p> : null}
      </div>
      <details className="customer-operation-evidence">
        <summary><Database size={15} />查看冻结证据与禁止动作</summary>
        <div>
          {run.evidence.map((item) => <p key={item.evidence_ref}><code>{item.evidence_ref}</code><span>{item.label}</span><em>{item.version_ref ?? "当前版本"}</em></p>)}
        </div>
        <ul>{run.result.prohibited_actions.map((item) => <li key={item}><CheckCircle2 size={14} />{item}</li>)}</ul>
        <footer><Clock3 size={14} />冻结于 {formatDateTime(run.evidence_snapshot.frozen_at)} · {run.evidence_snapshot.content_hash.slice(0, 16)}</footer>
      </details>
    </div>
  );
}

function DetailPanelHeader({ eyebrow, title, meta }: { eyebrow: string; title: string; meta: string }) {
  return <header><div><span>{eyebrow}</span><h2>{title}</h2></div><em>{meta}</em></header>;
}

function CustomerSignal({ item }: { item: Customer360Touchpoint }) {
  return (
    <article>
      <span><MousePointerClick aria-hidden="true" size={15} /></span>
      <div><strong>{TOUCHPOINT_LABELS[item.touchpoint_type] ?? item.touchpoint_type}</strong><p>{item.channel} · {item.campaign_key ?? "自然行为"}</p></div>
      <time>{formatDateTime(item.occurred_at)}</time>
      <code>{item.touchpoint_key}</code>
    </article>
  );
}

function LedgerEmpty({ label }: { label: string }) {
  return <div className="customer-ledger-empty"><PackageCheck aria-hidden="true" size={20} />{label}</div>;
}

function CustomerDetailState({
  message,
  note = "所有数据均按当前账号范围实时读取",
  failed = false,
  onRetry
}: {
  message: string;
  note?: string;
  failed?: boolean;
  onRetry?: () => void;
}) {
  return (
    <div className={`customer-360-state ${failed ? "failed" : ""}`} role={failed ? "alert" : undefined}>
      {failed ? <AlertTriangle aria-hidden="true" size={30} /> : <LoaderCircle className="spinning" aria-hidden="true" size={28} />}
      <strong>{message}</strong>
      <span>{note}</span>
      <div className="customer-detail-state-actions">
        <Link className="button secondary" href="/console/data/products/customers"><ArrowLeft size={16} />返回客户队列</Link>
        {onRetry ? <button className="button secondary" onClick={onRetry} type="button"><RefreshCw size={16} />重新读取</button> : null}
      </div>
    </div>
  );
}
