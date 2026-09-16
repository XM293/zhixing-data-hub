# 身份、权限与应用壳详细设计

本文展开 ADR-004，作为 `FND-007`、`IAM-*`、渠道、MCP 和行动中心任务的共同实现依据。

## 1. 领域关系

```text
Enterprise
  ├─ OrgUnit ─ Position
  │              └─ Membership ─ User ─ Principal
  ├─ AccessRole ─ Permission
  │       └─ RoleAssignment ─ ScopeGrant
  ├─ ChannelIdentity ─ Principal
  └─ AuthorizationDecision / IdentityManagementEvent

RoleTwin ─ owner_user_id / role_template_id
AgentRun ─ actor_context / role_twin_version_id
```

### 稳定对象

- `Enterprise`：私有化部署内的企业边界。
- `Principal`：所有鉴权和审计的统一主体，可为 `human`、`service` 或 `agent`。
- `User`：人员账号，引用一个人员主体；离职时停用账号，不删除历史记录。
- `OrgUnit`：部门、事业部或组织节点，支持稳定父子关系和有效期。
- `Position`：岗位定义，不直接等于权限。
- `Membership`：人员在组织和岗位中的任职，包含有效期和主兼职标记。
- `ChannelIdentity`：外部渠道身份与内部主体的显式映射。

### 授权对象

- `Permission`：资源与动作的稳定键。
- `AccessRole`：可版本化的权限集合。
- `RoleAssignment`：主体或成员关系获得访问角色的记录。
- `ScopeGrant`：角色赋权的企业、组织、店铺、知识空间或对象范围。
- `Delegation`：有起止时间、来源和可撤销状态的临时委托。
- `AuthorizationDecision`：一次授权检查的输入摘要和结果。

## 2. 数据所有权

`identity` 独占企业、人员主体、组织、岗位、任职、渠道身份、访问角色和授权范围。其他模块只保存稳定引用：

- `entity` 保存店铺、商品、SKU、客户、供应商等业务实体；需要负责人时引用 `principal_id` 或 `org_unit_id`。
- `role-twin` 引用所有者和岗位模板，不复制账号、部门或权限。
- `channel` 解析外部消息中的身份声明，持久映射由 `identity` 管理。
- `operations` 运输和检索日志；授权审计含义由 `identity` 维护。

## 3. 权限目录

权限键必须登记后使用，不允许业务代码临时拼接。首批目录：

| 领域 | 示例动作 |
|---|---|
| 平台 | `platform.navigation.read`、`identity.user.manage`、`identity.access.manage` |
| 知识 | `knowledge.document.read`、`knowledge.document.ingest`、`knowledge.policy.publish` |
| 记忆 | `memory.candidate.read`、`memory.candidate.review`、`memory.approved.retire` |
| 分身 | `role-twin.read`、`role-twin.configure`、`role-twin.invoke` |
| 数据 | `source.manage`、`metric.definition.read`、`metric.query.execute` |
| 会议 | `meeting.start`、`meeting.read`、`meeting.decision.confirm` |
| 行动 | `action.propose`、`action.approve`、`action.execute` |
| 运营 | `operations.run.read`、`audit.event.read` |

权限目录、访问角色和菜单映射必须版本化。删除权限采用停用，不复用历史权限键。

## 4. 数据范围

统一范围结构至少包含：

```json
{
  "scope_type": "enterprise | org_unit | org_subtree | business_unit | store | source | knowledge_space | object | self",
  "scope_ids": ["stable-id"],
  "valid_from": "timestamp-with-timezone",
  "valid_to": null
}
```

领域服务负责把通用范围解析成自己的查询条件。授权层返回可用范围，不直接生成任意 SQL。结构化经营查询必须将有效范围传入指标服务；知识检索必须将有效范围传入知识提供者；任何适配器不得忽略范围。

## 5. 请求与运行上下文

API 在认证边界创建 `ActorContext`，应用用例只接收可信上下文。建议公共契约：

