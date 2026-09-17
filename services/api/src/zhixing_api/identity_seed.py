from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from zhixing_api.data_models import (
    AccessRole,
    AccessRolePermission,
    Membership,
    OrgUnit,
    PermissionDefinition,
    Position,
    Principal,
    RoleAssignment,
    ScopeGrant,
    UserAccount,
)

PERMISSIONS = [
    ("platform.navigation.read", "读取平台导航", "platform", "read", "R0"),
    ("identity.user.manage", "管理用户账号", "identity.user", "manage", "R2"),
    ("identity.access.manage", "管理访问权限", "identity.access", "manage", "R3"),
    ("knowledge.document.read", "读取企业知识", "knowledge.document", "read", "R0"),
    ("knowledge.document.ingest", "导入企业知识", "knowledge.document", "ingest", "R1"),
    ("knowledge.provider.evaluate", "评测知识 Provider", "knowledge.provider", "evaluate", "R1"),
    ("knowledge.policy.publish", "发布企业制度", "knowledge.policy", "publish", "R2"),
    ("memory.candidate.read", "读取记忆候选", "memory.candidate", "read", "R1"),
    ("memory.candidate.review", "审核记忆候选", "memory.candidate", "review", "R2"),
    ("role-twin.read", "读取角色分身", "role-twin", "read", "R0"),
    ("role-twin.configure", "配置角色分身", "role-twin", "configure", "R2"),
    ("role-twin.invoke", "调用角色分身", "role-twin", "invoke", "R0"),
    ("agent-feedback.submit", "提交智能体回答反馈", "agent-feedback", "submit", "R0"),
    ("agent-feedback.review", "处理人工接管工单", "agent-feedback", "review", "R2"),
    ("evaluation.read", "读取智能体回归评测", "evaluation", "read", "R1"),
    ("evaluation.run", "运行智能体回归评测", "evaluation", "run", "R2"),
    ("evaluation.manage", "治理智能体评测用例", "evaluation", "manage", "R2"),
    ("source.manage", "管理数据来源", "source", "manage", "R2"),
    ("metric.definition.read", "读取指标口径", "metric.definition", "read", "R0"),
    ("metric.query.execute", "执行指标查询", "metric.query", "execute", "R0"),
    ("customer.profile.read", "读取客户洞察", "customer.profile", "read", "R0"),
    ("analysis.read", "读取经营分析", "analysis", "read", "R0"),
    ("analysis.run", "运行经营分析", "analysis", "run", "R1"),
    ("analysis.schedule.read", "读取经营巡店计划与运行", "analysis.schedule", "read", "R0"),
    ("analysis.schedule.manage", "管理经营巡店计划", "analysis.schedule", "manage", "R2"),
    ("meeting.start", "发起数字会议", "meeting", "start", "R1"),
    ("meeting.read", "读取数字会议", "meeting", "read", "R0"),
    ("meeting.decision.confirm", "确认会议决策", "meeting.decision", "confirm", "R3"),
    ("action.propose", "创建行动提案", "action", "propose", "R1"),
    ("action.approve", "审批行动提案", "action", "approve", "R3"),
    ("action.execute", "执行已批行动", "action", "execute", "R3"),
    ("action.work.read", "读取授权范围内行动工作项", "action.work", "read", "R0"),
    ("action.work.update", "更新本人领取的行动工作项", "action.work", "update", "R1"),
    ("action.work.manage", "管理授权范围内行动工作项", "action.work", "manage", "R2"),
    ("operations.run.read", "读取平台运行记录", "operations.run", "read", "R0"),
    ("operations.run.manage", "管理后台任务", "operations.run", "manage", "R2"),
    ("platform.config.read", "读取平台配置", "platform.config", "read", "R0"),
    ("platform.config.manage", "管理平台配置", "platform.config", "manage", "R2"),
    ("notification.read", "读取本人通知", "notification", "read", "R0"),
    ("notification.publish", "发布企业通知", "notification", "publish", "R2"),
    ("file.asset.read", "读取文件资产", "file.asset", "read", "R0"),
    ("file.asset.manage", "管理文件资产", "file.asset", "manage", "R2"),
    ("bulk.exchange.read", "读取批量交换任务", "bulk.exchange", "read", "R1"),
    ("bulk.exchange.manage", "管理批量交换任务", "bulk.exchange", "manage", "R2"),
    (
        "identity.delegation.manage",
        "管理临时访问委托",
        "identity.delegation",
        "manage",
        "R3",
    ),
    ("ai.provider.manage", "管理 AI Provider", "ai.provider", "manage", "R2"),
    ("audit.event.read", "读取审计记录", "audit.event", "read", "R1"),
    (
        "customer-service.conversation.read",
        "读取客服会话",
        "customer-service.conversation",
        "read",
        "R1",
    ),
    (
        "customer-service.reply.draft",
        "生成客服回复草稿",
        "customer-service.reply",
        "draft",
        "R1",
    ),
    (
        "customer-service.reply.send",
        "发送已确认客服回复",
        "customer-service.reply",
        "send",
        "R2",
    ),
    (
        "customer-service.handoff.create",
        "创建客服人工接管",
        "customer-service.handoff",
        "create",
        "R1",
    ),
    ("memory.chat.ingest", "导入角色聊天记录", "memory.chat", "ingest", "R1"),
    ("memory.approved.retire", "停用长期记忆", "memory.approved", "retire", "R2"),
    ("skill.registry.manage", "管理企业 Skill", "skill.registry", "manage", "R2"),
]


