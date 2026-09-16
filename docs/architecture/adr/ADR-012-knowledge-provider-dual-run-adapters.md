# ADR-012：知识与上下文 Provider 多路评测适配器

- 状态：Accepted（纵向切片）
- 日期：2026-08-29
- 关联能力：企业知识中心、证据检索、角色分身、供应商评测

## 背景

知行数枢需要把企业自己的文档、版本、生效窗口和证据切片作为长期真值，同时保留接入 WeKnora、RAGFlow、OpenViking 或客户自建检索服务的选择。供应商的知识库 ID、上下文 URI、分词方式、索引生命周期和返回字段都可能不同，不能让这些内部对象渗透到平台的知识治理、问答或权限模型。

## 决策

1. `KnowledgeDocument`、`KnowledgeVersion` 和 `KnowledgeChunk` 是平台唯一知识真值。多路评测只读取当前时点已生效且 `indexed` 的切片，并保存不可变的题集与内容范围快照。
2. 通过自有 `KnowledgeProvider` 协议封装健康检查、批量索引和受限检索。当前实现提供 WeKnora `knowledge-search`、RAGFlow `retrieval` 与 OpenViking resource context 三个适配器；未来连接器只需实现同一协议。
3. 每次运行给每个 Provider 使用独立命名空间，并在检索请求中限制该运行创建的知识/文档 ID，避免历史运行污染命中结果。供应商返回的 ID 不进入领域契约，平台通过稳定 `chunk_key` 标记和内容相似度回映射。
4. 固定基准题集从当前生效切片的章节标题生成，记录命中数、Recall@K、MRR、平均/P95 延迟、逐题返回切片键和脱敏失败原因；单个 Provider 失败时保留其他 Provider 的结果。
5. API 使用专门的 `knowledge.provider.evaluate` 权限，沿用 ActorContext、企业范围、请求/运行追踪和幂等键。UI 只投影权限，不能绕过后端授权。
6. 开发环境的 `mock-knowledge` 是独立 HTTP 契约沙箱，端口 `8300`，明确显示 `contract-sandbox`。它模拟三类公开协议、范围隔离和故障隔离，不代表真实供应商的相关性或容量表现。
7. 平台不在数据库中保存完整 Provider URL、API Key 或认证头，只保存端点 SHA-256 指纹；真实端点和凭证由运行环境注入。
8. OpenViking 只接收 `viking://resources/zhixing-evaluations/{run}` 下的运行隔离副本，评测固定使用 L2 resource 检索并从 URI 回映射稳定 `chunk_key`。OpenViking 的 memory、skill、session 和自动沉淀能力不在本切片内。
9. OpenViking 采用 AGPL-3.0。平台只实现独立 HTTP 客户端，不复制或修改其代码；客户正式部署、分发或定制 OpenViking 服务前必须完成单独的许可证与采购决策。

## 参考基线

- WeKnora：`references/open-source/knowledge/WeKnora`，MIT（部分第三方组件另有许可），锁定提交 `412dcc41c662`。
- RAGFlow：`references/open-source/knowledge/RAGFlow`，Apache-2.0，锁定提交 `2db8eb6c9118`。
- OpenViking：`references/open-source/context/OpenViking`，AGPL-3.0，锁定提交 `6e944cc3e148`。
- 参考仓库保持只读；实现只采用公开 HTTP 契约，不复制其内部表结构或领域模型。

## 后果与边界

平台能够在本地沙箱、客户私有部署和后续其他检索/上下文引擎之间切换，并用同一题集做可审计对照。单个 Provider 失败时运行状态为 `partial`，其他结果仍可使用，失败信息在持久化前脱敏。代价是每个 Provider 需要独立的契约测试、索引清理策略、容量评测和许可证判断。本切片不表示 `KNO-004`、`KNO-005` 或 `KNO-008` 已完成；真实连接、生产容量、文档解析质量和安全评审仍按原任务依赖推进。
