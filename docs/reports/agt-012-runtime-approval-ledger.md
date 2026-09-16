# AGT-012 Runtime 审批台账与重启边界

日期：2026-09-07

## 完成内容

- 新增迁移 `0050_runtime_approvals` 和 `AgentRuntimeApproval`；
- 审批请求持久化企业、Runtime Session、Turn、AgentRun、方法、Item、工具快照、状态、决定主体和追踪 ID；
- `approval.required` 事件自动生成 pending 审批台账；
- 审批决定后更新台账并调用当前 Runtime 进程的恢复接口；
- API 重启或 Runtime 进程不存在时不会伪造恢复成功，会返回 Runtime 冲突，由上层重新建立会话。

## 验证边界

- API Ruff 和 mypy 通过；
- Codex Runtime 测试 3/3 通过；
- API 的数据库测试本轮仍受当前工作区腾讯云 PostgreSQL 白名单未放行影响，需切换 SQLite 测试库或明天数据库链路恢复后复跑。

下一步：将审批台账接入 AI 运行控制台，并增加过期自动拒绝、重启后的待审批恢复策略和审批主体的更细权限规则。