def role_permission_id(role_key: str, permission_key: str) -> str:
    normalized_permission = permission_key.replace(".", "_").replace("-", "_")
    readable = f"role_permission_{role_key}_{normalized_permission}"
    if len(readable) <= 64:
        return readable
    digest = sha256(f"{role_key}:{permission_key}".encode()).hexdigest()[:48]
    return f"role_permission_{digest}"

ORG_UNITS = [
    ("org_group", "group", "知行电商集团", "enterprise", None),
    ("org_operations", "operations", "运营中心", "department", "org_group"),
    ("org_finance", "finance", "财务中心", "department", "org_group"),
    ("org_supply", "supply", "供应链中心", "department", "org_group"),
    ("org_service", "customer-service", "客户服务中心", "department", "org_group"),
    ("org_platform", "digital-platform", "数字平台中心", "department", "org_group"),
]

POSITIONS = [
    ("position_ceo", "ceo", "首席执行官", "executive", "org_group"),
    (
        "position_ops_manager",
        "operations-manager",
        "运营中心经理",
        "manager",
        "org_operations",
    ),
    (
        "position_ops_specialist",
        "operations-specialist",
        "运营专员",
        "specialist",
        "org_operations",
    ),
    (
        "position_finance_director",
        "finance-director",
        "财务负责人",
        "director",
        "org_finance",
    ),
    (
        "position_platform_admin",
        "platform-admin",
        "平台管理员",
        "specialist",
        "org_platform",
    ),
    (
        "position_service_agent",
        "service-agent",
        "客服专员",
        "specialist",
        "org_service",
    ),
]

ROLE_PERMISSIONS = {
    "executive": [
        "platform.navigation.read",
        "knowledge.document.read",
        "memory.candidate.read",
        "role-twin.read",
        "role-twin.configure",
        "role-twin.invoke",
        "agent-feedback.submit",
        "agent-feedback.review",
        "evaluation.read",
        "evaluation.run",
        "evaluation.manage",
        "metric.definition.read",
        "metric.query.execute",
        "customer.profile.read",
        "analysis.read",
        "analysis.run",
        "analysis.schedule.read",
        "analysis.schedule.manage",
        "meeting.start",
        "meeting.read",
        "meeting.decision.confirm",
        "action.propose",
        "action.work.read",
        "operations.run.read",
        "notification.read",
        "file.asset.read",
        "platform.config.read",
        "knowledge.policy.publish",
        "knowledge.provider.evaluate",
        "memory.candidate.review",
        "memory.approved.retire",
        "skill.registry.manage",
    ],
    "operations-manager": [
        "platform.navigation.read",
        "knowledge.document.read",
        "memory.candidate.read",
        "role-twin.read",
        "role-twin.invoke",
        "agent-feedback.submit",
        "agent-feedback.review",
        "evaluation.read",
        "metric.definition.read",
        "metric.query.execute",
        "customer.profile.read",
        "analysis.read",
        "analysis.run",
        "analysis.schedule.read",
        "analysis.schedule.manage",
        "meeting.start",
        "meeting.read",
        "action.propose",
        "action.approve",
        "action.work.read",
        "action.work.update",
        "action.work.manage",
        "operations.run.read",
        "notification.read",
        "file.asset.read",
        "knowledge.provider.evaluate",
    ],
    "employee": [
        "platform.navigation.read",
        "knowledge.document.read",
        "role-twin.invoke",
        "agent-feedback.submit",
        "metric.query.execute",
        "customer.profile.read",
        "analysis.read",
        "analysis.schedule.read",
        "action.work.read",
        "action.work.update",
        "notification.read",
    ],
    "platform-admin": [item[0] for item in PERMISSIONS],
    "service-agent": [
        "platform.navigation.read",
        "knowledge.document.read",
        "role-twin.invoke",
        "agent-feedback.submit",
        "agent-feedback.review",
        "customer-service.conversation.read",
        "customer.profile.read",
        "customer-service.reply.draft",
        "customer-service.reply.send",
        "customer-service.handoff.create",
        "notification.read",
    ],
    "finance-controller": [
        "platform.navigation.read",
        "knowledge.document.read",
        "role-twin.read",
        "role-twin.invoke",
        "agent-feedback.submit",
        "metric.definition.read",
        "metric.query.execute",
        "customer.profile.read",
        "analysis.read",
        "analysis.run",
        "analysis.schedule.read",
        "meeting.read",
        "meeting.decision.confirm",
        "action.approve",
        "action.work.read",
        "notification.read",
        "file.asset.read",
    ],
}

