"use client";

import { Building2, CircleAlert, KeyRound, LoaderCircle, RefreshCw, Save, ShieldCheck, UserRoundCog, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog, Drawer, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type { AccessDelegation, AccessGovernanceResponse, OrgTreeNode, PermissionExplanation } from "@/lib/platform-admin-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface DelegationDraft { key: string; delegatorId: string; delegateeId: string; permissions: string[]; scopeType: string; scopeIds: string; validFrom: string; validTo: string; reason: string; }

export function AccessDelegationPage() {
  const { roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<AccessGovernanceResponse | null>(null);
  const [draft, setDraft] = useState<DelegationDraft | null>(null);
  const [explanation, setExplanation] = useState<PermissionExplanation | null>(null);
  const [selectedPrincipalId, setSelectedPrincipalId] = useState("");
  const [permissionQuery, setPermissionQuery] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<AccessDelegation | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/access-governance`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId } });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "访问委托读取失败"));
    const result = (await response.json()) as AccessGovernanceResponse; setData(result); setSelectedPrincipalId((current) => current || result.principals[0]?.id || "");
  }, [roleId]);

  useEffect(() => { load().catch((value: unknown) => setError(value instanceof Error ? value.message : "访问委托读取失败")); }, [load]);

  const filteredPermissions = useMemo(() => (data?.permission_catalog ?? []).filter((item) => item.toLocaleLowerCase().includes(permissionQuery.trim().toLocaleLowerCase())), [data?.permission_catalog, permissionQuery]);

  async function createDelegation(): Promise<void> {
    if (!draft) return;
    setSaving(true); setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/access-governance/delegations`, { method: "POST", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("delegation"), reason: draft.reason.trim(), delegation_key: draft.key.trim(), delegator_principal_id: draft.delegatorId, delegatee_principal_id: draft.delegateeId, permissions: draft.permissions, scopes: [{ scope_type: draft.scopeType, scope_ids: draft.scopeIds.split(",").map((item) => item.trim()).filter(Boolean), effect: "allow" }], valid_from: new Date(draft.validFrom).toISOString(), valid_to: new Date(draft.validTo).toISOString() }) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "访问委托创建失败"));
      notify({ title: "访问委托已创建", description: draft.key, tone: "success" }); setDraft(null); await load();
    } catch (value: unknown) { notify({ title: "访问委托创建失败", description: value instanceof Error ? value.message : "请检查委托范围后重试", tone: "error" }); }
    finally { setSaving(false); }
  }

  async function revoke(item: AccessDelegation): Promise<void> {
    setSaving(true); setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/access-governance/delegations/${encodeURIComponent(item.id)}/revoke`, { method: "POST", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId }, body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("delegation-revoke"), reason: "撤销临时访问委托", expected_revision: item.revision }) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "访问委托撤销失败"));
      notify({ title: "访问委托已撤销", description: item.delegation_key, tone: "success" }); setRevokeTarget(null); await load();
    } catch (value: unknown) { notify({ title: "访问委托撤销失败", description: value instanceof Error ? value.message : "请重试", tone: "error" }); }
    finally { setSaving(false); }
  }

  async function explain(): Promise<void> {
    if (!selectedPrincipalId) return;
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/access-governance/permissions/${encodeURIComponent(selectedPrincipalId)}`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId } });
    if (!response.ok) { setError(await apiErrorMessage(response, "权限解释读取失败")); return; }
    setExplanation((await response.json()) as PermissionExplanation);
  }

  return <div className="platform-control-page access-delegation-page">
    <PageHeader actions={<div className="platform-header-actions"><button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新</button><button className="button primary" onClick={() => setDraft(createDraft(data))} type="button"><UserRoundCog size={15} />新建委托</button></div>} eyebrow="ACCESS GOVERNANCE" meta={`${data?.delegations.length ?? 0} 条委托`} title="组织与访问委托" />
    {error ? <InlineCallout description={error} title="操作未完成" tone="critical" /> : null}
    <div className="access-governance-grid"><aside className="org-tree-panel"><header><span>ORGANIZATION</span><h2>组织子树</h2></header><div>{data?.org_tree.map((node) => <OrgNode key={node.id} node={node} />)}</div></aside>
      <section className="platform-data-panel"><header><div><span>DELEGATIONS</span><h2>临时访问委托</h2></div><em>{data?.delegations.length ?? 0} 条</em></header><div className="platform-table-wrap"><table><thead><tr><th>委托</th><th>委托人</th><th>被委托人</th><th>权限</th><th>状态</th><th>有效期</th><th>操作</th></tr></thead><tbody>{data?.delegations.map((item) => <tr key={item.id}><td><strong>{item.delegation_key}</strong><small>{item.reason}</small></td><td>{item.delegator_name}</td><td>{item.delegatee_name}</td><td>{item.permissions.length}<small>{item.permissions.slice(0, 2).join(" · ")}</small></td><td><StatusBadge value={delegationStatus(item.status)} /></td><td>{formatDate(item.valid_from)}<small>{formatDate(item.valid_to)}</small></td><td>{!["revoked", "expired"].includes(item.status) ? <button aria-label="撤销委托" className="platform-icon-button danger" disabled={saving} onClick={() => setRevokeTarget(item)} title="撤销" type="button"><X size={14} /></button> : null}</td></tr>)}</tbody></table>{data?.delegations.length ? null : <div className="platform-empty-state"><ShieldCheck size={23} /><strong>当前没有临时委托</strong></div>}</div></section>
    </div>
    {draft && data ? <Drawer busy={saving} className="delegation-drawer" eyebrow="DELEGATION" footer={<><span>{draft.permissions.length} 项权限</span><button className="button secondary" disabled={saving} onClick={() => setDraft(null)} type="button">取消</button><button className="button primary" disabled={saving || draft.key.trim().length < 3 || draft.reason.trim().length < 3 || draft.permissions.length < 1 || !draft.scopeIds.trim()} onClick={() => void createDelegation()} type="button">{saving ? <LoaderCircle className="spinning" size={15} /> : <Save size={15} />}创建委托</button></>} onClose={() => setDraft(null)} size="large" title="新建访问委托"><div className="platform-form-grid overlay-form-grid">
      <label><span>委托标识</span><input onChange={(event) => setDraft({ ...draft, key: event.target.value })} value={draft.key} /></label>
      <label><span>委托人</span><select onChange={(event) => setDraft({ ...draft, delegatorId: event.target.value })} value={draft.delegatorId}>{data.principals.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.position}</option>)}</select></label>
      <label><span>被委托人</span><select onChange={(event) => setDraft({ ...draft, delegateeId: event.target.value })} value={draft.delegateeId}>{data.principals.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.position}</option>)}</select></label>
      <label><span>范围类型</span><select onChange={(event) => setDraft({ ...draft, scopeType: event.target.value })} value={draft.scopeType}><option value="enterprise">企业</option><option value="org_subtree">组织子树</option><option value="store">店铺</option><option value="self">本人</option></select></label>
      <label><span>范围 ID</span><input onChange={(event) => setDraft({ ...draft, scopeIds: event.target.value })} value={draft.scopeIds} /></label>
      <label><span>开始时间</span><input onChange={(event) => setDraft({ ...draft, validFrom: event.target.value })} type="datetime-local" value={draft.validFrom} /></label>
      <label><span>结束时间</span><input onChange={(event) => setDraft({ ...draft, validTo: event.target.value })} type="datetime-local" value={draft.validTo} /></label>
      <label className="platform-wide-field"><span>委托原因</span><input onChange={(event) => setDraft({ ...draft, reason: event.target.value })} value={draft.reason} /></label>
      <section className="permission-picker platform-wide-field"><header><span>权限</span><input onChange={(event) => setPermissionQuery(event.target.value)} placeholder="检索权限" value={permissionQuery} /></header><div>{filteredPermissions.map((permission) => <label key={permission}><input checked={draft.permissions.includes(permission)} onChange={(event) => setDraft({ ...draft, permissions: event.target.checked ? [...draft.permissions, permission] : draft.permissions.filter((item) => item !== permission) })} type="checkbox" /><span>{permission}</span></label>)}</div></section>
    </div></Drawer> : null}
    {revokeTarget ? <ConfirmDialog busy={saving} confirmLabel="撤销委托" description={`确认撤销 ${revokeTarget.delegation_key}？`} detail={`${revokeTarget.delegatee_name} 将立即失去该委托提供的 ${revokeTarget.permissions.length} 项权限。`} onCancel={() => setRevokeTarget(null)} onConfirm={() => void revoke(revokeTarget)} title="撤销访问委托" tone="danger" /> : null}
    <section className="permission-explanation-panel"><header><div><span>PERMISSION EXPLANATION</span><h2>权限解释</h2></div><div><select onChange={(event) => { setSelectedPrincipalId(event.target.value); setExplanation(null); }} value={selectedPrincipalId}>{data?.principals.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.organization}</option>)}</select><button className="button secondary compact" onClick={() => void explain()} type="button"><KeyRound size={14} />解析</button></div></header>{explanation ? <div className="permission-explanation-grid"><article><span>直接角色</span><strong>{explanation.direct_roles.length}</strong><p>{explanation.direct_roles.join(" · ") || "无"}</p></article><article><span>直接权限</span><strong>{explanation.direct_permissions.length}</strong><p>{explanation.direct_permissions.join(" · ") || "无"}</p></article><article><span>委托权限</span><strong>{explanation.delegated_permissions.length}</strong><p>{explanation.delegated_permissions.join(" · ") || "无"}</p></article><article><span>有效权限</span><strong>{explanation.effective_permissions.length}</strong><p>{explanation.effective_permissions.join(" · ") || "无"}</p></article></div> : <div className="platform-empty-state"><KeyRound size={23} /><strong>选择主体并解析权限</strong></div>}</section>
  </div>;
}

