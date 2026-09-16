"use client";

import {
  Braces,
  Building2,
  Check,
  CircleAlert,
  DatabaseZap,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  ShieldCheck
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Dialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type { DictionaryItem, PlatformConfigResponse, PlatformDictionary, PlatformParameter } from "@/lib/platform-admin-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface ParameterEditor { key: string; revision: number; valueType: string; value: string; status: string; reason: string; }
interface DictionaryEditor { dictionaryKey: string; itemKey: string; revision: number | null; label: string; value: string; sortOrder: string; status: string; reason: string; isNew: boolean; }

export interface EnterpriseProfile {
  legalName: string;
  taxId: string;
  businessScope: string;
  reportingCurrency: string;
  fxStandard: string;
  historyStart: string;
  contactEmail: string;
  notes: string;
}

const DEFAULT_ENTERPRISE_PROFILE: EnterpriseProfile = {
  legalName: "知行数枢智能科技（跨境运营中心）",
  taxId: "91310000MA1FL9988X",
  businessScope: "亚马逊北美多店铺精细化跨境电商运营",
  reportingCurrency: "USD (美元)",
  fxStandard: "发生月月末记账汇率（按领星ERP月度汇率表自动折算）",
  historyStart: "2025-01-01 00:00:00",
  contactEmail: "finance-reconcile@zhixing.com",
  notes: "支持多店铺全域聚合，单据自动按业务发生月汇率折算，历史数据从2025-01-01起拉取。"
};

export function PlatformConfigPage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<PlatformConfigResponse | null>(null);
  const [parameterEditor, setParameterEditor] = useState<ParameterEditor | null>(null);
  const [dictionaryEditor, setDictionaryEditor] = useState<DictionaryEditor | null>(null);
  const [activeDictionary, setActiveDictionary] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canManage = can("platform.config.manage");

  const [profile, setProfile] = useState<EnterpriseProfile>(DEFAULT_ENTERPRISE_PROFILE);
  const [profileEditing, setProfileEditing] = useState(false);
  const [profileForm, setProfileForm] = useState<EnterpriseProfile>(DEFAULT_ENTERPRISE_PROFILE);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const cached = localStorage.getItem("zhixing_enterprise_profile");
      if (cached) {
        try {
          const parsed = JSON.parse(cached) as EnterpriseProfile;
          setProfile(parsed);
          setProfileForm(parsed);
        } catch {}
      }
    }
  }, []);

  function saveProfile() {
    setProfile(profileForm);
    if (typeof window !== "undefined") {
      localStorage.setItem("zhixing_enterprise_profile", JSON.stringify(profileForm));
    }
    setProfileEditing(false);
    notify({
      title: "企业基本信息已更新",
      description: `已成功保存企业名称「${profileForm.legalName}」及财务基准币种配置。`,
      tone: "success"
    });
  }

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/config`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId } });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "平台配置读取失败"));
    const result = (await response.json()) as PlatformConfigResponse;
    setData(result);
    setActiveDictionary((current) => current || result.dictionaries[0]?.dictionary_key || "");
  }, [roleId]);

  useEffect(() => { setLoading(true); load().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "平台配置读取失败")).finally(() => setLoading(false)); }, [load]);

  const dictionary = useMemo(() => data?.dictionaries.find((item) => item.dictionary_key === activeDictionary) ?? null, [activeDictionary, data?.dictionaries]);

  async function saveParameter(): Promise<void> {
    if (!parameterEditor || !canManage) return;
    setSaving(true); setError(null);
    try {
      const value = parseValue(parameterEditor.value, parameterEditor.valueType);
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/config/parameters/${encodeURIComponent(parameterEditor.key)}`, {
        method: "PUT", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("parameter"), reason: parameterEditor.reason.trim(), expected_revision: parameterEditor.revision, value, status: parameterEditor.status })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "平台参数保存失败"));
      notify({ title: "平台参数已更新", description: parameterEditor.key, tone: "success" }); setParameterEditor(null); await load();
    } catch (reason: unknown) { notify({ title: "平台参数保存失败", description: reason instanceof Error ? reason.message : "请检查参数值后重试", tone: "error" }); }
    finally { setSaving(false); }
  }

  async function saveDictionaryItem(): Promise<void> {
    if (!dictionaryEditor || !canManage) return;
    setSaving(true); setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/config/dictionaries/${encodeURIComponent(dictionaryEditor.dictionaryKey)}/items/${encodeURIComponent(dictionaryEditor.itemKey)}`, {
        method: "PUT", headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("dictionary-item"), reason: dictionaryEditor.reason.trim(), expected_revision: dictionaryEditor.revision, label: dictionaryEditor.label.trim(), value: parseLooseValue(dictionaryEditor.value), sort_order: Number(dictionaryEditor.sortOrder), status: dictionaryEditor.status })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "字典项保存失败"));
      notify({ title: "字典项已更新", description: `${dictionaryEditor.dictionaryKey}.${dictionaryEditor.itemKey}`, tone: "success" }); setDictionaryEditor(null); await load();
    } catch (reason: unknown) { notify({ title: "字典项保存失败", description: reason instanceof Error ? reason.message : "请检查输入后重试", tone: "error" }); }
    finally { setSaving(false); }
  }

  if (loading && !data) return <ConfigState title="正在读取平台配置" />;

  return <div className="platform-control-page platform-config-page">
    <PageHeader actions={<button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新</button>} eyebrow="PLATFORM CONFIG" meta={`${data?.parameters.length ?? 0} 个参数 · ${data?.dictionaries.length ?? 0} 个字典`} title="参数与字典" />
    {error ? <InlineCallout description={error} title="操作未完成" tone="critical" /> : null}
    {/* Enterprise Basic Info & Operational Policy Section */}
    <section className="platform-data-panel" style={{ marginBottom: "20px" }}>
      <header>
        <div>
          <span>ENTERPRISE PROFILE</span>
          <h2>企业基本信息与核算口径配置</h2>
        </div>
        <div>
          {profileEditing ? (
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                className="button secondary compact"
                onClick={() => {
                  setProfileForm(profile);
                  setProfileEditing(false);
                }}
                type="button"
              >
                <RotateCcw size={14} />取消
              </button>
              <button
                className="button primary compact"
                onClick={saveProfile}
                type="button"
              >
                <Save size={14} />保存企业信息
              </button>
            </div>
          ) : (
            <button
              className="button secondary compact"
              onClick={() => {
                setProfileForm(profile);
                setProfileEditing(true);
              }}
              type="button"
            >
              <Pencil size={14} />编辑基本信息
            </button>
          )}
        </div>
      </header>

      {profileEditing ? (
        <div style={{ padding: "16px 20px", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" }}>
          <label>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>企业法定/品牌名称</span>
            <input
              onChange={(e) => setProfileForm({ ...profileForm, legalName: e.target.value })}
              style={{ width: "100%", padding: "8px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              value={profileForm.legalName}
            />
          </label>
          <label>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>统一社会信用代码 / 税号</span>
            <input
              onChange={(e) => setProfileForm({ ...profileForm, taxId: e.target.value })}
              style={{ width: "100%", padding: "8px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              value={profileForm.taxId}
            />
          </label>
          <label>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>跨境经营范围与业务模式</span>
            <input
              onChange={(e) => setProfileForm({ ...profileForm, businessScope: e.target.value })}
              style={{ width: "100%", padding: "8px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              value={profileForm.businessScope}
            />
          </label>
          <label>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>财务核算基准币种</span>
            <select
              onChange={(e) => setProfileForm({ ...profileForm, reportingCurrency: e.target.value })}
              style={{ width: "100%", padding: "8px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              value={profileForm.reportingCurrency}
            >
              <option value="USD (美元)">USD (美元) - 北美站基准</option>
              <option value="CNY (人民币)">CNY (人民币) - 母公司汇编基准</option>
            </select>
          </label>
          <label>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>汇率计算口径标准</span>
            <input
              onChange={(e) => setProfileForm({ ...profileForm, fxStandard: e.target.value })}
              style={{ width: "100%", padding: "8px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              value={profileForm.fxStandard}
            />
          </label>
          <label>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>历史数据同步起点</span>
            <input
              onChange={(e) => setProfileForm({ ...profileForm, historyStart: e.target.value })}
              style={{ width: "100%", padding: "8px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              value={profileForm.historyStart}
            />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>对账与财务负责人联系方式</span>
            <input
              onChange={(e) => setProfileForm({ ...profileForm, contactEmail: e.target.value })}
              style={{ width: "100%", padding: "8px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              value={profileForm.contactEmail}
            />
          </label>
          <label style={{ gridColumn: "1 / -1" }}>
            <span style={{ fontSize: "12px", fontWeight: 600, color: "#475569" }}>财务与经营备忘说明</span>
            <textarea
              onChange={(e) => setProfileForm({ ...profileForm, notes: e.target.value })}
              rows={2}
              style={{ width: "100%", padding: "8px 10px", borderRadius: "6px", border: "1px solid #cbd5e1" }}
              value={profileForm.notes}
            />
          </label>
        </div>
      ) : (
        <div style={{ padding: "16px 20px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "16px", fontSize: "13px" }}>
            <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
              <div style={{ color: "#64748b", fontSize: "12px" }}>企业法定/品牌名称</div>
              <strong style={{ fontSize: "15px", color: "#0f172a" }}>{profile.legalName}</strong>
              <div style={{ color: "#64748b", fontSize: "12px", marginTop: "4px" }}>税号: {profile.taxId}</div>
            </div>
            <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
              <div style={{ color: "#64748b", fontSize: "12px" }}>财务基准币种 & 汇率标准</div>
              <strong style={{ fontSize: "15px", color: "#2563eb" }}>{profile.reportingCurrency}</strong>
              <div style={{ color: "#64748b", fontSize: "12px", marginTop: "4px" }}>{profile.fxStandard}</div>
            </div>
            <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
              <div style={{ color: "#64748b", fontSize: "12px" }}>历史数据拉取起点</div>
              <strong style={{ fontSize: "15px", color: "#0f172a" }}>{profile.historyStart}</strong>
              <div style={{ color: "#64748b", fontSize: "12px", marginTop: "4px" }}>业务范围: {profile.businessScope}</div>
            </div>
            <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: "6px", border: "1px solid #e2e8f0" }}>
              <div style={{ color: "#64748b", fontSize: "12px" }}>对账与数据负责人</div>
              <strong style={{ fontSize: "15px", color: "#0f172a" }}>{profile.contactEmail}</strong>
              <div style={{ color: "#64748b", fontSize: "12px", marginTop: "4px" }}>备忘: {profile.notes}</div>
            </div>
          </div>
        </div>
      )}
    </section>
    <section className="platform-data-panel">
      <header><div><span>PARAMETERS</span><h2>平台参数</h2></div><em>{data?.parameters.length ?? 0} 项</em></header>
      <div className="platform-table-wrap"><table><thead><tr><th>参数</th><th>分组</th><th>类型</th><th>当前值</th><th>状态</th><th>版本</th><th>操作</th></tr></thead><tbody>{data?.parameters.map((item) => <tr key={item.parameter_key}><td><strong>{item.label}</strong><small>{item.parameter_key}</small></td><td>{item.group_key}</td><td><code>{item.value_type}</code></td><td><code>{displayValue(item.value)}</code></td><td><StatusBadge value={activeStatus(item.status)} /></td><td>r{item.revision}</td><td><button aria-label="编辑参数" className="platform-icon-button" disabled={!canManage} onClick={() => setParameterEditor(createParameterEditor(item))} title="编辑" type="button"><Pencil size={14} /></button></td></tr>)}</tbody></table></div>
      {parameterEditor ? <ConfigEditor busy={saving} onClose={() => setParameterEditor(null)} title={parameterEditor.key} version={`r${parameterEditor.revision}`}>
        <label><span>参数值</span><input onChange={(event) => setParameterEditor({ ...parameterEditor, value: event.target.value })} value={parameterEditor.value} /></label>
        <label><span>状态</span><select onChange={(event) => setParameterEditor({ ...parameterEditor, status: event.target.value })} value={parameterEditor.status}><option value="active">启用</option><option value="inactive">停用</option></select></label>
        <label className="platform-wide-field"><span>变更原因</span><input onChange={(event) => setParameterEditor({ ...parameterEditor, reason: event.target.value })} value={parameterEditor.reason} /></label>
        <footer><button className="button secondary" onClick={() => setParameterEditor(null)} type="button">取消</button><button className="button primary" disabled={saving || parameterEditor.reason.trim().length < 3} onClick={() => void saveParameter()} type="button">{saving ? <LoaderCircle className="spinning" size={15} /> : <Save size={15} />}保存</button></footer>
      </ConfigEditor> : null}
    </section>
    <div className="platform-split-workspace config-dictionary-workspace">
      <aside className="platform-side-list"><header><span>DICTIONARIES</span><h2>平台字典</h2></header>{data?.dictionaries.map((item) => <button className={item.dictionary_key === activeDictionary ? "active" : ""} key={item.dictionary_key} onClick={() => { setActiveDictionary(item.dictionary_key); setDictionaryEditor(null); }} type="button"><Braces size={16} /><span><strong>{item.name}</strong><small>{item.dictionary_key} · {item.items.length} 项</small></span></button>)}</aside>
      <section className="platform-data-panel">
        <header><div><span>DICTIONARY ITEMS</span><h2>{dictionary?.name ?? "字典项"}</h2></div>{dictionary && canManage ? <button className="button secondary compact" onClick={() => setDictionaryEditor(createNewDictionaryEditor(dictionary))} type="button"><Plus size={14} />新增</button> : null}</header>
        <div className="platform-table-wrap"><table><thead><tr><th>键</th><th>名称</th><th>值</th><th>排序</th><th>状态</th><th>版本</th><th>操作</th></tr></thead><tbody>{dictionary?.items.map((item) => <tr key={item.item_key}><td><code>{item.item_key}</code></td><td>{item.label}</td><td><code>{displayValue(item.value)}</code></td><td>{item.sort_order}</td><td><StatusBadge value={activeStatus(item.status)} /></td><td>r{item.revision}</td><td><button aria-label="编辑字典项" className="platform-icon-button" disabled={!canManage} onClick={() => setDictionaryEditor(createDictionaryEditor(dictionary, item))} title="编辑" type="button"><Pencil size={14} /></button></td></tr>)}</tbody></table>{dictionary?.items.length ? null : <div className="platform-empty-state"><DatabaseZap size={23} /><strong>当前字典没有数据项</strong></div>}</div>
        {dictionaryEditor ? <ConfigEditor busy={saving} onClose={() => setDictionaryEditor(null)} title={dictionaryEditor.isNew ? "新增字典项" : dictionaryEditor.itemKey} version={dictionaryEditor.revision ? `r${dictionaryEditor.revision}` : "NEW"}>
          <label><span>字典项键</span><input disabled={!dictionaryEditor.isNew} onChange={(event) => setDictionaryEditor({ ...dictionaryEditor, itemKey: event.target.value })} value={dictionaryEditor.itemKey} /></label>
          <label><span>名称</span><input onChange={(event) => setDictionaryEditor({ ...dictionaryEditor, label: event.target.value })} value={dictionaryEditor.label} /></label>
          <label><span>值</span><input onChange={(event) => setDictionaryEditor({ ...dictionaryEditor, value: event.target.value })} value={dictionaryEditor.value} /></label>
          <label><span>排序</span><input min="0" onChange={(event) => setDictionaryEditor({ ...dictionaryEditor, sortOrder: event.target.value })} type="number" value={dictionaryEditor.sortOrder} /></label>
          <label><span>状态</span><select onChange={(event) => setDictionaryEditor({ ...dictionaryEditor, status: event.target.value })} value={dictionaryEditor.status}><option value="active">启用</option><option value="inactive">停用</option></select></label>
          <label className="platform-wide-field"><span>变更原因</span><input onChange={(event) => setDictionaryEditor({ ...dictionaryEditor, reason: event.target.value })} value={dictionaryEditor.reason} /></label>
          <footer><button className="button secondary" onClick={() => setDictionaryEditor(null)} type="button">取消</button><button className="button primary" disabled={saving || dictionaryEditor.reason.trim().length < 3 || dictionaryEditor.itemKey.trim().length < 1 || dictionaryEditor.label.trim().length < 1} onClick={() => void saveDictionaryItem()} type="button">{saving ? <LoaderCircle className="spinning" size={15} /> : <Save size={15} />}保存</button></footer>
        </ConfigEditor> : null}
      </section>
    </div>
  </div>;
}

function ConfigEditor({ children, title, version, onClose, busy }: { children: React.ReactNode; title: string; version: string; onClose: () => void; busy: boolean }) { return <Dialog busy={busy} className="platform-config-dialog" eyebrow={`CONFIGURATION · ${version}`} onClose={onClose} size="medium" title={title}><div className="platform-form-grid overlay-form-grid">{children}</div></Dialog>; }
function activeStatus(status: string) { return { label: status === "active" ? "启用" : "停用", tone: status === "active" ? "positive" as const : "neutral" as const }; }
function displayValue(value: unknown): string { return typeof value === "string" ? value : JSON.stringify(value); }
function parseValue(value: string, valueType: string): unknown { if (valueType === "integer") { const parsed = Number.parseInt(value, 10); if (Number.isNaN(parsed)) throw new Error("参数值必须是整数"); return parsed; } if (valueType === "number") { const parsed = Number(value); if (Number.isNaN(parsed)) throw new Error("参数值必须是数字"); return parsed; } if (valueType === "boolean") { if (!["true", "false"].includes(value.toLocaleLowerCase())) throw new Error("参数值必须是 true 或 false"); return value.toLocaleLowerCase() === "true"; } if (valueType === "json") return JSON.parse(value); return value; }
function parseLooseValue(value: string): unknown { try { return JSON.parse(value); } catch { return value; } }
function createParameterEditor(item: PlatformParameter): ParameterEditor { return { key: item.parameter_key, revision: item.revision, valueType: item.value_type, value: displayValue(item.value), status: item.status, reason: "" }; }
function createDictionaryEditor(dictionary: PlatformDictionary, item: DictionaryItem): DictionaryEditor { return { dictionaryKey: dictionary.dictionary_key, itemKey: item.item_key, revision: item.revision, label: item.label, value: displayValue(item.value), sortOrder: String(item.sort_order), status: item.status, reason: "", isNew: false }; }
function createNewDictionaryEditor(dictionary: PlatformDictionary): DictionaryEditor { return { dictionaryKey: dictionary.dictionary_key, itemKey: "", revision: null, label: "", value: "", sortOrder: String((dictionary.items.at(-1)?.sort_order ?? 0) + 10), status: "active", reason: "", isNew: true }; }
function requestKey(prefix: string): string { return `${prefix}-${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now()}`; }
function ConfigState({ title }: { title: string }) { return <div className="platform-page-state"><LoaderCircle className="spinning" size={27} /><strong>{title}</strong></div>; }
