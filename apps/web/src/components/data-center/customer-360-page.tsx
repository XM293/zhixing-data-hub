"use client";

import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  CircleDollarSign,
  Database,
  Gauge,
  LoaderCircle,
  MousePointerClick,
  RefreshCw,
  Repeat2,
  ShieldCheck,
  Sparkles,
  UsersRound
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";

import { PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type {
  Customer360Customer,
  Customer360Response,
  Customer360Touchpoint
} from "@/lib/data-center-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const LIFECYCLE_LABELS: Record<string, string> = {
  new: "新客培育",
  growing: "成长客户",
  mature: "成熟客户",
  sleeping: "沉睡唤醒",
  at_risk: "流失预警"
};

const TOUCHPOINT_LABELS: Record<string, string> = {
  visit: "访问店铺",
  product_view: "浏览商品",
  add_cart: "加入购物车",
  add_to_cart: "加入购物车",
  campaign_click: "活动点击",
  coupon: "领取优惠券",
  coupon_claim: "领取优惠券",
  service: "咨询客服"
};

const MEMBER_LABELS: Record<string, string> = {
  regular: "普通会员",
  standard: "普通会员",
  silver: "银卡会员",
  gold: "金卡会员",
  platinum: "铂金会员",
  black_gold: "黑金会员"
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatMoney(value: number, compact = false): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    notation: compact ? "compact" : "standard",
    maximumFractionDigits: compact ? 1 : 2
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
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function scopeLabel(scopeKey: string): string {
  if (scopeKey === "enterprise") return "全企业";
  if (scopeKey === "store-flagship") return "旗舰店";
  if (scopeKey === "store-outlet") return "奥莱店";
  return `门店 · ${scopeKey}`;
}

function riskTone(score: number): "positive" | "warning" | "critical" | "neutral" {
  if (score >= 0.7) return "critical";
  if (score >= 0.45) return "warning";
  if (score < 0.2) return "positive";
  return "neutral";
}

function riskLabel(score: number): string {
  if (score >= 0.7) return "高风险";
  if (score >= 0.45) return "需关注";
  if (score < 0.2) return "低风险";
  return "稳定";
}

export function Customer360Page() {
  const { identity, identityLoading, can } = useExperience();
  const scopeOptions = useMemo(() => {
    if (!identity) return [];
    const options = new Set<string>();
    identity.actor.scopes
      .filter((scope) => scope.effect === "allow")
      .forEach((scope) => {
        if (scope.scope_type === "enterprise" && scope.scope_ids.includes(identity.enterprise_id)) {
          options.add("enterprise");
        }
        if (scope.scope_type === "store") scope.scope_ids.forEach((scopeId) => options.add(scopeId));
      });
    return [...options];
  }, [identity]);
  const [scopeKey, setScopeKey] = useState("enterprise");
  const [data, setData] = useState<Customer360Response | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (scopeOptions.length > 0 && !scopeOptions.includes(scopeKey)) setScopeKey(scopeOptions[0]);
  }, [scopeKey, scopeOptions]);

  const loadData = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    if (identityLoading) return;
    if (!identity || !can("customer.profile.read") || scopeOptions.length === 0) {
      setLoading(false);
      setData(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ scope_key: scopeKey, limit: "60" });
    apiFetch(`${API_BASE_URL}/api/v1/data-center/customer-360?${params}`, {
      cache: "no-store",
      signal: controller.signal
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiErrorMessage(response, "客户 360 数据暂不可用"));
        return response.json() as Promise<Customer360Response>;
      })
      .then(setData)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "无法读取客户 360 数据");
        setData(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [can, identity, identityLoading, reloadToken, scopeKey, scopeOptions.length]);

  if (identityLoading || loading) {
    return (
      <div className="customer-360-state" aria-live="polite">
        <LoaderCircle className="spinning" aria-hidden="true" size={28} />
        <strong>正在合并客户主档、交易与触点事实</strong>
        <span>所有指标均按当前账号的数据范围实时计算</span>
      </div>
    );
  }

  if (!identity || !can("customer.profile.read")) {
    return (
      <div className="customer-360-state failed" role="alert">
        <ShieldCheck aria-hidden="true" size={30} />
        <strong>当前账号没有客户画像读取权限</strong>
        <span>请由平台管理员分配 customer.profile.read 权限与企业或门店数据范围。</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="customer-360-state failed" role="alert">
        <AlertTriangle aria-hidden="true" size={30} />
        <strong>客户 360 工作台暂不可用</strong>
        <span>{error ?? "当前账号没有可用的客户数据范围"}</span>
        <button className="button secondary" onClick={loadData} type="button">重新连接</button>
      </div>
    );
  }

  const summary = data.summary;
  const stats = [
    { icon: UsersRound, label: "客户主档", value: formatNumber(summary.profile_count), note: `${formatNumber(summary.active_customer_count)} 位当前活跃` },
    { icon: CircleDollarSign, label: "关联成交", value: formatMoney(summary.paid_gmv_yuan, true), note: `客均价值 ${formatMoney(summary.average_customer_value_yuan)}` },
    { icon: Repeat2, label: "复购率", value: formatPercent(summary.repeat_purchase_rate), note: `${formatNumber(summary.repeat_customer_count)} 位复购客户` },
    { icon: Gauge, label: "流失预警", value: formatNumber(summary.at_risk_customer_count), note: `${formatPercent(summary.at_risk_customer_count / Math.max(summary.profile_count, 1))} 客群占比`, tone: "critical" },
    { icon: MousePointerClick, label: "客户触点", value: formatNumber(summary.touchpoint_count), note: `${formatNumber(summary.purchasing_customer_count)} 位已成交` },
    { icon: BadgeCheck, label: "可触达客户", value: formatNumber(summary.consented_customer_count), note: `${formatPercent(summary.consented_customer_count / Math.max(summary.profile_count, 1))} 已授权`, tone: "positive" }
  ];
  const maxSegmentCustomers = Math.max(...data.segments.map((item) => item.customer_count), 1);
  const maxTrend = Math.max(...data.touchpoint_trend.map((item) => item.touchpoint_count), 1);

  return (
    <div className="customer-360-page">
      <PageHeader
        actions={
          <div className="customer-360-actions">
            <label>
              <span>数据范围</span>
              <select aria-label="客户数据范围" onChange={(event) => setScopeKey(event.target.value)} value={scopeKey}>
                {scopeOptions.map((option) => <option key={option} value={option}>{scopeLabel(option)}</option>)}
              </select>
            </label>
            <button className="button secondary" onClick={loadData} type="button">
              <RefreshCw aria-hidden="true" size={16} />刷新数据
            </button>
          </div>
        }
        description="以客户主档为锚点，连接 CRM 行为、ERP 订单与退款事实，识别价值、阶段和流失风险。"
        eyebrow="CUSTOMER INTELLIGENCE · GOVERNED FACTS"
        meta={`${scopeLabel(data.scope_key)} · 数据库实时计算`}
        title="客户 360 运营工作台"
      />

      {error ? <div className="customer-360-error" role="alert"><AlertTriangle size={15} />{error}</div> : null}

      <section className="customer-360-stat-band" aria-label="客户经营指标">
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

      <div className="customer-360-insight-grid">
        <section className="customer-360-panel customer-segment-panel">
          <PanelHeader eyebrow="LIFECYCLE" meta={`${data.segments.length} 个阶段`} title="客户生命周期与价值分层" />
          <div className="customer-segment-list">
            {data.segments.map((segment) => (
              <article key={segment.key}>
                <div className="customer-segment-copy">
                  <span className={`customer-segment-mark ${segment.key}`} />
                  <div><strong>{segment.label}</strong><small>{formatNumber(segment.customer_count)} 位客户 · {formatNumber(segment.purchasing_customer_count)} 位成交</small></div>
                  <b>{formatMoney(segment.paid_gmv_yuan, true)}</b>
                </div>
                <div className="customer-segment-track"><i style={{ "--segment-width": `${segment.customer_count / maxSegmentCustomers * 100}%` } as CSSProperties} /></div>
                <footer><span>人均 {segment.average_order_count.toFixed(1)} 单</span><span>{segment.at_risk_customer_count > 0 ? `${segment.at_risk_customer_count} 位风险客户` : "当前风险可控"}</span></footer>
              </article>
            ))}
          </div>
        </section>

        <section className="customer-360-panel customer-channel-panel">
          <PanelHeader eyebrow="ACQUISITION" meta={`${data.channels.length} 个渠道`} title="获客渠道贡献" />
          <div className="customer-channel-table">
            <table>
              <thead><tr><th>渠道</th><th>客户</th><th>已成交</th><th>触点</th><th className="align-right">成交额</th></tr></thead>
              <tbody>
                {data.channels.map((channel) => (
                  <tr key={channel.key}>
                    <td><strong>{channel.label}</strong><small>{channel.key}</small></td>
                    <td>{formatNumber(channel.customer_count)}</td>
                    <td>{formatNumber(channel.purchasing_customer_count)}</td>
                    <td>{formatNumber(channel.touchpoint_count)}</td>
                    <td className="align-right"><b>{formatMoney(channel.paid_gmv_yuan, true)}</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="customer-360-panel customer-trend-panel">
          <PanelHeader eyebrow="BEHAVIOR SIGNAL" meta="最近 30 日" title="客户触点与活跃趋势" />
          <div className="customer-trend-chart" aria-label="最近 30 日客户触点趋势">
            {data.touchpoint_trend.map((point) => (
              <div key={point.business_date} title={`${point.business_date} · ${point.touchpoint_count} 个触点 · ${point.active_customer_count} 位活跃客户`}>
                <i style={{ height: `${Math.max(point.touchpoint_count / maxTrend * 100, 4)}%` }} />
                <b style={{ height: `${Math.max(point.active_customer_count / maxTrend * 100, 3)}%` }} />
              </div>
            ))}
          </div>
          <footer className="customer-trend-legend">
            <span><i />客户触点</span><span><i />活跃客户</span>
            <time>更新于 {formatDateTime(data.generated_at)}</time>
          </footer>
        </section>
      </div>

      <section className="customer-360-panel customer-priority-panel">
        <PanelHeader eyebrow="PRIORITY QUEUE" meta={`展示 ${data.customers.length} 位`} title="价值与流失风险优先队列" />
        <div className="customer-360-table-wrap">
          <table>
            <thead><tr><th>客户</th><th>生命周期</th><th>会员等级</th><th>归属门店</th><th>交易表现</th><th>行为触点</th><th>流失风险</th><th>最近活跃</th><th>详情</th></tr></thead>
            <tbody>
              {data.customers.map((customer) => <CustomerRow customer={customer} key={customer.customer_key} scopeKey={data.scope_key} />)}
            </tbody>
          </table>
        </div>
      </section>

      <div className="customer-360-bottom-grid">
        <section className="customer-360-panel customer-touchpoint-panel">
          <PanelHeader eyebrow="RECENT SIGNAL" meta={`${data.recent_touchpoints.length} 条`} title="最新客户行为触点" />
          <div className="customer-touchpoint-list">
            {data.recent_touchpoints.slice(0, 12).map((item) => <TouchpointRow item={item} key={item.touchpoint_key} />)}
          </div>
        </section>
        <section className="customer-360-panel customer-lineage-panel">
          <PanelHeader eyebrow="DATA LINEAGE" meta="可追溯" title="客户洞察资产血缘" />
          <div className="customer-lineage-list">
            {data.lineage.map((asset) => (
              <article key={asset.key}>
                <span><Database aria-hidden="true" size={17} /></span>
                <div><strong>{asset.label}</strong><code>{asset.table_name}</code></div>
                <b>{formatNumber(asset.record_count)}<small> 条</small></b>
                <footer>{asset.source_key} · schema {asset.source_schema_version} · map {asset.mapping_version}</footer>
              </article>
            ))}
          </div>
          <p className="customer-lineage-note"><Sparkles aria-hidden="true" size={14} />AI、MCP 与页面共用同一受治理服务，不会绕过账号权限或直接猜测原始表结构。</p>
        </section>
      </div>
    </div>
  );
}

function PanelHeader({ eyebrow, title, meta }: { eyebrow: string; title: string; meta: string }) {
  return <header><div><span>{eyebrow}</span><h2>{title}</h2></div><em>{meta}</em></header>;
}

function CustomerRow({ customer, scopeKey }: { customer: Customer360Customer; scopeKey: string }) {
  return (
    <tr>
      <td><strong className="customer-name">{customer.display_name}</strong><code>{customer.customer_key}</code><small>{customer.province} · 偏好 {customer.preferred_category}</small></td>
      <td><StatusBadge value={{ label: LIFECYCLE_LABELS[customer.lifecycle_stage] ?? customer.lifecycle_stage, tone: customer.lifecycle_stage === "at_risk" ? "critical" : customer.lifecycle_stage === "mature" ? "positive" : "info" }} /></td>
      <td><strong>{MEMBER_LABELS[customer.member_level] ?? customer.member_level}</strong><small>{customer.consent_status === "granted" ? "允许触达" : "未授权触达"}</small></td>
      <td><strong>{customer.home_store_name}</strong><small>{customer.acquisition_channel}</small></td>
      <td><strong>{formatMoney(customer.paid_gmv_yuan)}</strong><small>{customer.order_count} 单 · 退款 {formatMoney(customer.refund_amount_yuan)}</small></td>
      <td><strong>{formatNumber(customer.touchpoint_count)} 次</strong><small>{formatDateTime(customer.last_touchpoint_at)}</small></td>
      <td><StatusBadge value={{ label: `${riskLabel(customer.churn_risk_score)} ${formatPercent(customer.churn_risk_score)}`, tone: riskTone(customer.churn_risk_score) }} /></td>
      <td><strong>{formatDateTime(customer.last_active_at)}</strong><small>CRM · {customer.source_key}</small></td>
      <td>
        <Link
          aria-label={`查看 ${customer.display_name} 的客户 360 详情`}
          className="customer-detail-link"
          href={`/console/data/products/customers/${encodeURIComponent(scopeKey)}/${encodeURIComponent(customer.customer_key)}`}
        >
          查看<ArrowRight aria-hidden="true" size={14} />
        </Link>
      </td>
    </tr>
  );
}

function TouchpointRow({ item }: { item: Customer360Touchpoint }) {
  return (
    <article>
      <span><Activity aria-hidden="true" size={15} /></span>
      <div><strong>{item.customer_name}</strong><small>{TOUCHPOINT_LABELS[item.touchpoint_type] ?? item.touchpoint_type} · {item.channel}</small></div>
      <time>{formatDateTime(item.occurred_at)}</time>
      {item.campaign_key ? <em>{item.campaign_key}</em> : <em>{scopeLabel(item.store_key)}</em>}
    </article>
  );
}
