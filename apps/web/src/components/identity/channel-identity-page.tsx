"use client";

import {
  Ban,
  Check,
  CircleAlert,
  Fingerprint,
  Link2,
  LoaderCircle,
  Pencil,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Unlink,
  UserRoundSearch,
  X
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { ConfirmDialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import {
  channelBindingStatusLabel,
  filterChannelIdentities,
  type ChannelIdentityFilters
} from "@/lib/channel-identity-query";
import type {
  ChannelIdentityAdminResponse,
  ChannelIdentityConfigureRequest,
  ChannelIdentityItem,
  ChannelIdentityMutationResponse
} from "@/lib/channel-identity-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

interface ChannelEditor {
  identityId: string;
  expectedVersion: number;
  principalId: string;
  status: "active" | "suspended";
  reason: string;
  requestKey: string;
}

export function ChannelIdentityPage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<ChannelIdentityAdminResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editor, setEditor] = useState<ChannelEditor | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [filters, setFilters] = useState<ChannelIdentityFilters>({ channel: "all", status: "all", query: "" });
  const canManage = can("identity.user.manage");

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/identity/admin/channel-identities`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "无法读取渠道身份"));
    const result = (await response.json()) as ChannelIdentityAdminResponse;
    setData(result);
    setEditor((current) => {
      if (!current) return null;
      const next = result.items.find((item) => item.id === current.identityId);
      return next ? createEditor(next, current.reason) : null;
    });
  }, [roleId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "渠道身份读取失败"))
      .finally(() => setLoading(false));
  }, [load]);

  const filtered = useMemo(
    () => filterChannelIdentities(data?.items ?? [], filters),
    [data?.items, filters]
  );
  const channels = useMemo(
    () => Array.from(new Map((data?.items ?? []).map((item) => [item.channel_key, item.channel_label]))),
    [data?.items]
  );
  const selected = data?.items.find((item) => item.id === editor?.identityId) ?? null;

  async function saveConfiguration(): Promise<void> {
    if (!editor || !canManage) return;
    setSaving(true);
    setError(null);
    try {
      const payload: ChannelIdentityConfigureRequest = {
        schema_version: 1,
        client_request_key: editor.requestKey,
        expected_version: editor.expectedVersion,
        principal_id: editor.principalId || null,
        status: editor.status,
        reason: editor.reason.trim()
      };
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/identity/admin/channel-identities/${encodeURIComponent(editor.identityId)}/configuration`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
          body: JSON.stringify(payload)
        }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "渠道身份配置失败"));
      const result = (await response.json()) as ChannelIdentityMutationResponse;
      notify({ title: "渠道身份配置已生效", description: `${result.identity.observed_display_name ?? result.identity.external_identity_hint} · ${channelBindingStatusLabel(result.identity.binding_status)}`, tone: "success" });
      setConfirmOpen(false);
      await load();
    } catch (reason: unknown) {
      notify({ title: "渠道身份配置失败", description: reason instanceof Error ? reason.message : "请检查绑定关系后重试", tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <ChannelState title="正在读取渠道身份" />;
  if (!data) return <ChannelState error title={error ?? "渠道身份暂不可用"} />;

  return <div className="channel-identity-page">
    <PageHeader
      actions={<button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新</button>}
      eyebrow="CHANNEL IDENTITY"
      meta={`${data.stats.total} 个外部身份`}
      title="渠道身份"
    />
    {error ? <InlineCallout description={error} title="配置未完成" tone="critical" /> : null}
    <ChannelStats data={data} />
    <section className="channel-filter-bar" aria-label="渠道身份筛选">
      <label><span>渠道</span><select onChange={(event) => setFilters((current) => ({ ...current, channel: event.target.value }))} value={filters.channel}><option value="all">全部渠道</option>{channels.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label><span>绑定状态</span><select onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value as ChannelIdentityFilters["status"] }))} value={filters.status}><option value="all">全部状态</option><option value="unknown">未绑定</option><option value="bound">已绑定</option><option value="suspended">已停用</option></select></label>
      <label className="channel-query-field"><span>身份检索</span><div><Search size={15} /><input onChange={(event) => setFilters((current) => ({ ...current, query: event.target.value }))} placeholder="姓名、账号或指纹" value={filters.query} /></div></label>
    </section>
    <div className="channel-identity-workspace">
      <ChannelDirectory canManage={canManage} items={filtered} onSelect={(item) => setEditor(createEditor(item))} selectedId={editor?.identityId ?? null} />
      <ChannelConfigurationEditor
        accounts={data.accounts}
        editor={editor}
        identity={selected}
        onCancel={() => setEditor(null)}
        onChange={setEditor}
        onSave={() => setConfirmOpen(true)}
        reservedPrincipalIds={(data.items ?? [])
          .filter((item) => item.id !== selected?.id && item.channel_key === selected?.channel_key && item.external_tenant_key === selected?.external_tenant_key)
          .flatMap((item) => item.principal_id ? [item.principal_id] : [])}
        saving={saving}
      />
    </div>
    {confirmOpen && editor && selected ? <ConfirmDialog busy={saving} confirmLabel={channelChangeCopy(selected, editor).confirmLabel} description={channelChangeCopy(selected, editor).description} detail={channelChangeCopy(selected, editor).detail} onCancel={() => setConfirmOpen(false)} onConfirm={() => void saveConfiguration()} title={channelChangeCopy(selected, editor).title} tone={channelChangeCopy(selected, editor).tone} /> : null}
    <ChannelEvents data={data} />
  </div>;
}

