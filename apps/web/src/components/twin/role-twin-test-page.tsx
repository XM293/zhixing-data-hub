"use client";

import {
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  Clock3,
  Database,
  FileSearch,
  FlaskConical,
  History,
  LoaderCircle,
  Play,
  RefreshCw,
  ShieldCheck,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Dialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiErrorMessage } from "@/lib/api-error";
import { apiFetch } from "@/lib/api-client";
import type {
  RoleTwinTestCase,
  RoleTwinTestDecision,
  RoleTwinTestMutationResponse,
  RoleTwinTestReview,
  RoleTwinTestRun,
  RoleTwinTestStudioResponse
} from "@/lib/role-twin-test-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const CATEGORY_LABELS = {
  knowledge: "制度知识",
  data: "经营数据",
  boundary: "边界约束",
  style: "角色表达",
  decision: "决策规则"
} as const;

const DECISION_LABELS: Record<RoleTwinTestDecision, string> = {
  pass: "通过",
  needs_revision: "需要修正",
  fail: "不通过"
};

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function reviewTone(decision: RoleTwinTestDecision) {
  if (decision === "pass") return "positive" as const;
  if (decision === "fail") return "critical" as const;
  return "warning" as const;
}

function riskLabel(risk: RoleTwinTestCase["risk_level"]): string {
  return { low: "低风险", medium: "中风险", high: "高风险" }[risk];
}

