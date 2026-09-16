# 知识检索与角色分身问答实现基线

## 1. 当前交付范围

本轮建立第一条数据库到 AI 的真实纵向链路：企业测试资料进入版本化知识表，服务按章节切片并建立可替换检索索引，角色分身只使用返回的证据回答，回答、运行参数和实际引用全部持久化。

这条链路证明系统不是静态演示，但不等于完整知识平台已经完成。迁移 `0016_knowledge_ingestion_lifecycle` 已补充同步资料导入、内容哈希去重、结构化切片、规则冲突提示、版本发布/退役和生命周期台账。对象存储原件、后台解析队列、正式认证边界、完整知识范围交集、语义向量检索和跨领域冲突检测仍按后续任务实现。

## 2. 数据模型

Alembic `0010_knowledge_and_agent_runs` 建立知识和分身问答表，`0016_knowledge_ingestion_lifecycle` 增加导入与生命周期记录：

| 表 | 责任 |
|---|---|
| `knowledge_documents` | 企业知识对象、稳定业务键、知识空间、责任方、来源与内容哈希 |
| `knowledge_versions` | 不可变正文版本、发布状态、生效区间和变更摘要 |
| `knowledge_chunks` | 章节切片、稳定定位、索引状态和解析元数据 |
| `role_twin_profiles` | 稳定分身标识、岗位模板引用和负责人引用，不保存 `AccessRole` |
| `role_twin_versions` | 不可变个人配置版本、模板版本引用、模型、能力与三类行为规则 |
| `agent_runs` | 问题、结构化回答、实际分身版本、运行模式、模型、耗时、用量和降级原因 |
| `agent_run_evidence` | 一次运行实际使用的切片、排序分数、摘录和引用标签 |
| `agent_run_context_items` | 一次运行实际使用的已审核长期记忆或指标序列 ID、口径版本、摘要和引用标签 |
| `knowledge_ingestion_runs` | 一次导入的来源、哈希、解析器、切片数、重复/冲突状态和追踪标识 |
| `knowledge_lifecycle_events` | 发布、计划生效和退役命令的主体、理由、业务时间与追踪标识 |

角色分身配置不保存 `AccessRole`。问答入口通过受信 `ActorContext` 检查 `role-twin.invoke` 和 `knowledge.document.read`；检测到经营指标意图时再检查 `metric.query.execute` 与企业/门店数据范围。浏览器仍通过本地开发身份提供者选择测试主体，正式认证接入后只替换身份来源，不改变授权和上下文组装规则。

## 3. 测试知识集

种子版本 `1.6.0` 提供 6 份模拟电商企业资料和 7 个版本，覆盖：

- 电商运营绩效制度 v2 与未来生效的 v3；
- 广告预算审批与止损；
- 库存预警和补货协同；
- 客服补偿与人工升级；
- 店铺经营异常处置；
- 广告预算与库存联动会议决议。

这些资料是确定性测试数据，不代表客户真实制度。客户实施时通过知识导入契约新增或替换内容，不修改上层页面和问答响应结构。

## 4. 检索适配层

首期 `local-lexical-v1` 使用中文二至四字词元、英文业务词、标题命中、版本状态和生效时间进行确定性排序。选择该实现是为了让 SQLite 与 PostgreSQL 环境都可直接验收，并为后续质量对照提供稳定基线。

检索响应统一返回文档键、版本、状态、生效时间、标题、原文定位、摘录和相对分数。WeKnora、RAGFlow 与 OpenViking 已通过 Provider 多路评测验证稳定切片键回映射；后续替换为真实端点、pgvector 或其他引擎时，不改变业务 API、证据记录和前端组件。

## 5. 模型适配层

`ResponsesAIProvider` 使用 OpenAI 兼容的 `/v1/responses` 接口：

1. 首选严格 JSON Schema 输出；
2. 兼容服务拒绝 `metadata` 时，仅移除该字段并重试；
3. 服务仍拒绝结构化格式时，退到普通 JSON 文本并在本地校验；
4. 输出含未在输入证据中出现的数值或日期时，不放宽守卫，执行一次受控修正重试；第二次仍不合格才降级；
5. 模型不可用、响应无效或未配置时，返回明确标注的确定性证据摘要；
6. 所有模式都保存 `agent_runs`、`agent_run_evidence` 和 `agent_run_context_items`，不丢失可复现性。

