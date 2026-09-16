"use client";

import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  CircleDot,
  ClipboardCheck,
  Clock3,
  Database,
  ExternalLink,
  FileLock2,
  Gauge,
  LoaderCircle,
  MessageSquareQuote,
  Network,
  Plus,
  Play,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  X,
  UserCheck,
  UsersRound
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge, Surface } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import { useActiveWorkspaceKey } from "@/lib/workspace-context";
import type {
  DigitalMeetingDetailResponse,
  EvidenceSnapshotItem,
  MeetingClaim,
  MeetingDeliberationTurn,
  MeetingListItem,
  MeetingListResponse,
  MeetingConfirmResponse,
  MeetingCreateRequest,
  MeetingCreateResponse,
  MeetingRunResponse,
  RoleTwinCatalogItem
} from "@/lib/decision-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const PROTOCOL_STEPS = [
  ["draft", "议题登记"],
  ["evidence_frozen", "证据冻结"],
  ["independent_analysis", "独立分析"],
  ["cross_examination", "交叉质询"],
  ["risk_review", "风险审查"],
  ["decision_drafted", "决策草案"],
  ["human_confirmed", "人工确认"],
  ["actions_created", "行动已创建"]
] as const;

function formatTime(value: string | null): string {
  if (!value) return "未设置";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function protocolLabel(value: string): string {
  return PROTOCOL_STEPS.find(([key]) => key === value)?.[1] ?? value;
}

function protocolRank(value: string): number {
  return PROTOCOL_STEPS.findIndex(([key]) => key === value);
}

function stanceLabel(value: MeetingClaim["stance"]): string {
  return { support: "支持", oppose: "反对", conditional: "条件支持" }[value];
}

export function DecisionMeetingsPage({ meetingKey }: { meetingKey?: string }) {
  return meetingKey ? <DecisionMeetingDetail meetingKey={meetingKey} /> : <DecisionMeetingList />;
}

function DecisionMeetingList() {
  const router = useRouter();
  const { can, identity, identityLoading, roleId } = useExperience();
  const workspaceKey = useActiveWorkspaceKey();
  const [data, setData] = useState<MeetingListResponse | null>(null);
  const [twins, setTwins] = useState<RoleTwinCatalogItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [composerError, setComposerError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [twinsLoading, setTwinsLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);
  const [form, setForm] = useState<MeetingComposerState>(() => emptyMeetingComposer());

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/decision-meetings`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取数字会议"));
    const result = (await response.json()) as MeetingListResponse;
    setData(result);
    setForm((current) => {
      const template = result.templates[0];
      const scope = result.scopes.find((item) => item.type === "enterprise") ?? result.scopes[0];
      if (!template || !scope || current.title) return current;
      return {
        ...current,
        templateKey: template.key,
        title: template.default_title,
        topic: template.default_topic,
        successMetric: template.default_success_metric,
        scopeType: scope.type,
        scopeKey: scope.key
      };
    });
  }, [roleId]);

  const loadTwins = useCallback(async () => {
    setTwinsLoading(true);
    setComposerError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/twins`, {
        cache: "no-store",
        headers: { "X-Zhixing-Demo-Actor": roleId }
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取可用角色分身"));
      const result = (await response.json()) as { items: RoleTwinCatalogItem[] };
      const available = result.items.filter((item) => item.status === "published" && item.published_at);
      setTwins(available);
      setForm((current) => current.participantKeys.length ? current : {
        ...current,
        participantKeys: ["twin-ceo", "twin-ops", "twin-finance"].filter((key) => available.some((item) => item.key === key)).slice(0, 6)
      });
    } catch (reason: unknown) {
      setComposerError(reason instanceof Error ? reason.message : "角色分身目录暂不可用");
    } finally {
      setTwinsLoading(false);
    }
  }, [roleId]);

  useEffect(() => {
    load().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "会议中心连接失败")).finally(() => setLoading(false));
  }, [load]);

  function openComposer() {
    setComposerOpen(true);
    if (!form.clientRequestKey) setForm((current) => ({ ...current, clientRequestKey: makeClientRequestKey() }));
    if (!twins.length) void loadTwins();
  }

  function closeComposer() {
    if (creating) return;
    setComposerOpen(false);
    setComposerError(null);
  }

  function updateTemplate(templateKey: MeetingComposerState["templateKey"]) {
    const template = data?.templates.find((item) => item.key === templateKey);
    setForm((current) => template ? {
      ...current,
      templateKey,
      title: template.default_title,
      topic: template.default_topic,
      successMetric: template.default_success_metric
    } : { ...current, templateKey });
  }

  function updateScope(scopeKey: string) {
    const scope = data?.scopes.find((item) => item.key === scopeKey);
    setForm((current) => scope ? { ...current, scopeType: scope.type, scopeKey: scope.key } : current);
  }

  function toggleParticipant(key: string) {
    setForm((current) => {
      const selected = current.participantKeys.includes(key);
      if (selected) return { ...current, participantKeys: current.participantKeys.filter((item) => item !== key) };
      if (current.participantKeys.length >= 6) return current;
      return { ...current, participantKeys: [...current.participantKeys, key] };
    });
  }

  async function createMeeting(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!can("meeting.start")) {
      setComposerError("当前数据库身份没有发起数字会议权限，请切换到具备会议发起授权的负责人。");
      return;
    }
    if (form.participantKeys.length < 3) {
      setComposerError("至少选择 3 个已发布角色分身，才能形成可交叉质询的会议阵容。");
      return;
    }
    setCreating(true);
    setComposerError(null);
    const payload: MeetingCreateRequest = {
      schema_version: 1,
      client_request_key: form.clientRequestKey || makeClientRequestKey(),
      template_key: form.templateKey,
      title: form.title.trim(),
      topic: form.topic.trim(),
      scope_type: form.scopeType,
      scope_key: form.scopeKey,
      success_metric: form.successMetric.trim(),
      deadline_at: form.deadlineAt ? new Date(form.deadlineAt).toISOString() : null,
      participant_keys: form.participantKeys,
      workspace_key: workspaceKey
    };
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/decision-meetings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "创建数字会议失败"));
      const result = (await response.json()) as MeetingCreateResponse;
      router.push(`/console/meetings/${encodeURIComponent(result.meeting.key)}`);
    } catch (reason: unknown) {
      setComposerError(reason instanceof Error ? reason.message : "创建数字会议失败");
    } finally {
      setCreating(false);
    }
  }

  if (loading) return <MeetingPageState title="正在读取数字会议数据库" />;
  if (!data) return <MeetingPageState error title={error ?? "数字会议暂不可用"} />;

  const decisionCount = data.items.filter((item) => item.has_decision_package).length;
  const claimCount = data.items.reduce((sum, item) => sum + item.claim_count, 0);
  const deliberationCount = data.items.reduce((sum, item) => sum + item.deliberation_count, 0);
  return <div className="decision-meeting-page meeting-list-page">
    <PageHeader
      actions={<div className="meeting-page-actions"><button className="button secondary" onClick={() => void load()} type="button"><RefreshCw aria-hidden="true" size={15} />刷新会议</button><button className="button primary" disabled={identityLoading || !can("meeting.start")} onClick={openComposer} type="button"><Plus aria-hidden="true" size={16} />发起议题</button></div>}
      description="每个议题冻结同一组企业证据，让角色分身先独立研判，再保留分歧并形成可确认决策包。"
      eyebrow="DIGITAL DECISION ROOM · DATABASE VIEW"
      meta={`${data.items.length} 个数据库会议 · ${identity?.actor.display_name ?? "数据库身份加载中"}`}
      title="数字会议与决策"
    />
    {error ? <InlineCallout description={error} title="最近一次刷新失败" tone="warning" /> : null}
    {!can("meeting.start") && !identityLoading ? <InlineCallout description="当前身份可以读取会议台账，但没有 meeting.start 发起权限。" title="创建权限受限" tone="info" /> : null}
    {composerOpen ? <MeetingComposer data={data} error={composerError} form={form} loading={twinsLoading} creating={creating} twins={twins} onChange={setForm} onClose={closeComposer} onSubmit={createMeeting} onToggleParticipant={toggleParticipant} onTemplateChange={updateTemplate} onScopeChange={updateScope} /> : null}
    <section className="meeting-stat-band" aria-label="数字会议统计">
      <article><span><UsersRound size={16} />会议议题</span><strong>{data.items.length}</strong><p>固定模板 · 可重复执行</p></article>
      <article><span><Bot size={16} />会议发言</span><strong>{claimCount + deliberationCount}</strong><p>{claimCount} 条独立观点 · {deliberationCount} 条质询审查</p></article>
      <article><span><FileLock2 size={16} />证据快照</span><strong>{data.items.filter((item) => item.evidence_snapshot.startsWith("evs-")).length}</strong><p>知识、指标与记忆冻结</p></article>
      <article><span><CheckCircle2 size={16} />决策包</span><strong>{decisionCount}</strong><p>等待人类负责人确认</p></article>
    </section>
    <section className="meeting-ledger">
      <header><div><span>MEETING LEDGER</span><h2>会议运行台账</h2></div><em>数据来自 twin_meetings / meeting_claims / decision_packages</em></header>
      {data.items.map((meeting) => <MeetingLedgerRow key={meeting.key} meeting={meeting} />)}
    </section>
  </div>;
}

