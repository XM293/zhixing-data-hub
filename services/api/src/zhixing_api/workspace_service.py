from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from zhixing_api.action_service import list_action_proposals, list_action_work_items
from zhixing_api.actor_context import ActorContext, actor_scope_allows
from zhixing_api.data_center_schemas import TwinOverviewResponse
from zhixing_api.data_center_service import build_overview
from zhixing_api.data_selection import require_selected_data_scope
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.identity_service import current_identity, navigation_projection
from zhixing_api.scope_context import build_scope_context
from zhixing_api.workspace_schemas import (
    WorkspaceActivityView,
    WorkspaceAttentionView,
    WorkspaceCatalogResponse,
    WorkspaceFreshnessView,
    WorkspaceMetricView,
    WorkspaceProfileView,
    WorkspaceQuickActionView,
    WorkspaceReadModelResponse,
    WorkspaceSceneView,
    WorkspaceScopeView,
)


@dataclass(frozen=True, slots=True)
class WorkspaceDefinition:
    key: str
    label: str
    audience: tuple[str, ...]
    default_route: str
    navigation_keys: tuple[str, ...]
    metric_keys: tuple[str, ...]
    attention_query_keys: tuple[str, ...]
    quick_action_keys: tuple[str, ...]
    scene_key: str | None
    scene_label: str | None
    scene_object_refs: tuple[str, ...]
    scene_layers: tuple[str, ...]


