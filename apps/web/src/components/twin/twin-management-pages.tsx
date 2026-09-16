"use client";

import {
  Activity,
  Archive,
  Bot,
  BrainCircuit,
  Check,
  CheckCircle2,
  CircleAlert,
  FileClock,
  FlaskConical,
  LoaderCircle,
  MemoryStick,
  MessageSquareText,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Upload,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog, Dialog, useNotifications } from "@/components/console/interaction";
import {
  InlineCallout,
  PageHeader,
  StatusBadge,
  Surface
} from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type {
  ChatImportListResponse,
  ChatImportResponse,
  MemoryCandidateItem,
  MemoryCandidateListResponse,
  MemoryMutationResponse,
  MemoryProviderEvaluationRun,
  MemoryProviderOperationsResponse,
  RoleTwinCatalogItem,
  RoleTwinCatalogResponse
} from "@/lib/decision-types";
import type { TwinAnswerResponse } from "@/lib/knowledge-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type TwinManagementView = "templates" | "instances" | "memories" | "prompts" | "test";

const VIEW_COPY: Record<TwinManagementView, { eyebrow: string; title: string; description: string }> = {
  templates: {
    eyebrow: "ROLE BLUEPRINTS · DATABASE VIEW",
    title: "岗位分身模板",
    description: "把角色职责、分析框架、表达方式和工具能力沉淀为可发布的岗位蓝图。"
  },
  instances: {
    eyebrow: "ROLE TWINS · DATABASE VIEW",
    title: "角色分身实例",
    description: "查看每个分身的配置、记忆健康度、AI 运行和当前模型状态。"
  },
  memories: {
    eyebrow: "GOVERNED MEMORY · DATABASE VIEW",
    title: "角色记忆治理",
    description: "聊天与会议内容先进入候选队列，审核、冲突处理后才可成为长期记忆。"
  },
  prompts: {
    eyebrow: "CONFIG RELEASES · DATABASE VIEW",
    title: "分身配置版本",
    description: "角色表达、推理规则和回答边界随发布版本持久化并可追溯。"
  },
  test: {
    eyebrow: "EVIDENCE EVALUATION · LIVE AI",
    title: "分身证据测试",
    description: "直接调用当前分身与知识检索链，检查引用、边界、风格和模型降级状态。"
  }
};

