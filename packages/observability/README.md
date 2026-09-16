# `zhixing-observability`

`FND-008` 的跨进程可观测性基础包。API、未来 Worker、Agent Runtime 和 MCP 网关使用同一套：

- `request_id`：一次入口请求的稳定标识，HTTP 使用 `X-Request-ID` 传播；
- `run_id`：跨请求、后台任务和工具调用的业务运行标识，HTTP 使用 `X-Run-ID` 传播；
- 结构化事件：JSON 日志至少包含事件名、UTC 时间、级别和当前追踪上下文。

该包不依赖 FastAPI、数据库或具体日志平台。各入口在自己的适配层读取可信协议字段并绑定上下文，领域服务只读取当前上下文，不解释 HTTP。

ID 必须匹配 `^[a-z][a-z0-9_-]{7,95}$`。无效或缺失的外部 ID 会被替换，避免日志注入和无限长度字段。
