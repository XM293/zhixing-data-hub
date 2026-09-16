# 受治理角色记忆实现基线

## 1. 目标

角色分身不能把聊天记录直接当作企业事实。聊天原件先保留为可追溯消息，再抽取为 `MemoryCandidate`；只有经过授权人员审核并显式激活的 `ApprovedMemory` 才能进入分身上下文。

## 2. 数据链路

```text
聊天原件
  -> ChatImportRun
  -> ChatMessage（时间、参与者、话题、原文）
  -> MemoryCandidate（去重、置信度、制度冲突）
  -> 审核事件
  -> ApprovedMemory 不可变版本
  -> 激活 / 退役
  -> AgentRunContextItem
```

`MemoryCandidate` 是审核队列，不是长期记忆真值。`ApprovedMemory` 保存审核后内容、来源证据和版本；供应商记忆 ID 不进入该领域契约。

## 3. 状态机

| 当前状态 | 命令 | 下一状态 | 约束 |
|---|---|---|---|
| `candidate` | approve | `approved` | 待核验内容必须明确完成制度核验 |
| `candidate` | reject | `rejected` | 不创建长期记忆版本 |
| `approved` | activate | `active` | `conflict_status` 必须为 `clear` |
| `active` | retire | `retired` | 保留历史版本和既有运行引用 |

冲突候选可以通过 `retain_conflict` 被批准为历史记录，但不能激活。重复命令返回同一个生命周期事件，不重写历史。

## 4. 身份职责

- 平台管理员：`memory.chat.ingest`、`memory.candidate.read`；可以导入和查看，不能替业务负责人审核。
- CEO 测试主体：`memory.candidate.review`、`memory.approved.retire`；可以审核、激活和退役，不能导入原件。
- API 在每个命令入口重新授权；按钮可见性只用于用户体验。

其他部门负责人接入前，需要把当前企业范围进一步收窄为分身所有者或被委托对象范围。

## 5. 上下文优先级

分身回答按以下顺序解释信息：

1. 当前生效制度和结构化经营事实；
2. 已审核且已激活的角色记忆；
3. 模型一般能力仅用于组织表达，不生成企业事实。

每次运行同时写入 `agent_run_evidence` 和 `agent_run_context_items`。前端将正式证据显示为 `E1...`，长期记忆显示为 `M1...`，不把两者混成同一种来源。

## 6. 当前边界

- 首期解析 Markdown/文本式聊天导出，支持日期、发言人、续行和话题标题。
- 原始聊天目前存储在数据库；大文件、附件、语音/OCR 和对象存储清单后续迁移到 Worker。
- 候选抽取和数值冲突识别当前采用确定性规则，为供应商双跑提供可重复基线。
- 当前不自动修改候选原文；AI 清洗、合并和摘要必须生成新候选并保留原始消息引用。

## 7. 供应商双跑运维

`/api/v1/memories/provider-operations` 返回当前供应商目录、脱敏端点指纹、固定问题集和历史运行；具备 `memory.candidate.review` 的主体可以发起新评测。每次运行将同一批 `ApprovedMemory(status=active)` 写入供应商隔离命名空间，然后对相同问题执行检索并保存逐题命中、Recall@3、平均/P95 延迟和失败原因。

开发环境的 `services/mock-memory` 仅模拟 TencentDB-Agent-Memory v3 与 Mem0 自托管 HTTP 契约，界面必须显示 `contract-sandbox`，不能把结果描述为真实供应商性能。客户部署通过环境变量替换端点和认证；数据库仅保留端点指纹。详细边界见 `ADR-011-memory-provider-dual-run-adapters.md`。