function formatTime(value: string | null): string {
  if (!value) return "尚未运行";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function toneForStatus(status: string) {
  if (["active", "published", "completed"].includes(status)) return "positive" as const;
  if (["candidate", "unverified"].includes(status)) return "warning" as const;
  if (["rejected", "conflicted"].includes(status)) return "critical" as const;
  return "info" as const;
}

function statusLabel(status: string): string {
  return {
    active: "已生效",
    candidate: "待审核",
    approved: "已批准",
    rejected: "已拒绝",
    retired: "已退役",
    conflicted: "存在冲突",
    clear: "无冲突",
    unverified: "待核验",
    published: "已发布"
  }[status] ?? status;
}

export function TwinManagementPage({ view }: { view: TwinManagementView }) {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [catalog, setCatalog] = useState<RoleTwinCatalogResponse | null>(null);
  const [memories, setMemories] = useState<MemoryCandidateListResponse | null>(null);
  const [chatImports, setChatImports] = useState<ChatImportListResponse | null>(null);
  const [providerOperations, setProviderOperations] = useState<MemoryProviderOperationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [memoryAction, setMemoryAction] = useState<{ memory: MemoryCandidateItem; action: MemoryAction } | null>(null);
  const canImportChats = can("memory.chat.ingest");
  const canReviewMemories = can("memory.candidate.review");
  const canRetireMemories = can("memory.approved.retire");

  const load = useCallback(async () => {
    setError(null);
    const headers = { "X-Zhixing-Demo-Actor": roleId };
    const [twinsResponse, memoriesResponse, importsResponse, providerOperationsResponse] = await Promise.all([
      apiFetch(`${API_BASE_URL}/api/v1/twins`, { cache: "no-store", headers }),
      apiFetch(`${API_BASE_URL}/api/v1/memories`, { cache: "no-store", headers }),
      canImportChats && view === "memories"
        ? apiFetch(`${API_BASE_URL}/api/v1/memories/chat-imports`, { cache: "no-store", headers })
        : Promise.resolve(null),
      view === "memories"
        ? apiFetch(`${API_BASE_URL}/api/v1/memories/provider-operations`, { cache: "no-store", headers })
        : Promise.resolve(null)
    ]);
    if (!twinsResponse.ok) throw new Error(await apiErrorMessage(twinsResponse, "无法读取分身目录"));
    if (!memoriesResponse.ok) throw new Error(await apiErrorMessage(memoriesResponse, "无法读取记忆目录"));
    if (importsResponse && !importsResponse.ok) throw new Error(await apiErrorMessage(importsResponse, "无法读取聊天导入台账"));
    if (providerOperationsResponse && !providerOperationsResponse.ok) throw new Error(await apiErrorMessage(providerOperationsResponse, "无法读取记忆供应商运维数据"));
    setCatalog((await twinsResponse.json()) as RoleTwinCatalogResponse);
    setMemories((await memoriesResponse.json()) as MemoryCandidateListResponse);
    setChatImports(importsResponse ? (await importsResponse.json()) as ChatImportListResponse : null);
    setProviderOperations(providerOperationsResponse ? (await providerOperationsResponse.json()) as MemoryProviderOperationsResponse : null);
  }, [canImportChats, roleId, view]);

  useEffect(() => {
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "分身中心连接失败"))
      .finally(() => setLoading(false));
  }, [load]);

  if (loading) return <TwinPageState icon={<LoaderCircle className="spinning" />} title="正在读取角色分身数据库" />;
  if (!catalog || !memories) {
    return <TwinPageState icon={<CircleAlert />} title={error ?? "分身中心暂不可用"} retry={() => window.location.reload()} />;
  }

  const copy = VIEW_COPY[view];
  return (
    <div className="twin-management-page">
      <PageHeader
        actions={<div className="twin-page-actions">
          {view === "memories" && canImportChats ? <button className="button primary" onClick={() => setImportOpen(true)} type="button"><Upload aria-hidden="true" size={15} />导入聊天</button> : null}
          <button className="button secondary" onClick={() => void load()} type="button"><RefreshCw aria-hidden="true" size={15} />刷新数据库</button>
        </div>}
        description={copy.description}
        eyebrow={copy.eyebrow}
        meta={`数据库 · ${catalog.stats.profile_count} 个角色`}
        title={copy.title}
      />
      {error ? <InlineCallout description={error} title="最近一次刷新失败" tone="warning" /> : null}
      <TwinStatBand catalog={catalog} />
      {view === "memories" && providerOperations ? <MemoryProviderBenchmark canRun={canReviewMemories} data={providerOperations} onComplete={(run) => { notify({ title: "双跑评测已完成", description: run.evaluation_key, tone: "success" }); void load(); }} roleId={roleId} /> : null}
      {view === "memories" ? <MemoryGovernance canRetire={canRetireMemories} canReview={canReviewMemories} memories={memories.items} onAction={(memory, action) => setMemoryAction({ memory, action })} /> : null}
      {view === "memories" && chatImports ? <ChatImportLedger imports={chatImports} /> : null}
      {view === "test" ? <TwinTestRunner profiles={catalog.items} roleId={roleId} /> : null}
      {view !== "memories" && view !== "test" ? <TwinProfileGrid profiles={catalog.items} view={view} /> : null}
      {importOpen ? <ChatImportDialog onClose={() => setImportOpen(false)} onComplete={(result) => { setImportOpen(false); notify({ title: result.duplicate ? "聊天原件已存在" : "聊天原件已导入", description: result.duplicate ? "未重复创建消息和候选" : `${result.import_run.message_count} 条消息 · ${result.import_run.candidate_count} 条待审记忆`, tone: "success" }); void load(); }} profiles={catalog.items} roleId={roleId} /> : null}
      {memoryAction ? <MemoryActionDialog action={memoryAction.action} memory={memoryAction.memory} onClose={() => setMemoryAction(null)} onComplete={(result) => { setMemoryAction(null); notify({ title: "记忆状态已更新", description: `${statusLabel(result.candidate.status)} · ${result.candidate.content}`, tone: "success" }); void load(); }} roleId={roleId} /> : null}
    </div>
  );
}