interface MeetingComposerState {
  clientRequestKey: string;
  templateKey: "budget-inventory-review" | "inventory-clearance-review" | "kpi-incentive-review";
  title: string;
  topic: string;
  scopeType: "enterprise" | "store";
  scopeKey: string;
  successMetric: string;
  deadlineAt: string;
  participantKeys: string[];
}

function emptyMeetingComposer(): MeetingComposerState {
  return {
    clientRequestKey: "",
    templateKey: "budget-inventory-review",
    title: "",
    topic: "",
    scopeType: "enterprise",
    scopeKey: "enterprise",
    successMetric: "",
    deadlineAt: "",
    participantKeys: []
  };
}

function makeClientRequestKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `web-${crypto.randomUUID()}`;
  return `web-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function MeetingComposer({
  data,
  error,
  form,
  loading,
  creating,
  twins,
  onChange,
  onClose,
  onSubmit,
  onToggleParticipant,
  onTemplateChange,
  onScopeChange
}: {
  data: MeetingListResponse;
  error: string | null;
  form: MeetingComposerState;
  loading: boolean;
  creating: boolean;
  twins: RoleTwinCatalogItem[];
  onChange: React.Dispatch<React.SetStateAction<MeetingComposerState>>;
  onClose: () => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>;
  onToggleParticipant: (key: string) => void;
  onTemplateChange: (key: MeetingComposerState["templateKey"]) => void;
  onScopeChange: (key: string) => void;
}) {
  const selectedTemplate = data.templates.find((item) => item.key === form.templateKey);
  return <section className="meeting-composer" aria-label="议题编排台">
    <header className="meeting-composer-header"><div><span>TOPIC ORCHESTRATOR · GOVERNED CREATE</span><h2>议题编排台</h2><p>从模板、数据范围和角色阵容开始，创建一场可复盘的数据库数字会议。</p></div><button aria-label="关闭议题编排台" className="icon-button" onClick={onClose} type="button"><X size={18} /></button></header>
    <form onSubmit={(event) => void onSubmit(event)}>
      {error ? <InlineCallout description={error} title="议题还没有创建" tone="warning" /> : null}
      <div className="meeting-composer-grid">
        <label><span>会议模板</span><select onChange={(event) => onTemplateChange(event.target.value as MeetingComposerState["templateKey"])} value={form.templateKey}>{data.templates.map((template) => <option key={template.key} value={template.key}>{template.label}</option>)}</select><small>{selectedTemplate?.description}</small></label>
        <label><span>数据范围</span><select onChange={(event) => onScopeChange(event.target.value)} value={form.scopeKey}>{data.scopes.map((scope) => <option key={`${scope.type}-${scope.key}`} value={scope.key}>{scope.label}{scope.has_metric_data ? " · 有指标" : " · 待接入"}</option>)}</select><small>范围会在证据冻结时严格限制指标与已审核记忆。</small></label>
        <label className="wide"><span>议题标题</span><input maxLength={240} minLength={4} onChange={(event) => onChange((current) => ({ ...current, title: event.target.value }))} required value={form.title} /></label>
        <label className="wide"><span>需要分身回答的问题</span><textarea maxLength={500} minLength={10} onChange={(event) => onChange((current) => ({ ...current, topic: event.target.value }))} required rows={3} value={form.topic} /></label>
        <label className="wide"><span>成功指标与边界</span><input maxLength={500} minLength={6} onChange={(event) => onChange((current) => ({ ...current, successMetric: event.target.value }))} required value={form.successMetric} /></label>
        <label><span>期望完成时间 <em>可选</em></span><input onChange={(event) => onChange((current) => ({ ...current, deadlineAt: event.target.value }))} type="datetime-local" value={form.deadlineAt} /></label>
        <div className="meeting-composer-key"><span>请求幂等键</span><code>{form.clientRequestKey || "打开后生成"}</code><small>网络重试不会重复创建同一议题。</small></div>
      </div>
      <fieldset className="meeting-participant-picker"><legend>参会角色分身 <small>选择 3–6 位 · 已发布版本</small></legend>{loading ? <div className="meeting-composer-loading"><LoaderCircle className="spinning" size={16} />正在读取角色目录</div> : twins.length ? <div className="meeting-participant-grid">{twins.map((twin) => { const checked = form.participantKeys.includes(twin.key); return <label className={`meeting-participant-option ${checked ? "selected" : ""}`} key={twin.key}><input checked={checked} disabled={!checked && form.participantKeys.length >= 6} onChange={() => onToggleParticipant(twin.key)} type="checkbox" /><span className="meeting-participant-icon"><Bot size={17} /></span><span><strong>{twin.display_name}</strong><small>{twin.role_title} · {twin.model}</small></span><StatusBadge value={{ label: checked ? "已选" : "可选", tone: checked ? "positive" : "neutral" }} /></label>; })}</div> : <div className="meeting-composer-loading"><UsersRound size={17} />暂无可用的已发布角色分身</div>}</fieldset>
      <footer className="meeting-composer-footer"><span><ShieldAlert size={15} />创建后先冻结证据，运行和确认仍受后端权限控制。</span><div><button className="button secondary" disabled={creating} onClick={onClose} type="button">取消</button><button className="button primary" disabled={creating || loading || !canCreateParticipantCount(form.participantKeys.length)} type="submit">{creating ? <LoaderCircle className="spinning" size={16} /> : <Plus size={16} />}{creating ? "正在创建" : "创建并打开会议"}</button></div></footer>
    </form>
  </section>;
}

function canCreateParticipantCount(count: number): boolean { return count >= 3 && count <= 6; }

function MeetingLedgerRow({ meeting }: { meeting: MeetingListItem }) {
  return <Link className="meeting-ledger-row" href={`/console/meetings/${meeting.key}`}>
    <span className={`meeting-ledger-state ${meeting.has_decision_package ? "ready" : "active"}`}><CircleDot aria-hidden="true" size={16} /></span>
    <div className="meeting-ledger-topic"><small>{meeting.template_key} · {meeting.scope_label}</small><strong>{meeting.title}</strong><p>{meeting.topic}</p></div>
    <div><small>参与角色</small><strong>{meeting.participant_count} 位</strong><span>{meeting.claim_count} 条观点 · {meeting.deliberation_count} 条过程</span></div>
    <div><small>证据快照</small><strong>{meeting.evidence_snapshot}</strong><span>{protocolLabel(meeting.protocol_status)}</span></div>
    <div><small>发起人与更新</small><strong>{meeting.initiated_by_name}</strong><span>{formatTime(meeting.updated_at)} · {meeting.has_decision_package ? "决策草案" : protocolLabel(meeting.protocol_status)}</span></div>
    <ExternalLink aria-hidden="true" size={16} />
  </Link>;
}

function DecisionMeetingDetail({ meetingKey }: { meetingKey: string }) {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<DigitalMeetingDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [runModes, setRunModes] = useState<Record<string, string> | null>(null);
  const [duration, setDuration] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/decision-meetings/${encodeURIComponent(meetingKey)}`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取会议详情"));
    setData((await response.json()) as DigitalMeetingDetailResponse);
  }, [meetingKey, roleId]);

  useEffect(() => {
    load().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "会议详情连接失败")).finally(() => setLoading(false));
  }, [load]);

  async function runMeeting() {
    setRunning(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/decision-meetings/${encodeURIComponent(meetingKey)}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ refresh_evidence: true })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "数字会议执行失败"));
      const result = (await response.json()) as MeetingRunResponse;
      setData(result.detail);
      setRunModes(result.execution_modes);
      setDuration(result.duration_ms);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "数字会议执行失败");
    } finally {
      setRunning(false);
    }
  }

  async function confirmMeeting() {
    setConfirming(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/decision-meetings/${encodeURIComponent(meetingKey)}/confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Zhixing-Demo-Actor": roleId
        },
        body: JSON.stringify({ comment: "确认按决策包中的 KPI 与停止条件推进，所有行动先进入内部审批。" })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "人工确认失败"));
      const result = (await response.json()) as MeetingConfirmResponse;
      setData(result.detail);
      setConfirmOpen(false);
      notify({ title: "会议决策已确认", description: `${result.detail.action_proposals.length} 条行动提案已生成`, tone: "success" });
    } catch (reason: unknown) {
      notify({ title: "会议决策确认失败", description: reason instanceof Error ? reason.message : "请重试", tone: "error" });
    } finally {
      setConfirming(false);
    }
  }

  if (loading) return <MeetingPageState title="正在装载会议证据与角色观点" />;
  if (!data) return <MeetingPageState error title={error ?? "会议详情暂不可用"} />;

  const meeting = data.meeting;
  const canRun = can("meeting.start");
  const canConfirm = can("meeting.decision.confirm");
  const locked = Boolean(data.confirmation);
  return <div className="decision-meeting-page meeting-detail-page">
    <PageHeader
      actions={<div className="meeting-page-actions"><Link className="button secondary" href="/console"><Network aria-hidden="true" size={15} />查看三维会议室</Link>{locked ? <Link className="button primary" href="/console/actions/approvals"><ClipboardCheck size={16} />进入行动审批</Link> : <button className="button primary" disabled={running || !canRun} onClick={() => void runMeeting()} type="button">{running ? <LoaderCircle className="spinning" size={16} /> : <Play size={16} />}{running ? "三个角色正在研判" : data.decision_package ? "重新冻结并研判" : "运行数字会议"}</button>}</div>}
      description={meeting.topic}
      eyebrow="STRUCTURED DIGITAL MEETING · LIVE AI"
      meta={`${protocolLabel(meeting.protocol_status)} · 数据库`}
      title={meeting.title}
    />
    {error ? <InlineCallout description={error} title="会议执行未完成" tone="critical" /> : null}
    {!canRun && !locked ? <InlineCallout description="当前数据库身份可以读取会议证据，但没有 meeting.start 运行权限。" title="运行权限受限" tone="info" /> : null}
    {runModes ? <InlineCallout description={`${Object.entries(runModes).map(([key, value]) => `${key}: ${value}`).join(" · ")}${duration ? ` · 总耗时 ${duration}ms` : ""}`} title="本次 AI 执行模式" tone={Object.values(runModes).every((value) => value === "model") ? "positive" : "warning"} /> : null}
    <MeetingProtocol current={meeting.protocol_status} />
    <section className="meeting-brief-band">
      <div><span><Target size={15} />决策负责人</span><strong>{meeting.decision_owner}</strong></div>
      <div><span><Gauge size={15} />成功指标</span><strong>{meeting.success_metric}</strong></div>
      <div><span><Clock3 size={15} />期限</span><strong>{formatTime(meeting.deadline_at)}</strong></div>
      <div><span><UsersRound size={15} />会议阵容</span><strong>{meeting.participant_count} 位角色 · {meeting.claim_count} 条观点 · {meeting.deliberation_count} 条质询审查</strong></div>
    </section>
    <div className="meeting-evidence-layout">
      <EvidenceSnapshotPanel evidence={data.evidence} />
      <ParticipantRoster data={data} />
    </div>
    <RoleAnalysisPanel claims={data.claims} />
    <DeliberationPanel turns={data.deliberation_turns} />
    <DecisionPackagePanel canConfirm={canConfirm} confirming={confirming} data={data} onConfirm={() => setConfirmOpen(true)} />
    {confirmOpen && data.decision_package ? <ConfirmDialog busy={confirming} confirmLabel="确认并生成行动" description={`锁定“${meeting.title}”当前决策包？`} detail={`确认后将幂等生成 ${data.decision_package.actions.length} 条内部行动提案，决策包不可继续覆盖。`} onCancel={() => setConfirmOpen(false)} onConfirm={() => void confirmMeeting()} title="确认会议决策" tone="warning" /> : null}
  </div>;
}

