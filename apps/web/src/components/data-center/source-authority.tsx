"use client";

import { useCallback, useEffect, useState } from "react";

import { ConfirmDialog, Dialog, useNotifications } from "@/components/console/interaction";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";

interface Assignment { id: string; business_unit_id: string; source_key: string; fact_family: string; resource_key: string; status: string; version: number }
interface Resource { key: string; fact_family: string | null; projectable: boolean }
interface Form { business_unit_id: string; resource_key: string; status: string; expected_version: number }
const API = `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"}/api/v1/data-center/authority-assignments`;
const labels: Record<string, string> = { orders: "销售订单", after_sales: "销售售后", inventory: "仓库库存", fulfillments: "销售出库" };

export function SourceAuthority({ sourceKey, resources }: { sourceKey: string; resources: Resource[] }) {
  const { scopeOptions, scopeContext, identity } = useExperience();
  const { notify } = useNotifications();
  const [items, setItems] = useState<Assignment[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const available = resources.filter((row) => row.fact_family && row.projectable);
  const units = scopeOptions?.business_units.filter((unit) => unit.enterprise_id === identity?.enterprise_id && scopeContext?.business_unit_ids.includes(unit.key)) ?? [];
  const unitName = (key: string) => units.find((unit) => unit.key === key)?.label ?? key;
  const load = useCallback(async () => {
    const response = await apiFetch(API, { cache: "no-store" });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "读取权威规则失败"));
    setItems(await response.json() as Assignment[]); setError(null);
  }, []);
  useEffect(() => { void load().catch((reason: Error) => setError(reason.message)); }, [load]);
  const save = async () => {
    if (!form) return;
    setBusy(true);
    try {
      const response = await apiFetch(API, { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, source_key: sourceKey,
          fact_family: resources.find((row) => row.key === form.resource_key)?.fact_family }) });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "保存权威规则失败"));
      setConfirm(false); setForm(null); notify({ tone: "success", title: "权威规则已保存" }); await load();
    } catch (reason) { const message = reason instanceof Error ? reason.message : "保存失败";
      setError(message); notify({ tone: "error", title: message }); }
    finally { setBusy(false); }
  };
  return <>
    {error ? <p role="alert">{error}</p> : null}
    <div className="console-toolbar"><button className="button primary" type="button" disabled={busy || !available.length} onClick={() => setForm({ business_unit_id: "", resource_key: "", status: "active", expected_version: 0 })}>新增权威规则</button>
      <button className="button secondary" type="button" disabled={busy} onClick={() => void load().catch((reason: Error) => setError(reason.message))}>刷新</button></div>
    <table><thead><tr><th>业务单元</th><th>事实族</th><th>权威来源</th><th>状态 / 版本</th><th>操作</th></tr></thead><tbody>
      {items.map((row) => <tr key={row.id}><td>{unitName(row.business_unit_id)}</td><td>{labels[row.fact_family] ?? row.fact_family}</td><td>{row.source_key}</td><td>{row.status === "active" ? "启用" : "停用"} / {row.version}</td><td>
        <button className="button secondary" type="button" disabled={busy || !available.some((item) => item.key === row.resource_key)} onClick={() => setForm({ business_unit_id: row.business_unit_id, resource_key: row.resource_key, status: row.status, expected_version: row.version })}>调整</button>
      </td></tr>)}
      {!items.length ? <tr><td colSpan={5}>暂无权威规则</td></tr> : null}
    </tbody></table>
    {form ? <Dialog title="权威来源规则" busy={busy} onClose={() => setForm(null)} footer={<button type="button" className="button primary" disabled={busy || !form.business_unit_id || !form.resource_key} onClick={() => setConfirm(true)}>保存</button>}>
      {error ? <p role="alert">{error}</p> : null}<p>权威来源：{sourceKey}</p>
      <div className="platform-form-grid source-form-grid">
      <label>业务单元<select value={form.business_unit_id} disabled={form.expected_version > 0} onChange={(event) => setForm({ ...form, business_unit_id: event.target.value })}><option value="">请选择</option>{units.map((unit) => <option key={unit.key} value={unit.key}>{unit.label}</option>)}</select></label>
      <label>事实资源<select value={form.resource_key} disabled={form.expected_version > 0} onChange={(event) => setForm({ ...form, resource_key: event.target.value })}><option value="">请选择</option>{available.map((row) => <option key={row.key} value={row.key}>{labels[row.fact_family ?? ""] ?? row.key}</option>)}</select></label>
      <label>状态<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })}><option value="active">启用</option><option value="disabled">停用</option></select></label>
      </div>
    </Dialog> : null}
    {confirm && form ? <ConfirmDialog title="确认权威来源变更" description={`${unitName(form.business_unit_id)} / ${labels[form.resource_key] ?? form.resource_key}：${form.status === "active" ? `将权威来源设为 ${sourceKey}，替换已有指派。` : "停用权威规则，停止纳入权威查询。"}`} busy={busy} onCancel={() => setConfirm(false)} onConfirm={() => void save()} /> : null}
  </>;
}
