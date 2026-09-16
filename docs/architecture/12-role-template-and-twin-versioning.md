# 岗位模板与角色分身版本架构

状态：Implemented slice / Pending milestone dependencies  
关联任务：`TWI-001`、`TWI-002`、`TWI-003`、`TWI-004`

## 1. 目标与边界

角色分身不是账号、访问角色或一段可覆盖的 Prompt。首期正式模型分为三层：

| 层级 | 责任 | 不负责 |
|---|---|---|
| `RoleTemplate` | 企业岗位职责、能力边界和默认表达/推理/回答规则 | 个人身份、登录权限和具体模型运行 |
| `RoleTwinProfile` | 稳定分身标识、岗位模板引用和负责人引用 | 保存 `AccessRole`、复制组织权限或覆盖历史配置 |
| `RoleTwinVersion` | 一次不可变的个人配置快照，包括模板版本、模型、能力和三类行为规则 | 动态授权、渠道身份和运行证据 |

`AccessRole`、权限键和数据范围继续属于 IAM。调用分身时，服务使用受信 `ActorContext` 计算调用者、资源、渠道和工具的有效能力交集；分身本身不能扩大调用者权限。

## 2. 版本生命周期

岗位模板和分身实例都使用“稳定对象 + 不可变版本”结构：

1. 创建稳定对象时同时创建 `v1 draft`。
2. 只能从当前最高版本复制生成下一版；旧版本正文不允许原地修改。
3. 发布命令要求 `role-twin.configure` 权限并记录发布原因。
4. 发布后，新运行读取最高已发布版本；既有版本和历史运行保持不变。
5. 重复发布同一版本按幂等命令处理，不重复生成发布事件。

每次创建或发布都会写入 `role_configuration_events`，保存主体快照、原因、`request_id`、`run_id` 和发生时间。页面只呈现数据库事件，不在前端伪造版本历史。

## 3. 运行绑定

`agent_runs.role_twin_version_id` 保存一次回答或会议实际使用的分身版本。运行上下文同时保存知识证据、经营指标和已审核记忆引用，因此历史结果可以按“身份与范围 + 分身版本 + 数据/知识/记忆版本 + 模型”复现。

未发布的分身不可调用。岗位模板发布不自动改写既有分身；分身创建时显式绑定一个已发布模板版本，后续需要升级模板时必须生成新的分身版本并重新发布。

## 4. API 与管理台

读模型：

- `GET /api/v1/role-studio`

岗位模板命令：

- `POST /api/v1/role-templates`
- `POST /api/v1/role-templates/{template_key}/versions`
- `POST /api/v1/role-templates/{template_key}/versions/{version_number}/publish`

分身实例命令：

- `POST /api/v1/role-twins`
- `POST /api/v1/role-twins/{twin_key}/versions`
- `POST /api/v1/role-twins/{twin_key}/versions/{version_number}/publish`

管理台：

- `/console/twins/templates`：岗位职责、能力边界、草稿与发布版本。
- `/console/twins/instances`：岗位模板、负责人、模型、能力和个人规则。
- `/console/twins/prompts`：不可变版本发布台账和当前运行版本。

页面写操作由数据库身份投影控制。负责人选项来自企业主体目录，`RoleTwinProfile.owner_principal_id` 只引用主体，不复制姓名、岗位或权限。

## 5. 当前验收与剩余依赖

2026-08-28 已完成数据库迁移 `0019_role_twin_versioning`、三个角色契约、领域服务、授权命令、管理台和真实模型运行验证。浏览器完成“创建客户体验负责人模板 v1 -> 发布 -> 创建负责人分身 v1 -> 发布 -> 创建并发布分身 v2”，配置台账保留 v1/v2；真实 `AgentRun` 绑定 v2。

该纵向切片不提前关闭 M1 任务。正式认证与对象范围配置写操作、Token 预算、完整工具能力交集、回归评测、反馈纠错、渠道接入和产品负责人验收仍按任务索引推进。

## 6. 角色试跑与人工审核

迁移 `0020_role_twin_test_studio` 在角色分身域内增加首期试点审核闭环：

| 对象 | 责任 |
|---|---|
| `role_twin_test_cases` | 版本化固定问题、推荐分身、风险等级、预期行为和预期证据引用 |
| `role_twin_test_runs` | 一次真实问答运行、实际分身版本、`AgentRun`、模型与执行模式 |
| `role_twin_test_reviews` | 追加式人工审核事件、四维评分、结论、说明与主体快照 |

`/console/twins/test` 直接读取这些数据库对象。运行用例时仍经过 `role-twin.invoke`、知识读取和经营数据范围授权；审核要求 `role-twin.configure`。人工审核不会改写模型结果或上一条审核事件，最新结论只是全部事件上的读模型投影。

首批种子提供 6 个用例，覆盖制度生效边界、广告预算审批、授权经营趋势、缺少毛利时拒绝推断、经营异常汇报表达和无依据外部承诺。用例版本固定为 v1，后续修改问题或预期行为时必须新增版本，不得覆盖历史。

该试跑台用于 `TWI-004` 的角色本人样例回答审核，不替代 `EVA-001` 至 `EVA-004` 的通用评测运行器、百题黄金集和自动回归报告。