function ChannelStats({ data }: { data: ChannelIdentityAdminResponse }) {
  const items = [
    ["外部身份", data.stats.total, <Fingerprint key="total" size={16} />],
    ["已绑定", data.stats.bound, <Link2 key="bound" size={16} />],
    ["未绑定", data.stats.unknown, <UserRoundSearch key="unknown" size={16} />],
    ["已停用", data.stats.suspended, <Ban key="suspended" size={16} />],
    ["近 24 小时", data.stats.seen_last_24h, <Check key="recent" size={16} />]
  ];
  return <section className="channel-stat-band" aria-label="渠道身份统计">{items.map(([label, value, icon]) => <article key={String(label)}><span>{icon}{label}</span><strong>{value}</strong></article>)}</section>;
}

function ChannelDirectory({ canManage, items, onSelect, selectedId }: { canManage: boolean; items: ChannelIdentityItem[]; onSelect: (item: ChannelIdentityItem) => void; selectedId: string | null }) {
  return <section className="channel-directory-panel">
    <header><div><span>IDENTITY DIRECTORY</span><h2>外部身份目录</h2></div><em>{items.length} 条</em></header>
    <div className="channel-table-wrap"><table><thead><tr><th>外部身份</th><th>渠道 / 租户</th><th>内部账号</th><th>最近出现</th><th>状态</th><th aria-label="操作" /></tr></thead><tbody>{items.map((item) => <tr className={selectedId === item.id ? "active" : ""} key={item.id}><td><strong>{item.observed_display_name ?? "未知名称"}</strong><small>{item.external_identity_hint} · {item.external_identity_fingerprint}</small></td><td><strong>{item.channel_label}</strong><small>{item.external_tenant_key}</small></td><td>{item.principal_name ? <><strong>{item.principal_name}</strong><small>{item.principal_account_key}</small></> : <span className="channel-empty-binding">未绑定</span>}</td><td><strong>{formatTime(item.last_seen_at)}</strong><small>v{item.version}</small></td><td><ChannelStatus status={item.binding_status} /></td><td><button aria-label={`配置 ${item.observed_display_name ?? item.external_identity_hint}`} className="channel-icon-button" disabled={!canManage} onClick={() => onSelect(item)} title="配置" type="button"><Pencil size={15} /></button></td></tr>)}</tbody></table>{items.length ? null : <div className="channel-empty-state"><UserRoundSearch size={22} /><strong>没有匹配的渠道身份</strong></div>}</div>
  </section>;
}

function ChannelConfigurationEditor({ accounts, editor, identity, onCancel, onChange, onSave, reservedPrincipalIds, saving }: { accounts: ChannelIdentityAdminResponse["accounts"]; editor: ChannelEditor | null; identity: ChannelIdentityItem | null; onCancel: () => void; onChange: (editor: ChannelEditor | null) => void; onSave: () => void; reservedPrincipalIds: string[]; saving: boolean }) {
  if (!editor || !identity) return <aside className="channel-config-panel empty"><Fingerprint size={27} /><strong>选择一个渠道身份</strong></aside>;
  const account = accounts.find((item) => item.principal_id === editor.principalId);
  const reservedPrincipals = new Set(reservedPrincipalIds);
  return <aside className="channel-config-panel">
    <header><div><span>CONFIGURATION · v{identity.version}</span><h2>{identity.observed_display_name ?? identity.external_identity_hint}</h2></div><button aria-label="关闭配置" className="channel-icon-button" onClick={onCancel} title="关闭" type="button"><X size={16} /></button></header>
    <dl className="channel-config-identity"><div><dt>渠道</dt><dd>{identity.channel_label}</dd></div><div><dt>身份提示</dt><dd>{identity.external_identity_hint}</dd></div><div><dt>身份指纹</dt><dd><code>{identity.external_identity_fingerprint}</code></dd></div><div><dt>最近出现</dt><dd>{formatTime(identity.last_seen_at)}</dd></div></dl>
    <label><span>内部账号</span><select onChange={(event) => onChange({ ...editor, principalId: event.target.value })} value={editor.principalId}><option value="">未绑定</option>{accounts.map((item) => <option disabled={reservedPrincipals.has(item.principal_id)} key={item.principal_id} value={item.principal_id}>{item.display_name} · {item.organization} / {item.position}{reservedPrincipals.has(item.principal_id) ? " · 已绑定" : ""}</option>)}</select></label>
    {account ? <div className="channel-account-summary"><strong>{account.display_name}</strong><span>{account.login_name}</span><small>{account.organization} · {account.position}</small></div> : null}
    <fieldset className="channel-status-control"><legend>渠道状态</legend><div><button className={editor.status === "active" ? "active" : ""} onClick={() => onChange({ ...editor, status: "active" })} type="button">启用</button><button className={editor.status === "suspended" ? "active warning" : ""} onClick={() => onChange({ ...editor, status: "suspended" })} type="button">停用</button></div></fieldset>
    <label><span>变更原因</span><textarea maxLength={500} onChange={(event) => onChange({ ...editor, reason: event.target.value })} rows={3} value={editor.reason} /></label>
    <footer><button className="button secondary" onClick={onCancel} type="button"><X size={15} />取消</button><button className="button primary" disabled={saving || editor.reason.trim().length < 3 || (editor.principalId === (identity.principal_id ?? "") && editor.status === (identity.binding_status === "suspended" ? "suspended" : "active"))} onClick={onSave} type="button">{saving ? <LoaderCircle className="spinning" size={15} /> : editor.principalId ? <Save size={15} /> : <Unlink size={15} />}{saving ? "保存中" : "保存配置"}</button></footer>
  </aside>;
}

