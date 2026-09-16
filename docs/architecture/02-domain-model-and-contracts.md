# 核心领域模型与内部契约

## 核心领域对象

### SourceSystem

描述吉客云、CRM、店铺、广告、飞书、文件目录等来源。包含来源类型、连接器版本、同步策略和数据所有者。

### EnterpriseEntity

企业统一业务实体，包括店铺、商品、SKU、客户、供应商、活动和业务渠道。每个实体拥有内部稳定 ID，并通过 `ExternalIdMapping` 关联源系统 ID。人员、部门、岗位和任职由 `identity` 独占；业务实体需要负责人时只引用其稳定 ID。

### Enterprise / Principal / User / OrgUnit / Position / Membership

`Enterprise` 是部署内稳定企业边界。`Principal` 是认证、授权和审计主体；`User` 表示人员账号；`OrgUnit`、`Position` 和 `Membership` 表达组织结构和任职有效期。人员离职或调岗通过状态和新任职生效，不删除历史引用。

### AccessRole / Permission / ScopeGrant / ActorContext

`AccessRole` 聚合资源动作权限，`ScopeGrant` 限定企业、组织、店铺、知识空间或对象范围。`ActorContext` 由可信认证边界创建，贯穿 API、Agent、MCP、Worker 和 Action。访问角色、岗位与 RoleTwin 是三个不同概念。

### MetricDefinition

指标定义包括名称、业务含义、计算公式、时间粒度、可用维度、数据来源、负责人、版本和生效区间。GMV、退款率、毛利、广告ROI等必须先定义再供智能体查询。

### KnowledgeDocument / PolicyVersion

保存文档原件、解析结果、切片、发布状态、生效时间和废止关系。制度回答必须绑定具体版本。

### MemoryCandidate / ApprovedMemory

聊天或人工输入先形成候选，记录提取依据、类别、适用角色和置信度；审核通过后形成可版本化长期记忆。

### RoleTemplate / RoleTwin

`RoleTemplate` 描述岗位职责、通用规则和能力边界；`RoleTwin` 绑定具体人员风格、已审核记忆和渠道配置。人员离岗后，岗位资产可以继续使用，个人资产可停用。能力边界只会限制分身可以做什么，不授予调用者访问权限。

### EvidenceSnapshot

一次回答、会议或决策使用的数据、制度、指标和记忆版本集合。其作用是让结果可复现、可比较和可复盘。

### Topic / Claim / DecisionPackage

数字会议的议题、主张、证据、反驳、分歧、结论和行动项。会议不是拼接多个模型回答，而是围绕同一证据快照执行结构化协议。

### ActionProposal / ActionExecution / ActionWorkItem

区分“提出动作”“审批后登记”和“企业内部承接”。提案通过 `source_type + source_key + source_action_index` 关联数字会议、客户运营、经营分析或后续受治理工作流，同时保存授权范围和可选证据快照；`ActionExecution` 记录批准后的幂等内部登记与外部写入标志；`ActionWorkItem` 保存负责人、KPI、停止条件、版本和 `ready/claimed/in_progress/blocked/completed` 状态，`ActionWorkEvent` 追加记录领取、推进、阻塞、完成、释放和重开。来源业务只负责形成提案，审批、职责分离、承接状态和审计由行动领域统一处理。

## 事实优先级

```text
当前生效制度
> 已确认经营数据和指标定义
> 已审核FAQ和决策案例
> 已审核长期记忆
> 未审核历史聊天
> 模型一般知识
```

冲突时必须返回高优先级事实，并说明低优先级内容为何未采用。

## 首批内部服务契约

```text
register_source(source_spec)
sync_source(source_id, cursor)
resolve_entity(source_system, external_id)

authenticate(identity_claim)
resolve_actor_context(session_or_channel_identity)
authorize(actor_context, permission, resource, requested_scope)
record_authorization_decision(decision)

get_metric(metric_key, dimensions, time_range, as_of)
explain_metric(metric_key, version)
create_evidence_snapshot(items)

search_knowledge(query, scope, as_of)
read_policy_version(policy_id, version_or_time)
list_effective_policies(scope, as_of)

write_memory_candidate(role_id, evidence)
review_memory_candidate(candidate_id, decision)
search_approved_memory(role_id, query, as_of)

run_role_twin(actor_context, role_id, user_input, context)
start_meeting(actor_context, topic, participant_roles, evidence_snapshot_id)

propose_action(actor_context, tool_key, parameters, reason)
approve_action(actor_context, action_id, decision)
execute_action(actor_context, action_id)
list_action_work(actor_context, scope)
transition_action_work(actor_context, work_key, event, expected_version, idempotency_key)
```

## MCP工具分级

- `R0 查询`：读取制度、指标、实体和证据。
- `R1 分析`：生成报表、诊断和建议，不产生外部状态变化。
- `R2 草拟`：创建回复草稿、任务草稿或操作计划。
- `R3 执行`：产生外部状态变化，必须通过 Action 服务。

首期只实现 R0、R1 和有限 R2。业务应用不得绕过内部服务直接向 MCP 暴露数据库连接。

每个工具还必须声明权限键和范围解析方式。MCP 工具从受信会话获得 `ActorContext`，不接受调用者自行传入人员、部门或访问角色来扩大权限。

## 版本规则

- 制度、指标、角色配置、Prompt、记忆和工具定义均使用不可变版本。
- “当前版本”只是指针，不覆盖历史版本。
- EvidenceSnapshot 固定实际使用的版本和数据时间。
- 任何影响历史结论的变更通过新版本生效，不回写旧快照。