function MemoryProviderBenchmark({ canRun, data, onComplete, roleId }: { canRun: boolean; data: MemoryProviderOperationsResponse; onComplete: (run: MemoryProviderEvaluationRun) => void; roleId: string }) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestKey, setRequestKey] = useState<string | null>(null);
  const latestRun = data.runs[0] ?? null;

  async function runEvaluation() {
    const currentRequestKey = requestKey ?? globalThis.crypto?.randomUUID?.() ?? `memory-eval-${Date.now()}`;
    setRequestKey(currentRequestKey);
    setRunning(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/memories/provider-evaluations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ schema_version: 1, client_request_key: currentRequestKey, provider_keys: data.providers.map((provider) => provider.key), top_k: 3 })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "记忆供应商双跑评测失败"));
      const run = (await response.json()) as MemoryProviderEvaluationRun;
      setRequestKey(null);
      onComplete(run);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "记忆供应商双跑评测失败");
    } finally {
      setRunning(false);
    }
  }

  return <section className="memory-provider-lab">
    <header>
      <div><small>MEMORY PROVIDER LAB · AUDITED DUAL RUN</small><h2>长期记忆双跑评测</h2><p>将同一批已生效记忆写入隔离命名空间，用相同问题对比检索召回与延迟。评测结果进入数据库，不改变长期记忆主数据。</p></div>
      <button className="button primary" disabled={!canRun || running || data.providers.length === 0 || data.benchmark_cases.length === 0} onClick={() => void runEvaluation()} title={canRun ? "运行相同基准集的供应商双跑评测" : "当前角色没有记忆审核权限"} type="button">{running ? <LoaderCircle aria-hidden="true" className="spinning" size={15} /> : <FlaskConical aria-hidden="true" size={15} />}{running ? "正在双跑" : "运行双跑评测"}</button>
    </header>
    <div className="memory-provider-summary">
      <span><small>基准版本</small><strong>{data.benchmark_version}</strong></span>
      <span><small>已生效记忆</small><strong>{data.active_memory_count}</strong></span>
      <span><small>固定问题</small><strong>{data.benchmark_cases.length}</strong></span>
      <span><small>最近运行</small><strong>{latestRun ? formatTime(latestRun.finished_at ?? latestRun.started_at) : "尚未运行"}</strong></span>
    </div>
    {error ? <InlineCallout description={`${error}。再次执行会沿用同一幂等键。`} title="评测未完成" tone="critical" /> : null}
    {!canRun ? <InlineCallout description="可查看历史结果；只有拥有记忆审核权限的角色可以发起新评测。" title="当前为只读模式" tone="info" /> : null}
    <div className="memory-provider-grid">
      {data.providers.map((provider) => {
        const result = latestRun?.results.find((item) => item.provider_key === provider.key) ?? null;
        return <article key={provider.key}>
          <header><div><small>{provider.protocol}</small><h3>{provider.label}</h3></div><StatusBadge value={{ label: result ? result.status === "succeeded" ? "评测成功" : "评测失败" : "等待评测", tone: result?.status === "succeeded" ? "positive" : result?.status === "failed" ? "critical" : "info" }} /></header>
          <div className="memory-provider-mode"><span>运行模式</span><strong>{provider.mode}</strong><em>{provider.authentication_configured ? "认证已配置" : "无生产认证"}</em></div>
          <dl>
            <div><dt>Recall@3</dt><dd>{result ? `${Math.round(result.recall_at_k * 100)}%` : "--"}</dd></div>
            <div><dt>命中问题</dt><dd>{result ? `${result.hit_count} / ${result.query_count}` : "--"}</dd></div>
            <div><dt>平均延迟</dt><dd>{result ? `${result.average_latency_ms} ms` : "--"}</dd></div>
            <div><dt>P95 延迟</dt><dd>{result ? `${result.p95_latency_ms} ms` : "--"}</dd></div>
          </dl>
          <footer><span>端点指纹</span><code>{provider.endpoint_fingerprint.slice(0, 16)}</code></footer>
          {result?.failure_reason ? <p className="memory-provider-failure">{result.failure_reason}</p> : null}
        </article>;
      })}
    </div>
    <div className="memory-benchmark-cases">
      <header><div><small>FIXED BENCHMARK</small><strong>统一问题集与逐题命中</strong></div>{latestRun ? <span>{latestRun.actor_name} · {latestRun.status} · {latestRun.case_count} 题</span> : <span>等待首轮评测</span>}</header>
      {data.benchmark_cases.map((benchmarkCase) => <div key={benchmarkCase.key}><span>{benchmarkCase.category}</span><strong>{benchmarkCase.query}</strong><small>期望记忆 {benchmarkCase.expected_memory_keys.length} 条</small><div>{data.providers.map((provider) => { const item = latestRun?.results.find((result) => result.provider_key === provider.key)?.items.find((resultItem) => resultItem.case_key === benchmarkCase.key); return <em className={item?.hit ? "hit" : item ? "miss" : "pending"} key={provider.key}>{provider.label} {item ? item.hit ? `命中 · ${item.latency_ms}ms` : `未命中 · ${item.latency_ms}ms` : "待运行"}</em>; })}</div></div>)}
    </div>
  </section>;
}