WORKSPACE_CATALOG: tuple[WorkspaceDefinition, ...] = (
    WorkspaceDefinition(
        key="executive",
        label="企业决策中心",
        audience=("ceo", "executive"),
        default_route="/console/workspaces/executive",
        navigation_keys=(
            "home",
            "cockpit",
            "data",
            "analysis",
            "meetings",
            "actions",
            "knowledge",
            "twins",
        ),
        metric_keys=(
            "gmv_today",
            "orders_today",
            "refund_rate",
            "ad_roi",
            "active_members",
            "low_stock_skus",
        ),
        attention_query_keys=(
            "commerce_anomalies",
            "decision_pending",
            "action_pending",
            "data_freshness",
        ),
        quick_action_keys=(
            "ask_analysis",
            "view_anomalies",
            "start_meeting",
            "review_decision",
            "review_actions",
        ),
        scene_key="enterprise-campus",
        scene_label="企业园区",
        scene_object_refs=("campus", "operations-center", "warehouse", "decision-room"),
        scene_layers=("data-flow", "business-health", "meeting-presence"),
    ),
    WorkspaceDefinition(
        key="manager",
        label="部门经营工作台",
        audience=("manager", "department-manager"),
        default_route="/console/workspaces/manager",
        navigation_keys=(
            "home",
            "cockpit",
            "data",
            "analysis",
            "actions",
            "meetings",
            "knowledge",
            "twins",
        ),
        metric_keys=("gmv_today", "orders_today", "refund_rate", "ad_roi", "low_stock_skus"),
        attention_query_keys=(
            "commerce_anomalies",
            "team_work",
            "action_pending",
            "policy_updates",
        ),
        quick_action_keys=(
            "view_anomalies",
            "run_store_review",
            "assign_work",
            "review_actions",
            "start_meeting",
        ),
        scene_key="enterprise-campus",
        scene_label="经营空间",
        scene_object_refs=("operations-center", "warehouse", "decision-room"),
        scene_layers=("business-health", "work-items"),
    ),
    WorkspaceDefinition(
        key="operator",
        label="店铺运营工作台",
        audience=("employee", "operator", "store-operator"),
        default_route="/console/workspaces/operator",
        navigation_keys=("home", "data", "analysis", "actions", "knowledge"),
        metric_keys=("gmv_today", "orders_today", "refund_rate", "ad_roi", "low_stock_skus"),
        attention_query_keys=("commerce_anomalies", "my_work", "data_freshness"),
        quick_action_keys=("view_anomalies", "run_store_review", "open_work", "ask_analysis"),
        scene_key="warehouse-interior",
        scene_label="店铺与仓储",
        scene_object_refs=("warehouse", "operations-center"),
        scene_layers=("business-health", "inventory", "work-items"),
    ),
    WorkspaceDefinition(
        key="service",
        label="客服工作台",
        audience=("service", "customer-service"),
        default_route="/console/workspaces/service",
        navigation_keys=("home", "data", "customer-service", "knowledge", "actions"),
        metric_keys=("orders_today", "refund_rate"),
        attention_query_keys=("service_queue", "service_risk", "policy_updates"),
        quick_action_keys=("open_service_queue", "draft_reply", "open_work", "ask_policy"),
        scene_key="enterprise-campus",
        scene_label="客服作战室",
        scene_object_refs=("operations-center",),
        scene_layers=("service-queue", "work-items"),
    ),
    WorkspaceDefinition(
        key="finance",
        label="财务经营工作台",
        audience=("finance", "finance-manager"),
        default_route="/console/workspaces/finance",
        navigation_keys=("home", "cockpit", "data", "analysis", "actions", "knowledge", "meetings"),
        metric_keys=("gmv_today", "refund_rate", "ad_roi"),
        attention_query_keys=("reconciliation", "action_pending", "commerce_anomalies"),
        quick_action_keys=(
            "open_reconciliation",
            "view_anomalies",
            "review_actions",
            "ask_analysis",
        ),
        scene_key="enterprise-campus",
        scene_label="经营空间",
        scene_object_refs=("operations-center", "data-hall"),
        scene_layers=("business-health", "data-quality"),
    ),
    WorkspaceDefinition(
        key="people",
        label="制度与绩效工作台",
        audience=("people", "hr", "policy-owner"),
        default_route="/console/workspaces/people",
        navigation_keys=("home", "knowledge", "twins", "meetings", "actions"),
        metric_keys=(),
        attention_query_keys=("policy_updates", "memory_review", "team_work"),
        quick_action_keys=("publish_policy", "review_memory", "open_work", "start_meeting"),
        scene_key="enterprise-campus",
        scene_label="组织与制度空间",
        scene_object_refs=("operations-center",),
        scene_layers=("policy-status", "work-items"),
    ),
    WorkspaceDefinition(
        key="data-governance",
        label="数据治理工作台",
        audience=("data-governance", "data-admin"),
        default_route="/console/workspaces/data-governance",
        navigation_keys=("home", "data", "cockpit"),
        metric_keys=(),
        attention_query_keys=("data_freshness", "data_quality", "mapping_gaps"),
        quick_action_keys=("refresh_data", "open_quality", "open_sources", "open_metrics"),
        scene_key="enterprise-campus",
        scene_label="数据中心",
        scene_object_refs=("data-hall", "operations-center"),
        scene_layers=("data-flow", "data-quality"),
    ),
    WorkspaceDefinition(
        key="platform-ops",
        label="平台运行工作台",
        audience=("admin", "platform-ops", "platform-admin"),
        default_route="/console/workspaces/platform-ops",
        navigation_keys=("home", "admin", "cockpit"),
        metric_keys=(),
        attention_query_keys=(
            "platform_health",
            "failed_jobs",
            "authorization_changes",
            "channel_status",
        ),
        quick_action_keys=(
            "open_jobs",
            "manage_users",
            "open_audit",
            "open_tools",
            "open_channels",
        ),
        scene_key="enterprise-campus",
        scene_label="平台运行空间",
        scene_object_refs=("data-hall", "operations-center"),
        scene_layers=("data-flow", "platform-health"),
    ),
    WorkspaceDefinition(
        key="ai-ops",
        label="AI 运行工作台",
        audience=("ai-ops", "ai-admin"),
        default_route="/console/workspaces/ai-ops",
        navigation_keys=("home", "admin", "twins", "knowledge", "cockpit"),
        metric_keys=(),
        attention_query_keys=("ai_runtime", "memory_review", "evaluation_drift"),
        quick_action_keys=("open_ai_runtime", "open_twins", "open_evaluations", "open_tools"),
        scene_key="enterprise-campus",
        scene_label="AI 运行空间",
        scene_object_refs=("data-hall",),
        scene_layers=("ai-runtime", "data-flow"),
    ),
)


