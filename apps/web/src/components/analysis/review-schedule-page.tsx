"use client";

import {
  Bot,
  CalendarClock,
  CheckCircle2,
  CirclePause,
  CirclePlay,
  Clock3,
  FileCheck2,
  LoaderCircle,
  ListChecks,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  TriangleAlert,
  X
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useNotifications } from "@/components/console/interaction";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type { Tone } from "@/lib/experience-types";
import type {
  ReviewAutoPriority,
  ReviewRunStatus,
  StoreReviewPlan,
  StoreReviewPlanMutationResponse,
  StoreReviewSchedule,
  StoreReviewScheduleRun
} from "@/lib/review-schedule-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const WEEKDAYS = [
  { value: 1, label: "一" }, { value: 2, label: "二" }, { value: 3, label: "三" },
  { value: 4, label: "四" }, { value: 5, label: "五" }, { value: 6, label: "六" },
  { value: 7, label: "日" }
];
const STATUS_LABELS: Record<ReviewRunStatus, string> = {
  preparing: "准备入队",
  queued: "等待 Worker",
  running: "正在巡店",
  succeeded: "已完成",
  failed: "运行失败"
};

function formatDateTime(value: string | null, timeZone = "Asia/Shanghai"): string {
  if (!value) return "尚未运行";
  const zonedValue = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone
  }).format(new Date(zonedValue));
}

function statusTone(status: ReviewRunStatus): Tone {
  if (status === "succeeded") return "positive";
  if (status === "failed") return "critical";
  if (status === "running") return "info";
  return "warning";
}

function autoPolicyLabel(value: ReviewAutoPriority): string {
  if (value === "off") return "只生成简报";
  return value === "urgent" ? "仅紧急建议自动送审" : "高风险及以上自动送审";
}

