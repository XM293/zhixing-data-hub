"use client";

import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog, Dialog, useNotifications } from "@/components/console/interaction";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import { SourceSchedules } from "./source-schedules";
import { SourceBackfills } from "./source-backfills";
import { SourceConflicts } from "./source-conflicts";
import { SourceAuthority } from "./source-authority";
import { SourceBatchImport } from "./source-batch-import";
import { SourceMirrorPages } from "./source-mirror-pages";
import { LingxingOfficialOperations } from "./lingxing-official-operations";

const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center`;
const BINDING_LIMIT = 100;
const CHECKPOINT_LIMIT = 50;
const RUN_LIMIT = 50;
interface Resource { key: string; wave: string; status: string; schema_status: string; schema_confirmation_available: boolean; enabled: boolean; path: string; read_only: boolean; projectable: boolean; can_execute: boolean; execution_mode: string; schedule_strategy: string | null; fact_family: string | null; required_parameters: string[]; schedule_parameters: string[]; window_fields: string[]; window_format: string | null; max_window_days: number; retention_days: number | null; validation_status: string; validation_run_id: string | null; validation_error_code: string | null; last_validated_at: string | null }
interface Checkpoint { resource_key: string; partition_key: string; cursor: string | null; page_number: number | null; records_read: number | null; updated_at: string | null; status: string }
interface CheckpointPage { page: { offset: number; limit: number; total: number }; items: Checkpoint[] }
interface Binding { id: string; external_key: string; canonical_id: string; canonical_type: string; business_unit_id: string | null; status: string; suggested_business_unit_id: string | null; suggestion_reason: string | null; suggestion_evidence_count: number }
interface BindingPage { page: { offset: number; limit: number; total: number }; items: Binding[] }
interface Run { id: string; source_key: string; source_version: number | null; status: string; records_read: number; records_written: number }
interface Child { id: string; resource_key: string; partition_key: string; status: string; records_read: number; records_written: number; error_code: string | null }
interface Manifest { id: string; resource_key: string; page_number: number | null; content_hash: string; row_count: number; bytes: number; schema_status: string; fetched_at: string | null; mapping_version: string; replay_eligible: boolean }

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await apiFetch(`${API}${path}`, { method, cache: "no-store",
    headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) throw new Error(await apiErrorMessage(response, "来源操作失败"));
  return response.json() as Promise<T>;
}

function time(value: string | null) { return value ? new Date(value).toLocaleString("zh-CN") : "—"; }
function utcDate(value: string) { return `${value}T00:00:00.000Z`; }
function dayAfter(value: string) {
  const date = new Date(utcDate(value)); date.setUTCDate(date.getUTCDate() + 1); return date.toISOString();
}
function syncWindow(resource: Resource, start: string, end: string) {
  if (!resource.window_fields.length) return { window_start: null, window_end: null };
  if (resource.window_format === "date") return {
    window_start: utcDate(start),
    window_end: dayAfter(resource.window_fields.length === 1 ? start : end),
  };
  if (resource.window_fields.length === 1) {
    const lower = new Date(start); const upper = new Date(lower); upper.setUTCDate(upper.getUTCDate() + 1);
    return { window_start: lower.toISOString(), window_end: upper.toISOString() };
  }
  return { window_start: new Date(start).toISOString(), window_end: new Date(end).toISOString() };
}

export function SourceLedgerDialog({ sourceKey, name, systemType, onClose, onChanged }: {
  sourceKey: string; name: string; systemType: string; onClose: () => void; onChanged: () => Promise<void>;
}) {
  const { scopeOptions, scopeContext, identity, refreshScope } = useExperience();
  const { notify } = useNotifications();
  const base = `/sources/${encodeURIComponent(sourceKey)}`;
  const [resources, setResources] = useState<Resource[]>([]);
  const [providerEnabled, setProviderEnabled] = useState(false);
  const [catalogVersion, setCatalogVersion] = useState("");
  const [confirmSchema, setConfirmSchema] = useState<{ resource: Resource; version: string } | null>(null);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [checkpointTotal, setCheckpointTotal] = useState(0);
  const [checkpointOffset, setCheckpointOffset] = useState(0);
  const [checkpointResource, setCheckpointResource] = useState("");
  const [checkpointStatus, setCheckpointStatus] = useState("");
  const [checkpointQuery, setCheckpointQuery] = useState("");
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [bindingTotal, setBindingTotal] = useState(0);
  const [bindingOffset, setBindingOffset] = useState(0);
  const [bindingType, setBindingType] = useState("");
  const [bindingStatus, setBindingStatus] = useState("");
  const [bindingSuggestionsOnly, setBindingSuggestionsOnly] = useState(false);
  const [bindingQuery, setBindingQuery] = useState("");
  const [runs, setRuns] = useState<Run[]>([]);
  const [runTotal, setRunTotal] = useState(0);
  const [runOffset, setRunOffset] = useState(0);
  const [runStatus, setRunStatus] = useState("");
  const [runQuery, setRunQuery] = useState("");
  const [children, setChildren] = useState<Child[]>([]);
  const [manifests, setManifests] = useState<Manifest[]>([]);
  const [activeRun, setActiveRun] = useState<string | null>(null);
  const [tab, setTab] = useState("resources");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<Binding | null>(null);
  const [review, setReview] = useState<"approved" | "rejected" | null>(null);
  const [unit, setUnit] = useState("");
  const [timezone, setTimezone] = useState("");
  const [sync, setSync] = useState<Resource | null>(null);
  const [validating, setValidating] = useState(false);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [parameters, setParameters] = useState<Record<string, string>>({});
  const [cancel, setCancel] = useState<Run | null>(null);
  const [disable, setDisable] = useState<Resource | null>(null);
  const [replay, setReplay] = useState<{ manifest: Manifest; requestKey: string } | null>(null);
  const load = useCallback(async () => {
    const rs = await request<{ items: (Resource & { schema_confirmation_available: boolean })[]; provider_enabled: boolean; catalog_version: string }>(`${base}/resources`);
    setResources(rs.items); setCatalogVersion(rs.catalog_version); setProviderEnabled(rs.provider_enabled);
  }, [base]);
  const loadRuns = useCallback(async () => {
    const params = new URLSearchParams({
      source_key: sourceKey, offset: String(runOffset), limit: String(RUN_LIMIT),
    });
    if (runStatus) params.set("status", runStatus);
    if (runQuery.trim()) params.set("query", runQuery.trim());
    const page = await request<{ page: { total: number }; items: Run[] }>(`/sync-runs?${params}`);
    setRuns(page.items); setRunTotal(page.page.total);
  }, [runOffset, runQuery, runStatus, sourceKey]);
  const loadCheckpoints = useCallback(async () => {
    const params = new URLSearchParams({
      offset: String(checkpointOffset), limit: String(CHECKPOINT_LIMIT),
    });
    if (checkpointResource) params.set("resource_key", checkpointResource);
    if (checkpointStatus) params.set("status", checkpointStatus);
    if (checkpointQuery.trim()) params.set("query", checkpointQuery.trim());
    const page = await request<CheckpointPage>(`${base}/checkpoints?${params}`);
    setCheckpoints(page.items); setCheckpointTotal(page.page.total);
  }, [base, checkpointOffset, checkpointQuery, checkpointResource, checkpointStatus]);
  const loadBindings = useCallback(async () => {
    const params = new URLSearchParams({ offset: String(bindingOffset), limit: String(BINDING_LIMIT) });
    if (bindingType) params.set("canonical_type", bindingType);
    if (bindingStatus) params.set("status", bindingStatus);
    if (bindingSuggestionsOnly) params.set("suggestion_only", "true");
    if (bindingQuery.trim()) params.set("query", bindingQuery.trim());
    const page = await request<BindingPage>(`${base}/binding-page?${params}`);
    setBindings(page.items); setBindingTotal(page.page.total);
  }, [base, bindingOffset, bindingQuery, bindingStatus, bindingSuggestionsOnly, bindingType]);
  useEffect(() => { void load().catch((reason: Error) => setError(reason.message)); }, [load]);
  useEffect(() => { void loadRuns().catch((reason: Error) => setError(reason.message)); }, [loadRuns]);
  useEffect(() => { void loadCheckpoints().catch((reason: Error) => setError(reason.message)); }, [loadCheckpoints]);
  useEffect(() => { void loadBindings().catch((reason: Error) => setError(reason.message)); }, [loadBindings]);
  const act = async (action: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await action(); notify({ tone: "success", title: "操作成功" }); await Promise.all([load(), loadRuns(), loadBindings(), loadCheckpoints()]); await onChanged(); }
    catch (reason) { const message = reason instanceof Error ? reason.message : "操作失败"; setError(message); notify({ tone: "error", title: message }); }
    finally { setBusy(false); }
  };
  const inspect = async (run: { id: string }) => {
    setError(null);
    try {
      const [childRows, rawRows] = await Promise.all([
        request<Child[]>(`/sync-runs/${encodeURIComponent(run.id)}/resources`),
        request<Manifest[]>(`/sync-runs/${encodeURIComponent(run.id)}/raw-manifests`)
      ]);
      setActiveRun(run.id); setChildren(childRows); setManifests(rawRows);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "读取失败"); }
  };
  return <>
    <Dialog title={name} eyebrow="来源台账" size="large" onClose={onClose} busy={busy}>
      {error ? <p role="alert">{error}</p> : null}
      <div className="console-toolbar">
        <span className="badge">{providerEnabled ? "接入已启用" : "接入已停用"}</span>
        <SourceBatchImport sourceKey={sourceKey} resources={resources} providerEnabled={providerEnabled} onChanged={async () => { await load(); await onChanged(); }} />
        {[["resources", "资源"], ...(systemType === "lingxing" ? [["official", "官方接口"]] : []), ["schedules", "采集计划"], ["backfills", "历史回填"], ["mirror", "镜像页"], ["checkpoints", "同步进度"], ["bindings", "归属审核"], ["conflicts", "映射冲突"], ["authority", "权威规则"], ["runs", "运行与血缘"]].map(([key, label]) =>
          <button className={`button ${tab === key ? "primary" : "secondary"}`} key={key} type="button" onClick={() => setTab(key)}>{label}</button>)}
        <button className="button secondary" type="button" disabled={busy} onClick={() => void load().catch((reason: Error) => setError(reason.message))}>刷新</button>
      </div>
      <div className="table-wrap">
        {tab === "schedules" ? <SourceSchedules sourceKey={sourceKey} resources={resources} providerEnabled={providerEnabled} /> : null}
        {tab === "backfills" ? <SourceBackfills sourceKey={sourceKey} resources={resources} providerEnabled={providerEnabled} /> : null}
        {tab === "mirror" ? <SourceMirrorPages key={sourceKey} sourceKey={sourceKey}
          onInspect={(id) => { setTab("runs"); void inspect({ id }); }} /> : null}
        {tab === "conflicts" ? <SourceConflicts sourceKey={sourceKey} /> : null}
        {tab === "authority" ? <SourceAuthority sourceKey={sourceKey} resources={resources} /> : null}
        {tab === "official" ? <LingxingOfficialOperations sourceKey={sourceKey}
          onChanged={async () => { await load(); await onChanged(); }} /> : null}
        {tab === "resources" ? <table><thead><tr><th>资源</th><th>波次</th><th>Schema</th><th>采集状态</th><th>契约验证</th><th>规范映射</th><th>操作</th></tr></thead><tbody>
          {resources.map((item) => <tr key={item.key}><td>{item.key}</td><td>{item.wave}</td><td>{item.schema_status === "confirmed" ? "已确认" : "待确认"}</td><td>{item.enabled ? "已启用" : "已停用"}</td><td>{item.validation_status === "validated" ? `通过 · ${time(item.last_validated_at)}` : item.validation_status === "needs_attention" ? <><span>需处理</span><br /><code>{item.validation_error_code ?? "—"}</code></> : "未验证"}</td><td>{item.projectable ? "可写入" : "不可写入"}</td><td>
            <button className="button secondary" type="button" disabled={busy || !item.can_execute || (item.key.startsWith("official_") && item.validation_status !== "validated")} onClick={() => { setValidating(false); setSync(item); setStart(""); setEnd(""); setParameters({}); }}>同步</button>
            {item.key.startsWith("official_") ? <button className="button secondary" type="button" disabled={busy || !item.can_execute} onClick={() => { setValidating(true); setSync(item); setStart(""); setEnd(""); setParameters({}); }}>验证</button> : null}
            {item.schema_confirmation_available ? <button className="button secondary" type="button" disabled={busy || !catalogVersion} onClick={() => setConfirmSchema({ resource: item, version: catalogVersion })}>确认契约</button> : null}
            <button className="button secondary" type="button" disabled={busy || !item.path} onClick={() => {
              if (item.enabled) setDisable(item);
              else void act(async () => { await request(`${base}/resources/${encodeURIComponent(item.key)}`, "PATCH", { enabled: true }); });
            }}>{item.enabled ? "停用" : "启用"}</button>
          </td></tr>)}
        </tbody></table> : null}
        {tab === "checkpoints" ? <><div className="console-toolbar">
          <input aria-label="同步进度搜索" value={checkpointQuery} onChange={(event) => { setCheckpointQuery(event.target.value); setCheckpointOffset(0); }} placeholder="资源或分区" />
          <select aria-label="同步进度资源" value={checkpointResource} onChange={(event) => { setCheckpointResource(event.target.value); setCheckpointOffset(0); }}><option value="">全部资源</option>{resources.map((item) => <option key={item.key} value={item.key}>{item.key}</option>)}</select>
          <select aria-label="同步进度状态" value={checkpointStatus} onChange={(event) => { setCheckpointStatus(event.target.value); setCheckpointOffset(0); }}><option value="">全部状态</option><option value="active">有效</option><option value="completed">完成</option><option value="failed">失败</option></select>
        </div><table><thead><tr><th>资源 / 分区</th><th>游标</th><th>页</th><th>读取</th><th>状态</th><th>更新时间</th></tr></thead><tbody>
          {checkpoints.map((item) => <tr key={`${item.resource_key}:${item.partition_key}`}><td>{item.resource_key} / {item.partition_key}</td><td>{item.cursor ?? "—"}</td><td>{item.page_number ?? "—"}</td><td>{item.records_read ?? "—"}</td><td>{item.status}</td><td>{time(item.updated_at)}</td></tr>)}
          {!checkpoints.length ? <tr><td colSpan={6}>暂无同步进度</td></tr> : null}
        </tbody></table><div className="console-toolbar">
          <button className="button secondary" disabled={busy || checkpointOffset === 0} onClick={() => setCheckpointOffset(Math.max(0, checkpointOffset - CHECKPOINT_LIMIT))} type="button">上一页</button>
          <span>{checkpointTotal ? `${checkpointOffset + 1}-${Math.min(checkpointOffset + CHECKPOINT_LIMIT, checkpointTotal)} / ${checkpointTotal}` : "0 / 0"}</span>
          <button className="button secondary" disabled={busy || checkpointOffset + CHECKPOINT_LIMIT >= checkpointTotal} onClick={() => setCheckpointOffset(checkpointOffset + CHECKPOINT_LIMIT)} type="button">下一页</button>
        </div></> : null}
        {tab === "bindings" ? <><div className="console-toolbar">
          <select aria-label="归属类型" value={bindingType} onChange={(event) => { setBindingType(event.target.value); setBindingOffset(0); }}><option value="">全部类型</option><option value="store">店铺</option><option value="warehouse">仓库</option><option value="product">商品</option><option value="source_user">来源用户</option></select>
          <select aria-label="归属状态" value={bindingStatus} onChange={(event) => { setBindingStatus(event.target.value); setBindingOffset(0); }}><option value="">全部状态</option><option value="pending">待审核</option><option value="approved">已批准</option><option value="rejected">已拒绝</option></select>
          <label><input checked={bindingSuggestionsOnly} onChange={(event) => { setBindingSuggestionsOnly(event.target.checked); setBindingOffset(0); }} type="checkbox" />仅看有建议</label>
          <input aria-label="来源对象搜索" value={bindingQuery} onChange={(event) => { setBindingQuery(event.target.value); setBindingOffset(0); }} placeholder="来源对象键" />
        </div><table><thead><tr><th>来源对象</th><th>类型</th><th>业务单元</th><th>系统建议</th><th>状态</th><th>操作</th></tr></thead><tbody>
          {bindings.map((item) => { const suggested = scopeOptions?.business_units.find((bu) => bu.key === item.suggested_business_unit_id)?.label; return <tr key={item.id}><td>{item.external_key}</td><td>{item.canonical_type}</td><td>{scopeOptions?.business_units.find((bu) => bu.key === item.business_unit_id)?.label ?? "未分配"}</td><td>{suggested ? `${suggested} · ${item.suggestion_evidence_count} 条证据` : item.suggestion_reason === "conflicting_related_dimensions" ? "归属证据冲突" : "—"}</td><td>{item.status}</td><td><button className="button secondary" type="button" disabled={busy} onClick={() => { setEdit(item); const candidate = item.business_unit_id ?? item.suggested_business_unit_id; setUnit(candidate && scopeContext?.business_unit_ids.includes(candidate) ? candidate : ""); setTimezone(""); }}>审核</button></td></tr>; })}
          {!bindings.length ? <tr><td colSpan={6}>暂无来源对象</td></tr> : null}
        </tbody></table><div className="console-toolbar">
          <button className="button secondary" disabled={busy || bindingOffset === 0} onClick={() => setBindingOffset(Math.max(0, bindingOffset - BINDING_LIMIT))} type="button">上一页</button>
          <span>{bindingTotal ? `${bindingOffset + 1}-${Math.min(bindingOffset + BINDING_LIMIT, bindingTotal)} / ${bindingTotal}` : "0 / 0"}</span>
          <button className="button secondary" disabled={busy || bindingOffset + BINDING_LIMIT >= bindingTotal} onClick={() => setBindingOffset(bindingOffset + BINDING_LIMIT)} type="button">下一页</button>
        </div></> : null}
        {tab === "runs" ? <><div className="console-toolbar">
          <input aria-label="同步运行搜索" value={runQuery} onChange={(event) => { setRunQuery(event.target.value); setRunOffset(0); }} placeholder="运行编号" />
          <select aria-label="同步运行状态" value={runStatus} onChange={(event) => { setRunStatus(event.target.value); setRunOffset(0); }}><option value="">全部状态</option><option value="queued">排队中</option><option value="running">运行中</option><option value="succeeded">成功</option><option value="partial_failed">部分失败</option><option value="failed">失败</option><option value="cancelled">已取消</option></select>
        </div><table><thead><tr><th>运行</th><th>入队配置版本</th><th>状态</th><th>Raw 读取</th><th>规范写入</th><th>操作</th></tr></thead><tbody>
          {runs.map((item) => <tr key={item.id}><td>{item.id}</td><td>{item.source_version ?? "未知"}</td><td>{item.status}</td><td>{item.records_read}</td><td>{item.records_written}</td><td>
            <button className="button secondary" type="button" onClick={() => void inspect(item)}>血缘</button>
            {["queued", "running"].includes(item.status) ? <button className="button secondary" type="button" disabled={busy} onClick={() => setCancel(item)}>取消</button> : null}
          </td></tr>)}
          {!runs.length ? <tr><td colSpan={6}>暂无同步运行</td></tr> : null}
        </tbody></table><div className="console-toolbar">
          <button className="button secondary" disabled={busy || runOffset === 0} onClick={() => setRunOffset(Math.max(0, runOffset - RUN_LIMIT))} type="button">上一页</button>
          <span>{runTotal ? `${runOffset + 1}-${Math.min(runOffset + RUN_LIMIT, runTotal)} / ${runTotal}` : "0 / 0"}</span>
          <button className="button secondary" disabled={busy || runOffset + RUN_LIMIT >= runTotal} onClick={() => setRunOffset(runOffset + RUN_LIMIT)} type="button">下一页</button>
        </div>
          {activeRun ? <><h3>资源运行 · {activeRun}</h3><table><thead><tr><th>资源</th><th>分区</th><th>状态</th><th>读取 / 写入</th><th>错误</th></tr></thead><tbody>{children.map((item) => <tr key={item.id}><td>{item.resource_key}</td><td>{item.partition_key}</td><td>{item.status}</td><td>{item.records_read} / {item.records_written}</td><td>{item.error_code ?? "—"}</td></tr>)}</tbody></table>
            <h3>Raw 页</h3><table><thead><tr><th>资源 / 页</th><th>哈希</th><th>行数 / 字节</th><th>Schema</th><th>采集时间</th><th>操作</th></tr></thead><tbody>{manifests.map((item) => <tr key={item.id}><td>{item.resource_key} / {item.page_number ?? "—"}</td><td><code title={item.content_hash}>{item.content_hash.slice(0, 20)}</code></td><td>{item.row_count} / {item.bytes}</td><td>{item.schema_status}</td><td>{time(item.fetched_at)}</td><td><button type="button" className="button secondary" disabled={busy || !item.replay_eligible} onClick={() => setReplay({ manifest: item, requestKey: crypto.randomUUID() })}>重放映射</button></td></tr>)}</tbody></table></> : null}
        </> : null}
      </div>
    </Dialog>
    {edit ? <Dialog title="审核来源归属" onClose={() => setEdit(null)} busy={busy} footer={<>
      <button className="button secondary" type="button" disabled={busy} onClick={() => setReview("rejected")}>拒绝</button>
      <button className="button primary" type="button" disabled={busy || !unit || !scopeContext?.business_unit_ids.includes(unit)} onClick={() => setReview("approved")}>批准</button>
    </>}>{error ? <p role="alert">{error}</p> : null}<p>{edit.external_key}</p><div className="platform-form-grid source-form-grid"><label>业务单元<select value={unit} onChange={(event) => setUnit(event.target.value)}><option value="">请选择</option>{scopeOptions?.business_units.filter((item) => item.enterprise_id === identity?.enterprise_id && scopeContext?.business_unit_ids.includes(item.key)).map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
      {edit.canonical_type === "store" ? <label>店铺时区<input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Shanghai" /></label> : null}
      </div>
    </Dialog> : null}
    {sync ? <Dialog title={`${validating ? "验证" : "同步"} ${sync.key}`} onClose={() => { setSync(null); setValidating(false); }} busy={busy} footer={<button className="button primary" type="button" disabled={busy || (sync.window_fields.length > 0 && (!start || (sync.window_fields.length === 2 && !end))) || sync.schedule_parameters.some((key) => !parameters[key])} onClick={() => void act(async () => {
      const window = syncWindow(sync, start, end);
      if (validating) await request(`${base}/resources/${encodeURIComponent(sync.key)}/validate`, "POST", { resource_parameters: parameters, ...window });
      else await request(`${base}/imports`, "POST", { client_request_key: crypto.randomUUID(), selections: [{ resource_key: sync.key,
        resource_parameters: parameters, ...window }], partition_days: sync.window_fields.length === 1 ? 1 : 7 });
      setSync(null); setValidating(false);
    })}>{validating ? "加入验证队列" : "加入同步队列"}</button>}>
      {error ? <p role="alert">{error}</p> : null}
      <div className="platform-form-grid source-form-grid">
      {sync.window_fields.length ? <><label>{sync.window_fields.length === 1 ? "业务日期" : "开始"}<input type={sync.window_format === "date" ? "date" : "datetime-local"} value={start} onChange={(event) => setStart(event.target.value)} /></label>{sync.window_fields.length === 2 ? <label>结束<input type={sync.window_format === "date" ? "date" : "datetime-local"} value={end} onChange={(event) => setEnd(event.target.value)} /></label> : null}</> : null}
      {sync.schedule_parameters.map((key) => <label key={key}>{key}<input type="text" value={parameters[key] ?? ""} onChange={(event) => setParameters({ ...parameters, [key]: event.target.value })} /></label>)}
      </div>
    </Dialog> : null}
    {confirmSchema ? <ConfirmDialog title="确认资源契约" description={`批准 ${confirmSchema.resource.key} 使用目录版本 ${confirmSchema.version} 的规范映射？`}
      busy={busy} onCancel={() => setConfirmSchema(null)} onConfirm={() => void act(async () => {
        await request(`${base}/resources/${encodeURIComponent(confirmSchema.resource.key)}`, "PATCH", {
          enabled: confirmSchema.resource.enabled, confirm_catalog_version: confirmSchema.version,
        });
        setConfirmSchema(null);
      })} /> : null}
    {replay ? <ConfirmDialog title="重放 Raw 映射" description={`将 ${replay.manifest.resource_key} 第 ${replay.manifest.page_number ?? "—"} 页按映射版本 ${replay.manifest.mapping_version} 重新入队，更新通过校验的规范记录。`}
      busy={busy} onCancel={() => setReplay(null)} onConfirm={() => void act(async () => {
        await request(`/raw-manifests/${encodeURIComponent(replay.manifest.id)}/replay`, "POST", {
          client_request_key: replay.requestKey, expected_content_hash: replay.manifest.content_hash,
          expected_mapping_version: replay.manifest.mapping_version,
        });
        setReplay(null);
      })} /> : null}
    {review && edit ? <ConfirmDialog title={review === "approved" ? "批准来源归属" : "拒绝来源归属"}
      description={review === "approved" ? `将 ${edit.external_key} 归属到 ${scopeOptions?.business_units.find((item) => item.key === unit)?.label ?? unit}，后续事实按此范围写入。` : `拒绝 ${edit.external_key} 的归属，阻止后续事实按此归属写入。`}
      busy={busy} onCancel={() => setReview(null)} onConfirm={() => void act(async () => {
        await request(`${base}/bindings/${edit.id}`, "PATCH", review === "approved" ? { status: review, business_unit_id: unit, store_timezone: timezone || null } : { status: review });
        setReview(null); setEdit(null); await refreshScope();
      })} /> : null}
    {cancel ? <ConfirmDialog title="取消同步" description={`取消运行 ${cancel.id}？`} busy={busy} onCancel={() => setCancel(null)} onConfirm={() => void act(async () => { await request(`/sync-runs/${cancel.id}/cancel`, "POST"); setCancel(null); })} /> : null}
    {disable ? <ConfirmDialog title="停用资源" description={`停用 ${disable.key}？`} busy={busy} onCancel={() => setDisable(null)} onConfirm={() => void act(async () => { await request(`${base}/resources/${disable.key}`, "PATCH", { enabled: false }); setDisable(null); })} /> : null}
  </>;
}
