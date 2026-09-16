# ADR-008：企业工具网关与 MCP 只读纵向切片

- 状态：Accepted
- 日期：2026-08-28
- 关联：TD-008、AGT-006、AGT-007、IAM-006、UIA-014

## 背景

Codex、角色分身、数字会议和未来运营自动化都需要读取企业知识与经营数据。如果每种运行时各自连接数据库、解释权限或拼装供应商字段，数据范围、审计和业务口径会迅速分叉。MCP 是工具协议，不应成为数据库后门或新的业务服务层。

## 决策

建立数据库驱动的企业工具注册表，并由企业 API 承担工具执行。MCP 网关只完成协议适配、受信进程身份传递、错误映射和追踪元数据返回。

当前发布五个 R0 工具：

| 工具 | 应用能力 | 权限 | 范围解析 |
| --- | --- | --- | --- |
| `read_policy` | 读取生效制度与证据定位 | `knowledge.document.read` | 企业共享知识 |
| `search_knowledge` | 检索版本化知识切片 | `knowledge.document.read` | 企业共享知识 |
| `get_metric` | 读取指标定义与最新快照 | `metric.query.execute` | 指标 `scope_key` |
| `query_commerce_facts` | 读取规范经营事实与血缘 | `metric.query.execute` | 经营范围映射 |
| `query_customer_360` | 读取客户汇总与单客详情 | `customer.profile.read` | 客户范围映射 |

统一约束如下：

1. 工具参数禁止接收 `principal_id`、权限列表或任意企业 ID；主体由 `MCPGatewaySession` 绑定内部账号，令牌只返回一次且持久层仅保存哈希。
2. 工具定义、Schema、风险、权限键、范围解析器、版本、超时和状态持久化在 `tool_definitions`。
3. 每次调用把主体快照、输入、输出摘要、允许/拒绝/失败、错误码、耗时、认证方式、MCP 会话、可选 AgentRun、签发/执行权限版本、`request_id` 与 `run_id` 写入 `tool_invocations`。
4. API 在执行点重新调用身份授权服务；菜单可见、MCP 工具可发现和实际数据访问是三个不同判断。
5. MCP 不持有 SQL，不读取供应商原始字段，不复制知识检索或指标语义逻辑。
6. 首批工具声明 `readOnlyHint=true`、`idempotentHint=true`、`openWorldHint=false`。
7. 任意 SQL、任意 HTTP、Shell、外部写入和角色分身调用不在首批暴露范围内。

## 运行与配置

网关采用官方 MCP Python SDK 2.x，以 STDIO 服务运行。仓库提供项目级 `.codex/config.toml`；当前开发主机同时通过 `codex mcp add zhixing-enterprise` 登记相同服务。Codex 只连接 MCP 进程，MCP 进程调用 `http://127.0.0.1:8000` 的企业 API。

网关只接受运行时注入的 `ZHIXING_MCP_SESSION_TOKEN` 与匹配的 `ZHIXING_MCP_CLIENT_ID`。会话保存工具白名单、可选范围约束、签发权限版本和可选 AgentRun；API 每次请求重新加载当前账号和授权，再与会话约束取交集。网关为每次 HTTP 调用生成 `request_id`，并在同一进程中保持 `run_id`。

## 验收

- API 注册表和 MCP `list_tools` 返回会话允许且主体当前有权使用的相同工具集合；
- 知识检索、指标查询和制度读取均经过真实 HTTP API 并返回数据库结果；
- 真实 STDIO 子进程能够握手、列举工具并执行制度读取；
- 伪造主体参数被 Schema 拒绝，员工读取企业级指标被范围授权拒绝；
- 管理台可以查看工具 Schema 和调用台账，驾驶舱显示工具与调用数量；
- 重复迁移和种子不会生成重复工具定义。

## 2026-08-30 修订

迁移 `0042_trusted_mcp_gateway_sessions` 替换了原开发登录名进程身份。签发、列表、撤销和过期形成数据库生命周期；会话工具白名单与范围只能收窄当前主体，不能授予新权限。账号停用、权限或范围变化在下一次目录或工具调用时生效。角色分身身份不参与授权，`agent_run_id` 只用于把工具调用归属到实际发起主体的运行审计。

## 后续扩展条件

R1/R2 工具必须先补齐输入影响预览、审批策略、幂等键和补偿语义。角色分身工具必须先让 Context Builder 传播完整 `ActorContext` 与调用者范围。真实外部写入必须经过 Action Proposal、审批和执行台账，不直接从 MCP 工具触发。