@dataclass(frozen=True, slots=True)
class QuickActionDefinition:
    key: str
    label: str
    href: str
    required_permission: str | None


QUICK_ACTIONS: dict[str, QuickActionDefinition] = {
    "ask_analysis": QuickActionDefinition(
        "ask_analysis", "向企业助手提问", "/console/assistant", "role-twin.invoke"
    ),
    "ask_policy": QuickActionDefinition(
        "ask_policy", "查询制度", "/console/assistant", "role-twin.invoke"
    ),
    "view_anomalies": QuickActionDefinition(
        "view_anomalies", "查看经营异常", "/console/analysis/store-review", "analysis.read"
    ),
    "run_store_review": QuickActionDefinition(
        "run_store_review", "提交店铺诊断", "/console/analysis/store-review", "analysis.run"
    ),
    "start_meeting": QuickActionDefinition(
        "start_meeting", "发起数字会议", "/console/meetings", "meeting.start"
    ),
    "review_decision": QuickActionDefinition(
        "review_decision", "查看决策包", "/console/meetings", "meeting.read"
    ),
    "review_actions": QuickActionDefinition(
        "review_actions", "处理行动审批", "/console/actions/approvals", "action.approve"
    ),
    "assign_work": QuickActionDefinition(
        "assign_work", "分派运营工作", "/console/actions/work", "action.work.manage"
    ),
    "open_work": QuickActionDefinition(
        "open_work", "打开我的工作", "/console/actions/work", "action.work.read"
    ),
    "open_service_queue": QuickActionDefinition(
        "open_service_queue",
        "打开客服队列",
        "/console/customer-service/conversations",
        "customer-service.conversation.read",
    ),
    "draft_reply": QuickActionDefinition(
        "draft_reply",
        "生成回复草稿",
        "/console/customer-service/drafts",
        "customer-service.reply.draft",
    ),
    "publish_policy": QuickActionDefinition(
        "publish_policy", "发布制度版本", "/console/knowledge/policies", "knowledge.policy.publish"
    ),
    "review_memory": QuickActionDefinition(
        "review_memory", "审核记忆候选", "/console/twins/memories", "memory.candidate.review"
    ),
    "open_reconciliation": QuickActionDefinition(
        "open_reconciliation", "查看对账队列", "/console/data/quality", "metric.definition.read"
    ),
    "refresh_data": QuickActionDefinition(
        "refresh_data", "刷新数据源", "/console/data/sources", "source.manage"
    ),
    "open_quality": QuickActionDefinition(
        "open_quality", "查看数据质量", "/console/data/quality", "metric.definition.read"
    ),
    "open_sources": QuickActionDefinition(
        "open_sources", "管理数据源", "/console/data/sources", "source.manage"
    ),
    "open_metrics": QuickActionDefinition(
        "open_metrics", "查看指标目录", "/console/data/metrics", "metric.definition.read"
    ),
    "open_jobs": QuickActionDefinition(
        "open_jobs", "查看后台任务", "/console/admin/jobs", "operations.run.read"
    ),
    "manage_users": QuickActionDefinition(
        "manage_users", "管理用户账号", "/console/admin/users", "identity.user.manage"
    ),
    "open_audit": QuickActionDefinition(
        "open_audit", "查看审计记录", "/console/admin/audit", "audit.event.read"
    ),
    "open_tools": QuickActionDefinition(
        "open_tools", "管理工具注册", "/console/admin/tools", "identity.access.manage"
    ),
    "open_channels": QuickActionDefinition(
        "open_channels", "管理渠道身份", "/console/admin/channels", "identity.user.manage"
    ),
    "open_ai_runtime": QuickActionDefinition(
        "open_ai_runtime", "查看 AI 运行", "/console/admin/ai-runtime", "ai.provider.manage"
    ),
    "open_twins": QuickActionDefinition(
        "open_twins", "管理角色分身", "/console/twins/instances", "role-twin.read"
    ),
    "open_evaluations": QuickActionDefinition(
        "open_evaluations", "运行分身评测", "/console/twins/evaluations", "evaluation.read"
    ),
}