```text
ActorContext
  enterprise_id
  actor_principal_id
  on_behalf_of_principal_id
  authentication_method
  identity_source
  channel
  membership_ids
  role_keys
  permissions
  scopes
  policy_version
  request_id
  run_id?
```

AgentRun、Meeting、EvidenceSnapshot、Job 和 ActionProposal 保存该上下文的稳定引用或不可变摘要。工具调用同时记录 `actor_principal_id` 和 `on_behalf_of_principal_id`，禁止只记录 RoleTwin 名称。

## 6. 各入口执行规则

### Web 与 API

1. Web 完成认证，API 建立服务端会话或验证受信身份。
2. API 根据路由声明检查权限和资源范围。
3. 列表和查询在仓储或领域查询层应用数据范围。
4. 前端从 `/api/v1/identity/me` 获取当前用户、角色、范围和菜单投影。
5. 按钮不可见不代表授权完成，所有写接口必须再次检查。

### 飞书等渠道

1. 渠道适配器校验请求并提取外部身份。
2. `identity` 将外部身份解析为内部 `Principal`。
3. 未映射身份进入绑定或人工处理流程，不通过姓名自动匹配。
4. 群聊回答仍按发起消息的人员范围执行，不按群主或机器人范围执行。

### Agent 与 RoleTwin

1. 调用者必须拥有 `role-twin.invoke`。
2. Context Builder 只取得调用者有效范围内的知识、指标和记忆。
3. ToolGateway 对每次工具调用重新检查资源、动作和范围。
4. RoleTwin 的可用工具白名单只会收窄权限，不会授予权限。

### MCP 与 Codex

MCP 工具输入不接受任意 `principal_id`。网关从受信会话取得 `ActorContext`，并将其传给应用服务。Codex Runtime 只能调用已登记工具，不直接连接业务数据库。

### Worker 与行动执行

后台任务保存发起主体、企业、请求 ID、权限版本和目标范围。只读长任务可以使用创建时授权快照；涉及写入时必须在执行前按当前策略重新授权。审批人和执行人应分别记录，风险动作可要求二者不同。

## 7. 管理台壳子

管理台壳子包含：

- 企业与当前用户信息；
- 由后端能力投影生成的中心与菜单；
- 稳定菜单键、路由、图标、排序和阶段状态；
- 面包屑、会话失效、401、403、404 和 API 错误状态；
- 页面级和操作级授权组件；
- 管理员的用户、组织、任职、访问角色和授权范围页面。

菜单注册表不保存授权真值。后端先计算有效权限，再返回可见菜单；直接访问 URL 仍由 API 和服务端路由保护。

### 当前纵向切片的数据库身份底座

迁移 `0014_identity_access_foundation` 已落地 `Principal`、`UserAccount`、`OrgUnit`、`Position`、`Membership`、`PermissionDefinition`、`AccessRole`、`AccessRolePermission`、`RoleAssignment`、`ScopeGrant` 和 `AuthorizationDecision`。开发环境的 `X-Zhixing-Demo-Actor` 现在只负责选择本地认证提供者中的测试身份；API 必须从数据库加载主体、任职、角色、权限和范围，客户端不能传入任意主体、企业或权限列表。

| 开发身份 | 数据库授权语义 |
|---|---|
| CEO | 读取/启动会议、确认决策和提出行动；不能审批自己确认后产生的行动 |
| 部门经理 | 读取会议、在对象范围内审批行动；不能确认企业决策 |
| 员工 | 只读会议和授权知识；不能确认或审批 |
| 平台管理员 | 管理身份、数据源、运行和审计；不天然拥有业务决策确认或行动审批权 |
| 财务负责人 | 在授权对象范围内确认和审批，用于验证职责分离与冲突规则 |
| 服务主体 | 当前不授予会议确认或行动审批权限 |

`/api/v1/identity/me` 返回数据库身份、组织岗位、角色、权限、范围和动态菜单；`/api/v1/identity/admin/overview` 返回账号、组织、岗位、角色、授权范围、管理事件和授权决策摘要。管理台的用户账号、组织岗位、访问权限和审计页面直接读取这些接口。会议确认与行动审批同时检查权限和对象范围，每次允许或拒绝都持久化 `request_id`、`run_id`、策略版本和原因。

