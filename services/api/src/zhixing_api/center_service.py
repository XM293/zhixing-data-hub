from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from zhixing_api.actor_context import ActorContext
from zhixing_api.center_schemas import (
    CenterCatalogGroup,
    CenterCatalogItem,
    CenterCatalogResponse,
    ScopeContextResponse,
)
from zhixing_api.database import Database
from zhixing_api.scope_context import build_scope_context


@dataclass(frozen=True, slots=True)
class CenterDefinition:
    key: str
    group_key: str
    group_label: str
    label: str
    short_label: str
    icon_key: str
    href: str
    required_permissions: tuple[str, ...]
    scope_level: str
    scene_node_key: str | None = None
    delivery_state: str = "implemented"


CENTER_CATALOG: tuple[CenterDefinition, ...] = (
    CenterDefinition(
        "digital-twin", "experience", "工作入口", "数字孪生", "数字孪生", "boxes",
        "/console/spatial", ("platform.navigation.read",), "group", "campus"
    ),
    CenterDefinition(
        "workspaces", "experience", "工作入口", "岗位工作台", "工作台", "layout-dashboard",
        "/console/workspaces", ("platform.navigation.read",), "enterprise"
    ),
    CenterDefinition(
        "inbox", "experience", "工作入口", "消息中心", "消息中心", "bell",
        "/console/inbox", ("notification.read",), "enterprise"
    ),
    CenterDefinition(
        "assistant", "experience", "工作入口", "企业助手", "企业助手", "sparkles",
        "/console/assistant", ("role-twin.invoke",), "enterprise"
    ),
    CenterDefinition(
        "data-foundation", "data", "数据中心", "数据基础", "数据基础", "database",
        "/console/data/foundation/sources",
        ("source.manage", "metric.definition.read"),
        "enterprise", "data-hall"
    ),
    CenterDefinition(
        "data-sync-jobs", "data", "数据中心", "同步任务", "同步任务", "refresh-cw",
        "/console/data/foundation/sync-jobs",
        ("source.manage", "metric.definition.read"),
        "enterprise", "data-hall"
    ),
    CenterDefinition(
        "data-entities", "data", "数据中心", "企业实体", "企业实体", "boxes",
        "/console/data/foundation/entities", ("metric.definition.read",), "enterprise", "data-hall"
    ),
    CenterDefinition(
        "data-metrics", "data", "数据中心", "指标目录", "指标目录", "chart-no-axes-combined",
        "/console/data/foundation/metrics", ("metric.definition.read",), "enterprise", "data-hall"
    ),
    CenterDefinition(
        "data-quality", "data", "数据中心", "数据质量", "数据质量", "shield-check",
        "/console/data/foundation/quality", ("metric.definition.read",), "enterprise", "data-hall"
    ),
    CenterDefinition(
        "data-reconciliation", "data", "数据中心", "对账看板", "对账看板", "scale",
        "/console/data/foundation/reconciliation", ("metric.query.execute",), "enterprise", "data-hall"
    ),
    CenterDefinition(
        "data-products", "data", "数据中心", "数据产品", "数据产品", "layers-3",
        "/console/data/products/commerce", ("metric.query.execute",), "enterprise", "data-hall"
    ),
    CenterDefinition(
        "data-customers", "data", "数据中心", "客户 360", "客户 360", "users-round",
        "/console/data/products/customers", ("customer.profile.read",), "enterprise", "data-hall"
    ),
    CenterDefinition(
        "insights", "insights", "经营管理", "经营洞察", "经营洞察", "chart-no-axes-combined",
        "/console/analysis/store-review", ("analysis.read", "metric.query.execute"),
        "enterprise", "operations-center"
    ),
    CenterDefinition(
        "insights-ask", "insights", "经营管理", "经营问数", "经营问数", "sparkles",
        "/console/analysis/ask", ("analysis.read",), "enterprise", "operations-center"
    ),
    CenterDefinition(
        "insights-review-plans", "insights", "经营管理", "巡店计划", "巡店计划", "calendar-check",
        "/console/analysis/review-plans", ("analysis.schedule.read",), "enterprise",
        "operations-center"
    ),
    CenterDefinition(
        "insights-briefs", "insights", "经营管理", "经营简报", "经营简报", "file-text",
        "/console/analysis/briefs", ("analysis.read",), "enterprise", "operations-center"
    ),
    CenterDefinition(
        "cockpit", "insights", "经营管理", "经营驾驶舱", "驾驶舱", "gauge", "/console/cockpit",
        ("metric.query.execute",), "group", "data-hall"
    ),
    CenterDefinition(
        "commerce", "business", "业务中心", "渠道与店铺", "渠道店铺", "store",
        "/console/commerce/stores", ("metric.query.execute",), "store", "operations-center"
    ),
    CenterDefinition(
        "customer-service", "business", "业务中心", "客户与服务", "客户服务", "headset",
        "/console/customer-service/conversations", ("customer-service.conversation.read",),
        "enterprise", "operations-center"
    ),
    CenterDefinition(
        "fulfillment", "business", "业务中心", "履约与仓储", "履约仓储", "warehouse",
        "/console/fulfillment", ("metric.query.execute",), "warehouse", "warehouse",
        delivery_state="unavailable"
    ),
    CenterDefinition(
        "knowledge", "governance", "治理中心", "知识中心", "知识中心", "book-open",
        "/console/knowledge/documents", ("knowledge.document.read",), "enterprise", "knowledge-hall"
    ),
    CenterDefinition(
        "knowledge-policies", "governance", "治理中心", "制度版本", "制度版本", "file-check",
        "/console/knowledge/policies", ("knowledge.document.read",), "enterprise", "knowledge-hall"
    ),
    CenterDefinition(
        "knowledge-ingestion", "governance", "治理中心", "导入任务", "导入任务", "file-up",
        "/console/knowledge/ingestion", ("knowledge.document.ingest",), "enterprise",
        "knowledge-hall"
    ),
    CenterDefinition(
        "knowledge-evidence", "governance", "治理中心", "引用与证据", "引用证据", "quote",
        "/console/knowledge/evidence", ("knowledge.document.read",), "enterprise", "knowledge-hall"
    ),
    CenterDefinition(
        "organization", "governance", "治理中心", "组织与绩效", "组织绩效", "users-round",
        "/console/people/organization", ("identity.user.manage",), "org_unit",
        delivery_state="unavailable"
    ),
    CenterDefinition(
        "decisions", "governance", "治理中心", "决策与会议", "决策会议", "messages-square",
        "/console/meetings", ("meeting.read",), "group", "decision-room"
    ),
    CenterDefinition(
        "execution", "governance", "治理中心", "流程与行动", "流程行动", "list-checks",
        "/console/actions/work", ("action.work.read", "action.propose"), "org_unit"
    ),
    CenterDefinition(
        "execution-proposals", "governance", "治理中心", "行动提议", "行动提议", "send",
        "/console/actions/proposals", ("action.propose",), "org_unit"
    ),
    CenterDefinition(
        "execution-approvals", "governance", "治理中心", "审批队列", "审批队列", "check-circle-2",
        "/console/actions/approvals", ("action.approve",), "org_unit"
    ),
    CenterDefinition(
        "execution-ledger", "governance", "治理中心", "执行台账", "执行台账", "clipboard-check",
        "/console/actions/executions", ("action.execute",), "org_unit"
    ),
    CenterDefinition(
        "ai", "ai", "智能中心", "AI 与自动化", "AI 中心", "bot", "/console/twins/instances",
        ("role-twin.read",), "enterprise", "ai-hall"
    ),
    CenterDefinition(
        "ai-templates", "ai", "智能中心", "岗位模板", "岗位模板", "file-text",
        "/console/twins/templates", ("role-twin.read",), "enterprise", "ai-hall"
    ),
    CenterDefinition(
        "ai-memories", "ai", "智能中心", "记忆审核", "记忆审核", "brain",
        "/console/twins/memories", ("memory.candidate.read",), "enterprise", "ai-hall"
    ),
    CenterDefinition(
        "ai-prompts", "ai", "智能中心", "配置版本", "配置版本", "sliders-horizontal",
        "/console/twins/prompts", ("role-twin.configure",), "enterprise", "ai-hall"
    ),
    CenterDefinition(
        "ai-test", "ai", "智能中心", "分身测试", "分身测试", "flask-conical",
        "/console/twins/test", ("role-twin.read",), "enterprise", "ai-hall"
    ),
    CenterDefinition(
        "ai-evaluations", "ai", "智能中心", "回归评测", "回归评测", "scale",
        "/console/twins/evaluations", ("evaluation.read",), "enterprise", "ai-hall"
    ),
    CenterDefinition(
        "ai-feedback", "ai", "智能中心", "反馈工单", "反馈工单", "message-square-warning",
        "/console/twins/feedback", ("agent-feedback.review",), "enterprise", "ai-hall"
    ),
    CenterDefinition(
        "ai-skills", "ai", "智能中心", "Skill 注册", "Skill 注册", "wrench",
        "/console/twins/skills", ("skill.registry.manage",), "enterprise", "ai-hall"
    ),
    CenterDefinition(
        "integrations", "platform", "平台中心", "集成与连接", "集成连接", "plug-zap",
        "/console/integrations", ("source.manage",), "enterprise", delivery_state="unavailable"
    ),
    CenterDefinition(
        "platform", "platform", "平台中心", "平台管理", "平台管理", "settings",
        "/console/admin/users",
        ("identity.user.manage", "identity.access.manage"),
        "enterprise"
    ),
    CenterDefinition(
        "platform-org", "platform", "平台中心", "用户组织", "用户组织", "users-round",
        "/console/admin/org", ("identity.user.manage",), "enterprise"
    ),
    CenterDefinition(
        "platform-access", "platform", "平台中心", "访问权限", "访问权限", "shield-check",
        "/console/admin/access", ("identity.access.manage",), "enterprise"
    ),
    CenterDefinition(
        "platform-channels", "platform", "平台中心", "渠道身份", "渠道身份", "fingerprint",
        "/console/admin/channels", ("identity.user.manage",), "enterprise"
    ),
    CenterDefinition(
        "platform-runtime", "platform", "平台中心", "AI 运行控制", "AI 运行", "server-cog",
        "/console/admin/ai-runtime", ("ai.provider.manage",), "enterprise"
    ),
    CenterDefinition(
        "platform-tools", "platform", "平台中心", "工具注册", "工具注册", "wrench",
        "/console/admin/tools", ("identity.access.manage",), "enterprise"
    ),
    CenterDefinition(
        "platform-jobs", "platform", "平台中心", "后台任务", "后台任务", "list-checks",
        "/console/admin/jobs", ("operations.run.read",), "enterprise"
    ),
    CenterDefinition(
        "platform-config", "platform", "平台中心", "参数字典", "参数字典", "settings-2",
        "/console/admin/config", ("platform.config.read",), "enterprise"
    ),
    CenterDefinition(
        "platform-files", "platform", "平台中心", "文件资产", "文件资产", "file-box",
        "/console/admin/files", ("file.asset.read",), "enterprise"
    ),
    CenterDefinition(
        "platform-exchange", "platform", "平台中心", "批量交换", "批量交换", "arrow-left-right",
        "/console/admin/exchange", ("bulk.exchange.read",), "enterprise"
    ),
    CenterDefinition(
        "platform-delegations", "platform", "平台中心", "访问委托", "访问委托", "user-round-cog",
        "/console/admin/delegations", ("identity.delegation.manage",), "enterprise"
    ),
    CenterDefinition(
        "platform-audit", "platform", "平台中心", "审计记录", "审计记录", "scroll-text",
        "/console/admin/audit", ("audit.event.read",), "enterprise"
    ),
)