export function ReviewSchedulePage() {
  const { roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<StoreReviewSchedule | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showComposer, setShowComposer] = useState(false);
  const [selectedPlanKey, setSelectedPlanKey] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const actionKeys = useRef(new Map<string, string>());

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setRefreshing(true);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/analysis/review-plans`, {
        cache: "no-store",
        headers: { "X-Zhixing-Demo-Actor": roleId }
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取巡店计划"));
      const payload = (await response.json()) as StoreReviewSchedule;
      setData(payload);
      setError(null);
      setSelectedPlanKey((current) => current && payload.plans.some((item) => item.key === current)
        ? current
        : payload.plans[0]?.key ?? null);
    } finally {
      if (!quiet) setRefreshing(false);
    }
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    setData(null);
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取巡店计划"))
      .finally(() => setLoading(false));
  }, [load]);

  const hasLiveRun = data?.runs.some((item) => ["preparing", "queued", "running"].includes(item.status)) ?? false;
  useEffect(() => {
    if (!hasLiveRun) return;
    const timer = window.setInterval(() => void load(true).catch(() => undefined), 2500);
    return () => window.clearInterval(timer);
  }, [hasLiveRun, load]);

  const selectedPlan = useMemo(
    () => data?.plans.find((item) => item.key === selectedPlanKey) ?? data?.plans[0] ?? null,
    [data, selectedPlanKey]
  );

  const act = useCallback(async (plan: StoreReviewPlan, action: "pause" | "resume" | "run_now") => {
    const operation = `${plan.key}:${action}`;
    const idempotencyKey = actionKeys.current.get(operation) ?? `review-plan-action:${crypto.randomUUID()}`;
    actionKeys.current.set(operation, idempotencyKey);
    setBusyAction(operation);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/analysis/review-plans/${encodeURIComponent(plan.key)}/actions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({
          action,
          expected_version: action === "run_now" ? null : plan.version,
          idempotency_key: idempotencyKey
        })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "巡店计划操作失败"));
      const payload = (await response.json()) as StoreReviewPlanMutationResponse;
      setData(payload.schedule);
      actionKeys.current.delete(operation);
      notify({ title: action === "run_now" ? "巡店任务已入队" : action === "pause" ? "巡店计划已暂停" : "巡店计划已恢复", tone: "success" });
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "巡店计划操作失败");
    } finally {
      setBusyAction(null);
    }
  }, [notify, roleId]);

  if (loading && !data) return <ScheduleState loading />;
  if (!data) return <ScheduleState error={error ?? "巡店计划暂不可用"} />;

  return (
    <div className="review-schedule-page">
      <PageHeader
        actions={<div className="review-schedule-header-actions">
          <button className="button secondary" disabled={refreshing} onClick={() => void load().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "刷新失败"))} type="button"><RefreshCw className={refreshing ? "spinning" : ""} size={15} />刷新运行</button>
          {data.can_manage ? <button className="button primary" onClick={() => setShowComposer((value) => !value)} type="button">{showComposer ? <X size={16} /> : <Plus size={16} />}{showComposer ? "收起编排" : "新建巡店计划"}</button> : null}
        </div>}
        description="按企业业务时间自动冻结指标与规范经营事实，通过 Worker 生成诊断和简报；高优先级建议最多进入人工审批，不会自动批准或写店铺系统。"
        eyebrow="智能分析中心 · 自动巡店"
        meta={`数据库视图 · ${data.actor_name}`}
        title="巡店计划与经营预警"
      />

      {error ? <InlineCallout description={error} title="本次操作未完成" tone="critical" /> : null}
      {!data.can_manage ? <InlineCallout description="当前角色可以查看授权范围内的巡店结果、简报和待审批建议，但不能创建或修改自动计划。" title="只读运营指导" tone="info" /> : null}
      {showComposer && data.can_manage ? <PlanComposer data={data} onCancel={() => setShowComposer(false)} onCreated={(payload) => { setData(payload); setShowComposer(false); notify({ title: "巡店计划已创建", tone: "success" }); }} onError={setError} roleId={roleId} /> : null}

      <ScheduleStats data={data} />
      <div className="review-schedule-workspace">
        <section className="review-plan-index">
          <header><div><span>GOVERNED SCHEDULES</span><h2>巡店计划</h2></div><strong>{data.plans.length} 项</strong></header>
          {data.plans.length ? <div>{data.plans.map((plan) => <button className={plan.key === selectedPlan?.key ? "active" : ""} key={plan.key} onClick={() => setSelectedPlanKey(plan.key)} type="button"><span><strong>{plan.name}</strong><small>{plan.scope.label} · {plan.local_time} · 周{plan.weekdays.join("/")}</small></span><StatusBadge value={{ label: plan.status === "active" ? "运行中" : "已暂停", tone: plan.status === "active" ? "positive" : "neutral" }} /></button>)}</div> : <div className="review-plan-empty"><CalendarClock size={24} /><strong>尚未建立巡店计划</strong><span>负责人可从一个授权门店开始建立首个工作日巡检。</span></div>}
        </section>
        <section className="review-plan-detail">
          {selectedPlan ? <>
            <header><div><span>{selectedPlan.scope.type} · v{selectedPlan.version}</span><h2>{selectedPlan.name}</h2><p>{autoPolicyLabel(selectedPlan.auto_propose_min_priority)}</p></div><StatusBadge value={{ label: selectedPlan.status === "active" ? "已启用" : "已暂停", tone: selectedPlan.status === "active" ? "positive" : "neutral" }} /></header>
            <dl><div><dt>授权范围</dt><dd>{selectedPlan.scope.label}</dd></div><div><dt>观察窗口</dt><dd>{selectedPlan.window_days} 天</dd></div><div><dt>运行日</dt><dd>周 {selectedPlan.weekdays.join(" / ")}</dd></div><div><dt>业务时间</dt><dd>{selectedPlan.local_time} · {selectedPlan.timezone}</dd></div><div><dt>下次运行</dt><dd>{selectedPlan.status === "active" ? formatDateTime(selectedPlan.next_run_at, selectedPlan.timezone) : "计划已暂停"}</dd></div><div><dt>创建主体</dt><dd>{selectedPlan.created_by_name}</dd></div></dl>
            <div className="review-plan-boundary"><ShieldCheck size={17} /><div><strong>自动化边界</strong><span>冻结数据、生成诊断与简报{selectedPlan.auto_propose_min_priority === "off" ? "；不自动创建行动提案。" : "；命中阈值的建议只进入待审批状态。"}</span></div></div>
            {data.can_manage ? <footer><button className="button primary" disabled={busyAction !== null} onClick={() => void act(selectedPlan, "run_now")} type="button">{busyAction === `${selectedPlan.key}:run_now` ? <LoaderCircle className="spinning" size={15} /> : <Play size={15} />}立即巡店</button><button className="button secondary" disabled={busyAction !== null} onClick={() => void act(selectedPlan, selectedPlan.status === "active" ? "pause" : "resume")} type="button">{selectedPlan.status === "active" ? <Pause size={15} /> : <RotateCcw size={15} />}{selectedPlan.status === "active" ? "暂停计划" : "恢复计划"}</button></footer> : null}
          </> : <div className="review-plan-detail-empty"><CalendarClock size={30} /><strong>选择巡店计划</strong><span>查看业务时间、自动送审边界和最近运行。</span></div>}
        </section>
      </div>
      <RunLedger runs={data.runs} />
    </div>
  );
}

function PlanComposer({ data, onCancel, onCreated, onError, roleId }: { data: StoreReviewSchedule; onCancel: () => void; onCreated: (data: StoreReviewSchedule) => void; onError: (message: string) => void; roleId: string }) {
  const [name, setName] = useState("每日经营风险巡检");
  const [scopeKey, setScopeKey] = useState(data.available_scopes[0]?.key ?? "");
  const [windowDays, setWindowDays] = useState(30);
  const [localTime, setLocalTime] = useState("09:00");
  const [weekdays, setWeekdays] = useState([1, 2, 3, 4, 5]);
  const [policy, setPolicy] = useState<ReviewAutoPriority>("high");
  const [submitting, setSubmitting] = useState(false);
  const requestKey = useRef<string | null>(null);

  const submit = async () => {
    requestKey.current ??= `review-plan:${crypto.randomUUID()}`;
    setSubmitting(true);
    onError("");
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/analysis/review-plans`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ name, scope_key: scopeKey, window_days: windowDays, timezone: "Asia/Shanghai", local_time: localTime, weekdays, auto_propose_min_priority: policy, client_request_key: requestKey.current })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "创建巡店计划失败"));
      const payload = (await response.json()) as StoreReviewPlanMutationResponse;
      requestKey.current = null;
      onCreated(payload.schedule);
    } catch (reason: unknown) {
      onError(reason instanceof Error ? reason.message : "创建巡店计划失败");
    } finally {
      setSubmitting(false);
    }
  };

  return <section className="review-plan-composer"><header><div><span>SCHEDULE COMPOSER</span><h2>巡店计划编排</h2></div><button aria-label="关闭巡店计划编排" className="icon-button" onClick={onCancel} title="关闭" type="button"><X size={17} /></button></header><div className="review-plan-form"><label><span>计划名称</span><input onChange={(event) => setName(event.target.value)} value={name} /></label><label><span>数据范围</span><select onChange={(event) => setScopeKey(event.target.value)} value={scopeKey}>{data.available_scopes.map((scope) => <option key={scope.key} value={scope.key}>{scope.label}</option>)}</select></label><label><span>运行时间</span><input onChange={(event) => setLocalTime(event.target.value)} type="time" value={localTime} /></label><label><span>观察窗口</span><select onChange={(event) => setWindowDays(Number(event.target.value))} value={windowDays}><option value={14}>14 天</option><option value={30}>30 天</option><option value={60}>60 天</option><option value={90}>90 天</option></select></label><label><span>建议送审策略</span><select onChange={(event) => setPolicy(event.target.value as ReviewAutoPriority)} value={policy}><option value="off">只生成简报</option><option value="urgent">仅紧急建议送审</option><option value="high">高风险及以上送审</option></select></label><fieldset><legend>运行星期</legend><div>{WEEKDAYS.map((day) => <label key={day.value}><input checked={weekdays.includes(day.value)} onChange={(event) => setWeekdays((current) => event.target.checked ? [...current, day.value].sort() : current.filter((item) => item !== day.value))} type="checkbox" /><span>{day.label}</span></label>)}</div></fieldset></div><footer><div><ShieldCheck size={16} /><span>Worker 运行时重新校验计划创建人的当前权限和范围。</span></div><button className="button primary" disabled={submitting || name.trim().length < 2 || !scopeKey || weekdays.length === 0} onClick={() => void submit()} type="button">{submitting ? <LoaderCircle className="spinning" size={15} /> : <CheckCircle2 size={15} />}{submitting ? "正在创建" : "创建计划"}</button></footer></section>;
}

