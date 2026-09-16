import type { NavigationSection } from "@/lib/experience-types";

export const NAVIGATION: NavigationSection[] = [
  {
    key: "home",
    label: "工作入口",
    shortLabel: "工作入口",
    href: "/console",
    iconKey: "layout-dashboard",
    groupKey: "experience",
    deliveryState: "implemented",
    items: [
      { key: "home", label: "数字孪生", href: "/console" },
      { key: "workspaces", label: "岗位工作台", href: "/console/workspaces", requiredPermission: "platform.navigation.read" },
      { key: "inbox", label: "消息中心", href: "/console/inbox", requiredPermission: "notification.read" },
      { key: "assistant", label: "企业助手", href: "/console/assistant", requiredPermission: "role-twin.invoke" }
    ]
  },
  {
    key: "cockpit",
    label: "经营管理",
    shortLabel: "经营管理",
    href: "/console/cockpit",
    iconKey: "gauge",
    groupKey: "insights",
    deliveryState: "implemented",
    items: [{ key: "cockpit", label: "全域经营态势", href: "/console/cockpit", requiredPermission: "metric.query.execute" }]
  },
  {
    key: "commerce",
    label: "渠道与店铺",
    shortLabel: "渠道店铺",
    href: "/console/commerce/stores",
    iconKey: "store",
    groupKey: "business",
    deliveryState: "implemented",
    items: [{ key: "stores", label: "渠道与店铺", href: "/console/commerce/stores", requiredPermission: "metric.query.execute" }]
  },
  {
    key: "data",
    label: "数据基础中心",
    shortLabel: "数据基础",
    href: "/console/data/foundation/sources",
    iconKey: "database",
    groupKey: "data-foundation",
    deliveryState: "implemented",
    items: [
      { key: "sources", label: "数据源", href: "/console/data/foundation/sources", requiredPermission: "source.manage" },
      { key: "sync-jobs", label: "同步任务", href: "/console/data/foundation/sync-jobs", requiredPermission: "source.manage" },
      { key: "commerce", label: "经营事实", href: "/console/data/products/commerce", requiredPermission: "metric.query.execute" },
      { key: "customers", label: "客户 360", href: "/console/data/products/customers", requiredPermission: "customer.profile.read" },
      { key: "entities", label: "企业实体", href: "/console/data/foundation/entities", requiredPermission: "metric.definition.read" },
      { key: "metrics", label: "指标目录", href: "/console/data/foundation/metrics", requiredPermission: "metric.definition.read" },
      { key: "quality", label: "数据质量", href: "/console/data/foundation/quality", requiredPermission: "metric.definition.read" },
      { key: "reconciliation", label: "经营对账", href: "/console/data/foundation/reconciliation", requiredPermission: "metric.query.execute" }
    ]
  },
  {
    key: "knowledge",
    label: "知识中心",
    shortLabel: "知识中心",
    href: "/console/knowledge/documents",
    iconKey: "book-open",
    groupKey: "knowledge",
    deliveryState: "implemented",
    items: [
      { key: "documents", label: "知识文档", href: "/console/knowledge/documents", requiredPermission: "knowledge.document.read" },
      { key: "policies", label: "制度版本", href: "/console/knowledge/policies", requiredPermission: "knowledge.document.read" },
      { key: "ingestion", label: "导入任务", href: "/console/knowledge/ingestion", requiredPermission: "knowledge.document.ingest" },
      { key: "evidence", label: "引用与证据", href: "/console/knowledge/evidence", requiredPermission: "knowledge.document.read" }
    ]
  },
  {
    key: "twins",
    label: "角色分身中心",
    shortLabel: "分身中心",
    href: "/console/twins/instances",
    iconKey: "bot",
    groupKey: "ai",
    deliveryState: "implemented",
    items: [
      { key: "templates", label: "岗位模板", href: "/console/twins/templates", requiredPermission: "role-twin.read" },
      { key: "instances", label: "分身实例", href: "/console/twins/instances", requiredPermission: "role-twin.read" },
      { key: "memories", label: "记忆审核", href: "/console/twins/memories", requiredPermission: "memory.candidate.read" },
      { key: "prompts", label: "配置版本", href: "/console/twins/prompts", requiredPermission: "role-twin.configure" },
      { key: "test", label: "分身测试", href: "/console/twins/test", requiredPermission: "role-twin.read" },
      { key: "evaluations", label: "回归评测", href: "/console/twins/evaluations", requiredPermission: "evaluation.read" },
      { key: "feedback", label: "反馈工单", href: "/console/twins/feedback", requiredPermission: "agent-feedback.review" },
      { key: "skills", label: "Skill 注册", href: "/console/twins/skills", requiredPermission: "skill.registry.manage" }
    ]
  },
  {
    key: "meetings",
    label: "数字会议中心",
    shortLabel: "数字会议",
    href: "/console/meetings",
    iconKey: "messages-square",
    groupKey: "governance",
    deliveryState: "implemented",
    items: [{ key: "meetings", label: "会议与决策", href: "/console/meetings", requiredPermission: "meeting.read" }]
  },
  {
    key: "analysis",
    label: "经营洞察中心",
    shortLabel: "经营洞察",
    href: "/console/analysis/store-review",
    iconKey: "chart",
    groupKey: "insights",
    deliveryState: "implemented",
    items: [
      { key: "ask", label: "经营问数", href: "/console/analysis/ask", requiredPermission: "analysis.read" },
      { key: "store-review", label: "店铺诊断", href: "/console/analysis/store-review", requiredPermission: "analysis.read" },
      { key: "review-plans", label: "巡店计划", href: "/console/analysis/review-plans", requiredPermission: "analysis.schedule.read" },
      { key: "briefs", label: "经营简报", href: "/console/analysis/briefs", requiredPermission: "analysis.read" }
    ]
  },
  {
    key: "actions",
    label: "行动与执行中心",
    shortLabel: "行动中心",
    href: "/console/actions/work",
    iconKey: "list-checks",
    groupKey: "governance",
    deliveryState: "implemented",
    items: [
      { key: "work", label: "运营工作台", href: "/console/actions/work", requiredPermission: "action.work.read" },
      { key: "proposals", label: "行动提议", href: "/console/actions/proposals", requiredPermission: "action.propose" },
      { key: "approvals", label: "审批队列", href: "/console/actions/approvals", requiredPermission: "action.approve" },
      { key: "executions", label: "执行台账", href: "/console/actions/executions", requiredPermission: "action.execute" }
    ]
  },
  {
    key: "customer-service",
    label: "客服工作台",
    shortLabel: "客服工作台",
    href: "/console/customer-service/conversations",
    iconKey: "headset",
    groupKey: "business",
    deliveryState: "implemented",
    items: [
      {
        key: "conversations",
        label: "客户会话",
        href: "/console/customer-service/conversations",
        requiredPermission: "customer-service.conversation.read"
      },
      { key: "drafts", label: "回复草稿", href: "/console/customer-service/drafts", requiredPermission: "customer-service.reply.draft" }
    ]
  },
  {
    key: "admin",
    label: "平台管理",
    shortLabel: "平台管理",
    href: "/console/admin/users",
    iconKey: "settings",
    groupKey: "platform",
    deliveryState: "implemented",
    items: [
      { key: "users", label: "用户账号", href: "/console/admin/users", requiredPermission: "identity.user.manage" },
      { key: "org", label: "组织岗位", href: "/console/admin/org", requiredPermission: "identity.user.manage" },
      { key: "access", label: "访问权限", href: "/console/admin/access", requiredPermission: "identity.access.manage" },
      { key: "channels", label: "渠道身份", href: "/console/admin/channels", requiredPermission: "identity.user.manage" },
      { key: "ai-runtime", label: "AI 运行控制", href: "/console/admin/ai-runtime", requiredPermission: "ai.provider.manage" },
      { key: "tools", label: "工具注册", href: "/console/admin/tools", requiredPermission: "identity.access.manage" },
      { key: "jobs", label: "后台任务", href: "/console/admin/jobs", requiredPermission: "operations.run.read" },
      { key: "config", label: "参数字典", href: "/console/admin/config", requiredPermission: "platform.config.read" },
      { key: "files", label: "文件资产", href: "/console/admin/files", requiredPermission: "file.asset.read" },
      { key: "exchange", label: "批量交换", href: "/console/admin/exchange", requiredPermission: "bulk.exchange.read" },
      { key: "delegations", label: "访问委托", href: "/console/admin/delegations", requiredPermission: "identity.delegation.manage" },
      { key: "audit", label: "审计记录", href: "/console/admin/audit", requiredPermission: "audit.event.read" }
    ]
  }
];