GROUP_ORDER = {
    "experience": 10,
    "insights": 20,
    "data": 30,
    "business": 40,
    "governance": 50,
    "ai": 60,
    "platform": 70,
}


def center_catalog(database: Database, actor: ActorContext) -> CenterCatalogResponse:
    visible = [
        item
        for item in CENTER_CATALOG
        if item.delivery_state == "implemented"
        and (
            item.group_key != "platform"
            or bool({"identity.user.manage", "identity.access.manage"} & set(actor.permissions))
        )
        and any(permission in actor.permissions for permission in item.required_permissions)
    ]
    groups: dict[str, list[CenterCatalogItem]] = {}
    labels: dict[str, str] = {}
    for item in visible:
        groups.setdefault(item.group_key, []).append(
            CenterCatalogItem(
                key=item.key,
                group_key=item.group_key,
                label=item.label,
                short_label=item.short_label,
                icon_key=item.icon_key,
                href=item.href,
                delivery_state=item.delivery_state,  # type: ignore[arg-type]
                required_permissions=list(item.required_permissions),
                scope_level=item.scope_level,  # type: ignore[arg-type]
                scene_node_key=item.scene_node_key,
            )
        )
        labels[item.group_key] = item.group_label
    return CenterCatalogResponse(
        group_id=actor.group_id,
        enterprise_id=actor.enterprise_id,
        groups=[
            CenterCatalogGroup(
                key=key,
                label=labels[key],
                order=GROUP_ORDER.get(key, 999),
                items=items,
            )
            for key, items in sorted(groups.items(), key=lambda pair: GROUP_ORDER.get(pair[0], 999))
        ],
        resolved_at=datetime.now(UTC).isoformat(),
    )


def scope_context(database: Database, actor: ActorContext) -> ScopeContextResponse:
    context = build_scope_context(database, actor)
    return ScopeContextResponse.model_validate(context.snapshot())
