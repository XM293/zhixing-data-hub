# FND-008 / FND-009 平台基础能力评审

- 评审日期：2026-08-28
- 结论：验收通过
- 任务：`FND-008`、`FND-009`

## FND-008 可观测性与错误契约

验收证据：

- API 测试证明合法 `X-Request-ID`、`X-Run-ID` 原样传播，无效值会被替换；
- 401 与 403 返回相同版本的 Error Envelope，同时保留不同稳定错误码；
- 404、参数校验和业务冲突均进入统一错误契约；
- Web 所有 API 调用统一经过 `apiFetch`，每次请求生成 `request_id`，浏览器会话保持 `run_id`；
- `packages/observability` 不依赖 FastAPI，可由未来 Worker、Agent Runtime 与 MCP 网关复用；
- 实际 HTTP 200 和 404 响应均回传与调用方一致的追踪头。

结论：满足“Web、API、未来 Worker 共享追踪协议”和“401/403 结构一致”的任务边界。Worker 的任务领取、重试与持久化属于 `FND-010`，不反向阻塞本契约。

## FND-009 CI 与 Codex 非交互入口

验收证据：

- CI 使用冻结的 pnpm/uv 锁文件，串行执行 `pnpm check` 与 `pnpm build`；
- CI 仓库权限固定为 `contents: read`，不注入模型密钥，也不自动调用 Codex；
- `pnpm codex:task -- --task <TASK_ID>` 默认生成 `read-only`、`--ephemeral` 调用；
- `--write` 才切换为 `workspace-write`，且仅允许 `ready/in_progress` 任务；
- Windows 上已验证 Codex CLI 0.130.0 可由任务入口采用的 Shell 解析方式启动；
- 自动测试覆盖默认只读、显式写入、任务状态拒绝和 CI 质量门内容。

结论：满足“格式、类型、单测可在 CI 运行”和“Codex 任务默认只读”。仓库尚无远程提交，因此 hosted runner 运行记录暂不存在，但工作流使用的全部项目命令已在本地同环境连续通过。

## 状态决定

`FND-008` 与 `FND-009` 从 `review` 更新为 `done`。本评审不涉及 `UIA-006`，不会解锁产品范围门或领域任务。
