# 数据目录、质量控制与可伸缩测试接入

- 日期：2026-08-28
- 数据库修订：`0043_channel_identity_bindings`
- 适用范围：企业数据中心首个可运行纵向切片

## 1. 已实现边界

数据中心的七个页面均读取持久化数据库，不再使用前端 Fixture：

- 数据源：来源注册、契约版本、映射版本、同步链路和生产规模差距；
- 同步任务：批次状态、场景、规模档位、读写量、耗时、告警和错误；
- 经营事实：订单、订单行、退款、库存与广告事实的范围化汇总和血缘；
- 客户 360：CRM 客户主档、触点行为、ERP 交易价值、生命周期、流失风险和可审计单客时间线；
- 企业实体：稳定业务键、六类统一实体、属性投影、筛选和分页；
- 指标目录：口径、公式、维度、责任方、版本与最新指标快照；
- 数据质量：规则、最近检查结果、影响记录和 `sync_run_id`。

相关 API：

```text
GET  /api/v1/data-center/overview
GET  /api/v1/data-center/sync-runs
GET  /api/v1/data-center/entities
GET  /api/v1/data-center/metrics
GET  /api/v1/data-center/metric-series
GET  /api/v1/data-center/commerce-operations
GET  /api/v1/data-center/customer-360
GET  /api/v1/data-center/customer-360/{customer_key}
GET  /api/v1/data-center/quality
POST /api/v1/data-center/sources/{source_key}/sync
GET  /api/v1/customer-operations/studio
POST /api/v1/customer-operations/plans
POST /api/v1/analysis/runs/{analysis_run_id}/action-proposals
GET  /api/v1/analysis/review-plans
POST /api/v1/analysis/review-plans
POST /api/v1/analysis/review-plans/{plan_key}/actions
GET  /api/v1/action-work-items
POST /api/v1/action-work-items/{work_key}/events
```

## 2. 数据存储结构

```text
ExternalSystem
  -> SyncRun(volume_profile)
      -> SourceRecord(source_schema_version, mapping_version, content_hash)
      -> BusinessEntity(entity_type, canonical_key, attributes)
      -> MetricSnapshot(metric_key, scope_key, as_of)
      -> DataQualityResult(rule_id, sync_run_id, checked_at)
      -> CustomerProfile(customer_key, lifecycle_stage, churn_risk_score)
      -> CustomerTouchpointFact(customer_key, touchpoint_type, occurred_at)

CommerceOrderFact / CommerceRefundFact
  -> 按稳定 customer_key 进入客户价值汇总

CustomerOperationRun
  -> EvidenceSnapshot -> EvidenceSnapshotItem
  -> 结构化诊断与人工审批动作

BusinessAnalysisRun
  -> 经营建议 -> ActionProposal(source_type=business-analysis)
      -> ActionApprovalEvent -> ActionExecution(external_write=false)
      -> ActionWorkItem -> ActionWorkEvent

StoreReviewPlan
  -> StoreReviewScheduleRun -> BackgroundJob(analysis.daily-store-review)
      -> BusinessAnalysisRun -> BusinessBrief
      -> 可选 ActionProposal(status=pending_approval)

MetricDefinition(version, formula_expression, dimensions, owner)
DataQualityRule(category, asset_type, asset_key, expectation, severity)
```

原始记录保留第三方字段，统一实体通过通用的 `entity_type + canonical_key + attributes` 承载。未知客户字段优先在来源适配器和版本化映射中处理；只有跨客户稳定、需要数据库约束的概念才进入新的核心表或迁移。客户主档和触点已满足该条件，因此进入独立事实表；成交额和退款额继续由规范 ERP 事实提供，CRM 不成为第二套交易真值。

## 3. 第三方测试服务规模档位

测试服务生成确定性数据，同一档位重复请求得到相同明细对象，便于回归和内容哈希去重。平台通过四个连接器配置分别读取 ERP/OMS、CRM、广告和客服资源；`/api/v1/metrics/daily` 按 `domain` 输出各来源连续 90 天的企业与门店指标。第三方指标码由各来源独立的 `mapping_version` 映射为内部稳定指标键。

