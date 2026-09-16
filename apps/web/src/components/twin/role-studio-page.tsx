"use client";

import {
  Activity,
  Bot,
  Boxes,
  CheckCircle2,
  CircleAlert,
  Database,
  FileClock,
  GitBranch,
  History,
  LoaderCircle,
  Plus,
  RefreshCw,
  Rocket,
  ShieldCheck,
  Sparkles
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { ConfirmDialog, Drawer, useNotifications } from "@/components/console/interaction";
import { useExperience } from "@/demo/experience-provider";
import { apiErrorMessage } from "@/lib/api-error";
import { apiFetch } from "@/lib/api-client";
import type {
  RoleStudioMutationResponse,
  RoleStudioResponse,
  RoleTemplate,
  RoleTemplateVersion,
  RoleTwinInstance,
  RoleTwinVersion
} from "@/lib/role-studio-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type RoleStudioView = "templates" | "instances" | "prompts";

type EditorState =
  | { kind: "template"; template?: RoleTemplate }
  | { kind: "twin"; twin?: RoleTwinInstance };

type PublishTarget = {
  kind: "template" | "twin";
  key: string;
  label: string;
  versionNumber: number;
};

type MutationExecutor = (
  path: string,
  body: Record<string, unknown>
) => Promise<RoleStudioMutationResponse>;

const VIEW_COPY: Record<RoleStudioView, { eyebrow: string; title: string; description: string }> = {
  templates: {
    eyebrow: "ROLE TEMPLATE REGISTRY · DATABASE VIEW",
    title: "岗位模板资产",
    description: "把岗位职责、能力边界和通用分析规则沉淀为可复用、可发布的企业资产。"
  },
  instances: {
    eyebrow: "ROLE TWIN STUDIO · DATABASE VIEW",
    title: "角色分身实例",
    description: "将岗位模板绑定具体负责人，独立管理表达方式、推理规则、模型和能力范围。"
  },
  prompts: {
    eyebrow: "IMMUTABLE CONFIG LEDGER · DATABASE VIEW",
    title: "分身配置版本",
    description: "查看每次分身配置发布，追溯当前运行所使用的模型、角色边界和不可变历史版本。"
  }
};

function formatTime(value: string | null): string {
  if (!value) return "尚未发布";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(new Date(value));
}

function statusLabel(status: string): string {
  return { draft: "草稿", published: "已发布", retired: "已退役", active: "有效" }[status] ?? status;
}

function statusTone(status: string): "positive" | "warning" | "neutral" {
  if (status === "published" || status === "active") return "positive";
  if (status === "draft") return "warning";
  return "neutral";
}

function currentTemplateVersion(template: RoleTemplate): RoleTemplateVersion | undefined {
  return template.versions.find((item) => item.version_number === template.current_version_number)
    ?? template.versions[0];
}

function currentTwinVersion(twin: RoleTwinInstance): RoleTwinVersion | undefined {
  return twin.versions.find((item) => item.version_number === twin.current_version_number)
    ?? twin.versions[0];
}

function parseList(value: string): string[] {
  return value.split(/[\n,，]+/).map((item) => item.trim()).filter(Boolean);
}

export function RoleStudioPage({ view }: { view: RoleStudioView }) {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [studio, setStudio] = useState<RoleStudioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [publishTarget, setPublishTarget] = useState<PublishTarget | null>(null);
  const canConfigure = can("role-twin.configure");

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/role-studio`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取角色分身工作室"));
    setStudio((await response.json()) as RoleStudioResponse);
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "角色分身工作室连接失败"))
      .finally(() => setLoading(false));
  }, [load]);

  const mutate = useCallback<MutationExecutor>(async (path, body) => {
    const response = await apiFetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Zhixing-Demo-Actor": roleId
      },
      body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "角色配置写入失败"));
    const result = (await response.json()) as RoleStudioMutationResponse;
    setStudio(result.studio);
    notify({
      title: "角色配置已写入",
      description: `${result.event.configuration_key} v${result.event.version_number} · ${result.event.actor_name}`,
      tone: "success"
    });
    return result;
  }, [notify, roleId]);

  if (loading) {
    return <RoleStudioState icon={<LoaderCircle className="spinning" />} title="正在读取岗位模板与分身版本" />;
  }
  if (!studio) {
    return <RoleStudioState icon={<CircleAlert />} title={error ?? "角色分身工作室暂不可用"} retry={() => void load()} />;
  }

  const copy = VIEW_COPY[view];
  return (
    <div className="role-studio-page">
      <PageHeader
        actions={<div className="role-studio-page-actions">
          {canConfigure && view === "templates" ? (
            <button className="button primary" onClick={() => setEditor({ kind: "template" })} type="button">
              <Plus aria-hidden="true" size={15} />新建岗位模板
            </button>
          ) : null}
          {canConfigure && view === "instances" ? (
            <button className="button primary" onClick={() => setEditor({ kind: "twin" })} type="button">
              <Plus aria-hidden="true" size={15} />新建分身实例
            </button>
          ) : null}
          <button className="button secondary" onClick={() => void load()} type="button">
            <RefreshCw aria-hidden="true" size={15} />刷新数据库
          </button>
        </div>}
        description={copy.description}
        eyebrow={copy.eyebrow}
        meta={`数据库 · ${studio.stats.published_instance_count}/${studio.stats.instance_count} 个实例已发布`}
        title={copy.title}
      />

      {error ? <InlineCallout description={error} title="最近一次刷新失败" tone="warning" /> : null}
      {!canConfigure ? (
        <InlineCallout
          description="当前身份可以查看岗位与分身配置，但不能创建或发布版本。配置权限不会由分身本身授予。"
          title="只读角色工作室"
          tone="info"
        />
      ) : null}

      <RoleStudioStats studio={studio} />
      {view === "templates" ? (
        <TemplateRegistry
          canConfigure={canConfigure}
          onEdit={(template) => setEditor({ kind: "template", template })}
          onPublish={(target) => setPublishTarget(target)}
          templates={studio.templates}
        />
      ) : null}
      {view === "instances" ? (
        <TwinRegistry
          canConfigure={canConfigure}
          onEdit={(twin) => setEditor({ kind: "twin", twin })}
          onPublish={(target) => setPublishTarget(target)}
          twins={studio.twins}
        />
      ) : null}
      {view === "prompts" ? <ConfigurationLedger studio={studio} /> : null}

      {editor?.kind === "template" ? (
        <TemplateEditorDialog
          execute={mutate}
          onClose={() => setEditor(null)}
          onComplete={() => setEditor(null)}
          template={editor.template}
        />
      ) : null}
      {editor?.kind === "twin" ? (
        <TwinEditorDialog
          execute={mutate}
          onClose={() => setEditor(null)}
          onComplete={() => setEditor(null)}
          studio={studio}
          twin={editor.twin}
        />
      ) : null}
      {publishTarget ? (
        <PublishDialog
          execute={mutate}
          onClose={() => setPublishTarget(null)}
          onComplete={() => setPublishTarget(null)}
          target={publishTarget}
        />
      ) : null}
    </div>
  );
}

function RoleStudioStats({ studio }: { studio: RoleStudioResponse }) {
  const stats = [
    { label: "岗位模板", value: studio.stats.template_count, note: `${studio.stats.published_template_count} 个已发布`, icon: Boxes },
    { label: "分身实例", value: studio.stats.instance_count, note: `${studio.stats.published_instance_count} 个可调用`, icon: Bot },
    { label: "配置草稿", value: studio.stats.draft_version_count, note: "待审核发布", icon: FileClock },
    { label: "累计运行", value: studio.stats.run_count, note: "绑定具体分身版本", icon: Activity }
  ];
  return (
    <section className="role-studio-stat-band" aria-label="角色资产统计">
      {stats.map((item) => {
        const Icon = item.icon;
        return <article key={item.label}><span><Icon aria-hidden="true" size={16} />{item.label}</span><strong>{item.value}</strong><p>{item.note}</p></article>;
      })}
    </section>
  );
}

function TemplateRegistry({ canConfigure, onEdit, onPublish, templates }: {
  canConfigure: boolean;
  onEdit: (template: RoleTemplate) => void;
  onPublish: (target: PublishTarget) => void;
  templates: RoleTemplate[];
}) {
  return (
    <section className="role-template-registry" aria-label="岗位模板目录">
      <header><div><span>ROLE TEMPLATE CATALOG</span><h2>企业岗位模板</h2></div><em>{templates.length} 个稳定岗位资产</em></header>
      <div className="role-template-grid">
        {templates.map((template) => {
          const current = currentTemplateVersion(template);
          return (
            <article className="role-template-card" key={template.key}>
              <header>
                <span><GitBranch aria-hidden="true" size={18} /></span>
                <div><small>{template.key}</small><h3>{template.name}</h3></div>
                <StatusBadge value={{ label: statusLabel(template.status), tone: statusTone(template.status) }} />
              </header>
              <p>{template.description}</p>
              <div className="role-template-current">
                <div><span>当前岗位版本</span><strong>{current ? `v${current.version_number} · ${current.role_title}` : "尚未发布"}</strong></div>
                <div><span>分身实例</span><strong>{template.twin_count}</strong></div>
              </div>
              {current ? (
                <div className="role-boundary-columns">
                  <div><span><CheckCircle2 aria-hidden="true" size={13} />岗位职责</span>{current.responsibilities.map((item) => <p key={item}>{item}</p>)}</div>
                  <div><span><ShieldCheck aria-hidden="true" size={13} />能力边界</span>{current.capability_boundaries.map((item) => <p key={item}>{item}</p>)}</div>
                </div>
              ) : null}
              <VersionRows
                canConfigure={canConfigure}
                currentVersion={template.current_version_number}
                label={template.name}
                onPublish={onPublish}
                targetKey={template.key}
                targetKind="template"
                versions={template.versions}
              />
              {canConfigure ? <footer><button className="button secondary" onClick={() => onEdit(template)} type="button"><Plus aria-hidden="true" size={14} />创建新版本</button></footer> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function TwinRegistry({ canConfigure, onEdit, onPublish, twins }: {
  canConfigure: boolean;
  onEdit: (twin: RoleTwinInstance) => void;
  onPublish: (target: PublishTarget) => void;
  twins: RoleTwinInstance[];
}) {
  return (
    <section className="role-twin-registry" aria-label="角色分身实例目录">
      <header><div><span>ROLE TWIN INSTANCES</span><h2>已绑定负责人分身</h2></div><em>{twins.length} 个实例</em></header>
      <div className="role-twin-instance-grid">
        {twins.map((twin) => {
          const current = currentTwinVersion(twin);
          return (
            <article className="role-twin-instance" key={twin.key}>
              <header>
                <span><Bot aria-hidden="true" size={20} /></span>
                <div><small>{twin.template_name} · {twin.key}</small><h3>{current?.display_name ?? twin.key}</h3></div>
                <StatusBadge value={{ label: statusLabel(twin.status), tone: statusTone(twin.status) }} />
              </header>
              <dl>
                <div><dt>绑定负责人</dt><dd>{twin.owner_name ?? "企业通用分身"}</dd></div>
                <div><dt>当前版本</dt><dd>{twin.current_version_number ? `v${twin.current_version_number}` : "尚未发布"}</dd></div>
                <div><dt>累计运行</dt><dd>{twin.run_count}</dd></div>
                <div><dt>模型</dt><dd>{current?.model ?? "尚未配置"}</dd></div>
              </dl>
              {current ? <div className="role-capability-strip">{current.capabilities.map((item) => <span key={item}>{item}</span>)}</div> : null}
              {current ? <p className="role-twin-policy"><ShieldCheck aria-hidden="true" size={14} />{current.answer_policy}</p> : null}
              <VersionRows
                canConfigure={canConfigure}
                currentVersion={twin.current_version_number}
                label={current?.display_name ?? twin.key}
                onPublish={onPublish}
                targetKey={twin.key}
                targetKind="twin"
                versions={twin.versions}
              />
              {canConfigure ? <footer><button className="button secondary" onClick={() => onEdit(twin)} type="button"><Plus aria-hidden="true" size={14} />创建新版本</button></footer> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function VersionRows({ canConfigure, currentVersion, label, onPublish, targetKey, targetKind, versions }: {
  canConfigure: boolean;
  currentVersion: number | null;
  label: string;
  onPublish: (target: PublishTarget) => void;
  targetKey: string;
  targetKind: "template" | "twin";
  versions: Array<RoleTemplateVersion | RoleTwinVersion>;
}) {
  return (
    <div className="role-version-rows">
      <div className="role-version-heading"><span><History aria-hidden="true" size={13} />版本记录</span><em>历史不可覆盖</em></div>
      {versions.map((version) => (
        <div className="role-version-row" key={version.id}>
          <div><strong>v{version.version_number}</strong><span>{version.change_summary}</span></div>
          <time>{formatTime(version.published_at ?? version.created_at)}</time>
          {version.version_number === currentVersion ? <em>当前</em> : <StatusBadge value={{ label: statusLabel(version.status), tone: statusTone(version.status) }} />}
          {canConfigure && version.status === "draft" ? (
            <button
              aria-label={`发布 ${label} v${version.version_number}`}
              onClick={() => onPublish({ kind: targetKind, key: targetKey, label, versionNumber: version.version_number })}
              title="发布此版本"
              type="button"
            ><Rocket aria-hidden="true" size={14} /></button>
          ) : <span className="role-version-lock"><Database aria-hidden="true" size={13} /></span>}
        </div>
      ))}
    </div>
  );
}

function ConfigurationLedger({ studio }: { studio: RoleStudioResponse }) {
  const rows = useMemo(() => studio.twins.flatMap((twin) => twin.versions.map((version) => ({ twin, version }))), [studio.twins]);
  return (
    <section className="role-config-ledger">
      <header><div><span>CONFIGURATION RELEASE LEDGER</span><h2>分身版本发布台账</h2></div><em>{rows.length} 个不可变版本</em></header>
      <div className="role-config-table-wrap">
        <table>
          <thead><tr><th>分身 / 岗位模板</th><th>版本</th><th>Provider / Model</th><th>能力范围</th><th>变更摘要</th><th>创建 / 发布时间</th><th>状态</th></tr></thead>
          <tbody>{rows.map(({ twin, version }) => (
            <tr key={version.id}>
              <td><strong>{version.display_name}</strong><small>{twin.template_name} · {twin.key}</small></td>
              <td><strong>v{version.version_number}</strong><small>模板 v{version.template_version_number}</small></td>
              <td><strong>{version.provider}</strong><small>{version.model}</small></td>
              <td><div className="role-ledger-capabilities">{version.capabilities.map((item) => <span key={item}>{item}</span>)}</div></td>
              <td>{version.change_summary}</td>
              <td><strong>{formatTime(version.created_at)}</strong><small>{formatTime(version.published_at)}</small></td>
              <td><StatusBadge value={{ label: version.version_number === twin.current_version_number ? "当前发布" : statusLabel(version.status), tone: version.version_number === twin.current_version_number ? "positive" : statusTone(version.status) }} /></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <footer><GitBranch aria-hidden="true" size={14} />AgentRun 保存实际使用的分身版本 ID，历史问答和数字会议可以按版本复现。</footer>
    </section>
  );
}

function TemplateEditorDialog({ execute, onClose, onComplete, template }: {
  execute: MutationExecutor;
  onClose: () => void;
  onComplete: () => void;
  template?: RoleTemplate;
}) {
  const source = template ? currentTemplateVersion(template) : undefined;
  const [templateKey, setTemplateKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [roleTitle, setRoleTitle] = useState(source?.role_title ?? "");
  const [responsibilities, setResponsibilities] = useState(source?.responsibilities.join("\n") ?? "");
  const [boundaries, setBoundaries] = useState(source?.capability_boundaries.join("\n") ?? "");
  const [voiceGuide, setVoiceGuide] = useState(source?.default_voice_guide ?? "");
  const [reasoningGuide, setReasoningGuide] = useState(source?.default_reasoning_guide ?? "");
  const [answerPolicy, setAnswerPolicy] = useState(source?.default_answer_policy ?? "");
  const [summary, setSummary] = useState(template ? "更新岗位职责与能力边界" : "建立岗位模板初始版本");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const versionFields = {
      role_title: roleTitle,
      responsibilities: parseList(responsibilities),
      capability_boundaries: parseList(boundaries),
      default_voice_guide: voiceGuide,
      default_reasoning_guide: reasoningGuide,
      default_answer_policy: answerPolicy,
      change_summary: summary
    };
    try {
      await execute(
        template ? `/api/v1/role-templates/${template.key}/versions` : "/api/v1/role-templates",
        template ? versionFields : { template_key: templateKey, name, description, ...versionFields }
      );
      onComplete();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "岗位模板保存失败");
    } finally {
      setSubmitting(false);
    }
  }

  const formId = "role-template-editor-form";
  return (
    <Drawer
      busy={submitting}
      className="role-studio-dialog"
      eyebrow="ROLE TEMPLATE"
      footer={<>
        <button className="button secondary" disabled={submitting} onClick={onClose} type="button">取消</button>
        <button className="button primary" disabled={submitting} form={formId} type="submit">{submitting ? <LoaderCircle className="spinning" size={15} /> : <GitBranch size={15} />}{template ? "保存新版本" : "创建模板草稿"}</button>
      </>}
      onClose={onClose}
      size="large"
      title={template ? `${template.name} · 创建新版本` : "新建岗位模板"}
    >
        <form className="role-studio-editor-form" id={formId} onSubmit={submit}>
          {!template ? <div className="role-editor-grid"><FormField label="模板稳定键"><input onChange={(event) => setTemplateKey(event.target.value)} pattern="[a-z0-9][a-z0-9._-]+" required value={templateKey} /></FormField><FormField label="模板名称"><input onChange={(event) => setName(event.target.value)} required value={name} /></FormField><FormField className="wide" label="模板说明"><textarea onChange={(event) => setDescription(event.target.value)} required value={description} /></FormField></div> : null}
          <div className="role-editor-grid">
            <FormField label="岗位标题"><input onChange={(event) => setRoleTitle(event.target.value)} required value={roleTitle} /></FormField>
            <FormField label="变更摘要"><input onChange={(event) => setSummary(event.target.value)} required value={summary} /></FormField>
            <FormField label="岗位职责"><textarea onChange={(event) => setResponsibilities(event.target.value)} required value={responsibilities} /></FormField>
            <FormField label="能力边界"><textarea onChange={(event) => setBoundaries(event.target.value)} required value={boundaries} /></FormField>
            <FormField className="wide" label="默认表达方式"><textarea onChange={(event) => setVoiceGuide(event.target.value)} required value={voiceGuide} /></FormField>
            <FormField className="wide" label="默认推理规则"><textarea onChange={(event) => setReasoningGuide(event.target.value)} required value={reasoningGuide} /></FormField>
            <FormField className="wide" label="默认回答边界"><textarea onChange={(event) => setAnswerPolicy(event.target.value)} required value={answerPolicy} /></FormField>
          </div>
          {error ? <InlineCallout description={error} title="无法保存岗位版本" tone="critical" /> : null}
        </form>
    </Drawer>
  );
}

function TwinEditorDialog({ execute, onClose, onComplete, studio, twin }: {
  execute: MutationExecutor;
  onClose: () => void;
  onComplete: () => void;
  studio: RoleStudioResponse;
  twin?: RoleTwinInstance;
}) {
  const publishedTemplates = studio.templates.filter((item) => item.current_version_number !== null);
  const initialTemplateKey = twin?.template_key ?? publishedTemplates[0]?.key ?? "";
  const initialTemplate = studio.templates.find((item) => item.key === initialTemplateKey);
  const templateVersion = initialTemplate ? currentTemplateVersion(initialTemplate) : undefined;
  const source = twin ? currentTwinVersion(twin) : undefined;
  const [twinKey, setTwinKey] = useState("");
  const [templateKey, setTemplateKey] = useState(initialTemplateKey);
  const [ownerKey, setOwnerKey] = useState(twin?.owner_principal_key ?? "");
  const [displayName, setDisplayName] = useState(source?.display_name ?? (initialTemplate ? `${initialTemplate.name}分身` : ""));
  const [voiceGuide, setVoiceGuide] = useState(source?.voice_guide ?? templateVersion?.default_voice_guide ?? "");
  const [reasoningGuide, setReasoningGuide] = useState(source?.reasoning_guide ?? templateVersion?.default_reasoning_guide ?? "");
  const [answerPolicy, setAnswerPolicy] = useState(source?.answer_policy ?? templateVersion?.default_answer_policy ?? "");
  const [provider, setProvider] = useState(source?.provider ?? "openai-compatible-responses");
  const [model, setModel] = useState(source?.model ?? "environment-configured");
  const [capabilities, setCapabilities] = useState(source?.capabilities.join("\n") ?? templateVersion?.responsibilities.join("\n") ?? "");
  const [summary, setSummary] = useState(twin ? "更新分身表达与运行配置" : "建立分身初始配置");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function changeTemplate(nextKey: string) {
    setTemplateKey(nextKey);
    if (twin) return;
    const nextTemplate = studio.templates.find((item) => item.key === nextKey);
    const nextVersion = nextTemplate ? currentTemplateVersion(nextTemplate) : undefined;
    if (!nextTemplate || !nextVersion) return;
    setDisplayName(`${nextTemplate.name}分身`);
    setVoiceGuide(nextVersion.default_voice_guide);
    setReasoningGuide(nextVersion.default_reasoning_guide);
    setAnswerPolicy(nextVersion.default_answer_policy);
    setCapabilities(nextVersion.responsibilities.join("\n"));
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const versionFields = {
      display_name: displayName,
      voice_guide: voiceGuide,
      reasoning_guide: reasoningGuide,
      answer_policy: answerPolicy,
      provider,
      model,
      capabilities: parseList(capabilities),
      change_summary: summary
    };
    try {
      await execute(
        twin ? `/api/v1/role-twins/${twin.key}/versions` : "/api/v1/role-twins",
        twin ? versionFields : { twin_key: twinKey, template_key: templateKey, owner_principal_key: ownerKey || null, ...versionFields }
      );
      onComplete();
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "分身配置保存失败");
    } finally {
      setSubmitting(false);
    }
  }

  const formId = "role-twin-editor-form";
  return (
    <Drawer
      busy={submitting}
      className="role-studio-dialog"
      eyebrow="ROLE TWIN"
      footer={<>
        <button className="button secondary" disabled={submitting} onClick={onClose} type="button">取消</button>
        <button className="button primary" disabled={submitting || (!twin && !templateKey)} form={formId} type="submit">{submitting ? <LoaderCircle className="spinning" size={15} /> : <Sparkles size={15} />}{twin ? "保存新版本" : "创建分身草稿"}</button>
      </>}
      onClose={onClose}
      size="large"
      title={twin ? `${source?.display_name ?? twin.key} · 创建新版本` : "新建分身实例"}
    >
        <form className="role-studio-editor-form" id={formId} onSubmit={submit}>
          {!twin ? <div className="role-editor-grid">
            <FormField label="分身稳定键"><input onChange={(event) => setTwinKey(event.target.value)} pattern="[a-z0-9][a-z0-9._-]+" required value={twinKey} /></FormField>
            <FormField label="岗位模板"><select onChange={(event) => changeTemplate(event.target.value)} required value={templateKey}>{publishedTemplates.map((item) => <option key={item.key} value={item.key}>{item.name} · v{item.current_version_number}</option>)}</select></FormField>
            <FormField label="绑定负责人"><select onChange={(event) => setOwnerKey(event.target.value)} value={ownerKey}><option value="">企业通用分身</option>{studio.owners.map((owner) => <option disabled={owner.status !== "active"} key={owner.key} value={owner.key}>{owner.display_name} · {owner.key}</option>)}</select></FormField>
            <FormField label="分身名称"><input onChange={(event) => setDisplayName(event.target.value)} required value={displayName} /></FormField>
          </div> : <div className="role-editor-target"><Bot aria-hidden="true" size={19} /><div><strong>{source?.display_name}</strong><span>{twin.template_name} · 当前 v{twin.current_version_number}</span></div></div>}
          <div className="role-editor-grid">
            {twin ? <FormField label="分身名称"><input onChange={(event) => setDisplayName(event.target.value)} required value={displayName} /></FormField> : null}
            <FormField label="变更摘要"><input onChange={(event) => setSummary(event.target.value)} required value={summary} /></FormField>
            <FormField label="Provider"><input onChange={(event) => setProvider(event.target.value)} required value={provider} /></FormField>
            <FormField label="模型"><input onChange={(event) => setModel(event.target.value)} required value={model} /></FormField>
            <FormField className="wide" label="能力范围"><textarea onChange={(event) => setCapabilities(event.target.value)} required value={capabilities} /></FormField>
            <FormField className="wide" label="表达方式"><textarea onChange={(event) => setVoiceGuide(event.target.value)} required value={voiceGuide} /></FormField>
            <FormField className="wide" label="推理规则"><textarea onChange={(event) => setReasoningGuide(event.target.value)} required value={reasoningGuide} /></FormField>
            <FormField className="wide" label="回答边界"><textarea onChange={(event) => setAnswerPolicy(event.target.value)} required value={answerPolicy} /></FormField>
          </div>
          {error ? <InlineCallout description={error} title="无法保存分身版本" tone="critical" /> : null}
        </form>
    </Drawer>
  );
}

function PublishDialog({ execute, onClose, onComplete, target }: {
  execute: MutationExecutor;
  onClose: () => void;
  onComplete: () => void;
  target: PublishTarget;
}) {
  const [reason, setReason] = useState(`审核通过并发布 ${target.label} v${target.versionNumber}`);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const prefix = target.kind === "template" ? "role-templates" : "role-twins";
      await execute(`/api/v1/${prefix}/${target.key}/versions/${target.versionNumber}/publish`, { reason });
      onComplete();
    } catch (reasonValue: unknown) {
      setError(reasonValue instanceof Error ? reasonValue.message : "版本发布失败");
    } finally {
      setSubmitting(false);
    }
  }

  return <ConfirmDialog
    busy={submitting}
    confirmDisabled={reason.trim().length < 3}
    confirmLabel="确认发布"
    description={`发布 ${target.label} v${target.versionNumber}？`}
    detail="新运行将读取此版本；既有版本和历史运行记录不会被覆盖。"
    onCancel={onClose}
    onConfirm={() => void submit()}
    title="发布角色配置版本"
    tone="warning"
  >
    <div className="role-publish-target"><Rocket aria-hidden="true" size={20} /><div><strong>{target.kind === "template" ? "岗位模板版本" : "分身配置版本"}</strong><span>{target.key} · v{target.versionNumber}</span></div></div>
    <label className="confirm-input-field"><span>发布原因</span><textarea autoFocus onChange={(event) => setReason(event.target.value)} required value={reason} /></label>
    {error ? <InlineCallout description={error} title="无法发布版本" tone="critical" /> : null}
  </ConfirmDialog>;
}

function FormField({ children, className = "", label }: { children: React.ReactNode; className?: string; label: string }) {
  return <label className={className}><span>{label}</span>{children}</label>;
}

function RoleStudioState({ icon, retry, title }: { icon: React.ReactNode; retry?: () => void; title: string }) {
  return <div className="role-studio-state">{icon}<strong>{title}</strong>{retry ? <button className="button secondary" onClick={retry} type="button"><RefreshCw size={14} />重新连接</button> : null}</div>;
}