迁移 `0037_identity_management_operations` 新增带乐观版本的账号配置和不可变 `IdentityManagementEvent`。迁移 `0038_identity_catalog_operations` 为组织、岗位和访问角色目录增加版本字段，并新增不可变 `IdentityCatalogEvent`。迁移 `0039_auth_sessions` 增加只保存令牌哈希的服务端会话表，迁移 `0040_local_password_auth` 增加可选密码哈希。`POST /api/v1/identity/admin/users` 可以原子创建主体、账号、主任职、访问角色和范围，`PUT /api/v1/identity/admin/users/{account_key}/configuration` 可以调岗、换角色、调整范围和启停账号；组织、岗位和访问角色分别通过 `/admin/org-units`、`/admin/positions` 和 `/admin/access-roles` 受治理写入。目录接口使用请求键防止重复写入，更新使用乐观版本，并保存操作人快照、前后配置、变更字段、原因、`request_id` 和 `run_id`。停用组织前必须没有生效岗位，停用岗位前必须没有生效任职。岗位变化不会隐式授予访问角色，角色变化也不会改写岗位；当前管理员不能停用自身或修改自身访问包。`POST /api/v1/auth/login` 校验本地密码并建立 HttpOnly Cookie 或 Bearer 会话，开发环境兼容 `/api/v1/auth/development/session`；所有既有 API 统一解析会话，正式 SSO 和渠道提供者仍通过后续适配器接入。

迁移 `0041_worker_authorization_context` 将后台任务契约升级为 v2。新任务必须固化发起人快照、排队时权限版本、声明权限、目标范围和追踪链路；每次领取生成一次性执行令牌，持久层只保存哈希，终态或租约回收立即清除。自动巡店内部 API 会核对当前 Worker、令牌、任务请求/运行 ID、计划企业和范围，随后按任务发起主体重新解析数据库 ActorContext。排队快照只用于证明任务为何被创建，不授予持续权限；当前账号停用、权限移除或范围变化会在执行前返回 403，并将新的策略版本和拒绝原因写入 `AuthorizationDecision`。Worker 不发送任意主体、权限列表或范围来覆盖数据库任务记录。

迁移 `0042_trusted_mcp_gateway_sessions` 增加短期 `MCPGatewaySession` 和追加式生命周期事件。登录主体只能从当前已发布且本人拥有权限的 R0/R1 工具中签发白名单，只能把当前有效范围的子集交给会话；可选 `agent_run_id` 必须属于同一企业和同一实际发起主体。令牌只在签发响应返回一次，持久层保存哈希。MCP 网关必须同时提交令牌、绑定 `client_id`、独立 `request_id` 和稳定 `run_id`，不能提交登录名、主体、角色、权限或企业覆盖值。每次调用重新加载当前账号、角色、权限和范围，再与会话白名单及范围取交集；调用台账保存会话、AgentRun、认证方式和签发/执行权限版本。RoleTwin 和 AgentRun 只提供配置与审计归属，不提升实际调用人的权限。

迁移 `0043_channel_identity_bindings` 增加 `ChannelIdentity` 与追加式 `ChannelIdentityEvent`。外部身份以企业、渠道、渠道租户和 SHA-256 指纹唯一标识，数据库只返回短提示和截断指纹，不持久化外部身份原文。未知身份可由具备 `identity.user.manage` 的管理员绑定、换绑、解绑、停用或启用；配置接口同时校验乐观版本、幂等键和原因，并阻止同一渠道租户内一个内部主体重复绑定多个外部身份。解析成功后仍重新加载本地账号、任职、访问角色和范围，渠道映射不能成为权限真值。真实渠道适配器负责签名校验和提取外部身份，不能直接提交 `principal_id` 绕过解析。

