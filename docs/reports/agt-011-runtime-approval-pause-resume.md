# AGT-011 Runtime 审批暂停与恢复记录

日期：2026-09-07

## 已完成

- Codex Runtime 适配器不再自动拒绝服务端审批请求；遇到审批会进入等待状态；
- 增加 `resolve_approval(run_id, approve|decline)` 运行时协议；
- 批准时向 Codex 传递允许结果，拒绝时继续使用 fail-closed 拒绝结果；
- Runtime 事件已有 `approval.required` / `approval.resolved` 状态持久化；
- 增加 API 审批解析服务和 `/api/v1/ai-operations/runtime-sessions/{session_id}/approval` 路由；
- 审批接口复用 `ai.provider.manage` 权限和当前企业边界，不改变原始 ActorContext 权限。

## 验证

- Codex Runtime 3 项测试通过；
- API Ruff 和 mypy 通过；
- 由于当前工作区 `.env` 指向尚未放行的腾讯云 PostgreSQL，API 全量测试中的 `test_ai_operations.py` 本轮未能启动测试库，失败原因是数据库连接超时，不是代码断言失败。

## 后续边界

当前审批恢复依赖 Runtime 进程仍在当前 API 实例中。下一步需要把待审批请求摘要和 Skill/工具/范围快照落入独立审批表，并补 API/Worker 重启后的恢复与过期拒绝测试。
