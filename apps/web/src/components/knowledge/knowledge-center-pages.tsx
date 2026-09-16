"use client";

import {
  AlertTriangle,
  Archive,
  BookOpenCheck,
  Boxes,
  CalendarClock,
  CheckCircle2,
  CircleAlert,
  Database,
  FileClock,
  FileSearch,
  FileUp,
  Files,
  Gauge,
  Play,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { ConfirmDialog, Dialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiErrorMessage } from "@/lib/api-error";
import { apiFetch } from "@/lib/api-client";
import type {
  EvidenceSearchResponse,
  KnowledgeDocument,
  KnowledgeDocumentListResponse,
  KnowledgeIngestionListResponse,
  KnowledgeIngestionResponse,
  KnowledgeLifecycleResponse,
  KnowledgeProviderEvaluationRun,
  KnowledgeProviderOperationsResponse,
  KnowledgeVersion
} from "@/lib/knowledge-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type KnowledgeCenterView = "documents" | "policies" | "ingestion" | "evidence";

interface LifecycleTarget {
  action: "publish" | "retire";
  document: KnowledgeDocument;
  version: KnowledgeVersion;
}

function formatTime(value: string | null): string {
  if (!value) return "未设置";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function statusLabel(value: string): string {
  return ({ active: "当前有效", published: "已发布 / 待生效", scheduled: "计划生效", draft: "草稿", archived: "已归档" } as Record<string, string>)[value] ?? value;
}

function statusTone(value: string): "positive" | "warning" | "info" | "neutral" {
  if (value === "active") return "positive";
  if (value === "published" || value === "scheduled") return "warning";
  if (value === "draft") return "info";
  return "neutral";
}

function sourceLabel(value: string): string {
  if (value === "simulated-enterprise-document") return "连接器企业资料";
  if (value === "uploaded-text") return "人工导入原件";
  return value;
}

function KnowledgeState({ loading, error }: { loading: boolean; error: string | null }) {
  return (
    <div className={`knowledge-state ${error ? "failed" : ""}`} role={error ? "alert" : "status"}>
      {error ? <FileSearch size={28} /> : <Database className={loading ? "spinning" : ""} size={28} />}
      <strong>{error ? "知识数据库读取失败" : "正在读取企业知识库"}</strong>
      <span>{error ?? "汇总文档、版本、切片和索引状态"}</span>
    </div>
  );
}

function KnowledgeStats({ data }: { data: KnowledgeDocumentListResponse }) {
  const activeVersions = data.items.flatMap((item) => item.versions).filter((item) => item.status === "active").length;
  return (
    <section className="knowledge-stat-band" aria-label="知识中心统计">
      <article><span><Files size={16} />知识文档</span><strong>{data.page.total}</strong><p>保留原件和稳定业务键</p></article>
      <article><span><FileClock size={16} />不可变版本</span><strong>{data.version_count}</strong><p>{activeVersions} 个当前有效版本</p></article>
      <article><span><Boxes size={16} />证据切片</span><strong>{data.chunk_count}</strong><p>按章节定位并已建立索引</p></article>
      <article><span><ShieldCheck size={16} />知识边界</span><strong>1</strong><p>企业范围与正式知识优先</p></article>
    </section>
  );
}

function DocumentTable({ documents }: { documents: KnowledgeDocument[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>知识文档</th><th>知识空间</th><th>版本 / 切片</th><th>责任方</th><th>更新时间</th><th>状态</th></tr></thead>
        <tbody>
          {documents.map((document) => (
            <tr key={document.id}>
              <td data-label="知识文档"><strong className="knowledge-primary">{document.title}</strong><small>{document.key} · {document.document_type}</small><div className="knowledge-tags">{document.tags.slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div></td>
              <td data-label="知识空间">{document.knowledge_space}<small>{sourceLabel(document.source_type)}</small></td>
              <td data-label="版本 / 切片"><strong>{document.versions.length} 个版本</strong><small>{document.versions.reduce((sum, version) => sum + version.chunk_count, 0)} 个可引用切片</small></td>
              <td data-label="责任方">{document.owner}</td>
              <td data-label="更新时间">{formatTime(document.updated_at)}</td>
              <td data-label="状态"><StatusBadge value={{ label: statusLabel(document.status), tone: statusTone(document.status) }} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VersionTable({
  canPublish,
  documents,
  onLifecycle
}: {
  canPublish: boolean;
  documents: KnowledgeDocument[];
  onLifecycle: (target: LifecycleTarget) => void;
}) {
  const rows = documents.flatMap((document) => document.versions.map((version) => ({ document, version })));
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>制度 / 版本</th><th>生效区间</th><th>变更摘要</th><th>证据切片</th><th>责任方</th><th>版本状态</th><th>生命周期</th></tr></thead>
        <tbody>
          {rows.map(({ document, version }) => (
            <tr key={version.id}>
              <td data-label="制度 / 版本"><strong className="knowledge-primary">{document.title}</strong><small>{version.version_label} · version #{version.version_number}</small></td>
              <td data-label="生效区间">{formatTime(version.effective_from)}<small>至 {formatTime(version.effective_until)}</small></td>
              <td className="knowledge-summary" data-label="变更摘要">{version.change_summary}</td>
              <td data-label="证据切片"><strong>{version.chunk_count}</strong><small>indexed</small></td>
              <td data-label="责任方">{document.owner}</td>
              <td data-label="版本状态"><StatusBadge value={{ label: statusLabel(version.status), tone: statusTone(version.status) }} /></td>
              <td data-label="生命周期">{canPublish && version.status === "draft" ? <button className="button compact secondary" onClick={() => onLifecycle({ action: "publish", document, version })} type="button"><CalendarClock size={14} />发布</button> : null}{canPublish && ["active", "published", "scheduled"].includes(version.status) ? <button className="button compact ghost-critical" onClick={() => onLifecycle({ action: "retire", document, version })} type="button"><Archive size={14} />退役</button> : null}{!canPublish || version.status === "archived" ? <span className="knowledge-readonly">只读</span> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IngestionTable({ documents }: { documents: KnowledgeDocument[] }) {
  const rows = documents.flatMap((document) => document.versions.map((version) => ({ document, version })));
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>导入对象</th><th>内容哈希</th><th>解析</th><th>切片</th><th>索引</th><th>运行状态</th></tr></thead>
        <tbody>
          {rows.map(({ document, version }) => (
            <tr key={version.id}>
              <td data-label="导入对象"><strong className="knowledge-primary">{document.title} {version.version_label}</strong><small>{version.id}</small></td>
              <td data-label="内容哈希"><code>{document.content_hash.slice(0, 12)}</code><small>SHA-256</small></td>
              <td data-label="解析"><CheckCircle2 className="knowledge-ok" size={17} />章节结构已识别</td>
              <td data-label="切片"><strong>{version.chunk_count} 个</strong><small>稳定定位</small></td>
              <td data-label="索引">local-lexical-v1<small>适配器可替换</small></td>
              <td data-label="运行状态"><StatusBadge value={{ label: "已完成", tone: "positive" }} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IngestionLedger({ data }: { data: KnowledgeIngestionListResponse | null }) {
  if (!data || data.items.length === 0) return <div className="knowledge-ingestion-empty"><FileUp size={22} /><strong>尚无人工导入运行</strong><span>种子知识已完成初始化；后续上传会在此形成数据库运行记录。</span></div>;
  return <div className="table-wrap knowledge-ingestion-ledger"><table><thead><tr><th>导入对象</th><th>来源 / 哈希</th><th>解析结果</th><th>冲突</th><th>主体 / 时间</th><th>追踪</th></tr></thead><tbody>
    {data.items.map((run) => <tr key={run.id}>
      <td data-label="导入对象"><strong className="knowledge-primary">{run.document_title ?? "未生成文档"}</strong><small>{run.document_key ?? "-"} · {run.version_label ?? "-"}</small></td>
      <td data-label="来源 / 哈希">{run.source_filename}<small><code>{run.content_hash.slice(0, 16)}</code></small></td>
      <td data-label="解析结果"><StatusBadge value={{ label: run.status === "completed" ? "已完成" : run.status === "duplicate" ? "重复文件" : "失败", tone: run.status === "completed" ? "positive" : run.status === "duplicate" ? "info" : "critical" }} /><small>{run.parser_provider} · {run.chunk_count} 切片</small></td>
      <td data-label="冲突">{run.warnings.length > 0 ? <strong className="knowledge-conflict-count"><AlertTriangle size={14} />{run.warnings.length} 项</strong> : <span>无</span>}<small>{run.warnings[0]?.summary ?? "内容规则未发现冲突"}</small></td>
      <td data-label="主体 / 时间">{run.actor_name}<small>{formatTime(run.created_at)}</small></td>
      <td data-label="追踪"><code>{run.request_id}</code><small>{run.run_id}</small></td>
    </tr>)}
  </tbody></table></div>;
}

function EvidenceSearch() {
  const { roleId } = useExperience();
  const [query, setQuery] = useState("9 月退款率如何考核？");
  const [result, setResult] = useState<EvidenceSearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = useCallback(async (nextQuery: string) => {
    const trimmed = nextQuery.trim();
    if (trimmed.length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/knowledge/evidence/search?query=${encodeURIComponent(trimmed)}&limit=12`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId } });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "证据检索接口不可用"));
      setResult((await response.json()) as EvidenceSearchResponse);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "证据检索失败");
    } finally {
      setLoading(false);
    }
  }, [roleId]);

  useEffect(() => { void search("9 月退款率如何考核？"); }, [search]);

  return (
    <section className="knowledge-evidence-workspace">
      <form onSubmit={(event) => { event.preventDefault(); void search(query); }}>
        <Search aria-hidden="true" size={17} />
        <input aria-label="检索企业证据" onChange={(event) => setQuery(event.target.value)} value={query} />
        <button className="button primary" disabled={loading} type="submit">{loading ? "检索中" : "检索证据"}</button>
      </form>
      <div className="knowledge-retrieval-meta"><span>检索器：{result?.retrieval_provider ?? "local-lexical-v1"}</span><span>结果：{result?.items.length ?? 0} 条</span><span>版本和生效时间随引用返回</span></div>
      {error ? <KnowledgeState error={error} loading={false} /> : null}
      <div className="knowledge-evidence-grid">
        {result?.items.map((item, index) => (
          <article key={item.chunk_id}>
            <header><span>E{index + 1}</span><StatusBadge value={{ label: statusLabel(item.version_status), tone: statusTone(item.version_status) }} /></header>
            <h2>{item.document_title} <small>{item.version_label}</small></h2>
            <p>{item.excerpt}</p>
            <footer><span>{item.locator}</span><span>相关度 {Math.round(item.score * 100)}%</span><span>{formatTime(item.effective_from)} 生效</span></footer>
          </article>
        ))}
      </div>
    </section>
  );
}

function KnowledgeProviderLab({ roleId, canRun }: { roleId: string; canRun: boolean }) {
  const { notify } = useNotifications();
  const [data, setData] = useState<KnowledgeProviderOperationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestKey, setRequestKey] = useState(() => `knowledge-provider-ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/knowledge/provider-operations`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId } });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "知识 Provider 运维数据不可用"));
      setData((await response.json()) as KnowledgeProviderOperationsResponse);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "知识 Provider 运维数据读取失败");
    } finally {
      setLoading(false);
    }
  }, [roleId]);

  useEffect(() => { void load(); }, [load]);

  const run = async () => {
    if (!data || !canRun) return;
    setRunning(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/knowledge/provider-evaluations`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ schema_version: 1, client_request_key: requestKey, provider_keys: data.providers.map((item) => item.key), top_k: 3 })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "知识与上下文 Provider 评测失败"));
      const result = await response.json() as KnowledgeProviderEvaluationRun;
      notify({ title: result.idempotent ? "已复用评测运行" : "Provider 评测已完成", description: `${result.case_count} 道生效知识检索题`, tone: "success" });
      setRequestKey(`knowledge-provider-ui-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`);
      await load();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "知识与上下文 Provider 评测失败");
    } finally {
      setRunning(false);
    }
  };

  const latest = data?.runs[0];
  return (
    <section className="knowledge-provider-lab" aria-labelledby="knowledge-provider-lab-title">
      <header>
        <div><span className="knowledge-section-kicker">RETRIEVAL / CONTEXT ADAPTER LAB · 0029+</span><h2 id="knowledge-provider-lab-title">知识与上下文 Provider 多路评测</h2><p>平台知识版本仍是唯一事实来源；WeKnora、RAGFlow 与 OpenViking 只接收当前运行的隔离副本，并按固定题集返回稳定证据键。</p></div>
        <button className="button primary" disabled={!canRun || running || loading || !data} onClick={() => void run()} type="button"><Play size={15} />{running ? "评测中" : `发起 ${data?.providers.length ?? 3} 路评测`}</button>
      </header>
      <div className="knowledge-provider-summary">
        <span><strong>{data?.active_document_count ?? "—"}</strong><small>当前生效文档</small></span>
        <span><strong>{data?.active_chunk_count ?? "—"}</strong><small>当前索引切片</small></span>
        <span><strong>{data?.benchmark_cases.length ?? "—"}</strong><small>固定评测题</small></span>
        <span><strong>{latest ? formatTime(latest.finished_at) : "尚无运行"}</strong><small>最近运行</small></span>
      </div>
      {error ? <InlineCallout description={error} title="Provider 运维台不可用" tone="critical" /> : null}
      {!canRun ? <InlineCallout description="当前身份可读取知识检索，但没有发起 Provider 评测的权限。" title="需要评测权限" tone="warning" /> : null}
      <div className="knowledge-provider-grid">
        {(data?.providers ?? []).map((provider) => {
          const result = latest?.results.find((item) => item.provider_key === provider.key);
          return <article key={provider.key}>
            <header><div><Server size={17} /><span><strong>{provider.label}</strong><small>{provider.protocol}</small></span></div><StatusBadge value={{ label: provider.mode, tone: provider.mode === "contract-sandbox" ? "info" : "positive" }} /></header>
            <div className="knowledge-provider-mode"><span>端点指纹</span><code>{provider.endpoint_fingerprint}</code><span>{provider.authentication_configured ? "已配置认证" : "未配置认证 / 本地沙箱"}</span></div>
            <dl><div><dt>Recall@3</dt><dd>{result ? `${Math.round(result.recall_at_k * 100)}%` : "—"}</dd></div><div><dt>MRR</dt><dd>{result ? `${Math.round(result.mean_reciprocal_rank * 100)}%` : "—"}</dd></div><div><dt>平均延迟</dt><dd>{result ? `${result.average_latency_ms} ms` : "—"}</dd></div><div><dt>索引切片</dt><dd>{result?.indexed_chunk_count ?? "—"}</dd></div></dl>
            <footer><span>{result ? `${result.hit_count}/${result.query_count} 题命中` : "等待首次双跑"}</span><span>{result?.status === "succeeded" ? "结果已审计" : result?.failure_reason ?? "可替换连接器"}</span></footer>
          </article>;
        })}
      </div>
      {latest ? <div className="knowledge-provider-latest"><div><Gauge size={15} /><strong>最近运行 · {latest.evaluation_key}</strong><span>{latest.actor_name} · {formatTime(latest.started_at)} · {latest.benchmark_version}</span></div><span>{latest.status === "completed" ? `${latest.provider_keys.length} 路 Provider 完成` : latest.status}</span></div> : null}
      {loading && !data ? <div className="knowledge-provider-loading">正在读取当前生效知识与 Provider 状态…</div> : null}
    </section>
  );
}

function KnowledgeEvidencePage() {
  const { can, roleId } = useExperience();
  return <div className="knowledge-page"><PageHeader description="按企业问题检索实际可引用的文档版本、原文位置、生效时间和相关度。" eyebrow="EVIDENCE SEARCH · RETRIEVAL VIEW" meta="数据库实时检索" title="引用与证据检索" /><KnowledgeProviderLab canRun={can("knowledge.provider.evaluate")} roleId={roleId} /><EvidenceSearch /></div>;
}

function KnowledgeImportDialog({
  onClose,
  onComplete,
  roleId
}: {
  onClose: () => void;
  onComplete: (result: KnowledgeIngestionResponse) => void;
  roleId: string;
}) {
  const [form, setForm] = useState({
    document_key: "",
    title: "",
    document_type: "policy",
    knowledge_space: "企业制度",
    owner: "数字平台中心",
    tags: "",
    source_filename: "manual-import.md",
    version_label: "v1",
    content: "",
    change_summary: "首次导入"
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/knowledge/ingestions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ ...form, tags: form.tags.split(/[，,]/).map((item) => item.trim()).filter(Boolean) })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "知识原件导入失败"));
      onComplete((await response.json()) as KnowledgeIngestionResponse);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "知识原件导入失败");
    } finally {
      setSubmitting(false);
    }
  };

  return <Dialog busy={submitting} className="knowledge-dialog unified" eyebrow="KNOWLEDGE INGESTION · R1" onClose={onClose} size="large" title="导入企业资料原件">
    <form onSubmit={(event) => void submit(event)}>
      <label className="knowledge-file-picker"><FileUp size={18} /><span><strong>选择 Markdown 或文本原件</strong><small>{form.source_filename}</small></span><input accept=".md,.txt,text/markdown,text/plain" onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; void file.text().then((content) => setForm((current) => ({ ...current, content, source_filename: file.name, title: current.title || file.name.replace(/\.[^.]+$/, "") }))); }} type="file" /></label>
      <div className="knowledge-form-grid">
        <label><span>稳定文档键</span><input onChange={(event) => setForm({ ...form, document_key: event.target.value.toLocaleLowerCase() })} pattern="[a-z0-9][a-z0-9._-]+" placeholder="policy-store-service" required value={form.document_key} /></label>
        <label><span>文档标题</span><input onChange={(event) => setForm({ ...form, title: event.target.value })} required value={form.title} /></label>
        <label><span>文档类型</span><select onChange={(event) => setForm({ ...form, document_type: event.target.value })} value={form.document_type}><option value="policy">制度</option><option value="manual">操作手册</option><option value="handbook">员工手册</option><option value="decision">决策记录</option></select></label>
        <label><span>知识空间</span><input onChange={(event) => setForm({ ...form, knowledge_space: event.target.value })} required value={form.knowledge_space} /></label>
        <label><span>责任方</span><input onChange={(event) => setForm({ ...form, owner: event.target.value })} required value={form.owner} /></label>
        <label><span>版本标签</span><input onChange={(event) => setForm({ ...form, version_label: event.target.value })} required value={form.version_label} /></label>
        <label className="wide"><span>标签</span><input onChange={(event) => setForm({ ...form, tags: event.target.value })} placeholder="客服, 退款率, 考核" value={form.tags} /></label>
        <label className="wide"><span>变更摘要</span><input onChange={(event) => setForm({ ...form, change_summary: event.target.value })} required value={form.change_summary} /></label>
        <label className="wide"><span>原件正文</span><textarea onChange={(event) => setForm({ ...form, content: event.target.value })} placeholder="# 章节标题&#10;制度正文……" required rows={10} value={form.content} /></label>
      </div>
      {error ? <InlineCallout description={error} title="导入未完成" tone="critical" /> : null}
      <footer><button className="button secondary" onClick={onClose} type="button">取消</button><button className="button primary" disabled={submitting} type="submit"><FileUp size={15} />{submitting ? "正在导入" : "导入为草稿"}</button></footer>
    </form>
  </Dialog>;
}

function LifecycleDialog({
  onClose,
  onComplete,
  roleId,
  target
}: {
  onClose: () => void;
  onComplete: (result: KnowledgeLifecycleResponse) => void;
  roleId: string;
  target: LifecycleTarget;
}) {
  const [effectiveFrom, setEffectiveFrom] = useState(toLocalInputValue(new Date(Date.now() + 86_400_000)));
  const [reason, setReason] = useState(target.action === "publish" ? "负责人确认版本内容与生效窗口" : "负责人确认该版本停止生效");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/knowledge/versions/${target.version.id}/${target.action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify(target.action === "publish" ? { effective_from: new Date(effectiveFrom).toISOString(), reason } : { reason })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, target.action === "publish" ? "制度发布失败" : "制度退役失败"));
      onComplete((await response.json()) as KnowledgeLifecycleResponse);
    } catch (reasonValue: unknown) {
      setError(reasonValue instanceof Error ? reasonValue.message : "制度生命周期操作失败");
    } finally {
      setSubmitting(false);
    }
  };
  const publishing = target.action === "publish";
  return <ConfirmDialog busy={submitting} confirmDisabled={reason.trim().length < 2 || (publishing && !effectiveFrom)} confirmLabel={publishing ? "确认发布" : "确认退役"} description={`${publishing ? "发布" : "退役"} ${target.document.title} ${target.version.version_label}？`} detail={publishing ? "生效后将作为正式规则参与检索与回答。" : "历史内容和引用继续保留，但不再作为生效规则返回。"} onCancel={onClose} onConfirm={() => void submit()} title={publishing ? "发布制度版本" : "退役制度版本"} tone={publishing ? "warning" : "danger"}><div className="knowledge-lifecycle-target"><strong>{target.document.title}</strong><span>{target.version.version_label} · {target.version.change_summary}</span></div>{publishing ? <label className="confirm-input-field"><span>计划生效时间</span><input onChange={(event) => setEffectiveFrom(event.target.value)} required type="datetime-local" value={effectiveFrom} /></label> : null}<label className="confirm-input-field"><span>操作原因</span><textarea autoFocus={!publishing} onChange={(event) => setReason(event.target.value)} required rows={4} value={reason} /></label>{error ? <InlineCallout description={error} title="操作未完成" tone="critical" /> : null}</ConfirmDialog>;
}

function toLocalInputValue(value: Date): string {
  const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

const VIEW_COPY: Record<Exclude<KnowledgeCenterView, "evidence">, { eyebrow: string; title: string; description: string }> = {
  documents: { eyebrow: "KNOWLEDGE CATALOG · DATABASE VIEW", title: "企业知识文档", description: "集中管理制度、手册和决策记录的原件、版本、哈希与知识空间。" },
  policies: { eyebrow: "POLICY LIFECYCLE · VERSIONED", title: "制度版本与生效规则", description: "版本不可覆盖修改，当前规则、未来生效版本和历史区间可同时追溯。" },
  ingestion: { eyebrow: "INGESTION PIPELINE · TRACEABLE", title: "知识解析与索引运行", description: "逐个版本检查内容哈希、章节解析、证据切片和检索索引状态。" }
};

export function KnowledgeCenterPage({ view }: { view: KnowledgeCenterView }) {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<KnowledgeDocumentListResponse | null>(null);
  const [ingestionRuns, setIngestionRuns] = useState<KnowledgeIngestionListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [reloadToken, setReloadToken] = useState(0);
  const [importOpen, setImportOpen] = useState(false);
  const [lifecycleTarget, setLifecycleTarget] = useState<LifecycleTarget | null>(null);

  useEffect(() => {
    if (view === "evidence") return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    apiFetch(`${API_BASE_URL}/api/v1/knowledge/documents?limit=100`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId }, signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiErrorMessage(response, "知识中心接口不可用"));
        return response.json() as Promise<KnowledgeDocumentListResponse>;
      })
      .then(setData)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "无法读取知识中心");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [reloadToken, roleId, view]);

  useEffect(() => {
    if (view !== "ingestion" || !can("knowledge.document.ingest")) {
      setIngestionRuns(null);
      return;
    }
    const controller = new AbortController();
    apiFetch(`${API_BASE_URL}/api/v1/knowledge/ingestions?limit=50`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId }, signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiErrorMessage(response, "知识导入台账不可用"));
        return response.json() as Promise<KnowledgeIngestionListResponse>;
      })
      .then(setIngestionRuns)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "知识导入台账读取失败");
      });
    return () => controller.abort();
  }, [can, reloadToken, roleId, view]);

  if (view === "evidence") {
    return <KnowledgeEvidencePage />;
  }

  const copy = VIEW_COPY[view];
  const filtered = useMemo(() => {
    const source = view === "policies" ? data?.items.filter((item) => item.document_type === "policy") : data?.items;
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return source ?? [];
    return (source ?? []).filter((item) => `${item.title} ${item.key} ${item.owner} ${item.tags.join(" ")}`.toLocaleLowerCase().includes(normalized));
  }, [data, query, view]);

  return (
    <div className="knowledge-page">
      <PageHeader actions={<div className="knowledge-page-actions">{view === "ingestion" && can("knowledge.document.ingest") ? <button className="button primary" onClick={() => setImportOpen(true)} type="button"><FileUp size={15} />导入资料</button> : null}<button aria-label="刷新知识数据" className="icon-button" onClick={() => setReloadToken((value) => value + 1)} title="刷新知识数据" type="button"><RefreshCw size={16} /></button></div>} description={copy.description} eyebrow={copy.eyebrow} meta="数据库实时读取" title={copy.title} />
      {!data ? <KnowledgeState error={error} loading={loading} /> : <>
        <KnowledgeStats data={data} />
        <section className="knowledge-table-panel">
          <header><div><BookOpenCheck size={18} /><span><strong>{view === "documents" ? "知识资产目录" : view === "policies" ? "制度版本台账" : "版本处理流水线"}</strong><small>生成于 {formatTime(data.generated_at)}</small></span></div><label><Search size={15} /><input aria-label="搜索知识资产" onChange={(event) => setQuery(event.target.value)} placeholder="搜索标题、标签或责任方" value={query} /></label></header>
          {view === "documents" ? <DocumentTable documents={filtered} /> : null}
          {view === "policies" ? <VersionTable canPublish={can("knowledge.policy.publish")} documents={filtered} onLifecycle={setLifecycleTarget} /> : null}
          {view === "ingestion" ? <IngestionTable documents={filtered} /> : null}
          <footer><span>显示 {filtered.length} / {view === "policies" ? data.items.filter((item) => item.document_type === "policy").length : data.items.length} 个知识对象</span><span>数据源：knowledge_documents · knowledge_versions · knowledge_chunks</span></footer>
        </section>
        {view === "ingestion" && can("knowledge.document.ingest") ? <section className="knowledge-table-panel knowledge-run-panel"><header><div><FileUp size={18} /><span><strong>人工导入运行台账</strong><small>完成、重复、冲突与失败均保留追踪信息</small></span></div><em>{ingestionRuns?.items.length ?? 0} 条运行</em></header><IngestionLedger data={ingestionRuns} /></section> : null}
      </>}
      {importOpen ? <KnowledgeImportDialog onClose={() => setImportOpen(false)} onComplete={(result) => { setImportOpen(false); notify({ title: result.duplicate ? "知识原件已存在" : "知识原件已导入", description: result.duplicate ? `复用 ${result.version.version_label}` : `${result.document.title} ${result.version.version_label} · ${result.version.chunk_count} 个证据切片`, tone: "success" }); setReloadToken((value) => value + 1); }} roleId={roleId} /> : null}
      {lifecycleTarget ? <LifecycleDialog onClose={() => setLifecycleTarget(null)} onComplete={(result) => { setLifecycleTarget(null); notify({ title: result.event_type === "published" ? "制度版本已发布" : "制度版本已退役", description: `${result.document_key} ${result.version.version_label}`, tone: "success" }); setReloadToken((value) => value + 1); }} roleId={roleId} target={lifecycleTarget} /> : null}
    </div>
  );
}
