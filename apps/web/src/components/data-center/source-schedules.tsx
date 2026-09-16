"use client";

import { useCallback, useEffect, useId, useState } from "react";

import { ConfirmDialog, Dialog, useNotifications } from "@/components/console/interaction";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

interface Config {
  projection_mode: string;
  name: string; resource_key: string; strategy: string; status: string;
  resource_parameters: Record<string, string>;
  interval_seconds: number; overlap_seconds: number; safety_lag_seconds: number;
  reconcile_days: number; initial_start: string | null;
}
interface Schedule extends Config {
  id: string; version: number; watermark: string | null; next_run_at: string;
  last_success_at: string | null; active_run_id: string | null; error_code: string | null;
}
interface Resource { key: string; schedule_strategy: string | null; can_execute: boolean; schedule_parameters: string[]; validation_status?: string }
interface RolloutConfig {
  status: "paused" | "active"; incremental_start: string;
  window_interval_seconds: number; snapshot_interval_seconds: number;
  overlap_seconds: number; safety_lag_seconds: number; reconcile_days: number;
}
const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center`;
const displayTime = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN") : "—";
function localTime(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
function config(row: Schedule): Config {
  return { name: row.name, projection_mode: row.projection_mode, resource_key: row.resource_key, strategy: row.strategy,
    resource_parameters: row.resource_parameters,
    status: row.status === "active" ? "active" : "paused", interval_seconds: row.interval_seconds,
    overlap_seconds: row.overlap_seconds, safety_lag_seconds: row.safety_lag_seconds,
    reconcile_days: row.reconcile_days, initial_start: row.initial_start };
}

export function SourceSchedules({ sourceKey, resources, providerEnabled }: {
  sourceKey: string; resources: Resource[]; providerEnabled: boolean;
}) {
  const base = `${API}/sources/${encodeURIComponent(sourceKey)}/schedules`;
  const { notify } = useNotifications();
  const formId = useId();
  const rolloutFormId = useId();
  const [items, setItems] = useState<Schedule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<Config | null>(null);
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [confirm, setConfirm] = useState<Schedule | null>(null);
  const [rollout, setRollout] = useState<RolloutConfig | null>(null);
  const [start, setStart] = useState("");
  const load = useCallback(async () => {
    const response = await apiFetch(base, { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "读取采集计划失败"));
    setItems(await response.json() as Schedule[]); setError(null);
  }, [base]);
  useEffect(() => { void load().catch((reason: Error) => setError(reason.message)); }, [load]);
  const save = async (payload: Config, row: Schedule | null) => {
    setBusy(true);
    try {
      const response = await apiFetch(row ? `${base}/${row.id}?version=${row.version}` : base,
        { method: row ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "保存采集计划失败"));
      setForm(null); setConfirm(null); await load(); notify({ tone: "success", title: "采集计划已保存" });
    } catch (reason) { const message = reason instanceof Error ? reason.message : "保存失败";
      setError(message); notify({ tone: "error", title: message }); }
    finally { setBusy(false); }
  };
  const candidates = resources.filter((item) => item.schedule_strategy && item.can_execute
    && (!item.key.startsWith("official_") || item.validation_status === "validated"));
  const officialCandidates = candidates.filter((item) => item.key.startsWith("official_"));
  const selected = form ? candidates.find((item) => item.key === form.resource_key) : null;
  const saveRollout = async () => {
    if (!rollout) return;
    setBusy(true); setError(null);
    try {
      const response = await apiFetch(`${API}/sources/${encodeURIComponent(sourceKey)}/official-rollout/schedules`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...rollout, incremental_start: new Date(rollout.incremental_start).toISOString() }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "生成官方采集计划失败"));
      const result = await response.json() as { created_count: number; updated_count: number; unchanged_count: number };
      setRollout(null); await load();
      notify({ tone: "success", title: `官方计划：新增 ${result.created_count}，更新 ${result.updated_count}，保持 ${result.unchanged_count}` });
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "生成官方采集计划失败";
      setError(message); notify({ tone: "error", title: message });
    } finally { setBusy(false); }
  };
  return <>
    <div className="console-toolbar">
      <button className="button primary" type="button" disabled={busy || !candidates.length} onClick={() => {
        const resource = candidates[0]; setEditing(null); setStart("");
        setForm({ name: "", projection_mode: "deferred", resource_key: resource.key, strategy: resource.schedule_strategy!, status: "paused",
          resource_parameters: Object.fromEntries(resource.schedule_parameters.map((key) => [key, ""])),
          interval_seconds: 300, overlap_seconds: 300, safety_lag_seconds: 120, reconcile_days: 7, initial_start: null });
      }}>新增采集计划</button>
      <button className="button secondary" type="button" disabled={busy || !officialCandidates.length}
        onClick={() => { const start = new Date(); start.setDate(start.getDate() - 1); setRollout({
          status: "paused", incremental_start: localTime(start.toISOString()),
          window_interval_seconds: 3600, snapshot_interval_seconds: 86400,
          overlap_seconds: 300, safety_lag_seconds: 300, reconcile_days: 7,
        }); }}>生成官方计划</button>
      <button className="button secondary" type="button" onClick={() => void load().catch((reason: Error) => setError(reason.message))}>刷新</button>
    </div>
    {error ? <p role="alert">{error}</p> : null}
    <table><thead><tr><th>计划 / 资源</th><th>状态</th><th>频率</th><th>已完成水位</th><th>最近成功</th><th>下次检查</th><th>操作</th></tr></thead>
      <tbody>{items.map((item) => <tr key={item.id}><td>{item.name}<br />{item.resource_key}</td>
        <td>{item.status === "active" ? "启用" : item.status === "paused" ? "暂停" : "待处理"}{item.error_code ? <><br /><code>{item.error_code}</code></> : null}</td>
        <td>{item.interval_seconds} 秒</td><td>{displayTime(item.watermark)}</td><td>{displayTime(item.last_success_at)}</td>
        <td>{item.status === "active" ? displayTime(item.next_run_at) : "—"}</td><td>
          <button className="button secondary" type="button" disabled={busy || !!item.active_run_id} onClick={() => { setEditing(item); setForm(config(item)); setStart(localTime(item.initial_start)); }}>编辑</button>
          <button className="button secondary" type="button" disabled={busy || !!item.active_run_id || (item.status !== "active" && !providerEnabled)} onClick={() => setConfirm(item)}>{item.status === "active" ? "暂停" : "启用"}</button>
        </td></tr>)}{!items.length ? <tr><td colSpan={7}>暂无采集计划</td></tr> : null}</tbody></table>
    {form ? <Dialog title={editing ? "编辑采集计划" : "新增采集计划"} busy={busy} onClose={() => setForm(null)} footer={
      <button className="button primary" type="submit" form={formId} disabled={busy}>保存</button>}>
      <form className="platform-form-grid source-form-grid" id={formId} onSubmit={(event) => { event.preventDefault(); void save({ ...form,
        initial_start: form.strategy !== "snapshot" ? (editing?.initial_start ?? new Date(start).toISOString()) : null }, editing); }}>
        <label>名称<input value={form.name} maxLength={120} required onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label>处理方式<select value={form.projection_mode} onChange={(e) => setForm({ ...form, projection_mode: e.target.value })}>
          <option value="deferred">镜像采集 / 独立映射</option><option value="inline">采集并映射</option>
        </select></label>
        <label>资源<select value={form.resource_key} disabled={!!editing} onChange={(e) => {
          const resource = candidates.find((item) => item.key === e.target.value)!;
          setForm({ ...form, resource_key: resource.key, strategy: resource.schedule_strategy!,
            resource_parameters: Object.fromEntries(resource.schedule_parameters.map((key) => [key, ""])) });
        }}>{candidates.map((item) => <option key={item.key} value={item.key}>{item.key}</option>)}</select></label>
        {selected?.schedule_parameters.map((key) => <label key={key}>{key}<input required
          value={form.resource_parameters[key] ?? ""} onChange={(event) => setForm({ ...form,
            resource_parameters: { ...form.resource_parameters, [key]: event.target.value } })} /></label>)}
        <label>采集频率（秒）<input type="number" min={60} max={86400} required value={form.interval_seconds} onChange={(e) => setForm({ ...form, interval_seconds: Number(e.target.value) })} /></label>
        {form.strategy !== "snapshot" ? <>
          <label>采集起点<input type="datetime-local" required disabled={!!editing} value={start} onChange={(e) => setStart(e.target.value)} /></label>
          <label>重叠窗口（秒）<input type="number" min={1} max={86400} required value={form.overlap_seconds} onChange={(e) => setForm({ ...form, overlap_seconds: Number(e.target.value) })} /></label>
          <label>安全延迟（秒）<input type="number" min={0} max={3600} required value={form.safety_lag_seconds} onChange={(e) => setForm({ ...form, safety_lag_seconds: Number(e.target.value) })} /></label>
          <label>每日回看（天）<input type="number" min={1} max={30} required value={form.reconcile_days} onChange={(e) => setForm({ ...form, reconcile_days: Number(e.target.value) })} /></label>
        </> : null}
      </form>
    </Dialog> : null}
    {rollout ? <Dialog title="生成官方采集计划" busy={busy} onClose={() => setRollout(null)} footer={
      <button className="button primary" type="submit" form={rolloutFormId} disabled={busy}>生成计划</button>}>
      <form className="platform-form-grid source-form-grid" id={rolloutFormId} onSubmit={(event) => { event.preventDefault(); void saveRollout(); }}>
        <label>计划状态<select value={rollout.status} onChange={(event) => setRollout({ ...rollout, status: event.target.value as "paused" | "active" })}>
          <option value="paused">暂停</option><option value="active">启用</option>
        </select></label>
        <label>增量起点<input type="datetime-local" required value={rollout.incremental_start} onChange={(event) => setRollout({ ...rollout, incremental_start: event.target.value })} /></label>
        <label>窗口频率（秒）<input type="number" min={60} max={86400} required value={rollout.window_interval_seconds} onChange={(event) => setRollout({ ...rollout, window_interval_seconds: Number(event.target.value) })} /></label>
        <label>快照频率（秒）<input type="number" min={60} max={86400} required value={rollout.snapshot_interval_seconds} onChange={(event) => setRollout({ ...rollout, snapshot_interval_seconds: Number(event.target.value) })} /></label>
        <label>重叠窗口（秒）<input type="number" min={1} max={86400} required value={rollout.overlap_seconds} onChange={(event) => setRollout({ ...rollout, overlap_seconds: Number(event.target.value) })} /></label>
        <label>安全延迟（秒）<input type="number" min={0} max={3600} required value={rollout.safety_lag_seconds} onChange={(event) => setRollout({ ...rollout, safety_lag_seconds: Number(event.target.value) })} /></label>
        <label>每日回看（天）<input type="number" min={1} max={30} required value={rollout.reconcile_days} onChange={(event) => setRollout({ ...rollout, reconcile_days: Number(event.target.value) })} /></label>
      </form>
    </Dialog> : null}
    {confirm ? <ConfirmDialog title={confirm.status === "active" ? "暂停采集" : "启用采集"}
      description={`${confirm.name}：${confirm.status === "active" ? "停止产生新采集批次" : `每 ${confirm.interval_seconds} 秒检查并导入来源数据`}。`}
      busy={busy} onCancel={() => setConfirm(null)} onConfirm={() => void save({ ...config(confirm), status: confirm.status === "active" ? "paused" : "active" }, confirm)} /> : null}
  </>;
}
