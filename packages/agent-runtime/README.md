# Agent Runtime

本包定义知行数枢自有的智能体运行契约，不包含 Codex、模型供应商或业务数据库结构。

- `AgentRunSpec` 固定可信企业、发起主体、权限版本、允许工具和运行输入。
- 可选 `scope_context` 携带 ScopeContext v2 范围快照，法人必须与 Actor 一致；旧调用可省略。快照用于追溯，执行权限仍由当前身份和 MCP 再授权检查决定。
- 业务 API 续问前比较保存与当前范围版本；变化或历史记录缺少 v2 快照时返回 `runtime.scope_changed`，防止旧线程上下文跨范围复用。
- `AgentRunEvent` 将不同运行时转换为统一的启动、消息、工具、审批、完成和失败事件。
- `RuntimeCredentials` 只在启动进程时使用，不允许序列化或写入运行台账。
- `FakeAgentRuntime` 用于不调用模型的确定性流程测试。

Codex 实现在 `services/adapters/codex-runtime`，业务服务只能依赖本包契约。
