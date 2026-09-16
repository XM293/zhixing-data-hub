"use client";

import { useId, useRef, useState } from "react";

import { Dialog, useNotifications } from "@/components/console/interaction";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

interface Resource { key: string; wave: string; can_execute: boolean; required_parameters: string[]; schedule_parameters: string[]; window_fields: string[]; window_format: string | null; max_window_days: number; validation_status?: string }
interface Selection { id: string; resourceKey: string; parameters: Record<string, string>; start: string; end: string }
const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center`;
const parameterLabels: Record<string, string> = {
  start_date: "来源开始日期", end_date: "来源结束日期", enabled: "启用状态",
  isAuth: "授权状态", payMethod: "结算方式",
};
function utcDate(value: string) { return `${value}T00:00:00.000Z`; }
function dayAfter(value: string) {
  const date = new Date(utcDate(value)); date.setUTCDate(date.getUTCDate() + 1); return date.toISOString();
}
function syncWindow(resource: Resource, row: Selection) {
  if (!resource.window_fields.length) return { window_start: null, window_end: null };
  if (!row.start || (resource.window_fields.length === 2 && !row.end)) {
    throw new Error(`${resource.key} 需要完整时间范围`);
  }
  if (resource.window_format === "date") return {
    window_start: utcDate(row.start),
    window_end: dayAfter(resource.window_fields.length === 1 ? row.start : row.end),
  };
  if (resource.window_fields.length === 1) {
    const lower = new Date(row.start); const upper = new Date(lower);
    upper.setUTCDate(upper.getUTCDate() + 1);
    return { window_start: lower.toISOString(), window_end: upper.toISOString() };
  }
  const start = new Date(row.start); const end = new Date(row.end);
  if (end <= start) throw new Error(`${resource.key} 结束时间必须晚于开始时间`);
  return { window_start: start.toISOString(), window_end: end.toISOString() };
}

export function SourceBatchImport({ sourceKey, resources, providerEnabled, onChanged }: {
  sourceKey: string; resources: Resource[]; providerEnabled: boolean; onChanged: () => Promise<void>;
}) {
  const { notify } = useNotifications();
  const formId = useId();
  const [rows, setRows] = useState<Selection[] | null>(null);
  const [partitionDays, setPartitionDays] = useState(7);
  const [projectionMode, setProjectionMode] = useState("deferred");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const command = useRef<{ signature: string; key: string } | null>(null);
  const candidates = resources.filter((item) => item.can_execute
    && (!item.key.startsWith("official_") || item.validation_status === "validated"));
  const newRow = (): Selection => ({ id: crypto.randomUUID(), resourceKey: candidates[0]?.key ?? "", parameters: {}, start: "", end: "" });
  const update = (id: string, patch: Partial<Selection>) => setRows((current) => current?.map((row) => row.id === id ? { ...row, ...patch } : row) ?? null);
  const submit = async () => {
    if (!rows?.length) return;
    setBusy(true); setError(null);
    try {
      const selections = rows.map((row) => {
        const resource = candidates.find((item) => item.key === row.resourceKey);
        if (!resource) throw new Error("资源已停用，请刷新后重试");
        if (resource.schedule_parameters.some((key) => !row.parameters[key])) throw new Error(`${resource.key} 缺少查询参数`);
        return { resource_key: row.resourceKey, resource_parameters: row.parameters,
          ...syncWindow(resource, row) };
      });
      const singleDate = rows.some((row) => candidates.find((item) => item.key === row.resourceKey)?.window_fields.length === 1);
      const body = { selections, partition_days: singleDate ? 1 : partitionDays, projection_mode: projectionMode };
      const signature = JSON.stringify(body);
      if (command.current?.signature !== signature) command.current = { signature, key: crypto.randomUUID() };
      const response = await apiFetch(`${API}/sources/${encodeURIComponent(sourceKey)}/imports`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, client_request_key: command.current.key }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "批量导入入队失败"));
      const result = await response.json() as { partitions: number };
      setRows(null); notify({ tone: "success", title: `已提交 ${result.partitions} 个导入分区` });
      try { await onChanged(); } catch { notify({ tone: "error", title: "导入已提交，刷新运行列表失败" }); }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "批量导入入队失败";
      setError(message); notify({ tone: "error", title: message });
    } finally { setBusy(false); }
  };
  return <>
    <button className="button secondary" type="button" disabled={busy || !providerEnabled || !candidates.length}
      onClick={() => { setRows([newRow()]); setError(null); command.current = null; }}>批量导入</button>
    {rows ? <Dialog title="批量导入" size="large" busy={busy} onClose={() => setRows(null)} footer={<>
      <button type="button" className="button secondary" disabled={busy || rows.length >= 32} onClick={() => setRows([...rows, newRow()])}>添加资源</button>
      <button type="submit" form={formId} className="button primary" disabled={busy || !rows.length}>加入同步队列</button>
    </>}>
      {error ? <p role="alert">{error}</p> : null}
      <form id={formId} onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <label>处理方式<select value={projectionMode} onChange={(event) => setProjectionMode(event.target.value)}>
          <option value="deferred">镜像采集 / 独立映射</option><option value="inline">采集并映射</option>
        </select></label>
        <div className="platform-form-grid source-form-grid"><label>时间分区天数<input type="number" min={1} max={7} required value={partitionDays} onChange={(event) => setPartitionDays(Number(event.target.value))} /></label></div>
        {rows.map((row, index) => <fieldset className="source-import-row" key={row.id}>
          <legend>资源 {index + 1}</legend>
          <div className="platform-form-grid source-form-grid">
            <label>资源<select aria-label={`导入资源 ${index + 1}`} value={row.resourceKey} required onChange={(event) => update(row.id, { resourceKey: event.target.value, parameters: {}, start: "", end: "" })}>
              {candidates.map((item) => <option key={item.key} value={item.key}>{item.wave} · {item.key}</option>)}
            </select></label>
            {(() => { const resource = candidates.find((item) => item.key === row.resourceKey); return resource?.window_fields.length ? <>
              <label>{resource.window_fields.length === 1 ? "业务日期" : "开始"}<input type={resource.window_format === "date" ? "date" : "datetime-local"} required value={row.start} onChange={(event) => update(row.id, { start: event.target.value })} /></label>
              {resource.window_fields.length === 2 ? <label>结束<input type={resource.window_format === "date" ? "date" : "datetime-local"} required value={row.end} onChange={(event) => update(row.id, { end: event.target.value })} /></label> : null}
            </> : null; })()}
            {candidates.find((item) => item.key === row.resourceKey)?.schedule_parameters.map((key) => <label key={key}>{parameterLabels[key] ?? key}<input required type="text" value={row.parameters[key] ?? ""} onChange={(event) => update(row.id, { parameters: { ...row.parameters, [key]: event.target.value } })} /></label>)}
          </div>
          <button type="button" className="button secondary" disabled={busy} onClick={() => setRows(rows.filter((item) => item.id !== row.id))}>移除资源 {index + 1}</button>
        </fieldset>)}
      </form>
    </Dialog> : null}
  </>;
}