function MeetingProtocol({ current }: { current: string }) {
  const rank = protocolRank(current);
  return <section className="meeting-protocol" aria-label="数字会议协议状态">
    {PROTOCOL_STEPS.map(([key, label], index) => <div className={index < rank ? "complete" : index === rank ? "active" : "pending"} key={key}><span>{index < rank ? <CheckCircle2 size={15} /> : <b>{String(index + 1).padStart(2, "0")}</b>}</span><strong>{label}</strong></div>)}
  </section>;
}

function EvidenceSnapshotPanel({ evidence }: { evidence: DigitalMeetingDetailResponse["evidence"] }) {
  if (!evidence) return <Surface className="meeting-evidence-panel" meta="运行会议时自动创建" title="冻结证据快照"><div className="meeting-empty"><FileLock2 size={24} /><strong>尚未冻结证据</strong><span>运行会议后将锁定知识版本、经营指标和已审核记忆。</span></div></Surface>;
  const typeCounts = evidence.items.reduce<Record<string, number>>((counts, item) => ({ ...counts, [item.type]: (counts[item.type] ?? 0) + 1 }), {});
  return <Surface className="meeting-evidence-panel" meta={`${evidence.item_count} 项 · ${formatTime(evidence.frozen_at)}`} title="冻结证据快照">
    <div className="evidence-snapshot-meta"><code>{evidence.key}</code>{Object.entries(typeCounts).map(([key, value]) => <span key={key}>{key} {value}</span>)}</div>
    <div className="frozen-evidence-list">{evidence.items.map((item) => <FrozenEvidenceItem item={item} key={`${item.rank}-${item.key}`} />)}</div>
  </Surface>;
}

