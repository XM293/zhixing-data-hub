import {
  Bot,
  Boxes,
  FileText,
  ChartNoAxesCombined,
  Database,
  Gauge,
  Headset,
  LayoutDashboard,
  ListChecks,
  MessagesSquare,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Sparkles,
  type LucideIcon
} from "lucide-react";
import Link from "next/link";

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
  scale: ListChecks,
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
  if (catalog?.groups.length) {
    return (
      <>
        {catalog.groups.map((group) => (
          <div className="primary-nav-group" key={group.key}>
            <span className="primary-nav-group-label">{group.label}</span>
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
                  <Icon aria-hidden="true" size={19} strokeWidth={1.8} />
                  <span>{item.short_label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </>
    );
  }

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
        <div className="primary-nav-group" key={groupKey}>
          <span className="primary-nav-group-label">{FALLBACK_GROUP_LABELS[groupKey] ?? groupKey}</span>
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
                <Icon aria-hidden="true" size={19} strokeWidth={1.8} />
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
    "/console/data/products/customers": ["/console/data/customers"]
  };
  return [href, ...(legacyAliases[href] ?? [])].some(
    (candidate) => pathname === candidate || pathname.startsWith(`${candidate}/`)
  );
}
