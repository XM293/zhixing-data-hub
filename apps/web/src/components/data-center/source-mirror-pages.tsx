"use client";

import { useEffect, useState } from "react";
import { ConfirmDialog, useNotifications } from "@/components/console/interaction";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

interface Page {
  raw_manifest_id: string; resource_key: string; acquisition_run_id: string;
  projection_run_id: string | null; projection_status: string; fetched_at: string | null;
  row_count: number; records_written: number; schema_status: string; content_hash: string;
}
const states: Record<string, string> = { queued: "待映射", running: "映射中", succeeded: "已映射",
  failed: "失败", partial_failed: "部分失败", cancelled: "已取消", schema_pending: "字段待确认",
  scope_invalid: "范围隔离", schema_invalid: "结构隔离" };
const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center`;

export function SourceMirrorPages({ sourceKey, onInspect }: {
  sourceKey: string; onInspect: (runId: string) => void;
}) {
  const { notify } = useNotifications();
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<{ items: Page[]; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [quarantine, setQuarantine] = useState<Page | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null); setData(null);
    void (async () => {
      try {
        const response = await apiFetch(`${API}/sources/${encodeURIComponent(sourceKey)}/mirror-pages?offset=${offset}&limit=25`,
          { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error(await apiErrorMessage(response, "镜像页读取失败"));
        const result = await response.json() as { items: Page[]; total: number };
        if (!controller.signal.aborted) setData(result);
      } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "读取失败"); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    })();
    return () => controller.abort();
  }, [sourceKey, offset, revision]);
  const applyQuarantine = async () => {
    if (!quarantine) return;
    setLoading(true); setError(null);
    try {
      const response = await apiFetch(`${API}/raw-manifests/${encodeURIComponent(quarantine.raw_manifest_id)}/quarantine`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_content_hash: quarantine.content_hash, reason: "scope_invalid" }),
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "镜像页隔离失败"));
      setQuarantine(null); setRevision((value) => value + 1);
      notify({ tone: "success", title: "镜像页已隔离" });
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "镜像页隔离失败";
      setError(message); notify({ tone: "error", title: message });
    } finally { setLoading(false); }
  };
  return <><section aria-label="来源镜像页">
    <div className="console-toolbar"><button type="button" className="button secondary" disabled={loading} onClick={() => setRevision((value) => value + 1)}>刷新</button>
      <span>{data ? `${data.total} 页` : "—"}</span></div>
    {error ? <p role="alert">{error}</p> : null}
    {loading ? <p role="status">加载中</p> : null}
    <div style={{ overflowX: "auto" }}><table><thead><tr><th>资源 / Raw 页</th><th>采集时间</th><th>已采集</th><th>映射状态</th><th>规范写入</th><th>操作</th></tr></thead>
      <tbody>{data?.items.map((page) => <tr key={page.raw_manifest_id}>
        <td>{page.resource_key}<br /><button type="button" className="button secondary" onClick={() => onInspect(page.acquisition_run_id)}>采集血缘</button><br />{page.raw_manifest_id}</td><td>{page.fetched_at ? new Date(page.fetched_at).toLocaleString("zh-CN") : "未知"}</td>
        <td>{page.row_count}</td><td>{states[page.schema_status] ?? states[page.projection_status] ?? page.projection_status}</td><td>{page.records_written}</td><td>{page.projection_run_id ? <button type="button" className="button secondary" onClick={() => onInspect(page.projection_run_id!)}>映射血缘</button> : null}
          {!['scope_invalid', 'schema_invalid'].includes(page.schema_status) ? <button type="button" className="button secondary" disabled={loading || ["queued", "running"].includes(page.projection_status)} onClick={() => setQuarantine(page)}>隔离</button> : null}</td>
      </tr>)}{data && !data.items.length ? <tr><td colSpan={6}>暂无镜像页</td></tr> : null}</tbody></table></div>
    <div className="console-toolbar"><button type="button" className="button secondary" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>上一页</button>
      <button type="button" className="button secondary" disabled={loading || !data || offset + 25 >= data.total} onClick={() => setOffset(offset + 25)}>下一页</button></div>
  </section>
    {quarantine ? <ConfirmDialog title="隔离 Raw 页" tone="danger" busy={loading}
      description={`隔离 ${quarantine.resource_key} 的这一个 Raw 页？`}
      detail="隔离后该页不能进入规范映射或重放，原始归档和审计记录继续保留。"
      confirmLabel="确认隔离" onCancel={() => setQuarantine(null)} onConfirm={() => void applyQuarantine()} /> : null}
  </>;
}
