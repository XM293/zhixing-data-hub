from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from sqlalchemy import func, or_, select

from zhixing_api.actor_context import ActorContext
from zhixing_api.data_models import (
    AccessRole,
    AccessRolePermission,
    AuthorizationDecision,
    Enterprise,
    IdentityCatalogEvent,
    IdentityManagementEvent,
    Membership,
    OrgUnit,
    PermissionDefinition,
    Position,
    Principal,
    RoleAssignment,
    ScopeGrant,
    UserAccount,
)
from zhixing_api.database import Database
from zhixing_api.identity_schemas import (
    AccessRoleView,
    ActorScopeView,
    AuthorizationDecisionView,
    CurrentActorView,
    CurrentIdentityResponse,
    IdentityAdminOverviewResponse,
    IdentityCatalogEventView,
    IdentityManagementEventView,
    IdentityRoleAssignmentView,
    IdentityScopeGrantView,
    IdentityStats,
    NavigationItemView,
    NavigationSectionView,
    OrgUnitView,
    PermissionDefinitionView,
    PositionView,
    UserAccountView,
)


@dataclass(frozen=True)
class _NavigationItemDefinition:
    key: str
    label: str
    href: str
    required_permission: str | None = None


@dataclass(frozen=True)
class _NavigationSectionDefinition:
    key: str
    label: str
    short_label: str
    href: str
    icon_key: str
    delivery_state: Literal["prototype", "implemented", "unavailable"]
    required_permissions: tuple[str, ...]
    items: tuple[_NavigationItemDefinition, ...]
    group_key: str = "platform"