function TwinStatBand({ catalog }: { catalog: RoleTwinCatalogResponse }) {
  const stats = catalog.stats;
  const items = [
    { label: "角色分身", value: stats.profile_count, detail: "CEO / 运营 / 财务", icon: Bot },
    { label: "有效记忆", value: stats.active_memory_count, detail: "已审核并可参与推理", icon: MemoryStick },
    { label: "待审候选", value: stats.candidate_memory_count, detail: "尚未进入长期记忆", icon: FileClock },
    { label: "AI 运行", value: stats.agent_run_count, detail: "问答与会议运行总数", icon: Activity }
  ];
  return (
    <section className="twin-stat-band" aria-label="分身运行统计">
      {items.map((item) => {
        const Icon = item.icon;
        return <article key={item.label}><span><Icon aria-hidden="true" size={16} />{item.label}</span><strong>{item.value}</strong><p>{item.detail}</p></article>;
      })}
    </section>
  );
}

function TwinProfileGrid({ profiles, view }: { profiles: RoleTwinCatalogItem[]; view: Exclude<TwinManagementView, "memories" | "test"> }) {
  return (
    <section className="twin-profile-grid" aria-label="角色分身列表">
      {profiles.map((profile) => (
        <article className="twin-profile-card" key={profile.key}>
          <header>
            <span className={`twin-avatar-signal ${profile.key.replace("twin-", "")}`}><Bot aria-hidden="true" size={22} /></span>
            <div><small>{profile.role_title}</small><h2>{profile.display_name}</h2></div>
            <StatusBadge value={{ label: statusLabel(profile.status), tone: toneForStatus(profile.status) }} />
          </header>
          {view === "instances" ? <InstanceDetails profile={profile} /> : null}
          {view === "templates" ? <TemplateDetails profile={profile} /> : null}
          {view === "prompts" ? <PromptDetails profile={profile} /> : null}
        </article>
      ))}
    </section>
  );
}

function InstanceDetails({ profile }: { profile: RoleTwinCatalogItem }) {
  return <>
    <div className="twin-health-grid">
      <span><small>有效记忆</small><strong>{profile.active_memory_count}</strong></span>
      <span><small>待审候选</small><strong>{profile.candidate_memory_count}</strong></span>
      <span><small>累计运行</small><strong>{profile.run_count}</strong></span>
    </div>
    <div className="twin-capability-list">{profile.capabilities.map((item) => <span key={item}><CheckCircle2 aria-hidden="true" size={13} />{item}</span>)}</div>
    <footer><span>{profile.model}</span><time>最近运行 {formatTime(profile.latest_run_at)}</time></footer>
  </>;
}

