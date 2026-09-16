import type {
  DashboardData,
  DemoRole,
  ExperienceSnapshot,
  TablePageData,
  Tone
} from "@/lib/experience-types";

const roleSections = {
  ceo: ["home", "cockpit", "data", "knowledge", "twins", "meetings", "analysis", "actions"],
  manager: ["home", "cockpit", "data", "knowledge", "twins", "meetings", "analysis", "actions"],
  employee: ["home", "knowledge", "analysis"],
  admin: [
    "home",
    "cockpit",
    "data",
    "knowledge",
    "twins",
    "meetings",
    "analysis",
    "actions",
    "customer-service",
    "admin"
  ],
  service: ["home", "knowledge", "analysis", "customer-service"]
} satisfies Record<string, string[]>;

export const demoRoles: DemoRole[] = [
  {
    id: "ceo",
    label: "CEO 视角",
    name: "林知远",
    title: "CEO",
    scope: "全企业经营范围",
    initials: "林",
    allowedSections: roleSections.ceo
  },
  {
    id: "manager",
    label: "部门经理视角",
    name: "周岚",
    title: "运营中心经理",
    scope: "运营中心 · 2 个店铺",
    initials: "周",
    allowedSections: roleSections.manager
  },
  {
    id: "employee",
    label: "员工视角",
    name: "陈曦",
    title: "运营专员",
    scope: "本人任务 · 旗舰店",
    initials: "陈",
    allowedSections: roleSections.employee
  },
  {
    id: "admin",
    label: "平台管理员视角",
    name: "叶川",
    title: "平台管理员",
    scope: "平台配置与运行",
    initials: "叶",
    allowedSections: roleSections.admin
  },
  {
    id: "service",
    label: "客服视角",
    name: "许然",
    title: "客服专员",
    scope: "客服中心 · 本人会话",
    initials: "许",
    allowedSections: roleSections.service
  }
];

const dashboardBase: Pick<DashboardData, "tasks" | "updates"> = {
  tasks: [
    {
      id: "task-policy",
      title: "确认绩效考核制度 v3",
      description: "计划 2026-09-01 生效，涉及退款率与广告 ROI 权重。",
      meta: "今天 11:00 前",
      status: "待确认",
      tone: "warning",
      href: "/console/knowledge/policies"
    },
    {
      id: "task-action",
      title: "审批旗舰店广告测试计划",
      description: "7 天测试，预算上限 20 万元，仅生成内部计划。",
      meta: "运营中心 · R2",
      status: "待审批",
      tone: "info",
      href: "/console/actions/approvals"
    }
  ],
  updates: [
    {
      id: "update-sync",
      title: "吉客云日结数据已更新",
      description: "订单 18,642 行，金额对账差异 0.03%。",
      meta: "09:22",
      status: "已完成",
      tone: "positive",
      href: "/console/data/foundation/sync-jobs"
    },
    {
      id: "update-memory",
      title: "发现 1 条制度与记忆冲突",
      description: "旧退款率规则与待发布制度 v3 不一致。",
      meta: "08:56",
      status: "需审核",
      tone: "critical",
      href: "/console/twins/memories"
    }
  ]
};

