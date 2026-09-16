# AI、MCP 与 Codex Runtime 对账

> 历史快照：2026-08-31。当前迁移、Skill、测试和路线以 [`docs/PROJECT-STATE-AND-ROADMAP.md`](../PROJECT-STATE-AND-ROADMAP.md) 与 `docs/architecture/17-codex-agent-runtime.md` 为准。

日期：2026-08-31

## 结论

系统已有真实数据库、权限、知识/记忆治理、Responses Provider、五个只读 MCP 工具和工具调用审计，不是纯 UI 模拟。此前缺少独立 Agent Runtime，导致分身、会议、分析、客服和评测由应用服务直接调用模型，无法统一提供线程续跑、流式事件、取消和 Harness 审批。

本轮已经补齐运行时契约、FakeRuntime、Codex app-server 适配器、Runtime 握手 API、数据库探针台账和控制台状态。迁移 `0046_agent_runtime_sessions` 完成 Session、Turn、规范事件持久化与 Thread 重启恢复，迁移 `0047_agent_runtime_multiturn` 又完成逐事件详情、受控取消和同一 Thread 的分身多轮追问。内部 Web 分身问答已切到 Runtime + 逐轮受限 MCP 主链；数字会议、经营分析、客服和评测尚未迁移。

## 能力矩阵

| 能力 | 当前状态 | 实现位置 | 主要缺口 |
| --- | --- | --- | --- |
| 企业数据库 | 已实现 | API 迁移 0001-0047 | 生产容量、备份恢复和客户进场映射 |
| 账号与权限 | 已实现纵向切片 | 身份、角色、范围、委托、会话、审计 | SSO、生产身份源和全任务守卫收口 |
| AI Provider | 已实现 | `ResponsesAIProvider`、Provider 探针 | 预算、限流、模型路由和统一重试 |
| 知识问答 | 已实现纵向切片 | 制度版本、切片、引用、冲突、三路评测 | 正式知识后端选型和大文件异步解析 |
| 长期记忆 | 已实现纵向切片 | 候选、审核、版本、双路评测 | 真实供应商验收和大规模聊天清洗 |
| MCP 网关 | 已实现 | 官方 MCP Python SDK、受限会话 | R1/R2 工具；R3 必须进入 Action |
| 只读企业工具 | 已实现 5 个 | 制度、知识、指标、经营事实、客户 360 | 商品、物流、广告明细等后续工具 |
| AgentRuntime 契约 | 已实现 | `packages/agent-runtime` | 审批恢复与预算控制 |
| Codex Harness | 首条主链已接入 | `services/adapters/codex-runtime`、迁移 0045-0047 | 审批恢复及会议、分析、客服迁移 |
| Skills | 已实现纵向切片 | Skill Registry、版本、工具引用校验和配置审计 | Skill 运行时注入、审批恢复和更多领域 Skill |
| 内部 Web 分身 | Runtime 多轮主链可用 | 分身问答、逐轮受限 MCP、详情/取消/续问 | 前端流式输出与审批恢复 |
| 飞书/微信 | 未完成 | 渠道身份绑定已实现 | 真实飞书机器人、消息幂等和人工接管 |
| 自动运营 | 部分实现 | 定时巡店、提案、审批、内部工单 | 真实外部系统写入和补偿 |
| Computer Use | 未实现 | 任务仍 deferred | 隔离执行节点、录制回放、审批与验收 |

## 近期优先级

1. 补齐 Runtime 人工审批暂停与恢复 API。
2. 完成飞书问答渠道，复用同一 ActorContext、AgentRun、证据和人工接管。
3. 迁移数字会议、经营分析和客服主链。
4. 扩展 R1 分析和 R2 草拟工具；外部写操作继续走 Action 审批与幂等执行。

不优先复制 Codex App 界面，也不让 Codex 直接连接业务数据库。产品界面、经营上下文、权限、记录和审批属于知行数枢；Harness 只负责智能体循环与受控工具执行。

## 本轮验证

- `pnpm check` 通过，包含工作区约束、Web TypeScript、Python Ruff/Mypy 和完整测试链；
- API 110 项、Web 32 项、工作区 22 项测试通过，AgentRuntime、Codex Runtime、MCP、Worker 和三套模拟服务独立测试通过；
- `pnpm build` 通过，Next.js 生产构建完成；
- 本地数据库已升级到 `0047_agent_runtime_multiturn`，API `/health/live` 与 `/health/ready` 通过；
- 真实 Runtime 探针通过，记录 `codex-cli 0.150.0-alpha.12.2` 与 `app-server-json-rpc-v2`；探针只完成初始化握手，不启动模型 Turn；
- AI 运行控制台在 1280×720 与 390×844 验收通过；移动端操作区已消除横向溢出，浏览器无错误日志。

## 运行环境注意项

当前机器的系统 PowerShell PATH 首先解析到 `codex-cli 0.130.0`，项目通过 `uv run` 启动 API 时解析到 Codex Desktop 的 `0.150.0-alpha.12.2`。开发探针使用后者。正式部署必须通过 `CODEX_COMMAND` 固定经过验收的可执行文件，并在启动探针中校验协议与最低版本，不能依赖 PATH 顺序。
