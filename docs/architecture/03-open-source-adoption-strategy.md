# 开源项目采用策略

## 原则

参考项目用于缩短验证时间和吸收成熟设计，不直接决定产品领域模型。所有业务能力先通过自有接口表达，再决定使用开源组件、自研实现或云服务。

## 项目映射

### WeKnora

- 本项目用途：首期知识中心产品壳、文档解析、RAG、版本和飞书/IM接入能力的重点 POC。
- 重点阅读：知识库模型、文档版本、解析流水线、检索、工作区和 MCP。
- 不承担：经营数据仓库、统一指标、角色长期记忆和业务执行。
- 采用方式：优先做旁路 POC，通过 `KnowledgeProvider` 适配，不让上层保存 WeKnora 内部 ID。

### RAGFlow

- 本项目用途：复杂 PDF、表格、扫描件解析和检索效果对照组。
- 重点阅读：文档解析器、切片策略、检索和评测。
- 不承担：企业统一知识产品的默认结论；仅在 POC 结果优于 WeKnora 时替换或组合。
- 当前纵向切片：通过 `KnowledgeProvider` 适配器和独立 `mock-knowledge` 契约沙箱验证 `retrieval` API、文档范围约束和逐题 MRR/Recall 评测；结果只写入平台评测台账。

### 知识与上下文 Provider 多路评测边界

- WeKnora、RAGFlow 与 OpenViking 可以并行接收同一批当前生效知识切片，但不能成为制度版本、文档生命周期或证据权限的事实来源。
- 平台为每次运行创建隔离命名空间，检索请求只允许返回该运行的文档范围，再用稳定 `chunk_key` 回映射供应商结果。
- 真实部署前必须用客户样本补充 PDF、表格、扫描件、中文术语和权限过滤评测；本地沙箱的延迟和命中率不能外推到生产。

### OpenViking

- 本项目用途：Agent Context 层、层次上下文、资源/记忆/Skill统一组织和渐进加载设计参考。
- 重点阅读：上下文文件系统、检索协议、MCP、版本和多租户。
- 不承担：数据仓库、制度原件系统或企业指标层。
- 采用方式：已通过自有 Provider 边界接入公开 `/content/batch-write` 与 `/search/find` HTTP 契约，仅验证 resource context 的分层检索；其 AGPLv3 服务保持独立，产品化部署、分发或修改前需要单独许可证决策。

### TencentDB-Agent-Memory

- 本项目用途：角色事实、场景记忆、人格记忆、团队 Memory Hub 设计参考和候选后端。
- 重点阅读：记忆分层、抽取、去重、版本、Owner和状态流转。
- 不承担：正式制度和经营事实。
- 采用方式：已按 v3 Gateway 公开 HTTP 契约实现 `MemoryProvider` 适配器；双跑只索引当前评测的已生效记忆副本，不允许代理式接管全部模型流量。

### Mem0

- 本项目用途：长期记忆 API 和抽取效果对照基线。
- 重点阅读：memory add/search/update、图记忆与评测。
- 采用方式：已按自托管 memories/search 公开 HTTP 契约实现 `MemoryProvider` 适配器，用同一评测集横向对比，不先预设最终后端。

### OpenMetadata

- 本项目用途：未来数据目录、血缘、数据质量、连接器和数据资产治理参考。
- 首期使用：只参考领域模型和连接器规范，不立即部署完整平台。
- 引入条件：来源系统和数据资产数量足以让人工目录维护成为瓶颈。

### MetricFlow

- 本项目用途：GMV、退款率、毛利、库存周转和广告ROI等指标语义层参考。
- 首期使用：借鉴语义模型和查询规划，先实现最小指标注册与查询契约。
- 引入条件：指标和维度组合显著增加，最小实现不足以维护一致口径。

### Codex

- 本项目用途：Codex Harness、App Server、工具调用、沙箱、审批和跨轮任务实现参考；也是全程研发的主要执行环境。
- 不承担：企业数据治理、知识真值或业务领域模型。
- 采用方式：实现 `CodexRuntimeAdapter`，领域层保持运行时无关。

### LangGraph

- 本项目用途：数字会议、显式状态机、多步骤Agent编排的备选。
- 首期使用：参考流程建模，不与业务领域直接耦合。
- 引入条件：简单应用服务无法清楚表达会议、重试、人工中断和分支。

### Temporal

- 本项目用途：跨小时/跨天、可重试、可补偿的可靠业务工作流。
- 首期使用：阅读设计，不部署。
- 引入条件：巡店、批量任务或跨系统执行需要可靠恢复，普通任务队列无法满足。

### MCP Python SDK

- 本项目用途：企业自有 MCP 网关和工具 Schema 的标准实现参考。
- 采用方式：已正式采用官方 SDK 2.x 建立 STDIO 网关，当前发布 `read_policy`、`search_knowledge`、`get_metric` 和 `query_commerce_facts` 四个 R0 工具；业务逻辑、授权、客户范围映射和数据范围仍在内部应用服务。
- 代码边界：SDK 只负责协议、Schema、结构化输出和工具注解，不复制企业领域模型，不直接访问数据库。

### PigX 5.9.0（已授权参考工程）

- 本项目用途：企业管理平面能力、后台信息架构和管理交互的参考来源。
- 重点阅读：用户、组织、岗位、角色、菜单、审计、配置、通知、文件和批量管理流程。
- 不承担：知行数枢的企业数据中心、指标语义、正式知识、角色记忆、AI 运行、MCP 授权和行动真值。
- 采用方式：选择性吸收并使用知行数枢自有契约重写；不直接依赖 PigX 内部 ID、`sys_*` 表、Spring Cloud 基础设施或私有 API。
- 首期排除：Nacos、Gateway、Seata、Sentinel、Quartz、XXL-Job、Flowable、微信和支付等非必要运行时。
- 许可边界：用户已确认拥有商业授权；任何实际复制或分发代码前仍需保留许可证和版本来源记录，并单独评估升级与分发义务。
- 详细执行边界：见 `docs/development/06-pigx-selective-capability-integration-guide.md` 和 ADR-021。

## 推荐结论

首期默认组合：

```text
自有模块化应用 + PostgreSQL + MinIO
        │
        ├─ WeKnora（知识 POC）
        ├─ 自有 Memory Candidate 审核流
        ├─ 最小指标语义服务
        ├─ 自有 MCP/Tool Gateway
        ├─ Codex Runtime Adapter
        └─ PigX 管理能力参考（选择性重写，不作为核心依赖）
```

TencentDB-Agent-Memory 与 Mem0 已进入可审计双跑纵向切片：开发环境通过独立 `contract-sandbox` 验证双方公共协议，客户部署只需替换端点与运行时认证。其结果不会覆盖平台 `MemoryCandidate` / `ApprovedMemory` 真值。WeKnora、RAGFlow 与 OpenViking 已进入知识/资源上下文多路评测切片，知识中心可显示当前生效文档体量、Provider 模式、端点指纹、逐题命中、Recall@3、MRR 和延迟；OpenViking 的记忆、Skill 和 Session 接管仍未采用。OpenMetadata、MetricFlow、LangGraph 和 Temporal 在满足明确引入条件后再进入正式依赖。
