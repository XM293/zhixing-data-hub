"use client";

import {
  Activity,
  Check,
  CheckCircle2,
  CircleAlert,
  Clock3,
  FlaskConical,
  Gauge,
  History,
  LoaderCircle,
  Play,
  ShieldCheck,
  TriangleAlert,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type {
  EvaluationCase,
  EvaluationCandidate,
  EvaluationCandidateMutationResponse,
  EvaluationMutationResponse,
  EvaluationOutcome,
  EvaluationRun,
  EvaluationRunItem,
  EvaluationStudioResponse
} from "@/lib/evaluation-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const OUTCOME_LABELS: Record<EvaluationOutcome, string> = {
  passed: "自动通过",
  failed: "检查失败",
  review_required: "待人工复核",
  error: "运行异常"
};

const DOMAIN_LABELS: Record<string, string> = {
  knowledge: "制度知识",
  "role-twin": "角色行为",
  metric: "经营指标",
  authorization: "权限边界",
  meeting: "数字会议",
  tool: "工具调用"
};

function formatTime(value: string | null): string {
  if (!value) return "运行中";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function outcomeTone(outcome: EvaluationOutcome) {
  if (outcome === "passed") return "positive" as const;
  if (outcome === "review_required") return "warning" as const;
  return "critical" as const;
}

export function EvaluationStudioPage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [studio, setStudio] = useState<EvaluationStudioResponse | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedCaseKey, setSelectedCaseKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [reviewingCandidateId, setReviewingCandidateId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [candidateDecision, setCandidateDecision] = useState<{ candidate: EvaluationCandidate; action: "accept" | "reject" } | null>(null);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const canRun = can("evaluation.run");
  const canManage = can("evaluation.manage");

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/evaluations/studio`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取回归评测中心"));
    const result = (await response.json()) as EvaluationStudioResponse;
    setStudio(result);
    const firstRun = result.suites[0]?.latest_run;
    setSelectedRunId((current) =>
      result.suites.some((suite) => suite.recent_runs.some((run) => run.id === current))
        ? current
        : firstRun?.id ?? null
    );
    setSelectedCaseKey((current) =>
      result.suites.some((suite) => suite.cases.some((item) => item.key === current))
        ? current
        : result.suites[0]?.cases[0]?.key ?? null
    );
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "回归评测中心连接失败")
      )
      .finally(() => setLoading(false));
  }, [load]);

  const suite = studio?.suites[0] ?? null;
  const selectedRun = useMemo(
    () => suite?.recent_runs.find((item) => item.id === selectedRunId) ?? suite?.latest_run ?? null,
    [selectedRunId, suite]
  );
  const selectedCase = useMemo(
    () => suite?.cases.find((item) => item.key === selectedCaseKey) ?? suite?.cases[0] ?? null,
    [selectedCaseKey, suite]
  );
  const selectedItem = useMemo(
    () => selectedRun?.items.find((item) => item.case_key === selectedCase?.key) ?? null,
    [selectedCase, selectedRun]
  );

  async function runSuite() {
    if (!suite) return;
    setRunning(true);
    setError(null);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/evaluation-suites/${encodeURIComponent(suite.key)}/runs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Zhixing-Demo-Actor": roleId
          },
          body: JSON.stringify({
            client_request_key: `web-${roleId}-${Date.now()}`,
            case_keys: []
          })
        }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "批量评测未完成"));
      const result = (await response.json()) as EvaluationMutationResponse;
      setStudio(result.studio);
      setSelectedRunId(result.run.id);
      setSelectedCaseKey(result.run.items[0]?.case_key ?? null);
      notify({ title: "批量评测已完成", description: `${result.run.passed_count}/${result.run.total_count} 项自动通过 · ${result.run.review_required_count} 项待复核`, tone: "success" });
    } catch (reason: unknown) {
      notify({ title: "批量评测未完成", description: reason instanceof Error ? reason.message : "评测服务返回异常", tone: "error" });
    } finally {
      setRunning(false);
    }
  }

  async function reviewCandidate(
    candidate: EvaluationCandidate,
    action: "accept" | "reject"
  ) {
    setReviewingCandidateId(candidate.id);
    setCandidateError(null);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/evaluation-candidates/${encodeURIComponent(candidate.id)}/actions`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Zhixing-Demo-Actor": roleId
          },
          body: JSON.stringify({
            action,
            suite_key: suite?.key ?? "m1-role-twin-smoke",
            reason: action === "accept"
              ? "经评测负责人复核，纠正结论明确，纳入固定回归案例。"
              : "经评测负责人复核，当前反馈不适合进入固定回归集。",
            client_request_key: `web-${candidate.id}-${action}-${Date.now().toString(36)}`
          })
        }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "评测候选审核未完成"));
      const result = (await response.json()) as EvaluationCandidateMutationResponse;
      setStudio(result.studio);
      if (action === "accept") setSelectedCaseKey(candidate.proposed_case_key);
      notify({ title: action === "accept" ? "候选已接纳" : "候选已拒绝", description: candidate.proposed_title, tone: "success" });
      setCandidateDecision(null);
    } catch (reason: unknown) {
      setCandidateError(reason instanceof Error ? reason.message : "评测候选审核未完成");
    } finally {
      setReviewingCandidateId(null);
    }
  }

  if (loading) {
    return <EvaluationState icon={<LoaderCircle className="spinning" />} title="正在读取评测套件与基线" />;
  }
  if (!studio || !suite || !selectedCase) {
    return <EvaluationState icon={<CircleAlert />} title={error ?? "回归评测中心暂不可用"} />;
  }

  return (
    <div className="evaluation-page">
      <PageHeader
        actions={
          <button className="button primary" disabled={!canRun || running} onClick={() => void runSuite()} type="button">
            {running ? <LoaderCircle aria-hidden="true" className="spinning" size={16} /> : <Play aria-hidden="true" size={16} />}
            {running ? "正在批量运行" : "运行全部固定案例"}
          </button>
        }
        description="在知识、指标、权限或角色配置变更后，使用固定数据库身份批量验证回答质量与边界。"
        eyebrow="分身中心 · 持续评测"
        meta={`DATABASE · SUITE V${suite.version_number}`}
        title="智能体回归评测"
      />
      {!canRun ? (
        <InlineCallout description="当前身份可查看基线结果，但批量运行需要 evaluation.run 权限。" title="只读评测视图" tone="info" />
      ) : null}
      {error ? <InlineCallout description={error} title="评测请求未完成" tone="critical" /> : null}
      <EvaluationStats studio={studio} run={suite.latest_run} />
      <EvaluationCandidateQueue
        canManage={canManage}
        candidates={studio.candidates}
        onReview={(candidate, action) => { setCandidateError(null); setCandidateDecision({ candidate, action }); }}
        reviewingCandidateId={reviewingCandidateId}
      />
      <section className="evaluation-workbench">
        <aside className="evaluation-case-rail">
          <header>
            <div><span>VERSIONED CASES</span><h2>固定案例</h2></div>
            <strong>{suite.cases.length}</strong>
          </header>
          <div>
            {suite.cases.map((item) => {
              const result = selectedRun?.items.find((runItem) => runItem.case_key === item.key);
              return (
                <button className={item.key === selectedCase.key ? "active" : ""} key={item.key} onClick={() => setSelectedCaseKey(item.key)} type="button">
                  <span className={`evaluation-risk ${item.risk_level}`}>{item.risk_level}</span>
                  <div>
                    <small>{DOMAIN_LABELS[item.domain] ?? item.domain} · v{item.version_number}</small>
                    <strong>{item.title}</strong>
                    <p>{item.input.question}</p>
                    {result ? <StatusBadge value={{ label: OUTCOME_LABELS[result.outcome], tone: outcomeTone(result.outcome) }} /> : <em>尚无运行结果</em>}
                  </div>
                </button>
              );
            })}
          </div>
        </aside>
        <main className="evaluation-result-panel">
          <EvaluationCaseHeader item={selectedCase} />
          {selectedItem && selectedRun ? (
            <EvaluationResult item={selectedItem} run={selectedRun} />
          ) : (
            <div className="evaluation-empty"><FlaskConical size={28} /><strong>这个案例尚未形成基线</strong><span>运行全部固定案例后，检查明细会写入这里。</span></div>
          )}
        </main>
      </section>
      <EvaluationHistory runs={suite.recent_runs} selectedRunId={selectedRun?.id ?? null} onSelect={setSelectedRunId} />
      {candidateDecision ? <ConfirmDialog busy={reviewingCandidateId === candidateDecision.candidate.id} confirmLabel={candidateDecision.action === "accept" ? "接纳为案例" : "确认拒绝"} description={`${candidateDecision.action === "accept" ? "接纳" : "拒绝"}“${candidateDecision.candidate.proposed_title}”？`} detail={candidateDecision.action === "accept" ? "接纳后将冻结为版本化评测案例，并参与后续批量回归。" : "拒绝后原始反馈与审核结论继续保留。"} onCancel={() => setCandidateDecision(null)} onConfirm={() => void reviewCandidate(candidateDecision.candidate, candidateDecision.action)} title={candidateDecision.action === "accept" ? "接纳评测候选" : "拒绝评测候选"} tone={candidateDecision.action === "accept" ? "warning" : "danger"}>{candidateError ? <InlineCallout description={candidateError} title="审核未完成" tone="critical" /> : null}</ConfirmDialog> : null}
    </div>
  );
}