function FrozenEvidenceItem({ item }: { item: EvidenceSnapshotItem }) {
  return <article><b>E{item.rank}</b><span className={`evidence-type ${item.type}`}>{item.type}</span><div><strong>{item.label}</strong><small>{item.version_ref ?? "当前快照"}</small></div></article>;
}

function ParticipantRoster({ data }: { data: DigitalMeetingDetailResponse }) {
  const claimMap = new Map(data.claims.map((claim) => [claim.twin_key, claim]));
  return <Surface className="meeting-roster" meta="固定首期阵容" title="角色与运行状态">
    <div className="meeting-roster-list">{data.participants.map((participant) => {
      const claim = claimMap.get(participant.actor_key);
      return <article key={participant.actor_key}><span className={`role-orbit ${participant.actor_key.replace("twin-", "")}`}><Bot size={18} /></span><div><strong>{participant.role_name}</strong><small>{participant.position}</small><p>{claim?.summary ?? "等待独立分析"}</p></div><StatusBadge value={{ label: claim ? stanceLabel(claim.stance) : "等待运行", tone: claim ? "positive" : "neutral" }} /></article>;
    })}</div>
  </Surface>;
}

function RoleAnalysisPanel({ claims }: { claims: MeetingClaim[] }) {
  return <section className="role-analysis-section">
    <header><div><span>INDEPENDENT ANALYSIS</span><h2>三角色独立研判</h2></div><em>角色之间不会看到彼此的首次分析</em></header>
    {claims.length ? <div className="role-analysis-grid">{claims.map((claim) => <article className={`role-analysis-card ${claim.twin_key.replace("twin-", "")}`} key={claim.id}>
      <header><span><Bot size={18} /></span><div><small>{claim.role_title}</small><h3>{claim.twin_name}</h3></div><StatusBadge value={{ label: stanceLabel(claim.stance), tone: claim.stance === "oppose" ? "critical" : claim.stance === "conditional" ? "warning" : "positive" }} /></header>
      <p className="role-analysis-summary">{claim.summary}</p>
      <div className="role-claim-list">{claim.claims.map((item, index) => <div key={`${claim.id}-${index}`}><strong>{item.statement}</strong><span>{item.evidence_refs.join(" · ")} · {item.confidence}</span><small>假设：{item.assumption}</small></div>)}</div>
      <footer><div><span>主要风险</span><p>{claim.risks.join("；")}</p></div><div><span>建议</span><p>{claim.recommendation}</p></div></footer>
    </article>)}</div> : <div className="meeting-empty analysis-empty"><Sparkles size={25} /><strong>等待三角色独立分析</strong><span>运行后将显示主张、证据引用、假设、风险、未知项和建议。</span></div>}
  </section>;
}

