# Codex 驱动研发工作方式

## 目标

让 Codex 成为主要的架构、编码、测试、文档和质量执行工具，同时通过清晰的任务边界、验收样例和版本化文档降低长周期开发中的上下文漂移。

官方 OpenAI 文档说明，Codex SDK 可用于 CI/CD、内部工具和应用集成，并能启动、继续和恢复本地 Codex 线程；App Server提供线程、Turn、事件和审批协议；Skill用于保存可重复工作流。因此本项目将这三类能力分别用于自动化研发、产品运行时适配和团队流程固化。

参考：

- https://learn.chatgpt.com/docs/codex-sdk
- https://learn.chatgpt.com/docs/app-server
- https://learn.chatgpt.com/docs/build-skills
- https://learn.chatgpt.com/docs/non-interactive-mode

## 人与 Codex 的职责

### 人类负责人

- 确认产品优先级、业务范围和验收样例。
- 在 `UIA-006` 验收导航、角色工作台、跨模块故事和整体产品方向。
- 决定指标口径、制度效力和角色授权。
- 审核关键架构决策、数据库迁移和外部系统动作。
- 组织员工试点并判断业务价值。

### Codex

- 把需求整理为任务、Schema、接口和测试。
- 实现前后端、连接器、MCP、数据转换和部署配置。
- 运行测试、评测、静态检查和UI流程验证。
- 对照任务验收标准修复问题并更新文档。
- 分析参考仓库，但不直接把参考项目改成产品代码。

## 标准任务循环

```text
选择 ready 任务
  → 读取上下文与依赖
  → 输出实施计划
  → 定义/更新契约与验收样例
  → 实现
  → 单元/集成/评测/UI验证
  → 自审 Diff
  → 更新任务和文档
  → 交付结果
```

## 产品全景验收门

在首轮领域实现前，Codex 先执行 `UIA-001` 至 `UIA-005`，交付真实可运行的产品全景。产品负责人在 `UIA-006` 提出保留、修改、合并和推迟意见；Codex 完成修正并生成验收报告后，由产品负责人决定是否解锁 `DOM-001`。

该验收门只验证产品体验和信息架构。UI Read Model、Fixture 和模拟命令不直接成为数据库或领域模型，验收后仍按 ADR-001 至 ADR-004 实现核心架构。

## Codex上下文设计

- 根 `AGENTS.md` 保存不可破坏的全局原则。
- 子模块成熟后可增加局部 `AGENTS.md`，只补充本领域规则，不复制根规则。
- `tasks/task-index.yaml` 是机器可读任务源。
- 每个任务包包含目的、依赖、输出、验收和非目标。
- ADR记录有长期影响的技术取舍。
- 评测集保存真实问题、预期证据和错误类型。
- 参考项目目录按领域分类，避免 Codex 无边界搜索所有代码。

## 建议创建的仓库Skill

后续通过 `skill-creator` 创建以下项目级Skill：

1. `create-source-connector`：创建连接器、规范映射、样例、契约测试和同步游标。
2. `add-business-metric`：新增指标定义、维度、SQL、对账样例和问数评测。
3. `add-mcp-tool`：创建工具Schema、应用服务适配、失败语义和工具测试。
4. `ingest-policy-corpus`：处理制度原件、版本、生效时间、解析和问答评测。
5. `evaluate-role-twin`：运行事实、证据、风格、拒答和冲突评测。
6. `release-internal-build`：执行迁移、检查、构建、变更日志和内部发布。

## 研发阶段使用方式

### 交互式开发

在 Codex App/CLI 中领取一个任务，允许读取源码、修改工作区和运行测试。复杂任务分多个 Turn持续执行，不把多个Epic塞进一个请求。

### CI任务

使用非交互模式或 Codex SDK执行文档一致性检查、测试失败分析、评测结果总结和候选修复。CI中的Codex默认只读或只生成补丁，不自动发布。

仓库统一入口为 `pnpm codex:task -- --task <TASK_ID>`，固定使用 `codex exec --ephemeral --sandbox read-only`。只有明确加入 `--write` 才切换为 `workspace-write`，且脚本会拒绝对非 `ready/in_progress` 任务开放写入。基础 CI 本身不调用模型、不持有模型密钥，只运行冻结依赖安装、`pnpm check` 和 `pnpm build`；需要 AI 分析时由受控流水线另行调用只读入口。

### 产品内运行

首期通过 `CodexRuntimeAdapter` 封装 Codex SDK/App Server。若使用 App Server，优先服务端本地进程或Sidecar通信；不把实验性 WebSocket接口直接暴露给用户渠道。

## 完成定义

一个开发任务只有同时满足以下条件才能标记完成：

- 任务约定的文件、接口或页面已经交付。
- 所有验收标准有可复现证据。
- 新逻辑有测试；模型行为有评测样例。
- 数据库或配置变更有迁移说明。
- 相关产品/架构/操作文档已经更新。
- 没有把后续工作藏在无编号 TODO 中；剩余事项必须进入任务索引。

全景原型任务还要求：所有模拟能力明确标识、跨页面对象一致、关键故事可复现；`UIA-006` 未经产品负责人确认不得标记完成。
