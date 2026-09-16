"use client";

import { useCallback, useEffect, useId, useState } from "react";

import { ConfirmDialog, Dialog, useNotifications } from "@/components/console/interaction";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

interface Resource { key: string; schedule_strategy: string | null; can_execute: boolean; schedule_parameters: string[]; window_fields: string[]; window_format: string | null; max_window_days: number; validation_status?: string }
interface BackfillConfig {
  name: string; resource_key: string; resource_parameters: Record<string, string>;
  projection_mode: "inline" | "deferred"; status: "paused" | "active";
  window_start: string; window_end: string; partition_days: number; batch_size: number;
}
interface Backfill extends Omit<BackfillConfig, "status"> {
  id: string; status: string; cursor: string; active_run_id: string | null; windows_total: number;
  windows_succeeded: number; windows_no_data: number; windows_with_conflicts: number;
  windows_failed: number; records_read: number; records_written: number;
  error_code: string | null; version: number;
}
interface Coverage {
  id: string; window_start: string; window_end: string; status: string;
  records_read: number; records_written: number; error_code: string | null; attempt_count: number;
}
interface CoveragePage { items: Coverage[]; offset: number; limit: number; total: number }
interface RolloutConfig {
  status: "paused" | "active"; history_start: string; history_end: string; batch_size: number;
}

