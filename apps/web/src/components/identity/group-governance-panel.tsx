"use client";

import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog, Dialog, useNotifications } from "@/components/console/interaction";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/governance`;
interface Organization { id: string; code: string; name: string; timezone: string }
interface Unit { id: string; enterprise_id: string; unit_key: string; name: string; unit_type: string; parent_id: string | null; status: string; version: number }
interface Membership { id: string; enterprise_id: string; principal_id: string; status: string; version: number }
interface Profile { id: string; name: string; profile_key: string; version: string; base_currency: string; status: string }
interface Governance { group: Organization | null; can_manage_group: boolean; enterprises: Organization[]; business_units: Unit[]; memberships: Membership[]; principals: { id: string; display_name: string }[]; consolidation_profiles: Profile[] }
interface Editor { kind: "group" | "enterprise" | "unit" | "membership" | "profile"; id?: string; code: string; name: string; timezone: string; enterprise_id: string; parent_id: string; unit_type: string; principal_id: string; status: string; version?: number; profile_version: string; currency: string }

export function GroupGovernancePanel() {
  const { identity, can, refreshScope } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<Governance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [confirm, setConfirm] = useState(false);
  const load = useCallback(async () => {
    const response = await apiFetch(API, { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "集团组织读取失败"));
    setData(await response.json() as Governance);
  }, [identity?.enterprise_id]);
  useEffect(() => { void load().catch((reason: Error) => setError(reason.message)); }, [load]);
  const begin = (kind: Editor["kind"], row?: Organization | Unit | Membership) => {
    const next: Editor = { kind, id: row?.id, code: "", name: "", timezone: "Asia/Shanghai", enterprise_id: identity?.enterprise_id ?? "", parent_id: "", unit_type: "project", principal_id: "", status: "active", profile_version: "", currency: "" };
    if (row) {
      if ("code" in row) Object.assign(next, { code: row.code, name: row.name, timezone: row.timezone });
      if ("enterprise_id" in row) Object.assign(next, { enterprise_id: row.enterprise_id, status: row.status, version: row.version });
      if ("unit_key" in row) Object.assign(next, { code: row.unit_key, name: row.name, parent_id: row.parent_id ?? "", unit_type: row.unit_type });
      if ("principal_id" in row) next.principal_id = row.principal_id;
    }
    setError(null); setEditor(next);
  };
  const save = async () => {
    if (!editor) return;
    setBusy(true); setError(null);
    try {
      let path = ""; let method = "PUT"; let payload: unknown;
      if (editor.kind === "group" || editor.kind === "enterprise") {
        path = editor.kind === "group" ? "/group" : `/enterprises${editor.id ? `/${editor.id}` : ""}`;
        method = editor.kind === "enterprise" && !editor.id ? "POST" : "PUT";
        payload = { code: editor.code, name: editor.name, timezone: editor.timezone };
      } else if (editor.kind === "unit") {
        path = `/business-units${editor.id ? `/${editor.id}` : ""}`; method = editor.id ? "PUT" : "POST";
        payload = { enterprise_id: editor.enterprise_id, unit_key: editor.code, name: editor.name, unit_type: editor.unit_type, parent_id: editor.parent_id || null, status: editor.status, expected_version: editor.version ?? null };
      } else if (editor.kind === "membership") {
        path = "/memberships"; payload = { enterprise_id: editor.enterprise_id, principal_id: editor.principal_id, status: editor.status, expected_version: editor.version ?? null };
      } else {
        path = "/consolidation-profiles"; method = "POST";
        payload = { profile_key: editor.code, name: editor.name, version: editor.profile_version, base_currency: editor.currency, exchange_rate_policy: {}, elimination_rules: [] };
      }
      const response = await apiFetch(`${API}${path}`, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "集团组织保存失败"));
      setEditor(null); setConfirm(false); notify({ tone: "success", title: "组织变更已保存" });
      await load(); await refreshScope();
    } catch (reason) { const message = reason instanceof Error ? reason.message : "保存失败";
      setError(message); notify({ tone: "error", title: message }); setConfirm(false); }
    finally { setBusy(false); }
  };
  if (!data) return <section className="data-source-panel"><h2>集团组织</h2><p role={error ? "alert" : "status"}>{error ?? "正在读取集团组织"}</p></section>;
  const title = { group: "集团", enterprise: "法人", unit: "业务单元", membership: "成员关系", profile: "合并口径" };
  return <section className="data-source-panel">
    <header><h2>{data.group?.name ?? "集团组织"}</h2><div className="console-toolbar">
      {data.can_manage_group || (!data.group && can("identity.access.manage")) ? <button className="button secondary" type="button" onClick={() => begin("group", data.group ?? undefined)}>{data.group ? "编辑集团" : "创建集团"}</button> : null}
      {data.can_manage_group ? <button className="button secondary" type="button" onClick={() => begin("enterprise")}>新增法人</button> : null}
      <button className="button secondary" type="button" onClick={() => begin("unit")}>新增业务单元</button>
      {data.can_manage_group && can("identity.access.manage") ? <button className="button secondary" type="button" onClick={() => begin("membership")}>新增成员关系</button> : null}
      {data.can_manage_group ? <button className="button secondary" type="button" onClick={() => begin("profile")}>发布合并口径</button> : null}
    </div></header>
    {error && !editor ? <p role="alert">{error}</p> : null}
    <div className="table-wrap"><table><thead><tr><th>法人</th><th>标识</th><th>时区</th><th>操作</th></tr></thead><tbody>{data.enterprises.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.code}</td><td>{row.timezone}</td><td><button className="button secondary" type="button" onClick={() => begin("enterprise", row)}>编辑</button></td></tr>)}</tbody></table>
      <table><thead><tr><th>业务单元</th><th>法人</th><th>类型</th><th>状态 / 版本</th><th>操作</th></tr></thead><tbody>{data.business_units.map((row) => <tr key={row.id}><td>{row.name}</td><td>{data.enterprises.find((item) => item.id === row.enterprise_id)?.name}</td><td>{row.unit_type}</td><td>{row.status} / {row.version}</td><td><button className="button secondary" type="button" onClick={() => begin("unit", row)}>编辑</button></td></tr>)}{!data.business_units.length ? <tr><td colSpan={5}>暂无业务单元</td></tr> : null}</tbody></table>
      <table><thead><tr><th>成员</th><th>法人</th><th>状态</th><th>操作</th></tr></thead><tbody>{data.memberships.map((row) => <tr key={row.id}><td>{data.principals.find((item) => item.id === row.principal_id)?.display_name ?? row.principal_id}</td><td>{data.enterprises.find((item) => item.id === row.enterprise_id)?.name}</td><td>{row.status}</td><td>{data.can_manage_group && can("identity.access.manage") ? <button className="button secondary" type="button" onClick={() => begin("membership", row)}>编辑</button> : "—"}</td></tr>)}{!data.memberships.length ? <tr><td colSpan={4}>暂无成员关系</td></tr> : null}</tbody></table>
      <table><thead><tr><th>合并口径</th><th>版本</th><th>本位币</th><th>状态</th></tr></thead><tbody>{data.consolidation_profiles.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.version}</td><td>{row.base_currency}</td><td>{row.status}</td></tr>)}{!data.consolidation_profiles.length ? <tr><td colSpan={4}>暂无合并口径</td></tr> : null}</tbody></table>
    </div>
    {editor ? <Dialog title={`${editor.id ? "编辑" : "新增"}${title[editor.kind]}`} onClose={() => setEditor(null)} busy={busy} footer={<button className="button primary" disabled={busy} type="button" onClick={() => editor.status === "disabled" || editor.status === "revoked" ? setConfirm(true) : void save()}>保存</button>}>
      {error ? <p role="alert">{error}</p> : null}<div className="platform-form-grid overlay-form-grid">
        {editor.kind !== "membership" ? <><label>标识<input value={editor.code} onChange={(event) => setEditor({ ...editor, code: event.target.value })} /></label><label>名称<input value={editor.name} onChange={(event) => setEditor({ ...editor, name: event.target.value })} /></label></> : null}
        {["group", "enterprise"].includes(editor.kind) ? <label>时区<input value={editor.timezone} onChange={(event) => setEditor({ ...editor, timezone: event.target.value })} /></label> : null}
        {["unit", "membership"].includes(editor.kind) ? <label>法人<select disabled={!!editor.id} value={editor.enterprise_id} onChange={(event) => setEditor({ ...editor, enterprise_id: event.target.value, parent_id: "" })}>{data.enterprises.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label> : null}
        {editor.kind === "unit" ? <><label>类型<select value={editor.unit_type} onChange={(event) => setEditor({ ...editor, unit_type: event.target.value })}>{[["project", "项目"], ["brand", "品牌"], ["division", "事业部"], ["region", "区域"]].map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label>上级单元<select value={editor.parent_id} onChange={(event) => setEditor({ ...editor, parent_id: event.target.value })}><option value="">无</option>{data.business_units.filter((item) => item.enterprise_id === editor.enterprise_id && item.id !== editor.id && item.status === "active").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></> : null}
        {editor.kind === "membership" ? <label>成员<select disabled={!!editor.id} value={editor.principal_id} onChange={(event) => setEditor({ ...editor, principal_id: event.target.value })}><option value="">请选择</option>{data.principals.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label> : null}
        {["unit", "membership"].includes(editor.kind) ? <label>状态<select value={editor.status} onChange={(event) => setEditor({ ...editor, status: event.target.value })}><option value="active">有效</option><option value={editor.kind === "unit" ? "disabled" : "revoked"}>{editor.kind === "unit" ? "停用" : "撤销"}</option></select></label> : null}
        {editor.kind === "profile" ? <><label>版本<input value={editor.profile_version} onChange={(event) => setEditor({ ...editor, profile_version: event.target.value })} /></label><label>本位币<input value={editor.currency} maxLength={3} onChange={(event) => setEditor({ ...editor, currency: event.target.value.toUpperCase() })} /></label></> : null}
      </div>
    </Dialog> : null}
    {confirm ? <ConfirmDialog title="确认组织变更" description={editor?.kind === "membership" ? "撤销成员关系并使现有会话失效？" : "停用业务单元？"} busy={busy} onCancel={() => setConfirm(false)} onConfirm={() => void save()} /> : null}
  </section>;
}
