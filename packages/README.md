# 共享包

本目录只保存具有明确消费者和稳定边界的共享包。

计划中的首期包：

- `contracts`：JSON Schema、生成类型和兼容性检查。
- `observability`：run_id、结构化日志和错误 Envelope。
- `jobs`：PostgreSQL 任务表映射、幂等入队、领取、重试、超时和 Worker Runner。
- `agent-runtime`：运行时无关的启动、续跑、流式事件、审批与取消契约，以及确定性 FakeRuntime。
- `channel-adapter`：渠道消息和会话契约。

禁止创建无所有权的 `common` 或 `utils` 万能包；通用代码必须说明消费者和稳定性承诺。