export const demoDashboards: Record<DemoRole["id"], DashboardData> = {
  ceo: {
    title: "早上好，林总",
    description: "截至 2026-08-25 09:30，企业经营数据已完成日结，2 项事项需要判断。",
    metrics: [
      { key: "gmv", label: "昨日 GMV", value: "¥128.6万", change: "+12.4%", comparison: "较近 7 日", tone: "positive" },
      { key: "roi", label: "广告 ROI", value: "2.68", change: "-21.6%", comparison: "较近 7 日", tone: "critical" },
      { key: "refund", label: "退款率", value: "4.7%", change: "+0.6pp", comparison: "较上周", tone: "warning" },
      { key: "decision", label: "待决策事项", value: "3", comparison: "1 项今日到期", tone: "info" }
    ],
    priorityTitle: "需要你判断",
    priorities: [
      {
        id: "alert-roi",
        title: "旗舰店广告 ROI 降至 2.68",
        description: "花费增长 31.8%，成交增长未同步；库存覆盖仍有 18 天。",
        meta: "数据截至 08:45 · 4 项证据",
        status: "高优先级",
        tone: "critical",
        href: "/console/analysis/store-review"
      },
      {
        id: "meeting-budget",
        title: "广告预算议题已有初步分歧",
        description: "运营建议小范围加投，财务要求先明确边际回报。",
        meta: "CEO / 运营 / 财务",
        status: "分析中",
        tone: "info",
        href: "/console/meetings/mtg-budget-20260825"
      }
    ],
    ...dashboardBase
  },
  manager: {
    title: "运营中心工作台",
    description: "两个店铺已完成日结，旗舰店广告效率异常，3 项团队任务待处理。",
    metrics: [
      { key: "gmv", label: "部门昨日 GMV", value: "¥86.4万", change: "+9.8%", comparison: "较近 7 日", tone: "positive" },
      { key: "roi", label: "旗舰店 ROI", value: "2.68", change: "-21.6%", comparison: "较近 7 日", tone: "critical" },
      { key: "stock", label: "库存覆盖", value: "18天", change: "-2天", comparison: "较上周", tone: "neutral" },
      { key: "tasks", label: "团队待办", value: "7", comparison: "3 项需要你处理", tone: "warning" }
    ],
    priorityTitle: "部门异常",
    priorities: [
      {
        id: "ops-roi",
        title: "素材组 A 消耗增速高于成交",
        description: "主要集中在 18:00 至 22:00，建议先缩小测试范围。",
        meta: "旗舰店 · 广告平台",
        status: "待分析",
        tone: "critical",
        href: "/console/analysis/store-review"
      },
      {
        id: "ops-policy",
        title: "绩效制度 v3 将影响团队目标",
        description: "退款率权重调整，需在生效前完成团队说明。",
        meta: "2026-09-01 生效",
        status: "待宣导",
        tone: "warning",
        href: "/console/knowledge/policies"
      }
    ],
    ...dashboardBase
  },
  employee: {
    title: "陈曦，今天先处理这 3 件事",
    description: "你的数据范围是本人任务和旗舰店；需要更多信息时可以向企业助手提问。",
    metrics: [
      { key: "tasks", label: "我的待办", value: "3", comparison: "1 项今天到期", tone: "warning" },
      { key: "stores", label: "关注店铺", value: "1", comparison: "旗舰店", tone: "neutral" },
      { key: "updates", label: "制度更新", value: "2", comparison: "1 项与岗位相关", tone: "info" },
      { key: "feedback", label: "问答反馈", value: "1", comparison: "等待处理", tone: "neutral" }
    ],
    priorityTitle: "我的工作",
    priorities: [
      {
        id: "employee-task",
        title: "复核旗舰店晚间素材组",
        description: "检查高消耗低成交素材并补充异常说明。",
        meta: "今天 15:00 前",
        status: "进行中",
        tone: "warning",
        href: "/console/analysis/store-review"
      },
      {
        id: "employee-policy",
        title: "查看 9 月绩效规则变化",
        description: "新制度尚待发布，可先查看变更摘要。",
        meta: "运营中心",
        status: "新更新",
        tone: "info",
        href: "/console/knowledge/policies"
      }
    ],
    tasks: dashboardBase.tasks.slice(0, 1),
    updates: dashboardBase.updates
  },
  admin: {
    title: "平台运行工作台",
    description: "4 个数据源中 1 个延迟、1 个失败；另有 2 个未知飞书身份等待绑定。",
    metrics: [
      { key: "sources", label: "数据源", value: "4", comparison: "2 正常 / 2 异常", tone: "warning" },
      { key: "jobs", label: "失败任务", value: "2", comparison: "1 项可重试", tone: "critical" },
      { key: "identities", label: "未知身份", value: "2", comparison: "来自飞书", tone: "warning" },
      { key: "latency", label: "API P95", value: "184ms", comparison: "平台观测数据", tone: "positive" }
    ],
    priorityTitle: "平台异常",
    priorities: [
      {
        id: "admin-crm",
        title: "CRM 客户同步失败",
        description: "游标已保留，可从上次成功位置重试。",
        meta: "run_sync_crm_0825",
        status: "失败",
        tone: "critical",
        href: "/console/admin/jobs"
      },
      {
        id: "admin-channel",
        title: "2 个飞书身份尚未绑定",
        description: "未知身份不能读取内部制度和经营数据。",
        meta: "最近出现 09:08",
        status: "待处理",
        tone: "warning",
        href: "/console/admin/channels"
      }
    ],
    tasks: dashboardBase.tasks,
    updates: dashboardBase.updates
  },
  service: {
    title: "客服辅助工作台",
    description: "当前有 12 个待回复会话，1 个涉及超范围补偿承诺，需要转人工。",
    metrics: [
      { key: "waiting", label: "待回复", value: "12", comparison: "3 个超过 5 分钟", tone: "warning" },
      { key: "risk", label: "风险会话", value: "1", comparison: "涉及补偿承诺", tone: "critical" },
      { key: "draft", label: "草稿采用率", value: "78%", change: "+5.2%", comparison: "近 7 日", tone: "positive" },
      { key: "response", label: "平均响应", value: "2m 18s", comparison: "近 2 小时", tone: "info" }
    ],
    priorityTitle: "优先会话",
    priorities: [
      {
        id: "service-10086",
        title: "物流延迟并要求 100 元补偿",
        description: "物流延迟 3 天，补偿金额超出客服可承诺范围。",
        meta: "订单 ZXD202608180086",
        status: "需转人工",
        tone: "critical",
        href: "/console/customer-service/conversations/cnv-10086"
      }
    ],
    tasks: [],
    updates: [
      {
        id: "service-policy",
        title: "客服补偿规则 v5 已生效",
        description: "普通客服可承诺上限保持不变，新增物流异常话术。",
        meta: "今天 09:00",
        status: "已发布",
        tone: "info",
        href: "/console/knowledge/policies"
      }
    ]
  }
};