function DeliberationPanel({ turns }: { turns: MeetingDeliberationTurn[] }) {
  const roundOne = turns.filter((turn) => turn.turn_type === "challenge");
  const roundTwo = turns.filter((turn) => turn.turn_type === "response");
  const riskReview = turns.find((turn) => turn.turn_type === "risk_review");
  return <section className="meeting-deliberation-section">
    <header><div><span>DELIBERATION LEDGER</span><h2>两轮质询与反方审查</h2></div><em>只允许使用冻结证据，新增证据会单独标记</em></header>
    {turns.length ? <>
      <DeliberationRound label="ROUND 01 · CHALLENGE" title="第一轮：循环挑战关键假设" turns={roundOne} />
      <DeliberationRound label="ROUND 02 · RESPONSE" title="第二轮：回应质询并更新立场" turns={roundTwo} />
      {riskReview ? <RiskReview turn={riskReview} /> : null}
    </> : <div className="meeting-empty deliberation-empty"><MessageSquareQuote size={25} /><strong>等待交叉质询</strong><span>独立分析完成后，三位角色将进行两轮有新增证据约束的质询。</span></div>}
  </section>;
}

function DeliberationRound({ label, title, turns }: { label: string; title: string; turns: MeetingDeliberationTurn[] }) {
  return <div className="deliberation-round">
    <header><div><span>{label}</span><h3>{title}</h3></div><em>{turns.length} 条持久化发言</em></header>
    <div className="deliberation-turn-grid">{turns.map((turn) => <DeliberationTurnCard key={turn.id} turn={turn} />)}</div>
  </div>;
}