function ScheduleStats({ data }: { data: StoreReviewSchedule }) {
  const items = [
    { label: "计划总数", value: data.stats.plan_count, note: "当前授权范围", icon: CalendarClock },
    { label: "启用计划", value: data.stats.active_plan_count, note: "等待业务时间", icon: CirclePlay },
    { label: "队列运行", value: data.stats.queued_or_running_count, note: "Worker 处理", icon: Bot },
    { label: "成功运行", value: data.stats.succeeded_count, note: "已生成简报", icon: FileCheck2 },
    { label: "待审批建议", value: data.stats.pending_proposal_count, note: "不会自动批准", icon: ListChecks }
  ];
  return <section className="review-schedule-stats">{items.map((item) => { const Icon = item.icon; return <article key={item.label}><Icon size={18} /><span>{item.label}</span><strong>{item.value}</strong><small>{item.note}</small></article>; })}</section>;
}

function RunLedger({ runs }: { runs: StoreReviewScheduleRun[] }) {
  return <section className="review-run-ledger"><header><div><span>WORKER RUN LEDGER</span><h2>巡店运行台账</h2></div><strong>{runs.length} 次</strong></header>{runs.length ? <div className="review-run-table"><table><thead><tr><th>业务日 / 计划</th><th>范围</th><th>触发</th><th>状态</th><th>结果</th><th>队列</th><th>完成时间</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td><strong>{run.business_date}</strong><small>{run.plan_name}</small></td><td>{run.scope.label}</td><td>{run.trigger_type === "scheduled" ? <><Clock3 size={13} />定时</> : <><Play size={13} />手动</>}</td><td><StatusBadge value={{ label: STATUS_LABELS[run.status], tone: statusTone(run.status) }} /></td><td>{run.status === "succeeded" ? <span className="review-run-result"><strong>{run.execution_mode === "model" ? "真实模型" : "证据降级"}</strong><small>{run.proposal_count} 条建议送审</small></span> : run.status === "failed" ? <span className="review-run-error"><strong>{run.error_code}</strong><small>{run.error_message}</small></span> : "等待结果"}</td><td><code>{run.background_job_id?.slice(-12) ?? "准备中"}</code><small>尝试 {run.background_job_attempt}</small></td><td>{formatDateTime(run.completed_at)}</td></tr>)}</tbody></table></div> : <div className="review-run-empty"><CirclePause size={24} /><strong>暂无巡店运行</strong><span>计划到达业务时间，或负责人点击“立即巡店”后，运行会进入这里。</span></div>}<footer><Link className="button secondary" href="/console/analysis/briefs"><FileCheck2 size={15} />查看经营简报</Link><Link className="button secondary" href="/console/actions/approvals"><ListChecks size={15} />查看审批队列</Link></footer></section>;
}

function ScheduleState({ error, loading = false }: { error?: string; loading?: boolean }) {
  return <div className={`analysis-center-state ${error ? "failed" : ""}`} role={error ? "alert" : "status"}>{error ? <TriangleAlert size={28} /> : <LoaderCircle className={loading ? "spinning" : ""} size={28} />}<strong>{error ? "巡店计划暂不可用" : "正在读取巡店计划"}</strong><span>{error ?? "加载计划、Worker 任务、分析运行和待审批建议"}</span></div>;
}