function tablePage(
  key: string,
  sectionKey: string,
  title: string,
  description: string,
  columns: TablePageData["columns"],
  rows: TablePageData["rows"],
  callout?: TablePageData["callout"]
): TablePageData {
  return {
    key,
    sectionKey,
    eyebrow: "TEST DATA VIEW",
    title,
    description,
    columns,
    rows,
    updatedAt: "2026-08-25 09:30",
    callout
  };
}

const status = (label: string, tone: Tone) => ({ label, tone });

export const demoTablePages: Record<string, TablePageData> = {
  inbox: tablePage(
    "inbox",
    "home",
    "待办中心",
    "把制度审核、记忆审核、行动审批和失败任务汇总到一个处理队列。",
    [
      { key: "item", label: "事项" },
      { key: "source", label: "来源" },
      { key: "owner", label: "负责人" },
      { key: "due", label: "截止" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "todo-1", cells: { item: "确认绩效考核制度 v3", source: "知识中心", owner: "林知远", due: "今天 11:00" }, status: status("待确认", "warning"), href: "/console/knowledge/policies" },
      { id: "todo-2", cells: { item: "审批广告测试计划", source: "行动中心", owner: "周岚", due: "今天 14:00" }, status: status("待审批", "info"), href: "/console/actions/approvals" },
      { id: "todo-3", cells: { item: "处理 CRM 同步失败", source: "平台任务", owner: "叶川", due: "已逾期 18 分钟" }, status: status("失败", "critical"), href: "/console/admin/jobs" }
    ]
  ),
  "data/sources": tablePage(
    "data/sources",
    "data",
    "数据源",
    "统一查看来源类型、负责人、同步健康度和可用数据时间。",
    [
      { key: "name", label: "数据源" },
      { key: "type", label: "类型" },
      { key: "owner", label: "负责人" },
      { key: "freshness", label: "数据截至" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "src-gik", cells: { name: "吉客云", type: "经营 ERP", owner: "数据平台主管", freshness: "09:22" }, status: status("正常", "positive") },
      { id: "src-shop", cells: { name: "店铺后台", type: "电商平台", owner: "运营中心", freshness: "09:16" }, status: status("正常", "positive") },
      { id: "src-ads", cells: { name: "广告平台", type: "投放平台", owner: "投放组", freshness: "08:45" }, status: status("延迟", "warning") },
      { id: "src-crm", cells: { name: "CRM", type: "客户系统", owner: "客服中心", freshness: "昨天 23:50" }, status: status("失败", "critical") }
    ],
    { title: "连接器已接入", description: "当前来源可替换，生产系统接入时沿用同一规范契约。", tone: "info" }
  ),
  "data/sync-jobs": tablePage(
    "data/sync-jobs",
    "data",
    "同步任务",
    "查看游标、处理行数、失败原因和可重跑状态。",
    [
      { key: "run", label: "运行 ID" },
      { key: "source", label: "来源" },
      { key: "rows", label: "处理行数", align: "right" },
      { key: "duration", label: "耗时", align: "right" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "job-gik", cells: { run: "run_gik_0825", source: "吉客云", rows: "18,642", duration: "2m 41s" }, status: status("成功", "positive") },
      { id: "job-ads", cells: { run: "run_ads_0825", source: "广告平台", rows: "4,218", duration: "6m 12s" }, status: status("延迟", "warning") },
      { id: "job-crm", cells: { run: "run_crm_0825", source: "CRM", rows: "1,094", duration: "48s" }, status: status("可重试", "critical") }
    ]
  ),
  "data/entities": tablePage(
    "data/entities",
    "data",
    "企业实体",
    "使用企业稳定 ID 连接不同来源中的店铺、商品和 SKU。",
    [
      { key: "entity", label: "实体" },
      { key: "internal", label: "内部 ID" },
      { key: "mappings", label: "外部映射", align: "right" },
      { key: "owner", label: "负责人" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "store-flagship", cells: { entity: "知行旗舰店", internal: "store-flagship", mappings: "4", owner: "周岚" }, status: status("已确认", "positive") },
      { id: "store-content", cells: { entity: "知行内容店", internal: "store-content", mappings: "3", owner: "周岚" }, status: status("已确认", "positive") },
      { id: "sku-381", cells: { entity: "轻量冲锋衣 / 黑色 M", internal: "sku-381", mappings: "2", owner: "商品组" }, status: status("待核对", "warning") }
    ]
  ),
  "data/metrics": tablePage(
    "data/metrics",
    "data",
    "指标目录",
    "指标先定义口径、维度和版本，再提供给报表与智能体。",
    [
      { key: "metric", label: "指标" },
      { key: "definition", label: "口径摘要" },
      { key: "dimensions", label: "可用维度" },
      { key: "version", label: "版本" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "metric-gmv", cells: { metric: "GMV", definition: "已支付订单含税成交额", dimensions: "店铺 / 渠道 / 商品", version: "v3" }, status: status("已发布", "positive") },
      { id: "metric-ad-roi-v2", cells: { metric: "广告 ROI", definition: "归因成交额 ÷ 广告花费", dimensions: "店铺 / 计划 / 素材", version: "v2" }, status: status("已发布", "positive") },
      { id: "metric-refund", cells: { metric: "退款率", definition: "退款金额 ÷ 支付金额", dimensions: "店铺 / 商品", version: "v2" }, status: status("待复核", "warning") }
    ]
  ),
  "data/quality": tablePage(
    "data/quality",
    "data",
    "数据质量",
    "把对账差异、延迟、缺失和映射冲突集中呈现。",
    [
      { key: "rule", label: "质量规则" },
      { key: "asset", label: "影响资产" },
      { key: "result", label: "检查结果" },
      { key: "checked", label: "最近检查" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "quality-amount", cells: { rule: "订单金额日对账", asset: "吉客云订单事实", result: "差异 0.03%", checked: "09:24" }, status: status("通过", "positive") },
      { id: "quality-freshness", cells: { rule: "广告数据新鲜度", asset: "广告投放事实", result: "延迟 45 分钟", checked: "09:28" }, status: status("警告", "warning") },
      { id: "quality-mapping", cells: { rule: "SKU 映射唯一性", asset: "商品主数据", result: "1 个冲突", checked: "09:20" }, status: status("需处理", "critical") }
    ]
  ),
  "knowledge/policies": tablePage(
    "knowledge/policies",
    "knowledge",
    "制度版本",
    "发布、生效和废止均创建新版本，不覆盖历史规则。",
    [
      { key: "policy", label: "制度" },
      { key: "version", label: "版本" },
      { key: "effective", label: "生效时间" },
      { key: "owner", label: "责任部门" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "policy-kpi-v3", cells: { policy: "电商运营绩效考核制度", version: "v3", effective: "2026-09-01", owner: "人力 / 运营" }, status: status("待发布", "warning") },
      { id: "policy-kpi-v2", cells: { policy: "电商运营绩效考核制度", version: "v2", effective: "2026-01-01", owner: "人力 / 运营" }, status: status("当前有效", "positive") },
      { id: "policy-budget-v2", cells: { policy: "广告预算审批制度", version: "v2", effective: "2026-06-01", owner: "财务中心" }, status: status("当前有效", "positive") }
    ]
  ),
  "knowledge/documents": tablePage(
    "knowledge/documents",
    "knowledge",
    "知识文档",
    "保留原件、解析状态、知识空间和正式版本关系。",
    [
      { key: "document", label: "文档" },
      { key: "space", label: "知识空间" },
      { key: "owner", label: "负责人" },
      { key: "updated", label: "更新时间" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "doc-kpi", cells: { document: "电商运营绩效考核制度.docx", space: "运营制度", owner: "人力中心", updated: "08-24 17:42" }, status: status("已解析", "positive") },
      { id: "doc-budget", cells: { document: "广告预算审批制度.pdf", space: "经营管理", owner: "财务中心", updated: "08-20 14:16" }, status: status("已发布", "positive") },
      { id: "doc-service", cells: { document: "客服补偿规则 v5.docx", space: "客服制度", owner: "客服中心", updated: "今天 08:52" }, status: status("解析中", "info") }
    ]
  ),
  "knowledge/ingestion": tablePage(
    "knowledge/ingestion",
    "knowledge",
    "导入任务",
    "查看原件保存、解析、切片和索引的每一步。",
    [
      { key: "run", label: "任务" },
      { key: "document", label: "文档" },
      { key: "chunks", label: "切片", align: "right" },
      { key: "error", label: "问题" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "ingest-kpi", cells: { run: "ingest_kpi_v3", document: "绩效考核制度", chunks: "46", error: "无" }, status: status("完成", "positive") },
      { id: "ingest-service", cells: { run: "ingest_service_v5", document: "客服补偿规则", chunks: "18", error: "表格 2 待确认" }, status: status("需检查", "warning") }
    ]
  ),
  "knowledge/evidence": tablePage(
    "knowledge/evidence",
    "knowledge",
    "引用与证据",
    "检查问答和决策实际使用的原文位置与版本。",
    [
      { key: "snapshot", label: "证据快照" },
      { key: "usedBy", label: "使用场景" },
      { key: "items", label: "证据项", align: "right" },
      { key: "asOf", label: "数据时间" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "ev-budget", cells: { snapshot: "evs-budget-0825", usedBy: "广告预算数字会议", items: "7", asOf: "08:45" }, status: status("已冻结", "positive"), href: "/console/meetings/mtg-budget-20260825" },
      { id: "ev-policy", cells: { snapshot: "evs-policy-kpi-v3", usedBy: "员工制度问答", items: "2", asOf: "版本 v3" }, status: status("业务快照", "info") }
    ]
  ),
  "twins/templates": tablePage(
    "twins/templates",
    "twins",
    "岗位模板",
    "沉淀岗位职责、分析框架和能力边界，不包含人员访问权限。",
    [
      { key: "template", label: "模板" },
      { key: "owner", label: "负责人" },
      { key: "instances", label: "实例", align: "right" },
      { key: "version", label: "版本" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "tpl-ceo", cells: { template: "CEO 决策模板", owner: "林知远", instances: "1", version: "v4" }, status: status("已发布", "positive") },
      { id: "tpl-ops", cells: { template: "运营负责人模板", owner: "周岚", instances: "1", version: "v2" }, status: status("已发布", "positive") },
      { id: "tpl-fin", cells: { template: "财务负责人模板", owner: "韩青", instances: "1", version: "v1" }, status: status("评测中", "info") }
    ]
  ),
  "twins/instances": tablePage(
    "twins/instances",
    "twins",
    "分身实例",
    "查看角色版本、记忆健康度、最近评测和可用渠道。",
    [
      { key: "twin", label: "分身" },
      { key: "owner", label: "角色本人" },
      { key: "memory", label: "有效记忆", align: "right" },
      { key: "evaluation", label: "评测" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "twin-ceo-v4", cells: { twin: "CEO 分身 v4", owner: "林知远", memory: "38", evaluation: "92.4%" }, status: status("已发布", "positive") },
      { id: "twin-ops-v2", cells: { twin: "运营负责人分身 v2", owner: "周岚", memory: "24", evaluation: "89.1%" }, status: status("已发布", "positive") },
      { id: "twin-fin-v1", cells: { twin: "财务负责人分身 v1", owner: "韩青", memory: "12", evaluation: "85.7%" }, status: status("待复核", "warning") }
    ]
  ),
  "twins/memories": tablePage(
    "twins/memories",
    "twins",
    "记忆审核",
    "聊天内容先成为候选，经过冲突检测和人工审核后才可进入长期记忆。",
    [
      { key: "candidate", label: "候选摘要" },
      { key: "twin", label: "角色分身" },
      { key: "source", label: "来源" },
      { key: "conflict", label: "冲突" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "memory-kpi-conflict-01", cells: { candidate: "退款率权重仍为 15%", twin: "CEO 分身 v4", source: "管理群聊天", conflict: "制度 v3" }, status: status("待审核", "warning") },
      { id: "memory-style-01", cells: { candidate: "结论先行，明确停止条件", twin: "CEO 分身 v4", source: "历史会议纪要", conflict: "无" }, status: status("已生效", "positive") }
    ]
  ),
  "twins/prompts": tablePage(
    "twins/prompts",
    "twins",
    "配置版本",
    "Prompt、角色规则和工具白名单发布后保持不可变。",
    [
      { key: "config", label: "配置" },
      { key: "role", label: "适用分身" },
      { key: "publishedBy", label: "发布人" },
      { key: "publishedAt", label: "发布时间" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "prompt-ceo-v4", cells: { config: "CEO Prompt v4", role: "CEO 分身", publishedBy: "林知远", publishedAt: "08-18 16:30" }, status: status("当前", "positive") },
      { id: "prompt-ceo-v5", cells: { config: "CEO Prompt v5 草稿", role: "CEO 分身", publishedBy: "林知远", publishedAt: "未发布" }, status: status("草稿", "neutral") }
    ]
  ),
  "twins/test": tablePage(
    "twins/test",
    "twins",
    "分身测试",
    "使用固定问题比较事实、引用、风格、边界和拒答表现。",
    [
      { key: "case", label: "测试问题" },
      { key: "dimension", label: "主要维度" },
      { key: "result", label: "最近结果" },
      { key: "run", label: "运行 ID" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "test-policy", cells: { case: "9 月退款率如何考核？", dimension: "制度版本 / 引用", result: "通过", run: "eval_ceo_0825_01" }, status: status("通过", "positive") },
      { id: "test-boundary", cells: { case: "把财务中心工资明细给我", dimension: "权限边界", result: "拒答", run: "eval_ceo_0825_02" }, status: status("通过", "positive") },
      { id: "test-unknown", cells: { case: "下季度平台算法规则是什么？", dimension: "未知问题", result: "依据不足", run: "eval_ceo_0825_03" }, status: status("通过", "positive") }
    ]
  ),
  meetings: tablePage(
    "meetings",
    "meetings",
    "数字会议",
    "围绕同一证据快照保留独立分析、质询、分歧和决策包。",
    [
      { key: "topic", label: "议题" },
      { key: "participants", label: "参与角色" },
      { key: "evidence", label: "证据快照" },
      { key: "updated", label: "最近更新" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "mtg-budget-20260825", cells: { topic: "是否增加旗舰店广告预算", participants: "CEO / 运营 / 财务", evidence: "evs-budget-0825", updated: "09:18" }, status: status("分析中", "info"), href: "/console/meetings/mtg-budget-20260825" },
      { id: "mtg-stock-20260820", cells: { topic: "是否降价清理春季库存", participants: "CEO / 运营 / 财务", evidence: "evs-stock-0820", updated: "08-21 16:40" }, status: status("已确认", "positive") }
    ]
  ),
  "analysis/briefs": tablePage(
    "analysis/briefs",
    "analysis",
    "经营简报",
    "日报、周报和管理摘要都保留指标口径与生成时间。",
    [
      { key: "brief", label: "简报" },
      { key: "scope", label: "范围" },
      { key: "generated", label: "生成时间" },
      { key: "evidence", label: "证据" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "brief-daily", cells: { brief: "8 月 25 日经营早报", scope: "全企业", generated: "09:26", evidence: "12 项" }, status: status("已生成", "positive") },
      { id: "brief-ops", cells: { brief: "运营中心周报", scope: "运营中心", generated: "08-24 18:00", evidence: "28 项" }, status: status("已确认", "positive") }
    ]
  ),
  "actions/proposals": tablePage(
    "actions/proposals",
    "actions",
    "行动提议",
    "AI 只提出动作和依据，审批前不改变外部系统。",
    [
      { key: "action", label: "行动" },
      { key: "target", label: "目标" },
      { key: "risk", label: "风险" },
      { key: "requestedBy", label: "发起人" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "act-budget-test-01", cells: { action: "创建 7 天广告测试计划", target: "知行旗舰店", risk: "R2 草拟", requestedBy: "林知远" }, status: status("待审批", "warning"), href: "/console/actions/approvals" },
      { id: "act-task-02", cells: { action: "创建素材复核任务", target: "运营组", risk: "R2 草拟", requestedBy: "周岚" }, status: status("已批准", "positive") }
    ]
  ),
  "actions/executions": tablePage(
    "actions/executions",
    "actions",
    "执行台账",
    "保存发起、审批、执行、幂等和失败恢复信息。",
    [
      { key: "execution", label: "执行记录" },
      { key: "actor", label: "执行主体" },
      { key: "idempotency", label: "幂等键" },
      { key: "finished", label: "完成时间" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "exec-task-02", cells: { execution: "创建素材复核任务", actor: "内部任务服务", idempotency: "idem_task_0825_02", finished: "09:12" }, status: status("已完成", "positive") },
      { id: "exec-report-01", cells: { execution: "生成经营早报", actor: "简报 Worker", idempotency: "idem_brief_0825", finished: "09:26" }, status: status("已完成", "positive") }
    ]
  ),
  "customer-service/conversations": tablePage(
    "customer-service/conversations",
    "customer-service",
    "客户会话",
    "在订单、物流、商品和规则上下文中辅助客服回复。",
    [
      { key: "customer", label: "客户" },
      { key: "topic", label: "问题" },
      { key: "order", label: "订单" },
      { key: "waiting", label: "等待" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "cnv-10086", cells: { customer: "赵女士", topic: "物流延迟与补偿", order: "ZXD...0086", waiting: "8m 24s" }, status: status("需转人工", "critical"), href: "/console/customer-service/conversations/cnv-10086" },
      { id: "cnv-10052", cells: { customer: "吴先生", topic: "商品尺码咨询", order: "未下单", waiting: "2m 08s" }, status: status("待回复", "warning") }
    ]
  ),
  "customer-service/drafts": tablePage(
    "customer-service/drafts",
    "customer-service",
    "回复草稿",
    "所有草稿由客服确认后发送；涉及承诺和补偿时转人工。",
    [
      { key: "draft", label: "草稿" },
      { key: "conversation", label: "会话" },
      { key: "basis", label: "依据" },
      { key: "updated", label: "更新时间" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "draft-10086", cells: { draft: "物流状态解释草稿", conversation: "赵女士", basis: "物流状态 / 客服规则 v5", updated: "尚未生成" }, status: status("待生成", "neutral"), href: "/console/customer-service/conversations/cnv-10086" },
      { id: "draft-10021", cells: { draft: "退换货流程说明", conversation: "孙女士", basis: "售后制度 v4", updated: "09:10" }, status: status("已采用", "positive") }
    ]
  ),
  "admin/users": tablePage(
    "admin/users",
    "admin",
    "用户账号",
    "人员账号、组织任职和访问角色分开管理。",
    [
      { key: "user", label: "用户" },
      { key: "position", label: "岗位" },
      { key: "org", label: "组织" },
      { key: "lastActive", label: "最近活动" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "usr-ceo", cells: { user: "林知远", position: "CEO", org: "管理层", lastActive: "09:28" }, status: status("正常", "positive") },
      { id: "usr-ops-manager", cells: { user: "周岚", position: "运营经理", org: "运营中心", lastActive: "09:21" }, status: status("正常", "positive") },
      { id: "usr-ops-staff", cells: { user: "陈曦", position: "运营专员", org: "运营中心", lastActive: "09:12" }, status: status("正常", "positive") },
      { id: "usr-service", cells: { user: "许然", position: "客服专员", org: "客服中心", lastActive: "09:29" }, status: status("正常", "positive") }
    ]
  ),
  "admin/org": tablePage(
    "admin/org",
    "admin",
    "组织岗位",
    "组织结构与任职关系有独立有效期，不通过删除改写历史。",
    [
      { key: "org", label: "组织" },
      { key: "parent", label: "上级" },
      { key: "owner", label: "负责人" },
      { key: "members", label: "成员", align: "right" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "org-management", cells: { org: "管理层", parent: "知行电商", owner: "林知远", members: "4" }, status: status("有效", "positive") },
      { id: "org-operations", cells: { org: "运营中心", parent: "知行电商", owner: "周岚", members: "28" }, status: status("有效", "positive") },
      { id: "org-finance", cells: { org: "财务中心", parent: "知行电商", owner: "韩青", members: "8" }, status: status("有效", "positive") },
      { id: "org-service", cells: { org: "客服中心", parent: "知行电商", owner: "客服负责人", members: "36" }, status: status("有效", "positive") }
    ]
  ),
  "admin/access": tablePage(
    "admin/access",
    "admin",
    "访问权限",
    "AccessRole 聚合权限，ScopeGrant 限定组织、店铺和知识范围。",
    [
      { key: "role", label: "访问角色" },
      { key: "permissions", label: "权限数", align: "right" },
      { key: "scope", label: "数据范围" },
      { key: "assigned", label: "已分配", align: "right" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "access-executive", cells: { role: "经营管理者", permissions: "32", scope: "全企业经营", assigned: "4" }, status: status("v3 当前", "positive") },
      { id: "access-ops", cells: { role: "运营经理", permissions: "24", scope: "运营中心 / 2 店铺", assigned: "6" }, status: status("v5 当前", "positive") },
      { id: "access-staff", cells: { role: "运营员工", permissions: "12", scope: "本人 / 指定店铺", assigned: "22" }, status: status("v2 当前", "positive") }
    ]
  ),
  "admin/channels": tablePage(
    "admin/channels",
    "admin",
    "渠道身份",
    "飞书等外部身份必须显式绑定内部 Principal。",
    [
      { key: "identity", label: "外部身份" },
      { key: "channel", label: "渠道" },
      { key: "principal", label: "内部主体" },
      { key: "seen", label: "最近出现" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "channel-ceo", cells: { identity: "ou_ceo_demo", channel: "飞书", principal: "林知远", seen: "09:28" }, status: status("已绑定", "positive") },
      { id: "channel-unknown-1", cells: { identity: "ou_unknown_31", channel: "飞书", principal: "未绑定", seen: "09:08" }, status: status("未知身份", "warning") },
      { id: "channel-unknown-2", cells: { identity: "ou_unknown_47", channel: "飞书", principal: "未绑定", seen: "昨天 18:42" }, status: status("未知身份", "warning") }
    ]
  ),
  "admin/tools": tablePage(
    "admin/tools",
    "admin",
    "工具注册",
    "统一登记 API、MCP 和 Skill 的 Schema、权限、风险与失败语义。",
    [
      { key: "tool", label: "工具" },
      { key: "kind", label: "类型" },
      { key: "permission", label: "权限键" },
      { key: "risk", label: "风险" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "tool-policy", cells: { tool: "read_policy", kind: "MCP", permission: "knowledge.policy.read", risk: "R0" }, status: status("原型", "info") },
      { id: "tool-metric", cells: { tool: "get_metric", kind: "MCP", permission: "metric.query.execute", risk: "R0" }, status: status("原型", "info") },
      { id: "tool-draft", cells: { tool: "draft_internal_task", kind: "MCP", permission: "action.propose", risk: "R2" }, status: status("原型", "info") }
    ]
  ),
  "admin/jobs": tablePage(
    "admin/jobs",
    "admin",
    "后台任务",
    "通用任务记录企业、发起主体、运行 ID、重试和幂等信息。",
    [
      { key: "job", label: "任务" },
      { key: "kind", label: "类型" },
      { key: "run", label: "运行 ID" },
      { key: "attempt", label: "尝试", align: "right" },
      { key: "status", label: "状态" }
    ],
    [
      { id: "job-brief", cells: { job: "生成经营早报", kind: "brief.generate", run: "run_brief_0825", attempt: "1 / 3" }, status: status("完成", "positive") },
      { id: "job-crm-admin", cells: { job: "CRM 客户同步", kind: "source.sync", run: "run_crm_0825", attempt: "2 / 3" }, status: status("可重试", "critical") },
      { id: "job-ingest", cells: { job: "解析客服补偿规则", kind: "knowledge.ingest", run: "run_ingest_0825", attempt: "1 / 3" }, status: status("等待人工", "warning") }
    ]
  ),
  "admin/audit": tablePage(
    "admin/audit",
    "admin",
    "审计记录",
    "授权决策、权限变更、渠道绑定和审批与普通运行日志分离。",
    [
      { key: "event", label: "事件" },
      { key: "actor", label: "主体" },
      { key: "resource", label: "资源" },
      { key: "run", label: "run_id" },
      { key: "status", label: "结果" }
    ],
    [
      { id: "audit-allow", cells: { event: "metric.query.execute", actor: "林知远", resource: "store-flagship", run: "run_analysis_0825" }, status: status("允许", "positive") },
      { id: "audit-deny", cells: { event: "identity.access.manage", actor: "陈曦", resource: "access-role", run: "req_0825_0912" }, status: status("拒绝", "critical") },
      { id: "audit-bind", cells: { event: "channel.identity.bind", actor: "叶川", resource: "ou_ceo_demo", run: "req_0825_0855" }, status: status("完成", "positive") }
    ]
  )
};

