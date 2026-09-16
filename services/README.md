# 服务与 Worker

本目录保存模块化 API、后台 Worker、连接器和外部组件适配器。

首期结构：

- `api`：按 ADR-001 组织的 FastAPI 模块化单体。
- `mock-commerce`：独立第三方电商 HTTP 测试沙箱，包含 ERP/OMS、CRM 主档与行为触点、广告和客服契约。
- `mock-memory`：TencentDB Agent Memory v3 与 Mem0 self-hosted HTTP 契约沙箱。
- `mock-knowledge`：WeKnora、RAGFlow 与 OpenViking HTTP 契约沙箱，隔离评测文档、切片和 `viking://resources` 运行目录。
- `worker`：复用任务与可观测包、独立启动停止的后台任务进程。
- `connectors`：吉客云、CRM、文件等来源连接器。
- `adapters`：知识、记忆、模型和 Codex Runtime 适配器。

不同服务不得通过读取彼此私有表或内部目录完成跨领域调用。