function TemplateDetails({ profile }: { profile: RoleTwinCatalogItem }) {
  return <div className="twin-rule-stack">
    <div><span><Sparkles aria-hidden="true" size={14} />表达方式</span><p>{profile.voice_guide}</p></div>
    <div><span><BrainCircuit aria-hidden="true" size={14} />分析框架</span><p>{profile.reasoning_guide}</p></div>
    <div><span><ShieldCheck aria-hidden="true" size={14} />回答边界</span><p>{profile.answer_policy}</p></div>
  </div>;
}

function PromptDetails({ profile }: { profile: RoleTwinCatalogItem }) {
  return <>
    <div className="twin-config-code"><span>CONFIG KEY</span><code>{profile.key}.published</code></div>
    <dl className="twin-config-meta">
      <div><dt>Provider</dt><dd>{profile.provider}</dd></div>
      <div><dt>Model</dt><dd>{profile.model}</dd></div>
      <div><dt>发布时间</dt><dd>{formatTime(profile.published_at)}</dd></div>
      <div><dt>配置更新</dt><dd>{formatTime(profile.updated_at)}</dd></div>
    </dl>
    <p className="twin-config-note">表达、推理与回答边界分别存储；业务数据和人员访问权限不写入 Prompt。</p>
  </>;
}

type MemoryAction = "approve" | "reject" | "activate" | "retire";

function MemoryGovernance({ canRetire, canReview, memories, onAction }: { canRetire: boolean; canReview: boolean; memories: MemoryCandidateItem[]; onAction: (memory: MemoryCandidateItem, action: MemoryAction) => void }) {
  const [filter, setFilter] = useState("all");
  const filtered = useMemo(() => filter === "all" ? memories : memories.filter((item) => item.status === filter), [filter, memories]);
  return <>
    <div className="memory-filter" role="group" aria-label="记忆状态筛选">
      {[['all', '全部'], ['candidate', '待审核'], ['approved', '已批准'], ['active', '已生效'], ['rejected', '已拒绝'], ['retired', '已退役']].map(([key, label]) => (
        <button className={filter === key ? "active" : ""} key={key} onClick={() => setFilter(key)} type="button">{label}</button>
      ))}
    </div>
    <section className="memory-governance-list">
      {filtered.map((memory) => (
        <article key={memory.id}>
          <div className="memory-state-rail"><MemoryStick aria-hidden="true" size={18} /><span>{Math.round(memory.confidence * 100)}%</span></div>
          <div className="memory-main-copy">
            <header><div><small>{memory.twin_name} · {memory.category}</small><h2>{memory.content}</h2></div><StatusBadge value={{ label: statusLabel(memory.status), tone: toneForStatus(memory.status) }} /></header>
            <div className="memory-origin"><span>来源：{memory.source_ref}</span><span>类型：{memory.source_type}</span><time>更新 {formatTime(memory.updated_at)}</time></div>
            {memory.conflict_status !== "clear" ? <div className={`memory-conflict ${memory.conflict_status}`}><CircleAlert aria-hidden="true" size={14} /><span>{statusLabel(memory.conflict_status)}{memory.conflict_ref ? ` · ${memory.conflict_ref}` : " · 尚未完成来源核验"}</span></div> : null}
            <div className="memory-evidence-line"><MessageSquareText aria-hidden="true" size={13} /><span>{memory.evidence_refs.length} 条原始依据</span>{memory.memory_version ? <span>长期记忆 v{memory.memory_version}</span> : null}</div>
          </div>
          <div className="memory-governance-controls">
            <div className="memory-review-meta"><small>审核人</small><strong>{memory.reviewer ?? "等待审核"}</strong><span>{formatTime(memory.reviewed_at)}</span></div>
            <MemoryActionButtons canRetire={canRetire} canReview={canReview} memory={memory} onAction={onAction} />
          </div>
        </article>
      ))}
      {filtered.length === 0 ? <div className="memory-empty"><MemoryStick aria-hidden="true" size={20} /><strong>当前筛选没有记忆</strong></div> : null}
    </section>
  </>;
}

