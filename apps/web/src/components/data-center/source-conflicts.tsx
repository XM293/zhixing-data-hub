"use client";

import { useCallback, useDeferredValue, useEffect, useState } from "react";

import { ConfirmDialog, useNotifications } from "@/components/console/interaction";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

interface Conflict {
  id: string;
  source_key: string;
  external_object_key: string;
  status: string;
  resource_key: string | null;
  raw_manifest_id: string | null;
  error_code: string | null;
  resolved_manifest_id: string | null;
}

interface ConflictPage {
  page: { offset: number; limit: number; total: number };
  status_counts: Record<string, number>;
  items: Conflict[];
}

const PAGE_SIZE = 25;
const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center/mapping-conflicts`;
const reasons: Record<string, string> = {
  "mapping.unassigned": "来源对象未归属",
  schema_or_quality_invalid: "字段或质量校验失败",
  normalization_pending: "币种或时区待确认",
  source_time_comparison_pending: "更新时间口径待确认"
};
const statuses: Record<string, string> = {
  pending: "待处理",
  approved: "已批准",
  rejected: "已退回"
};

export function SourceConflicts({ sourceKey }: { sourceKey: string }) {
  const { notify } = useNotifications();
  const [data, setData] = useState<ConflictPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState<{
    row: Conflict;
    status: "approved" | "rejected";
  } | null>(null);
  const load = useCallback(async () => {
    const parameters = new URLSearchParams({
      source_key: sourceKey,
      offset: String(offset),
      limit: String(PAGE_SIZE)
    });
    if (status) parameters.set("status", status);
    if (deferredQuery.trim()) parameters.set("query", deferredQuery.trim());
    const response = await apiFetch(`${API}/page?${parameters}`, { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "读取冲突失败"));
    setData(await response.json() as ConflictPage);
    setError(null);
  }, [deferredQuery, offset, sourceKey, status, revision]);
  useEffect(() => {
    void load().catch((reason: Error) => setError(reason.message));
  }, [load]);
  const save = async () => {
    if (!review) return;
    setBusy(true);
    try {
      const response = await apiFetch(`${API}/${encodeURIComponent(review.row.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: review.status,
          expected_manifest_id: review.row.raw_manifest_id
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "审核失败"));
      setReview(null);
      notify({ tone: "success", title: "冲突审核已保存" });
      setRevision((value) => value + 1);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "审核失败";
      setError(message);
      notify({ tone: "error", title: message });
    } finally {
      setBusy(false);
    }
  };
  return <>
    {error ? <p role="alert">{error}</p> : null}
    <div className="console-toolbar">
      <input aria-label="冲突对象搜索" placeholder="资源或对象键" value={query}
        onChange={(event) => { setQuery(event.target.value); setOffset(0); }} />
      <select aria-label="冲突状态" value={status}
        onChange={(event) => { setStatus(event.target.value); setOffset(0); }}>
        <option value="">全部状态</option>
        <option value="pending">待处理 {data?.status_counts.pending ?? 0}</option>
        <option value="approved">已批准 {data?.status_counts.approved ?? 0}</option>
        <option value="rejected">已退回 {data?.status_counts.rejected ?? 0}</option>
      </select>
      <button type="button" className="button secondary" disabled={busy}
        onClick={() => setRevision((value) => value + 1)}>刷新</button>
    </div>
    <table><thead><tr><th>资源 / 对象</th><th>问题</th><th>状态</th><th>Raw / 修复证据</th><th>操作</th></tr></thead><tbody>
      {data?.items.map((row) => <tr key={row.id}>
        <td>{row.resource_key ?? "—"}<br />{row.external_object_key}</td>
        <td>{reasons[row.error_code ?? ""] ?? row.error_code ?? "—"}</td>
        <td>{statuses[row.status] ?? row.status}</td>
        <td><code>{row.raw_manifest_id ?? "—"}</code><br /><code>{row.resolved_manifest_id ?? "待重新映射验证"}</code></td>
        <td><button type="button" className="button secondary"
          disabled={busy || !row.resolved_manifest_id || row.status === "approved"}
          onClick={() => setReview({ row, status: "approved" })}>批准</button>
          <button type="button" className="button secondary"
            disabled={busy || row.status === "rejected"}
            onClick={() => setReview({ row, status: "rejected" })}>退回</button></td>
      </tr>)}
      {data && !data.items.length ? <tr><td colSpan={5}>暂无映射冲突</td></tr> : null}
    </tbody></table>
    <div className="console-toolbar">
      <button type="button" className="button secondary" disabled={busy || offset === 0}
        onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>上一页</button>
      <span>{data?.page.total ? `${offset + 1}-${Math.min(offset + PAGE_SIZE, data.page.total)} / ${data.page.total}` : "0 / 0"}</span>
      <button type="button" className="button secondary"
        disabled={busy || !data || offset + PAGE_SIZE >= data.page.total}
        onClick={() => setOffset(offset + PAGE_SIZE)}>下一页</button>
    </div>
    {review ? <ConfirmDialog
      title={review.status === "approved" ? "批准修复结果" : "退回映射冲突"}
      description={`${review.row.external_object_key}：${review.status === "approved" ? "确认已验证的映射修复结果。" : "保留冲突，等待重新处理。"}`}
      busy={busy}
      onCancel={() => setReview(null)}
      onConfirm={() => void save()}
    /> : null}
  </>;
}