function DeliberationTurnCard({ turn }: { turn: MeetingDeliberationTurn }) {
  if (!("challenges" in turn.payload)) return null;
  return <article className={`deliberation-turn-card ${turn.speaker_twin_key.replace("twin-", "")}`}>
    <header><span><MessageSquareQuote size={17} /></span><div><small>{turn.speaker_role_title}</small><strong>{turn.speaker_name}</strong></div><ArrowRight aria-hidden="true" size={14} /><div className="deliberation-target"><small>质询对象</small><strong>{turn.target_name ?? "会议整体"}</strong></div></header>
    <p>{turn.summary}</p>
    <div className="deliberation-points">{turn.payload.challenges.map((item, index) => <div key={`${turn.id}-${index}`}><span>针对：{item.target_claim}</span><strong>{item.statement}</strong><p>{item.question}</p><footer><em>{item.evidence_refs.join(" · ")}</em><b>新增 {item.new_evidence_refs.join(" · ")}</b></footer></div>)}</div>
    <footer><span className={turn.position_changed ? "changed" : "stable"}>{turn.position_changed ? "立场已调整" : "立场保持"}</span><strong>{turn.position_after ? stanceLabel(turn.position_after) : "不适用"}</strong><small>{turn.payload.unresolved.join("；")}</small></footer>
  </article>;
}