export function RoleTwinTestPage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [studio, setStudio] = useState<RoleTwinTestStudioResponse | null>(null);
  const [selectedCaseKey, setSelectedCaseKey] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedTwinKey, setSelectedTwinKey] = useState("");
  const [reviewRun, setReviewRun] = useState<RoleTwinTestRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canRun = can("role-twin.invoke");
  const canReview = can("role-twin.configure");

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/role-twin-test-studio`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取角色分身试跑台"));
    const result = (await response.json()) as RoleTwinTestStudioResponse;
    setStudio(result);
    setSelectedCaseKey((current) => result.cases.some((item) => item.key === current) ? current : result.cases[0]?.key ?? null);
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "角色试跑台连接失败"))
      .finally(() => setLoading(false));
  }, [load]);

  const selectedCase = useMemo(
    () => studio?.cases.find((item) => item.key === selectedCaseKey) ?? studio?.cases[0] ?? null,
    [selectedCaseKey, studio]
  );
  const selectedRun = useMemo(
    () => selectedCase?.runs.find((item) => item.id === selectedRunId) ?? selectedCase?.runs[0] ?? null,
    [selectedCase, selectedRunId]
  );

  useEffect(() => {
    if (!selectedCase) return;
    setSelectedTwinKey(selectedCase.target_twin_key);
    setSelectedRunId(selectedCase.runs[0]?.id ?? null);
  }, [selectedCase?.key]);

  async function runCase() {
    if (!selectedCase || !selectedTwinKey) return;
    setRunning(true);
    setError(null);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/role-twin-test-cases/${encodeURIComponent(selectedCase.key)}/runs`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Zhixing-Demo-Actor": roleId
          },
          body: JSON.stringify({ twin_key: selectedTwinKey })
        }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "角色试跑未完成"));
      const result = (await response.json()) as RoleTwinTestMutationResponse;
      setStudio(result.studio);
      setSelectedRunId(result.run.id);
      notify({ title: "试跑已完成", description: `${result.run.twin_name} v${result.run.role_twin_version_number} · 等待人工审核`, tone: "success" });
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "角色试跑未完成");
    } finally {
      setRunning(false);
    }
  }

  function selectCase(testCase: RoleTwinTestCase) {
    setSelectedCaseKey(testCase.key);
    setSelectedTwinKey(testCase.target_twin_key);
    setSelectedRunId(testCase.runs[0]?.id ?? null);
  }

  if (loading) return <RoleTwinTestState icon={<LoaderCircle className="spinning" />} title="正在读取角色测试用例与运行记录" />;
  if (!studio || !selectedCase) return <RoleTwinTestState icon={<CircleAlert />} title={error ?? "角色分身试跑台暂不可用"} retry={() => void load()} />;

  return (
    <div className="role-test-page">
      <PageHeader
        actions={<button className="button secondary" onClick={() => void load()} type="button"><RefreshCw aria-hidden="true" size={15} />刷新数据库</button>}
        description="用固定问题真实调用已发布分身，保存实际版本、证据上下文和人工审核事件。"
        eyebrow="ROLE TWIN PILOT REVIEW · DATABASE + LIVE AI"
        meta={`数据库 · ${studio.stats.case_count} 个版本化用例`}
        title="角色分身试跑台"
      />
      {error ? <InlineCallout description={error} title="最近一次操作失败" tone="critical" /> : null}
      <RoleTwinTestStats studio={studio} />

      <div className="role-test-layout">
        <aside className="role-test-case-rail" aria-label="角色测试用例库">
          <header><div><span>VERSIONED CASE LIBRARY</span><h2>试跑用例</h2></div><strong>{studio.cases.length}</strong></header>
          <div className="role-test-case-list">
            {studio.cases.map((item) => {
              const latest = item.runs[0]?.latest_review;
              return (
                <button className={item.key === selectedCase.key ? "active" : ""} key={item.id} onClick={() => selectCase(item)} type="button">
                  <span className={`role-test-risk ${item.risk_level}`}>{riskLabel(item.risk_level)}</span>
                  <div><small>{CATEGORY_LABELS[item.category]} · v{item.version_number}</small><strong>{item.title}</strong><p>{item.question}</p></div>
                  <em>{latest ? DECISION_LABELS[latest.decision] : item.runs.length ? "待审核" : "未运行"}</em>
                </button>
              );
            })}
          </div>
        </aside>

        <main className="role-test-workspace">
          <section className="role-test-case-brief" aria-labelledby="role-test-case-title">
            <header>
              <div><span>{CATEGORY_LABELS[selectedCase.category]} · {riskLabel(selectedCase.risk_level)} · CASE v{selectedCase.version_number}</span><h2 id="role-test-case-title">{selectedCase.title}</h2></div>
              <StatusBadge value={{ label: selectedCase.status === "active" ? "有效用例" : "已退役", tone: selectedCase.status === "active" ? "positive" : "neutral" }} />
            </header>
            <blockquote>{selectedCase.question}</blockquote>
            <div className="role-test-expectations">
              <div><span><ShieldCheck aria-hidden="true" size={15} />预期行为</span>{selectedCase.expected_behaviors.map((item) => <p key={item}><CheckCircle2 aria-hidden="true" size={14} />{item}</p>)}</div>
              <div><span><FileSearch aria-hidden="true" size={15} />预期证据</span>{selectedCase.expected_evidence_refs.length ? selectedCase.expected_evidence_refs.map((item) => <code key={item}>{item}</code>) : <p><CircleAlert aria-hidden="true" size={14} />本用例预期明确说明无正式依据</p>}</div>
            </div>
            <div className="role-test-run-controls">
              <label><span>运行分身</span><select onChange={(event) => setSelectedTwinKey(event.target.value)} value={selectedTwinKey}>{studio.twins.map((item) => <option key={item.key} value={item.key}>{item.display_name} · {item.role_title} · v{item.current_version_number}{item.key === selectedCase.target_twin_key ? "（推荐）" : ""}</option>)}</select></label>
              <button className="button primary" disabled={!canRun || running} onClick={() => void runCase()} type="button">{running ? <LoaderCircle aria-hidden="true" className="spinning" size={16} /> : <Play aria-hidden="true" size={16} />}{running ? "正在调用真实模型" : "运行当前用例"}</button>
            </div>
            {!canRun ? <p className="permission-hint">当前身份没有分身调用权限，API 仍会执行最终授权判断。</p> : null}
          </section>

          {selectedRun ? (
            <RoleTwinRunResult canReview={canReview} onReview={() => setReviewRun(selectedRun)} run={selectedRun} />
          ) : (
            <div className="role-test-empty"><FlaskConical aria-hidden="true" size={28} /><strong>该用例尚未运行</strong><span>选择已发布分身后运行，系统会保存实际配置版本、模型和证据上下文。</span></div>
          )}

          {selectedCase.runs.length ? <RoleTwinRunHistory onSelect={setSelectedRunId} runs={selectedCase.runs} selectedRunId={selectedRun?.id ?? null} /> : null}
        </main>
      </div>

      {reviewRun ? (
        <RoleTwinReviewDialog
          onClose={() => setReviewRun(null)}
          onComplete={(result) => {
            setStudio(result.studio);
            setSelectedRunId(result.run.id);
            setReviewRun(null);
            notify({ title: "审核结论已追加", description: `${result.run.latest_review?.reviewer_name ?? "审核人"} · ${result.run.latest_review ? DECISION_LABELS[result.run.latest_review.decision] : "待审核"}`, tone: "success" });
          }}
          roleId={roleId}
          run={reviewRun}
        />
      ) : null}
    </div>
  );
}

function RoleTwinTestStats({ studio }: { studio: RoleTwinTestStudioResponse }) {
  const stats = studio.stats;
  const items = [
    { label: "版本化用例", value: stats.case_count, detail: "固定问题与预期行为", icon: Database },
    { label: "真实运行", value: stats.run_count, detail: "绑定实际分身版本", icon: FlaskConical },
    { label: "待人工审核", value: stats.pending_review_count, detail: "尚无审核结论", icon: Clock3 },
    { label: "人工通过率", value: stats.pass_rate === null ? "--" : `${Math.round(stats.pass_rate * 100)}%`, detail: `${stats.passed_count}/${stats.reviewed_count} 个已审运行`, icon: ClipboardCheck }
  ];
  return <section className="role-test-stat-band" aria-label="角色试跑统计">{items.map((item) => { const Icon = item.icon; return <article key={item.label}><span><Icon aria-hidden="true" size={16} />{item.label}</span><strong>{item.value}</strong><p>{item.detail}</p></article>; })}</section>;
}