_NAVIGATION_CATALOG = (
    _NavigationSectionDefinition(
        "home",
        "工作台",
        "工作台",
        "/console",
        "layout-dashboard",
        "implemented",
        ("platform.navigation.read",),
        (
            _NavigationItemDefinition("home", "角色首页", "/console", "platform.navigation.read"),
            _NavigationItemDefinition("inbox", "消息中心", "/console/inbox", "notification.read"),
            _NavigationItemDefinition(
                "assistant", "企业助手", "/console/assistant", "role-twin.invoke"
            ),
        ),
    ),
    _NavigationSectionDefinition(
        "cockpit",
        "企业经营驾驶舱",
        "经营驾驶舱",
        "/console/cockpit",
        "gauge",
        "implemented",
        ("metric.query.execute",),
        (
            _NavigationItemDefinition(
                "cockpit", "全域经营态势", "/console/cockpit", "metric.query.execute"
            ),
        ),
    ),
    _NavigationSectionDefinition(
        "data",
        "企业数据中心",
        "数据中心",
        "/console/data/sources",
        "database",
        "implemented",
        (
            "source.manage",
            "metric.definition.read",
            "metric.query.execute",
            "customer.profile.read",
        ),
        (
            _NavigationItemDefinition(
                "sources", "数据源", "/console/data/sources", "source.manage"
            ),
            _NavigationItemDefinition(
                "sync-jobs", "同步任务", "/console/data/sync-jobs", "source.manage"
            ),
            _NavigationItemDefinition(
                "commerce", "经营事实", "/console/data/commerce", "metric.query.execute"
            ),
            _NavigationItemDefinition(
                "customers", "客户 360", "/console/data/customers", "customer.profile.read"
            ),
            _NavigationItemDefinition(
                "entities", "企业实体", "/console/data/entities", "metric.definition.read"
            ),
            _NavigationItemDefinition(
                "metrics", "指标目录", "/console/data/metrics", "metric.definition.read"
            ),
            _NavigationItemDefinition(
                "quality", "数据质量", "/console/data/quality", "metric.definition.read"
            ),
        ),
    ),
    _NavigationSectionDefinition(
        "knowledge",
        "企业知识中心",
        "知识中心",
        "/console/knowledge/documents",
        "book-open",
        "implemented",
        ("knowledge.document.read",),
        (
            _NavigationItemDefinition(
                "documents", "知识文档", "/console/knowledge/documents", "knowledge.document.read"
            ),
            _NavigationItemDefinition(
                "policies", "制度版本", "/console/knowledge/policies", "knowledge.document.read"
            ),
            _NavigationItemDefinition(
                "ingestion", "导入任务", "/console/knowledge/ingestion", "knowledge.document.ingest"
            ),
            _NavigationItemDefinition(
                "evidence", "引用与证据", "/console/knowledge/evidence", "knowledge.document.read"
            ),
        ),
    ),
    _NavigationSectionDefinition(
        "twins",
        "角色分身中心",
        "分身中心",
        "/console/twins/instances",
        "bot",
        "implemented",
        ("role-twin.read", "skill.registry.manage"),
        (
            _NavigationItemDefinition(
                "templates", "岗位模板", "/console/twins/templates", "role-twin.read"
            ),
            _NavigationItemDefinition(
                "instances", "分身实例", "/console/twins/instances", "role-twin.read"
            ),
            _NavigationItemDefinition(
                "memories", "记忆审核", "/console/twins/memories", "memory.candidate.read"
            ),
            _NavigationItemDefinition(
                "prompts", "配置版本", "/console/twins/prompts", "role-twin.configure"
            ),
            _NavigationItemDefinition("test", "分身测试", "/console/twins/test", "role-twin.read"),
            _NavigationItemDefinition(
                "evaluations", "回归评测", "/console/twins/evaluations", "evaluation.read"
            ),
            _NavigationItemDefinition(
                "feedback", "反馈工单", "/console/twins/feedback", "agent-feedback.review"
            ),
            _NavigationItemDefinition(
                "skills", "Skill 注册", "/console/twins/skills", "skill.registry.manage"
            ),
        ),
    ),
    _NavigationSectionDefinition(
        "meetings",
        "数字会议中心",
        "数字会议",
        "/console/meetings",
        "messages-square",
        "implemented",
        ("meeting.read",),
        (_NavigationItemDefinition("meetings", "会议与决策", "/console/meetings", "meeting.read"),),
    ),
    _NavigationSectionDefinition(
        "analysis",
        "智能分析中心",
        "智能分析",
        "/console/analysis/store-review",
        "chart",
        "implemented",
        ("metric.query.execute",),
        (
            _NavigationItemDefinition("ask", "经营问数", "/console/analysis/ask", "analysis.read"),
            _NavigationItemDefinition(
                "store-review", "店铺诊断", "/console/analysis/store-review", "analysis.read"
            ),
            _NavigationItemDefinition(
                "review-plans",
                "巡店计划",
                "/console/analysis/review-plans",
                "analysis.schedule.read",
            ),
            _NavigationItemDefinition(
                "briefs", "经营简报", "/console/analysis/briefs", "analysis.read"
            ),
        ),
    ),
    _NavigationSectionDefinition(
        "actions",
        "行动与执行中心",
        "行动中心",
        "/console/actions/work",
        "list-checks",
        "implemented",
        (
            "action.propose",
            "action.approve",
            "action.execute",
            "action.work.read",
            "action.work.update",
            "action.work.manage",
            "meeting.decision.confirm",
        ),
        (
            _NavigationItemDefinition(
                "work", "运营工作台", "/console/actions/work", "action.work.read"
            ),
            _NavigationItemDefinition(
                "proposals", "行动提议", "/console/actions/proposals", "action.propose"
            ),
            _NavigationItemDefinition(
                "approvals", "审批队列", "/console/actions/approvals", "action.approve"
            ),
            _NavigationItemDefinition(
                "executions", "执行台账", "/console/actions/executions", "action.execute"
            ),
        ),
    ),
    _NavigationSectionDefinition(
        "customer-service",
        "客服工作台",
        "客服工作台",
        "/console/customer-service/conversations",
        "headset",
        "implemented",
        ("customer-service.conversation.read",),
        (
            _NavigationItemDefinition(
                "conversations",
                "客户会话",
                "/console/customer-service/conversations",
                "customer-service.conversation.read",
            ),
            _NavigationItemDefinition(
                "drafts",
                "回复草稿",
                "/console/customer-service/drafts",
                "customer-service.reply.draft",
            ),
        ),
    ),
    _NavigationSectionDefinition(
        "admin",
        "平台管理",
        "平台管理",
        "/console/admin/users",
        "settings",
        "implemented",
        (
            "identity.user.manage",
            "identity.access.manage",
            "identity.delegation.manage",
            "ai.provider.manage",
            "audit.event.read",
            "platform.config.read",
            "operations.run.read",
            "file.asset.read",
            "bulk.exchange.read",
        ),
        (
            _NavigationItemDefinition(
                "users", "用户账号", "/console/admin/users", "identity.user.manage"
            ),
            _NavigationItemDefinition(
                "org", "组织岗位", "/console/admin/org", "identity.user.manage"
            ),
            _NavigationItemDefinition(
                "access", "访问权限", "/console/admin/access", "identity.access.manage"
            ),
            _NavigationItemDefinition(
                "channels", "渠道身份", "/console/admin/channels", "identity.user.manage"
            ),
            _NavigationItemDefinition(
                "ai-runtime", "AI 运行控制", "/console/admin/ai-runtime", "ai.provider.manage"
            ),
            _NavigationItemDefinition(
                "tools", "工具注册", "/console/admin/tools", "identity.access.manage"
            ),
            _NavigationItemDefinition(
                "jobs", "后台任务", "/console/admin/jobs", "operations.run.read"
            ),
            _NavigationItemDefinition(
                "config", "参数字典", "/console/admin/config", "platform.config.read"
            ),
            _NavigationItemDefinition(
                "files", "文件资产", "/console/admin/files", "file.asset.read"
            ),
            _NavigationItemDefinition(
                "exchange", "批量交换", "/console/admin/exchange", "bulk.exchange.read"
            ),
            _NavigationItemDefinition(
                "delegations",
                "访问委托",
                "/console/admin/delegations",
                "identity.delegation.manage",
            ),
            _NavigationItemDefinition(
                "audit", "审计记录", "/console/admin/audit", "audit.event.read"
            ),
        ),
    ),
)

