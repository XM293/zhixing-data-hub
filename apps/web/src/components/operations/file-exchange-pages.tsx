"use client";

import { Check, CircleAlert, Download, FileArchive, FilePlus2, LoaderCircle, Play, RefreshCw, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog, Dialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type { BulkExchangeDetailResponse, BulkExchangeJob, BulkExchangeListResponse, FileAsset, FileAssetListResponse } from "@/lib/platform-admin-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function FileAssetPage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<FileAssetListResponse | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [assetKey, setAssetKey] = useState("");
  const [category, setCategory] = useState("exchange");
  const [reason, setReason] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canManage = can("file.asset.manage");

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/files`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId } });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "文件资产读取失败"));
    setData((await response.json()) as FileAssetListResponse);
  }, [roleId]);

  useEffect(() => { load().catch((value: unknown) => setError(value instanceof Error ? value.message : "文件资产读取失败")); }, [load]);

  async function upload(): Promise<void> {
    if (!file || !canManage) return;
    setUploading(true); setError(null);
    try {
      const contentBase64 = await fileBase64(file);
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/files`, {
        method: "POST", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("file"), reason: reason.trim(), asset_key: assetKey.trim(), file_name: file.name, media_type: file.type || "application/octet-stream", content_base64: contentBase64, category, required_permission: "file.asset.read", scope_type: "enterprise", scope_id: data?.items[0]?.scope_id ?? "" })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "文件上传失败"));
      notify({ title: "文件已保存", description: file.name, tone: "success" }); setFile(null); setAssetKey(""); setReason(""); setUploadOpen(false); await load();
    } catch (value: unknown) { notify({ title: "文件上传失败", description: value instanceof Error ? value.message : "请检查文件后重试", tone: "error" }); }
    finally { setUploading(false); }
  }

  async function download(asset: FileAsset): Promise<void> {
    setDownloadingId(asset.id); setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/files/${encodeURIComponent(asset.id)}/content`, { headers: { "X-Zhixing-Demo-Actor": roleId } });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "文件下载失败"));
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = asset.file_name; anchor.click(); URL.revokeObjectURL(url);
    } catch (value: unknown) { notify({ title: "文件下载失败", description: value instanceof Error ? value.message : "请重试", tone: "error" }); }
    finally { setDownloadingId(null); }
  }

  return <div className="platform-control-page file-asset-page">
    <PageHeader actions={<div className="platform-header-actions"><button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新</button>{canManage ? <button className="button primary" onClick={() => setUploadOpen(true)} type="button"><Upload size={15} />上传文件</button> : null}</div>} eyebrow="FILE ASSETS" meta={`${data?.stats.total ?? 0} 个文件`} title="文件资产" />
    {error ? <InlineCallout description={error} title="操作未完成" tone="critical" /> : null}
    <section className="platform-stat-band" aria-label="文件统计"><Stat label="文件" value={data?.stats.total ?? 0} /><Stat label="可用" value={data?.stats.active ?? 0} /><Stat label="容量" value={formatBytes(data?.stats.bytes ?? 0)} /><Stat label="分类" value={data?.stats.categories ?? 0} /></section>
    {uploadOpen && canManage ? <Dialog busy={uploading} className="file-upload-dialog" eyebrow="UPLOAD" footer={<><button className="button secondary" disabled={uploading} onClick={() => setUploadOpen(false)} type="button">取消</button><button className="button primary" disabled={!file || uploading || assetKey.trim().length < 3 || reason.trim().length < 3} onClick={() => void upload()} type="button">{uploading ? <LoaderCircle className="spinning" size={15} /> : <Upload size={15} />}上传</button></>} onClose={() => setUploadOpen(false)} size="medium" title="上传文件"><div className="platform-form-grid overlay-form-grid">
      <label><span>文件</span><input onChange={(event) => { const next = event.target.files?.[0] ?? null; setFile(next); if (next && !assetKey) setAssetKey(normalizeAssetKey(next.name)); }} type="file" /></label>
      <label><span>资产标识</span><input onChange={(event) => setAssetKey(event.target.value)} value={assetKey} /></label>
      <label><span>分类</span><select onChange={(event) => setCategory(event.target.value)} value={category}><option value="exchange">批量交换</option><option value="knowledge">知识原件</option><option value="evidence">业务证据</option></select></label>
      <label className="platform-wide-field"><span>上传原因</span><input onChange={(event) => setReason(event.target.value)} value={reason} /></label>
    </div></Dialog> : null}
    <section className="platform-data-panel"><header><div><span>ASSET LEDGER</span><h2>文件目录</h2></div><em>{data?.items.length ?? 0} 条</em></header><div className="platform-table-wrap"><table><thead><tr><th>文件</th><th>分类</th><th>大小</th><th>范围</th><th>上传人</th><th>校验值</th><th>时间</th><th>操作</th></tr></thead><tbody>{data?.items.map((item) => <tr key={item.id}><td><strong>{item.file_name}</strong><small>{item.asset_key}</small></td><td>{categoryLabel(item.category)}</td><td>{formatBytes(item.size_bytes)}</td><td>{item.scope_type}<small>{item.scope_id}</small></td><td>{item.uploader_name}</td><td><code>{item.checksum_sha256.slice(0, 12)}</code></td><td>{formatTime(item.created_at)}</td><td><button aria-label="下载文件" className="platform-icon-button" disabled={downloadingId === item.id} onClick={() => void download(item)} title="下载" type="button">{downloadingId === item.id ? <LoaderCircle className="spinning" size={14} /> : <Download size={14} />}</button></td></tr>)}</tbody></table>{data?.items.length ? null : <div className="platform-empty-state"><FileArchive size={23} /><strong>当前没有文件资产</strong></div>}</div></section>
  </div>;
}

export function BulkExchangePage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<BulkExchangeListResponse | null>(null);
  const [detail, setDetail] = useState<BulkExchangeDetailResponse | null>(null);
  const [content, setContent] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [commitOpen, setCommitOpen] = useState(false);
  const canManage = can("bulk.exchange.manage");

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/bulk-exchanges`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId } });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "批量任务读取失败"));
    setData((await response.json()) as BulkExchangeListResponse);
  }, [roleId]);

  useEffect(() => { load().catch((value: unknown) => setError(value instanceof Error ? value.message : "批量任务读取失败")); }, [load]);

  async function selectJob(job: BulkExchangeJob): Promise<void> {
    const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/bulk-exchanges/${encodeURIComponent(job.id)}`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId } });
    if (!response.ok) { setError(await apiErrorMessage(response, "批量任务详情读取失败")); return; }
    setDetail((await response.json()) as BulkExchangeDetailResponse);
  }

  async function preflight(): Promise<void> {
    if (!canManage) return;
    setSaving(true); setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/bulk-exchanges/preflight`, { method: "POST", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("exchange-preflight"), reason: reason.trim(), dataset_key: "platform.dictionary-items", file_format: "csv", content }) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "批量预检失败"));
      const result = (await response.json()) as { job: BulkExchangeJob }; notify({ title: "批量预检已完成", description: result.job.id, tone: "success" }); setContent(""); setReason(""); await load(); await selectJob(result.job);
    } catch (value: unknown) { notify({ title: "批量预检失败", description: value instanceof Error ? value.message : "请检查 CSV 内容后重试", tone: "error" }); }
    finally { setSaving(false); }
  }

  async function commit(): Promise<void> {
    if (!detail || !canManage) return;
    setSaving(true); setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/bulk-exchanges/${encodeURIComponent(detail.job.id)}/commit`, { method: "POST", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("exchange-commit"), reason: "确认预检结果并写入数据" }) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "批量写入失败"));
      const result = (await response.json()) as { job: BulkExchangeJob }; notify({ title: "批量数据已写入", description: `${result.job.applied_rows} 行 · ${result.job.id}`, tone: "success" }); setCommitOpen(false); await load(); await selectJob(result.job);
    } catch (value: unknown) { notify({ title: "批量写入失败", description: value instanceof Error ? value.message : "请重试", tone: "error" }); }
    finally { setSaving(false); }
  }

  async function exportData(): Promise<void> {
    if (!canManage) return;
    setSaving(true); setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/bulk-exchanges/export`, { method: "POST", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("exchange-export"), reason: "导出当前平台字典", dataset_key: "platform.dictionary-items", file_format: "csv" }) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "数据导出失败"));
      const result = (await response.json()) as { job: BulkExchangeJob }; notify({ title: "导出任务已创建", description: result.job.id, tone: "success" }); await load(); await selectJob(result.job);
    } catch (value: unknown) { notify({ title: "数据导出失败", description: value instanceof Error ? value.message : "请重试", tone: "error" }); }
    finally { setSaving(false); }
  }

  return <div className="platform-control-page bulk-exchange-page">
    <PageHeader actions={canManage ? <button className="button secondary" disabled={saving} onClick={() => void exportData()} type="button"><Download size={15} />导出</button> : null} eyebrow="BULK EXCHANGE" meta={`${data?.items.length ?? 0} 个任务`} title="批量交换" />
    {error ? <InlineCallout description={error} title="操作未完成" tone="critical" /> : null}
    {canManage ? <section className="platform-inline-editor"><header><div><span>IMPORT PREFLIGHT</span><h3>导入预检</h3></div></header><div className="platform-form-grid">
      <label><span>数据集</span><select defaultValue="platform.dictionary-items" disabled><option value="platform.dictionary-items">平台字典项</option></select></label>
      <label><span>CSV 文件</span><input accept=".csv,text/csv" onChange={(event) => { const file = event.target.files?.[0]; if (file) void file.text().then(setContent); }} type="file" /></label>
      <label className="platform-wide-field platform-textarea-field"><span>CSV 内容</span><textarea onChange={(event) => setContent(event.target.value)} rows={6} value={content} /></label>
      <label className="platform-wide-field"><span>导入原因</span><input onChange={(event) => setReason(event.target.value)} value={reason} /></label>
      <footer><button className="button primary" disabled={saving || content.trim().length < 1 || reason.trim().length < 3} onClick={() => void preflight()} type="button">{saving ? <LoaderCircle className="spinning" size={15} /> : <Check size={15} />}开始预检</button></footer>
    </div></section> : null}
    <div className="platform-split-workspace"><section className="platform-data-panel"><header><div><span>EXCHANGE JOBS</span><h2>交换任务</h2></div><em>{data?.items.length ?? 0} 条</em></header><div className="platform-table-wrap"><table><thead><tr><th>任务</th><th>操作</th><th>状态</th><th>总行</th><th>有效</th><th>错误</th><th>写入</th><th>时间</th></tr></thead><tbody>{data?.items.map((job) => <tr className={detail?.job.id === job.id ? "selected" : ""} key={job.id} onClick={() => void selectJob(job)}><td><strong>{datasetLabel(job.dataset_key)}</strong><small>{job.id}</small></td><td>{job.operation === "import" ? "导入" : "导出"}</td><td><StatusBadge value={exchangeStatus(job.status)} /></td><td>{job.total_rows}</td><td>{job.valid_rows}</td><td>{job.invalid_rows}</td><td>{job.applied_rows}</td><td>{formatTime(job.created_at)}</td></tr>)}</tbody></table>{data?.items.length ? null : <div className="platform-empty-state"><FilePlus2 size={23} /><strong>当前没有批量任务</strong></div>}</div></section>
      <aside className="platform-detail-panel">{detail ? <><header><div><span>VALIDATION RESULT</span><h2>{datasetLabel(detail.job.dataset_key)}</h2></div><StatusBadge value={exchangeStatus(detail.job.status)} /></header><dl className="platform-detail-grid"><div><dt>总行</dt><dd>{detail.job.total_rows}</dd></div><div><dt>有效</dt><dd>{detail.job.valid_rows}</dd></div><div><dt>错误</dt><dd>{detail.job.invalid_rows}</dd></div><div><dt>写入</dt><dd>{detail.job.applied_rows}</dd></div></dl><section className="exchange-row-list"><h3>预检明细</h3>{detail.rows.map((row) => <article key={row.row_number}><span>{row.row_number}</span><div><strong>{String(row.normalized_data.item_key ?? "-")}</strong><small>{String(row.normalized_data.dictionary_key ?? "-")}</small>{row.errors.length ? <p>{row.errors.map((item) => `${String(item.field)}:${String(item.code)}`).join(" · ")}</p> : null}</div><StatusBadge value={exchangeStatus(row.status)} /></article>)}</section>{detail.job.status === "ready" && canManage ? <footer className="platform-detail-action"><button className="button primary" disabled={saving} onClick={() => setCommitOpen(true)} type="button"><Play size={15} />确认写入</button></footer> : null}</> : <div className="platform-empty-state"><CircleAlert size={23} /><strong>选择一个批量任务</strong></div>}</aside>
    </div>
    {commitOpen && detail ? <ConfirmDialog busy={saving} confirmLabel="确认写入" description={`将 ${detail.job.valid_rows} 行预检数据写入平台字典？`} detail={`${detail.job.invalid_rows} 行错误数据不会写入；成功行将形成平台配置修订和操作审计。`} onCancel={() => setCommitOpen(false)} onConfirm={() => void commit()} title="确认批量写入" tone="warning" /> : null}
  </div>;
}

function Stat({ label, value }: { label: string; value: number | string }) { return <article><span>{label}</span><strong>{value}</strong></article>; }
function exchangeStatus(value: string) { return { label: ({ ready: "待写入", validation_failed: "预检失败", succeeded: "成功", valid: "有效", invalid: "错误", applied: "已写入" } as Record<string, string>)[value] ?? value, tone: value === "succeeded" || value === "valid" || value === "applied" ? "positive" as const : value === "validation_failed" || value === "invalid" ? "critical" as const : "warning" as const }; }
function datasetLabel(value: string): string { return value === "platform.dictionary-items" ? "平台字典项" : value; }
function categoryLabel(value: string): string { return ({ exchange: "批量交换", knowledge: "知识原件", evidence: "业务证据" } as Record<string, string>)[value] ?? value; }
function formatBytes(value: number): string { if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB`; }
function formatTime(value: string): string { return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)); }
function normalizeAssetKey(value: string): string { return value.toLocaleLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || `asset-${Date.now()}`; }
function requestKey(prefix: string): string { return `${prefix}-${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now()}`; }
async function fileBase64(file: File): Promise<string> { const buffer = await file.arrayBuffer(); const bytes = new Uint8Array(buffer); let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte); return btoa(binary); }