统一审计检索不新建第二套操作日志表。`contracts/audit/unified-audit-ledger.schema.json` 和 `/api/v1/audit/events` 将 `AuthorizationDecision`、`IdentityManagementEvent`、`IdentityCatalogEvent`、`ChannelIdentityEvent`、`MCPGatewaySessionEvent`、`ToolInvocation`、`BackgroundJob`、`AgentRun` 与 `ActionWorkEvent` 投影为版本化只读账本。查询必须先检查 `audit.event.read` 和企业范围，再支持来源、结果、主体、时间、文本、`request_id`、`run_id` 与 `agent_run_id` 过滤。页面菜单仍只是该权限的投影，普通员工直接访问接口返回 403。返回属性采用逐来源允许清单，不包含主体快照、前后配置快照、外部身份原文、会话令牌、工具输入输出、任务载荷、Prompt、模型回答或任意详情对象。

数据中心路由不再把菜单可见当作授权。`overview` 至少要求有效会话和 `platform.navigation.read`；来源同步与运行台账使用 `source.manage`，实体/指标/质量管理使用 `metric.definition.read`，指标序列和规范经营事实使用 `metric.query.execute`，客户 360 使用 `customer.profile.read`。除企业数字孪生概览仍是企业级公共运营投影外，管理资源要求企业范围，经营与客户查询将 `enterprise` 或门店范围键转换为授权服务的 `scope_type/scope_id`，并将当前主体企业 ID 传入数据服务。前端经营事实页从会话身份读取有效范围，不接受页面自行声明主体。

缺少登录凭据或有效会话返回 401，权限或范围不足返回 403，并发版本、幂等内容冲突和管理员自锁返回 409。当前本地密码认证、渠道身份数据库映射、数据中心 HTTP 守卫、自动巡店 Worker 重授权和五个只读工具的 MCP 可信会话已可运行；正式 SSO、真实渠道适配器、委托、组织子树展开、企业数字孪生逐范围内容裁剪、完整 Agent Runtime 和其他 Worker/Action 类型继续由正式 `IAM-*` 任务推进。

## 8. 初始化与生命周期

- 种子数据创建一个企业、6 个测试主体/账号、6 个组织节点、6 个岗位、6 个访问角色、43 个权限、显式范围和 3 个脱敏渠道身份；不写入密码、外部身份原文或外部凭据。
- 正式认证落地后，首次登录要求替换初始化凭据；当前测试身份只允许在本地开发提供者中使用。
- 用户离职后停用登录和未到期委托，保留历史审计、运行和审批引用。
- 部门调整通过新 Membership 生效，不回写历史 ActorContext。
- 渠道身份解绑或重绑必须记录审计事件。

## 9. 最小验收矩阵

| 场景 | 预期 |
|---|---|
| 匿名读取受保护制度 | 401 |
| 普通员工访问管理页面 | 菜单不可见，直接访问为 403 |
| 部门经理查询其他部门店铺 | 403 或空范围，并记录拒绝原因 |
| 员工调用 CEO 分身 | 仅使用员工范围内证据 |
| 飞书未知身份提问 | 提示绑定或转人工，不返回内部资料 |
| Worker 执行已撤销授权的写任务 | 执行前拒绝并保留审计 |
| MCP 伪造主体参数 | Schema 拒绝或忽略客户端主体字段 |
| 权限角色变更 | 新版本生效，历史决策仍可复现 |
| 管理员重复创建或保存 | 相同请求重放原结果，不同内容返回 409 |
| 管理员停用自身或移除自身访问包 | 409，保留当前恢复路径 |

## 10. 演进条件

首期在模块化单体内实现确定性授权服务。出现以下情况再评估外部策略引擎：

- 条件策略数量显著增加；
- 需要跨多个独立服务共享关系授权；
- 授权关系图查询成为性能瓶颈；
- 需要由非研发人员编辑复杂策略。

无论是否引入外部引擎，`Permission`、`ScopeGrant`、`ActorContext` 和 `AuthorizationDecision` 保持企业自有契约。
