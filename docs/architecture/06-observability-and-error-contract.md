# 追踪上下文、结构化日志与错误契约

- 任务：`FND-008`
- 状态：Implemented / Accepted
- 契约版本：1

## 追踪模型

`request_id` 标识一次入口请求；`run_id` 标识一次可跨请求、后台任务、Agent、MCP 和 Action 的业务运行。入口缺少有效 ID 时自行生成，已有有效 ID 时原样传播。

HTTP 使用 `X-Request-ID` 与 `X-Run-ID`。API 在所有成功和失败响应中返回两者，并通过 CORS 暴露。后台任务消息和工具调用以后直接携带相同字段，不从日志文本反向解析。

Web 通过统一 `apiFetch` 入口为每次请求生成 `request_id`，并在当前浏览器会话中保持 `run_id`，使页面加载、同步操作和会议操作可以在 API 日志中连续定位。调用方传入的合法上下文会被保留，无效 ID 会在 Web 与 API 两侧分别校验并替换。未来 Worker、Agent Runtime 和 MCP 网关必须显式从任务消息或工具调用参数继承 `run_id`，不能用线程名或用户 ID 代替。

`packages/observability` 只提供 ID、`ContextVar` 上下文和 JSON 事件，不依赖 FastAPI。API 中间件位于入口适配层；领域服务可以读取当前上下文，但不能信任客户端提交的身份或授权范围。

## 错误 Envelope

所有 API 错误返回：

```json
{
  "schema_version": 1,
  "error": {
    "code": "authorization.denied",
    "message": "没有访问范围",
    "status": 403,
    "request_id": "req_...",
    "run_id": "run_...",
    "retryable": false,
    "details": {}
  }
}
```

`code` 是稳定机器语义，`message` 是可展示文本。参数验证只返回字段位置、类型和说明，不回显原始输入。未处理异常不把堆栈、数据库消息或凭据返回客户端。

401 与 403 使用同一 Envelope，但语义严格区分：未认证为 `auth.unauthenticated`，已认证无权为 `authorization.denied`。

## 日志边界

结构化事件至少包含 UTC 时间、级别、事件名、`request_id` 和 `run_id`。允许记录稳定主体、资源、状态、耗时和计数；禁止记录 API Key、Cookie、Authorization、Prompt 原文、制度全文或客户原始记录。

## 统一审计检索

运行日志、授权审计和领域追加式事件保持各自真值边界。统一审计中心只在读取时归一化以下来源，不把它们复制进通用日志表：

- 授权决策与身份目录变更；
- MCP 会话与工具调用；
- Worker 后台任务与 AgentRun；
- 行动工作状态事件。

统一事件固定企业、来源、事件类型、结果、主体、业务对象、时间、耗时以及可选 `request_id`、`run_id`、`agent_run_id`。来源特有属性只能从服务端允许清单生成；禁止返回令牌或哈希、Cookie、Prompt、Agent 回答、工具完整输入输出、后台任务载荷、客户原始数据、主体快照、配置前后快照和任意 `details` 对象。全文检索只作用于已经进入统一投影的非敏感摘要与稳定键。

平台管理员通过 `audit.event.read` 和企业范围读取 `/api/v1/audit/events`。来源、结果和主体 Facet 使用同一企业边界和其余筛选条件；分页上限为 100。前端使用统一追踪 ID 精确下钻，不能通过浏览器提交企业覆盖值或扩大查询范围。