function ChannelEvents({ data }: { data: ChannelIdentityAdminResponse }) {
  return <section className="channel-event-panel"><header><div><span>BINDING EVENTS</span><h2>绑定变更</h2></div><em>{data.recent_events.length} 条</em></header><div className="channel-event-list">{data.recent_events.map((event) => <article key={event.id}><div><strong>{eventLabel(event.event_type)}</strong><small>{formatTime(event.occurred_at)} · {event.actor_name}</small></div><span>{event.before_principal_name ?? "未绑定"} → {event.after_principal_name ?? "未绑定"}</span><p>{event.reason}</p><code>{event.request_id}</code></article>)}{data.recent_events.length ? null : <div className="channel-empty-state"><ShieldCheck size={21} /><strong>暂无绑定变更</strong></div>}</div></section>;
}

function ChannelStatus({ status }: { status: ChannelIdentityItem["binding_status"] }) {
  return <StatusBadge value={{ label: channelBindingStatusLabel(status), tone: status === "bound" ? "positive" : status === "suspended" ? "critical" : "warning" }} />;
}

function channelChangeCopy(identity: ChannelIdentityItem, editor: ChannelEditor): { title: string; description: string; detail: string; confirmLabel: string; tone: "warning" | "danger" | "primary" } {
  const name = identity.observed_display_name ?? identity.external_identity_hint;
  if (identity.principal_id && !editor.principalId) return { title: "解绑渠道身份", description: `确认解除 ${name} 的内部账号绑定？`, detail: "下一条渠道消息将无法解析为当前内部主体。", confirmLabel: "确认解绑", tone: "danger" };
  if (identity.principal_id && editor.principalId !== identity.principal_id) return { title: "换绑渠道身份", description: `确认变更 ${name} 对应的内部账号？`, detail: "新消息将按新的内部主体、角色和数据范围重新授权。", confirmLabel: "确认换绑", tone: "warning" };
  if (editor.status === "suspended" && identity.binding_status !== "suspended") return { title: "停用渠道身份", description: `确认停用 ${name}？`, detail: "停用期间该外部身份不能建立有效企业会话。", confirmLabel: "确认停用", tone: "danger" };
  if (!identity.principal_id && editor.principalId) return { title: "绑定渠道身份", description: `确认将 ${name} 绑定到所选内部账号？`, detail: "后续请求仍会按内部账号的当前权限和范围重新授权。", confirmLabel: "确认绑定", tone: "primary" };
  return { title: "保存渠道配置", description: `确认更新 ${name} 的渠道状态？`, detail: "变更将写入渠道身份事件和统一审计。", confirmLabel: "确认保存", tone: "warning" };
}

function createEditor(identity: ChannelIdentityItem, reason = ""): ChannelEditor {
  return { identityId: identity.id, expectedVersion: identity.version, principalId: identity.principal_id ?? "", status: identity.binding_status === "suspended" ? "suspended" : "active", reason, requestKey: requestKey() };
}

function requestKey(): string {
  const token = typeof globalThis.crypto?.randomUUID === "function" ? globalThis.crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return `channel-identity-${token}`;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function eventLabel(value: string): string {
  const labels: Record<string, string> = { "channel.identity.bound": "绑定", "channel.identity.rebound": "换绑", "channel.identity.unbound": "解绑", "channel.identity.suspended": "停用", "channel.identity.reactivated": "启用", "channel.identity.configured": "配置" };
  return labels[value] ?? value;
}

function ChannelState({ error = false, title }: { error?: boolean; title: string }) {
  return <div className={`channel-page-state ${error ? "error" : ""}`}>{error ? <CircleAlert size={27} /> : <LoaderCircle className="spinning" size={27} />}<strong>{title}</strong></div>;
}