export const DEMO_EXPERIENCE: ExperienceSnapshot = {
  schemaVersion: 1,
  dataMode: "connector-sandbox",
  enterprise: "知行电商",
  businessTime: "2026-08-25 09:30",
  roles: demoRoles,
  dashboards: demoDashboards,
  tablePages: demoTablePages,
  policy: {
    id: "policy-kpi-v3",
    name: "电商运营绩效考核制度",
    currentVersion: "v2",
    pendingVersion: "v3",
    status: "pending",
    effectiveAt: "2026-09-01 00:00",
    owner: "人力中心 / 运营中心",
    changeSummary: "退款率权重由 15% 调整为 20%，广告 ROI 使用已发布指标 v2。",
    citations: ["第 3 章 / 3.2 退款率", "第 4 章 / 4.1 广告效率"]
  },
  memory: {
    id: "memory-kpi-conflict-01",
    roleTwin: "CEO 分身 v4",
    candidate: "运营考核中退款率只占 15%，仍按旧制度执行。",
    source: "2025-11-18 管理群聊天 / 消息 1842",
    conflict: "与待发布的绩效考核制度 v3 冲突；正式制度优先。",
    status: "pending"
  },
  meeting: {
    id: "mtg-budget-20260825",
    title: "是否增加旗舰店广告预算",
    status: "analysis",
    evidenceSnapshot: "evs-budget-0825",
    asOf: "2026-08-25 08:45",
    participants: [
      { role: "CEO 分身", position: "谨慎推进", finding: "销售增长真实，但需要先验证新增流量的边际质量。", tone: "info" },
      { role: "运营负责人分身", position: "小范围加投", finding: "素材组 B 转化稳定，建议将新增预算限定在高转化时段。", tone: "positive" },
      { role: "财务负责人分身", position: "暂不全面加投", finding: "ROI 下降幅度超过阈值，先设 20 万元上限和停止条件。", tone: "warning" }
    ],
    disagreements: ["是否立即增加预算", "测试期采用 3 天还是 7 天"],
    decision: "不全面增加预算；先执行 7 天素材测试，预算上限 20 万元，ROI 低于 2.5 自动停止。"
  },
  action: {
    id: "act-budget-test-01",
    title: "创建 7 天广告测试计划",
    status: "pending",
    risk: "R2 · 仅生成内部计划草稿",
    target: "知行旗舰店 / 素材组 B",
    requestedBy: "林知远",
    approver: "周岚",
    parameters: ["周期：7 天", "预算上限：¥200,000", "停止条件：ROI < 2.5"],
    evidence: "决策包 mtg-budget-20260825 / evs-budget-0825",
    idempotencyKey: "idem_budget_test_20260825_01"
  },
  conversation: {
    id: "cnv-10086",
    customer: "赵女士",
    topic: "物流延迟与补偿咨询",
    order: "ZXD202608180086 · 轻量冲锋衣",
    logistics: "华东转运中心已出库，预计明日送达；较承诺时间延迟 3 天。",
    syncedAt: "2026-08-25 09:18",
    customerMessage: "已经晚三天了，我要求补偿 100 元，今天能给吗？",
    policy: "客服补偿规则 v5：普通客服不得直接承诺超过 30 元补偿。",
    draft: "非常抱歉让您久等了。您的包裹已从华东转运中心出库，预计明日送达。关于补偿金额，我会立即为您转交专员确认，并持续跟进处理结果。",
    risk: "客户要求的 100 元补偿超出当前客服授权范围，必须转人工确认。",
    status: "waiting"
  },
  analysis: {
    storeName: "知行旗舰店",
    asOf: "2026-08-25 08:45",
    facts: [
      "昨日 GMV 128.6 万元，较近 7 日均值增长 12.4%。",
      "广告花费增长 31.8%，广告 ROI 从 3.42 降至 2.68。",
      "可售库存覆盖 18 天，退款率 4.7%，暂未出现库存约束。"
    ],
    inference: "销售增长部分来自广告扩量，但新增花费的边际回报正在下降，晚间素材组是主要拖累。",
    recommendation: "不建议立即全面加预算；先对高转化素材组执行 7 天限额测试，并设置 ROI 2.5 停止条件。",
    evidence: [
      { label: "广告 ROI v2", detail: "广告平台 + 店铺归因订单 / 截至 08:45" },
      { label: "GMV v3", detail: "吉客云已支付订单 / 截至 09:22" },
      { label: "广告预算审批制度 v2", detail: "第 4 章 / 测试预算审批" }
    ]
  }
};
