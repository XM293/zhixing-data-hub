# 后台任务与 Worker

状态：Implemented / Accepted  
任务：`FND-010`

## 责任边界

- `packages/jobs`：稳定任务契约、ORM 映射、幂等入队、领取、状态迁移、租约恢复和 Runner。
- `services/worker`：数据库连接、处理器注册、轮询循环、信号停止和进程入口。
- `services/api/migrations`：唯一生产建表入口。运行时代码不得调用 `create_all`。
- 业务模块：只登记自己的 `job_type` 与处理器，不复制队列状态机。

M0 使用 PostgreSQL 任务表，不引入 Redis Broker。领取语句使用事务和 `FOR UPDATE SKIP LOCKED`，使多个 Worker 不会串行等待同一候选任务。

## 状态机

```text
queued ────────┐
               ├─ claim ─> running ─> succeeded
retry_wait ────┘                ├──> retry_wait（可重试且仍有次数）
                                └──> failed（永久失败或次数耗尽）

running + lease expired ────────> retry_wait / failed
```

每次领取都会增加 `attempt` 并创建独立 `job_attempts` 记录。任务行保存最新状态，尝试行保留每次执行结果；不能通过覆盖错误字段假装从未失败。

## 可信上下文与幂等

任务必须保存：

- `enterprise_id`；
- `initiator_type` 与 `initiator_id`；
- `request_id` 与 `run_id`；
- `(enterprise_id, job_type, idempotency_key)` 唯一键。

Worker 在执行处理器时重新绑定任务中的追踪上下文。未来 IAM 完成后，写任务还必须保存授权快照引用并在执行前重新授权；FND-010 不伪造尚未实现的 ActorContext。

## 重试、超时与停止

- 可重试错误使用指数退避，达到 `max_attempts` 后进入 `failed`。
- 处理器可调用 `JobExecutionContext.ensure_active()` 做协作式超时检查；Runner 在处理器返回后再次检查截止时间。
- 租约至少覆盖任务超时时间；进程失联后由其他 Worker 将过期任务恢复到重试队列。
- HTTP、模型和外部 SDK 必须设置不晚于任务截止时间的自身超时。Python 线程无法安全强杀阻塞调用，因此当前框架不声称提供进程级硬终止。
- `SIGINT/SIGTERM` 设置停止事件；空闲轮询立即唤醒并退出，执行中的处理器完成当前尝试后退出。

当长工作流需要可靠计时器、人工暂停或补偿时，按 ADR-002 评估 Temporal，而不是继续扩张这张任务表。

## 运行

```powershell
pnpm db:upgrade
pnpm worker:once
pnpm worker:run
```

`pnpm dev` 已登记 Worker。SQLite 只用于本地单进程体验；并发领取验收和部署必须使用 PostgreSQL。

## 已登记业务处理器

DAT-011 / 0064：`data-source.sync` 在 Worker 中直接执行只读 Provider，按页归档并提交规范映射与 checkpoint，不回调 API 执行采集。达到 100 页、180 秒或剩余期限不足 30 秒时，在已提交页之后发出 `JobContinuation`，释放领取权并重新排队。同一任务与父子运行继续使用原追踪标识。`attempt` 是领取轮次；`continuation_count` 是正常续跑次数；失败重试预算使用两者之差。`continuation_progress` 必须单调递增，续跑时校验有效且未过期的执行令牌，取消与失租不能续跑。

续跑不改变 max_attempts。人工重试只补充扣除正常续跑后的执行预算；`JobAttempt.status=continued` 保留每轮审计。升级 0064 后旧任务新增字段为 0。回滚前需停止并排空 Worker；不得让旧程序读取含正常续跑但无法识别其预算的任务。定时校正失败/取消 Job 对应的非终态来源台账，先提交子运行校正再刷新父批次，避免锁顺序反转；Provider 关闭时仍执行状态校正，不产生新的采集任务。

| `job_type` | 处理器责任 | 领域真值位置 |
|---|---|---|
| `system.noop` | 验证领取、完成和追踪上下文 | Worker 验收处理器 |
| `analysis.daily-store-review` | 调用已领取任务对应的经营巡店领域入口 | API 的分析、授权、证据与行动服务 |

巡店处理器只传递数据库任务 ID，不把计划、经营事实或账号权限复制进 Worker。API 要求该任务存在、类型匹配且处于 `running`，随后依据计划创建人的当前数据库账号重新构造 `ActorContext`。HTTP 5xx 与网络故障按可重试错误处理，业务拒绝按永久错误处理。

本地私有部署当前以“同库任务状态 + 仅本机 API”约束内部执行入口。进入多主机或不可信网络部署前，必须补充独立服务身份认证和网络边界；不能把任务 ID 本身视为服务凭证。
