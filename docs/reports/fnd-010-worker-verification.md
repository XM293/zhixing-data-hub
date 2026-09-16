# FND-010 Worker 验收记录

- 验收日期：2026-08-28
- 任务状态：`done`
- 数据库 revision：`0007_background_jobs`

## 自动化测试

- `packages/jobs/tests/test_jobs.py`：5 项，覆盖幂等入队、企业与发起主体/追踪持久化、失败重试、协作式超时、租约恢复和停止事件。
- `services/worker/tests/test_worker.py`：3 项，覆盖通用处理器注册、独立单次启动和缺少迁移时的明确失败。
- API 生命周期测试确认空库迁移创建 `background_jobs` 与 `job_attempts`，完整重建后仍到达 head。

## PostgreSQL 动态验收

在隔离项目 `zhixing-fnd010-verify`、PostgreSQL 16.15、数据库 `zhixing_fnd010_verify` 上执行：

1. 从空库升级到 `0007_background_jobs` 并播种企业数据。
2. 用相同 `(enterprise_id, job_type, idempotency_key)` 连续入队，确认只创建一个任务。
3. 在事务 A 对第一条候选任务持有行锁；事务 B 使用仓库领取接口，确认通过 `SKIP LOCKED` 取得第二条任务。
4. 释放行锁后领取并完成第一条任务。
5. 确认最终状态 `succeeded`，且 `run_id` 原样保留。
6. 运行 `worker.py --once`，确认 Worker 可独立启动并在无任务时退出。

动态探针返回 `idempotency_verified=true`、`skip_locked_verified=true`、`trace_verified=true`。随后已删除隔离容器、网络、命名卷和 `/tmp` 虚拟环境。

## 剩余边界

FND-010 只交付通用执行基础。具体同步、知识解析、Agent、评测和 Action 处理器，以及执行前 IAM 重新授权，仍由各自依赖任务实现。
