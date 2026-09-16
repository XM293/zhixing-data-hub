# Codex开发任务说明

`task-index.yaml` 是任务状态和依赖的唯一机器可读来源；各 `EPIC-*.md` 解释任务背景、交付边界和验收方式。

当前项目代码覆盖面已经领先于部分正式任务依赖。请先阅读 [`docs/PROJECT-STATE-AND-ROADMAP.md`](../docs/PROJECT-STATE-AND-ROADMAP.md)，理解 implementation、product_acceptance、production_readiness 三个成熟度维度；不要把 `blocked` 当成“没有代码”，也不要把 `implemented-slice` 当成已具备生产条件。

## 状态

- `ready`：依赖已满足，可以立即领取。
- `blocked`：依赖尚未完成，不应提前实施。
- `in_progress`：已有Codex任务正在执行。
- `review`：实现完成，等待验收或修正。
- `done`：验收通过。
- `deferred`：明确推迟到后续里程碑。

## 领取任务

向Codex提供：

```text
执行任务 <TASK_ID>。
先阅读 AGENTS.md、tasks/task-index.yaml 和任务所属EPIC文档；
确认依赖、输出和验收标准后完成实现、测试和文档更新。
```

## 里程碑

- `M0 产品全景与平台骨架`：先完成全景原型和产品负责人验收，再建设领域契约、身份权限、通用 Worker 和真实管理台能力。
- `M1 管理者分身试点`：制度、记忆、飞书问答、反馈和评测。
- `M2 数据与数字会议`：结构化经营数据、指标问数和多角色会议。
- `M3 运营执行`：巡店、行动中心、审批后执行和可靠工作流。
- `M4 客户服务`：面向店铺客户的辅助回复和受控自动沟通。

## 更新规则

Codex开始任务时将状态改为 `in_progress`；完成实现后改为 `review`并附验证记录；只有验收通过后改为 `done`。依赖任务完成时，维护者将可执行后继任务改为 `ready`。

`UIA-006` 是人工产品验收门。Codex 不得自行将其从 `review` 改为 `done`；产品负责人确认后才能解锁 `DOM-001` 和后续领域实现。