ROLE_WORKSPACE_KEYS: dict[str, tuple[str, ...]] = {
    "ceo": ("executive",),
    "executive": ("executive",),
    "operations-manager": ("manager",),
    "manager": ("manager",),
    "department-manager": ("manager",),
    "employee": ("operator",),
    "operator": ("operator",),
    "store-operator": ("operator",),
    "service": ("service",),
    "service-agent": ("service",),
    "customer-service": ("service",),
    "finance": ("finance",),
    "finance-controller": ("finance",),
    "finance-manager": ("finance",),
    "people": ("people",),
    "hr": ("people",),
    "policy-owner": ("people",),
    "data-admin": ("data-governance",),
    "data-governance": ("data-governance",),
    "admin": ("platform-ops",),
    "platform-admin": ("platform-ops",),
    "platform-ops": ("platform-ops",),
    "ai-admin": ("ai-ops",),
    "ai-ops": ("ai-ops",),
}


def workspace_definition(key: str) -> WorkspaceDefinition:
    for definition in WORKSPACE_CATALOG:
        if definition.key == key:
            return definition
    raise KeyError(key)


def resolve_workspace_for_actor(
    actor: ActorContext,
    workspace_key: str | None,
) -> WorkspaceDefinition | None:
    """Validate a client-selected workspace without changing the actor scope.

    Workspace selection is an intent only.  Every caller still uses the same
    ActorContext and domain permission checks after this validation.
    """
    if workspace_key is None:
        return None
    try:
        definition = workspace_definition(workspace_key)
    except KeyError as exc:
        raise ApiProblem(
            status_code=404,
            code="workspace.not_found",
            message="没有找到指定工作空间",
            details={"workspace_key": workspace_key},
        ) from exc
    if definition not in _available_definitions(actor):
        raise ApiProblem(
            status_code=403,
            code="workspace.not_allowed",
            message="当前账号未获得该工作空间",
            details={"workspace_key": workspace_key},
        )
    return definition


def actor_snapshot_with_workspace(
    actor: ActorContext,
    workspace_key: str | None,
) -> dict[str, object]:
    """Return a replayable actor snapshot with optional workspace intent."""
    snapshot = actor.snapshot()
    if workspace_key:
        snapshot["workspace_key"] = workspace_key
        try:
            snapshot["workspace_label"] = workspace_definition(workspace_key).label
        except KeyError:
            # Boundary callers validate the key; keeping this defensive makes
            # internal workers safe if they receive an old snapshot.
            snapshot["workspace_label"] = workspace_key
    return snapshot


def _available_definitions(actor: ActorContext) -> list[WorkspaceDefinition]:
    keys = list(ROLE_WORKSPACE_KEYS.get(actor.role_id, ()))
    for access_role_key in actor.access_role_keys:
        keys.extend(ROLE_WORKSPACE_KEYS.get(access_role_key, ()))
    if actor.role_id == "admin" and "ai.provider.manage" in actor.permissions:
        keys.append("ai-ops")
    if (
        actor.role_id in {"manager", "ceo", "finance", "data-admin"}
        and "metric.definition.read" in actor.permissions
    ):
        if actor.role_id == "data-admin":
            keys.append("data-governance")
    seen: set[str] = set()
    definitions: list[WorkspaceDefinition] = []
    for key in keys:
        if key in seen:
            continue
        try:
            definition = workspace_definition(key)
        except KeyError:
            continue
        seen.add(key)
        definitions.append(definition)
    if definitions:
        return definitions
    return [workspace_definition("operator")]