function EvaluationStats({ studio, run }: { studio: EvaluationStudioResponse; run: EvaluationRun | null }) {
  const items = [
    { icon: Gauge, label: "最新通过率", value: run ? `${Math.round(run.pass_rate * 100)}%` : "--", detail: run ? `${run.passed_count}/${run.total_count} 自动通过` : "等待首轮基线" },
    { icon: CheckCircle2, label: "自动通过", value: String(run?.passed_count ?? 0), detail: "全部确定性检查通过" },
    { icon: TriangleAlert, label: "待人工复核", value: String(run?.review_required_count ?? 0), detail: "表达与业务判断人工确认" },
    { icon: History, label: "历史运行", value: String(studio.stats.run_count), detail: run?.baseline_run_id ? "已关联上一版基线" : "首版基线" },
    { icon: Clock3, label: "待治理案例", value: String(studio.stats.pending_candidate_count), detail: `${studio.stats.candidate_count} 条纠错候选` },
    { icon: Activity, label: "总耗时", value: run ? `${(run.duration_ms / 1000).toFixed(1)}s` : "--", detail: run ? `${run.model} · ${run.provider}` : "等待运行" }
  ];
  return <section className="evaluation-stat-band" aria-label="评测运行统计">{items.map(({ icon: Icon, ...item }) => <article key={item.label}><span><Icon aria-hidden="true" size={16} />{item.label}</span><strong>{item.value}</strong><p>{item.detail}</p></article>)}</section>;
}

