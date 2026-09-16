# Codex Runtime Adapter

该适配器通过官方 `codex app-server` 的 STDIO JSON-RPC 协议，把 Codex Harness 转换为知行数枢自有 `AgentRuntime` 事件。

运行边界：

- 每个运行使用独立 app-server 子进程和独立 MCP 短期会话令牌。
- 默认 `readOnly` 沙箱；命令、文件变更、额外权限、用户输入和动态工具请求默认拒绝。
- 允许工具由 API 签发的 MCP 会话白名单决定，适配器不接受模型自报身份或权限。
- 令牌只进入子进程环境，不进入规格、事件、异常消息或日志。
- 业务数据仍由企业 API、权限服务和工具调用台账掌控。

本模块不直接依赖知行数枢数据库。API 负责创建和撤销 MCP 会话，并持久化规范运行事件。
