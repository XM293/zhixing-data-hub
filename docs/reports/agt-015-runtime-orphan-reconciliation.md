# AGT-015 Runtime 重启孤儿运行回收验收记录

日期：2026-09-08

## 本轮完成

- API 启动时扫描 `starting`、`running` 和 `waiting_approval` 的 Runtime 会话；
- 将没有当前 API 进程承载的会话安全标记为 `failed`；
- 将对应活动 Turn 标记为 `failed`；
- 将尚未处理的 Runtime 审批标记为 `expired`，避免重启后继续显示为可批准；
- 统一写入 `runtime_process_restarted` 和可审计失败原因；
- 保留已保存的 Codex Thread，后续显式恢复流程可以基于 Thread 创建新 Turn；
- 当前不伪造跨重启自动继续，也不重新执行原审批动作。

## 边界

本轮完成的是 fail-closed 的重启恢复边界，不是跨重启自动续跑。自动续跑还需要持久化完整 `AgentRunSpec`、重新签发当前主体的 MCP 会话、重新验证 Skill 和范围，并提供显式的人工恢复 API。

## 验证

- API Ruff：通过；
- API mypy：通过；
- Workspace 基础检查：通过。
