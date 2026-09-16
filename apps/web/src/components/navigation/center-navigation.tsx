"use client";

import {
  Bot,
  Boxes,
  ChevronDown,
  ChevronRight,
  FileText,
  ChartNoAxesCombined,
  Database,
  Gauge,
  Headset,
  LayoutDashboard,
  ListChecks,
  MessagesSquare,
  RefreshCw,
  Scale,
  Settings2,
  ShieldCheck,
  Sparkles,
  type LucideIcon
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import type { CenterCatalog } from "@/lib/identity-types";
import type { NavigationSection } from "@/lib/experience-types";

const ICONS: Record<string, LucideIcon> = {
  "layout-dashboard": LayoutDashboard,
  gauge: Gauge,
  database: Database,
  "book-open": FileText,
  bot: Bot,
  sparkles: Sparkles,
  bell: MessagesSquare,
  "refresh-cw": RefreshCw,
  "shield-check": ShieldCheck,
  "calendar-check": ListChecks,
  "file-text": FileText,
  "file-check": ShieldCheck,
  "file-up": FileText,
  quote: MessagesSquare,
  send: ListChecks,
  "check-circle-2": ShieldCheck,
  "clipboard-check": ListChecks,
  brain: Bot,
  "sliders-horizontal": Settings2,
  "flask-conical": Bot,
  scale: Scale,
  "message-square-warning": MessagesSquare,
  fingerprint: ShieldCheck,
  "server-cog": Settings2,
  wrench: Settings2,
  "file-box": Database,
  "arrow-left-right": ListChecks,
  "user-round-cog": Settings2,
  "scroll-text": FileText,
  "messages-square": MessagesSquare,
  chart: ChartNoAxesCombined,
  "chart-no-axes-combined": ChartNoAxesCombined,
  "list-checks": ListChecks,
  headset: Headset,
  settings: Settings2,
  boxes: Boxes,
  "layers-3": Database,
  store: Boxes,
  warehouse: Boxes,
  "users-round": LayoutDashboard,
  "plug-zap": Settings2
};

const FALLBACK_GROUP_LABELS: Record<string, string> = {
  experience: "工作入口",
  insights: "经营管理",
  "data-foundation": "数据中心",
  "data-products": "数据产品",
  business: "业务中心",
  knowledge: "治理中心",
  governance: "治理中心",
  ai: "智能中心",
  platform: "平台中心"
};

const CORE_NAV_ITEMS = [
  {
    key: "cockpit",
    label: "数字孪生 · 驾驶舱",
    shortLabel: "经营驾驶舱",
    href: "/console",
    icon: Boxes,
    matches: (pathname: string) =>
      pathname === "/console" || pathname.startsWith("/console/spatial") || pathname.startsWith("/console/cockpit")
  },
  {
    key: "reconciliation",
    label: "经营对账中心",
    shortLabel: "经营对账",
    href: "/console/reconciliation",
    icon: Scale,
    matches: (pathname: string) =>
      pathname.startsWith("/console/reconciliation") || pathname.startsWith("/console/data/foundation/reconciliation")
  },
  {
    key: "assistant",
    label: "高管分身会议室",
    shortLabel: "高管分身",
    href: "/console/assistant",
    icon: Bot,
    matches: (pathname: string) =>
      pathname.startsWith("/console/assistant") || pathname.startsWith("/console/analysis/ask")
  }
];

const OPS_NAV_ITEM = {
  key: "settings",
  label: "系统运维管理",
  shortLabel: "系统运维",
  href: "/console/settings",
  icon: Settings2,
  matches: (pathname: string) =>
    pathname.startsWith("/console/settings") || pathname.startsWith("/console/admin")
};

export function CenterNavigation({
  catalog,
  fallback,
  activeSectionKey,
  pathname
}: {
  catalog: CenterCatalog | null;
  fallback: NavigationSection[];
  activeSectionKey: string;
  pathname: string;
}) {
  const isCore = CORE_NAV_ITEMS.some((item) => item.matches(pathname)) || OPS_NAV_ITEM.matches(pathname);
  const [showAdvanced, setShowAdvanced] = useState(!isCore);

  useEffect(() => {
    if (!isCore) {
      setShowAdvanced(true);
    }
  }, [isCore, pathname]);

  return (
    <>
      {/* 3 大核心业务入口 */}
      <div className="primary-nav-group">
        <span className="primary-nav-group-label">核心经营中枢</span>
        {CORE_NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = item.matches(pathname);
          return (
            <Link
              aria-current={active ? "page" : undefined}
              className={`primary-nav-link ${active ? "active" : ""}`}
              href={item.href}
              key={item.key}
            >
              <Icon aria-hidden="true" size={19} strokeWidth={1.8} />
              <span>{item.shortLabel}</span>
            </Link>
          );
        })}
      </div>

      {/* 1 个统一运维管理入口 */}
      <div className="primary-nav-group">
        <span className="primary-nav-group-label">平台运维</span>
        <Link
          aria-current={OPS_NAV_ITEM.matches(pathname) ? "page" : undefined}
          className={`primary-nav-link ${OPS_NAV_ITEM.matches(pathname) ? "active" : ""}`}
          href={OPS_NAV_ITEM.href}
          key={OPS_NAV_ITEM.key}
        >
          <OPS_NAV_ITEM.icon aria-hidden="true" size={19} strokeWidth={1.8} />
          <span>{OPS_NAV_ITEM.shortLabel}</span>
        </Link>
      </div>

      {/* 展开全部专业模块 (给需要深钻底层表单的管理员备用) */}
      <div
        className="primary-nav-group"
        style={{
          marginTop: "0.75rem",
          borderTop: "1px dashed var(--border-subtle, rgba(255, 255, 255, 0.08))",
          paddingTop: "0.5rem"
        }}
      >
        <button
          type="button"
          onClick={() => setShowAdvanced((prev) => !prev)}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            width: "100%",
            padding: "0.45rem 0.6rem",
            background: "transparent",
            border: "none",
            color: "var(--text-muted, #94a3b8)",
            fontSize: "0.78rem",
            cursor: "pointer",
            borderRadius: "6px"
          }}
        >
          <span>全部专业模块 ({catalog?.groups?.reduce((acc, g) => acc + g.items.length, 0) ?? 35}+)</span>
          {showAdvanced ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        {showAdvanced && (
          <div className="advanced-nav-sections" style={{ marginTop: "0.5rem" }}>
            {catalog?.groups.length ? (
              catalog.groups.map((group) => (
                <div className="primary-nav-group" key={group.key} style={{ marginTop: "0.5rem" }}>
                  <span className="primary-nav-group-label" style={{ fontSize: "0.72rem", opacity: 0.8 }}>
                    {group.label}
                  </span>
                  {group.items.map((item) => {
                    const Icon = ICONS[item.icon_key] ?? LayoutDashboard;
                    const active = centerMatchesPath(item.key, item.href, pathname);
                    return (
                      <Link
                        aria-current={active ? "page" : undefined}
                        className={`primary-nav-link ${active ? "active" : ""}`}
                        href={item.href}
                        key={item.key}
                      >
                        <Icon aria-hidden="true" size={18} strokeWidth={1.6} />
                        <span>{item.short_label}</span>
                      </Link>
                    );
                  })}
                </div>
              ))
            ) : (
              renderFallbackSections(fallback, activeSectionKey, pathname)
            )}
          </div>
        )}
      </div>
    </>
  );
}