提示词把角色表达方式、分析规则和回答政策分开。模型只能使用输入的正式证据、授权经营数据与已激活长期记忆，不输出隐藏思维过程；正式制度和带口径版本的经营指标优先于角色记忆。面向用户的结果固定分为结论、可核验事实、建议动作、限制与未知、置信度。

密钥只通过 `AI_API_KEY` 环境变量传入。仓库不读取本机秘密文件，也不保存密钥或第三方管理凭证。

## 6. API 与页面

API：

- `GET /api/v1/knowledge/documents`
- `GET /api/v1/knowledge/evidence/search`
- `POST /api/v1/knowledge/ingestions`
- `GET /api/v1/knowledge/ingestions`
- `GET /api/v1/knowledge/versions/{version_id}`
- `GET /api/v1/knowledge/policies/{document_key}/effective?as_of=...`
- `POST /api/v1/knowledge/versions/{version_id}/publish`
- `POST /api/v1/knowledge/versions/{version_id}/retire`
- `GET /api/v1/twins/{twin_key}`
- `POST /api/v1/twins/{twin_key}/answers`

分身回答契约为 `contracts/twin/role-twin-answer.schema.json` v3。请求可选传入 `scope_key`；未指定时，企业负责人自动使用企业范围，部门经理和员工自动收敛到首个已授权门店。响应分别返回：

- `D1...Dn`：指标键、范围、口径版本、时间区间、最新值、区间变化、最值和日序列；
- `E1...En`：正式制度/知识版本、原文定位和检索相关度；
- `M1...Mn`：已审核且已激活的角色记忆、版本和来源。

指标意图与时间窗由独立 `agent_context_service` 解析。当前支持成交、订单、退款率、广告 ROI、低库存 SKU 和活跃会员；“近 N 天”限制在 1 至 365 天，通用经营趋势问题默认读取成交、订单、退款率和广告 ROI 四项 30 日序列。该模块只消费统一指标服务，不读取第三方字段。

数据库页面：

- `/console/knowledge/documents`
- `/console/knowledge/policies`
- `/console/knowledge/ingestion`
- `/console/knowledge/evidence`
- `/console/assistant`
- `/console/analysis/ask`

## 7. 后续完成条件

- 正式认证提供受信 `ActorContext`，取消浏览器开发身份头；
- 原件进入 MinIO；当前已具备哈希去重，解析和索引还需改为后台任务；
- 当前发布和退役已形成授权命令与生命周期事件；后续加入可配置的多人审批策略；
- 建立向量召回、重排和相同问题集评测，决定首期知识 provider；
- 将当前同一制度版本的规则冲突提示扩展到正式知识、经营事实和审核记忆之间的跨领域冲突；
- 分身管理页已支持岗位模板、个人实例和不可变配置版本发布；回归评测、反馈纠错与人工接管继续按后续任务实现。

## 8. 2026-08-28 经营上下文验收

- CEO 真实模型请求读取企业范围 4 条指标序列，每条包含 30 个数据库日点，执行模式为 `model`，模型为 `gpt-5.4-mini`；
- 员工同一问题自动使用 `store-flagship` 范围和 30 个日点；显式请求 `enterprise` 返回 `authorization.scope_denied`；
- 每条指标序列以 `metric-series` 写入运行上下文，保存指标定义版本、范围、内容哈希与引用标签；
- 数值守卫会把千分位金额与普通十进制、中文年月日与 ISO 日期归一为同一声明，避免把等价格式误判为幻觉；
- `/console/assistant` 同屏展示 D 数据证据、E 正式证据和 M 角色记忆；1280px 默认视口与 390×844 移动视口均无页面级横向溢出；
- 该纵向切片满足带证据问答的主要行为，但 `TWI-003` 仍保持 `in_progress`：完整能力交集还依赖任务索引中的 `TWI-001`、`AGT-005`、`AGT-006` 和 `IAM-004` 正式完成。

## 9. 2026-08-28 正式角色版本验收

- `0019_role_twin_versioning` 将岗位模板、分身稳定对象和不可变分身版本分开；负责人只引用企业主体，角色对象不复制访问角色；
- 管理台完成客户体验负责人岗位模板 v1、分身 v1 和强化风险表达的分身 v2 创建与发布，旧版本保持可追溯；
- 真实模型使用 `gpt-5.4-mini` 完成高风险客服会话回答，返回 4 条证据、4 项行动和高置信度结果；
- 数据库确认该 `AgentRun` 绑定已发布的 `RoleTwinVersion v2`，后续配置变化不会改写这次运行；
- 1280×720 和 390×844 浏览器视图无页面级横向溢出，控制台无应用错误。
