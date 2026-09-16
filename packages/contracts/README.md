# 共享契约

本目录保存跨 Web、API、Worker、MCP 与渠道入口共享的稳定协议。契约使用不可变 `schema_version` 演进，不从 ORM 或第三方组件模型自动生成。

当前已实现：

- `observability/trace-context.schema.json`：`request_id`、`run_id` 和 HTTP 传播头；
- `observability/error-envelope.schema.json`：所有 API 失败响应的统一结构。
- `jobs/job-record.schema.json`：后台任务的企业、发起主体、状态、幂等键与追踪字段。

第三方 SDK、OpenViking、TencentDB-Agent-Memory、Codex Runtime 等内部 ID 不得进入这些平台契约。
