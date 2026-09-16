"use client";

import { CircleAlert, Clock3, LoaderCircle, RefreshCw, RotateCcw, ServerCog } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type { BackgroundJob, JobAdminResponse, JobDetailResponse } from "@/lib/platform-admin-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function JobAdminPage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<JobAdminResponse | null>(null);
  const [detail, setDetail] = useState<JobDetailResponse | null>(null);
  const [status, setStatus] = useState("all");
  const [jobType, setJobType] = useState("all");
  const [query, setQuery] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [retryOpen, setRetryOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canManage = can("operations.run.manage");

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/jobs`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "后台任务读取失败"));
    setData((await response.json()) as JobAdminResponse);
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    load().catch((reasonValue: unknown) => setError(reasonValue instanceof Error ? reasonValue.message : "后台任务读取失败")).finally(() => setLoading(false));
  }, [load]);

  const jobs = useMemo(() => (data?.items ?? []).filter((item) => {
    const normalized = query.trim().toLocaleLowerCase();
    return (status === "all" || item.status === status) &&
      (jobType === "all" || item.job_type === jobType) &&
      (!normalized || [item.id, item.request_id, item.run_id].some((value) => value.toLocaleLowerCase().includes(normalized)));
  }), [data?.items, jobType, query, status]);

  async function selectJob(job: BackgroundJob): Promise<void> {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/jobs/${encodeURIComponent(job.id)}`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) {
      setError(await apiErrorMessage(response, "任务详情读取失败"));
      return;
    }
    setDetail((await response.json()) as JobDetailResponse);
    setReason("");
  }

  async function retry(): Promise<void> {
    if (!detail || !canManage) return;
    setSaving(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/jobs/${encodeURIComponent(detail.job.id)}/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("job-retry"), reason: reason.trim(), expected_attempt: detail.job.attempt })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "任务重试失败"));
      notify({ title: "后台任务已重新排队", description: detail.job.id, tone: "success" });
      setRetryOpen(false);
      await load();
      await selectJob({ ...detail.job, status: "queued" });
    } catch (reasonValue: unknown) {
      notify({ title: "任务重试失败", description: reasonValue instanceof Error ? reasonValue.message : "请重试", tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  if (loading && !data) return <JobState title="正在读取后台任务" />;

  return <div className="platform-control-page job-admin-page">
    <PageHeader actions={<button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新</button>} eyebrow="BACKGROUND JOBS" meta={`${data?.stats.total ?? 0} 个任务`} title="后台任务" />
    {error ? <InlineCallout description={error} title="操作未完成" tone="critical" /> : null}
    <section className="platform-stat-band" aria-label="任务统计">
      <Stat icon={<Clock3 size={16} />} label="排队" value={(data?.stats.queued ?? 0) + (data?.stats.retry_wait ?? 0)} />
      <Stat icon={<ServerCog size={16} />} label="运行" value={data?.stats.running ?? 0} />
      <Stat icon={<RefreshCw size={16} />} label="成功" value={data?.stats.succeeded ?? 0} />
      <Stat icon={<CircleAlert size={16} />} label="失败" value={data?.stats.failed ?? 0} />
    </section>
    <section className="platform-filter-bar" aria-label="任务筛选">
      <label><span>状态</span><select onChange={(event) => setStatus(event.target.value)} value={status}><option value="all">全部状态</option>{["queued", "running", "retry_wait", "succeeded", "failed", "cancelled"].map((item) => <option key={item} value={item}>{jobStatusLabel(item)}</option>)}</select></label>
      <label><span>任务类型</span><select onChange={(event) => setJobType(event.target.value)} value={jobType}><option value="all">全部类型</option>{data?.job_types.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
      <label className="platform-query-field"><span>检索</span><input onChange={(event) => setQuery(event.target.value)} placeholder="任务、Request、Run ID" value={query} /></label>
    </section>
    <div className="platform-split-workspace">
      <section className="platform-data-panel">
        <header><div><span>JOB LEDGER</span><h2>运行台账</h2></div><em>{jobs.length} 条</em></header>
        <div className="platform-table-wrap"><table><thead><tr><th>任务</th><th>状态</th><th>范围</th><th>执行轮次</th><th>更新时间</th></tr></thead><tbody>{jobs.map((job) => <tr className={detail?.job.id === job.id ? "selected" : ""} key={job.id} onClick={() => void selectJob(job)}><td><strong>{job.job_type}</strong><small>{job.id}</small></td><td><StatusBadge value={jobStatus(job.status)} /></td><td>{job.scope_type}<small>{job.scope_id}</small></td><td>{job.attempt}<small>正常续跑 {job.continuation_count ?? 0}</small></td><td>{formatTime(job.updated_at)}</td></tr>)}</tbody></table>{jobs.length ? null : <div className="platform-empty-state"><ServerCog size={23} /><strong>当前没有任务</strong></div>}</div>
      </section>
      <aside className="platform-detail-panel">
        {detail ? <>
          <header><div><span>JOB DETAIL</span><h2>{detail.job.job_type}</h2></div><StatusBadge value={jobStatus(detail.job.status)} /></header>
          <dl className="platform-detail-grid"><div><dt>任务 ID</dt><dd><code>{detail.job.id}</code></dd></div><div><dt>权限版本</dt><dd><code>{detail.permission_set_version}</code></dd></div><div><dt>Request ID</dt><dd><code>{detail.job.request_id}</code></dd></div><div><dt>Run ID</dt><dd><code>{detail.job.run_id}</code></dd></div></dl>
          <section className="platform-json-section"><h3>任务载荷</h3><pre>{JSON.stringify(detail.payload, null, 2)}</pre></section>
          <section className="platform-attempt-list"><h3>执行时间线</h3>{detail.attempts.map((attempt) => <article key={attempt.attempt_no}><span>{attempt.attempt_no}</span><div><strong>{jobStatusLabel(attempt.status)}</strong><small>{attempt.worker_id} · {formatTime(attempt.started_at)}</small>{attempt.error_message ? <p>{attempt.error_code} · {attempt.error_message}</p> : null}</div></article>)}</section>
          {canManage && ["failed", "cancelled"].includes(detail.job.status) ? <footer className="platform-detail-action"><button className="button primary" disabled={saving} onClick={() => setRetryOpen(true)} type="button"><RotateCcw size={15} />重新排队</button></footer> : null}
        </> : <div className="platform-empty-state"><ServerCog size={25} /><strong>选择一个后台任务</strong></div>}
      </aside>
    </div>
    {retryOpen && detail ? <ConfirmDialog busy={saving} confirmDisabled={reason.trim().length < 3} confirmLabel="确认重新排队" description={`重新执行 ${detail.job.job_type}？`} detail={`当前任务已执行 ${detail.job.attempt} 次，新的尝试会保留原 Attempt 时间线。`} onCancel={() => setRetryOpen(false)} onConfirm={() => void retry()} title="重试后台任务" tone="warning"><label className="confirm-input-field"><span>重试原因</span><textarea autoFocus onChange={(event) => setReason(event.target.value)} rows={3} value={reason} /></label></ConfirmDialog> : null}
  </div>;
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) { return <article><span>{icon}{label}</span><strong>{value}</strong></article>; }
function jobStatus(value: string) { return { label: jobStatusLabel(value), tone: value === "succeeded" ? "positive" as const : value === "failed" || value === "cancelled" ? "critical" as const : value === "running" ? "info" as const : "warning" as const }; }
function jobStatusLabel(value: string): string { return ({ queued: "排队", running: "运行中", retry_wait: "等待重试", succeeded: "成功", failed: "失败", cancelled: "已取消", timed_out: "超时", retry_scheduled: "已安排重试", continued: "已续跑" } as Record<string, string>)[value] ?? value; }
function formatTime(value: string): string { return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(value)); }
function requestKey(prefix: string): string { return `${prefix}-${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now()}`; }
function JobState({ title }: { title: string }) { return <div className="platform-page-state"><LoaderCircle className="spinning" size={27} /><strong>{title}</strong></div>; }