function RoleTwinRunResult({ canReview, onReview, run }: { canReview: boolean; onReview: () => void; run: RoleTwinTestRun }) {
  const review = run.latest_review;
  return (
    <section className="role-test-result" aria-label="角色试跑结果">
      <header>
        <div><span>LIVE AGENT RUN</span><h2>{run.twin_name} · v{run.role_twin_version_number}</h2><p>{run.provider} / {run.model} · {run.duration_ms.toLocaleString("zh-CN")} ms</p></div>
        <div>{review ? <StatusBadge value={{ label: DECISION_LABELS[review.decision], tone: reviewTone(review.decision) }} /> : <StatusBadge value={{ label: "待审核", tone: "warning" }} />}{canReview ? <button className="button secondary compact" onClick={onReview} type="button"><ClipboardCheck aria-hidden="true" size={14} />{review ? "追加复核" : "人工审核"}</button> : null}</div>
      </header>
      <div className="role-test-run-meta">
        <span><small>运行 ID</small><code>{run.agent_run_id}</code></span>
        <span><small>执行模式</small><strong>{run.execution_mode === "model" ? "真实模型" : "证据降级"}</strong></span>
        <span><small>证据上下文</small><strong>D{run.metric_context_count} / E{run.evidence_count} / M{run.memory_context_count}</strong></span>
        <span><small>运行时间</small><strong>{formatTime(run.created_at)}</strong></span>
      </div>
      <div className="role-test-summary"><FlaskConical aria-hidden="true" size={19} /><div><span>结构化结论 · 置信度 {run.answer.confidence}</span><strong>{run.answer.summary}</strong></div></div>
      <div className="role-test-answer-grid">
        <section><span>可核验事实</span>{run.answer.facts.length ? run.answer.facts.map((item) => <p key={item}>{item}</p>) : <p>未形成可核验事实。</p>}</section>
        <section><span>建议动作</span>{run.answer.actions.map((item) => <p key={item}>{item}</p>)}</section>
        <section><span>限制与未知</span>{run.answer.caveats.map((item) => <p key={item}>{item}</p>)}</section>
      </div>
      <div className="role-test-context-list">
        <header><span>ACTUAL RUN CONTEXT</span><strong>实际使用的数据库上下文</strong></header>
        {run.context_refs.length ? run.context_refs.map((item) => <div key={`${item.kind}-${item.rank}-${item.label}`}><b>{item.kind === "data" ? `D${item.rank}` : item.kind === "evidence" ? `E${item.rank}` : `M${item.rank}`}</b><span><strong>{item.label}</strong><small>{item.version_ref ?? "运行快照"} · {item.excerpt}</small></span></div>) : <p className="role-test-context-empty">本次运行没有保存可用上下文。</p>}
      </div>
      {review ? <div className="role-test-review-summary"><ClipboardCheck aria-hidden="true" size={17} /><div><strong>{review.reviewer_name} · {review.average_score.toFixed(1)} / 5</strong><span>{review.notes}</span><small>证据 {review.evidence_grounding} · 边界 {review.boundary_adherence} · 表达 {review.voice_match} · 实用 {review.usefulness} · {formatTime(review.created_at)}</small></div></div> : null}
      {run.reviews.length ? <div className="role-test-review-ledger"><header><span>APPEND-ONLY REVIEW LEDGER</span><strong>{run.reviews.length} 条不可变审核事件</strong></header>{run.reviews.map((item) => <div key={item.id}><StatusBadge value={{ label: DECISION_LABELS[item.decision], tone: reviewTone(item.decision) }} /><span><strong>{item.reviewer_name} · {item.average_score.toFixed(1)} / 5</strong><small>{item.notes}</small></span><time>{formatTime(item.created_at)}</time></div>)}</div> : null}
    </section>
  );
}

