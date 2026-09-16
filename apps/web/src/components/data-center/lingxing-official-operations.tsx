"use client";

import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog, useNotifications } from "@/components/console/interaction";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center`;
const LIMIT = 50;

interface Operation {
  id: string;
  title: string;
  documentation_url: string;
  method: "GET" | "POST";
  path: string;
  wave: string;
  execution_status: string;
  schema_status: string;
  resource_keys: string[];
  contract_status: string;
  required_fields: string[];
  scope_fields: string[];
  pagination_mode: string;
  window_fields: string[];
  raw_eligible: boolean;
  registered: boolean;
}

interface RegistryPage {
  summary: {
    official_read_operations: number;
    runtime_operations: number;
    runtime_resources: number;
    metadata_only_operations: number;
    source_enabled_runtime_resources: number;
  };
  page: { offset: number; limit: number; total: number };
  items: Operation[];
}

const executionLabels: Record<string, string> = {
  metadata_only: "待协议审核",
  runtime_raw_only: "可采集 Raw",
  runtime_projectable: "可规范映射"
};

export function LingxingOfficialOperations({ sourceKey, onChanged }: {
  sourceKey: string; onChanged?: () => Promise<void>;
}) {
  const { notify } = useNotifications();
  const [payload, setPayload] = useState<RegistryPage | null>(null);
  const [wave, setWave] = useState("");
  const [execution, setExecution] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [registering, setRegistering] = useState<string | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ offset: String(offset), limit: String(LIMIT) });
      if (wave) params.set("wave", wave);
      if (execution) params.set("execution_status", execution);
      if (query.trim()) params.set("query", query.trim());
      const response = await apiFetch(
        `${API}/sources/${encodeURIComponent(sourceKey)}/official-operations?${params}`,
        { cache: "no-store" }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "官方接口目录读取失败"));
      setPayload(await response.json() as RegistryPage);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "官方接口目录读取失败");
    } finally {
      setLoading(false);
    }
  }, [execution, offset, query, sourceKey, wave]);
  useEffect(() => { void load(); }, [load]);
  const register = async (item?: Operation) => {
    const identity = item?.id ?? "all";
    setRegistering(identity); setError(null);
    try {
      const path = item
        ? `${API}/sources/${encodeURIComponent(sourceKey)}/official-operations/${encodeURIComponent(item.id)}/resource`
        : `${API}/sources/${encodeURIComponent(sourceKey)}/official-resources/materialize`;
      const response = await apiFetch(path, item ? {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: false }),
      } : { method: "PUT" });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "官方资源登记失败"));
      await response.json();
      await load();
      await onChanged?.();
      notify({ tone: "success", title: item ? "Raw 资源已登记" : "可控 Raw 资源已全部登记" });
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "官方资源登记失败";
      setError(message); notify({ tone: "error", title: message });
    } finally { setRegistering(null); setConfirmAll(false); }
  };

  return <><div className="source-official-operations">
    <div className="console-toolbar">
      <select aria-label="波次" value={wave} onChange={(event) => { setWave(event.target.value); setOffset(0); }}>
        <option value="">全部波次</option>
        {Array.from({ length: 9 }, (_, index) => <option key={index} value={`W${index}`}>W{index}</option>)}
      </select>
      <select aria-label="执行状态" value={execution} onChange={(event) => { setExecution(event.target.value); setOffset(0); }}>
        <option value="">全部状态</option>
        <option value="runtime_projectable">可规范映射</option>
        <option value="runtime_raw_only">可采集 Raw</option>
        <option value="metadata_only">待协议审核</option>
      </select>
      <input aria-label="接口搜索" value={query} onChange={(event) => { setQuery(event.target.value); setOffset(0); }} placeholder="接口名称或路径" />
      <button className="button secondary" disabled={loading} onClick={() => void load()} type="button">刷新</button>
      <button className="button secondary" disabled={loading || registering !== null}
        onClick={() => setConfirmAll(true)} type="button">登记全部可控 Raw 资源</button>
    </div>
    {error ? <p role="alert">{error}</p> : null}
    {payload ? <>
      <div className="console-toolbar">
        <span className="badge">官方只读候选 {payload.summary.official_read_operations}</span>
        <span className="badge">运行时操作 {payload.summary.runtime_operations}</span>
        <span className="badge">运行时资源 {payload.summary.runtime_resources}</span>
        <span className="badge">当前来源已启用 {payload.summary.source_enabled_runtime_resources}</span>
        <span className="badge">待协议审核 {payload.summary.metadata_only_operations}</span>
      </div>
      <table><thead><tr><th>接口</th><th>波次</th><th>协议状态</th><th>范围 / 窗口</th><th>运行时资源</th><th>操作</th></tr></thead><tbody>
        {payload.items.map((item) => <tr key={item.id}>
          <td><a href={item.documentation_url} rel="noreferrer" target="_blank">{item.title}</a><br /><code>{item.method} {item.path}</code></td>
          <td>{item.wave}</td>
          <td>{executionLabels[item.execution_status] ?? item.execution_status}</td>
          <td>{item.scope_fields.length ? item.scope_fields.join("、") : "—"}<br />
            <small>{item.window_fields.length ? item.window_fields.join(" → ") : item.pagination_mode}</small></td>
          <td>{item.resource_keys.length ? item.resource_keys.join("、") : "—"}</td>
          <td>{item.raw_eligible && !item.registered ? <button className="button secondary"
            disabled={registering !== null} onClick={() => void register(item)} type="button">
              {registering === item.id ? "登记中" : "登记 Raw 资源"}</button>
            : item.registered ? "已登记" : "—"}</td>
        </tr>)}
        {!payload.items.length ? <tr><td colSpan={6}>暂无匹配接口</td></tr> : null}
      </tbody></table>
      <div className="console-toolbar">
        <button className="button secondary" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))} type="button">上一页</button>
        <span>{payload.page.total ? `${offset + 1}-${Math.min(offset + LIMIT, payload.page.total)} / ${payload.page.total}` : "0 / 0"}</span>
        <button className="button secondary" disabled={loading || offset + LIMIT >= payload.page.total} onClick={() => setOffset(offset + LIMIT)} type="button">下一页</button>
      </div>
    </> : null}
  </div>
    {confirmAll ? <ConfirmDialog title="登记全部可控 Raw 资源"
      description="把已确认分页、响应路径和店铺或仓库范围的官方只读接口登记到当前来源，初始保持停用。"
      busy={registering !== null} onCancel={() => setConfirmAll(false)}
      onConfirm={() => void register()} /> : null}
  </>;
}
