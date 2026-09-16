# ADR-018：通用行动来源与内部审批台账

- 日期：2026-08-30
- 状态：accepted
- 关联迁移：`0034_generalized_action_sources`

## 背景

行动中心最初只消费数字会议确认后的决策包，`ActionProposal` 因此强制关联会议和 `DecisionPackage`。客户运营方案同样需要把经过人工选择的模型步骤送入职责分离审批；如果在客户领域复制一套审批和执行表，权限、幂等和审计会出现两套真值。

## 决策

1. `ActionProposal` 增加 `source_type`、`source_key`、`source_label`、`source_action_index`、`scope_type`、`scope_key` 和可选 `evidence_snapshot_id`，统一表达来源与授权边界。
2. 首批来源为 `meeting-decision` 与 `customer-operation`。会议外键/决策包外键和客户运营运行外键均可空，但每条提案只能由领域服务填入与来源一致的一组关联。
3. 既有会议提案迁移时回填来源标题和会议对象范围，不改提案键、审批事件、执行记录或幂等键。
4. 客户运营步骤按 `customer_operation_run_id + source_action_index` 唯一。相同截止要求重复提交返回原提案，改变已提议步骤的截止要求返回冲突。
5. 创建客户提案要求 `action.propose` 与运行范围；列表按当前主体企业和范围过滤；批准继续要求 `action.approve`，且发起人与审批人必须分离。
6. 批准只创建 `external_write=false` 的内部 `ActionExecution`。来源业务不能直接调用第三方工具，也不能把模型步骤当作批准结论。

## 后果

- 数字会议、客户运营和未来经营分析/巡店工作流可以复用同一审批与审计模型，不复制行动真值。
- 行动中心可以显示来源类型、来源标题、范围、证据、KPI、停止条件和返回来源页面的链接。
- 迁移降级会先删除客户运营来源的提案及其内部审批/执行记录，再恢复会议外键非空约束；正式环境降级前必须先导出相关审计数据。
- 当前实现仍是纵向切片，不代表外部任务系统、飞书审批、失败补偿或正式 `ACT-*` 任务已经完成。
