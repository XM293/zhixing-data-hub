"use client";

import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Boxes,
  CircleDot,
  Database,
  Maximize2,
  Minimize2,
  Network,
  RadioTower,
  RefreshCw,
  ServerCog,
  UsersRound
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ScopeTwinPanel } from "@/components/twin/scope-twin-panel";
import { useExperience } from "@/demo/experience-provider";

import {
  buildAssetSeries,
  buildMetricTrendSeries,
  buildNodeGroups,
  buildNodeRing
} from "@/lib/cockpit-model";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type { MetricSeriesResponse } from "@/lib/data-center-types";
import type { EnterpriseTwinOverview } from "@/lib/twin-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const METRIC_ORDER = ["gmv_today", "orders_today", "ad_roi", "refund_rate", "active_members", "low_stock_skus"];
const TREND_METRICS = ["gmv_today", "orders_today", "refund_rate", "ad_roi"];

const METRIC_ICONS: Record<string, typeof Activity> = {
  gmv_today: Activity,
  orders_today: Boxes,
  ad_roi: RadioTower,
  refund_rate: ArrowDownRight,
  active_members: UsersRound,
  low_stock_skus: AlertTriangle
};

function formatMetric(value: number, unit: string): string {
  if (unit === "元" && value >= 10000) return `${(value / 10000).toFixed(1)}万`;
  if (value >= 10000) return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
  if (unit === "%" || unit === "x") return value.toFixed(2);
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
}