def _scope_view(actor: ActorContext) -> WorkspaceScopeView:
    allowed = [scope for scope in actor.scopes if scope.effect == "allow"]
    if not allowed:
        return WorkspaceScopeView(
            kind="enterprise",
            keys=[actor.enterprise_id],
            label="当前企业授权范围",
            as_of=datetime.now(UTC),
        )
    primary = allowed[0]
    keys = sorted(
        {
            item
            for scope in allowed
            if scope.scope_type == primary.scope_type
            for item in scope.scope_ids
        }
    )
    if primary.scope_type == "enterprise":
        label = "企业全域"
    elif primary.scope_type == "store":
        label = f"授权店铺 {len(keys)} 个"
    elif primary.scope_type == "org_subtree":
        label = f"组织子树 {len(keys)} 个"
    elif primary.scope_type == "self":
        label = "本人范围"
    else:
        label = f"授权范围 {len(keys)} 项"
    return WorkspaceScopeView(
        kind=primary.scope_type,
        keys=keys,
        label=label,
        as_of=datetime.now(UTC),
    )


def _profile_view(definition: WorkspaceDefinition) -> WorkspaceProfileView:
    return WorkspaceProfileView(
        key=definition.key,  # type: ignore[arg-type]
        label=definition.label,
        audience=list(definition.audience),
        default_route=definition.default_route,
        navigation_keys=list(definition.navigation_keys),
        metric_keys=list(definition.metric_keys),
        attention_query_keys=list(definition.attention_query_keys),
        quick_action_keys=list(definition.quick_action_keys),
        scene_key=definition.scene_key,
        layout_version=1,
        delivery_state="implemented",
    )


def list_workspaces(actor: ActorContext) -> WorkspaceCatalogResponse:
    definitions = _available_definitions(actor)
    return WorkspaceCatalogResponse(
        default_workspace_key=definitions[0].key,  # type: ignore[arg-type]
        workspaces=[_profile_view(item) for item in definitions],
        scope=_scope_view(actor),
        generated_at=datetime.now(UTC),
    )


def get_workspace_profile(actor: ActorContext, workspace_key: str) -> WorkspaceProfileView:
    definition = resolve_workspace_for_actor(actor, workspace_key)
    if definition is None:
        raise KeyError(workspace_key)
    return _profile_view(definition)


def _metric_status(metric_key: str, change_rate: float | None) -> tuple[str, str]:
    if change_rate is None:
        return "neutral", "当前快照"
    adverse = metric_key in {"refund_rate", "low_stock_skus"}
    rising = change_rate > 0
    if (adverse and rising) or (not adverse and not rising):
        return "warning", "较上一周期需要关注"
    return "positive", "较上一周期改善"


def _metric_views(
    definition: WorkspaceDefinition,
    overview: TwinOverviewResponse,
    actor: ActorContext,
) -> list[WorkspaceMetricView]:
    if "metric.query.execute" not in actor.permissions:
        return []
    metrics = getattr(overview, "metrics", [])
    result: list[WorkspaceMetricView] = []
    for metric in metrics:
        if metric.key not in definition.metric_keys:
            continue
        status, reason = _metric_status(metric.key, metric.change_rate)
        href = (
            "/console/data/commerce"
            if metric.key != "active_members"
            else "/console/data/customers"
        )
        result.append(
            WorkspaceMetricView(
                key=metric.key,
                label=metric.label,
                value=metric.value,
                unit=metric.unit,
                change_rate=metric.change_rate,
                as_of=metric.as_of,
                status=status,  # type: ignore[arg-type]
                status_reason=reason,
                href=href,
                evidence_refs=[f"metric:{metric.key}:{metric.as_of.isoformat()}"],
            )
        )
    return result


