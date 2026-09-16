# 本地开源参考仓库

这些仓库采用浅克隆，仅用于架构研究、POC和实现模式参考。它们不是本项目源码的一部分，默认只读，不进入知行数枢主仓库版本历史。

| 分类 | 项目 | 本地目录 | 主要参考内容 | 许可证 |
|---|---|---|---|---|
| 知识 | WeKnora | `knowledge/WeKnora` | 企业知识库、解析、RAG、版本、MCP、渠道 | MIT（部分第三方组件另有许可） |
| 知识 | RAGFlow | `knowledge/RAGFlow` | 复杂文档解析、检索、知识工作流 | Apache-2.0 |
| 上下文 | OpenViking | `context/OpenViking` | Agent Context、资源/记忆/Skill、层次检索 | AGPL-3.0 |
| 记忆 | TencentDB-Agent-Memory | `memory/TencentDB-Agent-Memory` | 分层长期记忆、团队Memory Hub | MIT |
| 记忆 | Mem0 | `memory/Mem0` | 长期记忆API和对照评测 | Apache-2.0 |
| 数据治理 | OpenMetadata | `governance/OpenMetadata` | 数据目录、血缘、质量、连接器、MCP | Apache-2.0 |
| 指标 | MetricFlow | `metrics/MetricFlow` | 指标语义、维度、查询规划 | Apache-2.0 |
| 运行时 | Codex | `runtime/Codex` | Agent Harness、App Server、工具、审批 | Apache-2.0 |
| 编排 | LangGraph | `orchestration/LangGraph` | 显式Agent状态机和多步骤编排 | MIT |
| 工作流 | Temporal | `workflow/Temporal` | 可靠长任务、重试和补偿 | MIT |
| 协议 | MCP Python SDK | `protocol/MCP-Python-SDK` | 企业MCP服务器和工具Schema | MIT |

## 使用顺序

1. 先阅读 `docs/architecture/03-open-source-adoption-strategy.md`。
2. 根据当前任务只进入一个或两个相关仓库。
3. 优先查找公开接口、领域模型、测试和部署边界，不从UI表象推断架构。
4. 采用设计前写ADR；复制代码前核对具体文件许可证和NOTICE要求。

## 更新仓库

仓库为浅克隆。更新单个仓库时进入其目录执行 `git pull --ff-only`，随后更新 `repos.lock.yaml` 中的分支、提交和日期。不要一次性无目的更新全部参考项目。

## 注意

OpenViking采用AGPL-3.0，研究和独立POC不等于可以无条件嵌入闭源产品。正式采用方式需要单独的许可证决策。此提醒不阻塞当前开发验证。