function MemoryActionButtons({ canRetire, canReview, memory, onAction }: { canRetire: boolean; canReview: boolean; memory: MemoryCandidateItem; onAction: (memory: MemoryCandidateItem, action: MemoryAction) => void }) {
  if (memory.status === "candidate" && canReview) return <div className="memory-review-actions"><button className="button compact" onClick={() => onAction(memory, "approve")} type="button"><Check aria-hidden="true" size={13} />审核</button><button className="button compact critical" onClick={() => onAction(memory, "reject")} type="button"><X aria-hidden="true" size={13} />拒绝</button></div>;
  if (memory.status === "approved" && canReview) return <div className="memory-review-actions"><button className="button compact" disabled={memory.conflict_status !== "clear"} onClick={() => onAction(memory, "activate")} title={memory.conflict_status === "clear" ? "启用长期记忆" : "冲突记忆不能启用"} type="button"><MemoryStick aria-hidden="true" size={13} />启用</button></div>;
  if (memory.status === "active" && canRetire) return <div className="memory-review-actions"><button className="button compact critical" onClick={() => onAction(memory, "retire")} type="button"><Archive aria-hidden="true" size={13} />退役</button></div>;
  return null;
}

function ChatImportLedger({ imports }: { imports: ChatImportListResponse }) {
  return <section className="chat-import-ledger">
    <header><div><small>CHAT SOURCE LEDGER</small><strong>聊天原件导入台账</strong></div><span>{imports.items.length} 条运行</span></header>
    {imports.items.length ? <div className="chat-import-table-wrap"><table><thead><tr><th>原件 / 分身</th><th>解析结果</th><th>参与者</th><th>状态</th><th>追踪</th></tr></thead><tbody>{imports.items.map((item) => <tr key={item.id}><td><strong>{item.source_filename}</strong><span>{item.twin_name} · {item.source_channel}</span></td><td><strong>{item.message_count} 消息 · {item.topic_count} 话题</strong><span>{item.candidate_count} 条候选</span></td><td>{item.participants.join(" / ")}</td><td><StatusBadge value={{ label: item.status === "completed" ? "已完成" : item.status === "duplicate" ? "重复原件" : "失败", tone: item.status === "completed" ? "positive" : "warning" }} /></td><td><code>{item.request_id}</code><span>{formatTime(item.created_at)}</span></td></tr>)}</tbody></table></div> : <div className="memory-empty"><MessageSquareText aria-hidden="true" size={20} /><strong>尚无聊天导入运行</strong></div>}
  </section>;
}