const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center`;
const displayTime = (value: string) => new Date(value).toLocaleString("zh-CN");
const localTime = (value: string) => {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};
const utcDate = (value: string) => `${value}T00:00:00.000Z`;
const dayAfter = (value: string) => {
  const date = new Date(utcDate(value)); date.setUTCDate(date.getUTCDate() + 1); return date.toISOString();
};
const stateLabel: Record<string, string> = {
  paused: "暂停", active: "执行中", completed: "已覆盖", needs_attention: "待处理",
  queued: "排队", running: "运行中", succeeded: "已采集", no_data: "无数据",
  succeeded_with_conflicts: "已采集 / 待映射", failed: "失败", cancelled: "已取消",
};

export function SourceBackfills({ sourceKey, resources, providerEnabled }: {
  sourceKey: string; resources: Resource[]; providerEnabled: boolean;
}) {
  const base = `${API}/sources/${encodeURIComponent(sourceKey)}/backfills`;
  const formId = useId();
  const rolloutFormId = useId();
  const { notify } = useNotifications();
  const [items, setItems] = useState<Backfill[]>([]);
  const [form, setForm] = useState<BackfillConfig | null>(null);
  const [editing, setEditing] = useState<Backfill | null>(null);
  const [confirm, setConfirm] = useState<Backfill | null>(null);
  const [selected, setSelected] = useState<Backfill | null>(null);
  const [rollout, setRollout] = useState<RolloutConfig | null>(null);
  const [coverage, setCoverage] = useState<CoveragePage>({ items: [], offset: 0, limit: 50, total: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const candidates = resources.filter((item) => item.can_execute
    && (!item.key.startsWith("official_") || item.validation_status === "validated")
    && ["updated_utc", "source_window"].includes(item.schedule_strategy ?? ""));
  const load = useCallback(async () => {
    const response = await apiFetch(base, { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "读取历史回填失败"));
    setItems(await response.json() as Backfill[]); setError(null);
  }, [base]);
  const loadCoverage = useCallback(async (row: Backfill, offset = 0) => {
    const response = await apiFetch(`${base}/${row.id}/windows?offset=${offset}&limit=50`,
                                    { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "读取覆盖窗口失败"));
    setCoverage(await response.json() as CoveragePage); setSelected(row);
  }, [base]);
  useEffect(() => { void load().catch((reason: Error) => setError(reason.message)); }, [load]);
  const save = async (payload: BackfillConfig, row: Backfill | null) => {
    setBusy(true);
    try {
      const response = await apiFetch(row ? `${base}/${row.id}?version=${row.version}` : base, {
        method: row ? "PUT" : "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "保存历史回填失败"));
      setForm(null); setConfirm(null); await load();
      notify({ tone: "success", title: "历史回填计划已保存" });
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "保存失败";
      setError(message); notify({ tone: "error", title: message });
    } finally { setBusy(false); }
  };
  const saveRollout = async () => {
    if (!rollout) return;
    setBusy(true); setError(null);
    try {
      const response = await apiFetch(`${API}/sources/${encodeURIComponent(sourceKey)}/official-rollout/backfills`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...rollout,
          history_start: utcDate(rollout.history_start), history_end: dayAfter(rollout.history_end) }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "生成官方历史回填失败"));
      const result = await response.json() as {
        created_count: number; updated_count: number; unchanged_count: number; planned_window_count: number;
      };
      setRollout(null); await load();
      notify({ tone: "success", title: `官方回填：新增 ${result.created_count}，更新 ${result.updated_count}，保持 ${result.unchanged_count}，共 ${result.planned_window_count} 个窗口` });
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "生成官方历史回填失败";
      setError(message); notify({ tone: "error", title: message });
    } finally { setBusy(false); }
  };
  const editable = (row: Backfill): BackfillConfig => ({
    name: row.name, resource_key: row.resource_key, resource_parameters: row.resource_parameters,
    projection_mode: row.projection_mode, status: row.status === "active" ? "active" : "paused",
    window_start: row.window_start, window_end: row.window_end,
    partition_days: row.partition_days, batch_size: row.batch_size,
  });
  const chosen = form ? candidates.find((item) => item.key === form.resource_key) : null;
  return <>
    <div className="console-toolbar">
      <button className="button primary" type="button" disabled={busy || !candidates.length}
        onClick={() => { const resource = candidates[0]; setEditing(null); setForm({
          name: "", resource_key: resource.key,
          resource_parameters: Object.fromEntries(resource.schedule_parameters.map((key) => [key, ""])),
          projection_mode: "deferred", status: "paused", window_start: "", window_end: "",
          partition_days: resource.window_fields.length === 1 ? 1 : resource.max_window_days,
          batch_size: 16,
        }); }}>新增历史回填</button>
      <button className="button secondary" type="button" disabled={busy || !candidates.some((item) => item.key.startsWith("official_"))}
        onClick={() => setRollout({ status: "paused", history_start: "2025-01-01",
          history_end: new Date().toISOString().slice(0, 10), batch_size: 16 })}>生成官方回填</button>
      <button className="button secondary" type="button"
        onClick={() => void load().catch((reason: Error) => setError(reason.message))}>刷新</button>
    </div>
    {error ? <p role="alert">{error}</p> : null}
    <table><thead><tr><th>计划 / 资源</th><th>状态</th><th>历史区间</th><th>覆盖窗口</th><th>记录</th><th>操作</th></tr></thead>
      <tbody>{items.map((item) => <tr key={item.id}><td>{item.name}<br />{item.resource_key}</td>
        <td>{stateLabel[item.status] ?? item.status}{item.error_code ? <><br /><code>{item.error_code}</code></> : null}</td>
        <td>{displayTime(item.window_start)}<br />至 {displayTime(item.window_end)}<br />水位 {displayTime(item.cursor)}</td>
        <td>{item.windows_succeeded + item.windows_no_data + item.windows_with_conflicts} / {item.windows_total}
          {item.windows_with_conflicts ? <><br />待映射 {item.windows_with_conflicts}</> : null}
          {item.windows_failed ? <><br />失败 {item.windows_failed}</> : null}</td>
        <td>读取 {item.records_read}<br />写入 {item.records_written}</td><td>
          <button className="button secondary" type="button" onClick={() => void loadCoverage(item).catch((reason: Error) => setError(reason.message))}>窗口</button>
          <button className="button secondary" type="button" disabled={busy || !!item.active_run_id || item.status === "completed"}
            onClick={() => { setEditing(item); const value = editable(item); setForm({ ...value,
              window_start: localTime(value.window_start), window_end: localTime(value.window_end) }); }}>编辑</button>
          <button className="button secondary" type="button"
            disabled={busy || !!item.active_run_id || item.status === "completed" || (item.status !== "active" && !providerEnabled)}
            onClick={() => setConfirm(item)}>{item.status === "active" ? "暂停" : "继续"}</button>
        </td></tr>)}{!items.length ? <tr><td colSpan={6}>暂无历史回填计划</td></tr> : null}</tbody></table>
    {selected ? <><h3>{selected.name}：覆盖窗口</h3><table><thead><tr><th>时间窗</th><th>状态</th><th>读取</th><th>写入</th><th>尝试</th></tr></thead>
      <tbody>{coverage.items.map((item) => <tr key={item.id}><td>{displayTime(item.window_start)}<br />至 {displayTime(item.window_end)}</td>
        <td>{stateLabel[item.status] ?? item.status}{item.error_code ? <><br /><code>{item.error_code}</code></> : null}</td>
        <td>{item.records_read}</td><td>{item.records_written}</td><td>{item.attempt_count}</td></tr>)}</tbody></table>
      <div className="console-toolbar"><button className="button secondary" type="button" disabled={coverage.offset === 0}
        onClick={() => void loadCoverage(selected, Math.max(0, coverage.offset - coverage.limit))}>上一页</button>
        <button className="button secondary" type="button" disabled={coverage.offset + coverage.limit >= coverage.total}
          onClick={() => void loadCoverage(selected, coverage.offset + coverage.limit)}>下一页</button></div></> : null}
    {form ? <Dialog title={editing ? "编辑历史回填" : "新增历史回填"} busy={busy}
      onClose={() => setForm(null)} footer={<button className="button primary" type="submit" form={formId} disabled={busy}>保存</button>}>
      <form className="platform-form-grid source-form-grid" id={formId} onSubmit={(event) => { event.preventDefault();
        void save({ ...form,
          window_start: editing?.window_start ?? (chosen?.window_format === "date" ? utcDate(form.window_start) : new Date(form.window_start).toISOString()),
          window_end: editing?.window_end ?? (chosen?.window_format === "date" ? dayAfter(form.window_end) : new Date(form.window_end).toISOString()) }, editing); }}>
        <label>名称<input required maxLength={120} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
        <label>资源<select disabled={!!editing} value={form.resource_key} onChange={(event) => { const resource = candidates.find((item) => item.key === event.target.value)!;
          setForm({ ...form, resource_key: resource.key,
            resource_parameters: Object.fromEntries(resource.schedule_parameters.map((key) => [key, ""])),
            partition_days: resource.window_fields.length === 1 ? 1 : form.partition_days }); }}>
          {candidates.map((item) => <option key={item.key} value={item.key}>{item.key}</option>)}</select></label>
        {chosen?.schedule_parameters.map((key) => <label key={key}>{key}<input required disabled={!!editing}
          value={form.resource_parameters[key] ?? ""} onChange={(event) => setForm({ ...form,
            resource_parameters: { ...form.resource_parameters, [key]: event.target.value } })} /></label>)}
        <label>起点<input type={chosen?.window_format === "date" ? "date" : "datetime-local"} required disabled={!!editing} value={form.window_start}
          onChange={(event) => setForm({ ...form, window_start: event.target.value })} /></label>
        <label>终点<input type={chosen?.window_format === "date" ? "date" : "datetime-local"} required disabled={!!editing} value={form.window_end}
          onChange={(event) => setForm({ ...form, window_end: event.target.value })} /></label>
        <label>单窗天数<input type="number" min={1} max={chosen?.window_fields.length === 1 ? 1 : chosen?.max_window_days ?? 7} required disabled={!!editing || chosen?.window_fields.length === 1} value={form.partition_days}
          onChange={(event) => setForm({ ...form, partition_days: Number(event.target.value) })} /></label>
        <label>每批窗口<input type="number" min={1} max={32} required value={form.batch_size}
          onChange={(event) => setForm({ ...form, batch_size: Number(event.target.value) })} /></label>
      </form>
    </Dialog> : null}
    {rollout ? <Dialog title="生成官方历史回填" busy={busy} onClose={() => setRollout(null)} footer={
      <button className="button primary" type="submit" form={rolloutFormId} disabled={busy}>生成计划</button>}>
      <form className="platform-form-grid source-form-grid" id={rolloutFormId} onSubmit={(event) => { event.preventDefault(); void saveRollout(); }}>
        <label>计划状态<select value={rollout.status} onChange={(event) => setRollout({ ...rollout, status: event.target.value as "paused" | "active" })}>
          <option value="paused">暂停</option><option value="active">启用</option>
        </select></label>
        <label>历史起点<input type="date" required value={rollout.history_start}
          onChange={(event) => setRollout({ ...rollout, history_start: event.target.value })} /></label>
        <label>历史终点<input type="date" required value={rollout.history_end}
          onChange={(event) => setRollout({ ...rollout, history_end: event.target.value })} /></label>
        <label>每批窗口<input type="number" min={1} max={32} required value={rollout.batch_size}
          onChange={(event) => setRollout({ ...rollout, batch_size: Number(event.target.value) })} /></label>
      </form>
    </Dialog> : null}
    {confirm ? <ConfirmDialog title={confirm.status === "active" ? "暂停历史回填" : "继续历史回填"}
      description={`${confirm.name}：${confirm.status === "active" ? "当前批次完成后停止派发" : "从覆盖水位继续派发未完成窗口"}。`}
      busy={busy} onCancel={() => setConfirm(null)} onConfirm={() => void save({ ...editable(confirm),
        status: confirm.status === "active" ? "paused" : "active" }, confirm)} /> : null}
  </>;
}
