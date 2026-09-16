"use client";

import {
  Building2,
  CircleAlert,
  Fingerprint,
  KeyRound,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  UserRoundCheck,
  UsersRound,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ConfirmDialog, Dialog, Drawer, useNotifications } from "@/components/console/interaction";
import { FieldError, InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { GroupGovernancePanel } from "@/components/identity/group-governance-panel";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type {
  IdentityAdminOverview,
  IdentityScopeType,
  IdentityUserAccount,
  IdentityUserConfigurationRequest,
  IdentityUserMutationResponse
} from "@/lib/identity-types";

export type IdentityAdminView = "users" | "org" | "access";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const VIEW_COPY: Record<IdentityAdminView, [string, string]> = {
  users: ["人员与权限", "企业用户账号"],
  org: ["人员与权限", "组织与岗位"],
  access: ["人员与权限", "访问角色与权限"]
};

const EXPERIENCE_ROLES = [
  ["employee", "员工"],
  ["manager", "部门经理"],
  ["finance", "财务负责人"],
  ["service", "客服人员"],
  ["ceo", "企业负责人"],
  ["admin", "平台管理员"]
] as const;

const SCOPE_TYPES: Array<[IdentityScopeType, string]> = [
  ["enterprise", "企业"],
  ["org_subtree", "组织子树"],
  ["business_unit", "业务单元"],
  ["store", "门店"],
  ["knowledge_space", "知识空间"],
  ["object", "指定对象"],
  ["self", "本人"]
];

const SCOPE_LABELS = Object.fromEntries(SCOPE_TYPES) as Record<string, string>;

function formatScopeLabel(value: string): string {
  const separator = value.indexOf(":");
  if (separator < 0) return value;
  const type = value.slice(0, separator).trim();
  const ids = value.slice(separator + 1).trim();
  return `${SCOPE_LABELS[type] ?? type}：${ids}`;
}

function authenticationLabel(value: string): string {
  if (value === "local-password") return "本地密码";
  if (value === "development-session") return "开发会话";
  if (value === "sso") return "企业 SSO";
  return value;
}

const FIELD_LABELS: Record<string, string> = {
  account: "账号",
  membership: "任职",
  role_assignments: "访问角色",
  scopes: "数据范围",
  status: "账号状态",
  name: "名称",
  unit_type: "类型",
  parent_org_unit_id: "上级组织",
  position_level: "岗位层级",
  description: "描述",
  permissions: "权限集合",
  display_name: "显示名称",
  email: "邮箱",
  experience_role_key: "体验角色",
  org_key: "组织",
  position_key: "岗位"
};

interface EditableScope {
  scope_type: IdentityScopeType;
  scope_ids_text: string;
  effect: "allow" | "deny";
}

interface EditableAssignment {
  role_key: string;
  scopes: EditableScope[];
}

interface UserEditorForm {
  mode: "create" | "edit";
  account_key: string | null;
  expected_version: number | null;
  client_request_key: string;
  login_name: string;
  initial_password: string;
  display_name: string;
  email: string;
  experience_role_key: string;
  org_key: string;
  position_key: string;
  status: "active" | "suspended";
  assignments: EditableAssignment[];
  reason: string;
}

type UserEditorField = "display_name" | "login_name" | "initial_password" | "email" | "position_key" | "reason" | "assignments";

function validateUserEditor(form: UserEditorForm): Partial<Record<UserEditorField, string>> {
  const errors: Partial<Record<UserEditorField, string>> = {};
  if (!form.display_name.trim()) errors.display_name = "请输入显示名称";
  if (!form.login_name.trim()) errors.login_name = "请输入登录名";
  else if (!/^[a-z0-9][a-z0-9._-]*$/.test(form.login_name)) errors.login_name = "仅支持小写字母、数字、点、横线和下划线";
  if (form.mode === "create" && form.initial_password.length < 12) errors.initial_password = "初始密码至少 12 位";
  if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) errors.email = "请输入有效邮箱";
  if (!form.position_key) errors.position_key = "请选择岗位";
  if (form.reason.trim().length < 3) errors.reason = "变更原因至少 3 个字符";
  if (!form.assignments.length) errors.assignments = "至少选择一个访问角色";
  else if (form.assignments.some((assignment) => !assignment.scopes.length || assignment.scopes.some((scope) => !scope.scope_ids_text.split(",").some((value) => value.trim())))) {
    errors.assignments = "每个访问角色至少需要一个有效数据范围";
  }
  return errors;
}

interface OrgEditorForm {
  mode: "create" | "edit";
  org_key: string;
  version: number | null;
  name: string;
  unit_type: string;
  parent_org_key: string;
  status: "active" | "suspended";
  reason: string;
  client_request_key: string;
}

interface PositionEditorForm {
  mode: "create" | "edit";
  position_key: string;
  version: number | null;
  name: string;
  position_level: string;
  org_key: string;
  status: "active" | "suspended";
  reason: string;
  client_request_key: string;
}

interface RoleEditorForm {
  mode: "create" | "edit";
  role_key: string;
  revision: number | null;
  name: string;
  description: string;
  status: "active" | "suspended";
  permissions: string[];
  reason: string;
  client_request_key: string;
}