function EvaluationCandidateQueue({
  canManage,
  candidates,
  onReview,
  reviewingCandidateId
}: {
  canManage: boolean;
  candidates: EvaluationCandidate[];
  onReview: (candidate: EvaluationCandidate, action: "accept" | "reject") => void;
  reviewingCandidateId: string | null;
}) {
  if (!candidates.length) return null;
  return (
    <section className="evaluation-candidate-queue" aria-label="反馈评测候选">
      <header>
        <div><span>FEEDBACK TO EVALUATION</span><h2>人工纠错候选</h2></div>
        <strong>{candidates.filter((item) => item.status === "pending").length} 待审核</strong>
      </header>
      <div>
        {candidates.map((candidate) => {
          const busy = reviewingCandidateId === candidate.id;
          const tone = candidate.status === "accepted" ? "positive" : candidate.status === "rejected" ? "critical" : "warning";
          const label = candidate.status === "accepted" ? "已进入回归集" : candidate.status === "rejected" ? "已拒绝" : "待审核";
          return (
            <article key={candidate.id}>
              <header>
                <div><small>{DOMAIN_LABELS[candidate.domain] ?? candidate.domain} · {candidate.risk_level.toUpperCase()}</small><strong>{candidate.proposed_title}</strong></div>
                <StatusBadge value={{ label, tone }} />
              </header>
              <blockquote>{candidate.input.question}</blockquote>
              <div className="evaluation-candidate-resolution"><span>人工纠正结论</span><p>{candidate.resolution_summary}</p></div>
              <footer>
                <span>{candidate.proposed_by_name} · {formatTime(candidate.created_at)}</span>
                {candidate.status === "pending" && canManage ? <div><button className="button secondary compact" disabled={busy} onClick={() => onReview(candidate, "reject")} type="button"><X size={14} />拒绝</button><button className="button primary compact" disabled={busy} onClick={() => onReview(candidate, "accept")} type="button">{busy ? <LoaderCircle className="spinning" size={14} /> : <Check size={14} />}接纳为案例</button></div> : null}
                {candidate.status !== "pending" ? <small>{candidate.reviewed_by_name} · {candidate.review_reason}</small> : null}
              </footer>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function EvaluationCaseHeader({ item }: { item: EvaluationCase }) {
  return <header className="evaluation-case-header"><div><span>{DOMAIN_LABELS[item.domain] ?? item.domain} · {item.risk_level.toUpperCase()} RISK</span><h2>{item.title}</h2></div><code>{item.key} / v{item.version_number}</code><blockquote>{item.input.question}</blockquote><div><span><ShieldCheck size={15} />可信身份：{item.actor_login_name}</span><span><FlaskConical size={15} />目标分身：{item.target_twin_key}</span><span><Gauge size={15} />Top K：{item.input.top_k ?? "--"}</span></div></header>;
}

function EvaluationResult({ item, run }: { item: EvaluationRunItem; run: EvaluationRun }) {
  return <div className="evaluation-result"><header><div><span>RUN RESULT</span><h3>{OUTCOME_LABELS[item.outcome]}</h3></div><StatusBadge value={{ label: OUTCOME_LABELS[item.outcome], tone: outcomeTone(item.outcome) }} /></header><div className="evaluation-run-meta"><span><small>Agent Run</small><code>{item.agent_run_id ?? item.observed_error_code ?? "未生成"}</code></span><span><small>执行身份</small><strong>{item.actor_name}</strong></span><span><small>模型</small><strong>{run.model}</strong></span><span><small>耗时</small><strong>{item.duration_ms} ms</strong></span></div><div className="evaluation-check-table"><header><div><span>DETERMINISTIC CHECK MATRIX</span><h3>自动检查明细</h3></div><strong>{item.checks.filter((check) => check.passed).length}/{item.checks.length}</strong></header><div className="evaluation-check-head"><span>检查项</span><span>预期</span><span>实际</span><span>结果</span></div>{item.checks.map((check) => <div className={check.passed ? "passed" : "failed"} key={check.key}><span>{check.passed ? <Check size={15} /> : <X size={15} />}<strong>{check.label}</strong><small>{check.key}</small></span><code>{check.expected}</code><code>{check.actual}</code><b>{check.passed ? "PASS" : "FAIL"}</b></div>)}</div>{item.outcome === "review_required" ? <div className="evaluation-review-note"><Clock3 size={18} /><div><strong>自动检查已通过，仍需人工复核</strong><span>角色语气、判断方式和业务可用性不应只由关键词规则决定。</span></div></div> : null}</div>;
}

function EvaluationHistory({ runs, selectedRunId, onSelect }: { runs: EvaluationRun[]; selectedRunId: string | null; onSelect: (id: string) => void }) {
  return <section className="evaluation-history"><header><History size={18} /><div><span>VERSION COMPARISON</span><strong>运行历史与基线变化</strong></div></header><div><table><thead><tr><th>运行时间</th><th>版本与模型</th><th>结果</th><th>通过率</th><th>基线变化</th><th>发起人</th></tr></thead><tbody>{runs.length ? runs.map((run) => <tr className={run.id === selectedRunId ? "active" : ""} key={run.id} onClick={() => onSelect(run.id)}><td><strong>{formatTime(run.completed_at)}</strong><code>{run.id}</code></td><td><strong>Suite v{run.suite_version_number}</strong><span>{run.model}</span></td><td><span>{run.passed_count} 通过 · {run.review_required_count} 复核 · {run.failed_count + run.error_count} 异常</span></td><td><strong>{Math.round(run.pass_rate * 100)}%</strong></td><td><strong>{run.pass_rate_delta === null ? "首版" : `${run.pass_rate_delta >= 0 ? "+" : ""}${Math.round(run.pass_rate_delta * 100)} pt`}</strong></td><td><span>{run.initiated_by_name}</span></td></tr>) : <tr><td colSpan={6}>尚无评测运行</td></tr>}</tbody></table></div></section>;
}

function EvaluationState({ icon, title }: { icon: React.ReactNode; title: string }) {
  return <div className="evaluation-page-state">{icon}<strong>{title}</strong></div>;
}
