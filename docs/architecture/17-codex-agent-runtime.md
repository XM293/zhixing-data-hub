# Codex Agent Runtime

## 目标边界

知行数枢把 Codex 开源 Harness 作为首个智能体运行时适配器，不把 Codex 的线程、Turn、工具项或审批结构直接写入领域服务。角色分身、会议、证据、行动、权限和审计继续使用平台自有对象。

官方能力依据：

- Codex Harness 与集成层：https://developers.openai.com/blog/codex-as-a-platform
- App Server 协议：https://learn.chatgpt.com/docs/app-server
- MCP 工具：https://developers.openai.com/api/docs/guides/tools-connectors-mcp

## 已实现模块

### 运行时契约

`packages/agent-runtime` 提供：

- `AgentRunSpec`：可信企业、主体、权限版本、输入、角色约束、模型、允许工具和输出 Schema；
- `AgentRunHandle`：平台运行与运行时线程、Turn 的映射；
- `AgentRunEvent`：启动、消息、工具、审批、完成、失败和取消事件；
- `AgentRuntime`：`start`、`resume`、`stream`、`cancel`、`close`；
- `FakeAgentRuntime`：无需模型的确定性流程和失败分支测试。

### Codex 适配器

`services/adapters/codex-runtime` 使用 STDIO JSON-RPC 接入 `codex app-server`：

1. 每个运行使用独立 app-server 子进程；
2. 完成 `initialize`/`initialized` 握手；
3. 使用 `thread/start` 和 `turn/start` 启动运行；
4. 将 `turn/*`、`item/*`、消息增量、MCP 工具和审批请求转换为平台事件；
5. 使用 `turn/interrupt` 取消活动 Turn；
6. 通过同一线程开始后续 Turn；
7. 关闭 API 时回收所有子进程。

### 控制面

AI 运行控制台分别显示 Responses Provider 与 Codex Runtime。`POST /api/v1/ai-operations/runtime-probes` 只执行 app-server 握手，不启动模型 Turn；结果写入 `agent_runtime_probe_runs`，包含执行主体、版本、状态、耗时、脱敏错误和追踪 ID。

迁移 `0046_agent_runtime_sessions` 进一步加入平台自有的 Runtime 映射：

- `AgentRuntimeSession` 保存 AgentRun、Codex Thread、`thread.sessionId` 与短期 MCP 会话的关联；
- `AgentRuntimeTurn` 保存每轮 Runtime Turn、模型、状态和脱敏失败；
- `AgentRuntimeEventRecord` 追加保存规范事件、平台序号和允许清单后的载荷；
- Prompt、回答正文、MCP Token、企业上下文和未经治理的 Codex 原始事件不进入 Runtime 事件表；
- API 进程释放后可使用已保存的 `thread.id` 调用 `thread/resume`，不从 Thread ID 推导 Session ID。

迁移 `0047_agent_runtime_multiturn` 将会话和业务运行进一步解耦：

- 一个 `AgentRuntimeSession` 对应一个 Codex Thread，Session 保留初始 AgentRun；
- 每次用户追问创建新的 AgentRun、证据快照和短期 MCP 会话，再向原 Session 追加 `AgentRuntimeTurn`；
- Turn 显式保存本轮 AgentRun、MCP 会话、`request_id` 和 `run_id`，不能从 Session 继承当前主体权限；
- 续问要求同企业、同真实提问主体、同角色分身且上一轮已经完成；
- Runtime 控制台可读取 Session、Turn 和脱敏 Event 详情，具备平台管理权限的主体可以对活动 Turn 发起受控取消；
- 取消只发送 `turn/interrupt` 并等待 Runtime 最终事件，不伪造完成状态，也不降级到其他 Provider 继续回答。

内部 Web 分身问答已经成为首条 Runtime 业务主链。服务先创建 `AgentRun`，再签发绑定该运行和真实提问人的短期 R0 MCP 会话；Runtime 完成后撤销会话并释放子进程。结构化输出继续经过数值证据校验，失败时依次降级到 Responses Provider 与确定性证据摘要，降级原因写入 AgentRun。

## 权限与工具边界

运行规格中的主体字段只用于审计，不能授予权限。启用企业工具时，适配器要求 API 签发的 `RuntimeCredentials`：

- MCP 会话令牌与客户端 ID 只注入子进程环境；
- 令牌不进入运行规格、事件、异常或数据库；
- 允许工具由 `MCPGatewaySession.allowed_tool_keys` 决定；
- API 在每次工具执行时重新计算当前账号权限和数据范围；
- 每轮追问重新签发当前真实主体的 MCP 会话，历史会话在回答结束后保持撤销；
- Codex 请求命令、文件修改、额外权限、动态工具或用户输入时默认拒绝；
- 默认沙箱为只读且只暴露指定运行目录。

## Skill 注册与版本治理

迁移 `0049_skill_registry` 和 Skill Studio 已将企业 Skill 纳入平台控制面；`0051_meeting_runtime_runs`、`0052_meeting_runtime_run_history` 又将数字会议独立分析接入同一运行审计链：

- Skill、版本和配置事件使用企业边界、主体、请求 ID、运行 ID 和不可变状态；
- 发布前只能引用 Tool Registry 中当前有效的工具键；Skill 不复制工具权限，运行时仍由 ActorContext 和 MCP Gateway 重新授权；
- 同一 Skill 只保留一个当前发布版本，旧版本转为 `retired`，历史配置可审计、可回放；
- Web 管理台 `/console/twins/skills` 支持创建草稿、编辑 Schema、版本发布和版本台账；会议角色运行额外保存会议、参会分身、证据快照和 Runtime Session 的映射。

## 尚未完成

当前内部 Web 分身问答和数字会议全阶段（独立分析、两轮质询、反方审查、主持汇总）已切换到 Runtime 主链；经营分析、客服和评测调度仍主要直接调用 `ResponsesAIProvider`。后续迁移顺序：

1. 完成 API 重启后的人工审批恢复、预算和长运行故障边界；
2. 迁移经营分析、客服和评测调度；
3. 在生产服务器具备渠道凭证后接入飞书流式渠道；
4. 评估 R1/R2 工具，R3 外部写入仍只能进入 Action 服务。

因此当前可以表述为“Codex Runtime 已承接分身问答和数字会议主链”，不能表述为“全部 AI 业务已由 Codex 执行”。
