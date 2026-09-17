"use client";

import {
  Bot,
  Boxes,
  Brain,
  ChevronDown,
  ChevronRight,
  Cpu,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  Headset,
  Layers,
  ListChecks,
  PlugZap,
  Quote,
  Scale,
  Settings2,
  ShieldCheck,
  Sparkles,
  Store,
  UsersRound,
  Wrench,
  type LucideIcon
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { CenterCatalog } from "@/lib/identity-types";
import type { NavigationSection } from "@/lib/experience-types";

export interface NavItemDef {
  key: string;
  label: string;
  shortLabel: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
  badgeTone?: "brand" | "amber" | "blue" | "neutral";
  matches: (pathname: string) => boolean;
}

export interface NavCenterDef {
  key: string;
  label: string;
  icon: LucideIcon;
  items: NavItemDef[];
}

export const FIVE_BUSINESS_CENTERS: NavCenterDef[] = [
  {
    key: "cockpit",
    label: "经营驾驶舱",
    icon: Gauge,
    items: [
      {
        key: "cockpit-overview",
        label: "全域态势驾驶舱",
        shortLabel: "全域态势",
        href: "/console/cockpit",
        icon: Gauge,
        badge: "实时",
        badgeTone: "brand",
        matches: (p) => p === "/console/cockpit" || p === "/console"
      },
      {
        key: "cockpit-spatial",
        label: "3D 空间数字孪生",
        shortLabel: "3D 孪生",
        href: "/console/spatial",
        icon: Boxes,
        badge: "3D",
        badgeTone: "blue",
        matches: (p) => p === "/console/spatial"
      },
      {
        key: "cockpit-briefs",
        label: "经营分析与简报",
        shortLabel: "经营简报",
        href: "/console/analysis/briefs",
        icon: FileText,
        matches: (p) => p.startsWith("/console/analysis")
      }
    ]
  },
  {
    key: "commerce",
    label: "跨境经营中心",
    icon: Store,
    items: [
      {
        key: "commerce-stores",
        label: "领星北美店铺看板",
        shortLabel: "领星店铺",
        href: "/console/commerce/stores",
        icon: Store,
        badge: "领星",
        badgeTone: "brand",
        matches: (p) => p === "/console/commerce/stores" || p === "/console/commerce"
      },
      {
        key: "commerce-reconciliation",
        label: "星云铁皮柜对账工作台",
        shortLabel: "铁皮柜对账",
        href: "/console/reconciliation",
        icon: Scale,
        badge: "真值",
        badgeTone: "amber",
        matches: (p) => p.startsWith("/console/reconciliation") || p === "/console/data/foundation/reconciliation"
      },
      {
        key: "commerce-facts",
        label: "订单与经营事实",
        shortLabel: "经营事实",
        href: "/console/data/products/commerce",
        icon: Database,
        matches: (p) => p.startsWith("/console/data/products/commerce") || p === "/console/data/commerce"
      },
      {
        key: "commerce-customers",
        label: "客户 360 档案",
        shortLabel: "客户 360",
        href: "/console/data/products/customers",
        icon: UsersRound,
        matches: (p) => p.startsWith("/console/data/products/customers") || p.startsWith("/console/data/customers")
      },
      {
        key: "commerce-cs",
        label: "智能客服接待",
        shortLabel: "智能客服",
        href: "/console/customer-service/conversations",
        icon: Headset,
        matches: (p) => p.startsWith("/console/customer-service")
      }
    ]
  },
  {
    key: "agents",
    label: "企业智能体",
    icon: Bot,
    items: [
      {
        key: "agents-assistant",
        label: "高管分身会议室",
        shortLabel: "高管分身",
        href: "/console/assistant",
        icon: Sparkles,
        badge: "CEO",
        badgeTone: "brand",
        matches: (p) => p.startsWith("/console/assistant") || p === "/console/analysis/ask"
      },
      {
        key: "agents-instances",
        label: "角色分身管理",
        shortLabel: "分身实例",
        href: "/console/twins/instances",
        icon: Bot,
        matches: (p) => p === "/console/twins/instances" || p === "/console/twins/templates"
      },
      {
        key: "agents-memories",
        label: "长期记忆审核",
        shortLabel: "记忆审核",
        href: "/console/twins/memories",
        icon: Brain,
        matches: (p) => p.startsWith("/console/twins/memories")
      },
      {
        key: "agents-evaluations",
        label: "分身回归评测",
        shortLabel: "回归评测",
        href: "/console/twins/evaluations",
        icon: FlaskConical,
        matches: (p) => p.startsWith("/console/twins/evaluations") || p === "/console/twins/test"
      },
      {
        key: "agents-actions",
        label: "决策行动台账",
        shortLabel: "行动台账",
        href: "/console/actions/work",
        icon: ListChecks,
        matches: (p) => p.startsWith("/console/actions")
      }
    ]
  },
  {
    key: "knowledge",
    label: "知识事实中心",
    icon: FileText,
    items: [
      {
        key: "knowledge-whitepaper",
        label: "铁皮柜白皮书与文档",
        shortLabel: "白皮书事实",
        href: "/console/knowledge/documents",
        icon: FileText,
        badge: "基准",
        badgeTone: "brand",
        matches: (p) => p === "/console/knowledge/documents" || p === "/console/knowledge"
      },
      {
        key: "knowledge-policies",
        label: "规则制度与版本",
        shortLabel: "制度规则",
        href: "/console/knowledge/policies",
        icon: ShieldCheck,
        matches: (p) => p.startsWith("/console/knowledge/policies")
      },
      {
        key: "knowledge-evidence",
        label: "事实链与证据引用",
        shortLabel: "证据引用",
        href: "/console/knowledge/evidence",
        icon: Quote,
        matches: (p) => p.startsWith("/console/knowledge/evidence")
      }
    ]
  },
  {
    key: "admin",
    label: "系统运维管理",
    icon: Settings2,
    items: [
      {
        key: "admin-users",
        label: "组织架构与账号",
        shortLabel: "用户权限",
        href: "/console/admin/users",
        icon: UsersRound,
        matches: (p) => p.startsWith("/console/admin/users") || p === "/console/admin/org" || p === "/console/admin/access"
      },
      {
        key: "admin-ai",
        label: "AI 运行控制",
        shortLabel: "AI 运行",
        href: "/console/admin/ai-runtime",
        icon: Cpu,
        matches: (p) => p.startsWith("/console/admin/ai-runtime")
      },
      {
        key: "admin-tools",
        label: "外部连接与工具",
        shortLabel: "外部工具",
        href: "/console/admin/tools",
        icon: PlugZap,
        matches: (p) => p.startsWith("/console/admin/tools")
      },
      {
        key: "admin-settings",
        label: "审计日志与配置",
        shortLabel: "系统配置",
        href: "/console/settings",
        icon: Wrench,
        matches: (p) => p.startsWith("/console/settings") || p.startsWith("/console/admin/audit")
      }
    ]
  }
];

export function CenterNavigation({
  pathname
}: {
  catalog?: CenterCatalog | null;
  fallback?: NavigationSection[];
  activeSectionKey?: string;
  pathname: string;
}) {
  // Track open state for each center accordion
  const [openCenters, setOpenCenters] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    for (const center of FIVE_BUSINESS_CENTERS) {
      const hasActive = center.items.some((item) => item.matches(pathname));
      initial[center.key] = hasActive || center.key === "cockpit";
    }
    return initial;
  });

  // Automatically expand center if navigation enters it
  useEffect(() => {
    for (const center of FIVE_BUSINESS_CENTERS) {
      if (center.items.some((item) => item.matches(pathname))) {
        setOpenCenters((prev) => ({ ...prev, [center.key]: true }));
      }
    }
  }, [pathname]);

  const toggleCenter = (centerKey: string) => {
    setOpenCenters((prev) => ({ ...prev, [centerKey]: !prev[centerKey] }));
  };

  return (
    <div className="modern-center-nav">
      {FIVE_BUSINESS_CENTERS.map((center) => {
        const CenterIcon = center.icon;
        const isOpen = !!openCenters[center.key];
        const isCenterActive = center.items.some((item) => item.matches(pathname));

        return (
          <div
            className={`nav-center-group ${isCenterActive ? "center-active" : ""}`}
            key={center.key}
          >
            <button
              aria-expanded={isOpen}
              className={`nav-center-header ${isCenterActive ? "header-active" : ""}`}
              onClick={() => toggleCenter(center.key)}
              type="button"
            >
              <div className="nav-center-title">
                <CenterIcon aria-hidden="true" size={17} strokeWidth={2} />
                <span>{center.label}</span>
              </div>
              <span className="nav-center-chevron">
                {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </span>
            </button>

            {isOpen && (
              <div className="nav-center-children">
                {center.items.map((item) => {
                  const ItemIcon = item.icon;
                  const isActive = item.matches(pathname);

                  return (
                    <Link
                      aria-current={isActive ? "page" : undefined}
                      className={`nav-sub-item ${isActive ? "active" : ""}`}
                      href={item.href}
                      key={item.key}
                    >
                      <span className="nav-sub-icon">
                        <ItemIcon aria-hidden="true" size={15} strokeWidth={1.8} />
                      </span>
                      <span className="nav-sub-label">{item.shortLabel}</span>
                      {item.badge && (
                        <span className={`nav-sub-badge badge-${item.badgeTone || "brand"}`}>
                          {item.badge}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