function renderFallbackSections(
  fallback: NavigationSection[],
  activeSectionKey: string,
  pathname: string
) {
  const fallbackSections = fallback.flatMap((section) => {
    if (section.key !== "data") return [section];
    const foundationKeys = new Set(["sources", "sync-jobs", "entities", "metrics", "quality"]);
    const foundationItems = section.items.filter((item) => foundationKeys.has(item.key));
    const productItems = section.items.filter((item) => !foundationKeys.has(item.key));
    const sections: NavigationSection[] = [];
    if (foundationItems.length) {
      sections.push({
        ...section,
        key: "data-foundation",
        label: "数据基础",
        shortLabel: "数据基础",
        href: foundationItems[0]?.href ?? section.href,
        groupKey: "data-foundation",
        items: foundationItems
      });
    }
    if (productItems.length) {
      sections.push({
        ...section,
        key: "data-products",
        label: "数据产品",
        shortLabel: "数据产品",
        href: productItems[0]?.href ?? section.href,
        groupKey: "data-products",
        items: productItems
      });
    }
    return sections;
  });
  const grouped = new Map<string, NavigationSection[]>();
  for (const item of fallbackSections) {
    const key = item.groupKey ?? "platform";
    grouped.set(key, [...(grouped.get(key) ?? []), item]);
  }
  return (
    <>
      {[...grouped.entries()].map(([groupKey, items]) => (
        <div className="primary-nav-group" key={groupKey} style={{ marginTop: "0.5rem" }}>
          <span className="primary-nav-group-label" style={{ fontSize: "0.72rem", opacity: 0.8 }}>
            {FALLBACK_GROUP_LABELS[groupKey] ?? groupKey}
          </span>
          {items.map((item) => {
            const Icon = ICONS[item.iconKey] ?? LayoutDashboard;
            const active = centerMatchesPath(item.key, item.href, pathname) || item.key === activeSectionKey;
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={`primary-nav-link ${active ? "active" : ""}`}
                href={item.href}
                key={item.key}
              >
                <Icon aria-hidden="true" size={18} strokeWidth={1.6} />
                <span>{item.shortLabel}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </>
  );
}

function centerMatchesPath(centerKey: string, href: string, pathname: string): boolean {
  if (centerKey === "digital-twin") return pathname === "/console" || pathname.startsWith("/console/spatial");
  const legacyAliases: Record<string, string[]> = {
    "/console/data/foundation/sources": ["/console/data/sources"],
    "/console/data/foundation/sync-jobs": ["/console/data/sync-jobs"],
    "/console/data/foundation/entities": ["/console/data/entities"],
    "/console/data/foundation/metrics": ["/console/data/metrics"],
    "/console/data/foundation/quality": ["/console/data/quality"],
    "/console/data/products/commerce": ["/console/data/commerce"],
    "/console/data/products/customers": ["/console/data/customers"],
    "/console/reconciliation": ["/console/data/foundation/reconciliation"]
  };
  return [href, ...(legacyAliases[href] ?? [])].some(
    (candidate) => pathname === candidate || pathname.startsWith(`${candidate}/`)
  );
}
