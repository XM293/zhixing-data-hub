"use client";

import {
  Activity,
  AlertTriangle,
  Braces,
  Database,
  Link2,
  Play,
  RefreshCw,
  Rows3,
  ServerCog,
  Waypoints
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";

import { PageHeader, StatusBadge } from "@/components/console/ui";
import { ConfirmDialog, Dialog } from "@/components/console/interaction";
import { SourceLedgerDialog } from "@/components/data-center/source-ledger-dialog";
import { useExperience } from "@/demo/experience-provider";
import { apiErrorMessage } from "@/lib/api-error";
import { apiFetch } from "@/lib/api-client";
import type { EnterpriseTwinOverview } from "@/lib/twin-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface SourceOperationsView {
  schema_version: 1;
  enterprise_id: string;
  enterprise_name: string;
  scope_context: Record<string, unknown>;
  sources: EnterpriseTwinOverview["sources"];
  latest_sync: EnterpriseTwinOverview["latest_sync"];
  source_record_count: number;
  resource_count: number;
  enabled_resource_count: number;
  pending_resource_count: number;
  generated_at: string;
}

interface SourceConfiguration {
  system_key: string;
  name: string;
  business_unit_id: string | null;
  provider_key: string | null;
  base_url: string;
  status: string;
  version: number;
}