ACCESS_ROLES = [
    (
        "role_executive_v1",
        "executive",
        "企业经营负责人",
        "企业经营、会议决策与分身调用",
        "1.0.0",
    ),
    (
        "role_operations_manager_v1",
        "operations-manager",
        "运营中心经理",
        "运营范围经营查询、会议发起和行动审批",
        "1.0.0",
    ),
    (
        "role_employee_v1",
        "employee",
        "普通员工",
        "本人范围知识问答与经营指导",
        "1.0.0",
    ),
    (
        "role_platform_admin_v1",
        "platform-admin",
        "平台管理员",
        "账号权限、数据来源与运行审计；不包含业务决策权",
        "1.0.0",
    ),
    (
        "role_service_agent_v1",
        "service-agent",
        "客服专员",
        "本人会话读取与回复草稿",
        "1.0.0",
    ),
    (
        "role_finance_controller_v1",
        "finance-controller",
        "财务决策负责人",
        "财务范围经营查询、会议确认与行动审批",
        "1.0.0",
    ),
]

PEOPLE = [
    (
        "principal-ceo-lin",
        "account_ceo",
        "ceo",
        "ceo",
        "林知远 / CEO",
        "position_ceo",
        "role_executive_v1",
        [("enterprise", ["ent_zhixing_demo"])],
    ),
    (
        "principal-ops-manager-zhou",
        "account_manager",
        "manager",
        "manager",
        "周岚 / 运营经理",
        "position_ops_manager",
        "role_operations_manager_v1",
        [
            ("org_subtree", ["org_operations"]),
            ("store", ["store-flagship", "store-outlet"]),
            ("object", ["mtg-budget-20260825"]),
        ],
    ),
    (
        "principal-employee-demo",
        "account_employee",
        "employee",
        "employee",
        "陈曦 / 运营专员",
        "position_ops_specialist",
        "role_employee_v1",
        [("self", ["principal-employee-demo"]), ("store", ["store-flagship"])],
    ),
    (
        "principal-platform-admin",
        "account_admin",
        "admin",
        "admin",
        "叶川 / 平台管理员",
        "position_platform_admin",
        "role_platform_admin_v1",
        [("enterprise", ["ent_zhixing_demo"])],
    ),
    (
        "principal-service-demo",
        "account_service",
        "service",
        "service",
        "许然 / 客服专员",
        "position_service_agent",
        "role_service_agent_v1",
        [("self", ["principal-service-demo"]), ("business_unit", ["org_service"])],
    ),
    (
        "principal-finance-chen",
        "account_finance",
        "finance",
        "finance",
        "陈硕 / 财务负责人",
        "position_finance_director",
        "role_finance_controller_v1",
        [("enterprise", ["ent_zhixing_demo"]), ("org_subtree", ["org_finance"])],
    ),
]


def identity_seed_checksum_payload() -> dict[str, object]:
    return {
        "permissions": PERMISSIONS,
        "org_units": ORG_UNITS,
        "positions": POSITIONS,
        "access_roles": ACCESS_ROLES,
        "role_permissions": ROLE_PERMISSIONS,
        "people": PEOPLE,
    }