function ChatImportDialog({ onClose, onComplete, profiles, roleId }: { onClose: () => void; onComplete: (result: ChatImportResponse) => void; profiles: RoleTwinCatalogItem[]; roleId: string }) {
  const [twinKey, setTwinKey] = useState(profiles[0]?.key ?? "twin-ceo");
  const [sourceFilename, setSourceFilename] = useState("management-chat.txt");
  const [sourceChannel, setSourceChannel] = useState("feishu-export");
  const [speakers, setSpeakers] = useState("");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/memories/chat-imports`, { method: "POST", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify({ twin_key: twinKey, source_filename: sourceFilename, source_channel: sourceChannel, timezone: "Asia/Shanghai", target_speakers: speakers.split(",").map((item) => item.trim()).filter(Boolean), content }) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "聊天导入失败"));
      onComplete((await response.json()) as ChatImportResponse);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "聊天导入失败");
    } finally {
      setSubmitting(false);
    }
  }

  return <Dialog busy={submitting} className="knowledge-dialog memory-import-modal unified" eyebrow="CHAT INGESTION · R1" onClose={onClose} size="large" title="导入角色聊天原件"><form onSubmit={(event) => void submit(event)}><div className="knowledge-form-grid"><label><span>目标分身</span><select onChange={(event) => setTwinKey(event.target.value)} value={twinKey}>{profiles.map((profile) => <option key={profile.key} value={profile.key}>{profile.display_name} · {profile.role_title}</option>)}</select></label><label><span>来源渠道</span><select onChange={(event) => setSourceChannel(event.target.value)} value={sourceChannel}><option value="feishu-export">飞书导出</option><option value="wechat-export">微信导出</option><option value="manual-paste">人工整理</option></select></label><label><span>原件文件名</span><input onChange={(event) => setSourceFilename(event.target.value)} required value={sourceFilename} /></label><label><span>候选发言人</span><input onChange={(event) => setSpeakers(event.target.value)} placeholder="林知远, 周岚" value={speakers} /></label></div><label><span>聊天原文</span><textarea onChange={(event) => setContent(event.target.value)} placeholder={'# 话题: 经营复盘\n[2026-08-28 09:30] 姓名: 发言内容'} required rows={13} value={content} /></label>{error ? <InlineCallout description={error} title="导入未完成" tone="critical" /> : null}<footer><button className="button secondary" onClick={onClose} type="button">取消</button><button className="button primary" disabled={submitting || content.trim().length < 20} type="submit">{submitting ? <LoaderCircle aria-hidden="true" className="spinning" size={15} /> : <Upload aria-hidden="true" size={15} />}{submitting ? "正在解析" : "导入并生成候选"}</button></footer></form></Dialog>;
}

function MemoryActionDialog({ action, memory, onClose, onComplete, roleId }: { action: MemoryAction; memory: MemoryCandidateItem; onClose: () => void; onComplete: (result: MemoryMutationResponse) => void; roleId: string }) {
  const copy: Record<MemoryAction, { title: string; button: string; reason: string }> = { approve: { title: "审核记忆候选", button: "确认批准", reason: "已核对原始依据与当前制度" }, reject: { title: "拒绝记忆候选", button: "确认拒绝", reason: "该内容不适合作为长期角色记忆" }, activate: { title: "启用长期记忆", button: "确认启用", reason: "允许该记忆参与分身推理上下文" }, retire: { title: "退役长期记忆", button: "确认退役", reason: "该记忆已被新经验或规则替代" } };
  const [reason, setReason] = useState(copy[action].reason);
  const [conflictResolution, setConflictResolution] = useState(memory.conflict_status === "conflicted" ? "retain_conflict" : "verified_clear");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const endpoint = action === "approve" || action === "reject" ? "review" : action;
      const body = action === "approve" || action === "reject" ? { decision: action, reason, ...(action === "approve" && memory.conflict_status !== "clear" ? { conflict_resolution: conflictResolution } : {}) } : { reason };
      const response = await apiFetch(`${API_BASE_URL}/api/v1/memories/${encodeURIComponent(memory.id)}/${endpoint}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "记忆状态更新失败"));
      onComplete((await response.json()) as MemoryMutationResponse);
    } catch (reasonValue: unknown) {
      setError(reasonValue instanceof Error ? reasonValue.message : "记忆状态更新失败");
    } finally {
      setSubmitting(false);
    }
  }

  const isDestructive = action === "reject" || action === "retire";
  return <ConfirmDialog busy={submitting} confirmDisabled={reason.trim().length < 2} confirmLabel={copy[action].button} description={`${copy[action].title}？`} detail={isDestructive ? "状态变更后不会删除原始依据和历史审计记录。" : "状态变更将立即影响后续分身上下文。"} onCancel={onClose} onConfirm={() => void submit()} title={copy[action].title} tone={isDestructive ? "danger" : "warning"}><div className="memory-action-target"><MemoryStick aria-hidden="true" size={18} /><div><strong>{memory.content}</strong><span>{memory.twin_name} · {memory.source_ref}</span></div></div>{action === "approve" && memory.conflict_status !== "clear" ? <label className="confirm-input-field"><span>冲突处理</span><select onChange={(event) => setConflictResolution(event.target.value)} value={conflictResolution}>{memory.conflict_status === "unverified" ? <option value="verified_clear">已核验，无制度冲突</option> : null}<option value="retain_conflict">保留冲突，仅作历史记录</option></select></label> : null}<label className="confirm-input-field"><span>操作原因</span><textarea autoFocus onChange={(event) => setReason(event.target.value)} rows={4} value={reason} /></label>{error ? <InlineCallout description={error} title="状态未更新" tone="critical" /> : null}</ConfirmDialog>;
}