def _event_attention(
    definition: WorkspaceDefinition,
    overview: TwinOverviewResponse,
    actor: ActorContext,
) -> list[WorkspaceAttentionView]:
    if "metric.query.execute" not in actor.permissions:
        return []
    result: list[WorkspaceAttentionView] = []
    for event in getattr(overview, "events", [])[:8]:
        severity = (
            "critical"
            if event.severity == "critical"
            else "warning"
            if event.severity == "warning"
            else "info"
        )
        result.append(
            WorkspaceAttentionView(
                key=f"event:{event.id}",
                kind="anomaly",
                title=event.title,
                detail=event.detail,
                severity=severity,  # type: ignore[arg-type]
                status="待处理" if severity in {"critical", "warning"} else "已记录",
                href="/console/analysis/store-review",
                evidence_refs=[f"event:{event.id}"],
                as_of=event.occurred_at,
            )
        )
    return result


def _freshness(overview: TwinOverviewResponse) -> list[WorkspaceFreshnessView]:
    return [
        WorkspaceFreshnessView(
            key=source.key,
            label=source.name,
            status=source.status,
            as_of=source.last_sync_at,
            detail=(
                f"{source.source_record_count:,} 条来源记录 · {source.mapping_version}"
                if source.last_sync_at
                else "等待首次同步"
            ),
        )
        for source in getattr(overview, "sources", [])
    ]


def _quick_actions(
    definition: WorkspaceDefinition,
    actor: ActorContext,
) -> list[WorkspaceQuickActionView]:
    result: list[WorkspaceQuickActionView] = []
    for key in definition.quick_action_keys:
        action = QUICK_ACTIONS.get(key)
        if action is None:
            continue
        enabled = (
            action.required_permission is None or action.required_permission in actor.permissions
        )
        result.append(
            WorkspaceQuickActionView(
                key=action.key,
                label=action.label,
                href=action.href,
                required_permission=action.required_permission,
                enabled=enabled,
                disabled_reason=None if enabled else "当前账号未获得该操作权限",
            )
        )
    return result


def _scene(
    definition: WorkspaceDefinition,
    overview: TwinOverviewResponse,
) -> WorkspaceSceneView | None:
    if definition.scene_key is None:
        return None
    available_scenes = {item.key for item in getattr(overview, "scenes", [])}
    return WorkspaceSceneView(
        key=definition.scene_key,
        label=definition.scene_label or definition.scene_key,
        route="/console/spatial",
        enabled=definition.scene_key in available_scenes,
        object_refs=list(definition.scene_object_refs),
        layer_keys=list(definition.scene_layers),
    )


def _actions_and_work(
    database: Database,
    definition: WorkspaceDefinition,
    actor: ActorContext,
) -> tuple[list[WorkspaceAttentionView], list[WorkspaceAttentionView]]:
    decisions: list[WorkspaceAttentionView] = []
    work_items: list[WorkspaceAttentionView] = []
    if {"action.approve", "action.propose", "action.work.read"} & set(actor.permissions):
        try:
            proposals = list_action_proposals(database, actor)
        except ApiProblem:
            proposals = None
        if proposals is not None:
            for proposal in proposals.items[:8]:
                if proposal.status == "pending_approval":
                    decisions.append(
                        WorkspaceAttentionView(
                            key=f"proposal:{proposal.key}",
                            kind="approval",
                            title=proposal.title,
                            detail=f"{proposal.owner} · {proposal.kpi}",
                            severity="high",
                            status="待审批",
                            href="/console/actions/approvals",
                            evidence_refs=list(proposal.evidence_refs),
                            as_of=proposal.created_at,
                        )
                    )
    if "action.work.read" in actor.permissions:
        try:
            items = list_action_work_items(database, actor)
        except ApiProblem:
            items = None
        if items is not None:
            for item in items.items[:8]:
                if item.status in {"ready", "claimed", "in_progress", "blocked"}:
                    work_items.append(
                        WorkspaceAttentionView(
                            key=f"work:{item.key}",
                            kind="work",
                            title=item.title,
                            detail=f"{item.owner_role} · {item.due_hint}",
                            severity="high" if item.status == "blocked" else "info",
                            status=item.status,
                            href="/console/actions/work",
                            evidence_refs=list(item.result_evidence_refs),
                            as_of=item.updated_at,
                        )
                    )
    return decisions, work_items