export function IdentityAdminPage({ view }: { view: IdentityAdminView }) {
  const { can, identity, identityLoading, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<IdentityAdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<UserEditorForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmUserSave, setConfirmUserSave] = useState(false);
  const canManage = can("identity.user.manage") && can("identity.access.manage");

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/identity/admin/overview`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取身份权限数据库"));
    setData((await response.json()) as IdentityAdminOverview);
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "身份权限服务连接失败"))
      .finally(() => setLoading(false));
  }, [load]);

  useEffect(() => {
    if (view !== "users") setEditor(null);
  }, [view]);

  async function submitConfiguration(form: UserEditorForm): Promise<void> {
    if (!data || !canManage) return;
    setSaving(true);
    setError(null);
    try {
      const assignments = form.assignments.map((assignment) => ({
        role_key: assignment.role_key,
        scopes: assignment.scopes.map((scope) => ({
          scope_type: scope.scope_type,
          scope_ids: scope.scope_ids_text.split(",").map((value) => value.trim()).filter(Boolean),
          effect: scope.effect
        }))
      }));
      if (!assignments.length || assignments.some((assignment) => !assignment.scopes.length || assignment.scopes.some((scope) => !scope.scope_ids.length))) {
        throw new Error("每个访问角色至少需要一个有效的数据范围");
      }
      const payload: IdentityUserConfigurationRequest = {
        schema_version: 1,
        client_request_key: form.client_request_key,
        display_name: form.display_name.trim(),
        email: form.email.trim() || null,
        ...(form.mode === "create" && form.initial_password.trim()
          ? { initial_password: form.initial_password }
          : {}),
        experience_role_key: form.experience_role_key,
        org_key: form.org_key,
        position_key: form.position_key,
        status: form.status,
        role_assignments: assignments,
        reason: form.reason.trim()
      };
      if (form.mode === "create") payload.login_name = form.login_name.trim().toLowerCase();
      else payload.expected_version = form.expected_version ?? 1;
      const endpoint = form.mode === "create"
        ? `${API_BASE_URL}/api/v1/identity/admin/users`
        : `${API_BASE_URL}/api/v1/identity/admin/users/${encodeURIComponent(form.account_key ?? "")}/configuration`;
      const response = await apiFetch(endpoint, {
        method: form.mode === "create" ? "POST" : "PUT",
        headers: {
          "Content-Type": "application/json",
          "X-Zhixing-Demo-Actor": roleId
        },
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "身份配置保存失败"));
      const result = (await response.json()) as IdentityUserMutationResponse;
      notify({ title: `${result.account.display_name} 已${result.operation === "created" ? "创建" : "更新"}`, description: `账号版本 v${result.account.version}`, tone: "success" });
      setConfirmUserSave(false);
      setEditor(null);
      await load();
    } catch (reason: unknown) {
      notify({ title: "身份配置保存失败", description: reason instanceof Error ? reason.message : "请检查输入后重试", tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  function requestUserSave(form: UserEditorForm): void {
    const current = form.mode === "edit" ? data?.users.find((item) => item.account_key === form.account_key) : null;
    if (current?.status !== "suspended" && form.status === "suspended") {
      setConfirmUserSave(true);
      return;
    }
    void submitConfiguration(form);
  }

  if (loading) return <IdentityState title="正在解析账号、组织与访问策略" />;
  if (!data) return <IdentityState error title={error ?? "身份权限数据暂不可用"} />;
  const copy = VIEW_COPY[view];
  return <div className="identity-admin-page">
    <PageHeader
      actions={<div className="identity-header-actions">
        <button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新权限视图</button>
        {view === "users" ? <button className="button primary" disabled={identityLoading || !canManage} onClick={() => setEditor(createEditor(data))} type="button"><Plus size={16} />新增账号</button> : null}
      </div>}
      eyebrow={copy[0]}
      meta={data.enterprise_name}
      title={copy[1]}
    />
    {error ? <InlineCallout description={error} title="身份管理操作未完成" tone="critical" /> : null}
    {!canManage && view === "users" ? <InlineCallout description="当前身份可以查看账号目录，但不能创建或修改人员、任职和访问范围。" title="管理权限受限" tone="info" /> : null}
    <IdentityStats data={data} />
    {view === "users" && editor ? <UserConfigurationEditor
      currentAccountId={identity?.actor.account_id ?? null}
      data={data}
      form={editor}
      onCancel={() => setEditor(null)}
      onChange={setEditor}
      onSubmit={() => requestUserSave(editor)}
      saving={saving}
    /> : null}
    {confirmUserSave && editor ? <ConfirmDialog busy={saving} confirmLabel="停用并保存" description={`确认停用 ${editor.display_name}？`} detail="账号现有会话和后续企业访问将被拒绝，历史审计记录继续保留。" onCancel={() => setConfirmUserSave(false)} onConfirm={() => void submitConfiguration(editor)} title="停用企业账号" tone="danger" /> : null}
    {view === "users" ? <UserDirectory
      canManage={canManage}
      currentAccountId={identity?.actor.account_id ?? null}
      data={data}
      onEdit={(user) => setEditor(editUser(user))}
    /> : null}
    {view === "org" ? <><GroupGovernancePanel /><OrganizationWorkspace canManage={can("identity.user.manage")} data={data} onReload={load} roleId={roleId} /></> : null}
    {view === "access" ? <AccessWorkspace canManage={can("identity.access.manage")} data={data} onReload={load} roleId={roleId} /> : null}
  </div>;
}

function IdentityStats({ data }: { data: IdentityAdminOverview }) {
  const items = [
    ["有效账号", data.stats.active_users, <UserRoundCheck key="users" size={16} />],
    ["组织 / 岗位", `${data.stats.org_units} / ${data.stats.positions}`, <Building2 key="org" size={16} />],
    ["访问角色", data.stats.access_roles, <KeyRound key="roles" size={16} />],
    ["权限目录", data.stats.permissions, <ShieldCheck key="permissions" size={16} />],
    ["管理变更", data.stats.management_events, <UsersRound key="management" size={16} />],
    ["授权决策", data.stats.authorization_decisions, <Fingerprint key="decisions" size={16} />],
    ["拒绝记录", data.stats.denied_decisions, <CircleAlert key="denied" size={16} />]
  ];
  return <section className="identity-stat-band" aria-label="身份权限统计">
    {items.map(([label, value, icon]) => <article key={String(label)}><span>{icon}{label}</span><strong>{value}</strong></article>)}
  </section>;
}

function UserConfigurationEditor({ currentAccountId, data, form, onCancel, onChange, onSubmit, saving }: {
  currentAccountId: string | null;
  data: IdentityAdminOverview;
  form: UserEditorForm;
  onCancel: () => void;
  onChange: (form: UserEditorForm) => void;
  onSubmit: () => void;
  saving: boolean;
}) {
  const [showErrors, setShowErrors] = useState(false);
  const editorRef = useRef<HTMLElement>(null);
  const positions = data.positions.filter((position) => position.org_key === form.org_key && position.status === "active");
  const isSelf = form.mode === "edit" && data.users.find((user) => user.account_key === form.account_key)?.account_id === currentAccountId;
  const errors = validateUserEditor(form);

  function fieldError(field: UserEditorField): string | undefined {
    return showErrors ? errors[field] : undefined;
  }

  function requestSubmit(): void {
    setShowErrors(true);
    if (Object.keys(errors).length) {
      window.requestAnimationFrame(() => editorRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
      return;
    }
    onSubmit();
  }

  function patch(values: Partial<UserEditorForm>): void {
    onChange({ ...form, ...values });
  }

  function toggleRole(roleKey: string): void {
    if (isSelf) return;
    const exists = form.assignments.some((assignment) => assignment.role_key === roleKey);
    patch({ assignments: exists ? form.assignments.filter((assignment) => assignment.role_key !== roleKey) : [...form.assignments, { role_key: roleKey, scopes: [defaultScope(roleKey, form, data)] }] });
  }

  function updateScope(roleKey: string, index: number, values: Partial<EditableScope>): void {
    patch({ assignments: form.assignments.map((assignment) => assignment.role_key === roleKey ? { ...assignment, scopes: assignment.scopes.map((scope, scopeIndex) => scopeIndex === index ? { ...scope, ...values } : scope) } : assignment) });
  }

  function addScope(roleKey: string): void {
    patch({ assignments: form.assignments.map((assignment) => assignment.role_key === roleKey ? { ...assignment, scopes: [...assignment.scopes, { scope_type: "store", scope_ids_text: "store-flagship", effect: "allow" }] } : assignment) });
  }

  function removeScope(roleKey: string, index: number): void {
    patch({ assignments: form.assignments.map((assignment) => assignment.role_key === roleKey ? { ...assignment, scopes: assignment.scopes.filter((_, scopeIndex) => scopeIndex !== index) } : assignment) });
  }

  return <Drawer
    busy={saving}
    className="identity-user-drawer"
    eyebrow={form.mode === "create" ? "NEW ACCOUNT PACKAGE" : `CONFIGURATION · v${form.expected_version}`}
    footer={<><div className="interaction-boundary"><ShieldCheck size={15} /><span>{form.assignments.length} 个角色 · {form.assignments.reduce((total, assignment) => total + assignment.scopes.length, 0)} 个范围</span></div><button className="button secondary" disabled={saving} onClick={onCancel} type="button">取消</button><button className="button primary" disabled={saving} onClick={requestSubmit} type="button">{saving ? <LoaderCircle className="spinning" size={16} /> : <Save size={16} />}{saving ? "正在保存" : "保存配置"}</button></>}
    onClose={onCancel}
    size="large"
    title={form.mode === "create" ? "创建人员账号" : `编辑 ${form.display_name}`}
  >
    <section className="identity-user-editor overlay-embedded" ref={editorRef}>
    {isSelf ? <div className="identity-editor-guard"><ShieldAlert size={16} /><span>当前账号的状态、访问角色和数据范围受防自锁保护。</span></div> : null}
    <div className="identity-form-grid">
      <label><span>显示名称</span><input aria-describedby="user-display-name-error" aria-invalid={Boolean(fieldError("display_name"))} maxLength={160} onChange={(event) => patch({ display_name: event.target.value })} value={form.display_name} /><FieldError id="user-display-name-error" message={fieldError("display_name")} /></label>
      <label><span>登录名</span><input aria-describedby="user-login-name-error" aria-invalid={Boolean(fieldError("login_name"))} disabled={form.mode === "edit"} maxLength={120} onChange={(event) => patch({ login_name: event.target.value.toLowerCase() })} pattern="[a-z0-9][a-z0-9._-]*" value={form.login_name} /><FieldError id="user-login-name-error" message={fieldError("login_name")} /></label>
      {form.mode === "create" ? <label><span>初始密码</span><input aria-describedby="user-initial-password-error" aria-invalid={Boolean(fieldError("initial_password"))} autoComplete="new-password" minLength={12} maxLength={256} onChange={(event) => patch({ initial_password: event.target.value })} placeholder="至少 12 位" type="password" value={form.initial_password} /><FieldError id="user-initial-password-error" message={fieldError("initial_password")} /></label> : null}
      <label><span>邮箱</span><input aria-describedby="user-email-error" aria-invalid={Boolean(fieldError("email"))} maxLength={240} onChange={(event) => patch({ email: event.target.value })} type="email" value={form.email} /><FieldError id="user-email-error" message={fieldError("email")} /></label>
      <label><span>体验角色</span><select onChange={(event) => patch({ experience_role_key: event.target.value })} value={form.experience_role_key}>{EXPERIENCE_ROLES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label><span>组织</span><select onChange={(event) => {
        const nextOrg = event.target.value;
        const nextPosition = data.positions.find((position) => position.org_key === nextOrg && position.status === "active");
        patch({ org_key: nextOrg, position_key: nextPosition?.position_key ?? "" });
      }} value={form.org_key}>{data.org_units.filter((org) => org.status === "active").map((org) => <option key={org.org_key} value={org.org_key}>{org.name}</option>)}</select></label>
      <label><span>岗位</span><select aria-describedby="user-position-error" aria-invalid={Boolean(fieldError("position_key"))} onChange={(event) => patch({ position_key: event.target.value })} value={form.position_key}>{positions.map((position) => <option key={position.position_key} value={position.position_key}>{position.name}</option>)}</select><FieldError id="user-position-error" message={fieldError("position_key")} /></label>
      <fieldset className="identity-status-control"><legend>账号状态</legend><div><button className={form.status === "active" ? "active" : ""} disabled={isSelf} onClick={() => patch({ status: "active" })} type="button">有效</button><button className={form.status === "suspended" ? "active warning" : ""} disabled={isSelf} onClick={() => patch({ status: "suspended" })} type="button">停用</button></div></fieldset>
      <label className="identity-reason-field"><span>变更原因</span><input aria-describedby="user-reason-error" aria-invalid={Boolean(fieldError("reason"))} maxLength={500} onChange={(event) => patch({ reason: event.target.value })} placeholder="入职、调岗或权限调整" value={form.reason} /><FieldError id="user-reason-error" message={fieldError("reason")} /></label>
    </div>
    <div className="identity-access-editor">
      <div className="identity-access-editor-title"><div><span>ACCESS PACKAGE</span><h3>访问角色与数据范围</h3></div><em>岗位不会自动获得权限</em></div>
      <div aria-describedby="user-assignments-error" aria-invalid={Boolean(fieldError("assignments"))} className="identity-role-picker" tabIndex={fieldError("assignments") ? -1 : undefined}>{data.access_roles.filter((role) => role.status === "active").map((role) => {
        const checked = form.assignments.some((assignment) => assignment.role_key === role.role_key);
        return <label className={checked ? "selected" : ""} key={role.role_key}><input checked={checked} disabled={isSelf} onChange={() => toggleRole(role.role_key)} type="checkbox" /><span><strong>{role.name}</strong><small>{role.permission_count} 项权限</small></span></label>;
      })}</div>
      <FieldError id="user-assignments-error" message={fieldError("assignments")} />
      <div className="identity-assignment-list">{form.assignments.map((assignment) => {
        const role = data.access_roles.find((item) => item.role_key === assignment.role_key);
        return <section key={assignment.role_key}><header><div><strong>{role?.name ?? assignment.role_key}</strong><small>{assignment.role_key}</small></div><StatusBadge value={{ label: `${assignment.scopes.length} 个范围`, tone: "neutral" }} /></header>
          <div className="identity-scope-editor">{assignment.scopes.map((scope, index) => <div className="identity-scope-row" key={`${assignment.role_key}-${index}`}>
            <select aria-label="范围类型" disabled={isSelf} onChange={(event) => updateScope(assignment.role_key, index, { scope_type: event.target.value as IdentityScopeType })} value={scope.scope_type}>{SCOPE_TYPES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
            <input aria-label="范围标识" disabled={isSelf} onChange={(event) => updateScope(assignment.role_key, index, { scope_ids_text: event.target.value })} placeholder="多个标识使用逗号分隔" value={scope.scope_ids_text} />
            <select aria-label="授权效果" disabled={isSelf} onChange={(event) => updateScope(assignment.role_key, index, { effect: event.target.value as "allow" | "deny" })} value={scope.effect}><option value="allow">允许</option><option value="deny">拒绝</option></select>
            <button aria-label="删除范围" className="identity-icon-button" disabled={isSelf || assignment.scopes.length === 1} onClick={() => removeScope(assignment.role_key, index)} title="删除范围" type="button"><Trash2 size={15} /></button>
          </div>)}</div>
          <footer><button className="button secondary" disabled={isSelf} onClick={() => addScope(assignment.role_key)} type="button"><Plus size={14} />添加范围</button></footer>
        </section>;
      })}</div>
    </div>
    </section>
  </Drawer>;
}

function UserDirectory({ canManage, currentAccountId, data, onEdit }: { canManage: boolean; currentAccountId: string | null; data: IdentityAdminOverview; onEdit: (user: IdentityUserAccount) => void }) {
  return <section className="identity-data-panel">
    <header><div><span>ACCOUNT / PRINCIPAL / MEMBERSHIP</span><h2>账号与任职目录</h2></div><em>{data.users.length} 个数据库账号</em></header>
    <div className="identity-table-wrap"><table><thead><tr><th>账号与主体</th><th>组织 / 岗位</th><th>访问角色</th><th>数据范围</th><th>认证来源</th><th>状态</th><th>操作</th></tr></thead><tbody>
      {data.users.map((user) => <tr key={user.account_key}>
        <td><strong>{user.display_name}</strong><small>{user.login_name} · {user.account_key} · v{user.version}</small></td>
        <td><strong>{user.organization}</strong><small>{user.position}</small></td>
        <td><div className="identity-tags">{user.access_roles.map((role) => <span key={role}>{role}</span>)}</div></td>
        <td><div className="identity-scope-list">{user.scope_labels.map((scope) => <span key={scope}>{formatScopeLabel(scope)}</span>)}</div></td>
        <td><strong>{authenticationLabel(user.authentication_source)}</strong><small>{user.email ?? "未设置邮箱"}</small></td>
        <td><StatusBadge value={{ label: user.status === "active" ? "有效" : "已停用", tone: user.status === "active" ? "positive" : "warning" }} /></td>
        <td><button aria-label={`编辑 ${user.display_name}`} className="identity-icon-button" disabled={!canManage} onClick={() => onEdit(user)} title={user.account_id === currentAccountId ? "编辑当前账号（状态和权限受保护）" : "编辑账号"} type="button"><Pencil size={15} /></button></td>
      </tr>)}
    </tbody></table></div>
  </section>;
}

function OrganizationWorkspace({ data, canManage, onReload, roleId }: { data: IdentityAdminOverview; canManage: boolean; onReload: () => Promise<void>; roleId: string }) {
  const { notify } = useNotifications();
  const [editor, setEditor] = useState<OrgEditorForm | PositionEditorForm | null>(null);
  const [saving, setSaving] = useState(false);

  async function saveEditor(): Promise<void> {
    if (!editor || !canManage) return;
    setSaving(true);
    try {
      const isOrg = "unit_type" in editor && "parent_org_key" in editor;
      const endpoint = isOrg
        ? editor.mode === "create" ? `${API_BASE_URL}/api/v1/identity/admin/org-units` : `${API_BASE_URL}/api/v1/identity/admin/org-units/${encodeURIComponent(editor.org_key)}`
        : editor.mode === "create" ? `${API_BASE_URL}/api/v1/identity/admin/positions` : `${API_BASE_URL}/api/v1/identity/admin/positions/${encodeURIComponent(editor.position_key)}`;
      const body = isOrg
        ? editor.mode === "create"
          ? { schema_version: 1, client_request_key: editor.client_request_key, org_key: editor.org_key.trim(), name: editor.name.trim(), unit_type: editor.unit_type.trim(), parent_org_key: editor.parent_org_key || null, reason: editor.reason.trim() }
          : { schema_version: 1, client_request_key: editor.client_request_key, expected_version: editor.version ?? 1, name: editor.name.trim(), unit_type: editor.unit_type.trim(), parent_org_key: editor.parent_org_key || null, status: editor.status, reason: editor.reason.trim() }
        : editor.mode === "create"
          ? { schema_version: 1, client_request_key: editor.client_request_key, position_key: editor.position_key.trim(), name: editor.name.trim(), position_level: editor.position_level.trim(), org_key: editor.org_key, reason: editor.reason.trim() }
          : { schema_version: 1, client_request_key: editor.client_request_key, expected_version: editor.version ?? 1, name: editor.name.trim(), position_level: editor.position_level.trim(), org_key: editor.org_key, status: editor.status, reason: editor.reason.trim() };
      const response = await apiFetch(endpoint, { method: editor.mode === "create" ? "POST" : "PUT", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "身份目录保存失败"));
      const result = (await response.json()) as { target_key: string; operation: string };
      notify({ title: `${result.target_key} 已${result.operation === "created" ? "创建" : "更新"}`, tone: "success" }); setEditor(null); await onReload();
    } catch (reason: unknown) { notify({ title: "身份目录保存失败", description: reason instanceof Error ? reason.message : "请检查输入后重试", tone: "error" }); }
    finally { setSaving(false); }
  }

  return <div className="identity-catalog-workspace">
    {editor ? <CatalogEditor editor={editor} data={data} onCancel={() => setEditor(null)} onChange={setEditor} onSubmit={() => void saveEditor()} saving={saving} /> : null}
    <div className="identity-org-layout">
      <section className="identity-data-panel org-unit-panel"><header><div><span>ORG UNIT TREE</span><h2>组织单元</h2></div><div className="identity-panel-actions"><em>{data.org_units.length} 个节点</em>{canManage ? <button className="button secondary compact" onClick={() => setEditor(createOrgEditor(data))} type="button"><Plus size={14} />新增组织</button> : null}</div></header>
        <div className="org-unit-list">{data.org_units.map((org) => <article key={org.org_key}><span><Building2 size={17} /></span><div><strong>{org.name}</strong><small>{org.parent_name ? `${org.parent_name} / ` : ""}{org.org_key} · v{org.version}</small></div><div><b>{org.position_count}</b><small>岗位</small></div><div><b>{org.member_count}</b><small>任职</small></div>{canManage ? <button aria-label={`编辑 ${org.name}`} className="identity-icon-button" onClick={() => setEditor(editOrgEditor(org, data))} title="编辑组织" type="button"><Pencil size={14} /></button> : null}</article>)}</div>
      </section>
      <section className="identity-data-panel"><header><div><span>POSITION CATALOG</span><h2>岗位目录</h2></div><div className="identity-panel-actions"><em>岗位不等于访问角色</em>{canManage ? <button className="button secondary compact" onClick={() => setEditor(createPositionEditor(data))} type="button"><Plus size={14} />新增岗位</button> : null}</div></header>
        <div className="position-list">{data.positions.map((position) => <article key={position.position_key}><div><strong>{position.name}</strong><small>{position.organization} · {position.position_key} · v{position.version}</small></div><span>{position.position_level}</span><b>{position.member_count} 人</b>{canManage ? <button aria-label={`编辑 ${position.name}`} className="identity-icon-button" onClick={() => setEditor(editPositionEditor(position, data))} title="编辑岗位" type="button"><Pencil size={14} /></button> : null}</article>)}</div>
      </section>
    </div>
  </div>;
}

function AccessWorkspace({ data, canManage, onReload, roleId }: { data: IdentityAdminOverview; canManage: boolean; onReload: () => Promise<void>; roleId: string }) {
  const { notify } = useNotifications();
  const [selectedKey, setSelectedKey] = useState(data.access_roles[0]?.role_key ?? "");
  const [editor, setEditor] = useState<RoleEditorForm | null>(null);
  const [saving, setSaving] = useState(false);
  const selected = useMemo(() => data.access_roles.find((role) => role.role_key === selectedKey) ?? data.access_roles[0], [data.access_roles, selectedKey]);
  if (!selected) return null;
  async function saveRole(): Promise<void> {
    if (!editor || !canManage) return;
    setSaving(true);
    try {
      const endpoint = editor.mode === "create" ? `${API_BASE_URL}/api/v1/identity/admin/access-roles` : `${API_BASE_URL}/api/v1/identity/admin/access-roles/${encodeURIComponent(editor.role_key)}`;
      const body = editor.mode === "create"
        ? { schema_version: 1, client_request_key: editor.client_request_key, role_key: editor.role_key.trim(), name: editor.name.trim(), description: editor.description.trim(), permissions: editor.permissions, reason: editor.reason.trim() }
        : { schema_version: 1, client_request_key: editor.client_request_key, expected_revision: editor.revision ?? 1, name: editor.name.trim(), description: editor.description.trim(), status: editor.status, permissions: editor.permissions, reason: editor.reason.trim() };
      const response = await apiFetch(endpoint, { method: editor.mode === "create" ? "POST" : "PUT", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "访问角色保存失败"));
      notify({ title: `${editor.name} 已${editor.mode === "create" ? "创建" : "更新"}`, tone: "success" }); setSelectedKey(editor.role_key); setEditor(null); await onReload();
    } catch (reason: unknown) { notify({ title: "访问角色保存失败", description: reason instanceof Error ? reason.message : "请检查输入后重试", tone: "error" }); }
    finally { setSaving(false); }
  }
  return <div className="identity-access-workspace">
    {editor ? <RoleEditor editor={editor} data={data} onCancel={() => setEditor(null)} onChange={setEditor} onSubmit={() => void saveRole()} saving={saving} /> : null}
    <div className="identity-access-layout">
      <section className="access-role-list"><header><div><span>ACCESS ROLE VERSIONS</span><h2>角色版本</h2></div>{canManage ? <button className="button secondary compact" onClick={() => setEditor(createRoleEditor(data))} type="button"><Plus size={14} />新增角色</button> : null}</header>{data.access_roles.map((role) => <button className={role.role_key === selected.role_key ? "active" : ""} key={role.role_key} onClick={() => setSelectedKey(role.role_key)} type="button"><div><strong>{role.name}</strong><small>{role.role_key} · v{role.version} · r{role.revision}</small></div><span>{role.permission_count} 权限</span></button>)}</section>
      <section className="access-role-detail"><header><div><span>POLICY SET · {selected.role_key}</span><h2>{selected.name}</h2><p>{selected.description}</p></div><div className="identity-panel-actions"><StatusBadge value={{ label: selected.status === "active" ? "生效中" : selected.status, tone: selected.status === "active" ? "positive" : "critical" }} />{canManage ? <button aria-label={`编辑 ${selected.name}`} className="identity-icon-button" onClick={() => setEditor(editRoleEditor(selected))} title="编辑访问角色" type="button"><Pencil size={15} /></button> : null}</div></header>
        <div className="access-role-summary"><div><span>版本</span><strong>{selected.version} / r{selected.revision}</strong></div><div><span>授权主体</span><strong>{selected.assignment_count}</strong></div><div><span>权限数量</span><strong>{selected.permission_count}</strong></div><div><span>范围类型</span><strong>{selected.scope_types.length}</strong></div></div>
        <div className="access-role-section"><span>权限集合</span><div className="permission-key-grid">{selected.permissions.map((permission) => <code key={permission}>{permission}</code>)}</div></div>
        <div className="access-role-section"><span>当前分配范围类型</span><div className="identity-tags">{selected.scope_types.map((scope) => <span key={scope}>{scope}</span>)}</div></div>
      </section>
    </div>
  </div>;
}

function CatalogEditor({ editor, data, onCancel, onChange, onSubmit, saving }: { editor: OrgEditorForm | PositionEditorForm; data: IdentityAdminOverview; onCancel: () => void; onChange: (editor: OrgEditorForm | PositionEditorForm) => void; onSubmit: () => void; saving: boolean }) {
  const isOrg = "unit_type" in editor;
  const patch = (values: Partial<OrgEditorForm> | Partial<PositionEditorForm>) => onChange({ ...editor, ...values } as OrgEditorForm | PositionEditorForm);
  return <Dialog busy={saving} className="identity-catalog-dialog" eyebrow={isOrg ? "ORG UNIT CATALOG" : "POSITION CATALOG"} footer={<><small>{editor.mode === "edit" ? `当前版本 v${editor.version}` : "创建后进入身份目录审计"}</small><button className="button secondary" disabled={saving} onClick={onCancel} type="button">取消</button><button className="button primary" disabled={saving || editor.reason.trim().length < 3 || !editor.name.trim()} onClick={onSubmit} type="button"><Save size={15} />{saving ? "保存中" : "保存目录"}</button></>} onClose={onCancel} size="medium" title={isOrg ? editor.mode === "create" ? "新增组织单元" : `编辑组织 · ${editor.org_key}` : editor.mode === "create" ? "新增岗位" : `编辑岗位 · ${editor.position_key}`}>
    <section className="identity-catalog-editor overlay-embedded">
    <div className="identity-form-grid">
      <label><span>{isOrg ? "组织标识" : "岗位标识"}</span><input disabled={editor.mode === "edit"} onChange={(event) => patch(isOrg ? { org_key: event.target.value.toLowerCase() } : { position_key: event.target.value.toLowerCase() })} value={isOrg ? editor.org_key : editor.position_key} /></label>
      <label><span>名称</span><input onChange={(event) => patch({ name: event.target.value })} value={editor.name} /></label>
      <label><span>{isOrg ? "组织类型" : "岗位层级"}</span><input onChange={(event) => patch(isOrg ? { unit_type: event.target.value } : { position_level: event.target.value })} value={isOrg ? editor.unit_type : editor.position_level} /></label>
      {isOrg ? <label><span>上级组织</span><select onChange={(event) => patch({ parent_org_key: event.target.value })} value={editor.parent_org_key}><option value="">无上级</option>{data.org_units.filter((org) => org.org_key !== editor.org_key && org.status === "active").map((org) => <option key={org.org_key} value={org.org_key}>{org.name} · {org.org_key}</option>)}</select></label> : <label><span>所属组织</span><select onChange={(event) => patch({ org_key: event.target.value })} value={editor.org_key}>{data.org_units.filter((org) => org.status === "active").map((org) => <option key={org.org_key} value={org.org_key}>{org.name}</option>)}</select></label>}
      {editor.mode === "edit" ? <fieldset className="identity-status-control"><legend>状态</legend><div><button className={editor.status === "active" ? "active" : ""} onClick={() => patch({ status: "active" })} type="button">生效</button><button className={editor.status === "suspended" ? "active warning" : ""} onClick={() => patch({ status: "suspended" })} type="button">停用</button></div></fieldset> : null}
      <label className="identity-reason-field"><span>变更原因</span><input maxLength={500} onChange={(event) => patch({ reason: event.target.value })} placeholder="记录组织或岗位变更原因" value={editor.reason} /></label>
    </div>
    </section>
  </Dialog>;
}

function RoleEditor({ editor, data, onCancel, onChange, onSubmit, saving }: { editor: RoleEditorForm; data: IdentityAdminOverview; onCancel: () => void; onChange: (editor: RoleEditorForm) => void; onSubmit: () => void; saving: boolean }) {
  const grouped = data.permission_catalog.reduce<Record<string, typeof data.permission_catalog>>((groups, permission) => { (groups[permission.resource] ??= []).push(permission); return groups; }, {});
  function togglePermission(key: string): void { onChange({ ...editor, permissions: editor.permissions.includes(key) ? editor.permissions.filter((item) => item !== key) : [...editor.permissions, key] }); }
  return <Drawer busy={saving} className="identity-role-drawer" eyebrow="ACCESS ROLE POLICY" footer={<><small>{editor.mode === "edit" ? `当前修订 r${editor.revision}` : "创建后进入身份目录审计"}</small><button className="button secondary" disabled={saving} onClick={onCancel} type="button">取消</button><button className="button primary" disabled={saving || !editor.permissions.length || editor.reason.trim().length < 3 || !editor.name.trim()} onClick={onSubmit} type="button"><Save size={15} />{saving ? "保存中" : "保存角色"}</button></>} onClose={onCancel} size="large" title={editor.mode === "create" ? "新增访问角色" : `编辑访问角色 · ${editor.role_key}`}>
    <section className="identity-catalog-editor role-editor overlay-embedded">
    <div className="identity-form-grid"><label><span>角色标识</span><input disabled={editor.mode === "edit"} onChange={(event) => onChange({ ...editor, role_key: event.target.value.toLowerCase() })} value={editor.role_key} /></label><label><span>角色名称</span><input onChange={(event) => onChange({ ...editor, name: event.target.value })} value={editor.name} /></label><label className="identity-wide-field"><span>描述</span><input onChange={(event) => onChange({ ...editor, description: event.target.value })} value={editor.description} /></label>{editor.mode === "edit" ? <fieldset className="identity-status-control"><legend>状态</legend><div><button className={editor.status === "active" ? "active" : ""} onClick={() => onChange({ ...editor, status: "active" })} type="button">生效</button><button className={editor.status === "suspended" ? "active warning" : ""} onClick={() => onChange({ ...editor, status: "suspended" })} type="button">停用</button></div></fieldset> : null}<label className="identity-reason-field"><span>变更原因</span><input maxLength={500} onChange={(event) => onChange({ ...editor, reason: event.target.value })} placeholder="记录访问策略变更原因" value={editor.reason} /></label></div>
    <div className="permission-editor"><div className="identity-access-editor-title"><div><span>PERMISSION CATALOG</span><h3>选择功能权限</h3></div><em>{editor.permissions.length} 项已选择</em></div>{Object.entries(grouped).map(([resource, permissions]) => <section key={resource}><header><strong>{resource}</strong><small>{permissions.length} 项</small></header><div className="permission-checkbox-grid">{permissions.map((permission) => <label className={editor.permissions.includes(permission.permission_key) ? "selected" : ""} key={permission.permission_key}><input checked={editor.permissions.includes(permission.permission_key)} onChange={() => togglePermission(permission.permission_key)} type="checkbox" /><span><strong>{permission.label}</strong><code>{permission.permission_key}</code></span><small>{permission.risk_level}</small></label>)}</div></section>)}</div>
    </section>
  </Drawer>;
}

function createEditor(data: IdentityAdminOverview): UserEditorForm {
  const org = data.org_units.find((item) => item.org_key === "operations") ?? data.org_units[0];
  const position = data.positions.find((item) => item.position_key === "operations-specialist")
    ?? data.positions.find((item) => item.org_key === org?.org_key)
    ?? data.positions[0];
  return {
    mode: "create",
    account_key: null,
    expected_version: null,
    client_request_key: newRequestKey("create"),
    login_name: "",
    initial_password: "",
    display_name: "",
    email: "",
    experience_role_key: "employee",
    org_key: org?.org_key ?? "",
    position_key: position?.position_key ?? "",
    status: "active",
    assignments: [{ role_key: "employee", scopes: [{ scope_type: "store", scope_ids_text: "store-flagship", effect: "allow" }] }],
    reason: ""
  };
}

function editUser(user: IdentityUserAccount): UserEditorForm {
  return {
    mode: "edit",
    account_key: user.account_key,
    expected_version: user.version,
    client_request_key: newRequestKey("configure"),
    login_name: user.login_name,
    initial_password: "",
    display_name: user.display_name,
    email: user.email ?? "",
    experience_role_key: user.experience_role_key,
    org_key: user.org_key,
    position_key: user.position_key,
    status: user.status === "active" ? "active" : "suspended",
    assignments: user.role_assignments.map((assignment) => ({
      role_key: assignment.role_key,
      scopes: assignment.scopes.map((scope) => ({
        scope_type: scope.scope_type,
        scope_ids_text: scope.scope_type === "self" ? "$self" : scope.scope_ids.join(", "),
        effect: scope.effect
      }))
    })),
    reason: ""
  };
}

function defaultScope(roleKey: string, form: UserEditorForm, data: IdentityAdminOverview): EditableScope {
  const orgId = data.org_units.find((item) => item.org_key === form.org_key)?.org_id ?? "";
  if (["platform-admin", "executive"].includes(roleKey)) return { scope_type: "enterprise", scope_ids_text: data.enterprise_id, effect: "allow" };
  if (roleKey === "service-agent") return { scope_type: "business_unit", scope_ids_text: orgId, effect: "allow" };
  if (["operations-manager", "finance-controller"].includes(roleKey)) return { scope_type: "org_subtree", scope_ids_text: orgId, effect: "allow" };
  return { scope_type: "self", scope_ids_text: "$self", effect: "allow" };
}

function createOrgEditor(data: IdentityAdminOverview): OrgEditorForm {
  return { mode: "create", org_key: "", version: null, name: "", unit_type: "department", parent_org_key: "group", status: "active", reason: "", client_request_key: newRequestKey("org-create") };
}

function editOrgEditor(org: IdentityAdminOverview["org_units"][number], data: IdentityAdminOverview): OrgEditorForm {
  const parent = data.org_units.find((item) => item.name === org.parent_name);
  return { mode: "edit", org_key: org.org_key, version: org.version, name: org.name, unit_type: org.unit_type, parent_org_key: parent?.org_key ?? "", status: org.status === "active" ? "active" : "suspended", reason: "", client_request_key: newRequestKey("org-update") };
}

function createPositionEditor(data: IdentityAdminOverview): PositionEditorForm {
  return { mode: "create", position_key: "", version: null, name: "", position_level: "specialist", org_key: data.org_units.find((item) => item.status === "active")?.org_key ?? "", status: "active", reason: "", client_request_key: newRequestKey("position-create") };
}

function editPositionEditor(position: IdentityAdminOverview["positions"][number], data: IdentityAdminOverview): PositionEditorForm {
  return { mode: "edit", position_key: position.position_key, version: position.version, name: position.name, position_level: position.position_level, org_key: position.org_key, status: position.status === "active" ? "active" : "suspended", reason: "", client_request_key: newRequestKey("position-update") };
}

function createRoleEditor(data: IdentityAdminOverview): RoleEditorForm {
  const defaults = data.permission_catalog.filter((item) => ["platform.navigation.read", "analysis.read"].includes(item.permission_key)).map((item) => item.permission_key);
  return { mode: "create", role_key: "", revision: null, name: "", description: "", status: "active", permissions: defaults, reason: "", client_request_key: newRequestKey("role-create") };
}

function editRoleEditor(role: IdentityAdminOverview["access_roles"][number]): RoleEditorForm {
  return { mode: "edit", role_key: role.role_key, revision: role.revision, name: role.name, description: role.description, status: role.status === "active" ? "active" : "suspended", permissions: [...role.permissions], reason: "", client_request_key: newRequestKey("role-update") };
}

function newRequestKey(action: string): string {
  const token = typeof globalThis.crypto?.randomUUID === "function" ? globalThis.crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return `identity-${action}-${token}`;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(value));
}

function IdentityState({ error = false, title }: { error?: boolean; title: string }) {
  return <div className={`identity-page-state ${error ? "error" : ""}`}>{error ? <CircleAlert size={27} /> : <LoaderCircle className="spinning" size={27} />}<strong>{title}</strong></div>;
}