export function projectNavigation(
  allowedSectionKeys: string[],
  projectedSections: Array<{ key: string; href: string }> = []
): NavigationSection[] {
  return NAVIGATION.filter((section) => allowedSectionKeys.includes(section.key)).map((section) => {
    const projected = projectedSections.find((item) => item.key === section.key);
    const href = projected && section.items.some((item) => item.href === projected.href)
      ? projected.href
      : section.href;
    return href === section.href ? section : { ...section, href };
  });
}

export function sectionForPath(pathname: string): NavigationSection {
  if (
    pathname === "/console" ||
    pathname.startsWith("/console/inbox") ||
    pathname.startsWith("/console/assistant") ||
    pathname === "/console/workspaces" ||
    pathname.startsWith("/console/workspaces/")
  ) {
    return NAVIGATION[0];
  }
  if (pathname === "/console/commerce" || pathname.startsWith("/console/commerce/")) {
    return NAVIGATION.find((section) => section.key === "commerce") ?? NAVIGATION[0];
  }
  return (
    NAVIGATION.find(
      (section) => section.key !== "home" && pathname.startsWith(`/console/${section.key}`)
    ) ?? NAVIGATION[0]
  );
}

export function pageKeyForPath(pathname: string): string {
  if (pathname === "/console") return "home";
  return pathname.replace(/^\/console\/?/, "").replace(/\/$/, "");
}