def _workspace_activities(overview: TwinOverviewResponse) -> list[WorkspaceActivityView]:
    return [
        WorkspaceActivityView(
            key=f"event:{event.id}",
            kind=event.event_type,
            title=event.title,
            detail=event.detail,
            status=event.severity,
            href="/console/cockpit",
            occurred_at=event.occurred_at,
        )
        for event in getattr(overview, "events", [])[:6]
    ]


def build_workspace_read_model(
    database: Database,
    actor: ActorContext,
    workspace_key: str,
) -> WorkspaceReadModelResponse:
    requested_definition = resolve_workspace_for_actor(actor, workspace_key)
    if requested_definition is None:
        raise KeyError(workspace_key)
    definition = requested_definition
    scope = build_scope_context(database, actor)
    legacy_scope = actor_scope_allows(actor, scope_type="enterprise", scope_id=actor.enterprise_id)
    try:
        require_selected_data_scope(database, actor, "enterprise")
    except ApiProblem as exc:
        if exc.code != "scope.selection_denied":
            raise
        legacy_scope = False
    overview = build_overview(database, enterprise_id=actor.enterprise_id) if legacy_scope else None
    identity = current_identity(database, actor)
    navigation = [
        section
        for section in navigation_projection(actor.permissions)
        if section.key in definition.navigation_keys
    ]
    decisions, work_items = (_actions_and_work(database, definition, actor)
                            if legacy_scope else ([], []))
    attention = _event_attention(definition, overview, actor) if overview else []
    latest_sync = overview.latest_sync if overview else None
    if latest_sync is not None and latest_sync.status in {"failed", "partial"}:
        if {"source.manage", "operations.run.read"} & set(actor.permissions):
            attention.append(
                WorkspaceAttentionView(
                    key=f"sync:{latest_sync.id}",
                    kind="system",
                    title="最近同步需要处理",
                    detail=latest_sync.error or latest_sync.warning or "同步批次存在异常",
                    severity="high" if latest_sync.status == "failed" else "warning",
                    status=latest_sync.status,
                    href="/console/data/sync-jobs",
                    evidence_refs=[f"sync:{latest_sync.id}"],
                    as_of=latest_sync.finished_at or latest_sync.started_at,
                )
            )
    attention.sort(
        key=lambda item: (
            item.severity not in {"critical", "high"},
            item.as_of or datetime.min.replace(tzinfo=UTC),
        ),
        reverse=False,
    )
    return WorkspaceReadModelResponse(
        workspace=_profile_view(definition),
        actor_name=actor.display_name,
        actor_position=identity.actor.position,
        actor_organization=identity.actor.organization,
        scope=_scope_view(actor) if legacy_scope else WorkspaceScopeView(
            kind=scope.scope_level,
            keys=list(scope.store_ids if scope.scope_level == "store" else
                      scope.warehouse_ids if scope.scope_level == "warehouse" else
                      scope.business_unit_ids if scope.scope_level == "business_unit" else
                      scope.selected_enterprise_ids),
            label=(scope.group_name or "集团") if scope.scope_level == "group"
                  else "当前所选授权范围", as_of=datetime.now(UTC)),
        scope_context=scope.snapshot(),
        navigation=navigation,
        metrics=_metric_views(definition, overview, actor) if overview else [],
        attention=attention[:12],
        decisions=decisions[:8],
        work_items=work_items[:8],
        activities=_workspace_activities(overview) if overview else [],
        freshness=_freshness(overview) if overview else [],
        quick_actions=_quick_actions(definition, actor),
        scene=_scene(definition, overview) if overview else None,
        generated_at=datetime.now(UTC),
    )
