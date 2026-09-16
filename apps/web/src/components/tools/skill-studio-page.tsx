"use client";

import {
  CheckCircle2,
  CircleAlert,
  GitBranch,
  LoaderCircle,
  Plus,
  RefreshCw,
  Rocket,
  Sparkles,
  Wrench
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { Drawer, ConfirmDialog, useNotifications } from "@/components/console/interaction";
import { useExperience } from "@/demo/experience-provider";
import { apiErrorMessage } from "@/lib/api-error";
import { apiFetch } from "@/lib/api-client";
import type {
  SkillDefinition,
  SkillStudioMutationResponse,
  SkillStudioResponse,
  SkillVersion
} from "@/lib/skill-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type EditorState = { kind: "create" } | { kind: "version"; skill: SkillDefinition };
type PublishTarget = { skill: SkillDefinition; version: SkillVersion };
type MutationExecutor = (path: string, body: Record<string, unknown>) => Promise<SkillStudioMutationResponse>;

export function SkillStudioPage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [studio, setStudio] = useState<SkillStudioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [publishTarget, setPublishTarget] = useState<PublishTarget | null>(null);
  const canManage = can("skill.registry.manage");

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/skills/studio`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取 Skill 注册表"));
    const result = (await response.json()) as SkillStudioResponse;
    setStudio(result);
    setSelectedKey((current) => current && result.skills.some((item) => item.key === current) ? current : result.skills[0]?.key ?? null);
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Skill 注册表连接失败"))
      .finally(() => setLoading(false));
  }, [load]);

  const mutate = useCallback<MutationExecutor>(async (path, body) => {
    const response = await apiFetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
      body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "Skill 配置写入失败"));
    const result = (await response.json()) as SkillStudioMutationResponse;
    setStudio(result.studio);
    setSelectedKey(result.event.skill_key);
    notify({
      title: result.idempotent ? "版本已是当前状态" : "Skill 配置已写入",
      description: `${result.event.skill_key} · v${result.event.version_number}`,
      tone: "success"
    });
    return result;
  }, [notify, roleId]);

  const selected = useMemo(
    () => studio?.skills.find((item) => item.key === selectedKey) ?? studio?.skills[0] ?? null,
    [selectedKey, studio]
  );

  if (loading) return <SkillStudioState title="正在读取 Skill 注册表" />;
  if (!studio) return <SkillStudioState error title={error ?? "Skill 注册表暂不可用"} retry={() => void load()} />;

  return (
    <div className="identity-admin-page skill-studio-page">
      <PageHeader
        actions={<div className="identity-header-actions">
          {canManage ? <button className="button primary" onClick={() => setEditor({ kind: "create" })} type="button"><Plus size={15} />新建 Skill</button> : null}
          <button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新注册表</button>
        </div>}
        eyebrow="AI 能力治理"
        meta={`数据库 · ${studio.stats.skill_count} 个 Skill`}
        title="Skill 注册与版本治理"
      />
      {error ? <InlineCallout description={error} title="最近一次刷新失败" tone="critical" /> : null}
      {!canManage ? <InlineCallout description="当前身份仅可查看已登记 Skill。" title="只读 Skill Studio" tone="info" /> : null}
      <SkillStats studio={studio} />
      <div className="skill-studio-layout">
        <section className="identity-data-panel skill-registry-panel">
          <header><div><span>SKILL REGISTRY</span><h2>已登记能力</h2></div><em>{studio.skills.length} 个</em></header>
          <div className="skill-list">
            {studio.skills.map((skill) => <SkillListItem key={skill.key} active={selected?.key === skill.key} onClick={() => setSelectedKey(skill.key)} skill={skill} />)}
          </div>
        </section>
        <SkillDetail canManage={canManage} onCreateVersion={(skill) => setEditor({ kind: "version", skill })} onPublish={(target) => setPublishTarget(target)} skill={selected} />
      </div>
      {editor ? <SkillEditorDialog availableTools={studio.available_tools} execute={mutate} onClose={() => setEditor(null)} onComplete={() => setEditor(null)} state={editor} /> : null}
      {publishTarget ? <SkillPublishDialog execute={mutate} onClose={() => setPublishTarget(null)} onComplete={() => setPublishTarget(null)} target={publishTarget} /> : null}
    </div>
  );
}

function SkillStats({ studio }: { studio: SkillStudioResponse }) {
  const items = [
    ["已登记 Skill", studio.stats.skill_count, <Sparkles key="skills" size={16} />],
    ["已发布 Skill", studio.stats.published_skill_count, <CheckCircle2 key="published" size={16} />],
    ["草稿版本", studio.stats.draft_version_count, <GitBranch key="draft" size={16} />],
    ["已发布版本", studio.stats.published_version_count, <Rocket key="versions" size={16} />],
    ["可编排工具", studio.stats.registered_tool_count, <Wrench key="tools" size={16} />]
  ];
  return <section className="identity-stat-band" aria-label="Skill 注册统计">{items.map(([label, value, icon]) => <article key={String(label)}><span>{icon}{label}</span><strong>{value}</strong></article>)}</section>;
}

function SkillListItem({ active, onClick, skill }: { active: boolean; onClick: () => void; skill: SkillDefinition }) {
  const current = currentVersion(skill);
  return <button className={`skill-list-item ${active ? "active" : ""}`} onClick={onClick} type="button">
    <span className="skill-list-icon"><Sparkles size={17} /></span>
    <span className="skill-list-copy"><strong>{skill.name}</strong><small>{skill.key}</small></span>
    <span className="skill-list-meta"><StatusBadge value={{ label: statusLabel(skill.status), tone: statusTone(skill.status) }} /><small>{current ? `v${current.version_number}` : "未发布"}</small></span>
  </button>;
}

function SkillDetail({ canManage, onCreateVersion, onPublish, skill }: { canManage: boolean; onCreateVersion: (skill: SkillDefinition) => void; onPublish: (target: PublishTarget) => void; skill: SkillDefinition | null }) {
  if (!skill) return <section className="identity-data-panel skill-detail-panel"><div className="skill-empty"><Sparkles size={26} /><strong>暂无 Skill</strong></div></section>;
  const current = currentVersion(skill);
  return <section className="identity-data-panel skill-detail-panel">
    <header><div><span>{skill.key}</span><h2>{skill.name}</h2></div><StatusBadge value={{ label: statusLabel(skill.status), tone: statusTone(skill.status) }} /></header>
    <div className="skill-detail-body">
      <p className="skill-description">{skill.description}</p>
      <div className="skill-detail-actions">{canManage ? <button className="button secondary compact" onClick={() => onCreateVersion(skill)} type="button"><GitBranch size={14} />创建新版本</button> : null}</div>
      {current ? <div className="skill-current-version"><div><span>当前版本</span><strong>v{current.version_number}</strong></div><StatusBadge value={{ label: statusLabel(current.status), tone: statusTone(current.status) }} /><small>{formatTime(current.published_at ?? current.created_at)}</small></div> : null}
      <div className="skill-version-list">
        <div className="skill-section-heading"><span>VERSION LEDGER</span><strong>版本历史</strong></div>
        {skill.versions.map((version) => <SkillVersionRow canManage={canManage} key={version.id} onPublish={() => onPublish({ skill, version })} version={version} />)}
      </div>
    </div>
  </section>;
}

function SkillVersionRow({ canManage, onPublish, version }: { canManage: boolean; onPublish: () => void; version: SkillVersion }) {
  return <article className="skill-version-row">
    <div className="skill-version-main"><span className="skill-version-number">v{version.version_number}</span><div><strong>{version.change_summary}</strong><small>{version.created_by ?? "系统"} · {formatTime(version.created_at)}</small></div></div>
    <div className="skill-version-tools">{version.tool_keys.map((key) => <code key={key}>{key}</code>)}</div>
    <div className="skill-version-actions"><StatusBadge value={{ label: statusLabel(version.status), tone: statusTone(version.status) }} />{canManage && version.status === "draft" ? <button className="button secondary compact" onClick={onPublish} type="button"><Rocket size={13} />发布</button> : null}</div>
  </article>;
}

function SkillEditorDialog({ availableTools, execute, onClose, onComplete, state }: { availableTools: string[]; execute: MutationExecutor; onClose: () => void; onComplete: () => void; state: EditorState }) {
  const skill = state.kind === "version" ? state.skill : undefined;
  const current = skill ? currentVersion(skill) : undefined;
  const [skillKey, setSkillKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState(current?.instructions ?? "");
  const [toolKeys, setToolKeys] = useState<string[]>(current?.tool_keys ?? []);
  const [inputSchema, setInputSchema] = useState(JSON.stringify(current?.input_schema ?? { type: "object" }, null, 2));
  const [outputSchema, setOutputSchema] = useState(JSON.stringify(current?.output_schema ?? { type: "object" }, null, 2));
  const [summary, setSummary] = useState(skill ? "更新 Skill 执行规则" : "建立 Skill 初始版本");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const formId = "skill-editor-form";

  function toggleTool(tool: string) { setToolKeys((currentTools) => currentTools.includes(tool) ? currentTools.filter((item) => item !== tool) : [...currentTools, tool]); }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const parsedInput = JSON.parse(inputSchema) as Record<string, unknown>;
      const parsedOutput = JSON.parse(outputSchema) as Record<string, unknown>;
      const fields = { instructions, tool_keys: toolKeys, input_schema: parsedInput, output_schema: parsedOutput, change_summary: summary };
      await execute(skill ? `/api/v1/skills/${skill.key}/versions` : "/api/v1/skills", skill ? fields : { skill_key: skillKey, name, description, ...fields });
      onComplete();
    } catch (reason: unknown) {
      setError(reason instanceof SyntaxError ? "Schema 必须是有效 JSON" : reason instanceof Error ? reason.message : "Skill 配置保存失败");
    } finally { setSubmitting(false); }
  }
  return <Drawer busy={submitting} className="skill-studio-dialog" eyebrow="SKILL REGISTRY" footer={<><button className="button secondary" disabled={submitting} onClick={onClose} type="button">取消</button><button className="button primary" disabled={submitting || toolKeys.length === 0} form={formId} type="submit">{submitting ? <LoaderCircle className="spinning" size={15} /> : <GitBranch size={15} />}{skill ? "保存新版本" : "创建 Skill 草稿"}</button></>} onClose={onClose} size="large" title={skill ? `${skill.name} · 创建新版本` : "新建 Skill"}>
    <form className="role-studio-editor-form" id={formId} onSubmit={submit}>
      {skill ? <div className="role-editor-target"><Sparkles size={19} /><div><strong>{skill.name}</strong><span>{skill.key} · 当前 v{skill.current_version_number ?? "未发布"}</span></div></div> : <div className="role-editor-grid"><FormField label="Skill 稳定键"><input onChange={(event) => setSkillKey(event.target.value)} pattern="[a-z0-9][a-z0-9._-]+" required value={skillKey} /></FormField><FormField label="名称"><input onChange={(event) => setName(event.target.value)} required value={name} /></FormField><FormField className="wide" label="描述"><textarea onChange={(event) => setDescription(event.target.value)} required value={description} /></FormField></div>}
      <div className="role-editor-grid"><FormField className="wide" label="执行指令"><textarea minLength={10} onChange={(event) => setInstructions(event.target.value)} required value={instructions} /></FormField><FormField className="wide" label="变更摘要"><input onChange={(event) => setSummary(event.target.value)} required value={summary} /></FormField><FormField className="wide" label="可编排工具"><div className="skill-tool-picker">{availableTools.map((tool) => <label className={toolKeys.includes(tool) ? "selected" : ""} key={tool}><input checked={toolKeys.includes(tool)} onChange={() => toggleTool(tool)} type="checkbox" />{tool}</label>)}</div></FormField><FormField label="输入 Schema"><textarea className="skill-schema-input" onChange={(event) => setInputSchema(event.target.value)} required value={inputSchema} /></FormField><FormField label="输出 Schema"><textarea className="skill-schema-input" onChange={(event) => setOutputSchema(event.target.value)} required value={outputSchema} /></FormField></div>
      {error ? <InlineCallout description={error} title="无法保存 Skill 版本" tone="critical" /> : null}
    </form>
  </Drawer>;
}

function SkillPublishDialog({ execute, onClose, onComplete, target }: { execute: MutationExecutor; onClose: () => void; onComplete: () => void; target: PublishTarget }) {
  const [reason, setReason] = useState(`审核通过并发布 ${target.skill.key} v${target.version.version_number}`);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit() {
    setSubmitting(true);
    setError(null);
    try { await execute(`/api/v1/skills/${target.skill.key}/versions/${target.version.version_number}/publish`, { reason }); onComplete(); }
    catch (reasonValue: unknown) { setError(reasonValue instanceof Error ? reasonValue.message : "Skill 发布失败"); }
    finally { setSubmitting(false); }
  }
  return <ConfirmDialog busy={submitting} confirmDisabled={reason.trim().length < 2} confirmLabel="确认发布" description={`发布 ${target.skill.name} v${target.version.version_number}？`} detail="新运行将读取此版本，历史版本保留。" onCancel={onClose} onConfirm={() => void submit()} title="发布 Skill 版本" tone="warning">
    <div className="role-publish-target"><Rocket size={20} /><div><strong>Skill 版本</strong><span>{target.skill.key} · v{target.version.version_number}</span></div></div><label className="confirm-input-field"><span>发布原因</span><textarea autoFocus onChange={(event) => setReason(event.target.value)} required value={reason} /></label>{error ? <InlineCallout description={error} title="无法发布版本" tone="critical" /> : null}
  </ConfirmDialog>;
}

function currentVersion(skill: SkillDefinition): SkillVersion | undefined { return skill.versions.find((item) => item.version_number === skill.current_version_number) ?? skill.versions[0]; }
function statusLabel(status: string): string { return { draft: "草稿", published: "已发布", retired: "已退役" }[status] ?? status; }
function statusTone(status: string): "positive" | "warning" | "neutral" { return status === "published" ? "positive" : status === "draft" ? "warning" : "neutral"; }
function formatTime(value: string): string { return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)); }
function FormField({ children, className = "", label }: { children: React.ReactNode; className?: string; label: string }) { return <label className={className}><span>{label}</span>{children}</label>; }
function SkillStudioState({ error = false, retry, title }: { error?: boolean; retry?: () => void; title: string }) { return <div className={`identity-page-state ${error ? "error" : ""}`}>{error ? <CircleAlert size={27} /> : <LoaderCircle className="spinning" size={27} />}<strong>{title}</strong>{retry ? <button className="button secondary" onClick={retry} type="button"><RefreshCw size={14} />重新连接</button> : null}</div>; }