function OrgNode({ node, depth = 0 }: { node: OrgTreeNode; depth?: number }) { return <div className="org-tree-node" style={{ "--org-depth": depth } as React.CSSProperties}><div><Building2 size={15} /><span><strong>{node.name}</strong><small>{node.unit_type} · {node.member_count} 人</small></span><StatusBadge value={delegationStatus(node.status)} /></div>{node.children.map((child) => <OrgNode depth={depth + 1} key={child.id} node={child} />)}</div>; }
function delegationStatus(value: string) { return { label: ({ active: "生效", scheduled: "待生效", revoked: "已撤销", expired: "已过期" } as Record<string, string>)[value] ?? value, tone: value === "active" ? "positive" as const : value === "revoked" ? "critical" as const : "warning" as const }; }
function formatDate(value: string): string { return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)); }
function localDate(value: Date): string { const offset = value.getTimezoneOffset() * 60_000; return new Date(value.getTime() - offset).toISOString().slice(0, 16); }
function createDraft(data: AccessGovernanceResponse | null): DelegationDraft { const now = new Date(); const tomorrow = new Date(now.getTime() + 24 * 60 * 60 * 1000); return { key: "", delegatorId: data?.principals[0]?.id ?? "", delegateeId: data?.principals[1]?.id ?? data?.principals[0]?.id ?? "", permissions: [], scopeType: "enterprise", scopeIds: data?.org_tree[0]?.id ?? "", validFrom: localDate(now), validTo: localDate(tomorrow), reason: "" }; }
function requestKey(prefix: string): string { return `${prefix}-${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now()}`; }