| 档位 | 店铺 | 商品 | SKU | 仓库 | 客户 | 客户触点 | 订单 | 广告计划 | 客服会话 | 统一实体总量 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| small | 3 | 12 | 36 | 2 | 18 | 108 | 24 | 24 | 60 | 179 |
| standard | 6 | 36 | 144 | 5 | 90 | 540 | 180 | 96 | 360 | 917 |
| large | 12 | 120 | 600 | 12 | 600 | 3,600 | 1,200 | 480 | 2,400 | 5,424 |

`scenario` 与 `volume_profile` 相互独立：前者验证正常、延迟、部分失败和连接失败；后者验证页面密度、分页和写入规模。两者都随同步批次持久化，保证问题可复现。

## 4. 当前规模判断

大型档已经足以验收高密度列表、类型筛选、分页、质量结果、90 天趋势和超宽屏布局，但不代表生产规模。2026-08-30 更新后的 CRM 大型同步读取 7,814 条资源记录并写入/更新 12,630 个数据库对象；数据库当前累计形成 50,131 条原始记录、18,761 条规范经营事实、600 个客户主档、3,600 条行为触点、5,424 个统一实体和 21 个已发布指标口径：

- 当前测试实体 5,424 / 首期接入验收基线 20,000，约 27.1%；
- 当前累计原始记录 50,131 / 首期接入验收基线 100,000，约 50.1%；
- 当前数据源 4 / 首期接入验收基线 4，四源均在线；
- 当前指标 21 / 首期接入验收基线 30，覆盖经营、供应链、会员、投放和服务质量。

真实接入前仍需补充供应商、组织引用、库存批次、订单明细、客户身份合并、同意变更历史、售后工单和更长保留期的历史事实。数据源页必须持续展示当前值与首期接入验收基线，不允许以测试档位替代容量验收。生产容量、历史保留年限和峰值吞吐必须在客户现场盘点后单独定标。

## 5. 后续接入规则

1. 每个客户系统实现独立连接器，返回统一 `ConnectorBatch`。
2. 原始响应先写 `SourceRecord`，映射失败不能覆盖原始证据。
3. 映射变更提升 `mapping_version`，来源结构变更记录 `source_schema_version`。
4. 大批量接入改为后台任务、游标分页和批量 upsert；当前同步 API 仅用于测试切片。
5. PostgreSQL 16 是客户环境目标数据库；SQLite 仅用于无 Docker 的单机开发。
6. 上层驾驶舱、分析、分身和 MCP 只依赖统一实体与指标契约，不读取供应商字段。
7. 指标历史按 `来源 + 指标键 + 范围键 + 数据时点` 幂等写入；API 与 MCP 使用同一日粒度序列服务，不由前端补点或生成随机趋势。
8. 客户主档、客户触点和订单/退款分别声明权威事实族；部分资源失败不得清理未成功读取的事实族。
9. 客户页面和 `query_customer_360` MCP 都通过 `customer.profile.read` 与平台范围映射访问统一服务，不直接读取 CRM 私有字段。
10. 单客基础建议由版本化确定性 Playbook 生成；AI 方案运行必须先冻结当前授权范围内的主档、汇总、订单、退款与触点，并只接受命中本次 `E*` 快照的引用。
11. 客户运营模型输出只是内部方案。服务端固定 `requires_human_approval=true`、`external_write_allowed=false`，自动消息、发券积分、退款补偿承诺和第三方写回不属于当前动作类型。
12. 模型失败、结构不合法或证据越界时回退确定性 Playbook；运行仍保存范围、执行主体、证据哈希、模型、Token、耗时和降级原因，不能静默伪装为模型成功。
13. 经营分析建议只能由具备 `action.propose` 且覆盖运行范围的主体选择送审；提案按运行和建议序号唯一，不由前端拼装另一套工作对象。
14. 行动批准后创建企业内部工作项；员工只能承接授权范围内的工作并更新本人项目，经理通过 `action.work.manage` 处理释放、重开和跨人调整。
15. 工作状态变化必须同时校验乐观版本和幂等键，并追加不可变事件；工作项不是第三方写入凭证，`ActionExecution.external_write` 在当前切片始终为 `false`。
16. 自动巡店计划只保存平台范围键和业务时间规则；调度器只负责幂等入队，Worker 执行时必须重新验证创建主体的当前账号、分析权限和数据范围。
17. 定时分析复用人工诊断的指标/规范事实查询和证据快照，不允许计划表保存一份经营数值副本。自动建议最多进入 `pending_approval`，不得绕过职责分离审批或直接写外部系统。
