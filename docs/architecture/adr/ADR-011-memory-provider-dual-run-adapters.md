# ADR-011：长期记忆供应商双跑适配器

- 状态：Accepted
- 日期：2026-08-29
- 关联能力：受治理角色记忆、供应商评测、角色分身运行上下文

## 背景

平台需要验证 TencentDB-Agent-Memory 与 Mem0 对企业角色记忆的抽取和召回效果，但不能让任一供应商接管审核、版本、权限或业务真值。客户私有化部署的网络、认证和供应商版本也可能不同，因此上层产品不能依赖供应商内部对象 ID。

## 决策

1. `MemoryCandidate` 与 `ApprovedMemory` 继续保存平台审核状态、不可变版本、证据来源和有效期；供应商只接收当前评测需要的已生效记忆副本。
2. 通过自有 `MemoryProvider` 协议接入供应商。首批适配 TencentDB-Agent-Memory v3 Gateway 的 conversation/add 与 atomic/search，以及 Mem0 自托管 API 的 memories 与 search。
3. 每次双跑冻结同一基准版本、相同已生效记忆和相同 `top_k`，供应商使用按运行隔离的命名空间，避免评测相互污染。
4. 评测保存可信执行人、请求幂等键、基准快照、命中、Recall@K、平均/P95 延迟、逐题返回键和失败原因；一个供应商失败不阻断另一个结果落库。
5. 数据库只保存端点 SHA-256 指纹，不保存完整 URL、API Key、Token 或供应商认证头。认证仅从运行环境读取。
6. 本地 `services/mock-memory` 是独立协议测试服务，模式明确标记为 `contract-sandbox`；它验证适配器与故障隔离，不代表真实供应商效果。
7. 供应商返回的记忆 ID 不进入平台领域契约；评测通过平台 `memory_key` 和内容相似度回映射。

## 参考基线

- TencentDB-Agent-Memory：MIT，`references/open-source/memory/TencentDB-Agent-Memory`，锁定提交 `97f94654280b`。
- Mem0：Apache-2.0，`references/open-source/memory/Mem0`，锁定提交 `8d5b7865bd05`。
- 参考仓库保持只读；实现只采用公开 HTTP 契约和边界设计，不复制供应商领域模型。

## 后果

平台可以在本地协议沙箱、客户私有部署或后续其他供应商之间切换，而不重写角色记忆治理与分身运行链。代价是需要维护适配器、版本化基准和供应商兼容测试。本纵向切片不表示正式 `MEM-005` 已完成；生产部署、真实数据对照、容量与故障演练仍受原任务依赖约束。