function RiskReview({ turn }: { turn: MeetingDeliberationTurn }) {
  if (!("failure_modes" in turn.payload)) return null;
  return <div className="meeting-risk-review">
    <header><span><ShieldAlert size={18} /></span><div><small>ADVERSARIAL REVIEW · ROUND 03</small><h3>反方风险审查</h3></div><StatusBadge value={{ label: `${turn.payload.failure_modes.length} 个失败模式`, tone: "critical" }} /></header>
    <p>{turn.summary}</p>
    <div className="risk-failure-grid">{turn.payload.failure_modes.map((item, index) => <article key={`${turn.id}-risk-${index}`}><b>{String(index + 1).padStart(2, "0")}</b><div><strong>{item.risk}</strong><p>{item.mechanism}</p><dl><div><dt>触发信号</dt><dd>{item.trigger}</dd></div><div><dt>缓解措施</dt><dd>{item.mitigation}</dd></div></dl><span>{item.evidence_refs.join(" · ")}</span></div></article>)}</div>
    <footer><div><span>反事实</span><p>{turn.payload.counterfactuals.join("；")}</p></div><div><span>错误激励</span><p>{turn.payload.incentive_risks.join("；")}</p></div><div><span>仍未解决</span><p>{turn.payload.unresolved.join("；")}</p></div></footer>
  </div>;
}