_NAVIGATION_GROUPS = {
    "home": "experience",
    "cockpit": "insights",
    "data": "data-foundation",
    "knowledge": "knowledge",
    "twins": "ai",
    "meetings": "decisions",
    "analysis": "insights",
    "actions": "execution",
    "customer-service": "service",
    "admin": "platform",
}


def navigation_projection(permissions: frozenset[str]) -> list[NavigationSectionView]:
    projection: list[NavigationSectionView] = []
    for section in _NAVIGATION_CATALOG:
        if not any(permission in permissions for permission in section.required_permissions):
            continue
        items = [
            NavigationItemView(
                key=item.key,
                label=item.label,
                href=item.href,
                required_permission=item.required_permission,
            )
            for item in section.items
            if item.required_permission is None or item.required_permission in permissions
        ]
        if items:
            section_href = (
                section.href if any(item.href == section.href for item in items) else items[0].href
            )
            projection.append(
                NavigationSectionView(
                    key=section.key,
                    label=section.label,
                    short_label=section.short_label,
                    href=section_href,
                    icon_key=section.icon_key,
                    delivery_state=section.delivery_state,
                    group_key=_NAVIGATION_GROUPS.get(section.key, section.group_key),
                    items=items,
                )
            )
    return projection


def navigation_sections(permissions: frozenset[str]) -> list[str]:
    return [section.key for section in navigation_projection(permissions)]


def current_identity(database: Database, actor: ActorContext) -> CurrentIdentityResponse:
    with database.session() as session:
        enterprise = session.get(Enterprise, actor.enterprise_id)
        if enterprise is None:
            raise LookupError("企业身份边界不存在")
        membership = session.scalar(
            select(Membership)
            .where(Membership.id.in_(actor.membership_ids))
            .order_by(Membership.is_primary.desc())
        )
        organization = session.get(OrgUnit, membership.org_unit_id) if membership else None
        position = session.get(Position, membership.position_id) if membership else None
        navigation = navigation_projection(actor.permissions)
        return CurrentIdentityResponse(
            enterprise_id=enterprise.id,
            enterprise_name=enterprise.name,
            group_id=actor.group_id or enterprise.group_id,
            actor=CurrentActorView(
                principal_id=actor.principal_id,
                principal_key=actor.actor_key,
                account_id=actor.user_account_id,
                login_name=actor.login_name,
                display_name=actor.display_name,
                experience_role_key=actor.role_id,
                organization=organization.name if organization else "未设置组织",
                position=position.name if position else "未设置岗位",
                access_role_keys=list(actor.access_role_keys),
                permissions=sorted(actor.permissions),
                scopes=[
                    ActorScopeView(
                        scope_type=scope.scope_type,
                        scope_ids=list(scope.scope_ids),
                        effect=cast(Literal["allow", "deny"], scope.effect),
                    )
                    for scope in actor.scopes
                ],
                permission_set_version=actor.permission_set_version,
                authentication_method=actor.authentication_method,
                group_id=actor.group_id or enterprise.group_id,
            ),
            navigation_sections=[section.key for section in navigation],
            navigation=navigation,
            resolved_at=datetime.now(UTC),
        )