function RoleTwinRunHistory({ onSelect, runs, selectedRunId }: { onSelect: (runId: string) => void; runs: RoleTwinTestRun[]; selectedRunId: string | null }) {
  return <section className="role-test-history"><header><History aria-hidden="true" size={16} /><div><span>IMMUTABLE RUN HISTORY</span><strong>该用例运行历史</strong></div></header><div className="role-test-history-table"><table><thead><tr><th>运行时间</th><th>分身版本</th><th>模型与模式</th><th>上下文</th><th>审核结论</th></tr></thead><tbody>{runs.map((run) => <tr className={run.id === selectedRunId ? "active" : ""} key={run.id} onClick={() => onSelect(run.id)}><td><strong>{formatTime(run.created_at)}</strong><code>{run.agent_run_id.slice(-10)}</code></td><td>{run.twin_name} · v{run.role_twin_version_number}</td><td>{run.model}<span>{run.execution_mode === "model" ? "真实模型" : "证据降级"}</span></td><td>D{run.metric_context_count} / E{run.evidence_count} / M{run.memory_context_count}</td><td>{run.latest_review ? <StatusBadge value={{ label: DECISION_LABELS[run.latest_review.decision], tone: reviewTone(run.latest_review.decision) }} /> : <StatusBadge value={{ label: "待审核", tone: "warning" }} />}</td></tr>)}</tbody></table></div></section>;
}

function RoleTwinReviewDialog({ onClose, onComplete, roleId, run }: { onClose: () => void; onComplete: (result: RoleTwinTestMutationResponse) => void; roleId: string; run: RoleTwinTestRun }) {
  const previous = run.latest_review;
  const [decision, setDecision] = useState<RoleTwinTestDecision>(previous?.decision ?? "pass");
  const [evidenceGrounding, setEvidenceGrounding] = useState(previous?.evidence_grounding ?? 4);
  const [boundaryAdherence, setBoundaryAdherence] = useState(previous?.boundary_adherence ?? 4);
  const [voiceMatch, setVoiceMatch] = useState(previous?.voice_match ?? 4);
  const [usefulness, setUsefulness] = useState(previous?.usefulness ?? 4);
  const [notes, setNotes] = useState(previous?.notes ?? "证据、边界、表达与行动建议均已人工核对。");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/role-twin-test-runs/${encodeURIComponent(run.id)}/reviews`, { method: "POST", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify({ decision, evidence_grounding: evidenceGrounding, boundary_adherence: boundaryAdherence, voice_match: voiceMatch, usefulness, notes }) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "人工审核未写入"));
      onComplete((await response.json()) as RoleTwinTestMutationResponse);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "人工审核未写入");
    } finally {
      setSubmitting(false);
    }
  }

  return <Dialog busy={submitting} className="knowledge-dialog role-test-review-dialog unified" eyebrow="HUMAN REVIEW EVENT · APPEND ONLY" onClose={onClose} size="large" title={`审核 ${run.twin_name} v${run.role_twin_version_number}`}><form onSubmit={(event) => void submit(event)}><div className="role-test-review-target"><FlaskConical aria-hidden="true" size={18} /><div><strong>{run.answer.summary}</strong><span>{run.agent_run_id} · {formatTime(run.created_at)}</span></div></div><fieldset className="role-test-decision"><legend>审核结论</legend>{(["pass", "needs_revision", "fail"] as RoleTwinTestDecision[]).map((item) => <label className={decision === item ? "active" : ""} key={item}><input checked={decision === item} name="decision" onChange={() => setDecision(item)} type="radio" value={item} /><span>{DECISION_LABELS[item]}</span></label>)}</fieldset><div className="role-test-score-grid"><ScoreField label="证据可靠" onChange={setEvidenceGrounding} value={evidenceGrounding} /><ScoreField label="边界遵守" onChange={setBoundaryAdherence} value={boundaryAdherence} /><ScoreField label="表达匹配" onChange={setVoiceMatch} value={voiceMatch} /><ScoreField label="业务实用" onChange={setUsefulness} value={usefulness} /></div><label className="role-test-review-notes"><span>审核说明</span><textarea onChange={(event) => setNotes(event.target.value)} rows={5} value={notes} /></label>{previous ? <InlineCallout description="本次复核会追加新事件，上一条审核结论继续保留。" title="不可变审核历史" tone="info" /> : null}{error ? <InlineCallout description={error} title="审核未完成" tone="critical" /> : null}<footer><button className="button secondary" onClick={onClose} type="button">取消</button><button className="button primary" disabled={submitting || notes.trim().length < 2} type="submit">{submitting ? <LoaderCircle aria-hidden="true" className="spinning" size={15} /> : <ClipboardCheck aria-hidden="true" size={15} />}{submitting ? "正在写入" : "追加审核事件"}</button></footer></form></Dialog>;
}

function ScoreField({ label, onChange, value }: { label: string; onChange: (value: number) => void; value: number }) {
  return <label><span>{label}<strong>{value}</strong></span><input aria-label={label} max={5} min={1} onChange={(event) => onChange(Number(event.target.value))} step={1} type="range" value={value} /></label>;
}

function RoleTwinTestState({ icon, retry, title }: { icon: React.ReactNode; retry?: () => void; title: string }) {
  return <div className="role-test-page-state">{icon}<strong>{title}</strong>{retry ? <button className="button secondary" onClick={retry} type="button">重新加载</button> : null}</div>;
}
