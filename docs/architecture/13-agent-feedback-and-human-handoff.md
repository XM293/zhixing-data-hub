# 回答反馈与人工接管

关联任务：`TWI-003`、`TWI-006`、`AGT-003`、`IAM-004`

## 1. 目标与边界

分身回答完成后，调用者可以记录“有帮助”、事实不准确、回答不完整、风险建议、范围问题或人工接管请求。除“有帮助”外的反馈创建人工接管工单，由具备审核权限的负责人认领、追加处理记录、解决或重开。

反馈闭环不会自动修改制度版本、角色记忆、分身配置、Prompt、评测集或外部系统。处理结论先作为可追溯的人类事件回传，后续再由各领域的正式审核流程决定是否变更业务真值。

## 2. 数据模型

迁移 `0021_agent_feedback_and_handoff` 增加：

| 对象 | 作用 | 关键约束 |
| --- | --- | --- |
| `agent_runs.actor_principal_id` | 保存实际提问主体 | 新问答必须写入，旧运行允许为空 |
| `agent_feedback_events` | 追加式反馈和处理事件 | 企业内 `idempotency_key` 唯一，不覆盖历史 |
| `human_handoff_cases` | 当前接管状态投影 | 同一提问人对同一运行最多一个工单 |

工单可以改变当前状态和处理人；每次状态变化同时追加事件，因此可以重建处理过程。解决工单时必须保存处理类型和可回传给提问人的正式结论。

## 3. 授权模型

- `agent-feedback.submit`：仅能反馈自己发起的 `AgentRun`，并查看自己的接管结果。
- `agent-feedback.review`：查看企业反馈队列，认领、记录、解决和重开工单。
- 员工不能通过已知运行 ID 读取其他员工的反馈；负责人读取队列同样留下授权决策审计。
- RoleTwin 不能替调用者提升反馈或处理权限。

## 4. API 与界面

| API | 权限 | 作用 |
| --- | --- | --- |
| `POST /api/v1/agent-runs/{run_id}/feedback` | `agent-feedback.submit` | 点赞、纠错或创建接管工单 |
| `GET /api/v1/agent-runs/{run_id}/feedback` | 提交者或审核者 | 查看单次运行反馈和工单状态 |
| `GET /api/v1/agent-feedback/mine` | `agent-feedback.submit` | 查看当前提问人的历史处理结果 |
| `GET /api/v1/agent-feedback/studio` | `agent-feedback.review` | 查看企业接管队列与统计 |
| `POST /api/v1/agent-feedback/cases/{case_id}/actions` | `agent-feedback.review` | 认领、追加记录、解决或重开 |

企业助手在回答下提供三个明确动作，并在侧栏显示“我的反馈”。`/console/twins/feedback` 是负责人工作台，展示原始问题、原始回答、分身版本、提问人、处理人、人工结论和完整事件链。

## 5. 首期验收

真实员工身份调用已发布分身后可以创建紧急接管工单；部门经理能够认领并解决；员工重新进入助手仍能看到人工处理结论。重复提交相同幂等键不会新增事件，普通员工不能打开企业反馈队列或处理工单。

这一纵向切片不代表 `TWI-006` 全部完成。飞书卡片反馈、正式渠道身份、SLA 通知、纠错转评测集以及跨领域变更审批仍受渠道、评测和正式 IAM 任务约束。