def identity_admin_overview(
    database: Database, *, enterprise_id: str
) -> IdentityAdminOverviewResponse:
    with database.session() as session:
        enterprise = session.get(Enterprise, enterprise_id)
        if enterprise is None:
            raise LookupError("企业身份边界不存在")
        now = datetime.now(UTC)

        principals = {
            item.id: item
            for item in session.scalars(
                select(Principal).where(Principal.enterprise_id == enterprise_id)
            )
        }
        org_units = list(
            session.scalars(
                select(OrgUnit)
                .where(OrgUnit.enterprise_id == enterprise_id)
                .order_by(OrgUnit.unit_type, OrgUnit.name)
            )
        )
        org_by_id = {item.id: item for item in org_units}
        positions = list(
            session.scalars(
                select(Position)
                .where(Position.enterprise_id == enterprise_id)
                .order_by(Position.position_level, Position.name)
            )
        )
        position_by_id = {item.id: item for item in positions}
        memberships = list(
            session.scalars(
                select(Membership).where(
                    Membership.enterprise_id == enterprise_id,
                    Membership.status == "active",
                    Membership.valid_from <= now,
                    or_(Membership.valid_to.is_(None), Membership.valid_to > now),
                )
            )
        )
        memberships_by_principal: dict[str, list[Membership]] = {}
        for item in memberships:
            memberships_by_principal.setdefault(item.principal_id, []).append(item)

        roles = list(
            session.scalars(
                select(AccessRole)
                .where(AccessRole.enterprise_id == enterprise_id)
                .order_by(AccessRole.name)
            )
        )
        role_by_id = {item.id: item for item in roles}
        assignments = list(
            session.scalars(
                select(RoleAssignment).where(
                    RoleAssignment.enterprise_id == enterprise_id,
                    RoleAssignment.status == "active",
                    RoleAssignment.valid_from <= now,
                    or_(RoleAssignment.valid_to.is_(None), RoleAssignment.valid_to > now),
                )
            )
        )
        assignments_by_principal: dict[str, list[RoleAssignment]] = {}
        for assignment_item in assignments:
            assignments_by_principal.setdefault(assignment_item.principal_id, []).append(
                assignment_item
            )
        grants = list(
            session.scalars(
                select(ScopeGrant).where(
                    ScopeGrant.enterprise_id == enterprise_id,
                    ScopeGrant.valid_from <= now,
                    or_(ScopeGrant.valid_to.is_(None), ScopeGrant.valid_to > now),
                )
            )
        )
        grants_by_assignment: dict[str, list[ScopeGrant]] = {}
        for grant_item in grants:
            grants_by_assignment.setdefault(grant_item.role_assignment_id, []).append(grant_item)

        accounts = list(
            session.scalars(
                select(UserAccount)
                .where(UserAccount.enterprise_id == enterprise_id)
                .order_by(UserAccount.local_login_name)
            )
        )
        user_views: list[UserAccountView] = []
        for account in accounts:
            principal = principals[account.principal_id]
            member = next(
                (
                    item
                    for item in memberships_by_principal.get(principal.id, [])
                    if item.is_primary
                ),
                None,
            )
            actor_assignments = assignments_by_principal.get(principal.id, [])
            actor_grants = [
                grant
                for assignment in actor_assignments
                for grant in grants_by_assignment.get(assignment.id, [])
            ]
            assignment_views = [
                IdentityRoleAssignmentView(
                    role_key=role_by_id[item.access_role_id].role_key,
                    role_name=role_by_id[item.access_role_id].name,
                    scopes=[
                        IdentityScopeGrantView(
                            scope_type=grant.scope_type,
                            scope_ids=list(grant.scope_ids),
                            effect=cast(Literal["allow", "deny"], grant.effect),
                        )
                        for grant in sorted(
                            grants_by_assignment.get(item.id, []),
                            key=lambda grant: grant.scope_type,
                        )
                    ],
                )
                for item in sorted(
                    actor_assignments,
                    key=lambda assignment: role_by_id[assignment.access_role_id].role_key,
                )
            ]
            user_views.append(
                UserAccountView(
                    account_id=account.id,
                    account_key=account.account_key,
                    login_name=account.local_login_name,
                    display_name=principal.display_name,
                    email=account.email,
                    experience_role_key=account.experience_role_key,
                    status=account.status,
                    authentication_source=account.authentication_source,
                    organization=(org_by_id[member.org_unit_id].name if member else "未设置组织"),
                    org_key=(org_by_id[member.org_unit_id].org_key if member else ""),
                    position=(position_by_id[member.position_id].name if member else "未设置岗位"),
                    position_key=(
                        position_by_id[member.position_id].position_key if member else ""
                    ),
                    access_roles=[
                        role_by_id[item.access_role_id].name for item in actor_assignments
                    ],
                    role_assignments=assignment_views,
                    scope_labels=[
                        f"{grant.scope_type}: {', '.join(grant.scope_ids)}"
                        for grant in actor_grants
                    ],
                    last_login_at=account.last_login_at,
                    version=account.version,
                )
            )

        permission_by_id = {item.id: item for item in session.scalars(select(PermissionDefinition))}
        permission_catalog = [
            PermissionDefinitionView(
                permission_key=item.permission_key,
                label=item.label,
                resource=item.resource,
                action=item.action,
                risk_level=item.risk_level,
                status=item.status,
            )
            for item in sorted(permission_by_id.values(), key=lambda value: value.permission_key)
        ]
        role_permission_links = list(session.scalars(select(AccessRolePermission)))
        role_views: list[AccessRoleView] = []
        for role in roles:
            role_permissions = [
                permission_by_id[item.permission_id].permission_key
                for item in role_permission_links
                if item.access_role_id == role.id and item.effect == "allow"
            ]
            role_assignments = [item for item in assignments if item.access_role_id == role.id]
            role_grants = [
                grant
                for assignment in role_assignments
                for grant in grants_by_assignment.get(assignment.id, [])
            ]
            role_views.append(
                AccessRoleView(
                    role_key=role.role_key,
                    name=role.name,
                    description=role.description,
                    version=role.version,
                    revision=role.revision,
                    status=role.status,
                    permission_count=len(role_permissions),
                    permissions=sorted(role_permissions),
                    assignment_count=len(role_assignments),
                    scope_types=sorted({grant.scope_type for grant in role_grants}),
                )
            )

        decisions = list(
            session.scalars(
                select(AuthorizationDecision)
                .where(AuthorizationDecision.enterprise_id == enterprise_id)
                .order_by(AuthorizationDecision.decided_at.desc())
                .limit(100)
            )
        )
        denied_count = int(
            session.scalar(
                select(func.count(AuthorizationDecision.id)).where(
                    AuthorizationDecision.enterprise_id == enterprise_id,
                    AuthorizationDecision.decision == "deny",
                )
            )
            or 0
        )
        decision_count = int(
            session.scalar(
                select(func.count(AuthorizationDecision.id)).where(
                    AuthorizationDecision.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        management_events = list(
            session.scalars(
                select(IdentityManagementEvent)
                .where(IdentityManagementEvent.enterprise_id == enterprise_id)
                .order_by(IdentityManagementEvent.occurred_at.desc())
                .limit(100)
            )
        )
        management_event_count = int(
            session.scalar(
                select(func.count(IdentityManagementEvent.id)).where(
                    IdentityManagementEvent.enterprise_id == enterprise_id
                )
            )
            or 0
        )
        catalog_events = list(
            session.scalars(
                select(IdentityCatalogEvent)
                .where(IdentityCatalogEvent.enterprise_id == enterprise_id)
                .order_by(IdentityCatalogEvent.occurred_at.desc())
                .limit(100)
            )
        )
        account_by_id = {item.id: item for item in accounts}
        # An actor can belong to another legal entity while acting here through group membership.
        # Only resolve names referenced by this legal entity's already-filtered audit records.
        audit_principal_ids = {item.actor_principal_id for item in decisions}
        audit_principal_ids.update(item.actor_principal_id for item in management_events)
        audit_principal_ids.update(item.target_principal_id for item in management_events)
        audit_principal_ids.update(item.actor_principal_id for item in catalog_events)
        audit_principals = {item.id: item for item in session.scalars(
            select(Principal).where(Principal.id.in_(audit_principal_ids)))}
        return IdentityAdminOverviewResponse(
            enterprise_id=enterprise.id,
            enterprise_name=enterprise.name,
            stats=IdentityStats(
                active_users=sum(item.status == "active" for item in accounts),
                org_units=len(org_units),
                positions=len(positions),
                access_roles=len(roles),
                permissions=len(permission_by_id),
                active_assignments=sum(item.status == "active" for item in assignments),
                authorization_decisions=decision_count,
                denied_decisions=denied_count,
                management_events=management_event_count,
            ),
            users=user_views,
            org_units=[
                OrgUnitView(
                    org_id=item.id,
                    org_key=item.org_key,
                    name=item.name,
                    unit_type=item.unit_type,
                    parent_name=(
                        org_by_id[item.parent_org_unit_id].name if item.parent_org_unit_id else None
                    ),
                    status=item.status,
                    version=item.version,
                    position_count=sum(position.org_unit_id == item.id for position in positions),
                    member_count=sum(member.org_unit_id == item.id for member in memberships),
                )
                for item in org_units
            ],
            positions=[
                PositionView(
                    position_key=item.position_key,
                    name=item.name,
                    position_level=item.position_level,
                    organization=org_by_id[item.org_unit_id].name,
                    org_key=org_by_id[item.org_unit_id].org_key,
                    status=item.status,
                    version=item.version,
                    member_count=sum(member.position_id == item.id for member in memberships),
                )
                for item in positions
            ],
            access_roles=role_views,
            permission_catalog=permission_catalog,
            recent_decisions=[
                AuthorizationDecisionView(
                    id=item.id,
                    request_id=item.request_id,
                    run_id=item.run_id,
                    actor_name=_principal_name(audit_principals, item.actor_principal_id),
                    permission_key=item.permission_key,
                    resource_type=item.resource_type,
                    resource_key=item.resource_key,
                    decision=cast(Literal["allow", "deny"], item.decision),
                    reason=item.reason,
                    policy_version=item.policy_version,
                    decided_at=item.decided_at,
                )
                for item in decisions
            ],
            recent_management_events=[
                IdentityManagementEventView(
                    id=item.id,
                    event_type=cast(
                        Literal["identity.user.created", "identity.user.configured"],
                        item.event_type,
                    ),
                    actor_name=_principal_name(audit_principals, item.actor_principal_id),
                    target_name=_principal_name(audit_principals, item.target_principal_id),
                    target_account_key=account_by_id[item.target_account_id].account_key,
                    changed_fields=list(item.changed_fields),
                    reason=item.reason,
                    request_id=item.request_id,
                    run_id=item.run_id,
                    occurred_at=item.occurred_at,
                )
                for item in management_events
            ],
            recent_catalog_events=[
                IdentityCatalogEventView(
                    id=item.id,
                    event_type=item.event_type,
                    target_type=item.target_type,
                    target_key=item.target_key,
                    actor_name=_principal_name(audit_principals, item.actor_principal_id),
                    changed_fields=list(item.changed_fields),
                    reason=item.reason,
                    request_id=item.request_id,
                    run_id=item.run_id,
                    occurred_at=item.occurred_at,
                )
                for item in catalog_events
            ],
            generated_at=datetime.now(UTC),
        )


def _principal_name(principals: dict[str, Principal], principal_id: str) -> str:
    principal = principals.get(principal_id)
    return principal.display_name if principal else "未知主体"
