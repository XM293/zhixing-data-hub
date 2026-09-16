"use client";

import { Bell, BellRing, CheckCheck, CircleAlert, ExternalLink, LoaderCircle, RefreshCw, Send } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Dialog, useNotifications } from "@/components/console/interaction";
import { InlineCallout, PageHeader, StatusBadge } from "@/components/console/ui";
import { useExperience } from "@/demo/experience-provider";
import { apiFetch } from "@/lib/api-client";
import { apiErrorMessage } from "@/lib/api-error";
import type { AccessGovernanceResponse, NotificationInboxResponse, NotificationItem, PrincipalOption } from "@/lib/platform-admin-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function NotificationInboxPage() {
  const { can, roleId } = useExperience();
  const { notify } = useNotifications();
  const [data, setData] = useState<NotificationInboxResponse | null>(null);
  const [status, setStatus] = useState("all");
  const [category, setCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [publisherOpen, setPublisherOpen] = useState(false);
  const [recipients, setRecipients] = useState<PrincipalOption[]>([]);
  const [recipientId, setRecipientId] = useState("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [publishCategory, setPublishCategory] = useState("system");
  const [severity, setSeverity] = useState("info");
  const [route, setRoute] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/notifications`, {
      cache: "no-store",
      headers: { "X-Zhixing-Demo-Actor": roleId }
    });
    if (!response.ok) throw new Error(await apiErrorMessage(response, "消息读取失败"));
    setData((await response.json()) as NotificationInboxResponse);
    if (can("notification.publish")) {
      const recipientResponse = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/access-governance`, { cache: "no-store", headers: { "X-Zhixing-Demo-Actor": roleId } });
      if (recipientResponse.ok) {
        const result = (await recipientResponse.json()) as AccessGovernanceResponse;
        setRecipients(result.principals);
        setRecipientId((current) => current || result.principals[0]?.id || "");
      }
    }
  }, [can, roleId]);

  useEffect(() => {
    setLoading(true);
    load()
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "消息读取失败"))
      .finally(() => setLoading(false));
  }, [load]);

  const categories = useMemo(
    () => Array.from(new Set((data?.items ?? []).map((item) => item.category))).sort(),
    [data?.items]
  );
  const items = useMemo(
    () => (data?.items ?? []).filter((item) =>
      (status === "all" || item.status === status) &&
      (category === "all" || item.category === category)
    ),
    [category, data?.items, status]
  );

  async function setRead(item: NotificationItem, read: boolean): Promise<void> {
    setSavingId(item.id);
    setError(null);
    try {
      const response = await apiFetch(
        `${API_BASE_URL}/api/v1/platform/notifications/${encodeURIComponent(item.id)}/read`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
          body: JSON.stringify({ schema_version: 1, read })
        }
      );
      if (!response.ok) throw new Error(await apiErrorMessage(response, "消息状态更新失败"));
      await load();
    } catch (reason: unknown) {
      notify({ title: "消息状态更新失败", description: reason instanceof Error ? reason.message : "请重试", tone: "error" });
    } finally {
      setSavingId(null);
    }
  }

  async function publish(): Promise<void> {
    if (!recipientId || !can("notification.publish")) return;
    setPublishing(true); setError(null);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/v1/platform/admin/notifications`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Zhixing-Demo-Actor": roleId },
        body: JSON.stringify({ schema_version: 1, client_request_key: requestKey("notification"), reason: reason.trim(), principal_ids: [recipientId], category: publishCategory, title: title.trim(), body: body.trim(), severity, action_route: route.trim() || null, channels: ["inbox"] })
      });
      if (!response.ok) throw new Error(await apiErrorMessage(response, "消息发布失败"));
      notify({ title: "消息已发布", description: title.trim(), tone: "success" });
      setTitle(""); setBody(""); setRoute(""); setReason(""); setPublisherOpen(false); await load();
    } catch (reasonValue: unknown) { notify({ title: "消息发布失败", description: reasonValue instanceof Error ? reasonValue.message : "请检查输入后重试", tone: "error" }); }
    finally { setPublishing(false); }
  }

  if (loading && !data) return <PageState title="正在读取消息" />;

  return <div className="platform-control-page notification-inbox-page">
    <PageHeader
      actions={<div className="platform-header-actions"><button className="button secondary" onClick={() => void load()} type="button"><RefreshCw size={15} />刷新</button>{can("notification.publish") ? <button className="button primary" onClick={() => setPublisherOpen(true)} type="button"><Send size={15} />发布消息</button> : null}</div>}
      eyebrow="INBOX"
      meta={`${data?.stats.unread ?? 0} 条未读`}
      title="消息中心"
    />
    {error ? <InlineCallout description={error} title="操作未完成" tone="critical" /> : null}
    <section className="platform-stat-band" aria-label="消息统计">
      <Stat icon={<BellRing size={16} />} label="未读" value={data?.stats.unread ?? 0} />
      <Stat icon={<CheckCheck size={16} />} label="已读" value={data?.stats.read ?? 0} />
      <Stat icon={<CircleAlert size={16} />} label="严重" value={data?.stats.critical ?? 0} />
      <Stat icon={<Bell size={16} />} label="全部" value={data?.stats.total ?? 0} />
    </section>
    <section className="platform-filter-bar" aria-label="消息筛选">
      <label><span>状态</span><select onChange={(event) => setStatus(event.target.value)} value={status}><option value="all">全部状态</option><option value="unread">未读</option><option value="read">已读</option></select></label>
      <label><span>分类</span><select onChange={(event) => setCategory(event.target.value)} value={category}><option value="all">全部分类</option>{categories.map((item) => <option key={item} value={item}>{categoryLabel(item)}</option>)}</select></label>
    </section>
    {publisherOpen && can("notification.publish") ? <Dialog busy={publishing} className="notification-publisher-dialog" eyebrow="PUBLISH" footer={<><button className="button secondary" disabled={publishing} onClick={() => setPublisherOpen(false)} type="button">取消</button><button className="button primary" disabled={publishing || !recipientId || title.trim().length < 1 || body.trim().length < 1 || reason.trim().length < 3} onClick={() => void publish()} type="button">{publishing ? <LoaderCircle className="spinning" size={15} /> : <Send size={15} />}发布</button></>} onClose={() => setPublisherOpen(false)} size="medium" title="发布消息"><div className="platform-form-grid overlay-form-grid">
      <label><span>接收人</span><select onChange={(event) => setRecipientId(event.target.value)} value={recipientId}>{recipients.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.organization}</option>)}</select></label>
      <label><span>分类</span><select onChange={(event) => setPublishCategory(event.target.value)} value={publishCategory}><option value="system">平台运行</option><option value="approval">审批</option><option value="data-quality">数据质量</option></select></label>
      <label><span>级别</span><select onChange={(event) => setSeverity(event.target.value)} value={severity}><option value="info">提示</option><option value="success">完成</option><option value="warning">预警</option><option value="critical">严重</option></select></label>
      <label><span>业务路由</span><input onChange={(event) => setRoute(event.target.value)} value={route} /></label>
      <label className="platform-wide-field"><span>标题</span><input onChange={(event) => setTitle(event.target.value)} value={title} /></label>
      <label className="platform-wide-field"><span>正文</span><input onChange={(event) => setBody(event.target.value)} value={body} /></label>
      <label className="platform-wide-field"><span>发布原因</span><input onChange={(event) => setReason(event.target.value)} value={reason} /></label>
    </div></Dialog> : null}
    <section className="notification-list-panel">
      <header><div><span>MESSAGES</span><h2>消息列表</h2></div><em>{items.length} 条</em></header>
      <div className="notification-record-list">
        {items.map((item) => <article className={item.status === "unread" ? "unread" : ""} key={item.id}>
          <span className={`notification-severity ${item.severity}`} aria-hidden="true" />
          <div className="notification-copy">
            <div><strong>{item.title}</strong><StatusBadge value={notificationStatus(item)} /></div>
            <p>{item.body}</p>
            <small>{categoryLabel(item.category)} · {formatTime(item.created_at)} · {deliveryLabel(item.deliveries)}</small>
          </div>
          <div className="notification-actions">
            {item.action_route ? <Link aria-label="打开业务对象" className="platform-icon-button" href={item.action_route} title="打开"><ExternalLink size={15} /></Link> : null}
            <button aria-label={item.status === "unread" ? "标记已读" : "标记未读"} className="platform-icon-button" disabled={savingId === item.id} onClick={() => void setRead(item, item.status === "unread")} title={item.status === "unread" ? "标记已读" : "标记未读"} type="button">{savingId === item.id ? <LoaderCircle className="spinning" size={15} /> : <CheckCheck size={15} />}</button>
          </div>
        </article>)}
        {items.length ? null : <div className="platform-empty-state"><Bell size={23} /><strong>当前没有消息</strong></div>}
      </div>
    </section>
  </div>;
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return <article><span>{icon}{label}</span><strong>{value}</strong></article>;
}

function notificationStatus(item: NotificationItem) {
  return { label: item.status === "unread" ? "未读" : "已读", tone: item.status === "unread" ? "warning" as const : "neutral" as const };
}

function categoryLabel(value: string): string {
  return ({ system: "平台运行", approval: "审批", "data-quality": "数据质量" } as Record<string, string>)[value] ?? value;
}

function deliveryLabel(deliveries: Record<string, string>): string {
  const labels = Object.entries(deliveries).map(([channel, deliveryStatus]) => `${channelLabel(channel)} ${deliveryStatus === "delivered" ? "已送达" : "待投递"}`);
  return labels.join(" · ") || "站内";
}

function channelLabel(value: string): string {
  return ({ inbox: "站内", feishu: "飞书", wechat: "微信" } as Record<string, string>)[value] ?? value;
}

function requestKey(prefix: string): string { return `${prefix}-${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now()}`; }

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function PageState({ title }: { title: string }) {
  return <div className="platform-page-state"><LoaderCircle className="spinning" size={27} /><strong>{title}</strong></div>;
}
