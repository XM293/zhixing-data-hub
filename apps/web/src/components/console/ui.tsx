"use client";

import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  ExternalLink,
  FileText,
  LoaderCircle,
  LockKeyhole,
  Minus,
  RefreshCcw,
  SearchX,
  TriangleAlert,
  X
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import type {
  DashboardItem,
  MetricCard,
  StatusValue,
  TablePageData,
  Tone
} from "@/lib/experience-types";
import { useExperience } from "@/demo/experience-provider";

export function PageHeader({
  eyebrow,
  title,
  meta,
  actions
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  meta?: string;
  actions?: React.ReactNode;
}) {
  const visibleEyebrow = eyebrow && /[\u3400-\u9fff]/.test(eyebrow) ? eyebrow : null;
  return (
    <header className="page-header">
      <div className="page-heading-copy">
        {visibleEyebrow ? <p className="page-eyebrow">{visibleEyebrow}</p> : null}
        <div className="page-title-row">
          <h1>{title}</h1>
          {meta ? <span className="page-meta">{meta}</span> : null}
        </div>
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function StatusBadge({ value }: { value: StatusValue }) {
  return <span className={`status-badge ${value.tone}`}>{value.label}</span>;
}

export function MetricStrip({ metrics }: { metrics: MetricCard[] }) {
  return (
    <section className="metric-strip" aria-label="关键指标">
      {metrics.map((metric) => {
        const TrendIcon = metric.change?.startsWith("+")
          ? ArrowUpRight
          : metric.change?.startsWith("-")
            ? ArrowDownRight
            : Minus;
        return (
          <div className="metric-cell" key={metric.key}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <div className={`metric-change ${metric.tone}`}>
              {metric.change ? <TrendIcon aria-hidden="true" size={14} /> : null}
              {metric.change ? <b>{metric.change}</b> : null}
              <small>{metric.comparison}</small>
            </div>
          </div>
        );
      })}
    </section>
  );
}

export function Surface({
  title,
  meta,
  action,
  children,
  className = ""
}: {
  title: string;
  meta?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`surface ${className}`}>
      <header className="surface-header">
        <div>
          <h2>{title}</h2>
          {meta ? <p>{meta}</p> : null}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

export function WorkList({ items }: { items: DashboardItem[] }) {
  if (items.length === 0) {
    return <EmptyState compact title="当前没有待处理事项" description="新的事项会自动出现在这里。" />;
  }
  return (
    <div className="work-list">
      {items.map((item) => (
        <Link className="work-row" href={item.href} key={item.id}>
          <span className={`work-indicator ${item.tone}`} aria-hidden="true" />
          <div className="work-copy">
            <div>
              <strong>{item.title}</strong>
              <StatusBadge value={{ label: item.status, tone: item.tone }} />
            </div>
            <p>{item.description}</p>
            <small>{item.meta}</small>
          </div>
          <ChevronRight aria-hidden="true" size={17} />
        </Link>
      ))}
    </div>
  );
}

export function InlineCallout({
  tone,
  title,
  description
}: {
  tone: Tone;
  title: string;
  description: string;
}) {
  const Icon = tone === "critical" ? TriangleAlert : tone === "positive" ? CheckCircle2 : CircleAlert;
  return (
    <div className={`inline-callout ${tone}`}>
      <Icon aria-hidden="true" size={18} />
      <div>
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
    </div>
  );
}

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return <span className="field-error" id={id} role="alert">{message}</span>;
}

type PageState = "normal" | "loading" | "empty" | "error";

export function GenericTablePage({
  page,
  extraAction
}: {
  page: TablePageData;
  extraAction?: React.ReactNode;
}) {
  const [pageState, setPageState] = useState<PageState>("normal");
  return (
    <div className="page-stack">
      <PageHeader
        actions={extraAction}
        description={page.description}
        eyebrow={page.eyebrow}
        meta={`更新于 ${page.updatedAt}`}
        title={page.title}
      />
      {page.callout ? <InlineCallout {...page.callout} /> : null}
      {page.metrics ? <MetricStrip metrics={page.metrics} /> : null}
      <Surface
        action={
          <label className="state-select">
            <span>页面状态</span>
            <select onChange={(event) => setPageState(event.target.value as PageState)} value={pageState}>
              <option value="normal">正常数据</option>
              <option value="loading">加载中</option>
              <option value="empty">空数据</option>
              <option value="error">请求失败</option>
            </select>
          </label>
        }
        meta={`${page.rows.length} 条业务记录`}
        title="数据列表"
      >
        {pageState === "normal" ? <DataTable page={page} /> : null}
        {pageState === "loading" ? <LoadingState /> : null}
        {pageState === "empty" ? (
          <EmptyState title="当前筛选条件下没有数据" description="调整筛选条件或等待下一次数据更新。" />
        ) : null}
        {pageState === "error" ? (
          <ErrorState onRetry={() => setPageState("normal")} />
        ) : null}
      </Surface>
    </div>
  );
}

export function DataTable({ page }: { page: TablePageData }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {page.columns.map((column) => (
              <th className={column.align === "right" ? "align-right" : ""} key={column.key}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {page.rows.map((row) => (
            <tr key={row.id}>
              {page.columns.map((column, index) => (
                <td className={column.align === "right" ? "align-right" : ""} key={column.key} data-label={column.label}>
                  {column.key === "status" && row.status ? (
                    <StatusBadge value={row.status} />
                  ) : index === 0 && row.href ? (
                    <Link className="table-primary-link" href={row.href}>
                      {row.cells[column.key]}
                      <ExternalLink aria-hidden="true" size={13} />
                    </Link>
                  ) : (
                    row.cells[column.key] ?? "—"
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EvidenceList({ items }: { items: Array<{ label: string; detail: string }> }) {
  return (
    <div className="evidence-list">
      {items.map((item) => (
        <div className="evidence-row" key={`${item.label}-${item.detail}`}>
          <FileText aria-hidden="true" size={17} />
          <div>
            <strong>{item.label}</strong>
            <span>{item.detail}</span>
          </div>
          <ExternalLink aria-hidden="true" size={14} />
        </div>
      ))}
    </div>
  );
}

export function Statement({
  label,
  tone,
  children
}: {
  label: string;
  tone: Tone;
  children: React.ReactNode;
}) {
  return (
    <div className={`statement ${tone}`}>
      <span>{label}</span>
      <p>{children}</p>
    </div>
  );
}

export function PermissionDenied(_props: { roleName: string }) {
  return (
    <div className="centered-state">
      <LockKeyhole aria-hidden="true" size={28} />
      <p className="page-eyebrow">访问受限</p>
      <h1>无权访问</h1>
      <p>当前账号无权访问此页面。</p>
      <Link className="button secondary" href="/console">
        返回工作台
      </Link>
    </div>
  );
}

export function NotFoundState() {
  return (
    <div className="centered-state">
      <SearchX aria-hidden="true" size={28} />
      <p className="page-eyebrow">页面未找到</p>
      <h1>页面不存在</h1>
      <p>页面不存在或地址已变更。</p>
      <Link className="button secondary" href="/console">
        返回工作台
      </Link>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  compact = false
}: {
  title: string;
  description: string;
  compact?: boolean;
}) {
  return (
    <div className={`empty-view ${compact ? "compact" : ""}`}>
      <SearchX aria-hidden="true" size={22} />
      <strong>{title}</strong>
      <span>{description}</span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="loading-view" role="status">
      <LoaderCircle aria-hidden="true" size={22} />
      <span>正在读取业务数据…</span>
      <div className="skeleton-lines" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="error-view" role="alert">
      <TriangleAlert aria-hidden="true" size={23} />
      <div>
        <strong>暂时无法读取数据</strong>
        <span>请求失败，最近成功数据时间为 2026-08-25 09:22。</span>
      </div>
      <button className="button secondary" onClick={onRetry} type="button">
        <RefreshCcw aria-hidden="true" size={15} />
        重试
      </button>
    </div>
  );
}

export function MetaGrid({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <dl className="meta-grid">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Timeline({
  items
}: {
  items: Array<{ title: string; description: string; meta: string; tone: Tone }>;
}) {
  return (
    <div className="timeline">
      {items.map((item) => (
        <div className="timeline-item" key={`${item.title}-${item.meta}`}>
          <span className={`timeline-dot ${item.tone}`} aria-hidden="true" />
          <div>
            <strong>{item.title}</strong>
            <p>{item.description}</p>
            <small>
              <Clock3 aria-hidden="true" size={13} />
              {item.meta}
            </small>
          </div>
        </div>
      ))}
    </div>
  );
}

export function CapabilityNote() {
  return null;
}

export function InlineLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link className="inline-link" href={href}>
      {children}
      <ArrowRight aria-hidden="true" size={15} />
    </Link>
  );
}

export function CyberDrawer({
  isOpen,
  onClose,
  title,
  children,
  footer
}: {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  if (!isOpen) return null;
  return (
    <>
      <div className="cyber-drawer-backdrop" onClick={onClose} />
      <aside className="cyber-drawer">
        <div className="cyber-drawer-header">
          <h3>{title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭抽屉"
            style={{
              background: "transparent",
              border: "none",
              color: "#94a3b8",
              cursor: "pointer",
              padding: "4px",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center"
            }}
          >
            <X size={18} />
          </button>
        </div>
        <div className="cyber-drawer-body">{children}</div>
        {footer ? <div className="cyber-drawer-footer">{footer}</div> : null}
      </aside>
    </>
  );
}

export function FinancialKpiCard({
  label,
  value,
  badgeText,
  badgeTone = "green",
  hint,
  cardTone = "blue"
}: {
  label: string;
  value: string;
  badgeText?: string;
  badgeTone?: "green" | "gold" | "purple";
  hint?: string;
  cardTone?: "blue" | "green" | "gold" | "purple";
}) {
  return (
    <div className={`financial-kpi-card tone-${cardTone}`}>
      <div className="financial-kpi-header">
        <span className="financial-kpi-label">{label}</span>
        {badgeText ? (
          <span className={`financial-kpi-badge ${badgeTone}`}>{badgeText}</span>
        ) : null}
      </div>
      <div className="financial-kpi-value">{value}</div>
      {hint ? <div className="financial-kpi-hint">{hint}</div> : null}
    </div>
  );
}