function TwinTestRunner({ profiles, roleId }: { profiles: RoleTwinCatalogItem[]; roleId: string }) {
  const [twinKey, setTwinKey] = useState(profiles[0]?.key ?? "twin-ceo");
  const [question, setQuestion] = useState("9 月退款率如何考核？");
  const [answer, setAnswer] = useState<TwinAnswerResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runTest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRunning(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/twins/${encodeURIComponent(twinKey)}/answers`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ question, top_k: 5 })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "分身测试失败"));
      setAnswer((await response.json()) as TwinAnswerResponse);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "分身测试失败");
    } finally {
      setRunning(false);
    }
  }

  return <div className="twin-test-layout">
    <Surface className="twin-test-console" meta="调用数据库知识检索与当前 AI Provider" title="测试输入">
      <form onSubmit={(event) => void runTest(event)}>
        <label><span>目标分身</span><select onChange={(event) => setTwinKey(event.target.value)} value={twinKey}>{profiles.map((profile) => <option key={profile.key} value={profile.key}>{profile.display_name} · {profile.role_title}</option>)}</select></label>
        <label><span>固定评测问题</span><textarea onChange={(event) => setQuestion(event.target.value)} rows={5} value={question} /></label>
        <button className="button primary" disabled={running || question.trim().length < 2} type="submit">{running ? <LoaderCircle className="spinning" aria-hidden="true" size={16} /> : <Play aria-hidden="true" size={16} />}{running ? "正在运行" : "运行证据测试"}</button>
      </form>
      {error ? <InlineCallout description={error} title="测试未完成" tone="critical" /> : null}
    </Surface>
    <Surface className="twin-test-result" meta={answer ? `${answer.provider} · ${answer.duration_ms}ms` : "等待运行"} title="结构化回答">
      {answer ? <>
        <div className="test-answer-heading"><FlaskConical aria-hidden="true" size={19} /><div><strong>{answer.answer.summary}</strong><span>置信度 {answer.answer.confidence} · {answer.execution_mode}</span></div></div>
        <div className="test-answer-columns"><div><span>可核验事实</span>{answer.answer.facts.map((item) => <p key={item}>{item}</p>)}</div><div><span>行动建议</span>{answer.answer.actions.map((item) => <p key={item}>{item}</p>)}</div></div>
        <div className="test-evidence-list">{answer.metric_context.map((item, index) => <div key={`${item.key}-${item.scope_key}`}><b>D{index + 1}</b><span>{item.label} · {item.latest_value ?? "暂无"}{item.unit}</span><small>{item.scope_key} · 口径 {item.definition_version} · {item.points.length} 个日点</small></div>)}{answer.evidence.map((item, index) => <div key={item.chunk_id}><b>E{index + 1}</b><span>{item.document_title} {item.version_label}</span><small>{item.locator}</small></div>)}{answer.memory_context.map((item, index) => <div key={item.id}><b>M{index + 1}</b><span>长期记忆 v{item.version_number} · {item.category}</span><small>{item.source_ref}</small></div>)}</div>
      </> : <div className="twin-test-empty"><FlaskConical aria-hidden="true" size={25} /><strong>尚无测试结果</strong><span>运行后将展示结构化回答、证据和实际 Provider 模式。</span></div>}
    </Surface>
  </div>;
}

function TwinPageState({ icon, title, retry }: { icon: React.ReactNode; title: string; retry?: () => void }) {
  return <div className="twin-page-state">{icon}<strong>{title}</strong>{retry ? <button className="button secondary" onClick={retry} type="button">重新加载</button> : null}</div>;
}
