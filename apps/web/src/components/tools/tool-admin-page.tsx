"use client";

import {
  Activity,
  Braces,
  CircleAlert,
  Gauge,
  KeyRound,
  LoaderCircle,
  PlugZap,
  RefreshCw,
  ShieldCheck
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type { ToolAdminOverview, ToolDefinition } from "@/lib/tool-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function ToolAdminPage() {
  const { roleId } = useExperience();
  const [data, setData] = useState<ToolAdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/tools/admin/overview`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取企业工具注册表"));
    setData((await response.json()) as ToolAdminOverview);
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "企业工具网关连接失败"))
      .finally(() => setLoading(false));
  }, [load]);

  if (loading) return <ToolState title="正在读取工具 Schema 与调用审计" />;
  if (!data) return <ToolState error title={error ?? "企业工具注册表暂不可用"} />;

  return <div className="identity-admin-page tool-admin-page">
    <PageHeader
      actions={<button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新注册表</button>}
      eyebrow="工具治理"
      meta={`schema ${data.schema_version}`}
      title="企业工具与 MCP 注册表"
    />
    {error ? <InlineCallout description={error} title="最近一次刷新失败" tone="critical" /> : null}
    <ToolStats data={data} />
    <ToolRegistry tools={data.tools} />
    <ToolInvocationLedger data={data} />
  </div>;
}

function ToolStats({ data }: { data: ToolAdminOverview }) {
  const items = [
    ["生效工具", data.stats.active_tools, <PlugZap key="active" size={16} />],
    ["R0 查询", data.stats.r0_tools, <ShieldCheck key="r0" size={16} />],
    ["累计调用", data.stats.invocations, <Activity key="invocations" size={16} />],
    ["成功", data.stats.succeeded, <Gauge key="success" size={16} />],
    ["范围拒绝", data.stats.denied, <KeyRound key="denied" size={16} />],
    ["执行失败", data.stats.failed, <CircleAlert key="failed" size={16} />]
  ];
  return <section className="identity-stat-band" aria-label="企业工具统计">
    {items.map(([label, value, icon]) => <article key={String(label)}><span>{icon}{label}</span><strong>{value}</strong></article>)}
  </section>;
}

function ToolRegistry({ tools }: { tools: ToolDefinition[] }) {
  return <section className="identity-data-panel tool-registry-panel">
    <header><div><span>SCHEMA / RISK / PERMISSION / SCOPE</span><h2>已发布工具定义</h2></div><em>{tools.length} 个数据库版本</em></header>
    <div className="tool-registry-grid">
      {tools.map((tool) => <article key={`${tool.key}@${tool.version}`}>
        <header><span><Braces size={17} /></span><div><small>{tool.key} · v{tool.version}</small><h3>{tool.display_name}</h3></div><StatusBadge value={{ label: tool.risk_level, tone: tool.risk_level === "R0" ? "positive" : "warning" }} /></header>
        <p>{tool.description}</p>
        <dl><div><dt>权限键</dt><dd><code>{tool.permission_key}</code></dd></div><div><dt>范围解析</dt><dd><code>{tool.scope_resolver}</code></dd></div><div><dt>提供者</dt><dd>{tool.provider}</dd></div><div><dt>超时</dt><dd>{tool.timeout_seconds}s</dd></div></dl>
        <div className="tool-schema-keys"><span>输入字段</span>{schemaKeys(tool).map((key) => <code key={key}>{key}</code>)}</div>
      </article>)}
    </div>
  </section>;
}

function ToolInvocationLedger({ data }: { data: ToolAdminOverview }) {
  return <section className="identity-data-panel tool-invocation-panel">
    <header><div><span>TOOL INVOCATION LEDGER</span><h2>最近工具调用</h2></div><em>{data.recent_invocations.length} 条数据库记录</em></header>
    {data.recent_invocations.length === 0 ? <div className="tool-empty-state"><Activity size={21} /><span>暂无调用记录</span></div> : <div className="identity-table-wrap"><table><thead><tr><th>工具 / 主体</th><th>权限与风险</th><th>状态</th><th>输出摘要</th><th>耗时</th><th>追踪</th></tr></thead><tbody>
      {data.recent_invocations.map((item) => <tr key={item.id}>
        <td><strong>{item.tool_key}</strong><small>{item.actor_name} · {item.authentication_method} · v{item.tool_version}</small></td>
        <td><code>{item.permission_key}</code><small>{item.risk_level}</small></td>
        <td><StatusBadge value={{ label: statusLabel(item.status), tone: item.status === "succeeded" ? "positive" : item.status === "denied" ? "critical" : "warning" }} />{item.error_code ? <small>{item.error_code}</small> : null}</td>
        <td><strong>{String(item.output_summary.item_count ?? 0)} 条结果</strong><small>{String(item.output_summary.serialized_bytes ?? 0)} bytes</small></td>
        <td><strong>{item.duration_ms} ms</strong><small>{formatTime(item.started_at)}</small></td>
        <td><small>{item.request_id}</small><small>{item.run_id}</small>{item.agent_run_id ? <small>{item.agent_run_id}</small> : null}</td>
      </tr>)}
    </tbody></table></div>}
  </section>;
}

function schemaKeys(tool: ToolDefinition): string[] {
  const properties = tool.input_schema.properties;
  if (!properties || typeof properties !== "object" || Array.isArray(properties)) return [];
  return Object.keys(properties);
}

function statusLabel(status: "succeeded" | "denied" | "failed"): string {
  if (status === "succeeded") return "成功";
  if (status === "denied") return "已拒绝";
  return "失败";
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(value));
}

function ToolState({ error = false, title }: { error?: boolean; title: string }) {
  return <div className={`identity-page-state ${error ? "error" : ""}`}>{error ? <CircleAlert size={27} /> : <LoaderCircle className="spinning" size={27} />}<strong>{title}</strong></div>;
}