function DecisionPackagePanel({ canConfirm, confirming, data, onConfirm }: { canConfirm: boolean; confirming: boolean; data: DigitalMeetingDetailResponse; onConfirm: () => void }) {
  const pkg = data.decision_package;
  const confirmation = data.confirmation;
  return <section className={`decision-package-section ${pkg ? "ready" : "pending"}`}>
    <header><div><span>DECISION PACKAGE</span><h2>主持人决策包</h2></div>{pkg ? <StatusBadge value={confirmation ? { label: "已确认并生成行动", tone: "positive" } : { label: "等待人工确认", tone: "warning" }} /> : <span className="decision-waiting"><LoaderCircle size={15} />尚未生成</span>}</header>
    {pkg ? <>
      <div className="decision-summary"><ShieldAlert size={21} /><div><small>建议结论</small><strong>{pkg.decision}</strong><p>{pkg.summary}</p></div></div>
      <div className="decision-balance-grid"><div><span>共识</span>{pkg.consensus.map((item) => <p key={item}><CheckCircle2 size={14} />{item}</p>)}</div><div><span>保留分歧</span>{pkg.disagreements.map((item) => <p key={item}><AlertTriangle size={14} />{item}</p>)}</div><div><span>风险</span>{pkg.risks.map((item) => <p key={item}><ShieldAlert size={14} />{item}</p>)}</div></div>
      <div className="decision-actions"><header><span>ACTION PROPOSALS</span><strong>{pkg.actions.length} 项待确认行动</strong></header>{pkg.actions.map((action, index) => <article key={`${action.title}-${index}`}><b>{String(index + 1).padStart(2, "0")}</b><div><strong>{action.title}</strong><span>{action.owner} · {action.due_hint}</span></div><div><small>KPI</small><p>{action.kpi}</p></div><div><small>停止条件</small><p>{action.stop_condition}</p></div><em>{action.evidence_refs.join(" · ")}</em></article>)}</div>
      {confirmation ? <div className="meeting-confirmation-band"><span><UserCheck size={19} /></span><div><small>HUMAN CONFIRMED · {formatTime(confirmation.confirmed_at)}</small><strong>{confirmation.confirmed_by_name}</strong><p>{confirmation.comment}</p></div><div><b>{data.action_proposals.length}</b><small>数据库行动提案</small><Link href="/console/actions/approvals">查看审批队列 <ArrowRight size={14} /></Link></div></div> : <div className="meeting-confirmation-gate"><div><span>人工确认闸门</span><strong>确认后将锁定当前决策包，并幂等生成 {pkg.actions.length} 条 R2 内部行动提案。</strong><p>审批前不改变外部系统；提案发起人与审批人必须分离。</p>{!canConfirm ? <small>当前数据库身份没有 meeting.decision.confirm 权限，请由具备决策确认授权的负责人处理。</small> : null}</div><button className="button primary" disabled={!canConfirm || confirming} onClick={onConfirm} type="button">{confirming ? <LoaderCircle className="spinning" size={16} /> : <UserCheck size={16} />}{confirming ? "正在确认并生成行动" : "确认决策并生成行动"}</button></div>}
    </> : <div className="meeting-empty"><Database size={25} /><strong>尚无数据库决策包</strong><span>点击“运行数字会议”，系统将冻结证据、执行三角色研判并保存主持汇总。</span></div>}
  </section>;
}

function MeetingPageState({ title, error = false }: { title: string; error?: boolean }) {
  return <div className={`meeting-page-state ${error ? "error" : ""}`}>{error ? <AlertTriangle size={27} /> : <LoaderCircle className="spinning" size={27} />}<strong>{title}</strong></div>;
}