def seed_identity(
    session: Session,
    *,
    enterprise_id: str,
    now: datetime,
    bootstrap_password_hash: str | None = None,
) -> None:
    valid_from = datetime(2026, 1, 1, tzinfo=UTC)
    for permission_key, label, resource, action, risk_level in PERMISSIONS:
        permission_id = f"permission_{permission_key.replace('.', '_').replace('-', '_')}"
        permission_item = session.get(PermissionDefinition, permission_id)
        if permission_item is None:
            permission_item = PermissionDefinition(id=permission_id, permission_key=permission_key)
            session.add(permission_item)
        permission_item.label = label
        permission_item.resource = resource
        permission_item.action = action
        permission_item.risk_level = risk_level
        permission_item.status = "active"

    for org_id, org_key, name, unit_type, parent_id in ORG_UNITS:
        org_item = session.get(OrgUnit, org_id)
        if org_item is None:
            org_item = OrgUnit(id=org_id, enterprise_id=enterprise_id, org_key=org_key)
            session.add(org_item)
        org_item.name = name
        org_item.unit_type = unit_type
        org_item.parent_org_unit_id = parent_id
        org_item.status = "active"
        org_item.valid_from = valid_from
        org_item.valid_to = None

    for position_id, position_key, name, level, org_id in POSITIONS:
        position_item = session.get(Position, position_id)
        if position_item is None:
            position_item = Position(
                id=position_id,
                enterprise_id=enterprise_id,
                position_key=position_key,
                org_unit_id=org_id,
            )
            session.add(position_item)
        position_item.name = name
        position_item.position_level = level
        position_item.status = "active"
        position_item.valid_from = valid_from
        position_item.valid_to = None

    for role_id, role_key, name, description, version in ACCESS_ROLES:
        role_item = session.get(AccessRole, role_id)
        if role_item is None:
            role_item = AccessRole(
                id=role_id,
                enterprise_id=enterprise_id,
                role_key=role_key,
                created_at=now,
            )
            session.add(role_item)
        role_item.name = name
        role_item.description = description
        role_item.version = version
        role_item.status = "active"

    session.flush()
    permissions = {
        item.permission_key: item for item in session.scalars(select(PermissionDefinition))
    }
    roles = {item.role_key: item for item in session.scalars(select(AccessRole))}
    for role_key, permission_keys in ROLE_PERMISSIONS.items():
        role = roles[role_key]
        for permission_key in permission_keys:
            permission = permissions[permission_key]
            link = session.scalar(
                select(AccessRolePermission).where(
                    AccessRolePermission.access_role_id == role.id,
                    AccessRolePermission.permission_id == permission.id,
                )
            )
            if link is None:
                link = AccessRolePermission(
                    id=role_permission_id(role_key, permission_key),
                    access_role_id=role.id,
                    permission_id=permission.id,
                )
                session.add(link)
            link.effect = "allow"

    position_org = {position_id: org_id for position_id, _, _, _, org_id in POSITIONS}
    for (
        principal_id,
        account_id,
        login_name,
        experience_role_key,
        display_name,
        position_id,
        access_role_id,
        scopes,
    ) in PEOPLE:
        principal = session.get(Principal, principal_id)
        if principal is None:
            principal = Principal(
                id=principal_id,
                enterprise_id=enterprise_id,
                principal_key=principal_id,
                created_at=now,
            )
            session.add(principal)
        principal.principal_type = "human"
        principal.display_name = display_name
        principal.status = "active"
        principal.updated_at = now

        account = session.get(UserAccount, account_id)
        if account is None:
            account = UserAccount(
                id=account_id,
                enterprise_id=enterprise_id,
                principal_id=principal_id,
                account_key=account_id,
                created_at=now,
            )
            session.add(account)
        account.local_login_name = login_name
        account.experience_role_key = experience_role_key
        account.email = None
        if account.password_hash is None and bootstrap_password_hash is not None:
            account.password_hash = bootstrap_password_hash
        account.authentication_source = (
            "local-password" if account.password_hash else "unconfigured"
        )
        account.status = "active"
        account.updated_at = now

        org_id = position_org[position_id]
        membership_id = f"membership_{login_name}"
        membership = session.get(Membership, membership_id)
        if membership is None:
            membership = Membership(
                id=membership_id,
                enterprise_id=enterprise_id,
                principal_id=principal_id,
                org_unit_id=org_id,
                position_id=position_id,
            )
            session.add(membership)
        membership.membership_type = "primary"
        membership.is_primary = True
        membership.status = "active"
        membership.valid_from = valid_from
        membership.valid_to = None

        assignment_id = f"assignment_{login_name}"
        assignment = session.get(RoleAssignment, assignment_id)
        if assignment is None:
            assignment = RoleAssignment(
                id=assignment_id,
                enterprise_id=enterprise_id,
                principal_id=principal_id,
                access_role_id=access_role_id,
            )
            session.add(assignment)
        assignment.status = "active"
        assignment.valid_from = valid_from
        assignment.valid_to = None
        for scope_type, scope_ids in scopes:
            grant_id = f"scope_{login_name}_{scope_type}"
            grant = session.get(ScopeGrant, grant_id)
            if grant is None:
                grant = ScopeGrant(
                    id=grant_id,
                    enterprise_id=enterprise_id,
                    role_assignment_id=assignment_id,
                    scope_type=scope_type,
                )
                session.add(grant)
            grant.scope_ids = scope_ids
            grant.effect = "allow"
            grant.valid_from = valid_from
            grant.valid_to = None