function formatCount(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatTime(value: string | null): string {
  if (!value) return "尚未同步";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function statusLabel(status: NonNullable<EnterpriseTwinOverview["meeting"]>["status"]): string {
  if (status === "scheduled") return "等待召集";
  if (status === "convening") return "分身入场";
  if (status === "in_session") return "研判进行中";
  return "决策包已形成";
}

export function EnterpriseCockpitPage() {
  const { scopeContext } = useExperience();
  if (!scopeContext) return <p role="status">正在读取范围</p>;
  if (scopeContext.scope_level !== "enterprise") return <ScopeTwinPanel key={scopeContext.scope_version} />;
  return <ScopedEnterpriseCockpitPage key={scopeContext?.scope_version ?? "pending"} />;
}

function ScopedEnterpriseCockpitPage() {
  const cockpitRef = useRef<HTMLElement>(null);
  const [overview, setOverview] = useState<EnterpriseTwinOverview | null>(null);
  const [metricSeries, setMetricSeries] = useState<MetricSeriesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

  const loadOverview = useCallback(async () => {
    setError(null);
    setSeriesError(null);
    const [overviewResult, seriesResult] = await Promise.allSettled([
      apiFetch(`${API_BASE_URL}/api/v1/data-center/overview`, { cache: "no-store" }),
      apiFetch(
        `${API_BASE_URL}/api/v1/data-center/metric-series?metric_keys=${TREND_METRICS.join(",")}&scope_key=enterprise&days=30`,
        { cache: "no-store" }
      )
    ]);
    if (overviewResult.status === "rejected") throw overviewResult.reason;
    if (!overviewResult.value.ok) {
      throw new Error(await apiErrorMessage(overviewResult.value, "数据中心接口不可用"));
    }
    setOverview((await overviewResult.value.json()) as EnterpriseTwinOverview);
    if (seriesResult.status === "fulfilled" && seriesResult.value.ok) {
      setMetricSeries((await seriesResult.value.json()) as MetricSeriesResponse);
    } else if (seriesResult.status === "fulfilled") {
      setSeriesError(await apiErrorMessage(seriesResult.value, "历史指标接口不可用"));
    } else {
      setSeriesError(seriesResult.reason instanceof Error ? seriesResult.reason.message : "历史指标接口不可用");
    }
  }, []);

  useEffect(() => {
    loadOverview()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取企业数据中心"))
      .finally(() => setLoading(false));
  }, [loadOverview]);

  useEffect(() => {
    const syncFullscreenState = () => setFullscreen(document.fullscreenElement === cockpitRef.current);
    document.addEventListener("fullscreenchange", syncFullscreenState);
    return () => document.removeEventListener("fullscreenchange", syncFullscreenState);
  }, []);

  const toggleFullscreen = useCallback(async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await cockpitRef.current?.requestFullscreen();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "浏览器未允许进入全屏模式");
    }
  }, []);

  const assets = useMemo(() => overview ? buildAssetSeries(overview) : [], [overview]);
  const nodeGroups = useMemo(() => overview ? buildNodeGroups(overview.nodes) : [], [overview]);
  const trends = useMemo(() => metricSeries ? buildMetricTrendSeries(metricSeries) : [], [metricSeries]);

  if (loading) {
    return (
      <div className="cockpit-state" aria-live="polite">
        <Database className="spinning" aria-hidden="true" size={28} />
        <strong>正在装载经营驾驶舱</strong>
        <span>汇总持久化指标、平台节点、事件与数字会议状态</span>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="cockpit-state failed" role="alert">
        <AlertTriangle aria-hidden="true" size={30} />
        <strong>经营驾驶舱暂不可用</strong>
        <span>{error}</span>
        <button onClick={() => window.location.reload()} type="button">重新连接</button>
      </div>
    );
  }

  const metrics = METRIC_ORDER.flatMap((metricKey) => {
    const metric = overview.metrics.find((item) => item.key === metricKey);
    return metric ? [metric] : [];
  });
  const maxAssetValue = Math.max(...assets.map((item) => item.value), 1);
  const connectedSources = overview.sources.filter((source) => source.status !== "disabled" && source.connection_status === "connected").length;
  const healthyNodes = overview.nodes.filter((node) => node.health >= 0.9).length;
  const latestEvents = overview.events.slice(0, 5);
  const ringStyle = { "--cockpit-ring": `conic-gradient(${buildNodeRing(nodeGroups)})` } as CSSProperties;
  const latestSourceTime = overview.sources
    .map((source) => source.last_sync_at)
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1) ?? null;

  return (
    <section className="enterprise-cockpit" aria-label="企业经营驾驶舱" ref={cockpitRef}>
      <header className="cockpit-header">
        <div>
          <div className="cockpit-kicker"><span /> ENTERPRISE INTELLIGENCE COCKPIT · DATABASE VIEW</div>
          <h1>{overview.enterprise.name}经营驾驶舱</h1>
          <p>把经营结果、数据资产、AI 运行和决策过程放在同一张实时业务大屏中。</p>
        </div>
        <div className="cockpit-header-actions">
          <div className="cockpit-live"><span /><div><strong>数据底座在线</strong><small>更新 {formatTime(latestSourceTime)}</small></div></div>
          <button
            aria-label={fullscreen ? "退出驾驶舱全屏" : "驾驶舱全屏"}
            onClick={() => void toggleFullscreen()}
            title={fullscreen ? "退出全屏" : "全屏展示"}
            type="button"
          >
            {fullscreen ? <Minimize2 aria-hidden="true" size={17} /> : <Maximize2 aria-hidden="true" size={17} />}
          </button>
          <button
            aria-label="刷新驾驶舱"
            onClick={() => void loadOverview().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "刷新失败"))}
            title="刷新驾驶舱"
            type="button"
          >
            <RefreshCw aria-hidden="true" size={17} />
          </button>
        </div>
      </header>

      {error ? <div className="cockpit-error" role="alert"><AlertTriangle size={15} />{error}</div> : null}

      <div className="cockpit-metric-grid" aria-label="核心经营指标">
        {metrics.map((metric) => {
          const MetricIcon = METRIC_ICONS[metric.key] ?? Activity;
          const change = metric.change_rate === null ? null : metric.change_rate * 100;
          const favorable = metric.key === "refund_rate" ? (change ?? 0) <= 0 : (change ?? 0) >= 0;
          const DeltaIcon = (change ?? 0) >= 0 ? ArrowUpRight : ArrowDownRight;
          return (
            <article key={metric.key}>
              <div><span className="cockpit-metric-icon"><MetricIcon aria-hidden="true" size={16} /></span><em>{metric.label}</em></div>
              <strong>{formatMetric(metric.value, metric.unit)}<small>{metric.unit === "元" && metric.value >= 10000 ? "元" : metric.unit}</small></strong>
              <p className={change === null ? "neutral" : favorable ? "positive" : "negative"}>
                {change === null ? <span>当前快照</span> : <><DeltaIcon aria-hidden="true" size={13} />{Math.abs(change).toFixed(1)}%</>}
                <time>{formatTime(metric.as_of)}</time>
              </p>
            </article>
          );
        })}
      </div>

      <div className="cockpit-dashboard-grid">
        <section className="cockpit-panel cockpit-delta-panel">
          <div className="cockpit-panel-heading"><div><span>30-DAY BUSINESS PULSE</span><h2>经营指标归一化趋势</h2></div><em>首日 = 100 · 日粒度</em></div>
          {trends.length > 0 ? (
            <>
              <div className="cockpit-trend-chart">
                <svg aria-label="近 30 日经营指标趋势" role="img" viewBox="0 0 720 220">
                  <title>近 30 日经营指标趋势</title>
                  <desc>成交金额、支付订单、退款率和广告 ROI 按首日归一化后的数据库序列。</desc>
                  {[0, 1, 2, 3, 4].map((line) => (
                    <line key={line} x1="0" x2="720" y1={line * 55} y2={line * 55} />
                  ))}
                  {trends.map((trend) => {
                    const lastPoint = trend.points.at(-1);
                    return (
                      <g key={trend.key}>
                        <path d={trend.path} style={{ stroke: trend.color }} />
                        {lastPoint ? <circle cx={lastPoint.x} cy={lastPoint.y} r="4" style={{ fill: trend.color }} /> : null}
                      </g>
                    );
                  })}
                </svg>
              </div>
              <div className="cockpit-trend-legend">
                {trends.map((trend) => {
                  const rate = trend.periodChangeRate === null ? null : trend.periodChangeRate * 100;
                  return (
                    <div key={trend.key}>
                      <i style={{ background: trend.color }} />
                      <span>{trend.label}</span>
                      <strong className={trend.favorable ? "favorable" : "unfavorable"}>
                        {rate === null ? "--" : `${rate > 0 ? "+" : ""}${rate.toFixed(1)}%`}
                      </strong>
                    </div>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="cockpit-trend-empty"><Activity aria-hidden="true" size={22} /><span>{seriesError ?? "同步历史指标后显示 30 日真实趋势"}</span></div>
          )}
          <p className="cockpit-chart-note">曲线来自指标快照数据库并按各指标首日归一化，仅用于比较趋势；原始值、单位和数据时点仍由指标 API 保留。</p>
        </section>

        <section className="cockpit-panel cockpit-node-panel">
          <div className="cockpit-panel-heading"><div><span>PLATFORM TOPOLOGY</span><h2>平台能力节点分布</h2></div><Network aria-hidden="true" size={19} /></div>
          <div className="cockpit-node-visual">
            <div className="cockpit-node-ring" style={ringStyle}><div><strong>{overview.nodes.length}</strong><span>平台节点</span></div></div>
            <div className="cockpit-node-legend">
              {nodeGroups.map((group) => <div key={group.key}><i style={{ background: group.color }} /><span>{group.label}</span><strong>{group.value}</strong></div>)}
            </div>
          </div>
          <div className="cockpit-node-summary"><span><strong>{healthyNodes}</strong>健康节点</span><span><strong>{overview.edges.length}</strong>数据关系</span><span><strong>{overview.database.schema_revision.replace(/_.*/, "")}</strong>迁移版本</span></div>
        </section>

        <section className="cockpit-panel cockpit-asset-panel">
          <div className="cockpit-panel-heading"><div><span>DATA & AI FOOTPRINT</span><h2>平台数据与 AI 内容资产</h2></div><Database aria-hidden="true" size={19} /></div>
          <div className="cockpit-asset-chart">
            {assets.map((asset) => (
              <div key={asset.key}><span>{asset.label}</span><div><i style={{ width: `${Math.max((asset.value / maxAssetValue) * 100, asset.value > 0 ? 4 : 0)}%`, background: asset.color }} /></div><strong>{asset.value}</strong></div>
            ))}
          </div>
          <p className="cockpit-chart-note">七类资产均由当前数据库记录聚合；完整表级数量保留在数据、知识、分身与工具目录。</p>
        </section>

        <section className="cockpit-panel cockpit-runtime-panel">
          <div className="cockpit-panel-heading"><div><span>LIVE OPERATIONS</span><h2>运行与决策现场</h2></div><CircleDot aria-hidden="true" size={19} /></div>
          <div className="cockpit-runtime-block">
            <div className="cockpit-source-line"><span className={connectedSources > 0 ? "online" : "offline"} /><div><strong>{overview.sources.length > 0 ? `${overview.sources.length} 个业务数据来源` : "尚无数据来源"}</strong><small>{connectedSources}/{overview.sources.length} 来源在线 · {formatCount(overview.source_record_count)} 条原始记录</small></div><em>{overview.latest_sync?.status ?? "idle"}</em></div>
            {overview.meeting ? <div className="cockpit-meeting-line"><UsersRound aria-hidden="true" size={19} /><div><strong>{overview.meeting.title}</strong><small>{overview.meeting.participants.length} 位分身 · {overview.meeting.evidence_snapshot}</small></div><em>{statusLabel(overview.meeting.status)}</em></div> : <p>暂无会议</p>}
          </div>
          <div className="cockpit-event-list">
            {latestEvents.map((event) => (
              <article key={event.id}><i className={event.severity} /><div><strong>{event.title}</strong><span>{event.detail}</span></div><time>{formatTime(event.occurred_at)}</time></article>
            ))}
          </div>
        </section>

        <section className="cockpit-panel cockpit-gap-panel">
          <div className="cockpit-panel-heading"><div><span>SOURCE CONNECTIONS</span><h2>来源连接状态</h2></div></div>
          <div className="cockpit-gap-list">
            {overview.sources.map((source, index) => (
              <article key={source.key}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong>{source.name}<em>{source.status === "disabled" ? "已停用" : source.connection_status === "connected" ? "已连接" : source.connection_status === "unknown" || !source.connection_status ? "未探测" : source.connection_status}</em></strong>
                  <p>最近同步：{formatTime(source.last_sync_at)}</p>
                </div>
              </article>
            ))}
            {!overview.sources.length ? <p>暂无来源</p> : null}
          </div>
        </section>
      </div>

      <footer className="cockpit-footprint">
        <span><ServerCog aria-hidden="true" size={13} />{overview.database.engine.toUpperCase()} · {overview.database.persistent ? "持久化" : "临时"}</span>
        <span><Database aria-hidden="true" size={13} />schema {overview.schema_version}</span>
        <span>生成于 {formatTime(overview.generated_at)}</span>
      </footer>
    </section>
  );
}