interface SourceEditor {
  system_key: string;
  name: string;
  business_unit_id: string;
  credential_ref: string;
  editing: boolean;
  expected_version?: number;
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

function formatCount(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function sourceTone(status: string): "positive" | "warning" | "critical" | "neutral" {
  if (status === "connected") return "positive";
  if (status === "degraded" || status === "delayed") return "warning";
  if (status === "failed" || status === "disconnected") return "critical";
  return "neutral";
}

function sourceStatus(status: string): string {
  if (status === "connected") return "在线";
  if (status === "degraded") return "部分降级";
  if (status === "delayed") return "同步延迟";
  if (status === "failed") return "连接失败";
  if (status === "disconnected") return "未连接";
  if (status === "configured") return "已配置";
  if (status === "disabled") return "已停用";
  if (status === "probe_queued") return "探测排队中";
  return status;
}

function syncStatus(status: string): string {
  if (status === "succeeded" || status === "success") return "成功";
  if (status === "running") return "运行中";
  if (status === "failed") return "失败";
  if (status === "partial") return "部分完成";
  if (status === "queued") return "排队中";
  if (status === "partial_failed") return "部分失败";
  if (status === "cancelled") return "已取消";
  return status;
}

export function DataSourcesPage() {
  const { scopeContext } = useExperience();
  return <ScopedDataSourcesPage key={scopeContext?.scope_version ?? "pending"} />;
}

function ScopedDataSourcesPage() {
  const { can, identity, scopeOptions } = useExperience();
  const [overview, setOverview] = useState<SourceOperationsView | null>(null);
  const [configurations, setConfigurations] = useState<SourceConfiguration[]>([]);
  const [editor, setEditor] = useState<SourceEditor | null>(null);
  const [ledger, setLedger] = useState<{ key: string; name: string; system_type: string } | null>(null);
  const [disableTarget, setDisableTarget] = useState<SourceConfiguration | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/data-center/source-operations`, { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "数据中心接口不可用"));
    setOverview((await response.json()) as SourceOperationsView);
    const sources = await apiFetch(`${API_BASE_URL}/api/v1/data-center/sources`, { cache: "no-store" });
    if (!sources.ok) throw new Error(await apiErrorMessage(sources, "来源配置读取失败"));
    setConfigurations(await sources.json() as SourceConfiguration[]);
  }, [identity?.enterprise_id]);

  useEffect(() => {
    loadOverview()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取数据中心"))
      .finally(() => setLoading(false));
  }, [loadOverview]);

  const connectedSources = useMemo(
    () => overview?.sources.filter((source) => source.status !== "disabled" && (source.connection_status === "connected" || source.status === "connected")).length ?? 0,
    [overview]
  );

  const saveSource = async () => {
    if (!editor) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/data-center/sources${editor.editing ? `/${encodeURIComponent(editor.system_key)}` : ""}`,
        {
          method: editor.editing ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            expected_version: editor.editing ? editor.expected_version : undefined,
            ...(editor.editing ? {} : {
              system_key: editor.system_key,
              provider_key: "lingxing",
              system_type: "lingxing"
            }),
            name: editor.name,
            business_unit_id: editor.business_unit_id || null,
            credential_ref: editor.credential_ref || undefined,
            base_url: editor.editing
              ? configurations.find((item) => item.system_key === editor.system_key)?.base_url
              : "https://openapi.lingxing.com"
          })
        }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "来源保存失败"));
      setEditor(null);
      await loadOverview();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "来源保存失败");
    } finally {
      setSaving(false);
    }
  };

  const changeSource = async (source: SourceConfiguration, action: "probe" | "disable") => {
    setSaving(true);
    setError(null);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/data-center/sources/${encodeURIComponent(source.system_key)}${action === "probe" ? "/probe" : ""}`,
        {
          method: action === "probe" ? "POST" : "PATCH",
          headers: { "Content-Type": "application/json" },
          body: action === "disable" ? JSON.stringify({ status: "disabled", expected_version: source.version }) : undefined
        }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "来源操作失败"));
      setDisableTarget(null);
      await loadOverview();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "来源操作失败");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="data-source-state" aria-live="polite">
        <Database className="spinning" aria-hidden="true" size={28} />
        <strong>正在汇总数据接入运行状态</strong>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="data-source-state failed" role="alert">
        <AlertTriangle aria-hidden="true" size={30} />
        <strong>数据源运行页暂不可用</strong>
        <span>{error}</span>
        <button className="button secondary" onClick={() => window.location.reload()} type="button">重新连接</button>
      </div>
    );
  }

  const latestSync = overview.latest_sync;
  const latestSource = overview.sources.find((source) => source.key === latestSync?.source_key);
  const largestSourceCount = Math.max(...overview.sources.map((source) => source.source_record_count), 1);
  const sourceTypes = Array.from(new Set(overview.sources.map((source) => source.system_type)));
  const stats = [
    { icon: Link2, label: "已注册来源", value: formatCount(overview.sources.length), unit: "个", note: `${connectedSources} 个在线` },
    { icon: Rows3, label: "原始记录", value: formatCount(overview.source_record_count), unit: "条", note: "来源记录与归档页接收数" },
    { icon: Waypoints, label: "来源资源", value: formatCount(overview.resource_count), unit: "个", note: "已登记资源" },
    { icon: Activity, label: "启用资源", value: formatCount(overview.enabled_resource_count), unit: "个", note: "允许排队执行" },
    { icon: Braces, label: "待确认资源", value: formatCount(overview.pending_resource_count), unit: "个", note: "Schema 待确认" },
    { icon: ServerCog, label: "最近写入", value: formatCount(latestSync?.records_written ?? 0), unit: "条", note: latestSync ? syncStatus(latestSync.status) : "尚无批次" }
  ];

  return (
    <div className="data-source-page">
      <PageHeader
        actions={
          <div className="data-source-actions">
            {can("source.manage") ? <button className="button primary" onClick={() => setEditor({ system_key: "", name: "", business_unit_id: "", credential_ref: "", editing: false })} type="button">新增来源</button> : null}
            <button
              className="button secondary"
              onClick={() => void loadOverview().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "刷新失败"))}
              type="button"
            >
              <RefreshCw aria-hidden="true" size={16} />
              刷新运行状态
            </button>
          </div>
        }
        eyebrow="数据中心"
        meta={`更新 ${formatTime(overview.generated_at)}`}
        title={`${overview.enterprise_name} · 来源治理`}
      />

      {error ? <div className="data-source-error" role="alert"><AlertTriangle size={15} />{error}</div> : null}

      <section className="data-source-stat-grid" aria-label="数据接入统计">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <article key={stat.label}>
              <span><Icon aria-hidden="true" size={17} />{stat.label}</span>
              <strong>{stat.value}<small>{stat.unit}</small></strong>
              <p>{stat.note}</p>
            </article>
          );
        })}
      </section>

      <div className="data-source-layout">
        <section className="data-source-panel source-registry-panel">
          <header><div><h2>来源注册与健康状态</h2></div><em>{connectedSources}/{overview.sources.length} 在线</em></header>
          <div className="table-wrap">
            <table>
              <thead><tr><th>来源</th><th>系统类型</th><th>数据契约</th><th>映射版本</th><th>原始记录</th><th>最后同步</th><th>运行状态</th><th>连接器运行</th></tr></thead>
              <tbody>
                {overview.sources.map((source) => (
                  <tr key={source.key}>
                    <td><strong className="source-name"><span />{source.name}</strong><code>{source.key} · {source.sync_run_count} 批</code></td>
                    <td>{source.system_type}</td>
                    <td>{source.source_schema_version}</td>
                    <td>{source.mapping_version}</td>
                    <td><strong>{formatCount(source.source_record_count)}</strong> 条</td>
                    <td>{formatTime(source.last_sync_at)}</td>
                    <td><StatusBadge value={{ label: sourceStatus(source.status === "disabled" ? source.status : source.connection_status && source.connection_status !== "unknown" ? source.connection_status : source.status), tone: sourceTone(source.status === "disabled" ? source.status : source.connection_status ?? source.status) }} /></td>
                    <td>
                      <button
                        aria-label={`同步${source.name}`}
                        className="source-sync-button"
                        disabled={!can("source.manage") || source.status === "disabled"}
                        onClick={() => setLedger(source)}
                        title={`选择${source.name}同步资源`}
                        type="button"
                      >
                        <Play aria-hidden="true" size={14} />运行
                      </button>
                      {can("source.manage") ? <>
                        <button className="button secondary" onClick={() => setLedger(source)} type="button">资源与归属</button>
                        <button className="button secondary" onClick={() => {
                          const config = configurations.find((item) => item.system_key === source.key);
                          if (config) setEditor({ system_key: config.system_key, name: config.name, business_unit_id: config.business_unit_id ?? "", credential_ref: "", editing: true, expected_version: config.version });
                        }} type="button">编辑</button>
                        <button className="button secondary" disabled={saving} onClick={() => {
                          const config = configurations.find((item) => item.system_key === source.key);
                          if (config) void changeSource(config, "probe");
                        }} type="button">探测</button>
                        <button className="button secondary" disabled={saving || source.status === "disabled"} onClick={() => {
                          const config = configurations.find((item) => item.system_key === source.key);
                          if (config) setDisableTarget(config);
                        }} type="button">停用</button>
                      </> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer><Database aria-hidden="true" size={14} />累计 {formatCount(overview.sources.reduce((total, source) => total + source.sync_run_count, 0))} 个同步批次 · 最近写入 {formatCount(latestSync?.records_written ?? 0)} 条</footer>
        </section>

        <section className="data-source-panel readiness-panel">
          <header><div><h2>来源数据规模</h2></div><em>{formatCount(overview.source_record_count)} 条</em></header>
          <div className="readiness-series">
            {overview.sources.map((source) => {
              const share = overview.source_record_count > 0 ? source.source_record_count / overview.source_record_count : 0;
              return (
                <article key={source.key}>
                  <div><strong>{source.name}</strong><span>{formatCount(source.source_record_count)} 条 · {new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 1 }).format(share)}</span></div>
                  <div className="readiness-track"><i style={{ "--readiness": `${Math.max((source.source_record_count / largestSourceCount) * 100, source.source_record_count > 0 ? 3 : 0)}%` } as CSSProperties} /></div>
                  <p>{source.system_type} · {source.sync_run_count} 个同步批次</p>
                </article>
              );
            })}
          </div>
        </section>

        <section className="data-source-panel sync-run-panel">
          <header><div><h2>最近一次同步链路</h2></div><em>{latestSync ? formatTime(latestSync.started_at) : "暂无运行"}</em></header>
          {latestSync ? (
            <>
              <div className="pipeline-flow">
                <article><span>01</span><div><strong>来源读取</strong><b>{formatCount(latestSync.records_read)} 条</b></div></article>
                <i />
                <article><span>02</span><div><strong>契约映射</strong><b>{latestSource?.mapping_version ?? "未配置"}</b></div></article>
                <i />
                <article><span>03</span><div><strong>持久化写入</strong><b>{formatCount(latestSync.records_written)} 条</b></div></article>
                <i />
                <article><span>04</span><div><strong>批次结果</strong><b>{syncStatus(latestSync.status)}</b></div></article>
              </div>
              <dl className="sync-run-meta">
                <div><dt>同步来源</dt><dd>{latestSource?.name ?? "未知来源"}</dd></div>
                <div><dt>同步批次</dt><dd>{latestSync.id}</dd></div>
                <div><dt>完成时间</dt><dd>{formatTime(latestSync.finished_at)}</dd></div>
                <div><dt>告警 / 错误</dt><dd>{latestSync.error ?? latestSync.warning ?? "无"}</dd></div>
              </dl>
            </>
          ) : <div className="pipeline-empty">暂无同步批次</div>}
        </section>

        <section className="data-source-panel connector-panel">
          <header><div><h2>来源类型分布</h2></div><em>{sourceTypes.length} 类</em></header>
          <div className="connector-grid">
            {sourceTypes.map((sourceType) => {
              const matchedSources = overview.sources.filter((source) => source.system_type === sourceType);
              const recordCount = matchedSources.reduce((total, source) => total + source.source_record_count, 0);
              return <article key={sourceType}><Database aria-hidden="true" size={19} /><div><strong>{sourceType}</strong><span>{matchedSources.map((source) => source.name).join("、")}</span></div><em>{formatCount(recordCount)} 条</em></article>;
            })}
          </div>
        </section>
      </div>
      {editor ? <Dialog busy={saving} onClose={() => setEditor(null)} title={editor.editing ? "编辑来源" : "新增来源"} size="medium" footer={<><button className="button secondary" disabled={saving} onClick={() => setEditor(null)} type="button">取消</button><button className="button primary" disabled={saving || !editor.system_key.trim() || !editor.name.trim()} onClick={() => void saveSource()} type="button">保存</button></>}>
        <div className="platform-form-grid overlay-form-grid">
          <label><span>来源标识</span><input disabled={editor.editing} onChange={(event) => setEditor({ ...editor, system_key: event.target.value })} value={editor.system_key} /></label>
          <label><span>来源名称</span><input onChange={(event) => setEditor({ ...editor, name: event.target.value })} value={editor.name} /></label>
          <label><span>业务单元</span><select onChange={(event) => setEditor({ ...editor, business_unit_id: event.target.value })} value={editor.business_unit_id}><option value="">未分配</option>{scopeOptions?.business_units.filter((unit) => unit.enterprise_id === identity?.enterprise_id).map((unit) => <option key={unit.key} value={unit.key}>{unit.label}</option>)}</select></label>
          <label><span>凭据引用</span><input autoComplete="off" onChange={(event) => setEditor({ ...editor, credential_ref: event.target.value })} value={editor.credential_ref} /></label>
          {error ? <p role="alert">{error}</p> : null}
        </div>
      </Dialog> : null}
      {disableTarget ? <ConfirmDialog busy={saving} confirmLabel="确认停用" description={`停用 ${disableTarget.name}？`} onCancel={() => setDisableTarget(null)} onConfirm={() => void changeSource(disableTarget, "disable")} title="停用来源" tone="danger" /> : null}
      {ledger ? <SourceLedgerDialog sourceKey={ledger.key} name={ledger.name} systemType={ledger.system_type} onClose={() => setLedger(null)} onChanged={loadOverview} /> : null}
    </div>
  );
}
